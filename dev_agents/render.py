"""Renderer przewodnika: treść (GuideContent) + szablon (guide_template.yaml) + mapa projektu → samowystarczalny HTML.

Co robi: render_guide() układa zakładki i sekcje w kolejności z szablonu (tylko sekcje dla technologii projektu),
dla każdej sekcji wybiera stan - treść, „nie wynika z kodu” (sekcja wymagana bez treści) albo pominięcie (sekcja
opcjonalna bez treści) - i wypełnia szablon Jinja2 guide.html.j2. CSS i JS z katalogu szablonów są wstawiane do
środka pliku, więc przewodnik otwiera się bez internetu. Escapowanie jest zawsze włączone: tekst od agentów
(np. "<script>") wyświetla się jako tekst.

Typy bloków: text, list, io, cards (karty „jak czytać” z kart zakładek w szablonie), steps (kroki z kodem do
skopiowania), code, table (kolumny z szablonu), glossary, paths (numery klocków diagramu jak w kolejności
flow.nodes, odnośnik do zakładki Przepływ), recipes. Pozostałe typy (config, flow, tree, dependency_graph)
dochodzą w krokach 35-38 - do tego czasu sekcja pokazuje widoczny znacznik „dochodzi w kolejnym kroku planu”.
Komórka tabeli zakończona znacznikiem „[wywnioskowane]” wyświetla się bez znacznika, z oznaczeniem
„wywnioskowane” (informacja z analizy kodu, niezapisana w nim wprost).

Uwaga: zakładka bez stałego lead, której pierwsza sekcja ma typ text (opis robota), dostaje nagłówek
„nazwa projektu: pierwszy akapit”, a pozostałe akapity jako lead - jak w makiecie; ta sekcja nie jest osobnym h2.

Dlaczego istnieje: model zwraca treść, nie HTML - wygląd pochodzi z zaakceptowanej makiety (dev_log/guide_mockup.html),
więc wszystkie przewodniki wyglądają tak samo, a zmiana wyglądu to zmiana plików w knowledge_base/templates/.

Rola: moduł rdzenia towaru, wołany na końcu przebiegu (zapis guide.html w dev_agents_doc/).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.render
        zapisuje przewodnik z przykładową treścią robota 02 do guide_test.html w katalogu głównym repo (stała nazwa,
        nadpisywany przy każdym uruchomieniu, w .gitignore - otwórz plik w przeglądarce), wypisuje ścieżkę, liczbę
        zakładek i sekcji oraz liczbę odwołań do zasobów z internetu
"""

import os

import jinja2

import dev_agents.guide_content as _content
import dev_agents.guide_template as _template
import dev_agents.schemas as _schemas

_READY_TYPES = ["text", "list", "io", "cards", "steps", "code", "table", "glossary", "paths", "recipes"]
_CONTENT_FIELDS = {
    "text": "paragraphs",
    "list": "items",
    "steps": "steps",
    "code": "code",
    "table": "rows",
    "glossary": "terms",
    "paths": "paths",
    "recipes": "recipes",
}
_UNCERTAIN_MARK = "[wywnioskowane]"
_PATH_KIND_LABELS = {"main": "sukces", "alternative": "alternatywna", "error": "awaryjna"}


# --- Przygotowanie danych ---


def _blocks_by_section(
    content: _content.GuideContent,
) -> dict[str, _content.GuideBlock]:
    """Zwraca {id sekcji: blok treści} ze wszystkich zakładek treści.

    Po co: szablon wyznacza kolejność sekcji, a treść znajdujemy po id sekcji - bez względu na to, w której
    zakładce treści pisarz ją zwrócił.
    """
    bloki = {}
    for zakladka in content.tabs:
        for blok in zakladka.blocks:
            bloki[blok.section_id] = blok
    return bloki


def _has_content(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
) -> bool:
    """Zwraca True, gdy blok ma treść dla typu sekcji (pole z _CONTENT_FIELDS; io - wejścia albo wyjścia).

    Po co: sekcja wymagana bez treści pokazuje „nie wynika z kodu”, opcjonalna znika.
    """
    if section.type == "io":
        czy_tresc = bool(block.inputs) or bool(block.outputs)
        return czy_tresc
    czy_tresc = bool(getattr(block, _CONTENT_FIELDS[section.type]))
    return czy_tresc


def _cell_view(
    text: str,
    label: str,
) -> dict:
    """Zwraca dane komórki tabeli: tekst bez znacznika „[wywnioskowane]”, etykietę kolumny i flagę uncertain.

    Po co: pisarz oznacza wywnioskowaną komórkę znacznikiem na końcu tekstu (komórka to zwykły napis), a przewodnik
    pokazuje zamiast niego oznaczenie „wywnioskowane” jak w makiecie.
    """
    widok = {"text": text, "label": label, "uncertain": False}
    bez_spacji = text.rstrip()
    if bez_spacji.endswith(_UNCERTAIN_MARK):
        widok["text"] = bez_spacji[: -len(_UNCERTAIN_MARK)].rstrip()
        widok["uncertain"] = True
    return widok


def _table_rows(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
) -> list[list[dict]]:
    """Zwraca wiersze tabeli jako listy komórek z etykietą kolumny z szablonu (pusta dla nadmiarowej komórki).

    Po co: etykieta kolumny w każdej komórce (atrybut data-l) układa tabelę w karty na telefonie, jak w makiecie.
    """
    wiersze = []
    for wiersz in block.rows:
        komorki = []
        for numer, tekst in enumerate(wiersz):
            etykieta = ""
            if numer < len(section.columns):
                etykieta = section.columns[numer]
            komorki.append(_cell_view(tekst, etykieta))
        wiersze.append(komorki)
    return wiersze


def _node_numbers(
    flow: _content.FlowGraph,
) -> dict[str, int]:
    """Zwraca {id klocka: numer na diagramie} - numer to pozycja klocka w flow.nodes, licząc od 1.

    Po co: kroki ścieżek procesu odsyłają do klocków diagramu tym samym numerem, który widać na diagramie.
    """
    numery = {}
    for numer, klocek in enumerate(flow.nodes, start=1):
        numery[klocek.id] = numer
    return numery


def _section_view(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
) -> dict | None:
    """Zwraca dane sekcji dla szablonu HTML (id, tytuł, typ, stan, blok) albo None, gdy sekcję pominąć.

    Po co: jedno miejsce decyzji „treść / nie wynika z kodu / dochodzi w kolejnym kroku / pomiń”.
    """
    widok = {
        "id": section.id,
        "title": section.title,
        "type": section.type,
        "block": block,
        "state": "content",
        "columns": section.columns,
        "rows": _table_rows(section, block),
    }
    if section.type not in _READY_TYPES:
        widok["state"] = "pending"
    elif section.type != "cards" and not _has_content(section, block):
        if not section.required:
            return None
        widok["state"] = "missing"
    return widok


def _tab_view(
    tab: _template.TemplateTab,
    blocks: dict[str, _content.GuideBlock],
    project_name: str,
) -> dict:
    """Zwraca dane zakładki dla szablonu HTML: id, nagłówek, akapity lead i widoki sekcji.

    Po co: nagłówek opisu robota („nazwa: jedno zdanie”) i lead liczone w Pythonie, szablon tylko wyświetla.
    """
    naglowek = tab.title
    lead = []
    if tab.lead:
        lead.append(tab.lead)
    sekcje = tab.sections
    if not tab.lead and sekcje and sekcje[0].type == "text":
        akapity = blocks.get(sekcje[0].id, _content.GuideBlock(section_id=sekcje[0].id)).paragraphs
        naglowek = project_name
        if akapity:
            naglowek = f"{project_name}: {akapity[0]}"
            lead = akapity[1:]
        sekcje = sekcje[1:]
    widoki = []
    for sekcja in sekcje:
        widok = _section_view(sekcja, blocks.get(sekcja.id, _content.GuideBlock(section_id=sekcja.id)))
        if widok is not None:
            widoki.append(widok)
    widok_zakladki = {"id": tab.id, "heading": naglowek, "lead": lead, "sections": widoki}
    return widok_zakladki


def _technology_line(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca opis technologii do środka bloku io, np. "python · roboforge".

    Po co: środkowe pole schematu „wejście - robot - wyjście” z faktów skanera, bez modelu.
    """
    czesci = [project_map.technology]
    for framework in project_map.frameworks:
        czesci.append(framework)
    opis = " · ".join(czesci)
    return opis


# --- Renderowanie ---


def render_guide(
    content: _content.GuideContent,
    template: _template.GuideTemplate,
    project_map: _schemas.ProjectMap,
    templates_dir: str,
    generated_at: str,
) -> str:
    """Zwraca kompletny HTML przewodnika z CSS i JS wstawionymi do środka pliku.

    Po co: jedna funkcja zamienia treść na plik guide.html - wołający tylko zapisuje wynik.
    """
    szablon = _template.sections_for_technology(template, project_map.technology)
    bloki = _blocks_by_section(content)
    zakladki = []
    menu = []
    karty = []
    for zakladka in szablon.tabs:
        zakladki.append(_tab_view(zakladka, bloki, content.project_name))
        menu.append({"id": zakladka.id, "title": zakladka.title})
        karty.append({"id": zakladka.id, "label": zakladka.card_label, "title": zakladka.title, "text": zakladka.card_text})
    with open(os.path.join(templates_dir, "guide.css"), encoding="utf-8") as plik:
        css = plik.read()
    with open(os.path.join(templates_dir, "guide.js"), encoding="utf-8") as plik:
        js = plik.read()
    srodowisko = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir), autoescape=True)
    html = srodowisko.get_template("guide.html.j2").render(
        project_name=content.project_name,
        project_root=project_map.root,
        generated_at=generated_at,
        technology_line=_technology_line(project_map),
        nav=menu,
        tabs=zakladki,
        cards=karty,
        node_numbers=_node_numbers(content.flow),
        path_kind_labels=_PATH_KIND_LABELS,
        css=css,
        js=js,
    )
    return html


# --- Test ręczny ---

if __name__ == "__main__":
    import re

    import dev_agents.config as _config
    import dev_agents.scanner as _scanner

    def _example_flow() -> _content.FlowGraph:
        """Składa mały diagram robota 02 - tylko po to, by ścieżki procesu miały numery klocków (rysowanie w kroku 36).

        Po co: odnośniki ścieżek do klocków liczone z prawdziwego obiektu FlowGraph.
        """
        diagram = _content.FlowGraph(
            nodes=[
                _content.FlowNode(id="start", kind="start", label="Start run.bat"),
                _content.FlowNode(id="pliki", kind="step", label="Lista plików CSV", module="przetwarzanie.py"),
                _content.FlowNode(id="naglowek", kind="decision", label="Nagłówek poprawny?"),
                _content.FlowNode(id="wiersze", kind="step", label="Sprawdzenie wierszy i rabaty", module="przetwarzanie.py"),
                _content.FlowNode(id="odrzut", kind="step", label="Plik do dane/odrzucone", module="przetwarzanie.py"),
                _content.FlowNode(id="wyniki", kind="step", label="Zapis wyników JSON i CSV", module="przetwarzanie.py"),
                _content.FlowNode(id="koniec", kind="end", label="Koniec"),
            ],
            edges=[
                _content.FlowEdge(source="start", target="pliki"),
                _content.FlowEdge(source="pliki", target="naglowek"),
                _content.FlowEdge(source="naglowek", target="wiersze", label="tak", kind="branch"),
                _content.FlowEdge(source="naglowek", target="odrzut", label="nie", kind="branch"),
                _content.FlowEdge(source="wiersze", target="wyniki"),
                _content.FlowEdge(source="odrzut", target="koniec"),
                _content.FlowEdge(source="wyniki", target="koniec"),
            ],
        )
        return diagram

    def _example_overview() -> _content.GuideTab:
        """Składa przykładową zakładkę Przegląd robota 02: opis, wejście i wyjście, wymagania, zależności, instalacja, pojęcia.

        Po co: każdy typ bloku tej zakładki z treścią; metryczka celowo pusta (blok config w kroku 35).
        """
        zakladka = _content.GuideTab(
            tab_id="przeglad",
            blocks=[
                _content.GuideBlock(
                    section_id="opis_robota",
                    paragraphs=[
                        "przetwarza pliki zamówień CSV i tworzy raport Excel",
                        "Robot czyta pliki zamówień z katalogu dane/wejscie, sprawdza wiersze, nalicza rabaty i odrzuca błędne pliki. Wyniki zapisuje jako JSON i CSV, a na końcu tworzy raport Excel dla działu sprzedaży.",
                    ],
                ),
                _content.GuideBlock(
                    section_id="wejscie_wyjscie",
                    inputs=[_content.IoItem(name="dane/wejscie/*.csv", location="przetwarzanie.py:52", description="pliki zamówień, jeden plik na dzień")],
                    outputs=[
                        _content.IoItem(name="dane/wyjscie/wyniki_*.json", location="przetwarzanie.py:380", description="zamówienia po przeliczeniu"),
                        _content.IoItem(name="raport_*.xlsx", location="raport.py:60", description="raport z 4 arkuszami"),
                    ],
                ),
                _content.GuideBlock(
                    section_id="wymagania",
                    rows=[
                        ["Python", "3.12 albo nowszy", "run.bat woła python bez ścieżki - domyślny Python z PATH [wywnioskowane]"],
                        ["Pliki i katalogi", "dane/wejscie/*.csv", "pliki zamówień w UTF-8, nagłówek w pierwszym wierszu"],
                        ["Konta i hasła", "zmienna środowiskowa ROBOT02_PASS", "przetwarzanie.py:22; potrzebna tylko przy WYSYLKA_DO_API = True"],
                    ],
                ),
                _content.GuideBlock(section_id="zaleznosci", code="openpyxl\nrequests"),
                _content.GuideBlock(
                    section_id="instalacja",
                    steps=[
                        _content.Step(title="Środowisko Python", text="Paczki instalowane w domyślnym Pythonie z PATH.", code="python -m pip install -r requirements.txt"),
                        _content.Step(title="Dane testowe", text="Kopiuje przykłady z dane\\przyklady do dane\\wejscie.", code="przygotuj_dane.bat"),
                        _content.Step(title="Konfiguracja", text="Ustawienia są stałymi na górze przetwarzanie.py - bez pliku konfiguracyjnego."),
                        _content.Step(title="Uruchomienie", text="run.bat przechodzi do katalogu robota, uruchamia przetwarzanie.py, a po sukcesie raport.py.", code="run.bat"),
                    ],
                ),
                _content.GuideBlock(
                    section_id="jak_sprawdzic",
                    items=[
                        "W dane/wyjscie pojawia się plik wyniki_RRRRMMDD.json z bieżącą datą.",
                        "Katalog dane/wejscie jest pusty, a przetworzone pliki leżą w dane/archiwum.",
                    ],
                ),
                _content.GuideBlock(
                    section_id="pojecia",
                    terms=[
                        _content.GlossaryTerm(term="Plik odrzucony", definition="Plik zamówień ze złym nagłówkiem albo rozszerzeniem, przeniesiony do dane/odrzucone bez przetwarzania."),
                        _content.GlossaryTerm(term="VIP", definition="Klient z dodatkowym rabatem 10%, łącznie z PROMO nie więcej niż 12%."),
                    ],
                ),
            ],
        )
        return zakladka

    def _example_other_tabs() -> list[_content.GuideTab]:
        """Składa przykładowe zakładki Ścieżki, Zmiany, Błędy i Dla dewelopera robota 02, z tekstem <script> w treści.

        Po co: bloki paths, table, recipes i list z treścią oraz test escapowania w komórce, w kodzie i na liście.
        """
        sciezki = _content.GuideTab(
            tab_id="sciezki",
            blocks=[
                _content.GuideBlock(
                    section_id="sciezki",
                    paths=[
                        _content.ProcessPath(
                            name="Poprawny plik zamówień",
                            kind="main",
                            steps=[
                                _content.PathStep(text="Lista plików CSV w dane/wejscie.", node_id="pliki"),
                                _content.PathStep(text="Nagłówek zgodny z oczekiwanym.", node_id="naglowek"),
                                _content.PathStep(text="Sprawdzenie wierszy, rabaty, duplikaty.", node_id="wiersze"),
                                _content.PathStep(text="Zapis wyników i przeniesienie pliku do archiwum.", node_id="wyniki"),
                            ],
                        ),
                        _content.ProcessPath(
                            name="Zły nagłówek",
                            kind="alternative",
                            steps=[
                                _content.PathStep(text="Nagłówek inny niż oczekiwany.", node_id="naglowek"),
                                _content.PathStep(text="Plik przeniesiony do dane/odrzucone.", node_id="odrzut"),
                            ],
                        ),
                        _content.ProcessPath(
                            name="Błąd wysyłki do API",
                            kind="error",
                            steps=[
                                _content.PathStep(text="Tylko przy WYSYLKA_DO_API = True: trzy próby, potem wpis w logu."),
                            ],
                        ),
                    ],
                ),
            ],
        )
        zmiany = _content.GuideTab(
            tab_id="zmiany",
            blocks=[
                _content.GuideBlock(
                    section_id="gdzie_zmienic",
                    rows=[
                        ["Adres API", "przetwarzanie.py:14, stała URL", "zmiana w kodzie - brak pliku konfiguracyjnego"],
                        ["Próg rabatu VIP", "przetwarzanie.py:18, stała RABAT_VIP", "limit łączny 12% liczony w run() [wywnioskowane]"],
                    ],
                ),
                _content.GuideBlock(
                    section_id="przepisy",
                    recipes=[
                        _content.Recipe(
                            title="Nowa kolumna w pliku zamówień",
                            when="dział sprzedaży dodaje kolumnę do pliku CSV",
                            files=[
                                _content.RecipeFile(path="przetwarzanie.py", change="oczekiwany nagłówek i odczyt kolumny"),
                                _content.RecipeFile(path="dane/przyklady/zamowienia_nowe.csv", change="przykład z nową kolumną", is_new=True),
                            ],
                            steps=[
                                "Dopisz kolumnę do stałej z oczekiwanym nagłówkiem.",
                                "Odczytaj wartość w pętli po wierszach w run().",
                                "Sprawdzenie: przygotuj_dane.bat, potem run.bat - plik nie trafia do odrzuconych.",
                            ],
                        ),
                    ],
                ),
            ],
        )
        bledy = _content.GuideTab(
            tab_id="bledy",
            blocks=[
                _content.GuideBlock(
                    section_id="awarie",
                    rows=[
                        ["Wszystkie pliki w dane/odrzucone", "zmieniony nagłówek w plikach od działu sprzedaży", "log, przetwarzanie.py: run", "porównaj nagłówek z oczekiwanym"],
                        ["Komunikat „przekracza limit” dla VIP z PROMO", "0.10 + 0.02 daje 0.12000000000000001", "przetwarzanie.py: run", "wynik poprawny, komunikat mylący [wywnioskowane]"],
                        ["Test escapowania <script>alert('x')</script>", "tekst od agenta", "komórka tabeli", "ma być widoczny jako tekst"],
                    ],
                ),
                _content.GuideBlock(
                    section_id="ryzykowne_miejsca",
                    rows=[
                        ["run", "przetwarzanie.py:41-411", "długa jednostka (371 linii)", "cały proces w jednej funkcji - dane przykładowe, w kroku 35 z mapy projektu"],
                    ],
                ),
            ],
        )
        deweloper = _content.GuideTab(
            tab_id="deweloper",
            blocks=[
                _content.GuideBlock(section_id="warstwy", rows=[["przetwarzanie.py", "cały proces: odczyt, sprawdzenie, rabaty, zapis"], ["raport.py", "raport Excel z wyników"]]),
                _content.GuideBlock(section_id="konwencje", items=["Stałe na górze pliku przetwarzanie.py - wszystkie ustawienia w kodzie.", "Test escapowania: <script>alert('x')</script> ma być widoczne jako tekst."]),
            ],
        )
        zakladki = [sciezki, zmiany, bledy, deweloper]
        return zakladki

    def _example_content() -> _content.GuideContent:
        """Składa przykładową treść robota 02 z każdym gotowym typem bloku.

        Po co: podgląd przewodnika bez modelu; sekcje bez treści pokazują „nie wynika z kodu” albo znikają.
        """
        zakladki = [_example_overview()]
        for zakladka in _example_other_tabs():
            zakladki.append(zakladka)
        tresc = _content.GuideContent(project_name="02_robot_bez_frameworku", flow=_example_flow(), tabs=zakladki)
        return tresc

    def _example_project_map(
        repo_dir: str,
        app_config: _config.AppConfig,
    ) -> _schemas.ProjectMap:
        """Zwraca mapę robota 02 ze skanera albo minimalną mapę, gdy robota testowego nie ma.

        Po co: renderer potrzebuje technologii, frameworków i ścieżki projektu.
        """
        robot_02 = os.path.normpath(os.path.join(repo_dir, "..", "..", "tests", "02_robot_bez_frameworku"))
        if os.path.isdir(robot_02):
            mapa = _scanner.build_project_map(robot_02, app_config.scan)
            return mapa
        mapa = _schemas.ProjectMap(project_name="02_robot_bez_frameworku", root=robot_02, technology="python", entrypoints=[], files=[], code_units=[])
        return mapa

    def _summary(
        html: str,
    ) -> dict:
        """Zwraca liczby do szybkiego sprawdzenia pliku: zakładki, sekcje h2, odwołania do internetu, bloki kodu,
        oznaczenia „wywnioskowane” w tabelach, odnośniki do klocków, znaczniki kolejnych kroków i escapowanie <script>.

        Po co: szybkie sprawdzenie pliku bez otwierania przeglądarki.
        """
        wynik = {
            "zakładek": len(re.findall(r'<section class="tab"', html)),
            "sekcji (h2)": len(re.findall(r"<h2 ", html)),
            "odwołań do zasobów z internetu": len(re.findall(r'<(?:link|script|img)[^>]+(?:href|src)="https?:', html)),
            "bloków kodu (Kopiuj)": html.count('<div class="cb">'),
            "„wywnioskowane” w tabelach": html.count('<span class="unc">wywnioskowane</span></td>'),
            "odnośników do klocków": html.count('<a class="ref"'),
            "sekcji czekających na kolejny krok": html.count("dochodzi w kolejnym kroku planu"),
            "<script> z treści escapowany": "&lt;script&gt;alert(" in html and "<script>alert(" not in html,
        }
        return wynik

    def manual_test():
        """Renderuje przykładową treść robota 02 do guide_test.html w katalogu głównym repo i wypisuje ścieżkę oraz podsumowanie.

        Po co: pierwszy widoczny przewodnik - do obejrzenia w przeglądarce.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _example_project_map(repo_dir, app_config)
        html = render_guide(_example_content(), szablon, mapa, os.path.dirname(app_config.paths.guide_template), "2026-11-26 20:00 (test)")
        sciezka = os.path.join(repo_dir, "guide_test.html")
        with open(sciezka, "w", encoding="utf-8") as plik:
            plik.write(html)
        print(f"Zapisano: {sciezka} ({len(html)} znaków)")
        for nazwa, wartosc in _summary(html).items():
            print(f"  {nazwa}: {wartosc}")
        print("Otwórz plik w przeglądarce: tabele, kroki z przyciskiem Kopiuj, pojęcia, ścieżki z numerami klocków, przepisy.")

    manual_test()
