"""Obsługa technologii Python: minimalne fakty o projekcie w Pythonie, podawane bez modelu.

Co robi: implementuje kontrakt Technology dla Pythona:
    - detect, is_source - projekt jest pythonowy, gdy ma pliki .py / .pyw,
    - find_entrypoints - pliki z blokiem `if __name__ == "__main__":` oraz main.py / __main__.py,
    - units - funkcje i metody pliku z zakresami linii,
    - references - pliki projektu importowane przez plik i pakiety spoza projektu,
    - knowledge_file - plik wiedzy technologies/python.md (konwencje projektów RPA w Pythonie).
Wszystko inne (co robi kod, jak płynie logika, co jest ryzykowne) opisują agenci na podstawie pełnego kodu.

Dlaczego istnieje: cała wiedza o Pythonie siedzi w tym module (AGENTS.md, reguła 7); to jedyny moduł towaru,
który importuje `ast`. Kod robota jest tylko czytany i parsowany - nigdy importowany ani uruchamiany.
Cały cudzy kod parsuje jedna funkcja (_parse_python), która wycisza SyntaxWarning: Python 3.12+ ostrzega
przy każdym napisie typu "C:\\folder" bez r - na mieście ostrzeżenia zasypywały ekran.

Rola: moduł technologii, używany przez rdzeń towaru przez kontrakt z base.py i rejestr.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.technologies.python
        jednostki i odwołania plików robotów testowych i plików tymczasowych (ścieżka Windows w zwykłym
        napisie - oczekiwane 0 ostrzeżeń, pakiet z importem względnym, plik z błędem składni), potem
        rozpoznanie projektu (detect, pliki źródłowe, punkty wejścia), na końcu plik wiedzy technologii
        (nazwa z knowledge_file(), czy plik istnieje w bazie wiedzy)
    python -m dev_agents.technologies.python <katalog projektu> <plik względny do katalogu>
        jednostki i odwołania jednego, dowolnego pliku
"""

import ast
import os
import sys
import warnings

import dev_agents.files as _files
import dev_agents.knowledge as _knowledge
import dev_agents.schemas as _schemas
import dev_agents.technologies.base as _base


# --- Parsowanie cudzego kodu ---


def _parse_python(
    root: str,
    path: str,
) -> ast.Module | None:
    """Czyta plik przez files.read_text_safe() i parsuje go do drzewa składni bez wypisywania SyntaxWarning; przy błędzie składni zwraca None.

    Po co: jedno miejsce parsowania cudzego kodu - ostrzeżenia o napisach typu "C:\\folder" dotyczą kodu robota,
    nie towaru; plik z błędem składni daje "brak danych" (zgodnie z kontraktem), a opisze go agent.
    """
    tekst = _files.read_text_safe(os.path.join(root, path))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        try:
            drzewo = ast.parse(tekst)
        except SyntaxError:
            return None
    return drzewo


# --- Odwołania do innych plików i pakietów ---


def _module_file(
    root: str,
    module: str,
) -> str:
    """Zwraca ścieżkę względną pliku projektu dla pełnej nazwy modułu ('src.report' -> 'src/report.py', pakiet -> '<pakiet>/__init__.py'); "" gdy takiego pliku nie ma.

    Po co: kontrakt każe podawać pliki projektu jako ścieżki - graf zależności łączy pliki bez wiedzy o Pythonie.
    """
    sciezka_bazowa = module.replace(".", "/")
    for kandydat in [sciezka_bazowa + ".py", sciezka_bazowa + "/__init__.py"]:
        if os.path.isfile(os.path.join(root, kandydat)):
            return kandydat
    return ""


def _relative_base(
    path: str,
    level: int,
    module: str | None,
) -> str:
    """Zamienia import względny na pełną nazwę modułu, np. w src/x.py: 'from .report import y' -> 'src.report'.

    Po co: jednolite nazwy modułów niezależnie od tego, czy autor pisał importy względne, czy bezwzględne.
    """
    czesci = os.path.dirname(path).split("/")
    czesci = czesci[: len(czesci) - (level - 1)]
    if module:
        czesci = czesci + module.split(".")
    niepuste = []
    for czesc in czesci:
        if czesc:
            niepuste.append(czesc)
    pelna_nazwa = ".".join(niepuste)
    return pelna_nazwa


def _imported_names(
    tree: ast.Module,
    path: str,
) -> list[str]:
    """Zwraca pełne nazwy wszystkich importów pliku (także w funkcjach i try), a przy 'from X import Y' także 'X.Y' - kandydata na podmoduł.

    Po co: surowa lista nazw, z której references() wybiera pliki projektu i pakiety; stary kod RPA często
    importuje wewnątrz funkcji.
    """
    nazwy = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                nazwy.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            baza = ""
            if node.module:
                baza = node.module
            if node.level > 0:
                baza = _relative_base(path, node.level, node.module)
            if baza:
                nazwy.append(baza)
            for alias in node.names:
                nazwy.append(f"{baza}.{alias.name}".strip("."))
    return nazwy


# --- Punkty wejścia ---


def _has_main_guard(
    tree: ast.Module,
) -> bool:
    """Sprawdza, czy moduł ma na najwyższym poziomie blok `if __name__ == "__main__":` (w dowolnej kolejności stron).

    Po co: taki blok oznacza, że plik jest przeznaczony do uruchamiania - główna wskazówka punktu wejścia.
    """
    for node in tree.body:
        if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
            tekst_warunku = ast.unparse(node.test).replace("'", '"')
            if tekst_warunku in ('__name__ == "__main__"', '"__main__" == __name__'):
                return True
    return False


def _entrypoint_sort_key(
    path: str,
) -> tuple:
    """Zwraca klucz sortowania punktów wejścia: najpierw main.py i __main__.py, potem pliki płytsze, potem alfabetycznie.

    Po co: moduły z blokiem testowym też są punktami wejścia - właściwy start ma być na początku listy.

    Uwaga: nazwy porównywane bez względu na wielkość liter - na Windows Main.py i main.py to ten sam plik.
    """
    priorytet = 1
    if os.path.basename(path).lower() in ("main.py", "__main__.py"):
        priorytet = 0
    klucz = (priorytet, path.count("/"), path.lower())
    return klucz


# --- Technologia ---


class PythonTechnology(_base.Technology):
    """Projekty w Pythonie: implementacja kontraktu Technology.

    Po co: towar opisuje głównie roboty w Pythonie - ta klasa podaje rdzeniowi pewne fakty o plikach,
    na których agenci opierają opis.
    """

    name = "python"

    def detect(
        self,
        root: str,
        files: list[str],
    ) -> bool:
        """Uznaje projekt za pythonowy, gdy jest w nim choć jeden plik źródłowy Pythona.

        Po co: implementacja kontraktu Technology.detect().

        Uwaga: projekt innej technologii z pomocniczymi skryptami .py też da True - dlatego rejestr sprawdza
        technologie bardziej szczegółowe przed Pythonem.
        """
        for path in files:
            if self.is_source(path):
                return True
        return False

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Traktuje jako kod źródłowy pliki .py i .pyw (skrypty Windows uruchamiane bez okna konsoli).

        Po co: implementacja kontraktu Technology.is_source().
        """
        czy_kod = path.lower().endswith((".py", ".pyw"))
        return czy_kod

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Zwraca pliki źródłowe z blokiem `if __name__ == "__main__":` oraz main.py i __main__.py, posortowane od najbardziej prawdopodobnego startu.

        Po co: implementacja kontraktu Technology.find_entrypoints(); prawdziwe uruchomienia z plików .bat/.ps1
        rozpoznają agenci z treści tych plików.
        """
        punkty = []
        for path in files:
            if not self.is_source(path):
                continue
            drzewo = _parse_python(root, path)
            czy_nazwa_main = os.path.basename(path).lower() in ("main.py", "__main__.py")
            if czy_nazwa_main or (drzewo is not None and _has_main_guard(drzewo)):
                punkty.append(path)
        punkty_wejscia = sorted(punkty, key=_entrypoint_sort_key)
        return punkty_wejscia

    def units(
        self,
        root: str,
        path: str,
    ) -> list[_schemas.SourceUnit]:
        """Zwraca funkcje i metody pliku (metody jako "Klasa.metoda") z zakresami linii, w kolejności w pliku; przy błędzie składni pustą listę.

        Po co: implementacja kontraktu Technology.units() - pewne numery linii dla agentów i przewodnika.

        Uwaga: funkcje zagnieżdżone w funkcjach nie są osobnymi jednostkami - liczą się do funkcji, w której leżą.
        """
        jednostki = []
        drzewo = _parse_python(root, path)
        if drzewo is None:
            return jednostki
        for node in drzewo.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                jednostki.append(_schemas.SourceUnit(name=node.name, start_line=node.lineno, end_line=node.end_lineno))
            if isinstance(node, ast.ClassDef):
                for metoda in node.body:
                    if isinstance(metoda, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        nazwa = f"{node.name}.{metoda.name}"
                        jednostki.append(_schemas.SourceUnit(name=nazwa, start_line=metoda.lineno, end_line=metoda.end_lineno))
        return jednostki

    def references(
        self,
        root: str,
        path: str,
    ) -> _schemas.References:
        """Zwraca importowane pliki projektu (ścieżki) i pakiety spoza projektu (nazwy główne, bez biblioteki standardowej), posortowane.

        Po co: implementacja kontraktu Technology.references() - graf zależności i wykrywanie frameworków.

        Uwaga: przy błędzie składni puste listy; importy dynamiczne (importlib, __import__) nie są wykrywane.
        """
        pliki = []
        pakiety = []
        drzewo = _parse_python(root, path)
        if drzewo is None:
            brak_odwolan = _schemas.References()
            return brak_odwolan
        for nazwa in _imported_names(drzewo, path):
            plik = _module_file(root, nazwa)
            pakiet = nazwa.split(".")[0]
            czy_projekt = os.path.exists(os.path.join(root, pakiet)) or os.path.isfile(os.path.join(root, pakiet + ".py"))
            if plik and plik != path and plik not in pliki:
                pliki.append(plik)
            elif not czy_projekt and pakiet not in sys.stdlib_module_names and pakiet not in pakiety:
                pakiety.append(pakiet)
        odwolania = _schemas.References(files=sorted(pliki), packages=sorted(pakiety))
        return odwolania

    def knowledge_file(
        self,
    ) -> str:
        """Zwraca nazwę pliku wiedzy o Pythonie: technologies/python.md (względnie do knowledge_base/knowledge/).

        Po co: implementacja kontraktu Technology.knowledge_file() - agenci dostają konwencje zespołu
        dla każdego projektu w Pythonie.
        """
        nazwa_pliku = "technologies/python.md"
        return nazwa_pliku


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile

    def _write_temp_files(
        directory: str,
    ) -> None:
        """Zapisuje w katalogu tymczasowym pliki testowe: ścieżka Windows w zwykłym napisie, pakiet z importami, błąd składni.

        Po co: przypadki brzegowe bez dokładania plików do repo.
        """
        tresci = {
            "sciezka_windows.py": 'KATALOG = "C:\\nowy\\folder"\n\n\ndef start():\n    print(KATALOG + "\\d")\n',
            "pakiet/__init__.py": "",
            "pakiet/narzedzia.py": "def pomoc():\n    return 1\n",
            "pakiet/glowny.py": (
                "import os\nfrom .narzedzia import pomoc\n\n\nclass Robot:\n    def start(self):\n"
                "        import requests\n        return pomoc()\n\n\nif __name__ == \"__main__\":\n    Robot().start()\n"
            ),
            "blad_skladni.py": 'print "start robota"\n',
        }
        for sciezka, tresc in tresci.items():
            pelna_sciezka = os.path.join(directory, sciezka)
            os.makedirs(os.path.dirname(pelna_sciezka), exist_ok=True)
            with open(pelna_sciezka, "w", encoding="utf-8") as plik:
                plik.write(tresc)

    def _list_files(
        root: str,
    ) -> list[str]:
        """Zwraca ścieżki względne plików katalogu bez środowisk wirtualnych (katalog z pyvenv.cfg) i __pycache__.

        Po co: lista plików do testu rozpoznania projektu, zanim powstanie skaner. Nie otwiera plików.
        """
        pliki = []
        for katalog, podkatalogi, nazwy in os.walk(root):
            zostaw = []
            for podkatalog in podkatalogi:
                if podkatalog != "__pycache__" and not os.path.isfile(os.path.join(katalog, podkatalog, "pyvenv.cfg")):
                    zostaw.append(podkatalog)
            podkatalogi[:] = zostaw
            for nazwa in nazwy:
                pliki.append(os.path.relpath(os.path.join(katalog, nazwa), root).replace("\\", "/"))
        pliki.sort()
        return pliki

    def _file_lines(
        technology: PythonTechnology,
        root: str,
        path: str,
    ) -> list[str]:
        """Zwraca linie opisu pliku: jednostki z zakresami, odwołania i liczbę ostrzeżeń SyntaxWarning, które wydostały się na ekran.

        Po co: logika testu bez wypisywania.
        """
        with warnings.catch_warnings(record=True) as zlapane:
            warnings.simplefilter("always")
            jednostki = technology.units(root, path)
            odwolania = technology.references(root, path)
        linie = [f"=== {path} ({root}) ==="]
        if len(jednostki) == 0:
            linie.append("  jednostki: (brak danych)")
        for jednostka in jednostki:
            dlugosc = jednostka.end_line - jednostka.start_line + 1
            linie.append(f"  {jednostka.name:<40} linie {jednostka.start_line}-{jednostka.end_line} ({dlugosc})")
        linie.append(f"  pliki projektu: {odwolania.files}")
        linie.append(f"  pakiety:        {odwolania.packages}")
        linie.append(f"  ostrzeżenia SyntaxWarning na ekranie: {len(zlapane)}")
        return linie

    def _project_lines(
        technology: PythonTechnology,
        title: str,
        root: str,
    ) -> list[str]:
        """Zwraca linie rozpoznania projektu: detect, pliki źródłowe, punkty wejścia.

        Po co: logika testu bez wypisywania.
        """
        pliki = _list_files(root)
        zrodla = []
        for path in pliki:
            if technology.is_source(path):
                zrodla.append(path)
        linie = [
            f"=== Projekt: {title} ===",
            f"  detect:           {technology.detect(root, pliki)}",
            f"  pliki źródłowe:   {zrodla}",
            f"  find_entrypoints: {technology.find_entrypoints(root, pliki)}",
        ]
        return linie

    def _knowledge_lines(
        technology: _base.Technology,
        repo_dir: str,
    ) -> list[str]:
        """Zwraca linie o pliku wiedzy technologii: nazwa z knowledge_file(), czy plik istnieje w bazie wiedzy i ile ma znaków.

        Po co: sprawdza, że nazwa z kontraktu wskazuje prawdziwy plik w knowledge_base/knowledge/ (czytany przez
        knowledge.read_kb_file(), czyli z kontrolą granicy bazy).
        """
        nazwa = technology.knowledge_file()
        tresc = ""
        try:
            tresc = _knowledge.read_kb_file(os.path.join(repo_dir, "knowledge_base"), nazwa)
        except OSError:
            tresc = ""
        pierwsza_linia = "(brak)"
        if tresc:
            pierwsza_linia = tresc.splitlines()[0]
        linie = [
            "=== Plik wiedzy technologii ===",
            f"  knowledge_file(): {nazwa!r}",
            f"  plik istnieje i nie jest pusty: {len(tresc) > 0}",
            f"  pierwsza linia: {pierwsza_linia}",
        ]
        return linie

    def _print_lines(
        lines: list[str],
    ) -> None:
        """Wypisuje gotowe linie i pustą linię odstępu.

        Po co: wypisywanie oddzielone od logiki testu.
        """
        for linia in lines:
            print(linia)
        print()

    def manual_test():
        """Z argumentami <katalog> <plik> - jednostki i odwołania pliku; bez argumentów - przypadki testowe i rozpoznanie projektów.

        Po co: sprawdzenie technologii na prawdziwym kodzie robotów i na przypadkach brzegowych.
        """
        technology = PythonTechnology()
        if len(sys.argv) == 3:
            _print_lines(_file_lines(technology, sys.argv[1], sys.argv[2]))
            return

        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        robot_01 = os.path.join(katalog_testow, "01_rpa_challange_roboforge")
        robot_02 = os.path.join(katalog_testow, "02_robot_bez_frameworku")
        temp_dir = tempfile.mkdtemp()
        try:
            _write_temp_files(temp_dir)
            pliki = [
                (robot_01, "main.py"),
                (robot_02, "przetwarzanie.py"),
                (temp_dir, "sciezka_windows.py"),
                (temp_dir, "pakiet/glowny.py"),
                (temp_dir, "blad_skladni.py"),
            ]
            for root, path in pliki:
                if not os.path.isfile(os.path.join(root, path)):
                    _print_lines([f"=== {path}: brak pliku w {root} - pomijam ==="])
                    continue
                _print_lines(_file_lines(technology, root, path))
            for tytul, root in [("robot 01", robot_01), ("robot 02", robot_02), ("katalog tymczasowy", temp_dir)]:
                if not os.path.isdir(root):
                    _print_lines([f"=== Projekt: {tytul} - brak katalogu {root}, pomijam ==="])
                    continue
                _print_lines(_project_lines(technology, tytul, root))
            _print_lines(_knowledge_lines(technology, katalog_repo))
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
