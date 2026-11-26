"""Baza wiedzy: spis plików wiedzy (index.md) i bezpieczny odczyt ich treści.

Co robi:
    - load_index() wczytuje knowledge_base/knowledge/index.md i zwraca listę wpisów KBEntry (plik, „Kiedy użyć”,
      tagi) - na tej podstawie planner wybiera pliki wiedzy dla projektu,
    - read_kb_file() zwraca treść wybranego pliku wiedzy - tylko pliku leżącego w knowledge_base/knowledge/
      (nazwa od modelu nie może wskazać pliku spoza bazy, także przez dowiązanie symboliczne).

Format index.md (zwykły tekst, łatwy do dopisywania): blok na plik, bloki oddzielone pustą linią:
    podkatalog/nazwa_pliku.md
    Kiedy użyć: ...
    Tagi: tag1, tag2
Nazwa pliku jest względna do knowledge_base/knowledge/ (tak jak pole knowledge frameworku w config.yaml). Linia „Tagi:”
jest opcjonalna. Blok, którego pierwsza linia nie jest nazwą pliku .md (nagłówek „# ...” i instrukcja na początku
pliku), jest pomijany.

Spis jest ścisły - błąd wychodzi przy wczytaniu, a nie jako cicho zgubiona wiedza: wpis bez „Kiedy użyć:” (np.
literówka), powtórzony wpis, wpis z nazwą wychodzącą poza bazę i wpis wskazujący plik, którego nie ma, kończą się
ValueError z nazwą pliku.

Czego NIE robi: nie wybiera plików dla projektu (planner), nie dodaje do wyboru plików technologii i wykrytych
frameworków (kod agentów), nie czyta szablonów przewodnika (guide_template.py).

Rola: moduł rdzenia towaru, wołany przez plannera i agentów w grafie (faza F). Katalog bazy to paths.knowledge_base
z config.yaml.

Test ręczny (z katalogu głównego repo; baza testowa w katalogu tymczasowym, który jest sprzątany):
    python -m dev_agents.knowledge
        wypisuje wpisy spisu testowego i wyniki przypadków (spis z podkatalogami, odczyt pliku, próby wyjścia poza
        bazę: „..”, ścieżka bezwzględna spoza bazy, „..” w środku, dowiązanie symboliczne; spis z literówką, powtórzeniem,
        brakującym plikiem i nazwą spoza bazy), na końcu „zgodne z oczekiwaniem: True” albo wypisuje, który przypadek
        się nie zgadza; jeśli w repo jest już prawdziwy index.md, wypisuje też jego wpisy
"""

import os

import pydantic

_INDEX_NAME = "index.md"
_WHEN_PREFIX = "Kiedy użyć:"
_TAGS_PREFIX = "Tagi:"


class KBEntry(pydantic.BaseModel):
    """Jeden wpis spisu bazy wiedzy: nazwa pliku względna do knowledge/, kiedy użyć (dla plannera), tagi."""

    filename: str
    when_to_use: str
    tags: list[str]


def _knowledge_dir(
    knowledge_base_dir: str,
) -> str:
    """Zwraca katalog knowledge/ bazy wiedzy po rozwiązaniu dowiązań (ścieżka bezwzględna).

    Po co: jedno miejsce, z którego liczy się granica bazy wiedzy.
    """
    katalog = os.path.realpath(os.path.join(knowledge_base_dir, "knowledge"))
    return katalog


def _resolve_kb_path(
    knowledge_base_dir: str,
    filename: str,
) -> str:
    """Zwraca ścieżkę pliku wiedzy po rozwiązaniu dowiązań; leżącą poza knowledge/ - ValueError z nazwą pliku.

    Po co: nazwę pliku podaje model albo wpis spisu - bez tej kontroli „..\\config.yaml”, ścieżka bezwzględna albo
    dowiązanie wskazujące poza bazę odczytałyby dowolny plik z dysku i wysłały go do modelu.
    """
    katalog = _knowledge_dir(knowledge_base_dir)
    sciezka = os.path.realpath(os.path.join(katalog, filename))
    if not os.path.normcase(sciezka).startswith(os.path.normcase(katalog) + os.sep):
        komunikat = f"Plik spoza bazy wiedzy: {filename}"
        raise ValueError(komunikat)
    return sciezka


def parse_entry(
    block_lines: list[str],
) -> KBEntry | None:
    """Zamienia blok spisu (linie bez pustych) na KBEntry; blok niebędący wpisem (nagłówek, instrukcja) - None.

    Po co: blok, którego pierwsza linia jest nazwą pliku .md, musi mieć „Kiedy użyć:” - inaczej ValueError z nazwą
    pliku (literówka w spisie nie może po cichu zgubić pliku wiedzy). Linia „Tagi:” jest opcjonalna.
    """
    pierwsza = block_lines[0]
    wpis = None
    if pierwsza.lower().endswith(".md") and not pierwsza.startswith("#"):
        kiedy = ""
        tagi = []
        for linia in block_lines[1:]:
            if linia.startswith(_WHEN_PREFIX):
                kiedy = linia[len(_WHEN_PREFIX) :].strip()
            elif linia.startswith(_TAGS_PREFIX):
                for tag in linia[len(_TAGS_PREFIX) :].split(","):
                    if tag.strip() != "":
                        tagi.append(tag.strip())
        if kiedy == "":
            komunikat = f"{_INDEX_NAME}: wpis „{pierwsza}” nie ma linii „{_WHEN_PREFIX}”"
            raise ValueError(komunikat)
        wpis = KBEntry(filename=pierwsza, when_to_use=kiedy, tags=tagi)
    return wpis


def parse_index(
    text: str,
) -> list[KBEntry]:
    """Dzieli tekst index.md na bloki oddzielone pustymi liniami i zwraca wpisy; powtórzona nazwa pliku - ValueError.

    Po co: spis jest zwykłym tekstem, żeby zespół mógł łatwo dopisywać pliki - tu zamieniamy go na dane dla plannera.
    """
    wpisy = []
    nazwy = set()
    blok = []
    for linia in text.splitlines() + [""]:
        if linia.strip() != "":
            blok.append(linia.strip())
            continue
        if blok:
            wpis = parse_entry(blok)
            if wpis is not None:
                if wpis.filename in nazwy:
                    komunikat = f"{_INDEX_NAME}: plik „{wpis.filename}” jest we wpisach dwa razy"
                    raise ValueError(komunikat)
                nazwy.add(wpis.filename)
                wpisy.append(wpis)
        blok = []
    return wpisy


def load_index(
    knowledge_base_dir: str,
) -> list[KBEntry]:
    """Wczytuje knowledge/index.md (UTF-8) i zwraca wpisy; wpis z nazwą spoza bazy albo bez pliku - ValueError.

    Po co: jedno wejście do spisu bazy wiedzy dla plannera; błędy spisu wychodzą od razu, z nazwą pliku.
    Argument: config.paths.knowledge_base.
    """
    sciezka_spisu = os.path.join(_knowledge_dir(knowledge_base_dir), _INDEX_NAME)
    with open(sciezka_spisu, encoding="utf-8") as plik:
        tekst = plik.read()
    wpisy = parse_index(tekst)
    for wpis in wpisy:
        sciezka = _resolve_kb_path(knowledge_base_dir, wpis.filename)
        if not os.path.isfile(sciezka):
            komunikat = f"{_INDEX_NAME}: wpis „{wpis.filename}” wskazuje plik, którego nie ma w bazie wiedzy"
            raise ValueError(komunikat)
    return wpisy


def read_kb_file(
    knowledge_base_dir: str,
    filename: str,
) -> str:
    """Zwraca treść pliku z knowledge_base/knowledge/ (UTF-8); nazwa wskazująca poza ten katalog - ValueError.

    Po co: nazwy plików do przeczytania wybiera model (planner) - bez kontroli błędna albo podsunięta nazwa
    (np. „../config.yaml”, ścieżka bezwzględna, dowiązanie) odczytałaby dowolny plik z dysku.
    Argumenty: knowledge_base_dir - config.paths.knowledge_base, filename - nazwa względna do knowledge/.
    """
    sciezka = _resolve_kb_path(knowledge_base_dir, filename)
    with open(sciezka, encoding="utf-8") as plik:
        tresc = plik.read()
    return tresc


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile

    import dev_agents.config as _config

    _TEST_INDEX = (
        "# Baza wiedzy - spis plików\n"
        "\n"
        "Planner czyta ten spis i wybiera pliki.\n"
        "Nowy plik: dopisz wpis poniżej.\n"
        "\n"
        "guide_goals.md\n"
        "Kiedy użyć: zawsze przy pisaniu przewodnika.\n"
        "Tagi: styl, odbiorca\n"
        "\n"
        "frameworks/roboforge.md\n"
        "Kiedy użyć: robot na frameworku Roboforge.\n"
        "Tagi: roboforge, framework\n"
        "\n"
        "technologies/python.md\n"
        "Kiedy użyć: projekt w Pythonie.\n"
    )
    _TEST_FILES = {
        "guide_goals.md": "Cele przewodnika.\n",
        "frameworks/roboforge.md": "Roboforge: cykl życia.\n",
        "technologies/python.md": "Konwencje Pythona.\n",
    }

    def _make_base(
        root: str,
        name: str,
        index_text: str,
        files: dict,
    ) -> str:
        """Tworzy w katalogu root bazę wiedzy <name>/knowledge/ z index.md i plikami; zwraca katalog bazy.

        Po co: każdy przypadek testowy ma własną, małą bazę w katalogu tymczasowym - w repo nie zostaje nic zbędnego.
        """
        baza = os.path.join(root, name)
        katalog = os.path.join(baza, "knowledge")
        os.makedirs(katalog)
        with open(os.path.join(katalog, _INDEX_NAME), "w", encoding="utf-8") as plik:
            plik.write(index_text)
        for nazwa, tresc in files.items():
            sciezka = os.path.join(katalog, nazwa)
            os.makedirs(os.path.dirname(sciezka), exist_ok=True)
            with open(sciezka, "w", encoding="utf-8") as plik:
                plik.write(tresc)
        return baza

    def _load_error(
        base: str,
    ) -> str:
        """Zwraca tekst błędu ValueError z load_index; brak błędu - pusty tekst.

        Po co: przypadki ze zepsutym spisem sprawdzane tym samym zapisem, bez powielania try/except.
        """
        tekst = ""
        try:
            load_index(base)
        except ValueError as blad:
            tekst = str(blad)
        return tekst

    def _read_error(
        base: str,
        filename: str,
    ) -> str:
        """Zwraca tekst błędu ValueError z read_kb_file; brak błędu - pusty tekst.

        Po co: próby wyjścia poza bazę sprawdzane tym samym zapisem.
        """
        tekst = ""
        try:
            read_kb_file(base, filename)
        except ValueError as blad:
            tekst = str(blad)
        return tekst

    def _symlink_case(
        root: str,
        base: str,
    ) -> str:
        """Tworzy w bazie dowiązanie do pliku poza nią i zwraca wynik próby odczytu: błąd, „brak uprawnień” albo treść.

        Po co: dowiązanie wskazujące poza bazę nie może jej obejść; bez uprawnień do dowiązań (zwykły Windows)
        przypadek jest pomijany z komunikatem.
        """
        poza = os.path.join(root, "poza.txt")
        with open(poza, "w", encoding="utf-8") as plik:
            plik.write("tajne\n")
        wynik = "brak uprawnień"
        try:
            os.symlink(poza, os.path.join(base, "knowledge", "dowiazanie.md"))
        except (OSError, NotImplementedError):
            return wynik
        wynik = _read_error(base, "dowiazanie.md")
        if wynik == "":
            wynik = "odczytano plik spoza bazy"
        return wynik

    def _print_entries(
        title: str,
        entries: list[KBEntry],
    ) -> None:
        """Wypisuje wpisy spisu: nazwa pliku, „Kiedy użyć”, tagi.

        Po co: w teście widać, czy index.md został poprawnie odczytany.
        """
        print(f"=== {title}: {len(entries)} wpisy ===")
        for wpis in entries:
            print(wpis.filename)
            print(f"  Kiedy użyć: {wpis.when_to_use}")
            print(f"  Tagi: {', '.join(wpis.tags)}")

    def _real_index(
        repo_dir: str,
    ) -> None:
        """Wypisuje wpisy prawdziwego index.md z bazy wiedzy repo albo komunikat, że go jeszcze nie ma.

        Po co: gdy spis powstanie (krok 42), ten sam test pokazuje go bez zmian w kodzie.
        """
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        sciezka = os.path.join(_knowledge_dir(app_config.paths.knowledge_base), _INDEX_NAME)
        if not os.path.isfile(sciezka):
            print(f"Prawdziwy spis: brak pliku {sciezka} (powstanie w kroku 42)")
            return
        _print_entries("Prawdziwy spis bazy wiedzy", load_index(app_config.paths.knowledge_base))

    def manual_test():
        """Sprawdza spis i odczyt na bazach testowych w katalogu tymczasowym i wypisuje, czy wszystko zgadza się z oczekiwaniem.

        Po co: sprawdzenie parsera index.md, ścisłości spisu i blokady odczytu spoza bazy bez prawdziwych danych.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        root = tempfile.mkdtemp()
        try:
            baza = _make_base(root, "dobra", _TEST_INDEX, _TEST_FILES)
            wpisy = load_index(baza)
            _print_entries("Spis testowy", wpisy)
            tresc = read_kb_file(baza, "frameworks/roboforge.md")
            print(f"Odczyt frameworks/roboforge.md: {tresc.strip()}")

            bez_pliku = _make_base(root, "bez_pliku", _TEST_INDEX, {"guide_goals.md": "x\n"})
            literowka = _make_base(root, "literowka", "guide_goals.md\nKiedy uzyc: literówka\n", _TEST_FILES)
            powtorzony = _make_base(root, "powtorzony", "guide_goals.md\nKiedy użyć: a\n\nguide_goals.md\nKiedy użyć: b\n", _TEST_FILES)
            spoza = _make_base(root, "spoza", "../poza.md\nKiedy użyć: wyjście poza bazę\n", _TEST_FILES)
            abs_path = os.path.join(root, "poza.txt")
            wynik_dowiazania = _symlink_case(root, baza)
            print("=== oczekiwane błędy ===")
            for tytul, blad in [
                ("brak pliku ze spisu", _load_error(bez_pliku)),
                ("literówka w „Kiedy użyć”", _load_error(literowka)),
                ("powtórzony wpis", _load_error(powtorzony)),
                ("nazwa spoza bazy w spisie", _load_error(spoza)),
                ("odczyt ../config.yaml", _read_error(baza, "../config.yaml")),
                ("odczyt ścieżki bezwzględnej spoza bazy", _read_error(baza, abs_path)),
                ("odczyt z .. w środku", _read_error(baza, "frameworks/../../x.md")),
                ("odczyt przez dowiązanie", wynik_dowiazania),
            ]:
                print(f"  {tytul}: {blad}")

            nazwy = []
            for wpis in wpisy:
                nazwy.append(wpis.filename)
            przypadki = [
                ("spis: 3 wpisy, nagłówek i instrukcja pominięte", nazwy == ["guide_goals.md", "frameworks/roboforge.md", "technologies/python.md"]),
                ("spis: tagi i „Kiedy użyć”", wpisy[0].tags == ["styl", "odbiorca"] and wpisy[0].when_to_use == "zawsze przy pisaniu przewodnika."),
                ("spis: wpis bez tagów ma pustą listę", wpisy[2].tags == []),
                ("odczyt pliku z podkatalogu", tresc == "Roboforge: cykl życia.\n"),
                ("brak pliku ze spisu: ValueError z nazwą", "frameworks/roboforge.md" in _load_error(bez_pliku) and "nie ma" in _load_error(bez_pliku)),
                ("literówka: ValueError z nazwą pliku", "guide_goals.md" in _load_error(literowka) and "Kiedy użyć" in _load_error(literowka)),
                ("powtórzony wpis: ValueError", "dwa razy" in _load_error(powtorzony)),
                ("nazwa spoza bazy w spisie: ValueError", "spoza bazy wiedzy" in _load_error(spoza)),
                ("../config.yaml odrzucone", "spoza bazy wiedzy" in _read_error(baza, "../config.yaml")),
                ("ścieżka bezwzględna spoza bazy odrzucona", "spoza bazy wiedzy" in _read_error(baza, abs_path)),
                ("„..” w środku odrzucone", "spoza bazy wiedzy" in _read_error(baza, "frameworks/../../x.md")),
                ("dowiązanie poza bazę odrzucone (albo brak uprawnień)", "spoza bazy wiedzy" in wynik_dowiazania or wynik_dowiazania == "brak uprawnień"),
            ]
            zgodne = True
            for opis, wynik in przypadki:
                if not wynik:
                    zgodne = False
                    print(f"  niezgodne: {opis}")
            print(f"Przypadków: {len(przypadki)}, zgodne z oczekiwaniem: {zgodne}")
        finally:
            shutil.rmtree(root)
        _real_index(repo_dir)

    manual_test()
