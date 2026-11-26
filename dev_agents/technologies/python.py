"""Obsługa technologii Python: implementacja kontraktu Technology dla projektów w Pythonie.

Co robi: na tym etapie buduje szkielet pliku .py (outline) - spis treści bez ciał funkcji: liczba linii,
opis modułu, stałe, zmienne modułu, kod wykonywany poza funkcjami, klasy i funkcje z sygnaturami,
pierwszym akapitem docstringu i zakresem linii. Szkielet pokazuje strukturę także kodu "spaghetti":
od razu widać funkcję na kilkaset linii albo logikę luzem poza funkcjami. Pozostałe metody kontraktu
dochodzą w kolejnych krokach.

Dlaczego istnieje: cała wiedza o Pythonie siedzi w tym module, a rdzeń towaru woła tylko metody kontraktu
(AGENTS.md, reguła 7). To jedyny moduł towaru, który importuje `ast` (parser Pythona z biblioteki
standardowej). Kod analizowanego projektu jest tylko czytany i parsowany - nigdy importowany ani
uruchamiany. Cały cudzy kod parsuje jedna funkcja (_parse_python), która wycisza SyntaxWarning:
Python 3.12+ ostrzega przy każdym napisie typu "C:\\folder" bez r, a w kodzie robotów takich napisów
jest pełno - na mieście ostrzeżenia zasypywały ekran.

Rola: moduł technologii, używany przez rdzeń towaru przez kontrakt z base.py.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.technologies.python
        szkielety: robot 01 (Main.py, src/parabank_page.py), robot 02 (przetwarzanie.py), plik ze ścieżką
        Windows w zwykłym napisie (z liczbą ostrzeżeń - oczekiwane 0) i plik w składni Pythona 2
        (oczekiwana linia z przyczyną zamiast szkieletu)
    python -m dev_agents.technologies.python <katalog projektu> <plik względny do katalogu>
        szkielet jednego, dowolnego pliku
"""

import ast
import os
import warnings

import dev_agents.files as _files
import dev_agents.technologies.base as _base


# --- Parsowanie cudzego kodu ---


def _parse_python(
    source: str,
) -> ast.Module:
    """Parsuje tekst kodu Pythona do drzewa składni, bez wypisywania ostrzeżeń SyntaxWarning.

    Po co: jedno miejsce parsowania cudzego kodu dla wszystkich funkcji modułu - ostrzeżenia o napisach
    typu "C:\\folder" dotyczą kodu robota, nie towaru, i nie mogą zasypywać ekranu.

    Uwaga: błąd składni (np. kod w Pythonie 2) nie jest łapany - wołający dostaje SyntaxError
    z numerem linii i opisem.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        drzewo = ast.parse(source)
    return drzewo


# --- Budowa szkieletu ---


def _first_paragraph(
    docstring: str | None,
    max_length: int = 200,
) -> str:
    """Zwraca pierwszy akapit docstringu (linie do pierwszej pustej), sklejony w jedną linię i przycięty do max_length.

    Po co: przy każdej klasie i funkcji szkielet pokazuje krótki opis; pierwsza linia często urywa się
    w pół zdania, a pełny docstring bywa bardzo długi - akapit to kompromis.
    """
    if not docstring:
        return ""
    linie_akapitu = []
    for linia in docstring.strip().splitlines():
        if not linia.strip():
            break
        linie_akapitu.append(linia.strip())
    akapit = " ".join(linie_akapitu)
    if len(akapit) > max_length:
        akapit = akapit[:max_length].rstrip() + "..."
    return akapit


def _constant_names(
    body: list,
) -> list[str]:
    """Zwraca nazwy stałych (przypisań do nazw pisanych WIELKIMI LITERAMI) w ciele modułu albo klasy.

    Po co: w kodzie RPA stałe niosą kluczową informację (adresy, katalogi, selektory, przełączniki) -
    same nazwy mówią analitykowi, czym operuje moduł, bez wydłużania szkieletu o wartości.
    """
    nazwy = []
    for node in body:
        cele = []
        if isinstance(node, ast.Assign):
            cele = node.targets
        elif isinstance(node, ast.AnnAssign):
            cele = [node.target]
        for cel in cele:
            if isinstance(cel, ast.Name) and cel.id.isupper():
                nazwy.append(cel.id)
    return nazwy


def _line_range(
    node,
) -> str:
    """Zwraca zakres linii definicji w postaci '[linie 40-310, razem 271]'.

    Po co: w szkielecie od razu widać bardzo długie funkcje i klasy - sygnał, gdzie jest najwięcej logiki.
    """
    liczba = node.end_lineno - node.lineno + 1
    zakres_linii = f"[linie {node.lineno}-{node.end_lineno}, razem {liczba}]"
    return zakres_linii


def _is_module_docstring(
    index: int,
    node,
) -> bool:
    """Sprawdza, czy instrukcja jest docstringiem modułu (pierwsza instrukcja pliku będąca samym napisem).

    Po co: docstring modułu nie jest "kodem poza funkcjami" i nie może trafić do opisu logiki luzem.
    """
    if index != 0 or not isinstance(node, ast.Expr):
        return False
    czy_docstring = isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
    return czy_docstring


def _module_level_segments(
    tree: ast.Module,
) -> list[list]:
    """Zbiera kod wykonywany na poziomie modułu (poza importami, definicjami i docstringiem) i grupuje go w odcinki kolejnych instrukcji.

    Po co: w kodzie "spaghetti" logika siedzi poza funkcjami i bez tego szkielet byłby pusty; podział na
    odcinki (np. stałe na górze, blok `if __name__` na dole) pokazuje, gdzie dokładnie ten kod leży.
    """
    definicje = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    odcinki = []
    biezacy = []
    for index, node in enumerate(tree.body):
        if isinstance(node, definicje) or _is_module_docstring(index, node):
            if len(biezacy) > 0:
                odcinki.append(biezacy)
                biezacy = []
        else:
            biezacy.append(node)
    if len(biezacy) > 0:
        odcinki.append(biezacy)
    return odcinki


def _flatten_segments(
    segments: list[list],
) -> list:
    """Skleja odcinki kodu modułu w jedną listę instrukcji.

    Po co: zmienne i liczniki pętli liczymy dla całego kodu poza funkcjami, niezależnie od podziału na odcinki.
    """
    instrukcje = []
    for odcinek in segments:
        for instrukcja in odcinek:
            instrukcje.append(instrukcja)
    return instrukcje


def _variable_names(
    statements: list,
) -> list[str]:
    """Zwraca nazwy zmiennych przypisywanych w podanych instrukcjach (bez stałych pisanych WIELKIMI LITERAMI), bez powtórzeń.

    Po co: w skryptach bez konwencji zmienne modułu są jedynym śladem tego, czym skrypt operuje
    (np. workbook, driver przeglądarki, plik logu).
    """
    nazwy = []
    for instrukcja in statements:
        for node in ast.walk(instrukcja):
            czy_przypisanie = isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
            if czy_przypisanie and not node.id.isupper() and node.id not in nazwy:
                nazwy.append(node.id)
    return nazwy


def _describe_module_code(
    segments: list[list],
) -> str:
    """Buduje jedną linię opisu kodu poza funkcjami: liczba instrukcji, odcinki linii, liczba pętli i bloków try.

    Po co: od razu widać, czy plik jest skryptem z logiką luzem (pętle, obsługa błędów), czy biblioteką
    funkcji z kilkoma stałymi.
    """
    instrukcje = _flatten_segments(segments)
    zakresy = []
    for odcinek in segments:
        zakresy.append(f"{odcinek[0].lineno}-{odcinek[-1].end_lineno}")
    petle = 0
    bloki_try = 0
    for instrukcja in instrukcje:
        for node in ast.walk(instrukcja):
            if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
                petle += 1
            elif isinstance(node, ast.Try):
                bloki_try += 1
    opis_kodu = f"Kod poza funkcjami: instrukcje {len(instrukcje)}, linie {', '.join(zakresy)}"
    if petle > 0 or bloki_try > 0:
        opis_kodu += f" - pętle: {petle}, try: {bloki_try}"
    return opis_kodu


def _format_decorators(
    node,
    indent: str,
) -> list[str]:
    """Zwraca linie dekoratorów klasy albo funkcji, każdy z wcięciem.

    Po co: dekoratory (np. rejestracja kroku we frameworku) zmieniają sposób wywołania funkcji -
    analityk musi je widzieć.
    """
    linie = []
    for dekorator in node.decorator_list:
        linie.append(f"{indent}@{ast.unparse(dekorator)}")
    return linie


def _format_function(
    node,
    indent: str,
) -> list[str]:
    """Buduje linie szkieletu jednej funkcji albo metody: dekoratory, sygnatura z zakresem linii, pierwszy akapit docstringu.

    Po co: sygnatura z typami i opisem to minimum, żeby analityk wiedział, co funkcja przyjmuje, co zwraca
    i do czego służy - bez czytania jej ciała.
    """
    linie = _format_decorators(node, indent)
    przedrostek = "def"
    if isinstance(node, ast.AsyncFunctionDef):
        przedrostek = "async def"
    typ_wyniku = ""
    if node.returns is not None:
        typ_wyniku = f" -> {ast.unparse(node.returns)}"
    linie.append(f"{indent}{przedrostek} {node.name}({ast.unparse(node.args)}){typ_wyniku}  {_line_range(node)}")
    opis = _first_paragraph(ast.get_docstring(node))
    if opis:
        linie.append(f"{indent}    {opis}")
    return linie


def _format_class(
    node: ast.ClassDef,
    indent: str,
) -> list[str]:
    """Buduje linie szkieletu klasy: nagłówek z klasami bazowymi i zakresem linii, docstring, stałe, metody, klasy zagnieżdżone.

    Po co: klasy bazowe pokazują zależność od frameworku (np. dziedziczenie po klasie robota),
    a lista metod - jakie kroki procesu klasa realizuje.
    """
    linie = _format_decorators(node, indent)
    bazy = []
    for baza in node.bases:
        bazy.append(ast.unparse(baza))
    naglowek = f"{indent}class {node.name}"
    if len(bazy) > 0:
        naglowek = f"{indent}class {node.name}({', '.join(bazy)})"
    linie.append(f"{naglowek}  {_line_range(node)}")

    opis = _first_paragraph(ast.get_docstring(node))
    if opis:
        linie.append(f"{indent}    {opis}")
    stale = _constant_names(node.body)
    if len(stale) > 0:
        linie.append(f"{indent}    Stałe: {', '.join(stale)}")

    for dziecko in node.body:
        if isinstance(dziecko, (ast.FunctionDef, ast.AsyncFunctionDef)):
            linie.extend(_format_function(dziecko, indent + "    "))
        elif isinstance(dziecko, ast.ClassDef):
            linie.extend(_format_class(dziecko, indent + "    "))
    return linie


def _build_outline(
    tree: ast.Module,
    line_count: int,
) -> str:
    """Składa szkielet całego modułu: liczba linii, docstring, stałe, zmienne, kod poza funkcjami, klasy i funkcje.

    Po co: to wynik metody outline() - jeden czytelny tekst, który analityk dostaje razem z kodem pliku.
    """
    linie = [f"Liczba linii: {line_count}"]
    opis = _first_paragraph(ast.get_docstring(tree))
    if opis:
        linie.append(f"Moduł: {opis}")
    stale = _constant_names(tree.body)
    if len(stale) > 0:
        linie.append(f"Stałe: {', '.join(stale)}")

    odcinki = _module_level_segments(tree)
    zmienne = _variable_names(_flatten_segments(odcinki))
    if len(zmienne) > 0:
        linie.append(f"Zmienne modułu: {', '.join(zmienne)}")
    if len(odcinki) > 0:
        linie.append(_describe_module_code(odcinki))

    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            linie.append("")
            linie.extend(_format_class(node, ""))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            linie.append("")
            linie.extend(_format_function(node, ""))

    szkielet = "\n".join(linie).strip()
    return szkielet


def _syntax_error_outline(
    error: SyntaxError,
) -> str:
    """Zwraca jedną linię "szkieletu" dla pliku, którego nie da się sparsować: numer linii i opis błędu składni.

    Po co: analityk i przewodnik wiedzą, dlaczego nie ma szkieletu - np. robot w Pythonie 2 albo plik
    z błędem to informacja do "Ryzykownych miejsc", a nie cicha dziura.
    """
    opis_bledu = f"Szkielet niedostępny: błąd składni w linii {error.lineno} ({error.msg})"
    return opis_bledu


# --- Technologia ---


class PythonTechnology(_base.Technology):
    """Projekty w Pythonie: implementacja kontraktu Technology.

    Po co: towar opisuje głównie roboty w Pythonie - ta klasa dostarcza rdzeniowi szkielety plików,
    a w kolejnych krokach także importy, wykrywanie technologii i punkty wejścia.
    """

    name = "python"

    def outline(
        self,
        root: str,
        path: str,
    ) -> str:
        """Czyta plik .py przez files.read_text_safe() i zwraca jego szkielet; przy błędzie składni - jedną linię z przyczyną.

        Po co: implementacja kontraktu Technology.outline() dla Pythona - kod jest tylko parsowany, nigdy
        uruchamiany, więc analiza jest bezpieczna także dla kodu, który wymaga środowiska robota.
        """
        tekst = _files.read_text_safe(os.path.join(root, path))
        try:
            drzewo = _parse_python(tekst)
        except SyntaxError as blad:
            szkielet_bledu = _syntax_error_outline(blad)
            return szkielet_bledu
        szkielet = _build_outline(drzewo, len(tekst.splitlines()))
        return szkielet


# --- Test ręczny ---

if __name__ == "__main__":
    import sys
    import tempfile

    def _outline_with_warning_count(
        technology: PythonTechnology,
        root: str,
        path: str,
    ) -> tuple[str, int]:
        """Buduje szkielet pliku i liczy ostrzeżenia SyntaxWarning, które przedostały się na zewnątrz. Zwraca (szkielet, liczba ostrzeżeń).

        Po co: dowód, że parsowanie cudzego kodu nie śmieci w konsoli - oczekiwane 0.
        """
        with warnings.catch_warnings(record=True) as zlapane:
            warnings.simplefilter("always")
            szkielet = technology.outline(root, path)
        liczba = 0
        for ostrzezenie in zlapane:
            if issubclass(ostrzezenie.category, SyntaxWarning):
                liczba += 1
        wynik = (szkielet, liczba)
        return wynik

    def _plain_parse_warning_count(
        source: str,
    ) -> int:
        """Parsuje tekst zwykłym ast.parse (bez wyciszenia) i zwraca liczbę ostrzeżeń SyntaxWarning.

        Po co: porównanie - pokazuje, że bez _parse_python ten sam plik dawałby ostrzeżenia.
        """
        with warnings.catch_warnings(record=True) as zlapane:
            warnings.simplefilter("always")
            ast.parse(source)
        liczba = 0
        for ostrzezenie in zlapane:
            if issubclass(ostrzezenie.category, SyntaxWarning):
                liczba += 1
        return liczba

    def _write_temp_files(
        directory: str,
    ) -> dict[str, str]:
        """Zapisuje w katalogu tymczasowym dwa pliki testowe i zwraca ich treść (nazwa pliku -> tekst).

        Po co: przypadki ścieżki Windows w zwykłym napisie i składni Pythona 2 bez dokładania plików do repo.
        """
        tresci = {
            "sciezka_windows.py": 'KATALOG = "C:\\nowy\\folder\\dane"\n\n\ndef start():\n    print(KATALOG + "\\d")\n',
            "python2.py": 'import os\n\nprint "start robota"\n',
        }
        for nazwa, tresc in tresci.items():
            with open(os.path.join(directory, nazwa), "w", encoding="utf-8") as plik:
                plik.write(tresc)
        return tresci

    def _collect_cases(
        temp_dir: str,
    ) -> list[tuple[str, str, str]]:
        """Zwraca przypadki testowe (opis, katalog, plik względny): pliki robotów testowych i pliki tymczasowe.

        Po co: jedna lista przypadków dla testu bez argumentów.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        robot_01 = os.path.join(katalog_testow, "01_rpa_challange_roboforge")
        robot_02 = os.path.join(katalog_testow, "02_robot_bez_frameworku")
        przypadki = [
            ("robot 01", robot_01, "Main.py"),
            ("robot 01", robot_01, "src/parabank_page.py"),
            ("robot 02", robot_02, "przetwarzanie.py"),
            ("ścieżka Windows w zwykłym napisie", temp_dir, "sciezka_windows.py"),
            ("składnia Pythona 2", temp_dir, "python2.py"),
        ]
        return przypadki

    def _print_case(
        title: str,
        root: str,
        path: str,
        outline_text: str,
        warning_count: int,
        plain_warning_count: int,
    ) -> None:
        """Wypisuje szkielet jednego pliku z nagłówkiem i liczbą ostrzeżeń SyntaxWarning.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane. plain_warning_count < 0 oznacza brak porównania.
        """
        print(f"=== {title}: {os.path.join(root, path)} ===")
        print(outline_text)
        komunikat = f"Ostrzeżenia SyntaxWarning na ekranie: {warning_count}"
        if plain_warning_count >= 0:
            komunikat += f" (zwykłe ast.parse dałoby: {plain_warning_count})"
        print(f"\n{komunikat}\n")

    def manual_test():
        """Z argumentami <katalog> <plik> - szkielet jednego pliku; bez argumentów - szkielety plików robotów testowych i plików tymczasowych.

        Po co: sprawdzenie szkieletu na prawdziwym kodzie, wyciszenia SyntaxWarning i obsługi błędu składni.
        """
        technology = PythonTechnology()
        if len(sys.argv) == 3:
            szkielet, liczba = _outline_with_warning_count(technology, sys.argv[1], sys.argv[2])
            _print_case("plik", sys.argv[1], sys.argv[2], szkielet, liczba, -1)
            return

        temp_dir = tempfile.mkdtemp()
        try:
            tresci = _write_temp_files(temp_dir)
            for opis, root, path in _collect_cases(temp_dir):
                if not os.path.exists(os.path.join(root, path)):
                    print(f"=== {opis}: brak pliku {os.path.join(root, path)} - pomijam ===\n")
                    continue
                szkielet, liczba = _outline_with_warning_count(technology, root, path)
                liczba_bez_wyciszenia = -1
                if path == "sciezka_windows.py":
                    liczba_bez_wyciszenia = _plain_parse_warning_count(tresci[path])
                _print_case(opis, root, path, szkielet, liczba, liczba_bez_wyciszenia)
        finally:
            for nazwa in os.listdir(temp_dir):
                os.remove(os.path.join(temp_dir, nazwa))
            os.rmdir(temp_dir)

    manual_test()
