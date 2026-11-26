"""Agent planner: na podstawie mapy projektu planuje pracę zespołu, zanim ktokolwiek przeczyta kod.

Co robi: create_plan() składa prompt plannera (mapa projektu jako JSON bez ścieżki bezwzględnej i bez kodu
źródłowego, ale z dosłowną treścią plików zależności, konfiguracji i uruchamiających; spis bazy wiedzy),
wywołuje model agenta planner ze schematem Plan (schemas.py) i poprawia odpowiedź zwykłym kodem
(complete_plan). planner_node() to węzeł grafu: tworzy plan, zapisuje go jako plan.json i dopisuje do stanu.

Co jest w planie (szczegóły w schemas.Plan): podsumowanie robota, zadania dla analityków (po jednym na każdą
jednostkę kodu, z wskazówką, w kolejności czytania) i pliki bazy wiedzy osobno dla analityków, autora diagramu
i pisarzy.

Co poprawia kod po odpowiedzi modelu (complete_plan), z listą uwag:
    - zadanie z jednostką, której nie ma w mapie projektu - usuwa,
    - zadanie powtórzone dla tej samej jednostki - zostawia pierwsze,
    - jednostkę z mapy, której planner nie ujął - dopisuje na końcu z pustą wskazówką (analizujemy wszystko),
    - plik wiedzy spoza spisu bazy wiedzy albo powtórzony - usuwa z listy.

Dlaczego istnieje: planner widzi cały projekt i przekazuje kolejnym agentom to, czego pojedynczy analityk nie
wie (miejsce jednostki w robocie, długie funkcje, kontakty z systemami, hasła w plikach) oraz wybiera dla
każdej grupy agentów tylko potrzebne pliki wiedzy. Model może się pomylić w nazwie albo pominąć jednostkę, a
żaden fragment robota nie może zniknąć z przewodnika po cichu, więc zgodność planu z mapą i spisem
zapewnia kod, a każdą poprawkę zgłasza jako uwagę (linia postępu).

Rola: agent fazy F; węzeł planner do grafu dołącza krok 48.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.agents.planner
        bez modelu i bez sieci: prompt (mapa bez ścieżki i kodu, z treścią konfiguracji, spis bazy wiedzy),
        poprawianie planu (nieznana, powtórzona i pominięta jednostka, nieznany i powtórzony plik wiedzy)
        oraz węzeł planner z udawanym modelem (plan.json, linie postępu); na końcu "zgodne z oczekiwaniem: True".
    python -m dev_agents.agents.planner <katalog robota>
        dodatkowo prawdziwy model plannera: czyta <katalog robota>/dev_agents_doc/project_map.json (najpierw
        python main.py --project <katalog robota> --render-only), zapisuje plan.json w tym samym katalogu wyników
        i wypisuje plan; wymaga zmiennych z kluczem i adresem modeli (nazwy w config.yaml).
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

import dev_agents.context as _context
import dev_agents.knowledge as _knowledge
import dev_agents.llm as _llm
import dev_agents.progress as _progress
import dev_agents.prompts as _prompts
import dev_agents.schemas as _schemas
import dev_agents.state as _state

_AGENT_NAME = "planner"


# --- Poprawianie planu ---


def _clean_knowledge(
    names: list[str],
    allowed: list[str],
    group: str,
    notes: list[str],
) -> list[str]:
    """Zwraca listę plików wiedzy bez nazw spoza spisu i bez powtórzeń; każde usunięcie dopisuje do notes.

    Po co: nazwę pliku wybiera model, więc literówka albo wymyślony plik nie może trafić do dalszych etapów
    (read_kb_file i tak odrzuciłby taki plik, ale wolimy zgłosić to od razu przy planie).

    Argumenty: allowed - nazwy plików ze spisu bazy wiedzy, group - nazwa grupy agentów do komunikatu.
    """
    czysta_lista = []
    for nazwa in names:
        if nazwa not in allowed:
            notes.append(f"usunięto plik wiedzy '{nazwa}' ({group}): nie ma go w spisie bazy wiedzy")
        elif nazwa in czysta_lista:
            notes.append(f"usunięto powtórzony plik wiedzy '{nazwa}' ({group})")
        else:
            czysta_lista.append(nazwa)
    return czysta_lista


def complete_plan(
    plan: _schemas.Plan,
    project_map: _schemas.ProjectMap,
    kb_index: list[_knowledge.KBEntry],
) -> tuple[_schemas.Plan, list[str]]:
    """Zwraca (poprawiony plan, lista uwag o poprawkach): zadania tylko dla jednostek z mapy, każda dokładnie raz, pliki wiedzy tylko ze spisu.

    Po co: gwarancja, że analizujemy wszystkie jednostki robota i że dalsze etapy dostają tylko istniejące
    nazwy; nic nie znika po cichu - każda poprawka trafia do uwag.

    Uwaga: kolejność zadań zostaje taka, jak ułożył planner; jednostki pominięte przez plannera są dopisywane na końcu.
    """
    uwagi = []
    nazwy_jednostek = []
    for jednostka in project_map.code_units:
        nazwy_jednostek.append(jednostka.name)
    zadania = []
    uzyte_jednostki = []
    for zadanie in plan.tasks:
        if zadanie.unit not in nazwy_jednostek:
            uwagi.append(f"usunięto zadanie dla nieznanej jednostki '{zadanie.unit}'")
        elif zadanie.unit in uzyte_jednostki:
            uwagi.append(f"usunięto powtórzone zadanie dla jednostki '{zadanie.unit}'")
        else:
            zadania.append(zadanie)
            uzyte_jednostki.append(zadanie.unit)
    for nazwa in nazwy_jednostek:
        if nazwa not in uzyte_jednostki:
            zadania.append(_schemas.AnalysisTask(unit=nazwa))
            uwagi.append(f"dopisano jednostkę '{nazwa}' bez wskazówki: planner jej nie ujął")
    nazwy_plikow = []
    for wpis in kb_index:
        nazwy_plikow.append(wpis.filename)
    poprawiony_plan = plan.model_copy(
        update={
            "tasks": zadania,
            "analyst_knowledge": _clean_knowledge(plan.analyst_knowledge, nazwy_plikow, "analitycy", uwagi),
            "flow_knowledge": _clean_knowledge(plan.flow_knowledge, nazwy_plikow, "autor diagramu", uwagi),
            "writer_knowledge": _clean_knowledge(plan.writer_knowledge, nazwy_plikow, "pisarze", uwagi),
        }
    )
    wynik = (poprawiony_plan, uwagi)
    return wynik


# --- Planowanie ---


def build_planner_variables(
    project_map: _schemas.ProjectMap,
    kb_index: list[_knowledge.KBEntry],
) -> dict:
    """Zwraca zmienne do szablonu prompts/planner/user.md: nazwę projektu, mapę projektu i spis bazy wiedzy jako JSON.

    Po co: w jednym miejscu widać, co dokładnie planner dostaje. Mapa idzie bez ścieżki bezwzględnej katalogu
    (nazwa użytkownika i układ dysku nie są modelowi potrzebne), bez kodu źródłowego (mapa go nie zawiera), ale
    z dosłowną treścią plików zależności, konfiguracji i uruchamiających. JSON bez zamiany polskich znaków na kody
    (ensure_ascii=False), żeby model i człowiek widzieli zwykły tekst.
    """
    dane_mapy = project_map.model_dump(exclude={"root"})
    dane_spisu = []
    for wpis in kb_index:
        dane_spisu.append(wpis.model_dump())
    zmienne_promptu = {
        "project_name": project_map.project_name,
        "project_map": json.dumps(dane_mapy, indent=2, ensure_ascii=False),
        "kb_index": json.dumps(dane_spisu, indent=2, ensure_ascii=False),
    }
    return zmienne_promptu


def create_plan(
    project_map: _schemas.ProjectMap,
    context: _context.RunContext,
) -> tuple[_schemas.Plan, list[str]]:
    """Tworzy plan dla projektu: składa prompt, wywołuje model agenta planner ze schematem Plan i poprawia odpowiedź; zwraca (plan, uwagi).

    Po co: cała logika plannera w jednej funkcji, z której korzysta węzeł grafu i test ręczny. invoke_structured
    (llm.py) każe modelowi odpowiedzieć zgodnie ze schematem Plan (metoda z profilu agenta w config.yaml); brak
    odpowiedzi zgodnej ze schematem kończy się błędem z przyczyną. Potem complete_plan zapewnia zgodność z mapą i spisem.
    """
    zmienne = build_planner_variables(project_map, context.knowledge_index)
    tekst_system, tekst_user = _prompts.render_prompt(context.config.paths.prompts, _AGENT_NAME, zmienne)
    odpowiedz = _llm.invoke_structured(
        context.models[_AGENT_NAME],
        _schemas.Plan,
        _llm.get_structured_output_method(context.config, _AGENT_NAME),
        [SystemMessage(content=tekst_system), HumanMessage(content=tekst_user)],
    )
    wynik = complete_plan(odpowiedz, project_map, context.knowledge_index)
    return wynik


# --- Węzeł grafu ---


def planner_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Węzeł planner: tworzy plan dla mapy projektu ze stanu, zapisuje plan.json i zwraca zmienione pole stanu: plan.

    Po co: drugi etap przebiegu - plan decyduje, jakie zadania dostaną analitycy i jaką wiedzę dostaną kolejni agenci.
    Praca węzła jest owinięta w Stage (progress.py): start, uwagi o poprawkach planu, koniec z czasem i liczbą zadań.
    """
    kontekst = runtime.context
    with _progress.Stage(kontekst.report, _AGENT_NAME) as etap:
        plan, uwagi = create_plan(state["project_map"], kontekst)
        for uwaga in uwagi:
            etap.note(f"uwaga: {uwaga}")
        zapisany_plik = kontekst.store.save_json("plan.json", plan)
        etap.set_result(f"zadań: {len(plan.tasks)}, zapisano {zapisany_plik}")
    zmiana_stanu = {"plan": plan}
    return zmiana_stanu


# --- Wyświetlanie ---


def print_plan(
    plan: _schemas.Plan,
) -> None:
    """Wypisuje plan: podsumowanie, zadania analityków ze wskazówkami i listy plików wiedzy.

    Po co: przy teście ręcznym widać od razu, czy planner zrozumiał projekt i czy uwzględnił wszystkie jednostki.
    """
    print("=== Plan ===\n")
    print(plan.summary)
    print(f"\nZadania analityków: {len(plan.tasks)}")
    for zadanie in plan.tasks:
        print(f"  {zadanie.unit}")
        print(f"    {zadanie.hint}")
    print(f"\nPliki wiedzy - analitycy:      {plan.analyst_knowledge}")
    print(f"Pliki wiedzy - autor diagramu: {plan.flow_knowledge}")
    print(f"Pliki wiedzy - pisarze:        {plan.writer_knowledge}")


# --- Test ręczny ---

if __name__ == "__main__":
    import os
    import shutil
    import sys
    import tempfile
    import types

    from langchain_core.messages import AIMessage

    import dev_agents.config as _config
    import dev_agents.guide_template as _guide_template
    import dev_agents.output as _output
    import dev_agents.scanner as _scanner

    _SOURCE_MARKER = "KOD_ZRODLOWY_MARKER"
    _CONFIG_LINE = "ustawienie_testowe: 42"

    class _FakeModel:
        """Udawany model: zapamiętuje wiadomości i zawsze zwraca ten sam, gotowy plan w kształcie odpowiedzi invoke_structured.

        Po co: sprawdzenie plannera bez sieci i kluczy.
        """

        def __init__(
            self,
            plan: _schemas.Plan,
        ):
            """Zapamiętuje plan do zwrócenia i zeruje licznik wywołań oraz ostatnie wiadomości.

            Po co: test sprawdza, ile razy i z czym model został zawołany.
            """
            self.plan = plan
            self.calls = 0
            self.messages = []

        def with_structured_output(
            self,
            schema,
            method=None,
            include_raw=False,
        ):
            """Zwraca samego siebie - udaje model ze schematem odpowiedzi.

            Po co: invoke_structured woła with_structured_output, a potem invoke.
            """
            return self

        def invoke(
            self,
            messages,
        ):
            """Zapamiętuje wiadomości i zwraca poprawną odpowiedź z gotowym planem.

            Po co: odtwarza kształt odpowiedzi prawdziwego modelu z include_raw=True.
            """
            self.calls += 1
            self.messages = messages
            odpowiedz = {"raw": AIMessage(content="{}"), "parsed": self.plan, "parsing_error": None}
            return odpowiedz

    def _write_temp_project(
        temp_dir: str,
    ) -> str:
        """Tworzy mały projekt w Pythonie z dwoma plikami kodu, konfiguracją i zależnościami; zwraca jego ścieżkę.

        Po co: test działa bez robotów testowych; znaczniki w kodzie i w konfiguracji pozwalają sprawdzić, co trafia do promptu.
        """
        projekt = os.path.join(temp_dir, "maly_robot")
        os.makedirs(projekt)
        pliki = {
            "main.py": f"import helper\n\n\ndef run():\n    znacznik = '{_SOURCE_MARKER}'\n    return helper.pomoc(znacznik)\n\n\nif __name__ == '__main__':\n    run()\n",
            "helper.py": "def pomoc(x):\n    return x\n",
            "config.yaml": f"{_CONFIG_LINE}\n",
            "requirements.txt": "requests\n",
        }
        for nazwa, tresc in pliki.items():
            with open(os.path.join(projekt, nazwa), "w", encoding="utf-8") as plik:
                plik.write(tresc)
        return projekt

    def _unit_names(
        project_map: _schemas.ProjectMap,
    ) -> list[str]:
        """Zwraca nazwy jednostek kodu z mapy projektu w kolejności mapy.

        Po co: testy układają plany i oczekiwania z nazw jednostek prawdziwej mapy, bez wpisywania ich na sztywno.
        """
        nazwy = []
        for jednostka in project_map.code_units:
            nazwy.append(jednostka.name)
        return nazwy

    def _messy_plan(
        unit_names: list[str],
    ) -> _schemas.Plan:
        """Składa plan z pięcioma błędami: nieznana jednostka, powtórzona jednostka, pominięta jednostka, nieznany i powtórzony plik wiedzy.

        Po co: udawany model zwraca plan, który complete_plan musi poprawić i zgłosić.
        """
        zadania = [
            _schemas.AnalysisTask(unit=unit_names[0], hint="punkt wejścia"),
            _schemas.AnalysisTask(unit="nie_ma_takiego.py", hint="wymyślona jednostka"),
            _schemas.AnalysisTask(unit=unit_names[0], hint="powtórka"),
        ]
        zepsuty_plan = _schemas.Plan(
            summary="Mały robot testowy.",
            tasks=zadania,
            analyst_knowledge=["nie_ma_takiego_pliku.md"],
            flow_knowledge=["diagram_rules.md", "diagram_rules.md"],
            writer_knowledge=["guide_goals.md"],
        )
        return zepsuty_plan

    def _prompt_checks(
        project_map: _schemas.ProjectMap,
        app_config: _config.AppConfig,
        kb_index: list[_knowledge.KBEntry],
    ) -> list[tuple[str, bool]]:
        """Sprawdza prompt plannera: mapa bez ścieżki bezwzględnej i bez kodu, z treścią konfiguracji, ze spisem bazy wiedzy; zwraca (opis, zgodne).

        Po co: ważne zasady (cudzy kod nie wychodzi do modelu, ścieżka dysku też nie) sprawdzane na prawdziwym promptcie.
        """
        zmienne = build_planner_variables(project_map, kb_index)
        tekst_system, tekst_user = _prompts.render_prompt(app_config.paths.prompts, _AGENT_NAME, zmienne)
        wyniki = [
            ("prompt: system i user niepuste, user ma tagi mapy i spisu", bool(tekst_system) and "<mapa_projektu>" in tekst_user and "<spis_bazy_wiedzy>" in tekst_user),
            ("prompt: mapa bez ścieżki bezwzględnej projektu", project_map.root not in tekst_user),
            ("prompt: nazwa projektu w treści", project_map.project_name in tekst_user),
            ("prompt: treść konfiguracji przepisana dosłownie", _CONFIG_LINE in tekst_user),
            ("prompt: bez kodu źródłowego", _SOURCE_MARKER not in tekst_user),
            ("prompt: spis bazy wiedzy z plikami", "guide_goals.md" in tekst_user and "diagram_rules.md" in tekst_user),
        ]
        return wyniki

    def _complete_checks(
        project_map: _schemas.ProjectMap,
        kb_index: list[_knowledge.KBEntry],
    ) -> list[tuple[str, bool]]:
        """Sprawdza complete_plan na planie z błędami: zadania i pliki wiedzy po poprawce oraz liczba i treść uwag; zwraca (opis, zgodne).

        Po co: gwarancja, że każda jednostka jest analizowana dokładnie raz i że poprawki są zgłoszone.
        """
        nazwy = _unit_names(project_map)
        poprawiony, uwagi = complete_plan(_messy_plan(nazwy), project_map, kb_index)
        jednostki_po = []
        for zadanie in poprawiony.tasks:
            jednostki_po.append(zadanie.unit)
        wyniki = [
            ("poprawka: jednostki = jednostki z mapy, każda raz, pierwsza zostaje na początku", sorted(jednostki_po) == sorted(nazwy) and jednostki_po[0] == nazwy[0]),
            ("poprawka: wskazówka pierwszego zadania zachowana", poprawiony.tasks[0].hint == "punkt wejścia"),
            ("poprawka: dopisana jednostka ma pustą wskazówkę", poprawiony.tasks[-1].hint == ""),
            ("poprawka: nieznany plik wiedzy usunięty", poprawiony.analyst_knowledge == []),
            ("poprawka: powtórzony plik wiedzy usunięty", poprawiony.flow_knowledge == ["diagram_rules.md"]),
            ("poprawka: poprawny plik wiedzy zostaje", poprawiony.writer_knowledge == ["guide_goals.md"]),
            ("poprawka: podsumowanie bez zmian", poprawiony.summary == "Mały robot testowy."),
            ("poprawka: pięć uwag", len(uwagi) == 5),
        ]
        return wyniki

    def _node_checks(
        project_map: _schemas.ProjectMap,
        app_config: _config.AppConfig,
        kb_index: list[_knowledge.KBEntry],
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza węzeł planner z udawanym modelem: stan, plan.json, wywołanie modelu i linie postępu; zwraca (opis, zgodne).

        Po co: cały węzeł (prompt, model, poprawianie, zapis, postęp) w jednym przebiegu bez sieci.
        """
        nazwy = _unit_names(project_map)
        model = _FakeModel(_messy_plan(nazwy))
        linie = []
        magazyn = _output.create_run_store(temp_dir)
        kontekst = _context.RunContext(
            config=app_config,
            store=magazyn,
            models={_AGENT_NAME: model},
            knowledge_index=kb_index,
            template=_guide_template.load_template(app_config.paths.guide_template),
            report=linie.append,
        )
        zmiana = planner_node({"project_map": project_map}, types.SimpleNamespace(context=kontekst))
        plan_ze_stanu = zmiana["plan"]
        plan_z_pliku = magazyn.load_json("plan.json", _schemas.Plan)
        nazwy_wiadomosci = []
        for wiadomosc in model.messages:
            nazwy_wiadomosci.append(type(wiadomosc).__name__)
        uwagi_w_liniach = 0
        for linia in linie:
            if "planner: uwaga: " in linia:
                uwagi_w_liniach += 1
        wyniki = [
            ("węzeł: zwraca tylko pole plan", list(zmiana.keys()) == ["plan"]),
            ("węzeł: plan.json równy planowi ze stanu", plan_z_pliku == plan_ze_stanu),
            ("węzeł: plan po poprawkach ma tyle zadań co jednostek", len(plan_ze_stanu.tasks) == len(nazwy)),
            ("węzeł: model zawołany raz, wiadomości system i człowiek", model.calls == 1 and nazwy_wiadomosci == ["SystemMessage", "HumanMessage"]),
            ("postęp: pierwsza linia to start", linie[0].endswith("] planner: start")),
            ("postęp: pięć linii z uwagami", uwagi_w_liniach == 5),
            ("postęp: ostatnia linia to koniec z czasem i liczbą zadań", "] planner: gotowe w " in linie[-1] and "zadań: " in linie[-1]),
        ]
        for linia in linie:
            print(f"    {linia}")
        return wyniki

    def _real_model_run(
        project_dir: str,
        app_config: _config.AppConfig,
    ) -> None:
        """Czyta mapę z <katalog robota>/dev_agents_doc/project_map.json, woła prawdziwy model plannera przez węzeł i wypisuje plan.

        Po co: sprawdzenie plannera na prawdziwym robocie i prawdziwym modelu; plan.json trafia do tego samego katalogu wyników.
        """
        magazyn = _output.create_run_store(project_dir, clear=False)
        if not os.path.isfile(magazyn.path("project_map.json")):
            sys.exit(f"BŁĄD: brak {magazyn.path('project_map.json')} - najpierw: python main.py --project {project_dir} --render-only")
        project_map = magazyn.load_json("project_map.json", _schemas.ProjectMap)
        try:
            kontekst = _context.build_context(app_config, magazyn, _progress.print_line)
        except (RuntimeError, ValueError, OSError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        print("\n=== Prawdziwy model plannera ===")
        zmiana = planner_node({"project_map": project_map}, types.SimpleNamespace(context=kontekst))
        print()
        print_plan(zmiana["plan"])

    def manual_test():
        """Sprawdza prompt, poprawianie planu i węzeł na udawanym modelu; z argumentem (katalog robota) woła też prawdziwy model.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że planner działa zgodnie z opisem, a część z modelem pokazuje plan na prawdziwym robocie.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        kb_index = _knowledge.load_index(app_config.paths.knowledge_base)
        temp_dir = tempfile.mkdtemp()
        try:
            projekt = _write_temp_project(temp_dir)
            project_map = _scanner.build_project_map(projekt, app_config.scan)
            print(f"Projekt testowy: technologia {project_map.technology}, jednostki {_unit_names(project_map)}")
            wyniki = []
            wyniki.extend(_prompt_checks(project_map, app_config, kb_index))
            wyniki.extend(_complete_checks(project_map, kb_index))
            print("\n=== Linie postępu węzła z udawanym modelem ===")
            wyniki.extend(_node_checks(project_map, app_config, kb_index, temp_dir))
        finally:
            shutil.rmtree(temp_dir)
        print("\n=== Sprawdzenia ===")
        wszystkie_zgodne = True
        for opis, zgodne in wyniki:
            print(f"  {opis}: {zgodne}")
            if not zgodne:
                wszystkie_zgodne = False
        print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
        if len(sys.argv) > 1:
            _real_model_run(os.path.abspath(sys.argv[1]), app_config)

    manual_test()
