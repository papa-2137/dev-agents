"""Graf agentów (LangGraph): na razie jeden węzeł - skan projektu.

Co robi: buduje graf START -> scan -> END. Węzeł scan woła scanner.build_project_map na projekcie ze stanu
(project_path) z ustawieniami skanowania z kontekstu (runtime.context.config.scan) i dopisuje do stanu
project_map. Węzeł niczego nie zapisuje na dysku - zapis wyników należy do wołającego (main.py, krok 44).

Dlaczego istnieje: kolejne etapy (planner, analitycy, autor diagramu, pisarze, recenzent) dołączamy do tego
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
        buduje kontekst (modele, spis bazy wiedzy, szablon) i uruchamia graf na małym projekcie tymczasowym
        oraz na robotach testowych 02 i 01 (tylko odczyt, bez zapisu w nich); dla każdego wypisuje stan końcowy
        i porównuje mapę z grafu z mapą z bezpośredniego skanu; na końcu "zgodne z oczekiwaniem: True".
        Jeśli w środowisku nie ma zmiennych z kluczem i adresem modeli (nazwy w config.yaml), test ustawia
        atrapy tylko dla tego procesu - modele nie są wołane.
"""

import os

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

import dev_agents.context as _context
import dev_agents.scanner as _scanner
import dev_agents.state as _state


# --- Węzły ---


def scan_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Skanuje projekt ze stanu i zwraca zmienione pole stanu: project_map.

    Po co: pierwszy węzeł grafu - od mapy projektu zaczynają się wszystkie dalsze etapy; niczego nie zapisuje.

    Uwaga: projekt bez rozpoznanej technologii daje mapę z technology=""; o przerwaniu pracy decyduje wołający.
    """
    mapa = _scanner.build_project_map(state["project_path"], runtime.context.config.scan)
    zmiana_stanu = {"project_map": mapa}
    return zmiana_stanu


# --- Budowa grafu ---


def build_graph():
    """Buduje i kompiluje graf START -> scan -> END; zwraca graf gotowy do invoke(stan, context=RunContext).

    Po co: jedno miejsce z układem grafu - kolejne kroki planu dopisują tu węzły i krawędzie.
    """
    budowniczy = StateGraph(_state.RunState, context_schema=_context.RunContext)
    budowniczy.add_node("scan", scan_node)
    budowniczy.add_edge(START, "scan")
    budowniczy.add_edge("scan", END)
    graf = budowniczy.compile()
    return graf


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile

    import dev_agents.config as _config
    import dev_agents.output as _output

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
        title: str,
        root: str,
    ) -> tuple[list[str], bool]:
        """Uruchamia graf na projekcie i zwraca (linie opisu stanu końcowego, czy mapa z grafu równa się mapie z bezpośredniego skanu).

        Po co: sprawdza, że węzeł scan daje dokładnie ten wynik co skaner wołany wprost, i że uruchomienie
        nie utworzyło ani nie zmieniło katalogu wyników w skanowanym projekcie.
        """
        katalog_wynikow = os.path.join(root, _output.OUTPUT_DIR_NAME)
        istnial_przed = os.path.exists(katalog_wynikow)
        stan = graph.invoke({"project_path": root}, context=context)
        istnieje_po = os.path.exists(katalog_wynikow)
        mapa = stan["project_map"]
        bezposrednio = _scanner.build_project_map(root, context.config.scan)
        zgodne = mapa == bezposrednio and istnial_przed == istnieje_po
        linie = [
            f"=== {title} ===",
            f"  klucze stanu końcowego: {sorted(stan.keys())}",
            f"  technologia: {mapa.technology}, plików: {len(mapa.files)}, pliki źródłowe: {len(mapa.source_files)}",
            f"  punkty wejścia: {mapa.entrypoints}, frameworki: {mapa.frameworks}",
            f"  krawędzie zależności: {len(mapa.dependency_edges)}, kolejność czytania: {mapa.reading_order}",
            f"  mapa z grafu == mapa z bezpośredniego skanu: {mapa == bezposrednio}",
            f"  katalog wyników w projekcie bez zmian: {istnial_przed == istnieje_po}",
        ]
        wynik_przypadku = (linie, zgodne)
        return wynik_przypadku

    def manual_test():
        """Buduje kontekst i graf, uruchamia je na projekcie tymczasowym i robotach testowych 02 i 01 (tylko odczyt).

        Po co: sprawdzenie szkieletu LangGraph z prawdziwym skanem, bez modelu i bez zapisu w cudzych projektach.
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
            kontekst = _context.build_context(app_config, magazyn)
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
                linie, zgodne = _run_case(graf, kontekst, tytul, root)
                for linia in linie:
                    print(linia)
                if not zgodne:
                    wszystkie_zgodne = False
            print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
