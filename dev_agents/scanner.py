"""Skaner analizowanego projektu: lista plików, role plików, frameworki i mapa projektu.

Co robi:
    - list_files() zwraca posortowaną listę ścieżek względnych (separator "/") wszystkich plików projektu,
      bez plików i katalogów pasujących do scan.ignore z configu, bez katalogów środowisk wirtualnych
      (rozpoznawanych po pliku pyvenv.cfg, więc działa dla dowolnej nazwy, np. test-venv) i zawsze bez
      katalogu dev_agents_doc/ - wyników towaru, które nie mogą trafić do analizy,
    - build_file_entries() nadaje każdemu plikowi rolę i rozmiar: secret (scan.secret_patterns, sprawdzane
      pierwsze), source (kod wg technologii projektu), pierwsza pasująca rola z scan.role_patterns, a bez
      dopasowania - other; plikom frameworku skopiowanego do projektu wpisuje framework_name (scan.frameworks.paths),
    - detect_frameworks() ustala frameworki projektu - po ścieżkach plików i po pakietach importowanych w kodzie
      robota (scan.frameworks.packages), więc działa też dla frameworku zainstalowanego poza projektem (np. w venv),
    - build_project_map() składa całą mapę projektu (ProjectMap): technologia, pliki z rolami, punkty wejścia,
      dla każdego pliku źródłowego robota jednostki z zakresami linii i odwołania (SourceFile), jednostki kodu
      do analizy (jeden plik źródłowy robota = jedna jednostka), wykryte frameworki i pliki tekstowe robota
      przepisane dosłownie (role z scan.text_roles, do scan.max_text_file_kb).

Dlaczego istnieje: to pierwszy krok mapy projektu - z listy plików korzystają technologia (detect, punkty
wejścia) i cała mapa, a rola decyduje, co dalej dzieje się z plikiem (kod - do analityków, konfiguracja
i pliki uruchamiające - jako tekst do agentów, sekret - wyłącznie metadane). Skaner nie otwiera żadnego
pliku sekretu; czyta tylko pliki źródłowe (przez technologię: units, references) i małe pliki o rolach
z scan.text_roles (zależności, konfiguracja, pliki uruchamiające).

Rola: moduł rdzenia towaru, używany przy budowie mapy projektu.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.scanner
        skrót mapy robotów testowych 01 i 02 oraz katalogu tymczasowego (katalogi do pominięcia, sekret .env,
        plik binarny, plik nieznanego typu, skopiowany framework z importem requests): tabela ścieżka | rola |
        rozmiar | framework, punkty wejścia, jednostki i odwołania plików źródłowych, jednostki kodu, pliki tekstowe
        (treść tylko zależności), frameworki;
        config testu ma dodatkowy, sztuczny framework z pakietem requests (nowy framework bez zmian w kodzie)
    python -m dev_agents.scanner <katalog projektu>
        pełna mapa dowolnego projektu jako JSON (config bez zmian)
"""

import fnmatch
import os

import dev_agents.config as _config
import dev_agents.files as _files
import dev_agents.schemas as _schemas
import dev_agents.technologies.base as _base
import dev_agents.technologies.registry as _registry


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

    Uwaga: framework_name dostają tylko pliki frameworku skopiowanego do projektu (wzorce scan.frameworks.paths).
    """
    wpisy = []
    for path in files:
        wpis = _schemas.FileEntry(
            path=path,
            role=_file_role(path, scan_config, technology),
            size_bytes=os.path.getsize(os.path.join(root, path)),
            framework_name=_framework_for_path(path, scan_config.frameworks),
        )
        wpisy.append(wpis)
    return wpisy


# --- Frameworki ---


def _framework_for_path(
    path: str,
    frameworks: dict[str, _config.FrameworkConfig],
) -> str:
    """Zwraca nazwę frameworku, do którego wzorców ścieżek pasuje plik; "" gdy żadnego.

    Po co: pliki frameworku skopiowanego do projektu nie są kodem robota - analitycy ich nie opisują.
    """
    for nazwa, framework in frameworks.items():
        if _is_ignored(path, framework.paths):
            return nazwa
    return ""


def _project_packages(
    source_files: list[_schemas.SourceFile],
) -> list[str]:
    """Zwraca posortowane nazwy pakietów importowanych w plikach źródłowych robota, bez powtórzeń.

    Po co: po pakietach rozpoznajemy frameworki zainstalowane poza projektem (np. Roboforge w venv).

    Uwaga: tylko kod robota - importy wewnątrz skopiowanego frameworku nie mogą wykryć innego frameworku.
    """
    pakiety = []
    for plik_zrodlowy in source_files:
        for pakiet in plik_zrodlowy.references.packages:
            if pakiet not in pakiety:
                pakiety.append(pakiet)
    posortowane = sorted(pakiety)
    return posortowane


def detect_frameworks(
    entries: list[_schemas.FileEntry],
    packages: list[str],
    frameworks: dict[str, _config.FrameworkConfig],
    technology_name: str,
) -> list[str]:
    """Zwraca nazwy frameworków projektu: tych z technologii projektu, które mają oznaczone pliki albo pakiet na liście importów.

    Po co: wykryty framework dostaje swój plik wiedzy dla agentów, a przewodnik opisuje cykl życia robota.
    """
    wykryte = []
    for nazwa, framework in frameworks.items():
        if framework.technology != technology_name:
            continue
        czy_po_pakiecie = False
        for pakiet in framework.packages:
            if pakiet in packages:
                czy_po_pakiecie = True
        czy_po_sciezce = False
        for wpis in entries:
            if wpis.framework_name == nazwa:
                czy_po_sciezce = True
        if czy_po_pakiecie or czy_po_sciezce:
            wykryte.append(nazwa)
    return wykryte


# --- Mapa projektu ---


def _read_text_files(
    root: str,
    entries: list[_schemas.FileEntry],
    scan_config: _config.ScanConfig,
) -> list[_schemas.TextFile]:
    """Zwraca pliki robota o rolach z scan.text_roles przepisane dosłownie; pomija pliki frameworku i większe niż limit.

    Po co: zależności, konfiguracja i pliki uruchamiające trafiają do agentów i przewodnika jako tekst
    przepisany przez kod - bez udziału modelu, więc bez przekłamań.

    Uwaga: pliki sekretów nie mogą tu trafić - config przy starcie dopuszcza w text_roles tylko role
    z role_patterns (bez secret i source). Plik większy niż max_text_file_kb zostaje tylko wpisem w files.
    """
    pliki_tekstowe = []
    limit_bajtow = scan_config.max_text_file_kb * 1024
    for wpis in entries:
        if wpis.role not in scan_config.text_roles or wpis.framework_name or wpis.size_bytes > limit_bajtow:
            continue
        tekst = _files.read_text_safe(os.path.join(root, wpis.path))
        pliki_tekstowe.append(_schemas.TextFile(path=wpis.path, role=wpis.role, text=tekst))
    return pliki_tekstowe


def _source_file(
    root: str,
    path: str,
    technology: _base.Technology,
) -> _schemas.SourceFile:
    """Zwraca fakty o pliku źródłowym policzone przez technologię: jednostki z zakresami linii i odwołania.

    Po co: jedno miejsce, w którym skaner pyta technologię o plik - reszta towaru korzysta już z mapy.
    """
    plik_zrodlowy = _schemas.SourceFile(
        path=path,
        units=technology.units(root, path),
        references=technology.references(root, path),
    )
    return plik_zrodlowy


def build_project_map(
    root: str,
    scan_config: _config.ScanConfig,
) -> _schemas.ProjectMap:
    """Zwraca mapę projektu: technologia, pliki z rolami, punkty wejścia, fakty o plikach źródłowych robota, jednostki kodu i frameworki.

    Po co: jeden obiekt dla dalszych etapów (graf zależności, agenci, zapis project_map.json).

    Uwaga: nierozpoznana technologia to nie błąd - mapa ma technology="", listę plików i pliki tekstowe; o przerwaniu
    pracy decyduje wołający. Pliki frameworku nie trafiają do source_files, code_units ani punktów wejścia.
    """
    katalog = os.path.abspath(root)
    pliki = list_files(katalog, scan_config)
    technologia = _registry.detect_technology(katalog, pliki)
    wpisy = build_file_entries(katalog, pliki, scan_config, technologia)
    mapa = _schemas.ProjectMap(
        project_name=os.path.basename(katalog),
        root=katalog,
        technology="",
        entrypoints=[],
        files=wpisy,
        code_units=[],
        text_files=_read_text_files(katalog, wpisy, scan_config),
    )
    if technologia is None:
        return mapa
    pliki_robota = []
    for wpis in wpisy:
        if wpis.framework_name:
            continue
        pliki_robota.append(wpis.path)
        if wpis.role == "source":
            mapa.source_files.append(_source_file(katalog, wpis.path, technologia))
            mapa.code_units.append(_schemas.CodeUnit(name=wpis.path, files=[wpis.path]))
    mapa.technology = technologia.name
    mapa.entrypoints = technologia.find_entrypoints(katalog, pliki_robota)
    pakiety = _project_packages(mapa.source_files)
    mapa.frameworks = detect_frameworks(wpisy, pakiety, scan_config.frameworks, technologia.name)
    return mapa


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import sys
    import tempfile

    def _make_temp_project(
        directory: str,
    ) -> None:
        """Tworzy projekt tymczasowy: kod, katalogi do pominięcia, sekret .env, plik binarny, plik nieznanego typu, skopiowany framework i pliki tekstowe.

        Po co: sprawdzenie pomijania, ról i mapy bez dotykania robotów testowych; plik frameworku importuje
        requests, a kod robota nie - sztuczny framework z pakietem requests nie może zostać wykryty; duzy.json
        (101 KB) przekracza limit plików tekstowych, a .env nie może trafić do plików tekstowych.
        """
        tresci = {
            "main.py": "import src.modul\n\nsrc.modul.pomoc()\n",
            "src/modul.py": "def pomoc():\n    return 1\n",
            "roboforge_framework/launcher.py": "import requests\n",
            ".env": "SEKRET=nie-moze-trafic-do-mapy\n",
            "config.yml": "adres: https://example.test\nhaslo: wpisane-wprost\n",
            "requirements.txt": "requests\n",
            "duzy.json": "x" * (101 * 1024),
        }
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
            "roboforge_framework/launcher.py",
            "config.yml",
            "requirements.txt",
            "duzy.json",
        ]
        for sciezka in pliki:
            pelna = os.path.join(directory, sciezka)
            os.makedirs(os.path.dirname(pelna), exist_ok=True)
            with open(pelna, "w", encoding="utf-8") as plik:
                plik.write(tresci.get(sciezka, ""))

    def _test_scan_config(
        scan_config: _config.ScanConfig,
    ) -> _config.ScanConfig:
        """Zwraca kopię sekcji scan z dopisanym sztucznym frameworkiem "sztuczny" (pakiet requests).

        Po co: sprawdzenie, że nowy framework to tylko wpis w configu, bez zmian w kodzie.
        """
        kopia = scan_config.model_copy(deep=True)
        kopia.frameworks["sztuczny"] = _config.FrameworkConfig(
            technology="python",
            paths=[],
            packages=["requests"],
            knowledge="frameworks/roboforge.md",
        )
        return kopia

    def _print_map_summary(
        title: str,
        project_map: _schemas.ProjectMap,
    ) -> None:
        """Wypisuje skrót mapy: pliki, punkty wejścia, jednostki i odwołania plików źródłowych, jednostki kodu, pliki tekstowe i frameworki.

        Po co: czytelny wynik testu zamiast długiego JSON; tylko formatuje gotowe dane. Treść wypisuje tylko dla
        plików zależności - konfiguracja może zawierać hasła, więc w teście tylko liczba linii.
        """
        technologia = project_map.technology
        if not technologia:
            technologia = "brak"
        print(f"=== {title}: {project_map.root} (technologia: {technologia}, plików: {len(project_map.files)}) ===")
        for wpis in project_map.files:
            print(f"  {wpis.path:<55} {wpis.role:<11} {wpis.size_bytes:>8}  {wpis.framework_name}")
        print(f"  Punkty wejścia: {project_map.entrypoints}")
        for plik_zrodlowy in project_map.source_files:
            jednostki = []
            for jednostka in plik_zrodlowy.units:
                jednostki.append(f"{jednostka.name} {jednostka.start_line}-{jednostka.end_line}")
            print(f"  {plik_zrodlowy.path}")
            print(f"      jednostki: {', '.join(jednostki)}")
            print(f"      pliki: {plik_zrodlowy.references.files}  pakiety: {plik_zrodlowy.references.packages}")
        nazwy_jednostek = []
        for jednostka_kodu in project_map.code_units:
            nazwy_jednostek.append(jednostka_kodu.name)
        print(f"  Jednostki kodu ({len(nazwy_jednostek)}): {nazwy_jednostek}")
        print(f"  Pliki tekstowe ({len(project_map.text_files)}):")
        for plik_tekstowy in project_map.text_files:
            linie = plik_tekstowy.text.splitlines()
            print(f"      {plik_tekstowy.path} ({plik_tekstowy.role}, linii: {len(linie)})")
            if plik_tekstowy.role == "dependency":
                for linia in linie:
                    print(f"          | {linia}")
        print(f"  Frameworki: {project_map.frameworks}\n")

    def manual_test():
        """Z argumentem <katalog> - pełna mapa projektu jako JSON; bez argumentów - skrót map robotów testowych i katalogu tymczasowego.

        Po co: sprawdzenie mapy na prawdziwych robotach i na przypadkach brzegowych.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        if len(sys.argv) == 2:
            print(build_project_map(sys.argv[1], app_config.scan).model_dump_json(indent=2))
            return

        scan_config = _test_scan_config(app_config.scan)
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        for tytul, nazwa in [("robot 01", "01_rpa_challange_roboforge"), ("robot 02", "02_robot_bez_frameworku")]:
            root = os.path.join(katalog_testow, nazwa)
            if not os.path.isdir(root):
                print(f"=== {tytul}: brak katalogu {root} - pomijam ===\n")
                continue
            _print_map_summary(tytul, build_project_map(root, scan_config))

        temp_dir = tempfile.mkdtemp()
        try:
            _make_temp_project(temp_dir)
            _print_map_summary("katalog tymczasowy", build_project_map(temp_dir, scan_config))
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
