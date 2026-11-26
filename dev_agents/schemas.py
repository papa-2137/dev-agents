"""Schematy danych przekazywanych między etapami towaru (klasy Pydantic, bez logiki).

Co zawiera: opis kształtu danych, które jeden etap produkuje, a następny odbiera. Na tym etapie:
mapa projektu - wynik skanera: pliki z rolami (FileEntry), jednostki kodu do analizy (CodeUnit) i całość
(ProjectMap) - oraz miary złożoności funkcji liczone przez technologię (FunctionMetrics). Kolejne schematy (pliki zależności, konfiguracja robota, graf zależności, plan, notatki
analityków, diagram przepływu, treść przewodnika, recenzja) dochodzą w krokach, które ich potrzebują.

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


# --- Mapa projektu (wynik skanera) ---


class FileEntry(pydantic.BaseModel):
    """Jeden plik analizowanego projektu: ścieżka, rola, rozmiar i przynależność do frameworku.

    Po co: skaner opisuje każdy plik jednym wpisem - po roli agenci i renderer wiedzą, czy plik to kod,
    konfiguracja, dane czy sekret (sekret trafia do modelu wyłącznie jako metadane).

    Uwaga: lista ról rośnie razem z planem. Teraz: source, config, data, secret, binary, docs, other;
    w kroku 20 dochodzi launcher (pliki .bat, .cmd, .ps1).
    """

    path: str  # ścieżka względna do katalogu projektu, z separatorem "/"
    role: str  # source | config | data | secret | binary | docs | other (launcher od kroku 20)
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
    """Wynik skanera: co jest w projekcie - pliki z rolami, punkty wejścia, jednostki kodu i wykryte frameworki, bez treści plików.

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
    frameworks: list[str] = []  # frameworki wykryte po importach; [] = robot bez frameworku



# --- Miary złożoności (wynik technologii) ---


class FunctionMetrics(pydantic.BaseModel):
    """Miary złożoności jednej funkcji albo kodu poza funkcjami: zakres linii, długość, głębokość zagnieżdżenia, rozgałęzienia.

    Po co: liczby wskazują, gdzie kod jest trudny - bez zgadywania przez model. Z nich powstaje tabela
    "Ryzykowne miejsca", a długie funkcje są analizowane po kawałkach.

    Uwaga: same liczby, bez ocen - progi (co jest "długie") stosuje kod, który z miar korzysta.
    """

    path: str  # ścieżka względna pliku
    name: str  # nazwa funkcji, "Klasa.metoda" albo "<kod poza funkcjami>"
    start_line: int
    end_line: int
    lines: int  # liczba linii (dla kodu poza funkcjami - suma odcinków)
    max_depth: int  # najgłębsze zagnieżdżenie bloków (if, pętle, try, with); elif na poziomie swojego if
    branches: int  # punkty decyzji: if/elif, pętle, except, wyrażenia warunkowe, and/or - jak w złożoności cyklomatycznej

# --- Test ręczny ---

if __name__ == "__main__":

    def _build_example_project_map() -> ProjectMap:
        """Składa ręcznie przykładową mapę robota 02 (bez frameworku, start z run.bat).

        Po co: dane do testu zapisu i odczytu JSON bez uruchamiania skanera, który powstanie w kolejnych krokach.

        Uwaga: role i wybór plików są ułożone ręcznie - pliki .bat mają na razie rolę other, bo rola
        launcher dochodzi w kroku 20.
        """
        files = [
            FileEntry(path="run.bat", role="other", size_bytes=350),
            FileEntry(path="przygotuj_dane.bat", role="other", size_bytes=234),
            FileEntry(path="przetwarzanie.py", role="source", size_bytes=17208),
            FileEntry(path="raport.py", role="source", size_bytes=2447),
            FileEntry(path="requirements.txt", role="config", size_bytes=18),
            FileEntry(path="dane/przyklady/zamowienia_2026-11-20.csv", role="data", size_bytes=461),
            FileEntry(path="dane/przyklady/notatka.txt", role="docs", size_bytes=79),
        ]
        code_units = [
            CodeUnit(name="przetwarzanie.py", files=["przetwarzanie.py"]),
            CodeUnit(name="raport.py", files=["raport.py"]),
        ]
        przykladowa_mapa = ProjectMap(
            project_name="02_robot_bez_frameworku",
            root=r"C:\Users\jankiwoj_box\Documents\projects\claude\tests\02_robot_bez_frameworku",
            technology="python",
            entrypoints=["przetwarzanie.py", "raport.py"],
            files=files,
            code_units=code_units,
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
