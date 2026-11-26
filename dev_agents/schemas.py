"""Schematy danych przekazywanych między etapami towaru (klasy Pydantic, bez logiki).

Co zawiera: opis kształtu danych, które jeden etap produkuje, a następny odbiera. Na tym etapie:
minimalne fakty o pliku źródłowym podawane przez technologię - jednostki z zakresami linii (SourceUnit),
odwołania do innych plików i pakietów (References), razem dla jednego pliku (SourceFile) - oraz mapa
projektu - wynik skanera: pliki z rolami (FileEntry), jednostki kodu do analizy (CodeUnit) i całość (ProjectMap). Kolejne schematy (pliki zależności,
konfiguracja robota, graf zależności, plan, notatki analityków, diagram przepływu, treść przewodnika,
recenzja) dochodzą w krokach, które ich potrzebują.

Dlaczego istnieje: jasna umowa między skanerem, technologiami, agentami i rendererem - każdy wie, co
dostaje i co oddaje. Każdy obiekt da się zapisać do JSON (model_dump_json) i wczytać z powrotem
(model_validate_json) - tak powstają pliki w dev_agents_doc/ analizowanego projektu (np. project_map.json).
Mapa projektu zawiera ścieżki i metadane, a nie treść plików - kod czytamy z dysku dopiero przy analizie,
dzięki czemu stan grafu pozostaje chudy.

Uwaga: schematy odpowiedzi modelu (dojdą później) będą miały przy polach Field(description="...") - model
widzi tylko schemat JSON. Schematy w tym pliku modelowi nie są podawane jako format odpowiedzi, więc mają
same typy i komentarze.

Rola: moduł używany przez wszystkie warstwy towaru (skaner, technologie, agenci, zapis wyników, renderer).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.schemas
Składa ręcznie przykładową mapę robota 02, wypisuje ją jako JSON i sprawdza, czy odczyt z JSON daje
obiekt równy oryginałowi (oczekiwane: True).
"""

import pydantic


# --- Fakty o plikach źródłowych (wynik technologii) ---


class SourceUnit(pydantic.BaseModel):
    """Jednostka pliku źródłowego - funkcja, klasa, metoda, workflow, zadanie - z nazwą i zakresem linii.

    Po co: pewne numery linii dla analityka i przewodnika, granice podziału długich plików na kawałki
    i długość jednostek do tabeli "Ryzykowne miejsca" - bez zgadywania przez model.
    """

    name: str  # np. "run", "Klasa.metoda", "Main.xaml", nazwa zadania Robot Framework
    start_line: int
    end_line: int


class References(pydantic.BaseModel):
    """Odwołania pliku źródłowego: inne pliki projektu i pakiety spoza projektu.

    Po co: z plików powstaje graf zależności i kolejność czytania, z pakietów - wykrywanie frameworków.

    Uwaga: same fakty z kodu; podział pakietów na standardowe i do zainstalowania oraz ich opis robią agenci.
    """

    files: list[str] = []  # ścieżki względne plików projektu (separator "/")
    packages: list[str] = []  # nazwy pakietów spoza projektu (w Pythonie bez biblioteki standardowej)


class SourceFile(pydantic.BaseModel):
    """Fakty o jednym pliku źródłowym robota policzone przez technologię: jednostki z zakresami linii i odwołania.

    Po co: z tych faktów korzystają graf zależności (krawędzie z references.files), wykrywanie frameworków
    (references.packages), podział długich plików i analitycy (numery linii) - liczone raz, przy skanie.
    """

    path: str  # ścieżka względna pliku (separator "/"), ta sama co w FileEntry
    units: list[SourceUnit] = []
    references: References = References()


# --- Mapa projektu (wynik skanera) ---


class FileEntry(pydantic.BaseModel):
    """Jeden plik analizowanego projektu: ścieżka, rola, rozmiar i przynależność do frameworku.

    Po co: skaner opisuje każdy plik jednym wpisem - po roli agenci i renderer wiedzą, czy plik to kod,
    konfiguracja, dane czy sekret (sekret trafia do modelu wyłącznie jako metadane).

    Uwaga: role: secret (tylko metadane), source (kod wg technologii), dependency, config, launcher (.bat, .cmd,
    .ps1), docs, data, binary (role z scan.role_patterns) i other (bez dopasowania).
    """

    path: str  # ścieżka względna do katalogu projektu, z separatorem "/"
    role: str  # secret | source | dependency | config | launcher | docs | data | binary | other
    size_bytes: int
    framework_name: str = ""  # nazwa frameworku, do którego należy plik; "" = kod projektu


class CodeUnit(pydantic.BaseModel):
    """Jednostka kodu do analizy - zadanie dla jednego analityka: nazwa i lista plików.

    Po co: analityk dostaje do opisania spójny kawałek kodu. W Pythonie jedna jednostka to zwykle jeden
    plik; lista plików zostawia miejsce na technologie, w których jeden proces składa się z kilku plików
    (np. UiPath).
    """

    name: str
    files: list[str]  # ścieżki względne plików jednostki


class ProjectMap(pydantic.BaseModel):
    """Wynik skanera: co jest w projekcie - pliki z rolami, punkty wejścia, jednostki kodu, fakty o plikach źródłowych i frameworki, bez treści plików.

    Po co: jeden obiekt opisujący projekt dla wszystkich dalszych etapów; zapisany jako project_map.json
    pozwala obejrzeć wynik skanera bez wywoływania modelu.

    Uwaga: pliki zależności i pliki konfiguracyjne robota dojdą jako osobne pola w krokach 23-24, razem
    ze swoimi klasami.
    """

    project_name: str
    root: str  # ścieżka bezwzględna do katalogu projektu
    technology: str  # np. python; "" = nie rozpoznano technologii
    entrypoints: list[str]  # ścieżki względne plików startowych
    files: list[FileEntry]
    code_units: list[CodeUnit]  # kod projektu do analizy (bez plików frameworku)
    source_files: list[SourceFile] = []  # fakty o plikach źródłowych robota (bez plików frameworku)
    frameworks: list[str] = []  # frameworki wykryte po ścieżkach i importach; [] = robot bez frameworku


# --- Test ręczny ---

if __name__ == "__main__":

    def _build_example_project_map() -> ProjectMap:
        """Składa ręcznie przykładową mapę robota 02 (bez frameworku, start z run.bat).

        Po co: dane do testu zapisu i odczytu JSON bez uruchamiania skanera, który powstanie w kolejnych krokach.

        Uwaga: role i wybór plików są ułożone ręcznie - prawdziwe role nadaje skaner.
        """
        files = [
            FileEntry(path="run.bat", role="launcher", size_bytes=350),
            FileEntry(path="przygotuj_dane.bat", role="launcher", size_bytes=234),
            FileEntry(path="przetwarzanie.py", role="source", size_bytes=17208),
            FileEntry(path="raport.py", role="source", size_bytes=2447),
            FileEntry(path="requirements.txt", role="dependency", size_bytes=18),
            FileEntry(path="dane/przyklady/zamowienia_2026-11-20.csv", role="data", size_bytes=461),
            FileEntry(path="dane/przyklady/notatka.txt", role="docs", size_bytes=79),
        ]
        code_units = [
            CodeUnit(name="przetwarzanie.py", files=["przetwarzanie.py"]),
            CodeUnit(name="raport.py", files=["raport.py"]),
        ]
        source_files = [
            SourceFile(
                path="przetwarzanie.py",
                units=[SourceUnit(name="log", start_line=31, end_line=38), SourceUnit(name="run", start_line=41, end_line=411)],
                references=References(packages=["requests"]),
            ),
            SourceFile(
                path="raport.py",
                units=[SourceUnit(name="main", start_line=13, end_line=71)],
                references=References(packages=["openpyxl"]),
            ),
        ]
        przykladowa_mapa = ProjectMap(
            project_name="02_robot_bez_frameworku",
            root=r"C:\Users\jankiwoj_box\Documents\projects\claude\tests\02_robot_bez_frameworku",
            technology="python",
            entrypoints=["przetwarzanie.py", "raport.py"],
            files=files,
            code_units=code_units,
            source_files=source_files,
        )
        return przykladowa_mapa

    def _round_trip(
        project_map: ProjectMap,
    ) -> tuple[str, bool]:
        """Zapisuje mapę do JSON, wczytuje ją z powrotem i zwraca (JSON, czy odczyt jest równy oryginałowi).

        Po co: sprawdza, że project_map.json zapisany przez towar da się wczytać bez utraty danych.
        """
        project_map_json = project_map.model_dump_json(indent=2)
        odczytana_mapa = ProjectMap.model_validate_json(project_map_json)
        wynik = (project_map_json, odczytana_mapa == project_map)
        return wynik

    def _print_round_trip(
        title: str,
        model_json: str,
        is_equal: bool,
    ) -> None:
        """Wypisuje obiekt jako JSON z tytułem i wynik porównania odczytu z oryginałem.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"=== {title} ===\n")
        print(model_json)
        print(f"\nOdczyt z JSON zgodny z oryginałem: {is_equal}")

    def manual_test():
        """Składa przykładową mapę robota 02, zapisuje ją do JSON, wczytuje z powrotem i wypisuje wynik.

        Po co: potwierdzenie, że mapa projektu przechodzi zapis i odczyt bez utraty danych.
        """
        project_map = _build_example_project_map()
        project_map_json, is_equal = _round_trip(project_map)
        _print_round_trip("ProjectMap (robot 02)", project_map_json, is_equal)

    manual_test()
