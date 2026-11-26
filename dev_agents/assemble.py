"""Składanie treści przewodnika: diagram i zakładki od pisarzy w jedną GuideContent ze sprawdzeniem kompletności.

Co robi:
    - build_content() składa GuideContent: nazwa projektu, diagram i zakładki w kolejności szablonu (dla technologii
      projektu); zakładka bez pisarza (np. Przepływ działania - sam diagram) i zakładka, której pisarz nie oddał,
      dostają pusty blok listy, żeby renderer miał komplet,
    - check_content() sprawdza całość zwykłym kodem: brak zakładki pisarza, problemy zakładek (brak wymaganej sekcji,
      komórki wierszy, wpisy metryczki bez znaczenia, ścieżki i odwołania do klocków - writer.check_tab) i problemy
      diagramu (flow.validate_flow),
    - assemble_node() to węzeł grafu: składa treść, zapisuje guide_content.json i zgłasza problemy jako uwagi.

Dlaczego istnieje: pisarze pracują równolegle i niezależnie, więc dopiero po nich da się sprawdzić całość. Sekcje
ze źródłem scanner i code nie mają bloków w treści - renderer wypełnia je z mapy projektu (guide_facts). Braki nie
przerywają przebiegu: guide_content.json jest zapisany zawsze, a lista problemów trafia na ekran i do recenzenta
(kroki 58-59). Zapisana treść pozwala powtórzyć renderowanie bez modelu.

Rola: moduł rdzenia towaru (faza F); węzeł assemble po pisarzach, przed renderem (krok 57).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.assemble
        na prawdziwym szablonie i zakładkach zbudowanych ręcznie: kolejność zakładek jak w szablonie, pusta zakładka
        dla diagramu i dla zakładki bez pisarza, zakładka spoza szablonu odrzucona, problemy (brak zakładki, brak
        wymaganej sekcji, odwołanie do nieistniejącego klocka, diagram z problemem), brak problemów dla kompletu,
        węzeł (guide_content.json, linie postępu); na końcu "zgodne z oczekiwaniem: True"
"""

from langgraph.runtime import Runtime

import dev_agents.agents.writer as _writer
import dev_agents.config as _config
import dev_agents.context as _context
import dev_agents.flow as _flow
import dev_agents.guide_content as _content
import dev_agents.guide_template as _template
import dev_agents.progress as _progress
import dev_agents.schemas as _schemas
import dev_agents.state as _state

_NODE_NAME = "assemble"


def build_content(
    project_map: _schemas.ProjectMap,
    flow: _content.FlowGraph,
    tabs: list[_content.GuideTab],
    template: _template.GuideTemplate,
) -> _content.GuideContent:
    """Składa GuideContent: zakładki w kolejności szablonu technologii projektu, z diagramem; brakująca zakładka jest pusta, obca odrzucona.

    Po co: renderer dostaje jeden obiekt z kompletem zakładek niezależnie od kolejności, w jakiej pisarze skończyli.
    Przy powtórzonym id zakładki wygrywa ostatnia.
    """
    szablon_technologii = _template.sections_for_technology(template, project_map.technology)
    wedlug_id = {}
    for zakladka in tabs:
        wedlug_id[zakladka.tab_id] = zakladka
    uporzadkowane = []
    for zakladka_szablonu in szablon_technologii.tabs:
        if zakladka_szablonu.id in wedlug_id:
            uporzadkowane.append(wedlug_id[zakladka_szablonu.id])
        else:
            uporzadkowane.append(_content.GuideTab(tab_id=zakladka_szablonu.id, blocks=[]))
    tresc = _content.GuideContent(project_name=project_map.project_name, flow=flow, tabs=uporzadkowane)
    return tresc


def check_content(
    content: _content.GuideContent,
    template: _template.GuideTemplate,
    technology: str,
    flow_config: _config.FlowConfig,
) -> list[str]:
    """Zwraca problemy całości: diagram (flow.validate_flow), brak zakładki pisarza i problemy zakładek (writer.check_tab) z id zakładki.

    Po co: jedno miejsce kontroli kompletności po pisarzach; pusta lista znaczy, że żadnego braku kod nie widzi.
    Ostrzeżenia diagramu o rozmiarze nie są problemami (zgłasza je autor diagramu).
    """
    problemy = []
    problemy_diagramu, _ = _flow.validate_flow(content.flow, flow_config)
    for problem in problemy_diagramu:
        problemy.append(f"diagram: {problem}")
    wedlug_id = {}
    for zakladka in content.tabs:
        wedlug_id[zakladka.tab_id] = zakladka
    szablon_technologii = _template.sections_for_technology(template, technology)
    for zakladka_szablonu in szablon_technologii.tabs:
        sekcje = _writer.writer_sections(zakladka_szablonu)
        if not sekcje:
            continue
        zakladka = wedlug_id.get(zakladka_szablonu.id)
        if zakladka is None or not zakladka.blocks:
            problemy.append(f"zakładka '{zakladka_szablonu.id}': brak treści od pisarza")
            continue
        for problem in _writer.check_tab(zakladka, sekcje, content.flow):
            problemy.append(f"zakładka '{zakladka_szablonu.id}': {problem}")
    return problemy


def assemble_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Węzeł assemble: składa treść ze stanu (diagram, zakładki), zapisuje guide_content.json i zwraca zmienione pole stanu: content.

    Po co: etap po pisarzach - cała treść przewodnika w jednym obiekcie. Praca jest owinięta w Stage: start, problemy
    jako uwagi, koniec z czasem, liczbą zakładek i problemów. Braki nie przerywają przebiegu (treść zapisana zawsze).
    """
    kontekst = runtime.context
    with _progress.Stage(kontekst.report, _NODE_NAME) as etap:
        tresc = build_content(state["project_map"], state["flow"], state.get("tabs", []), kontekst.template)
        problemy = check_content(tresc, kontekst.template, state["project_map"].technology, kontekst.config.flow)
        for problem in problemy:
            etap.note(f"problem: {problem}")
        zapisany_plik = kontekst.store.save_json("guide_content.json", tresc)
        etap.set_result(f"zakładek: {len(tresc.tabs)}, problemów: {len(problemy)}, zapisano {zapisany_plik}")
    zmiana_stanu = {"content": tresc}
    return zmiana_stanu


# --- Test ręczny ---

if __name__ == "__main__":
    import os
    import shutil
    import tempfile
    import types

    import dev_agents.output as _output

    def _flow_graph(
        starts: int,
    ) -> _content.FlowGraph:
        """Zwraca diagram: podana liczba startów, jeden krok n0 i koniec k; poprawny przy jednym starcie, z problemem przy dwóch.

        Po co: kontrolowany diagram do sprawdzenia problemów całości.
        """
        klocki = []
        strzalki = []
        for numer in range(starts):
            klocki.append(_content.FlowNode(id=f"s{numer}", kind="start", label="Start"))
            strzalki.append(_content.FlowEdge(source=f"s{numer}", target="n0"))
        klocki.append(_content.FlowNode(id="n0", kind="step", label="Krok", module="main.py", functions=["run:5"]))
        klocki.append(_content.FlowNode(id="k", kind="end", label="Koniec"))
        strzalki.append(_content.FlowEdge(source="n0", target="k"))
        diagram = _content.FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    def _tab(
        template: _template.GuideTemplate,
        tab_id: str,
        node_id: str,
    ) -> _content.GuideTab:
        """Zwraca kompletną zakładkę dla pisarza: pusty blok każdej wymaganej sekcji pisarza; w sekcji ścieżek jedna ścieżka główna z krokiem odwołującym się do node_id.

        Po co: komplet bez problemów albo (przy node_id spoza diagramu) z jednym problemem.
        """
        wynik = None
        for zakladka_szablonu in template.tabs:
            if zakladka_szablonu.id == tab_id:
                bloki = []
                for sekcja in _writer.writer_sections(zakladka_szablonu):
                    blok = _content.GuideBlock(section_id=sekcja.id)
                    if sekcja.type == "paths":
                        sciezka = _content.ProcessPath(name="Główna", kind="main", steps=[_content.PathStep(text="Krok.", node_id=node_id)])
                        blok = _content.GuideBlock(section_id=sekcja.id, paths=[sciezka])
                    bloki.append(blok)
                wynik = _content.GuideTab(tab_id=tab_id, blocks=bloki)
        return wynik

    def _map() -> _schemas.ProjectMap:
        """Zwraca minimalną mapę projektu w Pythonie.

        Po co: assemble czyta z niej nazwę projektu i technologię.
        """
        mapa = _schemas.ProjectMap(project_name="robot_testowy", root="x", technology="python", entrypoints=["main.py"], files=[], code_units=[])
        return mapa

    def _checks(
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza składanie i kontrolę kompletności na prawdziwym szablonie; zwraca (opis, zgodne).

        Po co: kolejność, puste zakładki, problemy i węzeł bez modelu i sieci.
        """
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _map()
        pelne = []
        for zakladka_szablonu in szablon.tabs:
            if _writer.writer_sections(zakladka_szablonu):
                pelne.append(_tab(szablon, zakladka_szablonu.id, "n0"))
        wyniki = []

        odwrocone = list(reversed(pelne))
        tresc = build_content(mapa, _flow_graph(1), odwrocone, szablon)
        identyfikatory = []
        for zakladka in tresc.tabs:
            identyfikatory.append(zakladka.tab_id)
        oczekiwane = []
        for zakladka_szablonu in szablon.tabs:
            oczekiwane.append(zakladka_szablonu.id)
        wyniki.append((f"kolejność zakładek jak w szablonie: {identyfikatory}", identyfikatory == oczekiwane))
        przeplyw = tresc.tabs[1]
        wyniki.append(("zakładka diagramu bez pisarza: pusta, diagram w treści", przeplyw.tab_id == "przeplyw" and przeplyw.blocks == [] and tresc.flow == _flow_graph(1)))
        obca = _content.GuideTab(tab_id="obca", blocks=[])
        tresc_z_obca = build_content(mapa, _flow_graph(1), pelne + [obca], szablon)
        wyniki.append(("zakładka spoza szablonu odrzucona", len(tresc_z_obca.tabs) == len(szablon.tabs)))

        problemy = check_content(tresc, szablon, "python", app_config.flow)
        wyniki.append(("komplet i poprawny diagram: bez problemów", problemy == []))

        bez_sciezek = build_content(mapa, _flow_graph(1), pelne[:1], szablon)
        problemy = check_content(bez_sciezek, szablon, "python", app_config.flow)
        wyniki.append(("brak zakładek pisarzy: problem dla każdej (bez diagramu)", len(problemy) == len(pelne) - 1 + 0 and "brak treści od pisarza" in problemy[0]))

        zle_sciezki = _tab(szablon, "sciezki", "n99")
        inne = []
        for zakladka in pelne:
            if zakladka.tab_id != "sciezki":
                inne.append(zakladka)
        problemy = check_content(build_content(mapa, _flow_graph(1), inne + [zle_sciezki], szablon), szablon, "python", app_config.flow)
        wyniki.append(("odwołanie do nieistniejącego klocka: problem z id zakładki", len(problemy) == 1 and problemy[0].startswith("zakładka 'sciezki': ") and "n99" in problemy[0]))

        pusta_przeglad = _content.GuideTab(tab_id="przeglad", blocks=[_content.GuideBlock(section_id="opis_robota")])
        inne = []
        for zakladka in pelne:
            if zakladka.tab_id != "przeglad":
                inne.append(zakladka)
        problemy = check_content(build_content(mapa, _flow_graph(1), inne + [pusta_przeglad], szablon), szablon, "python", app_config.flow)
        wyniki.append(("brak wymaganej sekcji: problem z id zakładki", len(problemy) >= 1 and "zakładka 'przeglad': brak bloku wymaganej sekcji" in problemy[0]))

        problemy = check_content(build_content(mapa, _flow_graph(2), pelne, szablon), szablon, "python", app_config.flow)
        wyniki.append(("diagram z dwoma startami: problem diagramu", len(problemy) == 1 and problemy[0].startswith("diagram: ")))

        linie = []
        magazyn = _output.RunStore(os.path.join(temp_dir, "wyniki"))
        kontekst = types.SimpleNamespace(config=app_config, template=szablon, report=linie.append, store=magazyn)
        stan = {"project_map": mapa, "flow": _flow_graph(1), "tabs": pelne}
        zmiana = assemble_node(stan, types.SimpleNamespace(context=kontekst))
        zapisana = magazyn.load_json("guide_content.json", _content.GuideContent)
        wyniki.append(("węzeł: zwraca content i zapisuje guide_content.json", list(zmiana) == ["content"] and zapisana == zmiana["content"]))
        wyniki.append((f"węzeł: linie postępu start i koniec", len(linie) == 2 and linie[0].endswith("] assemble: start") and "zakładek: 7, problemów: 0" in linie[1]))

        linie = []
        kontekst = types.SimpleNamespace(config=app_config, template=szablon, report=linie.append, store=magazyn)
        assemble_node({"project_map": mapa, "flow": _flow_graph(1), "tabs": []}, types.SimpleNamespace(context=kontekst))
        wyniki.append(("węzeł bez zakładek: problemy jako uwagi, treść zapisana", len(linie) >= 3 and "] assemble: problem: zakładka 'przeglad'" in linie[1]))
        return wyniki

    def manual_test():
        """Uruchamia sprawdzenia składania treści i wypisuje werdykt.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że składanie i kontrola kompletności działają bez modelu.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        temp_dir = tempfile.mkdtemp()
        try:
            wszystkie_zgodne = True
            for opis, zgodne in _checks(app_config, temp_dir):
                print(f"  {opis}: {zgodne}")
                if not zgodne:
                    wszystkie_zgodne = False
            print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
