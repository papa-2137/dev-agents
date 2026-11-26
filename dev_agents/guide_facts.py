"""Fakty z mapy projektu dla bloków przewodnika: drzewo plików, zależności do skopiowania, ryzykowne miejsca.

Co robi: z ProjectMap (skaner) i wpisów metryczki wylicza dane trzech bloków, które kod zna bez modelu:
build_tree() - drzewo katalogów i plików ze znacznikiem roli i opisem po najechaniu (z faktów: rola, rozmiar,
funkcje z zakresem linii; opis od pisarza ma pierwszeństwo), dependency_text() - treść plików zależności bez
zmian, risky_rows() - jednostki dłuższe niż próg i hasła wpisane wprost, z komentarzem pisarza dopasowanym po
dwóch pierwszych komórkach wiersza. Zwraca same napisy i słowniki, bez HTML - widoki robi render.py.

Dlaczego istnieje: pewne fakty (długość funkcji, linie, rozmiar, hasło wpisane wprost) mają pochodzić z kodu, a nie
z odpowiedzi modelu; pisarz dopisuje tylko to, czego kod nie wie (czym jest plik, dlaczego miejsce jest ryzykowne).

Czego NIE robi: nie otwiera plików i nie pokazuje treści plików z sekretami (rola secret to tylko nazwa i rozmiar);
pliki frameworku skopiowane do projektu pomija w drzewie (liczy je i podaje nazwy frameworków).

Rola: moduł rdzenia towaru, wołany przez render.py przy budowie widoków sekcji.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.guide_facts
        drzewo, zależności i ryzykowne miejsca robotów testowych 01 i 02 (tylko odczyt, nic nie jest zapisywane;
        brak robota - przypadek pomijany) oraz mapa zbudowana w pamięci: pliki frameworku, dwa pliki zależności,
        opis od pisarza, komentarz do ryzykownego miejsca i wiersz dodatkowy
"""

import dev_agents.guide_content as _content
import dev_agents.schemas as _schemas

_ROLE_TEXTS = {
    "source": "Kod robota",
    "dependency": "Lista zależności",
    "config": "Plik konfiguracyjny",
    "launcher": "Plik uruchamiający",
    "docs": "Dokumentacja",
    "data": "Plik danych",
    "binary": "Plik binarny",
    "secret": "Plik z sekretem. Treści nie analizowano.",
    "other": "Inny plik",
}
_MARKERS = {
    "source": "code",
    "dependency": "cfg",
    "config": "cfg",
    "secret": "sec",
}
_MAX_UNITS_IN_TIP = 6
_LONG_UNIT_BADGE = "długa jednostka"


# --- Hasło wpisane wprost ---


def password_mark(
    item: _content.ConfigItem,
) -> str:
    """Zwraca napis znacznika hasła: „hasło w pliku”, „hasło w kodzie” albo "" (gdy wpis nie jest hasłem wprost).

    Po co: ten sam napis w metryczce i w „Ryzykownych miejscach” - jedno miejsce zasady.
    """
    znacznik = ""
    if item.plain_password:
        znacznik = "hasło w kodzie"
        if item.file:
            znacznik = "hasło w pliku"
    return znacznik


# --- Zależności do skopiowania ---


def dependency_text(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca treść plików zależności (rola dependency) bez zmian; przy kilku plikach każdy z nagłówkiem „# --- ścieżka ---”.

    Po co: deweloper kopiuje listę paczek jednym kliknięciem; pusty tekst oznacza projekt bez pliku zależności.
    """
    pliki = []
    for plik in project_map.text_files:
        if plik.role == "dependency":
            pliki.append(plik)
    tekst = ""
    if len(pliki) == 1:
        tekst = pliki[0].text.rstrip("\n")
    if len(pliki) > 1:
        czesci = []
        for plik in pliki:
            czesci.append(f"# --- {plik.path} ---\n{plik.text.rstrip()}")
        tekst = "\n\n".join(czesci)
    return tekst


# --- Drzewo plików ---


def _size_text(
    size_bytes: int,
) -> str:
    """Zwraca rozmiar pliku jako „N B” albo „N.N KB”.

    Po co: czytelny rozmiar w opisie po najechaniu na plik.
    """
    tekst = f"{size_bytes} B"
    if size_bytes >= 1024:
        tekst = f"{size_bytes / 1024:.1f} KB"
    return tekst


def _units_by_path(
    project_map: _schemas.ProjectMap,
) -> dict[str, list[_schemas.SourceUnit]]:
    """Zwraca {ścieżka pliku źródłowego: jednostki z zakresami linii}.

    Po co: opis pliku kodu w drzewie zawiera jego funkcje z liniami - fakt ze skanera, bez modelu.
    """
    wynik = {}
    for plik in project_map.source_files:
        wynik[plik.path] = plik.units
    return wynik


def _units_text(
    units: list[_schemas.SourceUnit],
) -> str:
    """Zwraca „funkcje: nazwa (od-do), ...” dla pierwszych jednostek pliku albo "" (gdy plik nie ma jednostek).

    Po co: krótki spis funkcji w opisie pliku; więcej niż _MAX_UNITS_IN_TIP kończy się liczbą pominiętych.
    """
    czesci = []
    for jednostka in units[:_MAX_UNITS_IN_TIP]:
        czesci.append(f"{jednostka.name} ({jednostka.start_line}-{jednostka.end_line})")
    tekst = ""
    if czesci:
        tekst = "Funkcje: " + ", ".join(czesci)
        if len(units) > _MAX_UNITS_IN_TIP:
            tekst = tekst + f" i {len(units) - _MAX_UNITS_IN_TIP} innych"
    return tekst


def _writer_notes(
    writer_rows: list[list[str]],
) -> dict[str, list[str]]:
    """Zwraca {ścieżka bez końcowego „/”: wiersz [ścieżka, czym jest, rola]} z wierszy pisarza (krótsze niż 2 komórki pomija).

    Po co: opis pisarza ma pierwszeństwo przed faktami z kodu; katalog można opisać ze „/” albo bez.
    """
    notatki = {}
    for wiersz in writer_rows:
        if len(wiersz) >= 2:
            notatki[wiersz[0].rstrip("/")] = wiersz
    return notatki


def _file_node(
    entry: _schemas.FileEntry,
    entrypoints: list[str],
    units: dict[str, list[_schemas.SourceUnit]],
    notes: dict[str, list[str]],
) -> dict:
    """Zwraca węzeł pliku drzewa: nazwa, znacznik roli, opis „czym jest” i „rola” (fakty albo opis pisarza).

    Po co: jeden słownik na plik - render zamienia go na przycisk z opisem po najechaniu.
    """
    marker = _MARKERS.get(entry.role, "")
    czym = _ROLE_TEXTS.get(entry.role, _ROLE_TEXTS["other"])
    if entry.path in entrypoints:
        marker = "fill"
        czym = czym + " (punkt wejścia)"
    rola = f"Rozmiar: {_size_text(entry.size_bytes)}."
    funkcje = _units_text(units.get(entry.path, []))
    if funkcje:
        rola = rola + " " + funkcje
    notatka = notes.get(entry.path)
    if notatka:
        czym = notatka[1]
        if len(notatka) > 2:
            rola = notatka[2]
    wezel = {"name": entry.path.split("/")[-1], "is_dir": False, "marker": marker, "what": czym, "role_text": rola, "children": []}
    return wezel


def _tree_insert(
    root: dict,
    path: str,
    node: dict,
) -> None:
    """Wstawia węzeł pliku do drzewa katalogów (słowniki {dirs, files}), zakładając brakujące katalogi.

    Po co: z płaskiej listy ścieżek powstaje zagnieżdżone drzewo.
    """
    katalog = root
    for nazwa in path.split("/")[:-1]:
        if nazwa not in katalog["dirs"]:
            katalog["dirs"][nazwa] = {"dirs": {}, "files": []}
        katalog = katalog["dirs"][nazwa]
    katalog["files"].append(node)


def _count_files(
    directory: dict,
) -> int:
    """Zwraca liczbę plików w katalogu razem z podkatalogami.

    Po co: opis katalogu po najechaniu („plików: N”).
    """
    liczba = len(directory["files"])
    for podkatalog in directory["dirs"].values():
        liczba = liczba + _count_files(podkatalog)
    return liczba


def _name_key(
    node: dict,
) -> str:
    """Zwraca nazwę węzła bez rozróżniania wielkości liter - klucz sortowania.

    Po co: stała, przewidywalna kolejność plików w drzewie.
    """
    klucz = node["name"].casefold()
    return klucz


def _tree_children(
    directory: dict,
    prefix: str,
    notes: dict[str, list[str]],
) -> list[dict]:
    """Zwraca potomków katalogu: najpierw pliki, potem podkatalogi, każde alfabetycznie (jak w makiecie).

    Po co: kolejność drzewa jest wyliczana przez kod, nie zależy od kolejności plików na dysku.
    """
    pliki = list(directory["files"])
    pliki.sort(key=_name_key)
    dzieci = pliki
    for nazwa in sorted(directory["dirs"], key=str.casefold):
        podkatalog = directory["dirs"][nazwa]
        sciezka = prefix + nazwa
        czym = "Katalog"
        rola = f"Plików w katalogu: {_count_files(podkatalog)}."
        notatka = notes.get(sciezka)
        if notatka:
            czym = notatka[1]
            if len(notatka) > 2:
                rola = notatka[2]
        dzieci.append(
            {
                "name": nazwa + "/",
                "is_dir": True,
                "marker": "",
                "what": czym,
                "role_text": rola,
                "children": _tree_children(podkatalog, sciezka + "/", notes),
            }
        )
    return dzieci


def build_tree(
    project_map: _schemas.ProjectMap,
    writer_rows: list[list[str]],
) -> dict:
    """Zwraca drzewo projektu: korzeń, potomkowie, liczba plików i nazwy frameworków pominiętych w drzewie.

    Po co: blok „Drzewo projektu” - markery ról i opisy z faktów kodu, opisy pisarza (wiersze [ścieżka, czym jest, rola])
    mają pierwszeństwo. Pliki frameworku skopiowane do projektu są pominięte, żeby nie zasłaniały kodu robota.
    """
    notatki = _writer_notes(writer_rows)
    jednostki = _units_by_path(project_map)
    korzen = {"dirs": {}, "files": []}
    pominiete = 0
    frameworki = []
    for wpis in project_map.files:
        if wpis.framework_name:
            pominiete = pominiete + 1
            if wpis.framework_name not in frameworki:
                frameworki.append(wpis.framework_name)
        else:
            _tree_insert(korzen, wpis.path, _file_node(wpis, project_map.entrypoints, jednostki, notatki))
    drzewo = {
        "root": {
            "name": project_map.project_name + "/",
            "what": "Katalog główny projektu",
            "role_text": f"Plików w drzewie: {_count_files(korzen)}.",
        },
        "children": _tree_children(korzen, "", notatki),
        "file_count": _count_files(korzen),
        "skipped_count": pominiete,
        "skipped_frameworks": frameworki,
    }
    return drzewo


# --- Ryzykowne miejsca ---


def _long_unit_rows(
    project_map: _schemas.ProjectMap,
    long_unit_lines: int,
) -> list[dict]:
    """Zwraca wiersze jednostek dłuższych niż próg, od najdłuższej (remis: ścieżka, linia).

    Po co: długość funkcji to fakt ze skanera - najdłuższe jednostki to pierwsze miejsca do ostrożności.
    """
    dane = []
    for plik in project_map.source_files:
        for jednostka in plik.units:
            dlugosc = jednostka.end_line - jednostka.start_line + 1
            if dlugosc > long_unit_lines:
                dane.append((-dlugosc, plik.path, jednostka.start_line, jednostka.end_line, jednostka.name))
    dane.sort()
    wiersze = []
    for minus_dlugosc, sciezka, start, koniec, nazwa in dane:
        wiersze.append(
            {
                "place": nazwa,
                "where": f"{sciezka}:{start}-{koniec}",
                "badge": _LONG_UNIT_BADGE,
                "detail": f"{-minus_dlugosc} linii",
                "comment": "",
            }
        )
    return wiersze


def _password_rows(
    config_items: list[_content.ConfigItem],
) -> list[dict]:
    """Zwraca wiersze haseł wpisanych wprost (plain_password) z wpisów metryczki, w kolejności wpisów.

    Po co: hasło nie zginie, gdy pisarz o nim zapomni - decyzja użytkownika: błąd dewelopera ma wyjść w dokumentacji.
    """
    wiersze = []
    for wpis in config_items:
        if wpis.plain_password:
            miejsce = wpis.location
            if not miejsce:
                miejsce = wpis.file
            wiersze.append({"place": wpis.key, "where": miejsce, "badge": password_mark(wpis), "detail": "", "comment": ""})
    return wiersze


def _take_comment(
    row: dict,
    writer_rows: list[list[str]],
) -> tuple[str, list[list[str]]]:
    """Zwraca (komentarz pisarza do wiersza, wiersze pisarza bez wykorzystanego); wiersz pasuje po dwóch pierwszych komórkach.

    Po co: pisarz opisuje miejsca wskazane przez kod, powtarzając Miejsce i Plik i linie; komentarz to czwarta komórka.
    """
    komentarz = ""
    pozostale = []
    znaleziono = False
    for wiersz in writer_rows:
        pasuje = len(wiersz) >= 2 and wiersz[0] == row["place"] and wiersz[1] == row["where"]
        if pasuje and not znaleziono:
            znaleziono = True
            if len(wiersz) > 3:
                komentarz = wiersz[3]
        else:
            pozostale.append(wiersz)
    wynik = (komentarz, pozostale)
    return wynik


def risky_rows(
    project_map: _schemas.ProjectMap,
    config_items: list[_content.ConfigItem],
    long_unit_lines: int,
    writer_rows: list[list[str]],
) -> tuple[list[dict], list[list[str]]]:
    """Zwraca (wiersze z faktów kodu z komentarzem pisarza, wiersze dodatkowe pisarza bez zmian); hasła przed długimi jednostkami.

    Po co: tabela „Ryzykowne miejsca” - kod wskazuje hasła wpisane wprost i długie jednostki, pisarz dopisuje komentarz
    („Dlaczego ryzykowne”) i inne miejsca, których kod nie widzi (np. ścieżka względna).
    """
    wiersze = _password_rows(config_items)
    for wiersz in _long_unit_rows(project_map, long_unit_lines):
        wiersze.append(wiersz)
    pozostale = list(writer_rows)
    for wiersz in wiersze:
        komentarz, pozostale = _take_comment(wiersz, pozostale)
        wiersz["comment"] = komentarz
    wynik = (wiersze, pozostale)
    return wynik


# --- Test ręczny ---

if __name__ == "__main__":
    import os

    import dev_agents.config as _config
    import dev_agents.scanner as _scanner

    def _print_tree(
        children: list[dict],
        indent: str,
    ) -> None:
        """Wypisuje drzewo wcięciami: znacznik, nazwa i opis „czym jest” w nawiasie (rekurencyjnie).

        Po co: podgląd drzewa w konsoli bez HTML.
        """
        znaczniki = {"fill": "[#]", "code": "[ ]", "cfg": "[<>]", "sec": "[!]", "": "   "}
        for wezel in children:
            print(f"{indent}{znaczniki[wezel['marker']]} {wezel['name']}  ({wezel['what']} | {wezel['role_text']})")
            _print_tree(wezel["children"], indent + "    ")

    def _print_case(
        title: str,
        project_map: _schemas.ProjectMap,
        config_items: list[_content.ConfigItem],
        long_unit_lines: int,
        tree_rows: list[list[str]],
        risky_writer_rows: list[list[str]],
    ) -> None:
        """Wypisuje drzewo, zależności i ryzykowne miejsca dla jednej mapy projektu.

        Po co: wspólny wydruk przypadków testowych.
        """
        print(f"\n=== {title} ===")
        drzewo = build_tree(project_map, tree_rows)
        print(f"Drzewo: {drzewo['root']['name']} ({drzewo['file_count']} plików w drzewie, pominięte pliki frameworku: {drzewo['skipped_count']} {drzewo['skipped_frameworks']})")
        _print_tree(drzewo["children"], "  ")
        tekst = dependency_text(project_map)
        print("Zależności do skopiowania:")
        if tekst:
            for linia in tekst.split("\n"):
                print(f"  | {linia}")
        else:
            print("  (brak pliku zależności)")
        wiersze, dodatkowe = risky_rows(project_map, config_items, long_unit_lines, risky_writer_rows)
        print(f"Ryzykowne miejsca (próg {long_unit_lines} linii): z kodu {len(wiersze)}, dodatkowe od pisarza {len(dodatkowe)}")
        for wiersz in wiersze:
            opis = (wiersz["badge"] + " " + wiersz["detail"]).strip()
            print(f"  {wiersz['place']} | {wiersz['where']} | {opis} | komentarz: {wiersz['comment'] or '(brak)'}")
        for wiersz in dodatkowe:
            print(f"  [pisarz] {' | '.join(wiersz)}")

    def _robot_map(
        repo_dir: str,
        robot_name: str,
        app_config: _config.AppConfig,
    ) -> _schemas.ProjectMap | None:
        """Zwraca mapę robota testowego ze skanera (tylko odczyt) albo None, gdy robota nie ma.

        Po co: prawdziwe dane do testu; robot 01 jest tylko do odczytu - nic się nie zapisuje.
        """
        katalog = os.path.normpath(os.path.join(repo_dir, "..", "..", "tests", robot_name))
        mapa = None
        if os.path.isdir(katalog):
            mapa = _scanner.build_project_map(katalog, app_config.scan)
        return mapa

    def _memory_map() -> _schemas.ProjectMap:
        """Składa w pamięci mapę z plikami frameworku, dwoma plikami zależności i jednostką dłuższą niż próg.

        Po co: przypadki, których nie ma w robotach testowych (pominięcie frameworku, kilka plików zależności).
        """
        mapa = _schemas.ProjectMap(
            project_name="demo",
            root="demo",
            technology="python",
            entrypoints=["main.py"],
            files=[
                _schemas.FileEntry(path="main.py", role="source", size_bytes=2200),
                _schemas.FileEntry(path="config.yml", role="config", size_bytes=300),
                _schemas.FileEntry(path="requirements.txt", role="dependency", size_bytes=40),
                _schemas.FileEntry(path="certs/client.pfx", role="secret", size_bytes=2600),
                _schemas.FileEntry(path="src/page.py", role="source", size_bytes=900),
                _schemas.FileEntry(path="roboforge_framework/launcher.py", role="source", size_bytes=5000, framework_name="roboforge"),
            ],
            code_units=[],
            text_files=[
                _schemas.TextFile(path="requirements.txt", role="dependency", text="selenium==4.27.1\nopenpyxl==3.1.5\n"),
                _schemas.TextFile(path="package.json", role="dependency", text='{"name": "demo"}\n'),
            ],
            source_files=[
                _schemas.SourceFile(
                    path="main.py",
                    units=[_schemas.SourceUnit(name="run", start_line=10, end_line=210), _schemas.SourceUnit(name="log", start_line=212, end_line=220)],
                    references=_schemas.References(files=[], packages=[]),
                ),
            ],
        )
        return mapa

    def manual_test():
        """Wypisuje fakty dla robotów 01 i 02 (jeśli są) i dla mapy zbudowanej w pamięci.

        Po co: sprawdzenie drzewa, zależności i ryzykownych miejsc bez HTML i bez zapisu czegokolwiek w robotach.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        limit = app_config.analysis.long_unit_lines
        for nazwa, prog in [("02_robot_bez_frameworku", limit), ("01_rpa_challange_roboforge", 15)]:
            mapa = _robot_map(repo_dir, nazwa, app_config)
            if mapa is None:
                print(f"\n=== {nazwa} === pominięto: brak robota testowego obok repo")
            else:
                _print_case(nazwa, mapa, [], prog, [], [])
        haslo = _content.ConfigItem(file="config.yml", location="config.yml:12", key="password", value="Haslo123!", kind="account", plain_password=True, meaning="przykład")
        _print_case(
            "mapa w pamięci",
            _memory_map(),
            [haslo],
            100,
            [["main.py", "Punkt wejścia robota", "Spina cały proces"], ["src", "Moduły aplikacji"]],
            [
                ["run", "main.py:10-210", "długa jednostka", "cały proces w jednej funkcji"],
                ["password", "config.yml:12", "hasło w pliku", "hasło wpisane wprost"],
                ["INPUT_DIR", "main.py:9", "inne", "ścieżka względna"],
            ],
        )

    manual_test()
