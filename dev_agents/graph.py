"""Graf agentów (LangGraph): skan projektu, potem plan pracy.

Co robi: buduje graf START -> scan -> planner -> END. Węzeł scan woła scanner.build_project_map na projekcie ze stanu
(project_path) z ustawieniami skanowania z kontekstu (runtime.context.config.scan) i dopisuje do stanu
project_map. Węzeł niczego nie zapisuje na dysku - zapis wyników należy do wołającego (main.py, krok 44).
Pracę węzła owija Stage z progress.py: linie "scan: start" i "scan: gotowe w X s - wynik" (albo "BŁĄD po X s")
trafiają do runtime.context.report (krok 45). Węzeł planner (agents/planner.py, krok 48) czyta mapę ze stanu,
woła model małym planem pracy, dopisuje do stanu plan i zapisuje plan.json w magazynie wyników.

Dlaczego istnieje: kolejne etapy (analitycy, autor diagramu, pisarze, recenzent) dołączamy do tego
szkieletu po jednym - najpierw uczymy się LangGraph na grafie bez modelu. Graf przyjmuje stan (RunState)
i kontekst (RunContext) osobno: stan się zmienia w trakcie przebiegu, kontekst nie.

Rola: moduł rdzenia towaru; build_graph() woła main.py (krok 44) i test.

Pojęcia LangGraph użyte tutaj:
    StateGraph(RunState, context_schema=RunContext) - graf ze stanem i typem kontekstu,
    węzeł - zwykła funkcja (state, runtime) zwracająca TYLKO zmienione pola stanu,
    Runtime[RunContext] - wstrzykiwany do węzła; runtime.context to RunContext z invoke(..., context=...),
    START i END - znaczniki początku i końca; compile() zwraca graf, który się uruchamia przez invoke().

Test ręczny (z katalogu głównego repo; wymaga zainstalowanego langgraph, bez wywołań modelu i bez sieci):
    python -m dev_agents.graph
        buduje kontekst (modele, spis bazy wiedzy, szablon), podmienia model plannera na udawany (bez sieci)
        i uruchamia graf na małym projekcie tymczasowym oraz na robotach testowych 02 i 01 (tylko odczyt, bez
        zapisu w nich); dla każdego wypisuje stan końcowy, porównuje mapę z grafu z mapą z bezpośredniego skanu,
        sprawdza linie postępu (scan: start i koniec, planner: start i koniec z liczbą zadań) oraz to, że plan
        obejmuje wszystkie jednostki kodu i trafił do plan.json w magazynie tymczasowym; na końcu
        "zgodne z oczekiwaniem: True".
        Jeśli w środowisku nie ma zmiennych z kluczem i adresem modeli (nazwy w config.yaml), test ustawia
        atrapy tylko dla tego procesu - prawdziwe modele nie są wołane.
"""

import os

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

import dev_agents.agents.planner as _planner
import dev_agents.context as _context
import dev_agents.progress as _progress
import dev_agents.scanner as _scanner
import dev_agents.state as _state


# --- Węzły ---


def scan_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Skanuje projekt ze stanu i zwraca zmienione pole stanu: project_map.

    Po co: pierwszy węzeł grafu - od mapy projektu zaczynają się wszystkie dalsze etapy; niczego nie zapisuje
    na dysku, tylko zgłasza postęp przez runtime.context.report (start, koniec z czasem i krótkim wynikiem).

    Uwaga: projekt bez rozpoznanej technologii daje mapę z technology=""; o przerwaniu pracy decyduje wołający.
    """
    with _progress.Stage(runtime.context.report, "scan") as etap:
        mapa = _scanner.build_project_map(state["project_path"], runtime.context.config.scan)
        technologia = mapa.technology
        if not technologia:
            technologia = "technologia nierozpoznana"
        etap.set_result(f"{technologia}, plików: {len(mapa.files)}, punktów wejścia: {len(mapa.entrypoints)}")
    zmiana_stanu = {"project_map": mapa}
    return zmiana_stanu


# --- Budowa grafu ---


def build_graph():
    """Buduje i kompiluje graf START -> scan -> planner -> END; zwraca graf gotowy do invoke(stan, context=RunContext).

    Po co: jedno miejsce z układem grafu - kolejne kroki planu dopisują tu węzły i krawędzie.
    """
    budowniczy = StateGraph(_state.RunState, context_schema=_context.RunContext)
    budowniczy.add_node("scan", scan_node)
    budowniczy.add_node("planner", _planner.planner_node)
    budowniczy.add_edge(START, "scan")
    budowniczy.add_edge("scan", "planner")
    budowniczy.add_edge("planner", END)
    graf = budowniczy.compile()
    return graf


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile

    import dev_agents.config as _config
    import dev_agents.fakes as _fakes
    import dev_agents.output as _output
    import dev_agents.schemas as _schemas

    def _ensure_test_env(
        app_config: _config.AppConfig,
    ) -> list[str]:
        """Ustawia atrapy zmiennych z kluczem i adresem modeli, których brak w środowisku; zwraca nazwy ustawionych atrap.

        Po co: modele powstają przy starcie kontekstu i wymagają tych zmiennych, a test grafu nie woła modeli;
        prawdziwych wartości nie nadpisuje, a atrapy żyją tylko w tym procesie.
        """
        ustawione = []
        for profil in app_config.llm.profiles.values():
            if not os.environ.get(profil.api_key_env):
                os.environ[profil.api_key_env] = "klucz-testowy"
                ustawione.append(profil.api_key_env)
            if not os.environ.get(profil.base_url_env):
                os.environ[profil.base_url_env] = "http://localhost:1/v1"
                ustawione.append(profil.base_url_env)
        return ustawione

    def _write_temp_project(
        temp_dir: str,
    ) -> str:
        """Tworzy mały projekt w Pythonie w katalogu tymczasowym i zwraca jego ścieżkę.

        Po co: test działa także bez robotów testowych i nie dotyka żadnego prawdziwego projektu.
        """
        projekt = os.path.join(temp_dir, "maly_robot")
        os.makedirs(projekt)
        with open(os.path.join(projekt, "main.py"), "w", encoding="utf-8") as plik:
            plik.write("import requests\n\n\ndef run():\n    return requests.get('http://x')\n\n\nif __name__ == '__main__':\n    run()\n")
        with open(os.path.join(projekt, "requirements.txt"), "w", encoding="utf-8") as plik:
            plik.write("requests\n")
        return projekt

    def _context_lines(
        context: _context.RunContext,
    ) -> list[str]:
        """Zwraca linie opisujące kontekst: agenci z modelami, wpisy spisu bazy wiedzy i zakładki szablonu.

        Po co: widać, co graf dostaje od wołającego, bez otwierania kodu.
        """
        modele = []
        for agent_name, model in context.models.items():
            modele.append(f"{agent_name}={getattr(model, 'model_name', '?')}")
        pliki_wiedzy = []
        for wpis in context.knowledge_index:
            pliki_wiedzy.append(wpis.filename)
        zakladki = []
        for zakladka in context.template.tabs:
            zakladki.append(zakladka.id)
        linie = [
            "=== Kontekst przebiegu ===",
            f"  agenci i modele: {', '.join(modele)}",
            f"  spis bazy wiedzy: {pliki_wiedzy}",
            f"  zakładki szablonu: {zakladki}",
            f"  magazyn wyników: {context.store.output_dir}",
        ]
        return linie

    def _run_case(
        graph,
        context: _context.RunContext,
        progress_lines: list[str],
        title: str,
        root: str,
    ) -> tuple[list[str], bool]:
        """Uruchamia graf na projekcie i zwraca (linie opisu stanu końcowego, czy wynik zgadza się z oczekiwaniem).

        Po co: sprawdza, że węzeł scan daje dokładnie ten wynik co skaner wołany wprost, że uruchomienie
        nie utworzyło ani nie zmieniło katalogu wyników w skanowanym projekcie, że węzeł scan zgłosił dwie linie
        postępu (start i koniec), że plan z węzła planner obejmuje wszystkie jednostki kodu, jest zapisany jako
        plan.json w magazynie i że planner zgłosił start oraz koniec z liczbą zadań; progress_lines to lista,
        do której context.report dopisuje linie.
        """
        katalog_wynikow = os.path.join(root, _output.OUTPUT_DIR_NAME)
        istnial_przed = os.path.exists(katalog_wynikow)
        ile_linii_przed = len(progress_lines)
        stan = graph.invoke({"project_path": root}, context=context)
        nowe_linie = progress_lines[ile_linii_przed:]
        linie_scan = []
        linie_planner = []
        for linia_postepu in nowe_linie:
            if "] scan: " in linia_postepu:
                linie_scan.append(linia_postepu)
            if "] planner: " in linia_postepu:
                linie_planner.append(linia_postepu)
        postep_scan = len(linie_scan) == 2 and linie_scan[0].endswith("] scan: start") and "] scan: gotowe w " in linie_scan[1]
        istnieje_po = os.path.exists(katalog_wynikow)
        mapa = stan["project_map"]
        bezposrednio = _scanner.build_project_map(root, context.config.scan)
        plan = stan["plan"]
        liczba_jednostek = len(mapa.code_units)
        plan_pelny = len(plan.tasks) == liczba_jednostek
        plan_zapisany = context.store.load_json("plan.json", _schemas.Plan) == plan
        postep_planner = (
            len(linie_planner) >= 2
            and linie_planner[0].endswith("] planner: start")
            and f"zadań: {liczba_jednostek}," in linie_planner[-1]
        )
        zgodne = (
            mapa == bezposrednio
            and istnial_przed == istnieje_po
            and postep_scan
            and plan_pelny
            and plan_zapisany
            and postep_planner
        )
        linie = [
            f"=== {title} ===",
            f"  klucze stanu końcowego: {sorted(stan.keys())}",
            f"  technologia: {mapa.technology}, plików: {len(mapa.files)}, pliki źródłowe: {len(mapa.source_files)}",
            f"  punkty wejścia: {mapa.entrypoints}, frameworki: {mapa.frameworks}",
            f"  krawędzie zależności: {len(mapa.dependency_edges)}, kolejność czytania: {mapa.reading_order}",
            f"  mapa z grafu == mapa z bezpośredniego skanu: {mapa == bezposrednio}",
            f"  katalog wyników w projekcie bez zmian: {istnial_przed == istnieje_po}",
            f"  linie postępu węzła scan (start i koniec): {postep_scan}",
            f"  plan obejmuje wszystkie jednostki kodu ({liczba_jednostek}): {plan_pelny}",
            f"  plan.json w magazynie == plan ze stanu: {plan_zapisany}",
            f"  linie postępu węzła planner (start, uwagi, koniec z liczbą zadań): {postep_planner}",
        ]
        for linia_postepu in nowe_linie:
            linie.append(f"    {linia_postepu}")
        wynik_przypadku = (linie, zgodne)
        return wynik_przypadku

    def manual_test():
        """Buduje kontekst i graf, uruchamia je na projekcie tymczasowym i robotach testowych 02 i 01 (tylko odczyt).

        Po co: sprawdzenie szkieletu LangGraph z prawdziwym skanem i udawanym modelem plannera (pusty plan,
        który complete_plan uzupełnia o wszystkie jednostki), bez sieci i bez zapisu w cudzych projektach.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        atrapy = _ensure_test_env(app_config)
        if atrapy:
            print(f"Zmienne środowiskowe bez wartości - atrapy tylko dla testu: {atrapy}")
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        temp_dir = tempfile.mkdtemp()
        try:
            projekt_maly = _write_temp_project(temp_dir)
            magazyn = _output.create_run_store(temp_dir)
            linie_postepu = []
            kontekst = _context.build_context(app_config, magazyn, linie_postepu.append)
            kontekst.models["planner"] = _fakes.FakeStructuredModel(_schemas.Plan(summary="Plan testowy", tasks=[]))
            graf = build_graph()
            for linia in _context_lines(kontekst):
                print(linia)
            przypadki = [
                ("projekt tymczasowy", projekt_maly),
                ("robot 02", os.path.join(katalog_testow, "02_robot_bez_frameworku")),
                ("robot 01", os.path.join(katalog_testow, "01_rpa_challange_roboforge")),
            ]
            wszystkie_zgodne = True
            for tytul, root in przypadki:
                if not os.path.isdir(root):
                    print(f"=== {tytul}: brak katalogu {root} - pomijam ===")
                    continue
                linie, zgodne = _run_case(graf, kontekst, linie_postepu, tytul, root)
                for linia in linie:
                    print(linia)
                if not zgodne:
                    wszystkie_zgodne = False
            print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
