"""Skaner analizowanego projektu: lista plików, a w kolejnych krokach role plików i mapa projektu.

Co robi: na tym etapie list_files() zwraca posortowaną listę ścieżek względnych (separator "/") wszystkich
plików projektu, bez plików i katalogów pasujących do scan.ignore z configu, bez katalogów środowisk
wirtualnych (rozpoznawanych po pliku pyvenv.cfg, więc działa dla dowolnej nazwy, np. test-venv) i zawsze
bez katalogu dev_agents_doc/ - wyników towaru, które nie mogą trafić do analizy.

Dlaczego istnieje: to pierwszy krok mapy projektu - z tej listy korzystają technologia (detect, punkty
wejścia), role plików i cała mapa. Skaner tylko listuje nazwy, nie otwiera plików.

Rola: moduł rdzenia towaru, używany przy budowie mapy projektu.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.scanner
        listy plików robotów testowych 01 i 02 oraz katalogu tymczasowego z katalogami, które mają być
        pominięte (dev_agents_doc, .git, __pycache__, środowisko wirtualne o własnej nazwie)
    python -m dev_agents.scanner <katalog projektu>
        lista plików dowolnego projektu
"""

import fnmatch
import os

import dev_agents.config as _config


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


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import sys
    import tempfile

    def _make_temp_project(
        directory: str,
    ) -> None:
        """Tworzy w katalogu tymczasowym projekt z dwoma zwykłymi plikami i katalogami, które skaner ma pominąć.

        Po co: sprawdzenie pomijania bez dotykania robotów testowych.
        """
        pliki = [
            "main.py",
            "src/modul.py",
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

    def _print_files(
        title: str,
        root: str,
        files: list[str],
    ) -> None:
        """Wypisuje listę plików z nagłówkiem i liczbą plików.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"=== {title}: {root} ({len(files)} plików) ===")
        for sciezka in files:
            print(f"  {sciezka}")
        print()

    def manual_test():
        """Z argumentem <katalog> - lista plików projektu; bez argumentów - roboty testowe i katalog tymczasowy.

        Po co: sprawdzenie pomijania katalogów i wzorców na prawdziwych robotach i na przypadkach brzegowych.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        if len(sys.argv) == 2:
            _print_files("projekt", sys.argv[1], list_files(sys.argv[1], app_config.scan))
            return

        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        for tytul, nazwa in [("robot 01", "01_rpa_challange_roboforge"), ("robot 02", "02_robot_bez_frameworku")]:
            root = os.path.join(katalog_testow, nazwa)
            if not os.path.isdir(root):
                print(f"=== {tytul}: brak katalogu {root} - pomijam ===\n")
                continue
            _print_files(tytul, root, list_files(root, app_config.scan))

        temp_dir = tempfile.mkdtemp()
        try:
            _make_temp_project(temp_dir)
            _print_files("katalog tymczasowy (oczekiwane tylko main.py i src/modul.py)", temp_dir, list_files(temp_dir, app_config.scan))
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
