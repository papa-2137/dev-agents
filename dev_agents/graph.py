"""Graf agentów (LangGraph): skan projektu, plan pracy, równoległa analiza jednostek.

Co robi: buduje graf START -> scan -> planner -> (analyst x N, równolegle) -> flow_writer -> plan_tabs -> (writer x M, równolegle) -> assemble -> END. Węzeł scan woła scanner.build_project_map na projekcie ze stanu
(project_path) z ustawieniami skanowania z kontekstu (runtime.context.config.scan) i dopisuje do stanu
project_map. Węzeł niczego nie zapisuje na dysku - zapis wyników należy do wołającego (main.py, krok 44).
Pracę węzła owija Stage z progress.py: linie "scan: start" i "scan: gotowe w X s - wynik" (albo "BŁĄD po X s")
trafiają do runtime.context.report (krok 45). Węzeł planner (agents/planner.py, krok 48) czyta mapę ze stanu,
woła model małym planem pracy, dopisuje do stanu plan i zapisuje plan.json w magazynie wyników.
Po plannerze krawędź warunkowa (dispatch_analysts) wysyła Send("analyst", ładunek) na każde zadanie planu;
węzeł analyst (agents/analyst.py, krok 52) analizuje jedną jednostkę i zapisuje notes/<jednostka>.json, a reducer
pola notes w stanie skleja notatki wszystkich analityków. Ilu analityków pracuje naraz, ustawia
analysis.max_concurrency, przekazane do invoke przez run_config().
Po analitykach węzeł flow_writer (agents/flow_writer.py, krok 54) układa z notatek diagram całego procesu,
zapisuje flow.json i dopisuje do stanu flow; zaczyna dopiero, gdy skończą wszyscy analitycy (krawędź analyst ->
flow_writer czeka na wszystkie zadania wysłane przez Send).
Po diagramie węzeł plan_tabs (kod, bez modelu) wpisuje do stanu tab_ids: zakładki szablonu z sekcjami dla pisarza;
krawędź warunkowa dispatch_writers wysyła Send("writer", ładunek z tab_id) na każdą z nich, a węzeł writer
(agents/writer.py, krok 55) pisze zakładkę i zapisuje tabs/<zakładka>.json. Węzeł assemble (assemble.py, krok 56) czeka
na wszystkich pisarzy, składa treść przewodnika w kolejności szablonu, sprawdza kompletność i zapisuje guide_content.json.

Dlaczego istnieje: kolejne etapy (analitycy, autor diagramu, pisarze, recenzent) dołączamy do tego
szkieletu po jednym - najpierw uczymy się LangGraph na grafie bez modelu. Graf przyjmuje stan (RunState)
i kontekst (RunContext) osobno: stan się zmienia w trakcie przebiegu, kontekst nie.

Rola: moduł rdzenia towaru; build_graph() woła main.py (krok 44) i test.

Pojęcia LangGraph użyte tutaj:
    StateGraph(RunState, context_schema=RunContext) - graf ze stanem i typem kontekstu,
    węzeł - zwykła funkcja (state, runtime) zwracająca TYLKO zmienione pola stanu,
    Runtime[RunContext] - wstrzykiwany do węzła; runtime.context to RunContext z invoke(..., context=...),
    START i END - znaczniki początku i końca; compile() zwraca graf, który się uruchamia przez invoke(),
    Send(węzeł, ładunek) - polecenie "uruchom ten węzeł z tym stanem"; lista Send zwrócona z krawędzi warunkowej
    uruchamia węzeł wielokrotnie, równolegle (wzorzec map-reduce),
    reducer - funkcja przypisana polu stanu (Annotated[list, operator.add]), która łączy zwroty równoległych węzłów,
    config={"max_concurrency": n} w invoke() - ilu węzłów naraz.

Test ręczny (z katalogu głównego repo; wymaga zainstalowanego langgraph, bez wywołań modelu i bez sieci):
    python -m dev_agents.graph
        buduje kontekst (modele, spis bazy wiedzy, szablon), podmienia modele plannera, analityków, autora diagramu i pisarzy na udawane (bez sieci)
        i uruchamia graf na małym projekcie tymczasowym oraz na robotach testowych 02 i 01 (tylko odczyt, bez
        zapisu w nich); dla każdego wypisuje stan końcowy, porównuje mapę z grafu z mapą z bezpośredniego skanu,
        sprawdza linie postępu (scan, planner, analityk dla każdej jednostki, flow_writer: start i koniec z czasem), to, że plan
        obejmuje wszystkie jednostki kodu i trafił do plan.json w magazynie tymczasowym, oraz że notatek jest tyle
        co zadań, każda jednostka ma notatkę w stanie i w notes/<jednostka>.json, a diagram jest spójny i zapisany jako flow.json, a pisarzy było tylu co zakładek z sekcjami dla pisarza (każda zakładka raz, tabs/<zakładka>.json zgodne ze stanem),
        treść przewodnika ma zakładki w kolejności szablonu i jest zapisana jako guide_content.json; na końcu
        "zgodne z oczekiwaniem: True".
        Jeśli w środowisku nie ma zmiennych z kluczem i adresem modeli (nazwy w config.yaml), test ustawia
        atrapy tylko dla tego procesu - prawdziwe modele nie są wołane.
"""

import os

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

import dev_agents.agents.analyst as _analyst
import dev_agents.agents.flow_writer as _flow_writer
import dev_agents.agents.planner as _planner
import dev_agents.agents.writer as _writer
import dev_agents.assemble as _assemble
import dev_agents.config as _config
import dev_agents.context as _context
import dev_agents.progress as _progress
import dev_agents.guide_template as _template
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


def plan_tabs_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Wpisuje do stanu tab_ids: id zakładek szablonu (dla technologii projektu), które mają sekcje do napisania przez pisarza, w kolejności szablonu.

    Po co: krawędź warunkowa dispatch_writers widzi tylko stan, a lista zakładek zależy od szablonu z kontekstu i technologii
    projektu; węzeł nie woła modelu i niczego nie zapisuje.
    """
    szablon = _template.sections_for_technology(runtime.context.template, state["project_map"].technology)
    identyfikatory = []
    for zakladka in szablon.tabs:
        if _writer.writer_sections(zakladka):
            identyfikatory.append(zakladka.id)
    zmiana_stanu = {"tab_ids": identyfikatory}
    return zmiana_stanu


# --- Krawędzie warunkowe i ustawienia uruchomienia ---


def dispatch_analysts(
    state: _state.RunState,
) -> list[Send]:
    """Zwraca po jednym poleceniu Send("analyst", ...) na każde zadanie z planu; ładunek to mapa projektu, plan i zadanie.

    Po co: krawędź warunkowa za plannerem - LangGraph uruchomi węzeł analyst tyle razy, ile jest zadań, równolegle
    (nie więcej naraz niż max_concurrency). Plan jest uzupełniony przez complete_plan, więc zadań jest tyle co jednostek kodu.
    """
    polecenia = []
    for zadanie in state["plan"].tasks:
        ladunek = {"project_map": state["project_map"], "plan": state["plan"], "task": zadanie}
        polecenia.append(Send("analyst", ladunek))
    return polecenia


def dispatch_writers(
    state: _state.RunState,
) -> list[Send]:
    """Zwraca po jednym poleceniu Send("writer", ...) na każdą zakładkę z tab_ids; ładunek to mapa projektu, plan, notatki, diagram i tab_id.

    Po co: krawędź warunkowa za plan_tabs - LangGraph uruchomi węzeł writer tyle razy, ile jest zakładek, równolegle
    (nie więcej naraz niż max_concurrency). Każdy pisarz dostaje komplet notatek i gotowy diagram.
    """
    polecenia = []
    for identyfikator in state["tab_ids"]:
        ladunek = {"project_map": state["project_map"], "plan": state["plan"], "notes": state["notes"], "flow": state["flow"], "tab_id": identyfikator}
        polecenia.append(Send("writer", ladunek))
    return polecenia


def run_config(
    app_config: _config.AppConfig,
) -> dict:
    """Zwraca ustawienia uruchomienia grafu (argument config w invoke): max_concurrency z analysis.max_concurrency (dla analityków i pisarzy).

    Po co: LangGraph ogranicza liczbę równoległych węzłów tylko przez to ustawienie; jedno miejsce, które woła main.py i test.
    """
    ustawienia = {"max_concurrency": app_config.analysis.max_concurrency}
    return ustawienia


# --- Budowa grafu ---


def build_graph():
    """Buduje i kompiluje graf START -> scan -> planner -> analyst (po jednym na zadanie, równolegle) -> flow_writer -> plan_tabs -> writer (po jednym na zakładkę, równolegle) -> assemble -> END; zwraca graf gotowy do invoke(stan, context=RunContext, config=run_config(...)).

    Po co: jedno miejsce z układem grafu - kolejne kroki planu dopisują tu węzły i krawędzie.
    """
    budowniczy = StateGraph(_state.RunState, context_schema=_context.RunContext)
    budowniczy.add_node("scan", scan_node)
    budowniczy.add_node("planner", _planner.planner_node)
    budowniczy.add_edge(START, "scan")
    budowniczy.add_edge("scan", "planner")
    budowniczy.add_node("analyst", _analyst.analyst_node)
    budowniczy.add_conditional_edges("planner", dispatch_analysts, ["analyst"])
    budowniczy.add_node("flow_writer", _flow_writer.flow_writer_node)
    budowniczy.add_edge("analyst", "flow_writer")
    budowniczy.add_node("plan_tabs", plan_tabs_node)
    budowniczy.add_edge("flow_writer", "plan_tabs")
    budowniczy.add_node("writer", _writer.writer_node)
    budowniczy.add_conditional_edges("plan_tabs", dispatch_writers, ["writer"])
    budowniczy.add_node("assemble", _assemble.assemble_node)
    budowniczy.add_edge("writer", "assemble")
    budowniczy.add_edge("assemble", END)
    graf = budowniczy.compile()
    return graf


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile

    import dev_agents.config as _config
    import dev_agents.fakes as _fakes
    import dev_agents.flow as _flow
    import dev_agents.guide_content as _content
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

    def _fake_analyst_answer(
        messages,
    ):
        """Odpowiada jak model analityka: dla promptu części 1 notatką NoteFlow z celem, dla części 2 NoteDetails z pustymi listami.

        Po co: analityk woła model dwa razy z różnymi schematami, a udawany model rozpoznaje część po opisie w prompcie;
        nazwę jednostki i tak ustawia kod analityka, więc odpowiedź jej nie zależy.
        """
        odpowiedz = _schemas.NoteDetails(
            settings=[],
            requirements=[],
            external_dependencies=[],
            risky_places=[],
            possible_failures=[],
            extension_points=[],
            conventions=[],
            maintainer_hints=[],
            glossary_candidates=[],
        )
        if "CZĘŚĆ 1 z 2" in messages[1].content:
            odpowiedz = _schemas.NoteFlow(
                unit_name="dowolna",
                purpose="Cel testowy",
                flow_role="",
                automated_application="",
                key_functions=[],
                actions=[],
                process_steps=[],
                error_handling=[],
                inputs=[],
                outputs=[],
            )
        return odpowiedz

    def _fake_flow() -> _content.FlowGraph:
        """Zwraca mały poprawny diagram (start, jeden krok, koniec), którym odpowiada udawany autor diagramu.

        Po co: test grafu sprawdza przekazanie notatek i zapis diagramu, nie jego treść.
        """
        diagram = _content.FlowGraph(
            nodes=[
                _content.FlowNode(id="n1", kind="start", label="Start"),
                _content.FlowNode(id="n2", kind="step", label="Krok", module="main.py", functions=["run:1"]),
                _content.FlowNode(id="n3", kind="end", label="Koniec"),
            ],
            edges=[_content.FlowEdge(source="n1", target="n2"), _content.FlowEdge(source="n2", target="n3")],
        )
        return diagram

    def _make_fake_writer_answer(
        template: _template.GuideTemplate,
    ):
        """Zwraca funkcję odpowiedzi udawanego pisarza: dla zakładki z "tab_id: <id>" w prompcie zwraca odpowiedź z pustym blokiem każdej sekcji pisarza.

        Po co: pisarz woła model ze schematem zależnym od zakładki, więc udawana odpowiedź musi mieć klasę tego schematu;
        puste bloki nie mają problemów (puste sekcje wymagane renderer pokaże jako "nie wynika z kodu").
        """

        def answer(
            messages,
        ):
            """Czyta id zakładki z promptu i buduje odpowiedź w klasie schematu tej zakładki.

            Po co: odpowiedź udawanego modelu zależna od zakładki.
            """
            tab_id = ""
            for linia in messages[1].content.split("\n"):
                if linia.startswith("tab_id: "):
                    tab_id = linia[len("tab_id: "):].strip()
            sekcje = []
            for zakladka in template.tabs:
                if zakladka.id == tab_id:
                    sekcje = _writer.writer_sections(zakladka)
            bloki = []
            for sekcja in sekcje:
                blok = {"section_id": sekcja.id}
                for nazwa in _writer.block_fields(sekcje):
                    blok[nazwa] = []
                bloki.append(blok)
            odpowiedz = _writer.tab_response_model(sekcje).model_validate({"tab_id": tab_id, "blocks": bloki})
            return odpowiedz

        return answer

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
        plan.json w magazynie i że planner zgłosił start oraz koniec z liczbą zadań, że notatek jest tyle co zadań
        (każda jednostka dokładnie raz, także w notes/<jednostka>.json w magazynie) i że każdy analityk zgłosił start
        oraz koniec z czasem; progress_lines to lista, do której context.report dopisuje linie.
        """
        katalog_wynikow = os.path.join(root, _output.OUTPUT_DIR_NAME)
        istnial_przed = os.path.exists(katalog_wynikow)
        ile_linii_przed = len(progress_lines)
        stan = graph.invoke({"project_path": root}, context=context, config=run_config(context.config))
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
        notatki = stan.get("notes", [])
        nazwy_notatek = []
        for notatka in notatki:
            nazwy_notatek.append(notatka.unit_name)
        nazwy_zadan = []
        for zadanie in plan.tasks:
            nazwy_zadan.append(zadanie.unit)
        notatki_zgodne = len(notatki) == len(plan.tasks) and sorted(nazwy_notatek) == sorted(nazwy_zadan)
        notatki_zapisane = True
        for notatka in notatki:
            zapisana = context.store.load_json(f"notes/{notatka.unit_name}.json", _schemas.ModuleNote)
            if zapisana != notatka:
                notatki_zapisane = False
        start_analitykow = 0
        koniec_analitykow = 0
        for linia_postepu in nowe_linie:
            if "] analyst " in linia_postepu and linia_postepu.endswith(": start"):
                start_analitykow += 1
            if "] analyst " in linia_postepu and ": gotowe w " in linia_postepu:
                koniec_analitykow += 1
        postep_analitykow = start_analitykow == len(plan.tasks) and koniec_analitykow == len(plan.tasks)
        diagram = stan["flow"]
        problemy_diagramu, _ = _flow.validate_flow(diagram, context.config.flow)
        diagram_zapisany = context.store.load_json("flow.json", _content.FlowGraph) == diagram
        linie_flow = []
        for linia_postepu in nowe_linie:
            if "] flow_writer: " in linia_postepu:
                linie_flow.append(linia_postepu)
        postep_flow = len(linie_flow) == 2 and linie_flow[0].endswith("] flow_writer: start") and "] flow_writer: gotowe w " in linie_flow[1]
        diagram_zgodny = problemy_diagramu == [] and diagram_zapisany and postep_flow
        szablon_technologii = _template.sections_for_technology(context.template, mapa.technology)
        oczekiwane_zakladki = []
        wszystkie_zakladki = []
        for zakladka in szablon_technologii.tabs:
            wszystkie_zakladki.append(zakladka.id)
            if _writer.writer_sections(zakladka):
                oczekiwane_zakladki.append(zakladka.id)
        napisane = []
        for zakladka in stan.get("tabs", []):
            napisane.append(zakladka.tab_id)
        zakladki_zgodne = sorted(napisane) == sorted(oczekiwane_zakladki)
        zakladki_zapisane = True
        for zakladka in stan.get("tabs", []):
            if context.store.load_json(f"tabs/{zakladka.tab_id}.json", _content.GuideTab) != zakladka:
                zakladki_zapisane = False
        start_pisarzy = 0
        koniec_pisarzy = 0
        linie_assemble = []
        for linia_postepu in nowe_linie:
            if "] writer " in linia_postepu and linia_postepu.endswith(": start"):
                start_pisarzy += 1
            if "] writer " in linia_postepu and ": gotowe w " in linia_postepu:
                koniec_pisarzy += 1
            if "] assemble: " in linia_postepu:
                linie_assemble.append(linia_postepu)
        postep_pisarzy = start_pisarzy == len(oczekiwane_zakladki) and koniec_pisarzy == len(oczekiwane_zakladki)
        tresc = stan["content"]
        kolejnosc_tresci = []
        for zakladka in tresc.tabs:
            kolejnosc_tresci.append(zakladka.tab_id)
        tresc_zgodna = (
            kolejnosc_tresci == wszystkie_zakladki
            and tresc.flow == diagram
            and context.store.load_json("guide_content.json", _content.GuideContent) == tresc
            and len(linie_assemble) == 2
            and "problemów: 0" in linie_assemble[1]
        )
        zgodne = (
            mapa == bezposrednio
            and diagram_zgodny
            and zakladki_zgodne
            and zakladki_zapisane
            and postep_pisarzy
            and tresc_zgodna
            and notatki_zgodne
            and notatki_zapisane
            and postep_analitykow
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
            f"  notatek ({len(notatki)}) tyle co zadań, każda jednostka raz: {notatki_zgodne}",
            f"  notes/<jednostka>.json w magazynie == notatki ze stanu: {notatki_zapisane}",
            f"  analitycy: start i koniec z czasem dla każdej jednostki: {postep_analitykow}",
            f"  diagram bez problemów ({len(diagram.nodes)} klocków), flow.json == diagram ze stanu, linie postępu flow_writer: {diagram_zgodny}",
            f"  zakładki od pisarzy ({len(napisane)}) tyle co zakładek z sekcjami dla pisarza, każda raz: {zakladki_zgodne}",
            f"  tabs/<zakładka>.json w magazynie == zakładki ze stanu: {zakladki_zapisane}",
            f"  pisarze: start i koniec z czasem dla każdej zakładki: {postep_pisarzy}",
            f"  treść: zakładki w kolejności szablonu, diagram ze stanu, guide_content.json, assemble bez problemów: {tresc_zgodna}",
        ]
        for linia_postepu in nowe_linie:
            linie.append(f"    {linia_postepu}")
        wynik_przypadku = (linie, zgodne)
        return wynik_przypadku

    def manual_test():
        """Buduje kontekst i graf, uruchamia je na projekcie tymczasowym i robotach testowych 02 i 01 (tylko odczyt).

        Po co: sprawdzenie szkieletu LangGraph z prawdziwym skanem i udawanymi modelami plannera (pusty plan,
        który complete_plan uzupełnia o wszystkie jednostki), analityków (stała notatka), autora diagramu (stały diagram) i pisarzy (puste bloki sekcji), bez sieci i bez zapisu w cudzych projektach.
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
            kontekst.models["analyst"] = _fakes.FakeStructuredModel(_fake_analyst_answer)
            kontekst.models["flow_writer"] = _fakes.FakeStructuredModel(_fake_flow())
            kontekst.models["writer"] = _fakes.FakeStructuredModel(_make_fake_writer_answer(kontekst.template))
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
