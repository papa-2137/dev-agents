"""Agent autor diagramu: z notatek wszystkich analityków układa diagram całego procesu robota (FlowGraph).

Co robi: write_flow() składa prompt (podsumowanie plannera, kontekst projektu z kolejnością czytania i powiązaniami
plików, notatki analityków w kolejności czytania - tylko pola przebiegu, wiedza: zasady diagramu, technologia,
framework), woła model agenta flow_writer ze schematem FlowGraph (jedna odpowiedź) i sprawdza diagram kodem
(flow.validate_flow). Gdy są problemy albo ostrzeżenie o rozmiarze, woła model jeszcze raz - z poprzednią wersją
i listą problemów w prompcie. Drugą wersję bierze, chyba że ma więcej problemów niż pierwsza. flow_writer_node()
to węzeł grafu: zapisuje flow.json i dopisuje do stanu flow.

Dlaczego istnieje: diagram jest kręgosłupem przewodnika - jedyny agent, który widzi cały proces naraz (analitycy
widzą po jednej jednostce). Model zwraca tylko graf klocków i strzałek; poprawność gwarantuje kod: nie ukrywamy
problemów - diagram, który po ponowieniu nadal ma problemy, jest zwracany razem z ich listą (renderer nie rysuje
niespójnego diagramu, tylko pokazuje listę problemów).

Rola: agent grafu (faza F); do grafu po analitykach dołącza go krok 54.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.agents.flow_writer
        offline, na udawanym modelu: kolejność notatek, prompt (notatki w kolejności czytania tylko z polami przebiegu,
        zasady diagramu, limity, brak ścieżki dysku), jedno wywołanie dla poprawnego diagramu, ponowienie z listą
        problemów i poprzednią wersją, ponowienie przy ostrzeżeniu o rozmiarze, wybór lepszej z dwóch wersji,
        diagram z problemami po ponowieniu, odmowa bez notatek, węzeł grafu (flow.json, linie postępu);
        na końcu "zgodne z oczekiwaniem: True"
    python -m dev_agents.agents.flow_writer <katalog robota>
        dodatkowo woła PRAWDZIWY model: skanuje robota w pamięci, czyta <katalog robota>/dev_agents_doc/notes/*.json
        (najpierw pełny przebieg: python main.py --project <katalog robota>) i plan.json (gdy go nie ma - plan minimalny),
        wypisuje problemy i ostrzeżenia diagramu, zapisuje flow.json w katalogu wyników robota i podgląd przewodnika
        (zakładka Przepływ działania, reszta zaślepki) w guide_test.html w katalogu głównym repo.
        Wymaga zmiennych środowiskowych z kluczem i adresem modeli (nazwy w config.yaml).
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

import dev_agents.agents.common as _common
import dev_agents.context as _context
import dev_agents.flow as _flow
import dev_agents.guide_content as _content
import dev_agents.llm as _llm
import dev_agents.progress as _progress
import dev_agents.prompts as _prompts
import dev_agents.schemas as _schemas
import dev_agents.state as _state

_AGENT_NAME = "flow_writer"


# --- Dane dla promptu ---


def order_notes(
    notes: list[_schemas.ModuleNote],
    plan: _schemas.Plan,
) -> list[_schemas.ModuleNote]:
    """Zwraca notatki w kolejności zadań z planu (kolejność czytania); notatki spoza planu dochodzą na końcu, alfabetycznie.

    Po co: analitycy pracują równolegle i notatki wracają w dowolnej kolejności, a autor diagramu ma dostać proces
    od punktu wejścia w głąb.
    """
    wedlug_nazwy = {}
    for notatka in notes:
        wedlug_nazwy[notatka.unit_name] = notatka
    uporzadkowane = []
    for zadanie in plan.tasks:
        if zadanie.unit in wedlug_nazwy:
            uporzadkowane.append(wedlug_nazwy.pop(zadanie.unit))
    for nazwa in sorted(wedlug_nazwy):
        uporzadkowane.append(wedlug_nazwy[nazwa])
    return uporzadkowane


def format_notes(
    notes: list[_schemas.ModuleNote],
) -> str:
    """Zwraca notatki jako tekst do promptu: każda w znaczniku <notatka jednostka="...">, w treści JSON tylko z polami przebiegu (NoteFlow).

    Po co: diagram potrzebuje celu, roli, czynności, przebiegu, obsługi błędów oraz wejść i wyjść - ustawienia,
    ryzyka i awarie to materiał dla pisarzy, więc nie zajmują tokenów autora diagramu. JSON bez zamiany polskich
    znaków na kody (ensure_ascii=False).
    """
    pola = set(_schemas.NoteFlow.model_fields)
    bloki = []
    for notatka in notes:
        dane = notatka.model_dump(include=pola)
        tresc = json.dumps(dane, ensure_ascii=False, indent=1)
        bloki.append(f'<notatka jednostka="{notatka.unit_name}">\n{tresc}\n</notatka>')
    tekst = "\n\n".join(bloki)
    return tekst


def build_project_context(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca kontekst projektu jako JSON: nazwa, technologia, punkty wejścia, frameworki, kolejność czytania i powiązania plików.

    Po co: autor diagramu widzi, od czego robot startuje i które pliki z których korzystają; bez ścieżki bezwzględnej
    katalogu (układ dysku nie jest modelowi potrzebny) i bez faktów o funkcjach - te są w notatkach.
    """
    dane = {
        "project_name": project_map.project_name,
        "technology": project_map.technology,
        "entrypoints": project_map.entrypoints,
        "frameworks": project_map.frameworks,
        "reading_order": project_map.reading_order,
        "dependency_edges": project_map.dependency_edges,
    }
    tekst = json.dumps(dane, ensure_ascii=False, indent=1)
    return tekst


def build_flow_variables(
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    notes: list[_schemas.ModuleNote],
    knowledge_text: str,
    flow_limits: tuple[int, int],
    previous_flow: _content.FlowGraph | None,
    problems: list[str],
) -> dict:
    """Zwraca zmienne do szablonu prompts/flow_writer/user.md; przy ponowieniu (previous_flow i problemy) także sekcję poprawki.

    Po co: w jednym miejscu widać, co dokładnie autor diagramu dostaje. Argumenty: flow_limits - (max_nodes,
    max_decisions) z config.flow, knowledge_text - gotowy tekst wiedzy (common.format_knowledge), previous_flow
    i problems - poprzednia wersja diagramu i lista problemów albo None i pusta lista przy pierwszym wywołaniu.
    """
    poprzedni_tekst = ""
    if previous_flow is not None:
        poprzedni_tekst = previous_flow.model_dump_json(indent=1)
    linie_problemow = []
    for problem in problems:
        linie_problemow.append(f"- {problem}")
    zmienne = {
        "project_name": project_map.project_name,
        "plan_summary": plan.summary,
        "max_nodes": flow_limits[0],
        "max_decisions": flow_limits[1],
        "project_context": build_project_context(project_map),
        "notes": format_notes(notes),
        "knowledge": knowledge_text,
        "previous_flow": poprzedni_tekst,
        "problems_text": "\n".join(linie_problemow),
    }
    return zmienne


# --- Wywołanie modelu ---


def _ask_model(
    context: _context.RunContext,
    variables: dict,
) -> _content.FlowGraph:
    """Składa prompt z podanych zmiennych, woła model agenta flow_writer ze schematem FlowGraph i zwraca diagram.

    Po co: jedno wywołanie modelu - pierwsze i ponowione różnią się tylko zmiennymi. Brak odpowiedzi zgodnej ze
    schematem kończy się RuntimeError z przyczyną (llm.invoke_structured).
    """
    tekst_system, tekst_user = _prompts.render_prompt(context.config.paths.prompts, _AGENT_NAME, variables)
    odpowiedz = _llm.invoke_structured(
        context.models[_AGENT_NAME],
        _content.FlowGraph,
        _llm.get_structured_output_method(context.config, _AGENT_NAME),
        [SystemMessage(content=tekst_system), HumanMessage(content=tekst_user)],
    )
    return odpowiedz


def _check_flow(
    flow: _content.FlowGraph,
    context: _context.RunContext,
) -> tuple[list[str], list[str]]:
    """Zwraca (problemy, ostrzeżenia) diagramu według flow.validate_flow z progami z configu.

    Po co: jedno miejsce sprawdzenia dla pierwszej i ponowionej wersji.
    """
    wynik = _flow.validate_flow(flow, context.config.flow)
    return wynik


def write_flow(
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    notes: list[_schemas.ModuleNote],
    context: _context.RunContext,
) -> tuple[_content.FlowGraph, list[str], list[str], int]:
    """Układa diagram z notatek: zwraca (diagram, problemy, ostrzeżenia, liczba wywołań modelu - 1 albo 2).

    Po co: cała logika autora diagramu w jednej funkcji, z której korzystają węzeł grafu i test ręczny. Pierwsza
    wersja z promptu z notatkami w kolejności czytania; gdy validate_flow zgłosi problemy albo ostrzeżenie o rozmiarze,
    model dostaje jedno ponowienie z poprzednią wersją i listą (problemy i ostrzeżenia razem). Druga wersja wygrywa,
    chyba że ma więcej problemów niż pierwsza - wtedy zostaje pierwsza. Zwrócone problemy i ostrzeżenia dotyczą
    zwróconej wersji; niepuste problemy znaczą, że diagram jest niespójny (decyduje o tym wołający).

    Uwaga: brak notatek to ValueError - nie ma z czego układać diagramu.
    """
    if not notes:
        komunikat_bledu = "Brak notatek analityków - nie ma z czego ułożyć diagramu"
        raise ValueError(komunikat_bledu)
    uporzadkowane = order_notes(notes, plan)
    pliki_wiedzy = _common.collect_knowledge_files(context.config, project_map, plan.flow_knowledge)
    tekst_wiedzy = _common.format_knowledge(context.config, pliki_wiedzy)
    limity = (context.config.flow.max_nodes, context.config.flow.max_decisions)
    zmienne = build_flow_variables(project_map, plan, uporzadkowane, tekst_wiedzy, limity, None, [])
    diagram = _ask_model(context, zmienne)
    problemy, ostrzezenia = _check_flow(diagram, context)
    wywolania = 1
    if problemy or ostrzezenia:
        zmienne_poprawki = build_flow_variables(project_map, plan, uporzadkowane, tekst_wiedzy, limity, diagram, problemy + ostrzezenia)
        druga_wersja = _ask_model(context, zmienne_poprawki)
        wywolania = 2
        problemy_2, ostrzezenia_2 = _check_flow(druga_wersja, context)
        if len(problemy_2) <= len(problemy):
            diagram = druga_wersja
            problemy = problemy_2
            ostrzezenia = ostrzezenia_2
    wynik = (diagram, problemy, ostrzezenia, wywolania)
    return wynik


# --- Węzeł grafu ---


def flow_writer_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Węzeł flow_writer: układa diagram z notatek ze stanu, zapisuje flow.json i zwraca zmienione pole stanu: flow.

    Po co: etap po analitykach - diagram całego procesu. Praca jest owinięta w Stage: start, uwagi o problemach
    i ostrzeżeniach diagramu (po ponowieniu), koniec z czasem, liczbą klocków i strzałek oraz liczbą wywołań modelu.
    Niespójny diagram nie przerywa przebiegu - jest zapisany, a jego problemy zgłoszone jako uwagi (renderer pokaże listę).
    """
    kontekst = runtime.context
    with _progress.Stage(kontekst.report, _AGENT_NAME) as etap:
        diagram, problemy, ostrzezenia, wywolania = write_flow(state["project_map"], state["plan"], state["notes"], kontekst)
        for problem in problemy:
            etap.note(f"problem: {problem}")
        for ostrzezenie in ostrzezenia:
            etap.note(f"ostrzeżenie: {ostrzezenie}")
        zapisany_plik = kontekst.store.save_json("flow.json", diagram)
        etap.set_result(f"klocków: {len(diagram.nodes)}, strzałek: {len(diagram.edges)}, wywołań modelu: {wywolania}, zapisano {zapisany_plik}")
    zmiana_stanu = {"flow": diagram}
    return zmiana_stanu


# --- Test ręczny ---

if __name__ == "__main__":
    import glob
    import os
    import sys
    import tempfile
    import types

    import dev_agents.config as _config
    import dev_agents.fakes as _fakes
    import dev_agents.guide_placeholders as _placeholders
    import dev_agents.guide_template as _guide_template
    import dev_agents.output as _output
    import dev_agents.render as _render
    import dev_agents.scanner as _scanner

    _RULES_MARKER = "Zasady diagramu przepływu"

    def _note(
        unit_name: str,
        purpose: str,
    ) -> _schemas.ModuleNote:
        """Zwraca notatkę z jedną czynnością, hasłem w ustawieniach i ryzykiem - tyle, by sprawdzić, które pola trafiają do promptu.

        Po co: test sprawdza, że autor diagramu dostaje pola przebiegu, a nie ustawienia i ryzyka (to materiał pisarzy).
        """
        notatka = _schemas.ModuleNote.model_validate(
            {
                "unit_name": unit_name,
                "purpose": purpose,
                "flow_role": "Główna jednostka.",
                "automated_application": "",
                "key_functions": [],
                "actions": [{"title": f"Czynność {unit_name}", "kind": "step", "function": "run", "line": 5, "description": "", "reads": [], "writes": [], "certain": True}],
                "process_steps": [],
                "error_handling": [],
                "inputs": [],
                "outputs": [],
                "settings": [{"file": "config.yaml", "group": "", "key": "UKRYTE_USTAWIENIE", "value": "x", "kind": "other", "location": "", "used_in": [], "plain_password": False, "meaning": "", "certain": True}],
                "requirements": [],
                "external_dependencies": [],
                "risky_places": [{"place": "run", "location": "a.py:1-2", "kind": "test", "reason": "UKRYTE_RYZYKO"}],
                "possible_failures": [],
                "extension_points": [],
                "conventions": [],
                "maintainer_hints": [],
                "glossary_candidates": [],
            }
        )
        return notatka

    def _diagram(
        steps: int,
        starts: int = 1,
    ) -> _content.FlowGraph:
        """Zwraca prosty diagram: podana liczba startów, potem łańcuch klocków step i koniec; poprawny, gdy startów jest 1.

        Po co: kontrolowany diagram do testów - dwa starty dają problem, dużo klocków daje ostrzeżenie o rozmiarze.
        """
        klocki = []
        strzalki = []
        for numer in range(starts):
            klocki.append(_content.FlowNode(id=f"s{numer}", kind="start", label="Start"))
        poprzedni = "s0"
        for numer in range(steps):
            identyfikator = f"n{numer}"
            klocki.append(_content.FlowNode(id=identyfikator, kind="step", label=f"Krok {numer}", module="main.py", functions=["run:5"]))
            strzalki.append(_content.FlowEdge(source=poprzedni, target=identyfikator))
            poprzedni = identyfikator
        klocki.append(_content.FlowNode(id="k", kind="end", label="Koniec"))
        strzalki.append(_content.FlowEdge(source=poprzedni, target="k"))
        for numer in range(1, starts):
            strzalki.append(_content.FlowEdge(source=f"s{numer}", target="n0"))
        diagram = _content.FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    def _model(
        answers: list[_content.FlowGraph],
        seen_prompts: list[str],
    ) -> _fakes.FakeStructuredModel:
        """Zwraca udawany model, który kolejnymi wywołaniami odpowiada kolejnymi diagramami z listy i zapamiętuje prompty użytkownika.

        Po co: test steruje tym, co model odpowie przy pierwszym i ponowionym wywołaniu.
        """

        def answer(
            messages,
        ):
            """Zapamiętuje prompt użytkownika i zwraca diagram o numerze równym liczbie dotychczasowych promptów.

            Po co: odpowiedź udawanego modelu zależna od numeru wywołania.
            """
            numer = len(seen_prompts)
            seen_prompts.append(messages[1].content)
            odpowiedz = answers[min(numer, len(answers) - 1)]
            return odpowiedz

        model = _fakes.FakeStructuredModel(answer)
        return model

    def _context_for(
        app_config: _config.AppConfig,
        model,
        report,
        store,
    ) -> types.SimpleNamespace:
        """Zwraca uproszczony kontekst (config, model flow_writer, report, magazyn) - tyle, ile czytają write_flow i węzeł.

        Po co: test offline nie buduje prawdziwych modeli wszystkich agentów i nie wymaga kluczy.
        """
        kontekst = types.SimpleNamespace(config=app_config, models={_AGENT_NAME: model}, report=report, store=store)
        return kontekst

    def _empty_map(
        root: str,
    ) -> _schemas.ProjectMap:
        """Zwraca mapę projektu z jedną jednostką i kontekstem (punkt wejścia, kolejność czytania, powiązania); ścieżka root jest tylko po to, by sprawdzić, że nie trafia do promptu.

        Po co: write_flow czyta z mapy tylko kontekst projektu, więc wystarczy mapa zbudowana ręcznie.
        """
        mapa = _schemas.ProjectMap(
            project_name="robot_testowy",
            root=root,
            technology="python",
            entrypoints=["main.py"],
            files=[],
            code_units=[],
            reading_order=["main.py", "helper.py"],
            dependency_edges=[["main.py", "helper.py"]],
        )
        return mapa

    def _offline_checks(
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza autora diagramu na udawanym modelu; zwraca (opis, zgodne).

        Po co: kolejność notatek, prompt, ponowienia, wybór lepszej wersji, brak notatek i węzeł grafu bez sieci i kosztu.
        """
        sciezka_dysku = os.path.join(temp_dir, "ukryty_katalog_uzytkownika")
        mapa = _empty_map(sciezka_dysku)
        plan = _schemas.Plan(
            summary="Plan testowy.",
            tasks=[_schemas.AnalysisTask(unit="main.py"), _schemas.AnalysisTask(unit="helper.py")],
            flow_knowledge=["diagram_rules.md"],
        )
        notatki = [_note("helper.py", "CEL_POMOCNIKA"), _note("main.py", "CEL_GLOWNEJ"), _note("obca.py", "CEL_OBCEJ")]
        magazyn = _output.RunStore(os.path.join(temp_dir, "wyniki"))
        wyniki = []

        uporzadkowane = order_notes(notatki, plan)
        nazwy = []
        for notatka in uporzadkowane:
            nazwy.append(notatka.unit_name)
        wyniki.append((f"order_notes: kolejność planu, obca na końcu ({nazwy})", nazwy == ["main.py", "helper.py", "obca.py"]))

        prompty = []
        model = _model([_diagram(3)], prompty)
        kontekst = _context_for(app_config, model, [].append, magazyn)
        diagram, problemy, ostrzezenia, wywolania = write_flow(mapa, plan, notatki, kontekst)
        pierwszy = prompty[0]
        wyniki.append(("poprawny diagram: jedno wywołanie, bez problemów i ostrzeżeń", model.calls == 1 and wywolania == 1 and problemy == [] and ostrzezenia == []))
        wyniki.append(("poprawny diagram: zwrócony taki, jaki odpowiedział model", diagram == _diagram(3)))
        wyniki.append(("prompt: notatki w kolejności czytania", 0 < pierwszy.index("CEL_GLOWNEJ") < pierwszy.index("CEL_POMOCNIKA") < pierwszy.index("CEL_OBCEJ")))
        wyniki.append(("prompt: pola przebiegu są, ustawienia i ryzyka nie", "Czynność main.py" in pierwszy and "UKRYTE_USTAWIENIE" not in pierwszy and "UKRYTE_RYZYKO" not in pierwszy))
        wyniki.append(("prompt: zasady diagramu z bazy wiedzy", _RULES_MARKER in pierwszy))
        wyniki.append(("prompt: kolejność czytania i powiązania plików", '"reading_order"' in pierwszy and "helper.py" in pierwszy and '"dependency_edges"' in pierwszy))
        wyniki.append(("prompt: limity z configu", f"najwyżej {app_config.flow.max_nodes} klocków" in pierwszy and f"najwyżej {app_config.flow.max_decisions} decyzji" in pierwszy))
        wyniki.append(("prompt: bez ścieżki dysku i bez sekcji poprawki", "ukryty_katalog_uzytkownika" not in pierwszy and "<poprawka>" not in pierwszy))

        prompty = []
        model = _model([_diagram(3, starts=2), _diagram(3)], prompty)
        kontekst = _context_for(app_config, model, [].append, magazyn)
        diagram, problemy, ostrzezenia, wywolania = write_flow(mapa, plan, notatki, kontekst)
        problemy_pierwszej, _ = _flow_module_validate(_flow_for_two_starts(), app_config)
        wyniki.append(("ponowienie: dwa starty → dwa wywołania, druga wersja poprawna", model.calls == 2 and wywolania == 2 and problemy == [] and diagram == _diagram(3)))
        wyniki.append(("ponowienie: prompt z poprzednią wersją i listą problemów", "<poprawka>" in prompty[1] and '"s1"' in prompty[1] and problemy_pierwszej[0] in prompty[1]))

        prompty = []
        za_duzy = _diagram(app_config.flow.max_nodes + 2)
        model = _model([za_duzy, za_duzy], prompty)
        kontekst = _context_for(app_config, model, [].append, magazyn)
        diagram, problemy, ostrzezenia, wywolania = write_flow(mapa, plan, notatki, kontekst)
        wyniki.append(("ostrzeżenie o rozmiarze: ponowienie, po nim ostrzeżenie zostaje, diagram bez problemów", model.calls == 2 and problemy == [] and len(ostrzezenia) == 1 and "klocków" in prompty[1]))

        prompty = []
        gorsza = _diagram(3, starts=2)
        gorsza.nodes[2].module = ""
        model = _model([_diagram(3, starts=2), gorsza], prompty)
        kontekst = _context_for(app_config, model, [].append, magazyn)
        diagram, problemy, ostrzezenia, wywolania = write_flow(mapa, plan, notatki, kontekst)
        wyniki.append(("druga wersja gorsza (dwa starty i klocek bez modułu): zostaje pierwsza (dwa starty)", model.calls == 2 and diagram == _diagram(3, starts=2) and len(problemy) >= 1))

        prompty = []
        model = _model([_diagram(3, starts=2)], prompty)
        kontekst = _context_for(app_config, model, [].append, magazyn)
        diagram, problemy, ostrzezenia, wywolania = write_flow(mapa, plan, notatki, kontekst)
        wyniki.append(("problemy po ponowieniu: zwrócone razem z diagramem", model.calls == 2 and len(problemy) >= 1 and "start" in problemy[0]))

        blad = ""
        try:
            write_flow(mapa, plan, [], kontekst)
        except ValueError as wyjatek:
            blad = str(wyjatek)
        wyniki.append(("brak notatek: ValueError", "Brak notatek" in blad))

        linie = []
        model = _model([_diagram(3)], [])
        kontekst = _context_for(app_config, model, linie.append, magazyn)
        stan = {"project_map": mapa, "plan": plan, "notes": notatki}
        zmiana = flow_writer_node(stan, types.SimpleNamespace(context=kontekst))
        zapisany = magazyn.load_json("flow.json", _content.FlowGraph)
        wyniki.append(("węzeł: zwraca flow i zapisuje flow.json", list(zmiana) == ["flow"] and zmiana["flow"] == _diagram(3) and zapisany == _diagram(3)))
        wyniki.append(("węzeł: linie postępu start i koniec z liczbą klocków i wywołań", len(linie) == 2 and linie[0].endswith("] flow_writer: start") and "klocków: 5, strzałek: 4, wywołań modelu: 1" in linie[1]))

        linie = []
        model = _model([_diagram(3, starts=2)], [])
        kontekst = _context_for(app_config, model, linie.append, magazyn)
        flow_writer_node(stan, types.SimpleNamespace(context=kontekst))
        wyniki.append(("węzeł: problemy diagramu jako uwagi, przebieg się nie przerywa", len(linie) >= 3 and "] flow_writer: problem: " in linie[1]))
        return wyniki

    def _flow_for_two_starts() -> _content.FlowGraph:
        """Zwraca ten sam diagram z dwoma startami, który w teście odpowiada model przy pierwszym wywołaniu.

        Po co: test porównuje listę problemów tego diagramu z tekstem poprawki w prompcie.
        """
        diagram = _diagram(3, starts=2)
        return diagram

    def _flow_module_validate(
        flow: _content.FlowGraph,
        app_config: _config.AppConfig,
    ) -> tuple[list[str], list[str]]:
        """Zwraca (problemy, ostrzeżenia) diagramu z flow.validate_flow - niezależnie od kodu agenta.

        Po co: test sprawdza, że lista problemów w prompcie ponowienia to dokładnie to, co zgłasza kod sprawdzający.
        """
        wynik = _flow.validate_flow(flow, app_config.flow)
        return wynik

    def _real_model_run(
        project_dir: str,
        app_config: _config.AppConfig,
    ) -> None:
        """Czyta notatki robota z dev_agents_doc/notes, woła prawdziwy model autora diagramu, wypisuje wynik i zapisuje flow.json oraz podgląd HTML.

        Po co: sprawdzenie autora diagramu na prawdziwych notatkach i modelu, bez ponownej analizy kodu. Robota nie
        zmienia poza katalogiem wyników (flow.json); podgląd idzie do guide_test.html w katalogu głównym repo.
        """
        project_map = _scanner.build_project_map(project_dir, app_config.scan)
        katalog_wynikow = os.path.join(project_dir, _output.OUTPUT_DIR_NAME)
        pliki_notatek = sorted(glob.glob(os.path.join(katalog_wynikow, "notes", "**", "*.json"), recursive=True))
        if not pliki_notatek:
            sys.exit(f"BŁĄD: brak notatek w {os.path.join(katalog_wynikow, 'notes')} - najpierw pełny przebieg: python main.py --project {project_dir}")
        notatki = []
        for plik_notatki in pliki_notatek:
            with open(plik_notatki, encoding="utf-8") as plik:
                notatki.append(_schemas.ModuleNote.model_validate_json(plik.read()))
        sciezka_planu = os.path.join(katalog_wynikow, "plan.json")
        if os.path.isfile(sciezka_planu):
            with open(sciezka_planu, encoding="utf-8") as plik:
                plan = _schemas.Plan.model_validate_json(plik.read())
        else:
            plan = _schemas.Plan(summary=f"Robot {project_map.project_name} (technologia: {project_map.technology}); plan minimalny.", tasks=[])
            print("Plan minimalny (brak plan.json w katalogu wyników robota).")
        magazyn = _output.RunStore(katalog_wynikow)
        try:
            kontekst = _context.build_context(app_config, magazyn, _progress.print_line)
        except (RuntimeError, ValueError, OSError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        print(f"\n=== Prawdziwy model autora diagramu: {project_map.project_name}, notatek: {len(notatki)} ===")
        stan = {"project_map": project_map, "plan": plan, "notes": notatki}
        try:
            zmiana = flow_writer_node(stan, types.SimpleNamespace(context=kontekst))
        except (ValueError, RuntimeError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        diagram = zmiana["flow"]
        problemy, ostrzezenia = _flow.validate_flow(diagram, app_config.flow)
        print(f"\nKlocki: {len(diagram.nodes)}, strzałki: {len(diagram.edges)}, problemy: {len(problemy)}, ostrzeżenia: {len(ostrzezenia)}")
        for numer, klocek in enumerate(diagram.nodes, start=1):
            print(f"  {numer:2}. [{klocek.kind}] {klocek.label} ({klocek.module} {', '.join(klocek.functions)})")
        for strzalka in diagram.edges:
            print(f"      {strzalka.source} -> {strzalka.target} [{strzalka.kind}] {strzalka.label}")
        szablon = _guide_template.load_template(app_config.paths.guide_template)
        tresc = _placeholders.build_placeholder_content(szablon, project_map).model_copy(update={"flow": diagram})
        html = _render.render_guide(
            tresc,
            szablon,
            project_map,
            os.path.dirname(app_config.paths.guide_template),
            "podgląd diagramu",
            app_config.analysis.long_unit_lines,
            app_config.flow,
        )
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sciezka_html = os.path.join(katalog_repo, "guide_test.html")
        with open(sciezka_html, "w", encoding="utf-8") as plik:
            plik.write(html)
        print(f"\nZapisano flow.json w {katalog_wynikow} i podgląd {sciezka_html} (zakładka Przepływ działania)")

    def manual_test():
        """Uruchamia sprawdzenia offline autora diagramu i wypisuje werdykt; z argumentem <katalog robota> woła też prawdziwy model.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że autor diagramu składa prompt, ponawia i wybiera wersję
        poprawnie; część z prawdziwym modelem pokazuje diagram z prawdziwych notatek.
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
            if len(sys.argv) > 1:
                _real_model_run(sys.argv[1], app_config)
        finally:
            import shutil

            shutil.rmtree(temp_dir)

    manual_test()
