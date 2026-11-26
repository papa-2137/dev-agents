"""Skaner analizowanego projektu: lista plików, a w kolejnych krokach role plików i mapa projektu.

Co robi:
    - list_files() zwraca posortowaną listę ścieżek względnych (separator "/") wszystkich plików projektu,
      bez plików i katalogów pasujących do scan.ignore z configu, bez katalogów środowisk wirtualnych
      (rozpoznawanych po pliku pyvenv.cfg, więc działa dla dowolnej nazwy, np. test-venv) i zawsze bez
      katalogu dev_agents_doc/ - wyników towaru, które nie mogą trafić do analizy,
    - build_file_entries() nadaje każdemu plikowi rolę i rozmiar: secret (scan.secret_patterns, sprawdzane
      pierwsze), source (kod wg technologii projektu), pierwsza pasująca rola z scan.role_patterns, a bez
      dopasowania - other.

Dlaczego istnieje: to pierwszy krok mapy projektu - z listy plików korzystają technologia (detect, punkty
wejścia) i cała mapa, a rola decyduje, co dalej dzieje się z plikiem (kod - do analityków, konfiguracja
i pliki uruchamiające - jako tekst do agentów, sekret - wyłącznie metadane). Skaner nie otwiera żadnego
pliku - listuje nazwy i rozmiary.

Rola: moduł rdzenia towaru, używany przy budowie mapy projektu.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.scanner
        tabele ścieżka | rola | rozmiar dla robotów testowych 01 i 02 oraz katalogu tymczasowego (katalogi,
        które mają być pominięte, sekret .env, plik binarny, plik nieznanego typu), pod każdą liczba plików w rolach
    python -m dev_agents.scanner <katalog projektu>
        tabela dowolnego projektu
"""

import fnmatch
import os

import dev_agents.config as _config
import dev_agents.schemas as _schemas
import dev_agents.technologies.base as _base


# --- Lista plików ---


def _is_ignored(
    name: str,
    patterns: list[str],
) -> bool:
    """Sprawdza, czy nazwa pliku albo katalogu pasuje do któregoś wzorca (np. ".git", "*.pyc").

    Po co: jedno miejsce porównania nazw z listą scan.ignore - dla plików i dla katalogów.

    Uwaga: fnmatch na Windows porównuje bez względu na wielkość liter, na Linuksie z rozróżnieniem.
    """
    for wzorzec in patterns:
        if fnmatch.fnmatch(name, wzorzec):
            return True
    return False


def _is_skipped_directory(
    parent: str,
    name: str,
    patterns: list[str],
) -> bool:
    """Sprawdza, czy skaner ma pominąć katalog: dev_agents_doc, środowisko wirtualne (pyvenv.cfg) albo wzorzec z scan.ignore.

    Po co: decyzja o katalogu w jednym miejscu - list_files() tylko z niej korzysta.
    """
    if name == "dev_agents_doc":
        return True
    if os.path.isfile(os.path.join(parent, name, "pyvenv.cfg")):
        return True
    czy_pominac = _is_ignored(name, patterns)
    return czy_pominac


def list_files(
    root: str,
    scan_config: _config.ScanConfig,
) -> list[str]:
    """Zwraca posortowaną listę ścieżek względnych (separator "/") plików projektu, bez pomijanych plików i katalogów.

    Po co: pierwszy krok mapy projektu; separator "/" niezależnie od systemu, żeby ścieżki w mapie
    i w przewodniku wyglądały tak samo w Windows i w Linuksie.
    """
    katalog_projektu = os.path.abspath(root)
    sciezki = []
    for katalog, podkatalogi, nazwy_plikow in os.walk(katalog_projektu):
        do_przejscia = []
        for nazwa in podkatalogi:
            if not _is_skipped_directory(katalog, nazwa, scan_config.ignore):
                do_przejscia.append(nazwa)
        podkatalogi[:] = do_przejscia  # zmiana listy w miejscu mówi os.walk, do których katalogów wejść
        for nazwa in nazwy_plikow:
            if not _is_ignored(nazwa, scan_config.ignore):
                sciezka = os.path.relpath(os.path.join(katalog, nazwa), katalog_projektu)
                sciezki.append(sciezka.replace(os.sep, "/"))
    posortowane = sorted(sciezki, key=str.lower)
    return posortowane


# --- Role plików ---


def _role_from_patterns(
    name: str,
    role_patterns: dict[str, list[str]],
) -> str:
    """Zwraca pierwszą rolę z scan.role_patterns, do której wzorców pasuje nazwa pliku; "other", gdy żadna.

    Po co: role plików innych niż kod są w configu - zespół dopasowuje je do swoich projektów bez zmian w kodzie.

    Uwaga: kolejność ról w config.yaml decyduje, która wygrywa (np. dependency przed data dla requirements.txt).
    """
    for rola, wzorce in role_patterns.items():
        if _is_ignored(name, wzorce):
            return rola
    return "other"


def _file_role(
    path: str,
    scan_config: _config.ScanConfig,
    technology: _base.Technology | None,
) -> str:
    """Zwraca rolę pliku: secret, source albo rolę z wzorców (z other dla nieznanych).

    Po co: sekret sprawdzany jest pierwszy - plik pasujący do wzorca sekretu nigdy nie zostanie potraktowany
    jak kod ani konfiguracja, więc jego treść nie trafi do modelu.

    Argumenty: technology - technologia projektu albo None, gdy nie rozpoznano żadnej (wtedy nie ma plików source).
    """
    nazwa = os.path.basename(path)
    if _is_ignored(nazwa, scan_config.secret_patterns):
        return "secret"
    if technology is not None and technology.is_source(path):
        return "source"
    rola = _role_from_patterns(nazwa, scan_config.role_patterns)
    return rola


def build_file_entries(
    root: str,
    files: list[str],
    scan_config: _config.ScanConfig,
    technology: _base.Technology | None,
) -> list[_schemas.FileEntry]:
    """Zwraca FileEntry (ścieżka, rola, rozmiar w bajtach) dla każdego pliku z listy, w tej samej kolejności.

    Po co: z tej listy powstaje mapa projektu - kolejne etapy wiedzą, które pliki są kodem, które wolno czytać
    i które są tylko metadanymi.

    Uwaga: framework_name zostaje puste - pliki frameworku oznacza osobny etap skanera.
    """
    wpisy = []
    for path in files:
        rozmiar = os.path.getsize(os.path.join(root, path))
        wpisy.append(_schemas.FileEntry(path=path, role=_file_role(path, scan_config, technology), size_bytes=rozmiar))
    return wpisy


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import sys
    import tempfile

    import dev_agents.technologies.registry as _registry

    def _make_temp_project(
        directory: str,
    ) -> None:
        """Tworzy projekt tymczasowy: zwykłe pliki, katalogi do pominięcia, sekret .env, plik binarny i plik nieznanego typu.

        Po co: sprawdzenie pomijania i ról bez dotykania robotów testowych.
        """
        pliki = [
            "main.py",
            "src/modul.py",
            ".env",
            "narzedzia/program.exe",
            "dziwny.xyz",
            "dev_agents_doc/guide.html",
            ".git/config",
            "src/__pycache__/modul.cpython-314.pyc",
            "moje_srodowisko/pyvenv.cfg",
            "moje_srodowisko/Lib/site-packages/obca_paczka.py",
        ]
        for sciezka in pliki:
            pelna = os.path.join(directory, sciezka)
            os.makedirs(os.path.dirname(pelna), exist_ok=True)
            with open(pelna, "w", encoding="utf-8") as plik:
                plik.write("")

    def _scan(
        root: str,
        scan_config: _config.ScanConfig,
    ) -> tuple[str, list[_schemas.FileEntry]]:
        """Listuje pliki, wybiera technologię projektu i nadaje role. Zwraca (nazwa technologii albo "brak", wpisy).

        Po co: logika testu bez wypisywania - ten sam przebieg co później w mapie projektu.
        """
        pliki = list_files(root, scan_config)
        technologia = _registry.detect_technology(root, pliki)
        nazwa_technologii = "brak"
        if technologia is not None:
            nazwa_technologii = technologia.name
        wpisy = build_file_entries(root, pliki, scan_config, technologia)
        wynik = (nazwa_technologii, wpisy)
        return wynik

    def _print_entries(
        title: str,
        root: str,
        technology_name: str,
        entries: list[_schemas.FileEntry],
    ) -> None:
        """Wypisuje tabelę ścieżka | rola | rozmiar i liczbę plików w każdej roli.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"=== {title}: {root} (technologia: {technology_name}, plików: {len(entries)}) ===")
        licznik = {}
        for wpis in entries:
            print(f"  {wpis.path:<55} {wpis.role:<11} {wpis.size_bytes:>8}")
            licznik[wpis.role] = licznik.get(wpis.role, 0) + 1
        podsumowanie = []
        for rola, liczba in licznik.items():
            podsumowanie.append(f"{rola}: {liczba}")
        print(f"  role -> {', '.join(podsumowanie)}\n")

    def manual_test():
        """Z argumentem <katalog> - tabela ról projektu; bez argumentów - roboty testowe i katalog tymczasowy.

        Po co: sprawdzenie listy plików i ról na prawdziwych robotach i na przypadkach brzegowych.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        if len(sys.argv) == 2:
            nazwa_technologii, wpisy = _scan(sys.argv[1], app_config.scan)
            _print_entries("projekt", sys.argv[1], nazwa_technologii, wpisy)
            return

        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        for tytul, nazwa in [("robot 01", "01_rpa_challange_roboforge"), ("robot 02", "02_robot_bez_frameworku")]:
            root = os.path.join(katalog_testow, nazwa)
            if not os.path.isdir(root):
                print(f"=== {tytul}: brak katalogu {root} - pomijam ===\n")
                continue
            nazwa_technologii, wpisy = _scan(root, app_config.scan)
            _print_entries(tytul, root, nazwa_technologii, wpisy)

        temp_dir = tempfile.mkdtemp()
        try:
            _make_temp_project(temp_dir)
            nazwa_technologii, wpisy = _scan(temp_dir, app_config.scan)
            _print_entries("katalog tymczasowy", temp_dir, nazwa_technologii, wpisy)
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
