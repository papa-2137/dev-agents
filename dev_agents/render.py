"""Renderer przewodnika: treść (GuideContent) + szablon (guide_template.yaml) + mapa projektu → samowystarczalny HTML.

Co robi: render_guide() układa zakładki i sekcje w kolejności z szablonu (tylko sekcje dla technologii projektu),
dla każdej sekcji wybiera stan - treść, „nie wynika z kodu” (sekcja wymagana bez treści) albo pominięcie (sekcja
opcjonalna bez treści) - i wypełnia szablon Jinja2 guide.html.j2. CSS i JS z katalogu szablonów są wstawiane do
środka pliku, więc przewodnik otwiera się bez internetu. Escapowanie jest zawsze włączone: tekst od agentów
(np. "<script>") wyświetla się jako tekst.

Typy bloków: text, list, io, cards (karty „jak czytać” z kart zakładek w szablonie), steps (kroki z kodem do
skopiowania), code, table (kolumny z szablonu), glossary, paths (numery klocków diagramu jak w kolejności
flow.nodes, odnośnik do zakładki Przepływ), recipes, config (metryczka: kafelki po rodzaju wpisu i tabela
„Pełna konfiguracja”; hasło wpisane wprost z czerwonym znacznikiem), tree (drzewo plików z opisami po najechaniu).
Pozostałe typy (flow, dependency_graph) dochodzą w kolejnych krokach - do tego czasu sekcja pokazuje widoczny znacznik
„dochodzi w kolejnym kroku planu”.
Fakty z kodu zamiast odpowiedzi modelu (guide_facts.py): sekcja typu code ze źródłem scanner (zależności) to treść
plików zależności z mapy projektu; tabela ze źródłem code (ryzykowne miejsca) to długie jednostki i hasła wpisane
wprost, a wiersze pisarza dodają komentarz i inne miejsca; drzewo bierze fakty z mapy, opisy pisarza mają pierwszeństwo.
Komórka tabeli zakończona znacznikiem „[wywnioskowane]” wyświetla się bez znacznika, z oznaczeniem
„wywnioskowane” (informacja z analizy kodu, niezapisana w nim wprost).

Uwaga: zakładka bez stałego lead, której pierwsza sekcja ma typ text (opis robota), dostaje nagłówek
„nazwa projektu: pierwszy akapit”, a pozostałe akapity jako lead - jak w makiecie; ta sekcja nie jest osobnym h2.

Dlaczego istnieje: model zwraca treść, nie HTML - wygląd pochodzi z zaakceptowanej makiety (dev_log/guide_mockup.html),
więc wszystkie przewodniki wyglądają tak samo, a zmiana wyglądu to zmiana plików w knowledge_base/templates/.

Rola: moduł rdzenia towaru, wołany na końcu przebiegu (zapis guide.html w dev_agents_doc/).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.render
        zapisuje przewodnik z przykładową treścią robota 02 (metryczka ze stałych w kodzie, jak w robocie bez pliku
        konfiguracyjnego) do guide_test.html w katalogu głównym repo (stała nazwa, nadpisywany przy każdym uruchomieniu,
        w .gitignore - otwórz plik w przeglądarce), wypisuje ścieżkę i liczby kontrolne; dodatkowo sprawdza w pamięci
        metryczkę bez wpisów (zdanie o braku konfiguracji) oraz przewodniki robotów 01 i 02 bez zapisu plików
        (robot 01: tylko liczby; brak robota - przypadek pomijany)
    python -m dev_agents.render plik
        to samo, ale metryczka z przykładowego pliku config.yml jak w makiecie (sekcje, hasło wpisane wprost,
        zmienna środowiskowa, stała w kodzie)
"""

import os

import jinja2

import dev_agents.guide_content as _content
import dev_agents.guide_facts as _facts
import dev_agents.guide_template as _template
import dev_agents.schemas as _schemas

_READY_TYPES = ["text", "list", "io", "cards", "steps", "code", "table", "glossary", "paths", "recipes", "config", "tree"]
_CONTENT_FIELDS = {
    "text": "paragraphs",
    "list": "items",
    "steps": "steps",
    "code": "code",
    "table": "rows",
    "glossary": "terms",
    "paths": "paths",
    "recipes": "recipes",
    "config": "config_items",
    "tree": "rows",
}
_MISSING_TEXT = "Nie wynika z kodu."
_MISSING_TEXTS = {
    "config": "Robot nie ma konfiguracji - nie wynika z kodu.",
    "dependencies": "Robot nie ma pliku zależności (requirements.txt ani pyproject.toml).",
}
_RISKY_BADGE_COLORS = {"długa jednostka": "m", "hasło w pliku": "r", "hasło w kodzie": "r"}
_RISKY_CODE_COLUMN = 1
_RISKY_REASONS = {
    "długa jednostka": "Długa jednostka kodu: trudno ją przeczytać i zmienić bez pomyłki.",
    "hasło w pliku": "Hasło wpisane wprost w plik: trafia do repozytorium i kopii zapasowych.",
    "hasło w kodzie": "Hasło wpisane wprost w kod: trafia do repozytorium i kopii zapasowych.",
}
_UNCERTAIN_MARK = "[wywnioskowane]"
_PATH_KIND_LABELS = {"main": "sukces", "alternative": "alternatywna", "error": "awaryjna"}
_CONFIG_TILES = [
    ("SYSTEMY ZEWNĘTRZNE", ["system"]),
    ("KONTA I ZMIENNE ŚRODOWISKOWE", ["account", "env_var"]),
    ("PLIKI WEJŚCIOWE", ["input_file"]),
    ("PLIKI WYJŚCIOWE", ["output_file"]),
    ("LOGI", ["log"]),
    ("PRZEŁĄCZNIKI", ["switch"]),
]
_CONFIG_BADGES = {
    "system": ["sieć", "r"],
    "account": ["konto", "m"],
    "env_var": ["zmienna środowiskowa", "r"],
    "input_file": ["ścieżka", "m"],
    "output_file": ["ścieżka", "m"],
    "log": ["ścieżka", "m"],
    "switch": ["przełącznik", "m"],
    "other": ["", "m"],
}
_CODE_SECTION_LABEL = "w kodzie"


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
    """Zwraca dane komórki tabeli: tekst bez znacznika „[wywnioskowane]”, etykietę kolumny, flagę uncertain oraz
    pola code (tekst jako kod) i badge (znacznik przed tekstem) ustawiane przez wołającego.

    Po co: pisarz oznacza wywnioskowaną komórkę znacznikiem na końcu tekstu (komórka to zwykły napis), a przewodnik
    pokazuje zamiast niego oznaczenie „wywnioskowane” jak w makiecie.
    """
    widok = {"text": text, "label": label, "uncertain": False, "code": False, "badge": "", "badge_color": ""}
    bez_spacji = text.rstrip()
    if bez_spacji.endswith(_UNCERTAIN_MARK):
        widok["text"] = bez_spacji[: -len(_UNCERTAIN_MARK)].rstrip()
        widok["uncertain"] = True
    return widok


def _column_label(
    columns: list[str],
    number: int,
) -> str:
    """Zwraca etykietę kolumny o danym numerze albo "" (gdy szablon ma mniej kolumn niż komórek).

    Po co: nadmiarowa komórka wiersza nie przewraca renderera.
    """
    etykieta = ""
    if number < len(columns):
        etykieta = columns[number]
    return etykieta


def _table_rows(
    rows: list[list[str]],
    columns: list[str],
    code_column: int,
) -> list[list[dict]]:
    """Zwraca wiersze tabeli jako listy komórek z etykietą kolumny z szablonu; komórki kolumny code_column jako kod (-1 = brak).

    Po co: etykieta kolumny w każdej komórce (atrybut data-l) układa tabelę w karty na telefonie, jak w makiecie.
    """
    wiersze = []
    for wiersz in rows:
        komorki = []
        for numer, tekst in enumerate(wiersz):
            komorka = _cell_view(tekst, _column_label(columns, numer))
            komorka["code"] = numer == code_column
            komorki.append(komorka)
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


def _config_entry(
    item: _content.ConfigItem,
) -> dict:
    """Zwraca dane jednego wpisu metryczki dla szablonu: wartość, etykieta, znaczenie, znaczniki i miejsca użycia.

    Po co: kafelki i tabela pokazują ten sam wpis; kod przygotowuje napisy, szablon tylko je wyświetla.
    """
    etykieta = item.key
    if item.group:
        etykieta = f"{item.group}.{item.key}"
    odznaka = _CONFIG_BADGES[item.kind]
    miejsca = []
    if not item.file and item.location:
        miejsca.append({"text": item.location, "constant": True})
    for miejsce in item.used_in:
        miejsca.append({"text": miejsce, "constant": False})
    wpis = {
        "kind": item.kind,
        "key": item.key,
        "label": etykieta,
        "value": item.value,
        "meaning": item.meaning,
        "uncertain": not item.certain,
        "password": _facts.password_mark(item),
        "badge_text": odznaka[0],
        "badge_color": odznaka[1],
        "places": miejsca,
    }
    return wpis


def _config_section_label(
    item: _content.ConfigItem,
) -> str:
    """Zwraca nagłówek wiersza grupującego w tabeli: sekcja pliku, nazwa pliku albo „w kodzie” (stała w kodzie).

    Po co: tabela „Pełna konfiguracja” dzieli wpisy jak plik konfiguracyjny, a stałe z kodu zbiera osobno.
    """
    etykieta = item.file
    if item.group:
        etykieta = item.group
    if not item.file:
        etykieta = _CODE_SECTION_LABEL
    return etykieta


def _config_tiles(
    items: list[_content.ConfigItem],
) -> list[dict]:
    """Zwraca kafelki metryczki w stałej kolejności: tytuł i wpisy danego rodzaju (kafelek bez wpisów pomijany).

    Po co: szybki przegląd ustawień pogrupowanych po tym, czego dotyczą; rodzaj „inne” jest tylko w tabeli.
    """
    kafelki = []
    for tytul, rodzaje in _CONFIG_TILES:
        wpisy = []
        for wpis in items:
            if wpis.kind in rodzaje:
                wpisy.append(_config_entry(wpis))
        if wpisy:
            kafelki.append({"title": tytul, "entries": wpisy})
    return kafelki


def _config_groups(
    items: list[_content.ConfigItem],
) -> list[dict]:
    """Zwraca wpisy pogrupowane kolejno: {label, entries}; nowa grupa, gdy zmienia się nagłówek sekcji.

    Po co: tabela zachowuje kolejność wpisów od agenta (bez sortowania), a wiersze grupujące wstawia się przy zmianie sekcji.
    """
    grupy = []
    for wpis in items:
        etykieta = _config_section_label(wpis)
        if not grupy or grupy[-1]["label"] != etykieta:
            grupy.append({"label": etykieta, "entries": []})
        grupy[-1]["entries"].append(_config_entry(wpis))
    return grupy


def _config_view(
    block: _content.GuideBlock,
) -> dict:
    """Zwraca dane metryczki dla szablonu: nagłówek (pliki i zdanie od agenta), kafelki, grupy tabeli, liczbę wpisów.

    Po co: cały blok config w jednym słowniku; nagłówek pokazuje nazwy plików konfiguracyjnych albo „Ustawienia w kodzie”,
    a zdanie o sposobie wczytania pliku bierze z pierwszego akapitu bloku (jeśli agent je napisał).
    """
    pliki = []
    for wpis in block.config_items:
        if wpis.file and wpis.file not in pliki:
            pliki.append(wpis.file)
    naglowek = "Ustawienia w kodzie"
    if pliki:
        naglowek = ", ".join(pliki)
    zdanie = ""
    if block.paragraphs:
        zdanie = block.paragraphs[0]
    widok = {
        "header": naglowek,
        "sentence": zdanie,
        "tiles": _config_tiles(block.config_items),
        "groups": _config_groups(block.config_items),
        "count": len(block.config_items),
    }
    return widok


def _all_config_items(
    blocks: dict[str, _content.GuideBlock],
) -> list[_content.ConfigItem]:
    """Zwraca wszystkie wpisy metryczki ze wszystkich bloków treści.

    Po co: „Ryzykowne miejsca” biorą hasła wpisane wprost z metryczki, bez względu na zakładkę, w której ją opisano.
    """
    wpisy = []
    for blok in blocks.values():
        for wpis in blok.config_items:
            wpisy.append(wpis)
    return wpisy


def _risky_fact_cells(
    fact: dict,
    columns: list[str],
) -> list[dict]:
    """Zwraca komórki wiersza ryzykownego miejsca z faktów kodu: miejsce, plik i linie (kod), rodzaj ze znacznikiem, powód.

    Po co: powód to komentarz pisarza, a gdy go brak - zdanie domyślne dla rodzaju; fakty (linie, długość) zawsze z kodu.
    """
    powod = fact["comment"]
    if not powod:
        powod = _RISKY_REASONS[fact["badge"]]
    miejsce = _cell_view(fact["place"], _column_label(columns, 0))
    plik = _cell_view(fact["where"], _column_label(columns, 1))
    plik["code"] = True
    rodzaj = _cell_view(fact["detail"], _column_label(columns, 2))
    rodzaj["badge"] = fact["badge"]
    rodzaj["badge_color"] = _RISKY_BADGE_COLORS[fact["badge"]]
    uzasadnienie = _cell_view(powod, _column_label(columns, 3))
    komorki = [miejsce, plik, rodzaj, uzasadnienie]
    return komorki


def _risky_view(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
    project_map: _schemas.ProjectMap,
    config_items: list[_content.ConfigItem],
    long_unit_lines: int,
) -> list[list[dict]]:
    """Zwraca wiersze tabeli ryzykownych miejsc: z faktów kodu (hasła, długie jednostki), potem dodatkowe wiersze pisarza.

    Po co: kod wskazuje miejsca, pisarz dopisuje tylko komentarz i miejsca, których kod nie widzi.
    """
    fakty, dodatkowe = _facts.risky_rows(project_map, config_items, long_unit_lines, block.rows)
    wiersze = []
    for fakt in fakty:
        wiersze.append(_risky_fact_cells(fakt, section.columns))
    for wiersz in _table_rows(dodatkowe, section.columns, _RISKY_CODE_COLUMN):
        wiersze.append(wiersz)
    return wiersze


def _fact_view(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
    project_map: _schemas.ProjectMap,
    config_items: list[_content.ConfigItem],
    long_unit_lines: int,
) -> dict:
    """Zwraca dane sekcji liczone z faktów kodu (drzewo, zależności, ryzykowne miejsca) albo {} dla pozostałych sekcji.

    Po co: pewne fakty (pliki, treść pliku zależności, linie i długości funkcji, hasło wprost) pochodzą z kodu, nie z modelu;
    klucz has_content mówi, czy sekcja ma co pokazać, a missing_text - co napisać, gdy nie ma.
    """
    widok = {}
    if section.type == "tree":
        drzewo = _facts.build_tree(project_map, block.rows)
        widok = {"tree": drzewo, "has_content": drzewo["file_count"] > 0}
    if section.type == "code" and section.source == "scanner":
        tekst = _facts.dependency_text(project_map)
        widok = {"code_text": tekst, "has_content": bool(tekst), "missing_text": _MISSING_TEXTS["dependencies"]}
    if section.type == "table" and section.source == "code":
        wiersze = _risky_view(section, block, project_map, config_items, long_unit_lines)
        brak = (
            f"Nie znaleziono ryzykownych miejsc: żadna jednostka kodu nie przekracza {long_unit_lines} linii, "
            "a w metryczce nie ma haseł wpisanych wprost."
        )
        widok = {"rows": wiersze, "has_content": bool(wiersze), "missing_text": brak}
    return widok


def _section_view(
    section: _template.TemplateSection,
    block: _content.GuideBlock,
    project_map: _schemas.ProjectMap,
    config_items: list[_content.ConfigItem],
    long_unit_lines: int,
) -> dict | None:
    """Zwraca dane sekcji dla szablonu HTML (id, tytuł, typ, stan, blok i dane z faktów) albo None, gdy sekcję pominąć.

    Po co: jedno miejsce decyzji „treść / nie wynika z kodu / dochodzi w kolejnym kroku / pomiń”.
    """
    widok = {
        "id": section.id,
        "title": section.title,
        "type": section.type,
        "block": block,
        "state": "content",
        "columns": section.columns,
        "rows": _table_rows(block.rows, section.columns, -1),
        "config": None,
        "tree": None,
        "code_text": block.code,
        "missing_text": _MISSING_TEXTS.get(section.type, _MISSING_TEXT),
    }
    if section.type == "config":
        widok["config"] = _config_view(block)
    fakty = _fact_view(section, block, project_map, config_items, long_unit_lines)
    czy_tresc = True
    if fakty:
        czy_tresc = fakty.pop("has_content")
        widok.update(fakty)
    elif section.type in _READY_TYPES and section.type != "cards":
        czy_tresc = _has_content(section, block)
    if section.type not in _READY_TYPES:
        widok["state"] = "pending"
    elif not czy_tresc:
        if not section.required:
            return None
        widok["state"] = "missing"
    return widok


def _tab_view(
    tab: _template.TemplateTab,
    blocks: dict[str, _content.GuideBlock],
    project_name: str,
    project_map: _schemas.ProjectMap,
    long_unit_lines: int,
) -> dict:
    """Zwraca dane zakładki dla szablonu HTML: id, nagłówek, akapity lead i widoki sekcji.

    Po co: nagłówek opisu robota („nazwa: jedno zdanie”) i lead liczone w Pythonie, szablon tylko wyświetla.
    """
    wpisy_konfiguracji = _all_config_items(blocks)
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
        blok = blocks.get(sekcja.id, _content.GuideBlock(section_id=sekcja.id))
        widok = _section_view(sekcja, blok, project_map, wpisy_konfiguracji, long_unit_lines)
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
    long_unit_lines: int,
) -> str:
    """Zwraca kompletny HTML przewodnika z CSS i JS wstawionymi do środka pliku.

    Po co: jedna funkcja zamienia treść na plik guide.html - wołający tylko zapisuje wynik. long_unit_lines to próg
    z config.yaml (analysis.long_unit_lines) dla tabeli „Ryzykowne miejsca”.
    """
    szablon = _template.sections_for_technology(template, project_map.technology)
    bloki = _blocks_by_section(content)
    zakladki = []
    menu = []
    karty = []
    for zakladka in szablon.tabs:
        zakladki.append(_tab_view(zakladka, bloki, content.project_name, project_map, long_unit_lines))
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
    import sys

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

    def _example_config_code() -> list[_content.ConfigItem]:
        """Składa przykładową metryczkę robota 02: same stałe w kodzie (robot nie ma pliku konfiguracyjnego).

        Po co: przypadek „konfiguracja tylko w kodzie” - nagłówek „Ustawienia w kodzie”, jedna grupa „w kodzie” w tabeli.
        """
        wpisy = [
            _content.ConfigItem(location="przetwarzanie.py:14", key="URL", value="https://api.example.test/zamowienia", kind="system", meaning="adres API, do którego robot wysyła zamówienia", used_in=["przetwarzanie.py:301"]),
            _content.ConfigItem(location="przetwarzanie.py:9", key="INPUT_DIR", value="dane/wejscie", kind="input_file", meaning="katalog z plikami zamówień CSV", used_in=["przetwarzanie.py:52"]),
            _content.ConfigItem(location="przetwarzanie.py:10", key="OUTPUT_DIR", value="dane/wyjscie", kind="output_file", meaning="wyniki JSON i CSV oraz raport Excel", used_in=["przetwarzanie.py:380"]),
            _content.ConfigItem(location="przetwarzanie.py:22", key="ENV_PASSWORD", value="ROBOT02_PASS", kind="env_var", meaning="nazwa zmiennej z hasłem do API; potrzebna przy WYSYLKA_DO_API = True", used_in=["przetwarzanie.py:298"]),
            _content.ConfigItem(location="przetwarzanie.py:24", key="WYSYLKA_DO_API", value="False", kind="switch", meaning="True = wysyłka zamówień do API z ponawianiem", used_in=["przetwarzanie.py:296"]),
            _content.ConfigItem(location="przetwarzanie.py:26", key="LIMIT_RABATU", value="0.12", kind="other", meaning="łączny limit rabatu VIP i PROMO", used_in=["przetwarzanie.py:210"], certain=False),
        ]
        return wpisy

    def _example_config_file() -> list[_content.ConfigItem]:
        """Składa przykładową metryczkę z pliku config.yml jak w makiecie: sekcje, konto, zmienna, hasło wprost, stała w kodzie.

        Po co: przypadek „plik konfiguracyjny” - czerwony znacznik „hasło w pliku”, wiersze grupujące, wpis wywnioskowany.
        """
        wpisy = [
            _content.ConfigItem(file="config.yml", group="input", key="excel_path", value="resources/in/challenge.xlsx", kind="input_file", meaning="plik Excel z danymi do wpisania w formularz", used_in=["main.py:57"]),
            _content.ConfigItem(file="config.yml", group="output", key="report_db", value="resources/report.db", kind="output_file", meaning="baza raportowa, wiersz po każdym rekordzie", used_in=["main.py:58"]),
            _content.ConfigItem(file="config.yml", group="output", key="account_states", value="resources/acc_states.txt", kind="output_file", meaning="stany kont odczytane z ParaBank", used_in=["main.py:59"], certain=False),
            _content.ConfigItem(file="config.yml", group="parabank", key="url", value="https://parabank.parasoft.com/parabank/", kind="system", meaning="adres aplikacji bankowej", used_in=["main.py:139"]),
            _content.ConfigItem(file="config.yml", group="parabank", key="username", value="robot", kind="account", meaning="login robota w ParaBank", used_in=["main.py:142"]),
            _content.ConfigItem(file="config.yml", group="parabank", key="password_env", value="FAKE_PASSWD", kind="env_var", meaning="nazwa zmiennej z hasłem do ParaBank; brak zmiennej zatrzymuje robota", used_in=["main.py:135", "main.py:137"]),
            _content.ConfigItem(file="config.yml", location="config.yml:12", group="parabank", key="password", value="Haslo123!", kind="account", plain_password=True, meaning="przykład: hasło wpisane wprost w plik", used_in=["main.py:140"]),
            _content.ConfigItem(location="przetwarzanie.py:14", key="URL", value="https://api.example.test/zamowienia", kind="system", meaning="adres API; stała w kodzie, nie w pliku konfiguracyjnym"),
            _content.ConfigItem(file="config.yml", group="logger", key="logs_dir", value="logs", kind="log", meaning="katalog dziennych logów CSV", used_in=["main.py:54"]),
            _content.ConfigItem(file="config.yml", group="logger", key="debug", value="false", kind="switch", meaning="true = także komunikaty DEBUG frameworku", used_in=["main.py:54"]),
        ]
        return wpisy

    def _example_overview(
        config_items: list[_content.ConfigItem],
        config_sentence: str,
    ) -> _content.GuideTab:
        """Składa przykładową zakładkę Przegląd robota 02: opis, metryczka, wejście i wyjście, wymagania, zależności, instalacja, pojęcia.

        Po co: każdy typ bloku tej zakładki z treścią; metryczka z podanych wpisów (zdanie do nagłówka może być puste).
        """
        akapity = []
        if config_sentence:
            akapity.append(config_sentence)
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
                _content.GuideBlock(section_id="metryczka", paragraphs=akapity, config_items=config_items),
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
                        ["run", "przetwarzanie.py:41-411", "długa jednostka", "cały proces w jednej funkcji: odczyt, sprawdzenie, rabaty i zapis [wywnioskowane]"],
                        ["URL", "przetwarzanie.py:14", "adres w kodzie", "adres API wpisany w kod - zmiana wymaga edycji pliku i ponownego uruchomienia"],
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
        struktura = _content.GuideTab(
            tab_id="struktura",
            blocks=[
                _content.GuideBlock(
                    section_id="drzewo",
                    rows=[
                        ["przetwarzanie.py", "Główny skrypt robota", "Cały proces: odczyt plików CSV, sprawdzenie, rabaty, zapis wyników"],
                        ["run.bat", "Plik uruchamiający", "Uruchamia przetwarzanie.py, a po sukcesie raport.py"],
                    ],
                ),
            ],
        )
        zakladki = [sciezki, struktura, zmiany, bledy, deweloper]
        return zakladki

    def _example_content(
        config_items: list[_content.ConfigItem],
        config_sentence: str,
    ) -> _content.GuideContent:
        """Składa przykładową treść robota 02 z każdym gotowym typem bloku i podaną metryczką.

        Po co: podgląd przewodnika bez modelu; sekcje bez treści pokazują „nie wynika z kodu” albo znikają.
        """
        zakladki = [_example_overview(config_items, config_sentence)]
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

    def _section_html(
        html: str,
        section_id: str,
    ) -> str:
        """Zwraca fragment HTML od nagłówka sekcji o podanym id do następnego nagłówka h2 (albo do końca zakładki).

        Po co: liczniki tabel i drzewa liczone tylko w jednej sekcji.
        """
        poczatek = html.find(f'<h2 id="s-{section_id}">')
        fragment = ""
        if poczatek >= 0:
            koniec = html.find("<h2 ", poczatek + 1)
            if koniec < 0:
                koniec = html.find("</section>", poczatek)
            fragment = html[poczatek:koniec]
        return fragment

    def _summary(
        html: str,
    ) -> dict:
        """Zwraca liczby do szybkiego sprawdzenia pliku: zakładki, sekcje h2, odwołania do internetu, bloki kodu,
        oznaczenia „wywnioskowane” w tabelach, odnośniki do klocków, znaczniki kolejnych kroków, escapowanie <script>,
        liczby z metryczki (kafelki, grupy i wiersze tabeli, hasła wprost, zdanie o braku konfiguracji) oraz
        liczby z drzewa, zależności i ryzykownych miejsc (wiersze, znaczniki, zdania o braku).

        Po co: szybkie sprawdzenie pliku bez otwierania przeglądarki.
        """
        ryzykowne = _section_html(html, "ryzykowne_miejsca")
        hasla_ryzykowne = len(re.findall(r'<td data-l="Rodzaj"><span class="kv r">hasło w (?:pliku|kodzie)</span>', ryzykowne))
        hasla_razem = len(re.findall(r'<span class="kv r">hasło w (?:pliku|kodzie)</span>', html))
        drzewo = _section_html(html, "drzewo")
        wynik = {
            "zakładek": len(re.findall(r'<section class="tab"', html)),
            "sekcji (h2)": len(re.findall(r"<h2 ", html)),
            "odwołań do zasobów z internetu": len(re.findall(r'<(?:link|script|img)[^>]+(?:href|src)="https?:', html)),
            "bloków kodu (Kopiuj)": html.count('<div class="cb">'),
            "„wywnioskowane” w tabelach": html.count('<span class="unc">wywnioskowane</span></td>'),
            "odnośników do klocków": html.count('<a class="ref"'),
            "sekcji czekających na kolejny krok": html.count("dochodzi w kolejnym kroku planu"),
            "<script> z treści escapowany": "&lt;script&gt;alert(" in html and "<script>alert(" not in html,
            "metryczka: kafelków": html.count("<div><h3>"),
            "metryczka: grup w tabeli": html.count('<tr class="csec">'),
            "metryczka: wierszy w tabeli": html.count('<td class="val"'),
            "metryczka: znaczników hasła wprost": hasla_razem - hasla_ryzykowne,
            "metryczka: zdanie o braku konfiguracji": "Robot nie ma konfiguracji - nie wynika z kodu." in html,
            "drzewo: przycisków z opisem (z korzeniem)": drzewo.count('<button class="it'),
            "drzewo: opisów pisarza": drzewo.count('data-w="Główny skrypt robota"') + drzewo.count('data-w="Plik uruchamiający"'),
            "zależności: zdanie o braku pliku": "Robot nie ma pliku zależności" in html,
            "ryzykowne: wierszy": ryzykowne.count('<td data-l="Miejsce">'),
            "ryzykowne: długich jednostek": ryzykowne.count('<span class="kv m">długa jednostka</span>'),
            "ryzykowne: haseł wprost": hasla_ryzykowne,
            "ryzykowne: komentarzy pisarza": ryzykowne.count("cały proces w jednej funkcji") + ryzykowne.count("wpisany w kod - zmiana"),
        }
        return wynik

    def _render_example(
        repo_dir: str,
        app_config: _config.AppConfig,
        config_items: list[_content.ConfigItem],
        config_sentence: str,
    ) -> str:
        """Renderuje przykładowy przewodnik robota 02 z podaną metryczką i zwraca HTML.

        Po co: ten sam szablon, mapa i treść dla wszystkich wariantów metryczki w teście.
        """
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _example_project_map(repo_dir, app_config)
        tresc = _example_content(config_items, config_sentence)
        html = render_guide(tresc, szablon, mapa, os.path.dirname(app_config.paths.guide_template), "2026-11-26 20:00 (test)", app_config.analysis.long_unit_lines)
        return html

    def _render_robot_in_memory(
        repo_dir: str,
        app_config: _config.AppConfig,
        robot_name: str,
        long_unit_lines: int,
    ) -> str | None:
        """Renderuje w pamięci przewodnik robota testowego bez treści od pisarza i zwraca HTML (None, gdy robota nie ma).

        Po co: drzewo, zależności i ryzykowne miejsca z prawdziwych robotów (też robota 01, tylko do odczytu); nic nie jest
        zapisywane na dysk.
        """
        katalog = os.path.normpath(os.path.join(repo_dir, "..", "..", "tests", robot_name))
        html = None
        if os.path.isdir(katalog):
            mapa = _scanner.build_project_map(katalog, app_config.scan)
            szablon = _template.load_template(app_config.paths.guide_template)
            tresc = _content.GuideContent(project_name=robot_name, flow=_content.FlowGraph(nodes=[], edges=[]), tabs=[])
            html = render_guide(tresc, szablon, mapa, os.path.dirname(app_config.paths.guide_template), "test", long_unit_lines)
        return html

    def _print_robot_counts(
        repo_dir: str,
        app_config: _config.AppConfig,
        robot_name: str,
        long_unit_lines: int,
    ) -> None:
        """Wypisuje liczby z przewodnika robota (bez treści od pisarza): przyciski drzewa, zależności i ryzykowne miejsca.

        Po co: sprawdzenie sekcji z faktów kodu na prawdziwych robotach, bez zapisu plików.
        """
        html = _render_robot_in_memory(repo_dir, app_config, robot_name, long_unit_lines)
        if html is None:
            print(f"{robot_name}: pominięto (brak robota testowego obok repo)")
            return
        wynik = _summary(html)
        print(
            f"{robot_name} (próg {long_unit_lines} linii): drzewo - przycisków {wynik['drzewo: przycisków z opisem (z korzeniem)']}, "
            f"zdanie o braku pliku zależności: {wynik['zależności: zdanie o braku pliku']}, "
            f"ryzykowne - wierszy {wynik['ryzykowne: wierszy']}, długich jednostek {wynik['ryzykowne: długich jednostek']}"
        )

    def manual_test():
        """Renderuje przykładowy przewodnik robota 02 do guide_test.html w katalogu głównym repo i wypisuje podsumowanie.

        Po co: widoczny przewodnik do obejrzenia w przeglądarce; wariant metryczki z argumentu: brak = stałe w kodzie,
        „plik” = przykładowy config.yml; dodatkowo sprawdzenie w pamięci metryczki bez wpisów oraz przewodników
        robotów 01 i 02 (bez zapisu plików, bez treści od pisarza).
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        wpisy = _example_config_code()
        zdanie = ""
        if len(sys.argv) > 1 and sys.argv[1] == "plik":
            wpisy = _example_config_file()
            zdanie = "wczytywany w main.py:51 przez get_config(CONFIG_FILE) · ścieżki względne liczone od katalogu projektu"
        html = _render_example(repo_dir, app_config, wpisy, zdanie)
        sciezka = os.path.join(repo_dir, "guide_test.html")
        with open(sciezka, "w", encoding="utf-8") as plik:
            plik.write(html)
        print(f"Zapisano: {sciezka} ({len(html)} znaków)")
        for nazwa, wartosc in _summary(html).items():
            print(f"  {nazwa}: {wartosc}")
        pusta = _summary(_render_example(repo_dir, app_config, [], ""))
        print(f"Metryczka bez wpisów (w pamięci): zdanie o braku konfiguracji: {pusta['metryczka: zdanie o braku konfiguracji']}, kafelków: {pusta['metryczka: kafelków']}")
        print("Roboty testowe w pamięci (bez zapisu plików):")
        limit = app_config.analysis.long_unit_lines
        _print_robot_counts(repo_dir, app_config, "02_robot_bez_frameworku", limit)
        _print_robot_counts(repo_dir, app_config, "01_rpa_challange_roboforge", limit)
        _print_robot_counts(repo_dir, app_config, "01_rpa_challange_roboforge", 15)
        print("Otwórz plik w przeglądarce: metryczka, drzewo (najedź na plik), zależności, ryzykowne miejsca, tabele, kroki z Kopiuj, pojęcia, ścieżki, przepisy.")

    manual_test()
