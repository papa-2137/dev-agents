"""Renderer przewodnika: treść (GuideContent) + szablon (guide_template.yaml) + mapa projektu → samowystarczalny HTML.

Co robi: render_guide() układa zakładki i sekcje w kolejności z szablonu (tylko sekcje dla technologii projektu),
dla każdej sekcji wybiera stan - treść, „nie wynika z kodu” (sekcja wymagana bez treści) albo pominięcie (sekcja
opcjonalna bez treści) - i wypełnia szablon Jinja2 guide.html.j2. CSS i JS z katalogu szablonów są wstawiane do
środka pliku, więc przewodnik otwiera się bez internetu. Escapowanie jest zawsze włączone: tekst od agentów
(np. "<script>") wyświetla się jako tekst.

Typy bloków w tym kroku: text, list, io, cards (karty „jak czytać” z kart zakładek w szablonie). Pozostałe typy
dochodzą w krokach 34-38 - do tego czasu sekcja pokazuje widoczny znacznik „dochodzi w kolejnym kroku planu”.

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

_READY_TYPES = ["text", "list", "io", "cards"]
_CONTENT_FIELDS = {"text": "paragraphs", "list": "items"}


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
    """Zwraca True, gdy blok ma treść dla typu sekcji (text - akapity, list - punkty, io - wejścia albo wyjścia).

    Po co: sekcja wymagana bez treści pokazuje „nie wynika z kodu”, opcjonalna znika.
    """
    if section.type == "io":
        czy_tresc = bool(block.inputs) or bool(block.outputs)
        return czy_tresc
    czy_tresc = bool(getattr(block, _CONTENT_FIELDS[section.type]))
    return czy_tresc


def _section_view(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
) -> dict | None:
    """Zwraca dane sekcji dla szablonu HTML (id, tytuł, typ, stan, blok) albo None, gdy sekcję pominąć.

    Po co: jedno miejsce decyzji „treść / nie wynika z kodu / dochodzi w kolejnym kroku / pomiń”.
    """
    widok = {"id": section.id, "title": section.title, "type": section.type, "block": block, "state": "content"}
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
        css=css,
        js=js,
    )
    return html


# --- Test ręczny ---

if __name__ == "__main__":
    import re

    import dev_agents.config as _config
    import dev_agents.scanner as _scanner

    def _example_content() -> _content.GuideContent:
        """Składa przykładową treść robota 02: opis, wejście i wyjście, listy oraz tekst z <script> (test escapowania).

        Po co: podgląd szkieletu przewodnika bez modelu; pozostałe sekcje celowo puste („nie wynika z kodu”).
        """
        przeglad = _content.GuideTab(
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
                    section_id="jak_sprawdzic",
                    items=[
                        "W dane/wyjscie pojawia się plik wyniki_RRRRMMDD.json z bieżącą datą.",
                        "Katalog dane/wejscie jest pusty, a przetworzone pliki leżą w dane/archiwum.",
                    ],
                ),
            ],
        )
        deweloper = _content.GuideTab(
            tab_id="deweloper",
            blocks=[
                _content.GuideBlock(section_id="konwencje", items=["Stałe na górze pliku przetwarzanie.py - wszystkie ustawienia w kodzie.", "Test escapowania: <script>alert('x')</script> ma być widoczne jako tekst."]),
            ],
        )
        tresc = _content.GuideContent(
            project_name="02_robot_bez_frameworku",
            flow=_content.FlowGraph(nodes=[], edges=[]),
            tabs=[przeglad, deweloper],
        )
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
    ) -> tuple[int, int, int, bool]:
        """Zwraca (liczba zakładek, liczba sekcji h2, odwołania do zasobów z internetu, czy <script> z treści jest escapowany).

        Po co: szybkie sprawdzenie pliku bez otwierania przeglądarki.
        """
        zakladki = len(re.findall(r'<section class="tab"', html))
        sekcje = len(re.findall(r"<h2 ", html))
        zewnetrzne = len(re.findall(r'<(?:link|script|img)[^>]+(?:href|src)="https?:', html))
        escapowany = "&lt;script&gt;alert(" in html and "<script>alert(" not in html
        wynik = (zakladki, sekcje, zewnetrzne, escapowany)
        return wynik

    def manual_test():
        """Renderuje przykładową treść robota 02 do guide_test.html w katalogu głównym repo i wypisuje ścieżkę oraz podsumowanie.

        Po co: pierwszy widoczny przewodnik - do obejrzenia w przeglądarce.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _example_project_map(repo_dir, app_config)
        html = render_guide(_example_content(), szablon, mapa, os.path.dirname(app_config.paths.guide_template), "2026-11-26 18:30 (test)")
        sciezka = os.path.join(repo_dir, "guide_test.html")
        with open(sciezka, "w", encoding="utf-8") as plik:
            plik.write(html)
        zakladki, sekcje, zewnetrzne, escapowany = _summary(html)
        print(f"Zapisano: {sciezka}")
        print(f"  zakładek: {zakladki}, sekcji (h2): {sekcje}, rozmiar: {len(html)} znaków")
        print(f"  odwołania do zasobów z internetu: {zewnetrzne}")
        print(f"  <script> z treści escapowany: {escapowany}")
        print("Otwórz plik w przeglądarce i sprawdź zakładki, karty „jak czytać” i polskie znaki.")

    manual_test()
