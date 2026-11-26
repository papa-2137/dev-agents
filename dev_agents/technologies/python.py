"""Obsługa technologii Python: implementacja kontraktu Technology dla projektów w Pythonie.

Co robi: na tym etapie dla pliku .py buduje:
    - szkielet (outline) - spis treści bez ciał funkcji: liczba linii, opis modułu, stałe, zmienne modułu,
      kod wykonywany poza funkcjami, klasy i funkcje z sygnaturami, pierwszym akapitem docstringu i zakresem
      linii; pokazuje strukturę także kodu "spaghetti" (funkcja na kilkaset linii, logika luzem),
    - zależności (imports) w trzech grupach: pliki projektu (ścieżki względne - z nich powstaje graf
      zależności), biblioteki zewnętrzne i biblioteka standardowa (nazwy modułów),
    - szkielet sterowania jednej funkcji (control_outline) - same rozgałęzienia, pętle, obsługa błędów, wyjścia
      i wywołania funkcji oraz modułów, z liniami, bez treści gałęzi; prosty blok sklejony w jedną linię,
    - miary złożoności każdej funkcji (metrics) - długość, głębokość zagnieżdżenia, rozgałęzienia,
oraz rozpoznaje projekt Pythona (detect, is_source) i jego punkty wejścia (find_entrypoints).

Dlaczego istnieje: cała wiedza o Pythonie siedzi w tym module, a rdzeń towaru woła tylko metody kontraktu
(AGENTS.md, reguła 7). To jedyny moduł towaru, który importuje `ast` (parser Pythona z biblioteki
standardowej). Kod analizowanego projektu jest tylko czytany i parsowany - nigdy importowany ani
uruchamiany. Cały cudzy kod parsuje jedna funkcja (_parse_python), która wycisza SyntaxWarning:
Python 3.12+ ostrzega przy każdym napisie typu "C:\\folder" bez r, a w kodzie robotów takich napisów
jest pełno - na mieście ostrzeżenia zasypywały ekran.

Rola: moduł technologii, używany przez rdzeń towaru przez kontrakt z base.py.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.technologies.python
        szkielety i importy: robot 01 (main.py, src/parabank_page.py), robot 02 (przetwarzanie.py), plik ze
        ścieżką Windows w zwykłym napisie (z liczbą ostrzeżeń - oczekiwane 0), pakiet tymczasowy z importem
        względnym, importami w funkcji i w try oraz modułem usuniętym z biblioteki standardowej, plik
        w składni Pythona 2 (linia z przyczyną zamiast szkieletu, puste grupy importów); potem szkielet
        sterowania run() i kodu poza funkcjami robota 02, miary robotów 01 i 02, na końcu rozpoznanie
        projektu (detect, pliki źródłowe, punkty wejścia) robotów 01 i 02 oraz katalogów tymczasowych
    python -m dev_agents.technologies.python <katalog projektu> <plik względny do katalogu>
        szkielet, importy i miary jednego, dowolnego pliku
    python -m dev_agents.technologies.python <katalog projektu> <plik> <funkcja>
        szkielet sterowania funkcji ("run", "Klasa.metoda"; "" = kod poza funkcjami)
"""

import ast
import os
import sys
import warnings

import dev_agents.files as _files
import dev_agents.schemas as _schemas
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


# --- Importy ---


def _module_file(
    root: str,
    module: str,
) -> str:
    """Zwraca ścieżkę względną pliku projektu dla pełnej nazwy modułu (np. 'src.report' -> 'src/report.py', pakiet -> '<pakiet>/__init__.py'); "" gdy takiego pliku nie ma.

    Po co: kontrakt każe zwracać zależności wewnętrzne jako ścieżki plików - dzięki temu graf zależności
    w rdzeniu łączy pliki i nie musi wiedzieć, jak Python zamienia nazwy modułów na pliki.

    Uwaga: pakiet bez __init__.py (namespace package) nie ma pliku - import samego takiego pakietu nie daje
    ścieżki; importy jego modułów (np. 'src.report') dają.
    """
    sciezka_bazowa = "/".join(module.split("."))
    kandydaci = [sciezka_bazowa + ".py", sciezka_bazowa + "/__init__.py"]
    for kandydat in kandydaci:
        if os.path.isfile(os.path.join(root, kandydat)):
            return kandydat
    return ""


def _is_project_module(
    root: str,
    module: str,
) -> bool:
    """Sprawdza, czy moduł o podanej pełnej nazwie (np. 'src.report') istnieje w katalogu projektu jako plik .py albo katalog.

    Po co: od tego zależy, czy import trafi do plików projektu, czy do bibliotek.

    Uwaga: nie rozpoznaje modułów instalowanych w trybie edytowalnym (pip install -e) - takie moduły trafiają
    do bibliotek zewnętrznych.
    """
    sciezka_bazowa = os.path.join(root, *module.split("."))
    czy_istnieje = os.path.isfile(sciezka_bazowa + ".py") or os.path.isdir(sciezka_bazowa)
    return czy_istnieje


def _resolve_relative(
    path: str,
    level: int,
    module: str | None,
) -> str:
    """Zamienia import względny na pełną nazwę modułu, np. w src/x.py: 'from .report import y' -> 'src.report'.

    Po co: jednolite, pełne nazwy modułów niezależnie od tego, czy autor kodu pisał importy względne, czy bezwzględne.
    """
    czesci_pakietu = []
    katalog = os.path.dirname(path.replace("\\", "/"))
    if katalog:
        czesci_pakietu = katalog.split("/")
    if level > 1:
        czesci_pakietu = czesci_pakietu[: len(czesci_pakietu) - (level - 1)]
    if module:
        czesci_pakietu = czesci_pakietu + module.split(".")
    niepuste = []
    for czesc in czesci_pakietu:
        if czesc:
            niepuste.append(czesc)
    pelna_nazwa = ".".join(niepuste)
    return pelna_nazwa


def _imported_modules(
    tree: ast.Module,
    root: str,
    path: str,
) -> list[tuple[str, bool]]:
    """Zbiera wszystkie importy pliku (także wewnątrz funkcji i try/except) jako pary (pełna nazwa modułu, czy względny).

    Po co: stary kod RPA często importuje wewnątrz funkcji albo warunkowo - przejście po całym drzewie łapie
    te importy. Przy 'from pakiet import nazwa' dokłada '.nazwa' tylko wtedy, gdy to podmoduł istniejący
    w projekcie (np. 'from src import report' -> 'src.report'); funkcji i klas z importu nie traktuje jak modułów.
    """
    moduly = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                moduly.append((alias.name, False))
        elif isinstance(node, ast.ImportFrom):
            czy_wzgledny = node.level > 0
            baza = ""
            if node.module:
                baza = node.module
            if czy_wzgledny:
                baza = _resolve_relative(path, node.level, node.module)
            podmoduly_projektu = []
            for alias in node.names:
                nazwa = alias.name
                if baza:
                    nazwa = f"{baza}.{alias.name}"
                if _is_project_module(root, nazwa):
                    podmoduly_projektu.append(nazwa)
            if len(podmoduly_projektu) > 0:
                for nazwa in podmoduly_projektu:
                    moduly.append((nazwa, czy_wzgledny))
            elif baza:
                moduly.append((baza, czy_wzgledny))
    return moduly


def _classify_module(
    root: str,
    module: str,
    is_relative: bool,
) -> str:
    """Przypisuje moduł do grupy: internal (z projektu), stdlib (biblioteka standardowa) albo external (reszta).

    Po co: podział oddziela prawdziwe zależności do zainstalowania (external) od biblioteki standardowej
    i od współpracy między plikami projektu - to trafia wprost do przewodnika.

    Uwaga: najpierw sprawdzany jest projekt - własny plik o nazwie modułu standardowego (np. logging.py)
    przesłania moduł standardowy. Grupę stdlib wyznacza lista Pythona, na którym działa towar, uzupełniona
    o moduły usunięte w Pythonie 3.12-3.13 - robot działający na starszym Pythonie może ich używać,
    a nie są to zależności do zainstalowania.
    """
    usuniete_ze_stdlib = [
        "aifc", "asynchat", "asyncore", "audioop", "cgi", "cgitb", "chunk", "crypt", "distutils", "imghdr",
        "imp", "lib2to3", "mailcap", "msilib", "nis", "nntplib", "ossaudiodev", "pipes", "smtpd", "sndhdr",
        "spwd", "sunau", "telnetlib", "uu", "xdrlib",
    ]
    pakiet_glowny = module.split(".")[0]
    if is_relative or _is_project_module(root, pakiet_glowny):
        return "internal"
    if pakiet_glowny in sys.stdlib_module_names or pakiet_glowny in usuniete_ze_stdlib:
        return "stdlib"
    return "external"


# --- Szkielet sterowania i miary złożoności ---


def _functions(
    body: list,
    prefix: str = "",
) -> list[tuple[str, ast.AST]]:
    """Zwraca funkcje i metody z ciała modułu albo klasy jako pary (nazwa, węzeł); metody jako "Klasa.metoda", także w klasach zagnieżdżonych.

    Po co: jedna lista funkcji dla miar i dla wyszukiwania funkcji po nazwie w szkielecie sterowania.

    Uwaga: funkcje zdefiniowane wewnątrz innych funkcji nie są osobnymi pozycjami - liczą się do funkcji, w której leżą.
    """
    funkcje = []
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funkcje.append((prefix + node.name, node))
        elif isinstance(node, ast.ClassDef):
            funkcje.extend(_functions(node.body, prefix + node.name + "."))
    return funkcje


def _imported_names(
    tree: ast.Module,
) -> list[str]:
    """Zwraca nazwy wprowadzone importami w pliku (moduły i importowane nazwy, z uwzględnieniem aliasów).

    Po co: szkielet sterowania pokazuje wywołania funkcji modułów (np. shutil.move, requests.post), a pomija
    metody na danych (np. lista.append) - rozpoznaje je po tym, czy początek wywołania to importowana nazwa.
    """
    nazwy = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                nazwa = alias.name
                if alias.asname:
                    nazwa = alias.asname
                nazwy.append(nazwa.split(".")[0])
    return nazwy


def _call_name(
    call: ast.Call,
    module_names: list[str],
) -> str:
    """Zwraca nazwę wywołania do szkieletu sterowania albo "", gdy wywołanie jest pomijane.

    Po co: pokazujemy wywołania funkcji po nazwie (log, open) oraz funkcji modułów i metod obiektu
    (shutil.move, requests.post, self.page.fill) - to kontakty z systemami i kroki procesu; metody na danych
    (wiersz.strip, lista.append) to szum i są pomijane.
    """
    funkcja = call.func
    if isinstance(funkcja, ast.Name):
        return funkcja.id
    poczatek = funkcja
    while isinstance(poczatek, ast.Attribute):
        poczatek = poczatek.value
    if isinstance(poczatek, ast.Name):
        if poczatek.id in module_names or poczatek.id == "self":
            nazwa = ast.unparse(funkcja)
            return nazwa
    return ""


def _statement_calls(
    statements: list,
    module_names: list[str],
) -> list[str]:
    """Zwraca nazwy wywołań stojących jako osobna instrukcja albo prawa strona przypisania, bez powtórzeń, w kolejności występowania.

    Po co: wywołania schowane w argumentach i warunkach nie są osobnymi krokami - warunki widać w liniach if.
    """
    nazwy = []
    for instrukcja in statements:
        wywolanie = None
        if isinstance(instrukcja, ast.Expr) and isinstance(instrukcja.value, ast.Call):
            wywolanie = instrukcja.value
        elif isinstance(instrukcja, (ast.Assign, ast.AugAssign, ast.AnnAssign)) and isinstance(instrukcja.value, ast.Call):
            wywolanie = instrukcja.value
        if wywolanie is None:
            continue
        nazwa = _call_name(wywolanie, module_names)
        if nazwa and nazwa not in nazwy:
            nazwy.append(nazwa)
    return nazwy


def _short(
    node,
    max_length: int = 60,
) -> str:
    """Zwraca kod wyrażenia (np. warunku) jako tekst skrócony do max_length znaków z "..." na końcu.

    Po co: warunki bywają bardzo długie - w szkielecie wystarczy początek, pełny warunek jest w kodzie pod podaną linią.
    """
    tekst = ast.unparse(node)
    if len(tekst) > max_length:
        tekst = tekst[:max_length].rstrip() + "..."
    return tekst


def _is_control(
    node,
) -> bool:
    """Sprawdza, czy instrukcja jest strukturą sterującą z własnymi blokami (if, pętla, try, with, match).

    Po co: tylko takie instrukcje dostają w szkielecie osobną linię z wcięciem; reszta jest sklejana.
    """
    struktury = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.TryStar, ast.With, ast.AsyncWith, ast.Match)
    czy_struktura = isinstance(node, struktury)
    return czy_struktura


def _jump_text(
    node,
) -> str:
    """Zwraca opis instrukcji wyjścia (return, raise z nazwą wyjątku, break, continue) albo "", gdy to nie wyjście.

    Po co: wyjścia z bloku pokazują ścieżki błędów i pominięć - kluczowe dla diagramu i opisu procesu.
    """
    if isinstance(node, ast.Return):
        return "return"
    if isinstance(node, ast.Break):
        return "break"
    if isinstance(node, ast.Continue):
        return "continue"
    if isinstance(node, ast.Raise):
        if isinstance(node.exc, ast.Call):
            opis_raise = f"raise {ast.unparse(node.exc.func)}"
            return opis_raise
        if node.exc is not None:
            opis_raise = f"raise {ast.unparse(node.exc)}"
            return opis_raise
        return "raise"
    return ""


def _block_has_control(
    body: list,
) -> bool:
    """Sprawdza, czy blok zawiera choć jedną strukturę sterującą.

    Po co: blok bez struktur sterujących jest pokazywany w jednej linii z nagłówkiem - szkielet jest krótszy.
    """
    for instrukcja in body:
        if _is_control(instrukcja):
            return True
    return False


def _block_suffix(
    body: list,
    module_names: list[str],
) -> str:
    """Zwraca dopisek do linii prostego bloku: wywołania i wyjście na końcu, np. "  [log, shutil.move; -> continue]"; "" gdy nic do pokazania.

    Po co: prosty blok (np. walidacja z continue) mieści się w jednej linii zamiast kilku.
    """
    czesci = []
    wywolania = _statement_calls(body, module_names)
    if len(wywolania) > 0:
        czesci.append(", ".join(wywolania))
    if len(body) > 0:
        wyjscie = _jump_text(body[-1])
        if wyjscie:
            czesci.append("-> " + wyjscie)
    dopisek = ""
    if len(czesci) > 0:
        dopisek = "  [" + "; ".join(czesci) + "]"
    return dopisek


def _block_lines(
    line: int,
    header: str,
    body: list,
    indent: str,
    module_names: list[str],
) -> list[str]:
    """Zwraca linie szkieletu jednego bloku: prosty blok - jedna linia z dopiskiem; blok ze strukturami - nagłówek i wcięta zawartość.

    Po co: wspólny sposób wypisywania każdego bloku (if, pętla, try, except, with, case).
    """
    if not _block_has_control(body):
        linie_prostego = [f"{indent}{line}: {header}{_block_suffix(body, module_names)}"]
        return linie_prostego
    linie = [f"{indent}{line}: {header}"]
    linie.extend(_control_lines(body, indent + "  ", module_names))
    return linie


def _if_lines(
    node: ast.If,
    indent: str,
    module_names: list[str],
) -> list[str]:
    """Zwraca linie szkieletu instrukcji if z łańcuchem elif i blokiem else, wszystkie na jednym poziomie wcięcia.

    Po co: łańcuch elif czyta się jak lista przypadków, a nie jak coraz głębsze zagnieżdżenie.
    """
    linie = _block_lines(node.lineno, "if " + _short(node.test), node.body, indent, module_names)
    dalej = node.orelse
    while len(dalej) == 1 and isinstance(dalej[0], ast.If):
        elif_node = dalej[0]
        linie.extend(_block_lines(elif_node.lineno, "elif " + _short(elif_node.test), elif_node.body, indent, module_names))
        dalej = elif_node.orelse
    if len(dalej) > 0:
        linie.extend(_block_lines(dalej[0].lineno, "else", dalej, indent, module_names))
    return linie


def _try_lines(
    node,
    indent: str,
    module_names: list[str],
) -> list[str]:
    """Zwraca linie szkieletu instrukcji try: blok try, każdy except z typem wyjątku, else i finally.

    Po co: obsługa błędów to osobne ścieżki procesu - każdy except jest widoczny z linią i typem wyjątku.
    """
    linie = _block_lines(node.lineno, "try", node.body, indent, module_names)
    for obsluga in node.handlers:
        naglowek = "except"
        if obsluga.type is not None:
            naglowek = "except " + _short(obsluga.type)
        linie.extend(_block_lines(obsluga.lineno, naglowek, obsluga.body, indent, module_names))
    if len(node.orelse) > 0:
        linie.extend(_block_lines(node.orelse[0].lineno, "else", node.orelse, indent, module_names))
    if len(node.finalbody) > 0:
        linie.extend(_block_lines(node.finalbody[0].lineno, "finally", node.finalbody, indent, module_names))
    return linie


def _calls_line(
    statements: list,
    indent: str,
    module_names: list[str],
) -> list[str]:
    """Zwraca jedną linię z wywołaniami ciągu zwykłych instrukcji (numer linii pierwszej z nich) albo pustą listę, gdy wywołań brak.

    Po co: kolejne zwykłe instrukcje między strukturami sterującymi są sklejane w jedną linię - kroki procesu
    bez treści przypisań.
    """
    linie = []
    wywolania = _statement_calls(statements, module_names)
    if len(wywolania) > 0:
        linie.append(f"{indent}{statements[0].lineno}: {', '.join(wywolania)}")
    return linie


def _control_lines(
    body: list,
    indent: str,
    module_names: list[str],
) -> list[str]:
    """Zwraca linie szkieletu sterowania ciągu instrukcji: struktury sterujące z wcięciem, wyjścia i sklejone wywołania.

    Po co: rdzeń szkieletu sterowania - przechodzi bloki rekurencyjnie i pomija treść gałęzi.
    """
    linie = []
    zwykle = []
    for node in body:
        wyjscie = _jump_text(node)
        czy_definicja = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        if _is_control(node) or wyjscie or czy_definicja:
            linie.extend(_calls_line(zwykle, indent, module_names))
            zwykle = []
        if isinstance(node, ast.If):
            linie.extend(_if_lines(node, indent, module_names))
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            naglowek = f"for {_short(node.target, 30)} in {_short(node.iter, 50)}"
            linie.extend(_block_lines(node.lineno, naglowek, node.body, indent, module_names))
            if len(node.orelse) > 0:
                linie.extend(_block_lines(node.orelse[0].lineno, "else (pętla bez break)", node.orelse, indent, module_names))
        elif isinstance(node, ast.While):
            linie.extend(_block_lines(node.lineno, "while " + _short(node.test), node.body, indent, module_names))
            if len(node.orelse) > 0:
                linie.extend(_block_lines(node.orelse[0].lineno, "else (pętla bez break)", node.orelse, indent, module_names))
        elif isinstance(node, (ast.Try, ast.TryStar)):
            linie.extend(_try_lines(node, indent, module_names))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            konteksty = []
            for element in node.items:
                konteksty.append(_short(element.context_expr, 40))
            linie.extend(_block_lines(node.lineno, "with " + ", ".join(konteksty), node.body, indent, module_names))
        elif isinstance(node, ast.Match):
            linie.append(f"{indent}{node.lineno}: match {_short(node.subject)}")
            for przypadek in node.cases:
                naglowek = "case " + _short(przypadek.pattern, 40)
                linie.extend(_block_lines(przypadek.pattern.lineno, naglowek, przypadek.body, indent + "  ", module_names))
        elif wyjscie:
            linie.append(f"{indent}{node.lineno}: {wyjscie}")
        elif czy_definicja:
            linie.append(f"{indent}{node.lineno}: def/class {node.name} (definicja zagnieżdżona)")
        else:
            zwykle.append(node)
    linie.extend(_calls_line(zwykle, indent, module_names))
    return linie


def _max_depth(
    statements: list,
    depth: int,
) -> int:
    """Zwraca najgłębsze zagnieżdżenie bloków (if, pętle, try, with, match) w ciągu instrukcji; elif liczy się na poziomie swojego if.

    Po co: głębokie zagnieżdżenie to najczęstsza przyczyna błędów przy zmianach w kodzie "spaghetti".
    """
    najglebiej = depth
    for node in statements:
        bloki = []
        bloki_na_tym_poziomie = []
        if isinstance(node, ast.If):
            bloki.append(node.body)
            if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                bloki_na_tym_poziomie.append(node.orelse)
            elif len(node.orelse) > 0:
                bloki.append(node.orelse)
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            bloki.append(node.body)
            bloki.append(node.orelse)
        elif isinstance(node, (ast.Try, ast.TryStar)):
            bloki.append(node.body)
            for obsluga in node.handlers:
                bloki.append(obsluga.body)
            bloki.append(node.orelse)
            bloki.append(node.finalbody)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            bloki.append(node.body)
        elif isinstance(node, ast.Match):
            for przypadek in node.cases:
                bloki.append(przypadek.body)
        for blok in bloki:
            najglebiej = max(najglebiej, _max_depth(blok, depth + 1))
        for blok in bloki_na_tym_poziomie:
            najglebiej = max(najglebiej, _max_depth(blok, depth))
    return najglebiej


def _count_branches(
    statements: list,
) -> int:
    """Liczy punkty decyzji w ciągu instrukcji: if/elif, pętle, except, wyrażenia warunkowe, operatory and/or, warunki w wyrażeniach listowych, przypadki match.

    Po co: liczba rozgałęzień (jak w złożoności cyklomatycznej) mówi, ile ścieżek trzeba przetestować i opisać.
    """
    licznik = 0
    for instrukcja in statements:
        for node in ast.walk(instrukcja):
            if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.match_case)):
                licznik += 1
            elif isinstance(node, ast.BoolOp):
                licznik += len(node.values) - 1
            elif isinstance(node, ast.comprehension):
                licznik += len(node.ifs)
    return licznik


def _module_code_metrics(
    tree: ast.Module,
    path: str,
) -> list[_schemas.FunctionMetrics]:
    """Zwraca miary kodu poza funkcjami jako jedną pozycję "<kod poza funkcjami>" albo pustą listę, gdy takiego kodu nie ma.

    Po co: w skryptach "spaghetti" logika bywa luzem na poziomie modułu - też musi trafić do miar.
    """
    odcinki = _module_level_segments(tree)
    miary = []
    if len(odcinki) == 0:
        return miary
    instrukcje = _flatten_segments(odcinki)
    liczba_linii = 0
    for odcinek in odcinki:
        liczba_linii += odcinek[-1].end_lineno - odcinek[0].lineno + 1
    miary.append(
        _schemas.FunctionMetrics(
            path=path,
            name="<kod poza funkcjami>",
            start_line=odcinki[0][0].lineno,
            end_line=odcinki[-1][-1].end_lineno,
            lines=liczba_linii,
            max_depth=_max_depth(instrukcje, 0),
            branches=_count_branches(instrukcje),
        )
    )
    return miary


# --- Punkty wejścia ---


def _is_main_guard(
    node,
) -> bool:
    """Sprawdza, czy instrukcja to blok `if __name__ == "__main__":` (strony porównania w dowolnej kolejności).

    Po co: taki blok oznacza, że plik jest przeznaczony do uruchamiania - główna wskazówka, od którego pliku
    startuje projekt.
    """
    if not isinstance(node, ast.If) or not isinstance(node.test, ast.Compare):
        return False
    porownanie = node.test
    if len(porownanie.ops) != 1 or not isinstance(porownanie.ops[0], ast.Eq):
        return False
    czy_name = False
    czy_main = False
    for strona in [porownanie.left, porownanie.comparators[0]]:
        if isinstance(strona, ast.Name) and strona.id == "__name__":
            czy_name = True
        if isinstance(strona, ast.Constant) and strona.value == "__main__":
            czy_main = True
    czy_blok_main = czy_name and czy_main
    return czy_blok_main


def _has_main_guard(
    root: str,
    path: str,
) -> bool:
    """Sprawdza, czy plik .py ma na poziomie modułu blok `if __name__ == "__main__":`; plik z błędem składni - False.

    Po co: kod jest tylko parsowany, nie uruchamiany - bezpieczne wykrywanie punktów wejścia także w projektach,
    które wymagają środowiska robota (przeglądarki, aplikacji, haseł).
    """
    tekst = _files.read_text_safe(os.path.join(root, path))
    try:
        drzewo = _parse_python(tekst)
    except SyntaxError:
        return False
    for node in drzewo.body:
        if _is_main_guard(node):
            return True
    return False


def _entrypoint_sort_key(
    path: str,
) -> tuple:
    """Zwraca klucz sortowania punktów wejścia: najpierw main.py i __main__.py, potem pliki płytsze, potem alfabetycznie.

    Po co: moduły z własnym blokiem testowym też są punktami wejścia - właściwy start projektu ma być na
    początku listy.

    Uwaga: nazwy porównywane bez względu na wielkość liter - na Windows Main.py i main.py to ten sam plik.
    """
    nazwa = os.path.basename(path).lower()
    priorytet = 1
    if nazwa in ("main.py", "__main__.py"):
        priorytet = 0
    glebokosc = len(path.replace("\\", "/").split("/"))
    klucz = (priorytet, glebokosc, path.lower())
    return klucz


# --- Technologia ---


class PythonTechnology(_base.Technology):
    """Projekty w Pythonie: implementacja kontraktu Technology.

    Po co: towar opisuje głównie roboty w Pythonie - ta klasa dostarcza rdzeniowi szkielety plików, importy,
    szkielety sterowania, miary złożoności, rozpoznanie projektu i punkty wejścia.
    """

    name = "python"

    def detect(
        self,
        root: str,
        files: list[str],
    ) -> bool:
        """Uznaje projekt za pythonowy, gdy jest w nim choć jeden plik źródłowy Pythona (.py, .pyw).

        Po co: implementacja kontraktu Technology.detect() - na tej podstawie rejestr technologii wybierze
        obsługę Pythona dla całego projektu.

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

        Po co: implementacja kontraktu Technology.is_source() - tylko te pliki trafią do analityków jako
        jednostki kodu; konfiguracja, dane i binarki są opisywane metadanymi.
        """
        czy_kod = path.lower().endswith((".py", ".pyw"))
        return czy_kod

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Zwraca punkty wejścia: pliki źródłowe z blokiem `if __name__ == "__main__":` oraz pliki main.py i __main__.py; posortowane - main.py/__main__.py, potem płytsze, potem alfabetycznie.

        Po co: implementacja kontraktu Technology.find_entrypoints() - przewodnik zaczyna opis od miejsca
        uruchomienia. Bloki testowe w zwykłych modułach też są wykrywane, dlatego kolejność wskazuje
        najbardziej prawdopodobny start na początku; prawdziwe uruchomienia z plików .bat/.ps1 dokłada skaner.
        """
        punkty = []
        for path in files:
            if not self.is_source(path):
                continue
            czy_nazwa_main = os.path.basename(path).lower() in ("main.py", "__main__.py")
            if czy_nazwa_main or _has_main_guard(root, path):
                punkty.append(path)
        punkty_wejscia = sorted(punkty, key=_entrypoint_sort_key)
        return punkty_wejscia

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

    def imports(
        self,
        root: str,
        path: str,
    ) -> dict[str, list[str]]:
        """Czyta plik .py i zwraca jego zależności: internal - ścieżki względne plików projektu, external i stdlib - nazwy modułów; bez powtórzeń, posortowane.

        Po co: implementacja kontraktu Technology.imports() dla Pythona - z niej powstaje graf zależności,
        wykrywanie frameworków i sekcja zależności w przewodniku.

        Uwaga: przy błędzie składni zwraca puste grupy (przyczynę pokazuje outline() tego pliku). Nie wykrywa
        importów dynamicznych (importlib.import_module, __import__) - ich nazwy znane są dopiero po
        uruchomieniu kodu.
        """
        grupy = {"internal": [], "external": [], "stdlib": []}
        tekst = _files.read_text_safe(os.path.join(root, path))
        try:
            drzewo = _parse_python(tekst)
        except SyntaxError:
            return grupy

        for modul, czy_wzgledny in _imported_modules(drzewo, root, path):
            grupa = _classify_module(root, modul, czy_wzgledny)
            wpis = modul
            if grupa == "internal":
                wpis = _module_file(root, modul)
                if wpis == "":
                    continue
            if wpis not in grupy[grupa]:
                grupy[grupa].append(wpis)

        importy_w_grupach = {}
        for nazwa_grupy, wpisy in grupy.items():
            importy_w_grupach[nazwa_grupy] = sorted(wpisy)
        return importy_w_grupach

    def control_outline(
        self,
        root: str,
        path: str,
        function_name: str,
    ) -> str:
        """Zwraca szkielet sterowania funkcji ("run", "Klasa.metoda") albo kodu poza funkcjami (""): nagłówek z zakresem linii, potem struktury sterujące, wyjścia i wywołania.

        Po co: implementacja kontraktu Technology.control_outline() dla Pythona - mapa logiki długiej funkcji
        w ok. 1/3 jej długości, ze wszystkimi poziomami warunków i numerami linii.

        Uwaga: przy błędzie składni zwraca linię z przyczyną; przy nieznanej nazwie - linię z listą dostępnych funkcji.
        """
        tekst = _files.read_text_safe(os.path.join(root, path))
        try:
            drzewo = _parse_python(tekst)
        except SyntaxError as blad:
            szkielet_bledu = _syntax_error_outline(blad)
            return szkielet_bledu
        nazwy_modulow = _imported_names(drzewo)

        if function_name == "":
            odcinki = _module_level_segments(drzewo)
            linie = [_describe_module_code(odcinki)]
            linie.extend(_control_lines(_flatten_segments(odcinki), "  ", nazwy_modulow))
            szkielet_modulu = "\n".join(linie)
            return szkielet_modulu

        dostepne = []
        for nazwa, node in _functions(drzewo.body):
            dostepne.append(nazwa)
            if nazwa == function_name:
                linie = [f"def {nazwa}({ast.unparse(node.args)})  {_line_range(node)}"]
                linie.extend(_control_lines(node.body, "  ", nazwy_modulow))
                szkielet_funkcji = "\n".join(linie)
                return szkielet_funkcji
        komunikat = f"Brak funkcji '{function_name}' w pliku {path}. Dostępne: {', '.join(dostepne)}"
        return komunikat

    def metrics(
        self,
        root: str,
        path: str,
    ) -> list[_schemas.FunctionMetrics]:
        """Zwraca miary złożoności kodu poza funkcjami (jeśli jest) i każdej funkcji oraz metody pliku, w kolejności w pliku.

        Po co: implementacja kontraktu Technology.metrics() dla Pythona - liczby do tabeli "Ryzykowne miejsca"
        i do decyzji o analizie długich funkcji po kawałkach.

        Uwaga: przy błędzie składni zwraca pustą listę (przyczynę pokazuje outline() tego pliku).
        """
        tekst = _files.read_text_safe(os.path.join(root, path))
        try:
            drzewo = _parse_python(tekst)
        except SyntaxError:
            miary_bledu = []
            return miary_bledu
        miary = _module_code_metrics(drzewo, path)
        for nazwa, node in _functions(drzewo.body):
            miary.append(
                _schemas.FunctionMetrics(
                    path=path,
                    name=nazwa,
                    start_line=node.lineno,
                    end_line=node.end_lineno,
                    lines=node.end_lineno - node.lineno + 1,
                    max_depth=_max_depth(node.body, 0),
                    branches=_count_branches(node.body),
                )
            )
        return miary


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
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
        """Zapisuje w katalogu tymczasowym pliki testowe i zwraca ich treść (ścieżka względna -> tekst).

        Po co: przypadki ścieżki Windows w zwykłym napisie, importów w pakiecie (względny, w funkcji, w try,
        moduł usunięty z biblioteki standardowej), modułu z blokiem __main__, składni Pythona 2 i katalogu
        bez kodu - bez dokładania plików do repo.
        """
        tresci = {
            "sciezka_windows.py": 'KATALOG = "C:\\nowy\\folder\\dane"\n\n\ndef start():\n    print(KATALOG + "\\d")\n',
            "pakiet/__init__.py": "",
            "pakiet/narzedzia.py": "def pomoc():\n    return 1\n\n\nif __name__ == \"__main__\":\n    print(pomoc())\n",
            "pakiet/glowny.py": (
                "import os\n"
                "from .narzedzia import pomoc\n"
                "from . import narzedzia\n"
                "\n"
                "try:\n"
                "    import telnetlib\n"
                "except ImportError:\n"
                "    telnetlib = None\n"
                "\n"
                "\n"
                "def wyslij():\n"
                "    import requests\n"
                "    return requests\n"
            ),
            "python2.py": 'import os\n\nprint "start robota"\n',
            "bez_kodu/dane.txt": "tylko dane\n",
        }
        for sciezka, tresc in tresci.items():
            pelna_sciezka = os.path.join(directory, sciezka)
            os.makedirs(os.path.dirname(pelna_sciezka), exist_ok=True)
            with open(pelna_sciezka, "w", encoding="utf-8") as plik:
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
            ("robot 01", robot_01, "main.py"),
            ("robot 01", robot_01, "src/parabank_page.py"),
            ("robot 02", robot_02, "przetwarzanie.py"),
            ("ścieżka Windows w zwykłym napisie", temp_dir, "sciezka_windows.py"),
            ("pakiet tymczasowy", temp_dir, "pakiet/glowny.py"),
            ("składnia Pythona 2", temp_dir, "python2.py"),
        ]
        return przypadki

    def _print_case(
        title: str,
        root: str,
        path: str,
        outline_text: str,
        imports: dict[str, list[str]],
        warning_count: int,
        plain_warning_count: int,
    ) -> None:
        """Wypisuje szkielet i importy jednego pliku z nagłówkiem oraz liczbą ostrzeżeń SyntaxWarning.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane. plain_warning_count < 0 oznacza brak porównania.
        """
        print(f"=== {title}: {os.path.join(root, path)} ===")
        print(outline_text)
        print("\nImporty:")
        for grupa, wpisy in imports.items():
            opis_wpisow = "(brak)"
            if len(wpisy) > 0:
                opis_wpisow = ", ".join(wpisy)
            print(f"  {grupa}: {opis_wpisow}")
        komunikat = f"Ostrzeżenia SyntaxWarning na ekranie: {warning_count}"
        if plain_warning_count >= 0:
            komunikat += f" (zwykłe ast.parse dałoby: {plain_warning_count})"
        print(f"\n{komunikat}\n")

    def _print_control_outline(
        title: str,
        outline_text: str,
        function_lines: int,
    ) -> None:
        """Wypisuje szkielet sterowania z nagłówkiem i stosunkiem jego długości do długości funkcji.

        Po co: od razu widać, ile razy szkielet jest krótszy od kodu; function_lines <= 0 oznacza brak porównania.
        """
        print(f"=== Szkielet sterowania: {title} ===")
        print(outline_text)
        liczba_linii_szkieletu = len(outline_text.splitlines())
        if function_lines > 0:
            print(f"\nLinii szkieletu: {liczba_linii_szkieletu} z {function_lines} linii kodu\n")
        else:
            print(f"\nLinii szkieletu: {liczba_linii_szkieletu}\n")

    def _print_metrics(
        title: str,
        metrics: list,
    ) -> None:
        """Wypisuje miary złożoności jako tabelę: nazwa, linie od-do, długość, głębokość, rozgałęzienia.

        Po co: czytelne porównanie funkcji pliku; tylko formatuje gotowe dane.
        """
        print(f"=== Miary: {title} ===")
        if len(metrics) == 0:
            print("(brak danych)\n")
            return
        print(f"{'funkcja':<40} {'linie':<10} {'długość':>8} {'głębokość':>10} {'rozgałęzienia':>14}")
        for miara in metrics:
            zakres = f"{miara.start_line}-{miara.end_line}"
            print(f"{miara.name:<40} {zakres:<10} {miara.lines:>8} {miara.max_depth:>10} {miara.branches:>14}")
        print()

    def _function_length(
        metrics: list,
        name: str,
    ) -> int:
        """Zwraca liczbę linii funkcji o podanej nazwie z listy miar albo 0, gdy jej nie ma.

        Po co: do porównania długości szkieletu sterowania z długością funkcji.
        """
        for miara in metrics:
            if miara.name == name:
                return miara.lines
        return 0

    def _run_complexity_cases(
        technology: PythonTechnology,
        temp_dir: str,
    ) -> None:
        """Wypisuje szkielet sterowania run() i kodu poza funkcjami robota 02 oraz miary plików robotów 01 i 02 i pliku w Pythonie 2.

        Po co: sprawdzenie szkieletu sterowania i miar na kodzie "spaghetti" i na kodzie uporządkowanym.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        robot_01 = os.path.join(katalog_testow, "01_rpa_challange_roboforge")
        robot_02 = os.path.join(katalog_testow, "02_robot_bez_frameworku")
        if os.path.exists(os.path.join(robot_02, "przetwarzanie.py")):
            miary_02 = technology.metrics(robot_02, "przetwarzanie.py")
            _print_control_outline("robot 02 przetwarzanie.py, run()", technology.control_outline(robot_02, "przetwarzanie.py", "run"), _function_length(miary_02, "run"))
            _print_control_outline("robot 02 przetwarzanie.py, kod poza funkcjami", technology.control_outline(robot_02, "przetwarzanie.py", ""), -1)
        przypadki_miar = [
            ("robot 01 main.py", robot_01, "main.py"),
            ("robot 01 src/parabank_page.py", robot_01, "src/parabank_page.py"),
            ("robot 02 przetwarzanie.py", robot_02, "przetwarzanie.py"),
            ("robot 02 raport.py", robot_02, "raport.py"),
            ("składnia Pythona 2", temp_dir, "python2.py"),
        ]
        for opis, root, path in przypadki_miar:
            if not os.path.exists(os.path.join(root, path)):
                print(f"=== Miary: {opis} - brak pliku, pomijam ===\n")
                continue
            _print_metrics(opis, technology.metrics(root, path))

    def _list_project_files(
        root: str,
    ) -> list[str]:
        """Zwraca ścieżki względne (separator "/") wszystkich plików katalogu, z pominięciem środowisk wirtualnych (katalog z pyvenv.cfg) i __pycache__.

        Po co: lista plików do testu detect/find_entrypoints, zanim powstanie skaner (krok 18) - bez tysięcy
        plików z test-venv robota 01. Zwraca tylko nazwy, nie otwiera plików.
        """
        pliki = []
        for katalog, podkatalogi, nazwy_plikow in os.walk(root):
            zostaw = []
            for podkatalog in podkatalogi:
                czy_venv = os.path.isfile(os.path.join(katalog, podkatalog, "pyvenv.cfg"))
                if not czy_venv and podkatalog != "__pycache__":
                    zostaw.append(podkatalog)
            podkatalogi[:] = zostaw
            for nazwa in nazwy_plikow:
                sciezka = os.path.relpath(os.path.join(katalog, nazwa), root).replace("\\", "/")
                pliki.append(sciezka)
        pliki.sort()
        return pliki

    def _check_project(
        technology: PythonTechnology,
        root: str,
    ) -> dict:
        """Zwraca wynik rozpoznania projektu: liczba plików, detect, pliki źródłowe, punkty wejścia.

        Po co: logika testu bez wypisywania.
        """
        pliki = _list_project_files(root)
        zrodla = []
        for path in pliki:
            if technology.is_source(path):
                zrodla.append(path)
        wynik = {
            "plików": len(pliki),
            "detect": technology.detect(root, pliki),
            "pliki źródłowe": zrodla,
            "find_entrypoints": technology.find_entrypoints(root, pliki),
        }
        return wynik

    def _print_project_check(
        title: str,
        root: str,
        result: dict,
    ) -> None:
        """Wypisuje wynik rozpoznania projektu z nagłówkiem.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"=== Projekt: {title} ({root}) ===")
        for klucz, wartosc in result.items():
            print(f"{klucz + ':':<18}{wartosc}")
        print()

    def _run_project_cases(
        technology: PythonTechnology,
        temp_dir: str,
    ) -> None:
        """Wypisuje rozpoznanie projektu dla robotów 01 i 02, katalogu tymczasowego i jego podkatalogu bez kodu.

        Po co: sprawdzenie detect, is_source i find_entrypoints na prawdziwych robotach i na przypadkach brzegowych.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        przypadki = [
            ("robot 01", os.path.join(katalog_testow, "01_rpa_challange_roboforge")),
            ("robot 02", os.path.join(katalog_testow, "02_robot_bez_frameworku")),
            ("katalog tymczasowy", temp_dir),
            ("katalog bez kodu", os.path.join(temp_dir, "bez_kodu")),
        ]
        for opis, root in przypadki:
            if not os.path.isdir(root):
                print(f"=== Projekt: {opis} - brak katalogu {root}, pomijam ===\n")
                continue
            _print_project_check(opis, root, _check_project(technology, root))

    def manual_test():
        """Z argumentami <katalog> <plik> [funkcja] - szkielet, importy i miary pliku albo szkielet sterowania funkcji; bez argumentów - przypadki testowe.

        Po co: sprawdzenie szkieletu, importów, szkieletu sterowania i miar na prawdziwym kodzie, wyciszenia
        SyntaxWarning i obsługi błędu składni.
        """
        technology = PythonTechnology()
        if len(sys.argv) == 4:
            _print_control_outline(f"{sys.argv[2]}, {sys.argv[3]!r}", technology.control_outline(sys.argv[1], sys.argv[2], sys.argv[3]), -1)
            return
        if len(sys.argv) == 3:
            szkielet, liczba = _outline_with_warning_count(technology, sys.argv[1], sys.argv[2])
            importy = technology.imports(sys.argv[1], sys.argv[2])
            _print_case("plik", sys.argv[1], sys.argv[2], szkielet, importy, liczba, -1)
            _print_metrics(sys.argv[2], technology.metrics(sys.argv[1], sys.argv[2]))
            return

        temp_dir = tempfile.mkdtemp()
        try:
            tresci = _write_temp_files(temp_dir)
            for opis, root, path in _collect_cases(temp_dir):
                if not os.path.exists(os.path.join(root, path)):
                    print(f"=== {opis}: brak pliku {os.path.join(root, path)} - pomijam ===\n")
                    continue
                szkielet, liczba = _outline_with_warning_count(technology, root, path)
                importy = technology.imports(root, path)
                liczba_bez_wyciszenia = -1
                if path == "sciezka_windows.py":
                    liczba_bez_wyciszenia = _plain_parse_warning_count(tresci[path])
                _print_case(opis, root, path, szkielet, importy, liczba, liczba_bez_wyciszenia)
            _run_complexity_cases(technology, temp_dir)
            _run_project_cases(technology, temp_dir)
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
