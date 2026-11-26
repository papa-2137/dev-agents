"""Treść przewodnika bez modelu: zaślepki w sekcjach agentów i przykładowy diagram.

Co robi: build_placeholder_content() składa GuideContent dla projektu z samych zaślepek - każda sekcja, którą
w gotowym przewodniku wypełni agent (źródło llm), dostaje blok z tekstami w nawiasach kwadratowych w kształcie
zgodnym z typem sekcji (akapity, punkty, kroki, wiersz tabeli z tyloma komórkami, ile ma kolumn, wejście i wyjście,
ścieżki trzech rodzajów, przepis z plikiem nowym i istniejącym, wpisy metryczki dla każdego rodzaju kafelka);
kolejność czytania dostaje zdania „plik: [dlaczego czytać ten plik w tym miejscu]” dla pierwszych plików z mapy.
placeholder_flow() zwraca ogólny diagram przykładowy: każdy napis zaczyna się od „[przykład]”, a moduły, pliki i
zmienne są zaślepkami w nawiasach, więc nic w nim nie udaje faktu o prawdziwym robocie.

Dlaczego istnieje: krok 39 (main.py --render-only) pokazuje przewodnik z prawdziwego robota przed pierwszym
wywołaniem modelu - sekcje z kodu (drzewo, zależności, graf, ryzykowne miejsca, kolejność czytania) są prawdziwe,
a sekcje agentów mają zaślepki, więc widać układ i ilość miejsca, a wygląd można poprawić, zanim wydamy tokeny.
Zaślepka nie jest „Nie wynika z kodu.” - to zdanie znaczyłoby, że kod niczego nie zawiera, a tu po prostu jeszcze
nie pracował agent.

Czego NIE robi: nie wywołuje modelu, nie czyta plików projektu (korzysta tylko z mapy projektu) i nie wymyśla
wartości konfiguracji ani haseł - wpisy metryczki mają wartość „[wartość]”, więc nie trafiają do „Ryzykownych miejsc”.

Rola: moduł rdzenia towaru, wołany przez main.py (--render-only); w fazie F zaślepki zastąpi treść od agentów.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.guide_placeholders
        dla robotów testowych 02 i 01 (tylko odczyt; brak robota - przypadek pomijany): liczba bloków, sekcje agentów
        bez zaślepki (oczekiwane 0), wynik sprawdzenia diagramu przykładowego (oczekiwane: bez problemów) i liczby
        z przewodnika renderowanego w pamięci; bez zapisu plików
    python -m dev_agents.guide_placeholders robot01
    python -m dev_agents.guide_placeholders robot02
        to samo, a dodatkowo zapisuje przewodnik wskazanego robota do guide_test.html w katalogu głównym repo (stała
        nazwa, w .gitignore; w robocie nic nie jest zapisywane)
"""

import dev_agents.guide_content as _content
import dev_agents.guide_template as _template
import dev_agents.schemas as _schemas

_PLACEHOLDER_TEXT = "tu będzie tekst agenta"
_READING_PLACEHOLDER_FILES = 3
_FLOW_NODE_IDS = {"start": "start", "step": "krok", "system": "system", "decision": "warunek", "yes": "tak", "end": "koniec"}
_CONFIG_PLACEHOLDER_KINDS = ["system", "account", "env_var", "input_file", "output_file", "log", "switch"]


# --- Diagram przykładowy ---


def placeholder_flow() -> _content.FlowGraph:
    """Zwraca ogólny diagram przykładowy: start, czynność, kontakt z systemem, decyzja (gałąź „tak” z pętlą, „nie” do końca), koniec.

    Po co: zakładka Przepływ pokazuje wygląd diagramu i wierszy „Krok po kroku” (wszystkie rodzaje klocków, cztery
    rodzaje kafelków danych, jedno obejście i strzałka pętli); napisy są zaślepkami, a diagram przechodzi validate_flow.
    """
    id_ = _FLOW_NODE_IDS
    diagram = _content.FlowGraph(
        nodes=[
            _content.FlowNode(id=id_["start"], kind="start", label="[przykład] Start"),
            _content.FlowNode(
                id=id_["step"],
                kind="step",
                label="[przykład] Czynność robota",
                description="[przykład: tu będzie opis kroku od agenta]",
                module="[moduł]",
                functions=["[funkcja]:1"],
                reads=[_content.DataRef(name="[plik wejściowy]", kind="file"), _content.DataRef(name="[ZMIENNA_ŚRODOWISKOWA]", kind="env")],
                writes=[_content.DataRef(name="[dane w pamięci]", kind="memory")],
            ),
            _content.FlowNode(
                id=id_["system"],
                kind="system",
                label="[przykład] Kontakt z systemem",
                description="[przykład: tu będzie opis kontaktu z systemem zewnętrznym]",
                module="[moduł]",
                reads=[_content.DataRef(name="[system zewnętrzny]", kind="system")],
                writes=[_content.DataRef(name="[plik wynikowy]", kind="file")],
            ),
            _content.FlowNode(id=id_["decision"], kind="decision", label="[przykład] Warunek spełniony?", description="[przykład: tu będzie opis decyzji]"),
            _content.FlowNode(id=id_["yes"], kind="step", label="[przykład] Gałąź tak", module="[moduł]"),
            _content.FlowNode(id=id_["end"], kind="end", label="[przykład] Koniec"),
        ],
        edges=[
            _content.FlowEdge(source=id_["start"], target=id_["step"]),
            _content.FlowEdge(source=id_["step"], target=id_["system"]),
            _content.FlowEdge(source=id_["system"], target=id_["decision"]),
            _content.FlowEdge(source=id_["decision"], target=id_["yes"], label="tak", kind="branch"),
            _content.FlowEdge(source=id_["decision"], target=id_["end"], label="nie", kind="branch"),
            _content.FlowEdge(source=id_["yes"], target=id_["step"], label="powtórz", kind="loop"),
        ],
    )
    return diagram


# --- Bloki zaślepek ---


def _label(
    section: _template.TemplateSection,
    text: str,
) -> str:
    """Zwraca zaślepkę w nawiasach kwadratowych z tytułem sekcji, np. "[Wymagania: tu będzie tekst agenta]".

    Po co: na stronie od razu widać, której sekcji agenta dotyczy zaślepka.
    """
    zaslepka = f"[{section.title}: {text}]"
    return zaslepka


def _text_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok text z dwoma akapitami zaślepek (pierwszy akapit opisu robota staje się nagłówkiem zakładki).

    Po co: pokazuje nagłówek „nazwa: zdanie” i akapit lead w pierwszej zakładce.
    """
    blok = _content.GuideBlock(section_id=section.id, paragraphs=[_label(section, _PLACEHOLDER_TEXT), _label(section, "drugi akapit")])
    return blok


def _list_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok list: dwa punkty zaślepek, a dla listy ze źródłem scanner (kolejność czytania) zdania „plik: [dlaczego]”.

    Po co: kolejność czytania ma pliki z kodu - pisarz dopisuje tylko zdanie, więc zaślepka ma format „plik: zdanie”.
    """
    punkty = [_label(section, "punkt 1"), _label(section, "punkt 2")]
    if section.source == "scanner":
        punkty = []
        for sciezka in project_map.reading_order[:_READING_PLACEHOLDER_FILES]:
            punkty.append(f"{sciezka}: [dlaczego czytać ten plik w tym miejscu]")
    blok = _content.GuideBlock(section_id=section.id, items=punkty)
    return blok


def _io_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok io z jednym wejściem i jednym wyjściem w zaślepkach.

    Po co: schemat „wejście - robot - wyjście” z zaślepkami zamiast pustych ramek.
    """
    blok = _content.GuideBlock(
        section_id=section.id,
        inputs=[_content.IoItem(name="[wejście]", location="[plik:linia]", description="[tu będzie opis wejścia]")],
        outputs=[_content.IoItem(name="[wyjście]", location="[plik:linia]", description="[tu będzie opis wyjścia]")],
    )
    return blok


def _steps_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok steps: dwa kroki, drugi z kodem do skopiowania.

    Po co: widać numerowaną listę i ramkę kodu z przyciskiem „Kopiuj”.
    """
    blok = _content.GuideBlock(
        section_id=section.id,
        steps=[
            _content.Step(title="[Krok 1]", text="[tu będzie opis kroku]"),
            _content.Step(title="[Krok 2]", text="[tu będzie opis kroku]", code="[polecenie do skopiowania]"),
        ],
    )
    return blok


def _table_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok table z jednym wierszem zaślepek: po jednej komórce na kolumnę z szablonu.

    Po co: tabela ma poprawną liczbę kolumn i etykiety kart na telefonie.
    """
    wiersz = []
    for kolumna in section.columns:
        wiersz.append(f"[{kolumna}]")
    blok = _content.GuideBlock(section_id=section.id, rows=[wiersz])
    return blok


def _glossary_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok glossary z jednym pojęciem zaślepki.

    Po co: widać układ słowniczka (sekcja opcjonalna znikłaby bez treści).
    """
    blok = _content.GuideBlock(section_id=section.id, terms=[_content.GlossaryTerm(term="[pojęcie]", definition="[tu będzie definicja]")])
    return blok


def _paths_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok paths z trzema ścieżkami (sukces, alternatywna, awaryjna), kroki odsyłają do klocków diagramu przykładowego.

    Po co: widać wszystkie trzy oznaczenia rodzaju ścieżki i numerowane odnośniki do klocków.
    """
    id_ = _FLOW_NODE_IDS
    sciezki = [
        _content.ProcessPath(
            name="[Ścieżka główna]",
            kind="main",
            steps=[
                _content.PathStep(text="[krok na ścieżce]", node_id=id_["start"]),
                _content.PathStep(text="[krok na ścieżce]", node_id=id_["step"]),
                _content.PathStep(text="[krok na ścieżce]", node_id=id_["end"]),
            ],
        ),
        _content.ProcessPath(name="[Ścieżka alternatywna]", kind="alternative", steps=[_content.PathStep(text="[krok na ścieżce]", node_id=id_["decision"])]),
        _content.ProcessPath(name="[Ścieżka awaryjna]", kind="error", steps=[_content.PathStep(text="[krok na ścieżce]")]),
    ]
    blok = _content.GuideBlock(section_id=section.id, paths=sciezki)
    return blok


def _recipes_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok recipes z jednym przepisem: plik istniejący i nowy (czerwona ramka) oraz kroki.

    Po co: widać układ przepisu i oba rodzaje znaczników plików.
    """
    przepis = _content.Recipe(
        title="[Tytuł przepisu]",
        when="[kiedy użyć przepisu]",
        files=[
            _content.RecipeFile(path="[plik do zmiany]", change="[co zmienić]"),
            _content.RecipeFile(path="[nowy plik]", change="[co dodać]", is_new=True),
        ],
        steps=["[krok 1]", "[krok 2]"],
    )
    blok = _content.GuideBlock(section_id=section.id, recipes=[przepis])
    return blok


def _config_block(
    section: _template.TemplateSection,
    project_map: _schemas.ProjectMap,
) -> _content.GuideBlock:
    """Zwraca blok config: po jednym wpisie zaślepki dla każdego rodzaju kafelka, z wartością „[wartość]” (bez haseł).

    Po co: widać wszystkie kafelki metryczki i tabelę „Pełna konfiguracja”; wartości prawdziwego pliku konfiguracyjnego
    przepisze agent, a zaślepka nie może udawać hasła wpisanego wprost ani trafić do „Ryzykownych miejsc”.
    """
    plik = ""
    for wpis in project_map.files:
        if wpis.role == "config" and not plik:
            plik = wpis.path
    wpisy = []
    for rodzaj in _CONFIG_PLACEHOLDER_KINDS:
        wpisy.append(
            _content.ConfigItem(
                file=plik,
                location="[plik:linia]",
                key=f"[klucz: {rodzaj}]",
                value="[wartość]",
                kind=rodzaj,
                meaning="[tu będzie znaczenie od agenta]",
            )
        )
    blok = _content.GuideBlock(section_id=section.id, paragraphs=["[zdanie o wczytywaniu konfiguracji: tu będzie tekst agenta]"], config_items=wpisy)
    return blok


_BUILDERS = {
    "text": _text_block,
    "list": _list_block,
    "io": _io_block,
    "steps": _steps_block,
    "table": _table_block,
    "glossary": _glossary_block,
    "paths": _paths_block,
    "recipes": _recipes_block,
    "config": _config_block,
}


# --- Całość ---


def build_placeholder_content(
    template: _template.GuideTemplate,
    project_map: _schemas.ProjectMap,
) -> _content.GuideContent:
    """Zwraca treść przewodnika z zaślepkami w sekcjach agentów (dla technologii projektu) i diagramem przykładowym.

    Po co: przewodnik z prawdziwego robota bez modelu. Sekcje z faktami kodu (źródło code, drzewo, zależności, graf)
    zostają bez bloku - renderer wypełnia je z mapy projektu; kolejność czytania (lista ze źródłem scanner) dostaje
    zaślepki zdań pisarza.
    """
    szablon = _template.sections_for_technology(template, project_map.technology)
    zakladki = []
    for zakladka in szablon.tabs:
        bloki = []
        for sekcja in zakladka.sections:
            if sekcja.source != "code" and sekcja.type in _BUILDERS:
                bloki.append(_BUILDERS[sekcja.type](sekcja, project_map))
        zakladki.append(_content.GuideTab(tab_id=zakladka.id, blocks=bloki))
    tresc = _content.GuideContent(project_name=project_map.project_name, flow=placeholder_flow(), tabs=zakladki)
    return tresc


# --- Test ręczny ---

if __name__ == "__main__":
    import os
    import sys

    import dev_agents.config as _config
    import dev_agents.flow as _flow
    import dev_agents.render as _render
    import dev_agents.scanner as _scanner

    def _robot_html(
        repo_dir: str,
        app_config: _config.AppConfig,
        robot_name: str,
    ) -> str | None:
        """Renderuje w pamięci przewodnik z zaślepkami robota testowego i wypisuje liczby kontrolne; None, gdy robota nie ma.

        Po co: sprawdzenie na prawdziwych mapach (tylko odczyt, nic nie jest zapisywane w robocie).
        """
        katalog = os.path.normpath(os.path.join(repo_dir, "..", "..", "tests", robot_name))
        if not os.path.isdir(katalog):
            print(f"\n=== {robot_name} === pominięto: brak robota testowego obok repo")
            return None
        mapa = _scanner.build_project_map(katalog, app_config.scan)
        szablon = _template.load_template(app_config.paths.guide_template)
        tresc = build_placeholder_content(szablon, mapa)
        sekcje_agentow = []
        for zakladka in _template.sections_for_technology(szablon, mapa.technology).tabs:
            for sekcja in zakladka.sections:
                if sekcja.source == "llm" and sekcja.type in _BUILDERS:
                    sekcje_agentow.append(sekcja.id)
        zablokowane = set()
        for zakladka in tresc.tabs:
            for blok in zakladka.blocks:
                zablokowane.add(blok.section_id)
        brakujace = []
        for identyfikator in sekcje_agentow:
            if identyfikator not in zablokowane:
                brakujace.append(identyfikator)
        problemy, ostrzezenia = _flow.validate_flow(tresc.flow, app_config.flow)
        html = _render.render_guide(
            tresc,
            szablon,
            mapa,
            os.path.dirname(app_config.paths.guide_template),
            "2026-11-26 20:00 (test)",
            app_config.analysis.long_unit_lines,
            app_config.flow,
        )
        print(f"\n=== {robot_name} ===")
        print(f"  bloków zaślepek: {len(zablokowane)}, sekcji agentów: {len(sekcje_agentow)}, sekcje agentów bez zaślepki: {brakujace}")
        print(f"  diagram przykładowy: klocków {len(tresc.flow.nodes)}, problemy: {problemy}, ostrzeżenia: {ostrzezenia}")
        print(f"  przewodnik: {len(html)} znaków, sekcji (h2): {html.count('<h2 ')}, sekcji czekających: {html.count('dochodzi w kolejnym kroku planu')}")
        print(f"  zaślepek „tu będzie” w tekście: {html.count('tu będzie')}, „Nie wynika z kodu.”: {html.count('Nie wynika z kodu.')}, rysunków (diagram, graf): {html.count('<svg id=')}")
        print(f"  bez haseł w ryzykownych miejscach: {html.count('hasło w pliku') == 0 and html.count('hasło w kodzie') == 0}")
        return html

    def manual_test():
        """Wypisuje liczby dla robotów 02 i 01; z argumentem robot01 albo robot02 zapisuje przewodnik do guide_test.html.

        Po co: sprawdzenie zaślepek i diagramu przykładowego na prawdziwych mapach bez zapisu czegokolwiek w robotach.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        wybrany = ""
        if len(sys.argv) > 1:
            wybrany = sys.argv[1]
        zapis = None
        for nazwa, skrot in [("02_robot_bez_frameworku", "robot02"), ("01_rpa_challange_roboforge", "robot01")]:
            html = _robot_html(repo_dir, app_config, nazwa)
            if html is not None and wybrany == skrot:
                zapis = html
        if zapis is not None:
            sciezka = os.path.join(repo_dir, "guide_test.html")
            with open(sciezka, "w", encoding="utf-8") as plik:
                plik.write(zapis)
            print(f"\nZapisano: {sciezka} - otwórz w przeglądarce")

    manual_test()
