"""Rejestr technologii: lista obsługiwanych technologii i wybór technologii dla projektu.

Co robi: available_technologies() zwraca wszystkie technologie w kolejności sprawdzania, detect_technology()
wybiera pierwszą, która rozpoznaje projekt, a get_technology() zwraca technologię po nazwie zapisanej
w mapie projektu (ProjectMap.technology).

Dlaczego istnieje: jedno miejsce, w którym wpisuje się nową technologię - rdzeń towaru (skaner, agenci)
pyta rejestr i nie zna żadnej technologii z nazwy. Rejestr jest osobnym modułem, a nie __init__.py pakietu:
__init__.py uruchamia się przy każdym `python -m dev_agents.technologies.<technologia>`, więc importy
technologii w nim ładowałyby uruchamiany moduł dwa razy.

Jak dodać technologię: utwórz podklasę Technology w osobnym pliku (kontrakt: base.py, wzorzec: python.py),
zaimportuj moduł poniżej i dopisz obiekt klasy do listy w available_technologies() - w miejscu zgodnym
z kolejnością sprawdzania.

Rola: moduł używany przez rdzeń towaru (skaner, agenci) do wyboru i odnalezienia technologii projektu.

Test ręczny (z katalogu głównego repo; same listy nazw plików, bez czytania dysku):
    python -m dev_agents.technologies.registry
Wypisuje rejestr (z oznaczeniem technologii pustych), wybór technologii dla trzech przykładowych list
plików, wyszukiwanie po nazwie i zachowanie metody pustej klasy.
"""

import dev_agents.technologies.base as _base
import dev_agents.technologies.nice as _nice
import dev_agents.technologies.python as _python
import dev_agents.technologies.robotframework as _robotframework
import dev_agents.technologies.uipath as _uipath


# --- Rejestr ---


def available_technologies() -> list[_base.Technology]:
    """Zwraca obiekty wszystkich obsługiwanych technologii w kolejności, w jakiej są sprawdzane.

    Po co: jedno miejsce, w którym wpisuje się nową technologię.

    Uwaga: kolejność ma znaczenie - najpierw technologie bardziej szczegółowe, na końcu Python. Projekt UiPath
    albo Robot Framework może zawierać pomocnicze pliki .py i nie może zostać uznany za pythonowy.
    """
    technologie = [
        _uipath.UiPathTechnology(),
        _robotframework.RobotFrameworkTechnology(),
        _nice.NiceTechnology(),
        _python.PythonTechnology(),
    ]
    return technologie


def detect_technology(
    root: str,
    files: list[str],
) -> _base.Technology | None:
    """Zwraca pierwszą technologię, której detect() rozpoznaje projekt; None, gdy żadna nie pasuje.

    Po co: skaner wybiera tu obsługę technologii dla całego projektu (ProjectMap.technology) - od niej
    zależy, które pliki są kodem, jak budować szkielety i jak czytać importy.

    Argumenty: files - wszystkie pliki projektu (ścieżki względne do root), po odfiltrowaniu ignorowanych.
    """
    for technologia in available_technologies():
        if technologia.detect(root, files):
            return technologia
    return None


def get_technology(
    name: str,
) -> _base.Technology | None:
    """Zwraca technologię o podanej nazwie (atrybut name, np. "python"); None dla pustej albo nieznanej nazwy.

    Po co: mapa projektu przechowuje tylko nazwę technologii, a dalsze etapy potrzebują obiektu technologii
    (np. analityk do szkieletu pliku).
    """
    if name == "":
        return None
    for technologia in available_technologies():
        if technologia.name == name:
            return technologia
    return None


# --- Test ręczny ---

if __name__ == "__main__":

    def _is_empty_class(
        technology: _base.Technology,
    ) -> bool:
        """Sprawdza, czy technologia jest pustą klasą - is_source() rzuca NotImplementedError.

        Po co: test pokazuje, które technologie są gotowe, a które czekają na implementację.
        """
        try:
            technology.is_source("plik.txt")
        except NotImplementedError:
            return True
        return False

    def _registry_lines() -> list[str]:
        """Zwraca linie opisu rejestru: numer w kolejności, nazwa, klasa, stan (gotowa / pusta).

        Po co: logika testu bez wypisywania.
        """
        linie = []
        numer = 0
        for technologia in available_technologies():
            numer += 1
            stan = "gotowa"
            if _is_empty_class(technologia):
                stan = "pusta (do implementacji)"
            linie.append(f"{numer}. {technologia.name:<15} {type(technologia).__name__:<26} {stan}")
        return linie

    def _detection_lines() -> list[str]:
        """Zwraca linie wyboru technologii dla przykładowych list plików (lista -> nazwa technologii albo None).

        Po co: pokazuje kolejność sprawdzania - projekt UiPath z plikiem .py daje dziś python, bo UiPath jest pustą klasą.
        """
        przyklady = [
            ("robot w Pythonie", ["main.py", "src/report.py", "config.yml"]),
            ("projekt UiPath z pomocniczym .py", ["project.json", "Main.xaml", "helper.py"]),
            ("same dane", ["dane.xlsx"]),
        ]
        linie = []
        for opis, pliki in przyklady:
            technologia = detect_technology("", pliki)
            nazwa = "None"
            if technologia is not None:
                nazwa = technologia.name
            linie.append(f"{opis:<34} {pliki} -> {nazwa}")
        return linie

    def _lookup_lines() -> list[str]:
        """Zwraca linie wyszukiwania technologii po nazwie dla "python", "uipath", "" i nazwy nieznanej.

        Po co: sprawdza get_technology(), także dla pustej nazwy (projekt nierozpoznany).
        """
        linie = []
        for nazwa in ["python", "uipath", "", "cobol"]:
            technologia = get_technology(nazwa)
            wynik = "None"
            if technologia is not None:
                wynik = type(technologia).__name__
            linie.append(f"get_technology({nazwa!r}) -> {wynik}")
        return linie

    def _empty_class_lines() -> list[str]:
        """Zwraca linie zachowania pustej klasy UiPath: find_entrypoints() (NotImplementedError) i metody opcjonalne ("brak danych").

        Po co: pusta klasa zgłasza czytelny błąd z nazwą technologii, a metody opcjonalne działają z domyślną odpowiedzią.
        """
        uipath = get_technology("uipath")
        linie = []
        try:
            uipath.find_entrypoints("", ["Main.xaml"])
        except NotImplementedError as blad:
            linie.append(f"find_entrypoints(): NotImplementedError: {blad}")
        linie.append(f"units(): {uipath.units('', 'Main.xaml')}")
        linie.append(f"references(): {uipath.references('', 'Main.xaml')!r}")
        return linie

    def _print_section(
        title: str,
        lines: list[str],
    ) -> None:
        """Wypisuje sekcję testu: tytuł i linie.

        Po co: wypisywanie oddzielone od logiki testu.
        """
        print(f"=== {title} ===")
        for linia in lines:
            print(linia)
        print()

    def manual_test():
        """Wypisuje rejestr, wybór technologii, wyszukiwanie po nazwie i zachowanie pustej klasy.

        Po co: sprawdzenie rejestru bez dysku i bez robotów testowych.
        """
        _print_section("Rejestr (kolejność sprawdzania)", _registry_lines())
        _print_section("detect_technology", _detection_lines())
        _print_section("get_technology", _lookup_lines())
        _print_section("Pusta klasa (UiPath)", _empty_class_lines())

    manual_test()
