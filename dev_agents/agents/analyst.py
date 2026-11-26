"""Agent analityk: czyta kod jednej jednostki i zwraca notatkę ModuleNote (bez grafu).

Co robi: dla zadania z planu (AnalysisTask) składa prompt z pełnym kodem jednostki (każda linia z numerem),
faktami o plikach jednostki i jej powiązaniach, plikami tekstowymi robota (zależności, konfiguracja, pliki
uruchamiające - dosłownie, z numerami linii), podsumowaniem i wskazówką plannera oraz wiedzą (technologia,
frameworki, pliki wybrane przez plannera), woła model agenta analyst DWA razy (schemat NoteFlow: przebieg jednostki,
potem NoteDetails: ustawienia, wymagania, ryzyka - ten sam kod, inna część notatki), składa odpowiedzi w ModuleNote
i poprawia ją: nazwa jednostki jest zawsze z zadania, a numer linii czynności spoza pliku (też ujemny) zamieniany jest
na 0. Każda poprawka jest zgłaszana jako uwaga.

Dlaczego istnieje: analityk jest jedynym agentem, który czyta kod - jego notatka to surowiec dla autora diagramu
i wszystkich pisarzy. Numery linii w kodzie sprawiają, że odwołania w notatce (funkcja, linia) są dokładne, a nie
policzone przez model "na oko". Pliki o roli secret nigdy nie są czytane, a plik większy niż analysis.max_file_size_kb
kończy się ValueError z nazwą pliku (czytanie dużych plików po kawałkach dochodzi w kroku 51). Notatka jest zwracana
w dwóch odpowiedziach, bo bramka odrzuca schematy powyżej 48 pól, a cała notatka ma ich 54 (pomiar: scripts/probe_schema.py).

Czego NIE robi: nie jest węzłem grafu (równoległych analityków dokłada krok 52), niczego nie zapisuje na dysku,
nie dzieli długich plików na kawałki (krok 51).

Rola: agent grafu (faza F); wołają go węzeł analityków (krok 52) i test ręczny.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.agents.analyst
        offline, na udawanym modelu: prompt (kod z numerami linii, plik konfiguracyjny z numerami, wiedza technologii,
        wskazówka plannera, brak ścieżki dysku), odmowa czytania pliku sekretu, odmowa dla pliku większego niż limit,
        nieznana jednostka, dwa wywołania modelu (część 1 i część 2 notatki), składanie notatki, poprawianie notatki
        z dwoma błędami; na końcu "zgodne z oczekiwaniem: True"
    python -m dev_agents.agents.analyst <katalog robota> <nazwa jednostki>
        dodatkowo woła PRAWDZIWY model: skanuje robota w pamięci, bierze plan z <katalog robota>/dev_agents_doc/plan.json
        (gdy go nie ma - plan minimalny), wypisuje notatkę jako JSON i ostrzeżenia o liniach; NICZEGO nie zapisuje
        (można podać robota 01 - czytany jest tylko kod jednostki i pliki tekstowe, nie pliki sekretów).
        Wymaga zmiennych środowiskowych z kluczem i adresem modeli (nazwy w config.yaml).
"""

import json
import os

from langchain_core.messages import HumanMessage, SystemMessage

import dev_agents.agents.common as _common
import dev_agents.context as _context
import dev_agents.files as _files
import dev_agents.llm as _llm
import dev_agents.prompts as _prompts
import dev_agents.schemas as _schemas

_AGENT_NAME = "analyst"

# Części notatki: (plik z opisem części w prompts/analyst, schemat odpowiedzi modelu). Kolejność = kolejność wywołań.
_NOTE_PARTS = [
    ("part_flow.md", _schemas.NoteFlow),
    ("part_details.md", _schemas.NoteDetails),
]


# --- Dane dla promptu ---


def find_unit(
    project_map: _schemas.ProjectMap,
    unit_name: str,
) -> _schemas.CodeUnit:
    """Zwraca jednostkę kodu o podanej nazwie z mapy projektu; nieznana nazwa - ValueError z listą znanych nazw.

    Po co: zadanie z planu wskazuje jednostkę po nazwie, a analityk potrzebuje jej plików.
    """
    nazwy = []
    for jednostka in project_map.code_units:
        if jednostka.name == unit_name:
            return jednostka
        nazwy.append(jednostka.name)
    komunikat_bledu = f"Nieznana jednostka kodu '{unit_name}'. Jednostki w mapie projektu: {nazwy}"
    raise ValueError(komunikat_bledu)


def read_unit_code(
    project_map: _schemas.ProjectMap,
    unit: _schemas.CodeUnit,
    max_file_size_kb: int,
) -> tuple[str, int]:
    """Zwraca (kod jednostki z numerami linii w znacznikach <plik>, największa liczba linii wśród plików jednostki).

    Po co: analityk dostaje pełny kod każdego pliku jednostki; liczba linii służy do sprawdzenia numerów linii
    w odpowiedzi. Plik spoza mapy, plik o roli secret (nigdy nie czytany) i plik większy niż limit w KB kończą
    się ValueError z nazwą pliku - nic nie jest czytane po cichu ani przycinane.
    """
    wpisy = {}
    for wpis in project_map.files:
        wpisy[wpis.path] = wpis
    bloki = []
    najwiecej_linii = 0
    for sciezka in unit.files:
        wpis = wpisy.get(sciezka)
        if wpis is None:
            raise ValueError(f"Plik jednostki '{unit.name}' nie jest w mapie projektu: {sciezka}")
        if wpis.role == "secret":
            raise ValueError(f"Plik jednostki '{unit.name}' ma rolę secret i nie jest czytany: {sciezka}")
        if wpis.size_bytes > max_file_size_kb * 1024:
            raise ValueError(
                f"Plik {sciezka} ma {wpis.size_bytes} B - więcej niż analysis.max_file_size_kb ({max_file_size_kb} KB); "
                "czytanie dużych plików po kawałkach dochodzi w kroku 51"
            )
        tekst = _files.read_text_safe(os.path.join(project_map.root, *sciezka.split("/")))
        liczba_linii = _common.count_lines(tekst)
        if liczba_linii > najwiecej_linii:
            najwiecej_linii = liczba_linii
        bloki.append(f'<plik sciezka="{sciezka}" linii="{liczba_linii}">\n{_common.number_lines(tekst)}\n</plik>')
    kod = "\n\n".join(bloki)
    wynik = (kod, najwiecej_linii)
    return wynik


def format_text_files(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca pliki tekstowe robota (zależności, konfiguracja, uruchamiające) dosłownie, z numerami linii, w znacznikach <plik_tekstowy>.

    Po co: analityk szuka w nich ustawień, wartości i haseł wpisanych wprost; numery linii pozwalają wskazać miejsce
    (np. config.yml:12). Bez plików tekstowych zwraca zdanie o braku.
    """
    if not project_map.text_files:
        tekst_braku = "(brak plików tekstowych)"
        return tekst_braku
    bloki = []
    for plik in project_map.text_files:
        bloki.append(f'<plik_tekstowy sciezka="{plik.path}" rola="{plik.role}">\n{_common.number_lines(plik.text)}\n</plik_tekstowy>')
    tekst = "\n\n".join(bloki)
    return tekst


def build_project_context(
    project_map: _schemas.ProjectMap,
    unit: _schemas.CodeUnit,
) -> str:
    """Zwraca JSON z kontekstem jednostki: technologia, punkty wejścia, frameworki, powiązania z innymi plikami i fakty o plikach jednostki.

    Po co: analityk widzi, jak jednostka wpisuje się w robota (kto ją wywołuje, co importuje, jakie ma funkcje
    z zakresami linii), bez czytania całej mapy projektu. JSON bez zamiany polskich znaków na kody.
    """
    krawedzie = []
    for krawedz in project_map.dependency_edges:
        if krawedz[0] in unit.files or krawedz[1] in unit.files:
            krawedzie.append(krawedz)
    fakty_plikow = []
    for plik in project_map.source_files:
        if plik.path in unit.files:
            fakty_plikow.append(plik.model_dump())
    dane = {
        "technology": project_map.technology,
        "entrypoints": project_map.entrypoints,
        "frameworks": project_map.frameworks,
        "dependency_edges": krawedzie,
        "source_files": fakty_plikow,
    }
    tekst = json.dumps(dane, indent=2, ensure_ascii=False)
    return tekst


def build_analyst_variables(
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    task: _schemas.AnalysisTask,
    unit: _schemas.CodeUnit,
    unit_code: str,
    knowledge_text: str,
    note_part: str,
) -> dict:
    """Zwraca zmienne do szablonu prompts/analyst/user.md: zadanie, kontekst, kod z numerami linii, pliki tekstowe, wiedzę i opis części notatki.

    Po co: w jednym miejscu widać, co dokładnie analityk dostaje. Pusta wskazówka plannera zamieniana jest na zdanie
    "brak wskazówki", żeby w prompcie nie było pustego miejsca. Ścieżki bezwzględnej katalogu projektu w prompcie nie ma.
    """
    wskazowka = task.hint
    if wskazowka == "":
        wskazowka = "(brak wskazówki)"
    zmienne_promptu = {
        "project_name": project_map.project_name,
        "unit_name": unit.name,
        "unit_files": ", ".join(unit.files),
        "plan_summary": plan.summary,
        "hint": wskazowka,
        "project_context": build_project_context(project_map, unit),
        "unit_code": unit_code,
        "text_files": format_text_files(project_map),
        "knowledge": knowledge_text,
        "note_part": note_part,
    }
    return zmienne_promptu


# --- Analiza jednostki ---


def fix_note(
    note: _schemas.ModuleNote,
    unit_name: str,
    max_line: int,
) -> tuple[_schemas.ModuleNote, list[str]]:
    """Zwraca (poprawiona notatka, lista uwag): nazwa jednostki z zadania, numer linii czynności spoza pliku (też ujemny) zamieniony na 0.

    Po co: model może przekręcić nazwę jednostki albo wymyślić numer linii spoza pliku - dalsze etapy polegają na tych
    polach, więc poprawia je kod, a każda poprawka trafia do uwag. Schemat nie ma ograniczeń liczbowych (bramka ich
    nie przyjmuje), więc zakres numerów linii sprawdza ta funkcja.
    """
    uwagi = []
    poprawki = {}
    if note.unit_name != unit_name:
        uwagi.append(f"nazwa jednostki w notatce '{note.unit_name}' zmieniona na '{unit_name}'")
        poprawki["unit_name"] = unit_name
    czynnosci = []
    for czynnosc in note.actions:
        if czynnosc.line > max_line or czynnosc.line < 0:
            uwagi.append(f"czynność '{czynnosc.title}': linia {czynnosc.line} poza plikiem (linii: {max_line}), ustawiono 0")
            czynnosci.append(czynnosc.model_copy(update={"line": 0}))
        else:
            czynnosci.append(czynnosc)
    poprawki["actions"] = czynnosci
    poprawiona = note.model_copy(update=poprawki)
    wynik = (poprawiona, uwagi)
    return wynik


def merge_note(
    flow: _schemas.NoteFlow,
    details: _schemas.NoteDetails,
) -> _schemas.ModuleNote:
    """Składa dwie odpowiedzi modelu (przebieg i szczegóły) w jedną notatkę ModuleNote.

    Po co: model zwraca notatkę w dwóch częściach, bo cała ma więcej pól, niż przyjmuje bramka; dalsze etapy
    dostają jeden obiekt jak dawniej. Pola części nie nachodzą na siebie, a walidacja ModuleNote sprawdza komplet.
    """
    dane = flow.model_dump()
    dane.update(details.model_dump())
    notatka = _schemas.ModuleNote.model_validate(dane)
    return notatka


def analyze_unit(
    task: _schemas.AnalysisTask,
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    context: _context.RunContext,
) -> tuple[_schemas.ModuleNote, list[str]]:
    """Analizuje jednostkę z zadania: czyta kod, woła model agenta analyst dwa razy (NoteFlow, NoteDetails), składa i poprawia notatkę; zwraca (notatka, uwagi).

    Po co: cała logika analityka w jednej funkcji, z której korzystają węzeł grafu (krok 52) i test ręczny. Wiedza
    to pliki technologii i frameworków (dołącza kod) oraz pliki wybrane przez plannera dla analityków. Oba wywołania
    dostają ten sam kod i różnią się opisem części (prompts/analyst/part_*.md) oraz schematem. Błędy (nieznana
    jednostka, plik sekretu, plik za duży, odpowiedź niezgodna ze schematem - z nazwą schematu) kończą się wyjątkiem.
    """
    jednostka = find_unit(project_map, task.unit)
    kod, najwiecej_linii = read_unit_code(project_map, jednostka, context.config.analysis.max_file_size_kb)
    pliki_wiedzy = _common.collect_knowledge_files(context.config, project_map, plan.analyst_knowledge)
    tekst_wiedzy = _common.format_knowledge(context.config, pliki_wiedzy)
    metoda = _llm.get_structured_output_method(context.config, _AGENT_NAME)
    odpowiedzi = []
    for plik_czesci, schemat in _NOTE_PARTS:
        opis_czesci = _prompts.read_prompt_file(context.config.paths.prompts, _AGENT_NAME, plik_czesci)
        zmienne = build_analyst_variables(project_map, plan, task, jednostka, kod, tekst_wiedzy, opis_czesci)
        tekst_system, tekst_user = _prompts.render_prompt(context.config.paths.prompts, _AGENT_NAME, zmienne)
        odpowiedz = _llm.invoke_structured(
            context.models[_AGENT_NAME],
            schemat,
            metoda,
            [SystemMessage(content=tekst_system), HumanMessage(content=tekst_user)],
        )
        odpowiedzi.append(odpowiedz)
    notatka = merge_note(odpowiedzi[0], odpowiedzi[1])
    wynik = fix_note(notatka, task.unit, najwiecej_linii)
    return wynik


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import sys
    import tempfile
    import types

    import dev_agents.config as _config
    import dev_agents.fakes as _fakes
    import dev_agents.output as _output
    import dev_agents.progress as _progress
    import dev_agents.scanner as _scanner

    _HASLO = "Haslo123!"
    _CODE_MARKER = "KOD_MARKER_TESTOWY"

    def _write_temp_project(
        temp_dir: str,
    ) -> str:
        """Tworzy mały projekt w Pythonie z plikiem konfiguracyjnym (hasło wpisane wprost) w katalogu tymczasowym i zwraca jego ścieżkę.

        Po co: test sprawdza prompt na prawdziwej mapie z prawdziwego skanu, bez dotykania cudzych projektów.
        """
        projekt = os.path.join(temp_dir, "maly_robot")
        os.makedirs(projekt)
        kod = f"import requests\n\n\ndef run():\n    # {_CODE_MARKER}\n    return requests.get('http://x')\n\n\nif __name__ == '__main__':\n    run()\n"
        with open(os.path.join(projekt, "main.py"), "w", encoding="utf-8") as plik:
            plik.write(kod)
        with open(os.path.join(projekt, "config.yml"), "w", encoding="utf-8") as plik:
            plik.write(f"api:\n  url: http://x\n  password: {_HASLO}\n")
        with open(os.path.join(projekt, "requirements.txt"), "w", encoding="utf-8") as plik:
            plik.write("requests\n")
        return projekt

    def _messy_note() -> _schemas.ModuleNote:
        """Zwraca notatkę z dwoma błędami: zła nazwa jednostki i czynność z linią spoza pliku.

        Po co: sprawdzenie, że fix_note poprawia odpowiedź modelu i zgłasza każdą poprawkę.
        """
        czynnosci = [
            _schemas.NoteAction(title="Pobierz stronę", kind="system", function="run", line=5, description="", reads=[], writes=[], certain=True),
            _schemas.NoteAction(title="Wymyślona czynność", kind="step", function="run", line=9999, description="", reads=[], writes=[], certain=True),
        ]
        haslo = _schemas.NoteSetting(
            file="config.yml",
            location="config.yml:3",
            group="api",
            key="password",
            value=_HASLO,
            kind="account",
            plain_password=True,
            meaning="Hasło.",
            used_in=[],
            certain=True,
        )
        notatka = _schemas.ModuleNote(
            unit_name="inna_nazwa.py",
            purpose="Pobiera stronę.",
            flow_role="",
            automated_application="",
            key_functions=[],
            actions=czynnosci,
            process_steps=[],
            error_handling=[],
            inputs=[],
            outputs=[],
            settings=[haslo],
            requirements=[],
            external_dependencies=[],
            risky_places=[],
            possible_failures=[],
            extension_points=[],
            conventions=[],
            maintainer_hints=[],
            glossary_candidates=[],
        )
        return notatka

    def _split_note(
        note: _schemas.ModuleNote,
    ) -> tuple[_schemas.NoteFlow, _schemas.NoteDetails]:
        """Dzieli notatkę na dwie odpowiedzi modelu: NoteFlow (przebieg) i NoteDetails (szczegóły).

        Po co: udawany model odpowiada obiektami schematów, które dostałby od prawdziwego modelu.
        """
        dane = note.model_dump()
        flow = _schemas.NoteFlow.model_validate(dane)
        details = _schemas.NoteDetails.model_validate(dane)
        wynik = (flow, details)
        return wynik

    def _make_answer_function(
        note: _schemas.ModuleNote,
        seen_prompts: list[str],
    ):
        """Zwraca funkcję odpowiedzi udawanego modelu: dla promptu części 1 odpowiada NoteFlow, dla części 2 NoteDetails; zapamiętuje prompty użytkownika.

        Po co: analityk woła model dwa razy z różnymi schematami, a udawany model nie widzi schematu - rozpoznaje
        część po opisie w prompcie.
        """
        flow, details = _split_note(note)

        def answer(
            messages,
        ):
            """Zapamiętuje prompt użytkownika i zwraca odpowiedź dla części wskazanej w prompcie.

            Po co: odpowiedź udawanego modelu zależna od wiadomości (FakeStructuredModel przyjmuje taką funkcję).
            """
            seen_prompts.append(messages[1].content)
            odpowiedz = details
            if "CZĘŚĆ 1 z 2" in messages[1].content:
                odpowiedz = flow
            return odpowiedz

        return answer

    def _context_for(
        app_config: _config.AppConfig,
        model,
    ) -> types.SimpleNamespace:
        """Zwraca uproszczony kontekst (config i model agenta analyst) - tyle, ile czyta analyze_unit.

        Po co: test offline nie buduje prawdziwych modeli wszystkich agentów i nie wymaga kluczy.
        """
        kontekst = types.SimpleNamespace(config=app_config, models={_AGENT_NAME: model})
        return kontekst

    def _raises(
        function,
        *args,
    ) -> str:
        """Woła funkcję z argumentami i zwraca komunikat ValueError, który rzuciła; gdy nie rzuciła - pusty tekst.

        Po co: test sprawdza komunikaty błędów w jednym miejscu.
        """
        komunikat = ""
        try:
            function(*args)
        except ValueError as blad:
            komunikat = str(blad)
        return komunikat

    def _offline_checks(
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza analityka na udawanym modelu: prompt, odmowy czytania, poprawianie notatki i liczbę wywołań modelu; zwraca (opis, zgodne).

        Po co: cała ścieżka analizy (kod, wiedza, prompt, model, poprawki) bez sieci i kluczy.
        """
        root = _write_temp_project(temp_dir)
        project_map = _scanner.build_project_map(root, app_config.scan)
        plan = _schemas.Plan(summary="Plan testowy: robot pobiera stronę.", tasks=[], analyst_knowledge=["guide_goals.md"])
        zadanie = _schemas.AnalysisTask(unit="main.py", hint="Punkt wejścia, łączy się ze stroną.")
        zepsuta = _messy_note()
        widziane_prompty = []
        model = _fakes.FakeStructuredModel(_make_answer_function(zepsuta, widziane_prompty))
        notatka, uwagi = analyze_unit(zadanie, project_map, plan, _context_for(app_config, model))
        prompt_user = widziane_prompty[0]
        prompt_user_czesc_2 = widziane_prompty[1]
        prompt_system = model.messages[0].content
        flow_zepsuty, details_zepsute = _split_note(zepsuta)
        wpisy = {}
        for wpis in project_map.files:
            wpisy[wpis.path] = wpis
        mapa_z_sekretem = project_map.model_copy(update={"files": [wpisy["main.py"].model_copy(update={"role": "secret"})]})
        komunikat_sekretu = _raises(read_unit_code, mapa_z_sekretem, project_map.code_units[0], 100)
        komunikat_limitu = _raises(read_unit_code, project_map, project_map.code_units[0], 0)
        komunikat_nieznanej = _raises(find_unit, project_map, "nie_ma.py")
        bez_wskazowki = build_analyst_variables(project_map, plan, _schemas.AnalysisTask(unit="main.py"), project_map.code_units[0], "kod", "wiedza", "opis części")
        wyniki = [
            ("prompt: kod z numerami linii", f"    5|     # {_CODE_MARKER}" in prompt_user and '<plik sciezka="main.py" linii="10">' in prompt_user),
            ("prompt: plik konfiguracyjny z numerami i hasłem dosłownie", f"    3|   password: {_HASLO}" in prompt_user),
            ("prompt: wiedza technologii i plik plannera", 'nazwa="technologies/python.md"' in prompt_user and 'nazwa="guide_goals.md"' in prompt_user),
            ("prompt: wskazówka i podsumowanie plannera", "Punkt wejścia, łączy się ze stroną." in prompt_user and "Plan testowy: robot pobiera stronę." in prompt_user),
            ("prompt: fakty o pliku (funkcja run z zakresem linii)", '"name": "run"' in prompt_user and '"main.py"' in prompt_user),
            ("prompt: bez ścieżki dysku katalogu projektu", root not in prompt_user and root not in prompt_system),
            ("prompt: brak wskazówki zamieniony na zdanie", bez_wskazowki["hint"] == "(brak wskazówki)"),
            ("model zawołany dwa razy: wiadomości system i człowiek", model.calls == 2 and len(model.messages) == 2),
            ("prompty: część 1 i część 2 mają swój opis, ten sam kod i ten sam system", "CZĘŚĆ 1 z 2" in prompt_user and "CZĘŚĆ 2 z 2" not in prompt_user and "CZĘŚĆ 2 z 2" in prompt_user_czesc_2 and "CZĘŚĆ 1 z 2" not in prompt_user_czesc_2 and _CODE_MARKER in prompt_user_czesc_2),
            ("merge_note: dwie części dają notatkę równą oryginałowi", merge_note(flow_zepsuty, details_zepsute) == zepsuta),
            ("notatka złożona: czynności z części 1, ustawienia z części 2", notatka.actions[0].title == "Pobierz stronę" and notatka.settings[0].key == "password"),
            ("notatka: nazwa jednostki z zadania", notatka.unit_name == "main.py"),
            ("notatka: czynność z linią spoza pliku ma linię 0, poprawna zostaje", notatka.actions[0].line == 5 and notatka.actions[1].line == 0),
            (f"notatka: dwie uwagi o poprawkach ({len(uwagi)})", len(uwagi) == 2),
            ("notatka: hasło wpisane wprost zachowane dosłownie", notatka.settings[0].value == _HASLO and notatka.settings[0].plain_password),
            ("plik sekretu odmówiony (ValueError z rolą secret)", "secret" in komunikat_sekretu and "main.py" in komunikat_sekretu),
            ("plik większy niż limit odmówiony (ValueError z limitem)", "max_file_size_kb" in komunikat_limitu and "main.py" in komunikat_limitu),
            ("nieznana jednostka: ValueError z listą jednostek", "nie_ma.py" in komunikat_nieznanej and "main.py" in komunikat_nieznanej),
        ]
        return wyniki

    def _real_model_run(
        project_dir: str,
        unit_name: str,
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> None:
        """Skanuje robota w pamięci, woła prawdziwy model analityka dla jednostki i wypisuje notatkę jako JSON; niczego nie zapisuje w robocie.

        Po co: sprawdzenie analityka na prawdziwym robocie i modelu. Plan pochodzi z dev_agents_doc/plan.json robota,
        o ile istnieje (odczyt), inaczej jest minimalny. Magazyn wyników powstaje w katalogu tymczasowym.
        """
        project_map = _scanner.build_project_map(project_dir, app_config.scan)
        sciezka_planu = os.path.join(project_dir, _output.OUTPUT_DIR_NAME, "plan.json")
        if os.path.isfile(sciezka_planu):
            with open(sciezka_planu, encoding="utf-8") as plik:
                plan = _schemas.Plan.model_validate_json(plik.read())
            print(f"Plan: {sciezka_planu}")
        else:
            plan = _schemas.Plan(summary=f"Robot {project_map.project_name} (technologia: {project_map.technology}); plan minimalny, bez plannera.", tasks=[])
            print("Plan minimalny (brak plan.json w katalogu wyników robota).")
        zadanie = _schemas.AnalysisTask(unit=unit_name)
        for zadanie_planu in plan.tasks:
            if zadanie_planu.unit == unit_name:
                zadanie = zadanie_planu
        try:
            kontekst = _context.build_context(app_config, _output.create_run_store(temp_dir), _progress.print_line)
        except (RuntimeError, ValueError, OSError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        print(f"\n=== Prawdziwy model analityka: {unit_name} ===")
        try:
            notatka, uwagi = analyze_unit(zadanie, project_map, plan, kontekst)
        except (ValueError, RuntimeError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        print(notatka.model_dump_json(indent=2))
        print(f"\nUwagi o poprawkach: {len(uwagi)}")
        for uwaga in uwagi:
            print(f"  {uwaga}")
        print(f"Czynności: {len(notatka.actions)}, ustawienia: {len(notatka.settings)}, trudne miejsca: {len(notatka.risky_places)}, awarie: {len(notatka.possible_failures)}")

    def manual_test():
        """Uruchamia sprawdzenia offline analityka i wypisuje werdykt; z argumentami <katalog robota> <jednostka> woła też prawdziwy model.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że analityk składa prompt i poprawia notatkę poprawnie; część
        z prawdziwym modelem pokazuje, jak analityk radzi sobie z prawdziwym kodem.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        temp_dir = tempfile.mkdtemp()
        try:
            wyniki = _offline_checks(app_config, temp_dir)
            print("=== Sprawdzenia offline ===")
            wszystkie_zgodne = True
            for opis, zgodne in wyniki:
                print(f"  {opis}: {zgodne}")
                if not zgodne:
                    wszystkie_zgodne = False
            print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
            if len(sys.argv) >= 3:
                _real_model_run(sys.argv[1], sys.argv[2], app_config, temp_dir)
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
