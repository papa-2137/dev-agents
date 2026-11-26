"""Ostatni etap przebiegu: gotowa treść przewodnika (GuideContent) zamieniona na plik guide.html.

Co robi: finalize_node() bierze ze stanu treść złożoną przez assemble i mapę projektu, woła renderer (render.render_guide)
z szablonem, progami z configu i godziną generowania, zapisuje dev_agents_doc/guide.html i zwraca zmienione pole
stanu: guide_path (ścieżka pliku). Praca jest owinięta w Stage: start, koniec z czasem, liczbą zakładek i rozmiarem pliku.

Dlaczego istnieje: dopiero ten węzeł daje użytkownikowi to, po co uruchamia towar - przewodnik do otwarcia w przeglądarce.
Render nie woła modelu, więc ten sam plik da się odtworzyć z guide_content.json bez kosztu. Braki treści nie blokują
renderu: renderer pokazuje „nie wynika z kodu” albo listę problemów diagramu (uwagi o brakach zgłosił już assemble).

Rola: węzeł grafu (faza F), po assemble.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.finalize
        na prawdziwym szablonie i treści z pustymi blokami pisarzy: węzeł zwraca guide_path, plik guide.html powstaje
        w magazynie, zawiera nazwę projektu, wszystkie zakładki szablonu i diagram, linie postępu (start, koniec
        z liczbą zakładek); na końcu "zgodne z oczekiwaniem: True"
"""

import datetime
import os

from langgraph.runtime import Runtime

import dev_agents.context as _context
import dev_agents.progress as _progress
import dev_agents.render as _render
import dev_agents.state as _state

_NODE_NAME = "finalize"
_FILE_NAME = "guide.html"


def finalize_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Węzeł finalize: renderuje state["content"] do guide.html w magazynie wyników i zwraca zmienione pole stanu: guide_path.

    Po co: ostatni etap - przewodnik HTML z treści agentów. Znacznik czasu w stopce to godzina generowania.
    """
    kontekst = runtime.context
    with _progress.Stage(kontekst.report, _NODE_NAME) as etap:
        wygenerowano = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        html = _render.render_guide(
            state["content"],
            kontekst.template,
            state["project_map"],
            os.path.dirname(kontekst.config.paths.guide_template),
            wygenerowano,
            kontekst.config.analysis.long_unit_lines,
            kontekst.config.flow,
        )
        zapisany_plik = kontekst.store.save_text(_FILE_NAME, html)
        etap.set_result(f"zakładek: {len(state['content'].tabs)}, rozmiar: {len(html) // 1024} KB, zapisano {zapisany_plik}")
    zmiana_stanu = {"guide_path": zapisany_plik}
    return zmiana_stanu


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile
    import types

    import dev_agents.agents.writer as _writer
    import dev_agents.config as _config
    import dev_agents.guide_content as _content
    import dev_agents.guide_template as _template
    import dev_agents.output as _output
    import dev_agents.schemas as _schemas

    def _checks(
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza węzeł na prawdziwym szablonie i treści z pustymi blokami sekcji pisarzy; zwraca (opis, zgodne).

        Po co: render z treści agentów bez modelu i sieci.
        """
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _schemas.ProjectMap(project_name="robot_testowy", root="x", technology="python", entrypoints=["main.py"], files=[], code_units=[])
        diagram = _content.FlowGraph(
            nodes=[
                _content.FlowNode(id="s0", kind="start", label="Start TESTOWY"),
                _content.FlowNode(id="n0", kind="step", label="Krok", module="main.py", functions=["run:5"]),
                _content.FlowNode(id="k", kind="end", label="Koniec"),
            ],
            edges=[_content.FlowEdge(source="s0", target="n0"), _content.FlowEdge(source="n0", target="k")],
        )
        zakladki = []
        for zakladka in szablon.tabs:
            bloki = []
            for sekcja in _writer.writer_sections(zakladka):
                bloki.append(_content.GuideBlock(section_id=sekcja.id))
            zakladki.append(_content.GuideTab(tab_id=zakladka.id, blocks=bloki))
        tresc = _content.GuideContent(project_name="robot_testowy", flow=diagram, tabs=zakladki)
        linie = []
        magazyn = _output.RunStore(os.path.join(temp_dir, "wyniki"))
        kontekst = types.SimpleNamespace(config=app_config, template=szablon, report=linie.append, store=magazyn)
        zmiana = finalize_node({"content": tresc, "project_map": mapa}, types.SimpleNamespace(context=kontekst))
        wyniki = []
        wyniki.append(("węzeł zwraca tylko guide_path", list(zmiana) == ["guide_path"]))
        istnieje = os.path.isfile(zmiana["guide_path"])
        wyniki.append(("guide.html powstał w magazynie", istnieje and zmiana["guide_path"].endswith("guide.html")))
        with open(zmiana["guide_path"], encoding="utf-8") as plik:
            html = plik.read()
        wyniki.append(("guide.html: nazwa projektu i diagram", "robot_testowy" in html and "Start TESTOWY" in html))
        wszystkie = True
        for zakladka in szablon.tabs:
            if zakladka.title not in html:
                wszystkie = False
        wyniki.append(("guide.html: tytuły wszystkich zakładek szablonu", wszystkie))
        wyniki.append(("linie postępu: start i koniec z liczbą zakładek", len(linie) == 2 and linie[0].endswith("] finalize: start") and "zakładek: 7" in linie[1]))
        return wyniki

    def manual_test():
        """Uruchamia sprawdzenia węzła finalize i wypisuje werdykt.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że render treści do pliku działa bez modelu.
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
