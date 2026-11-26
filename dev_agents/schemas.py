"""Schematy danych przekazywanych między etapami towaru (klasy Pydantic, bez logiki).

Co zawiera: opis kształtu danych, które jeden etap produkuje, a następny odbiera. Na tym etapie:
minimalne fakty o pliku źródłowym podawane przez technologię - jednostki z zakresami linii (SourceUnit),
odwołania do innych plików i pakietów (References), razem dla jednego pliku (SourceFile) - oraz mapa
projektu - wynik skanera: pliki z rolami (FileEntry), jednostki kodu do analizy (CodeUnit), pliki
przepisane dosłownie (TextFile: zależności, konfiguracja, pliki uruchamiające) i całość (ProjectMap) - także
z grafem zależności między plikami robota i kolejnością czytania kodu. Dalej plan - wynik plannera
(AnalysisTask: jednostka kodu i wskazówka; Plan: podsumowanie, zadania analizy i pliki wiedzy dla analityków,
autora diagramu i pisarzy). Treść przewodnika i diagram są w guide_content.py. Kolejne schematy (notatki
analityków, recenzja) dochodzą w krokach, które ich potrzebują.

Dlaczego istnieje: jasna umowa między skanerem, technologiami, agentami i rendererem - każdy wie, co
dostaje i co oddaje. Każdy obiekt da się zapisać do JSON (model_dump_json) i wczytać z powrotem
(model_validate_json) - tak powstają pliki w dev_agents_doc/ analizowanego projektu (np. project_map.json).
Mapa projektu zawiera ścieżki i metadane, a nie treść kodu - kod czytamy z dysku dopiero przy analizie,
dzięki czemu stan grafu pozostaje chudy; dosłownie trzymamy tylko małe pliki tekstowe (TextFile).

Uwaga: schematy odpowiedzi modelu (Plan i AnalysisTask, dalej notatka analityka i recenzja) mają przy polach
Field(description="...") - model widzi tylko schemat JSON - i są płaskie, bez wariantów anyOf. Schematy faktów
o projekcie (SourceUnit ... ProjectMap) modelowi nie są podawane jako format odpowiedzi, więc mają same typy
i komentarze.

Rola: moduł używany przez wszystkie warstwy towaru (skaner, technologie, agenci, zapis wyników, renderer).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.schemas
Składa ręcznie przykładową mapę robota 02 i przykładowy plan, wypisuje je jako JSON i sprawdza, czy odczyt
z JSON daje obiekt równy oryginałowi (oczekiwane: True). Dla planu sprawdza też schemat JSON dla modelu:
brak wariantów anyOf i opis przy każdym polu oraz odrzucenie planu bez wymaganych pól; na końcu
"zgodne z oczekiwaniem: True".
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


class TextFile(pydantic.BaseModel):
    """Plik tekstowy robota przepisany dosłownie: ścieżka, rola i treść.

    Po co: pełna lista zależności do skopiowania w przewodniku (W2) oraz konfiguracja i pliki uruchamiające
    dla agentów (metryczka, uruchomienie, dostępy) - przepisane przez kod, więc bez ryzyka przekłamania.

    Uwaga: które role trafiają tu, ustala scan.text_roles; sekrety i kod nigdy.
    """

    path: str  # ścieżka względna (separator "/")
    role: str  # dependency | config | launcher (wg scan.text_roles)
    text: str  # treść odczytana przez files.read_text_safe (końce linii "\n")


class ProjectMap(pydantic.BaseModel):
    """Wynik skanera: co jest w projekcie - pliki z rolami, punkty wejścia, jednostki kodu, fakty o plikach źródłowych i frameworki, bez treści plików.

    Po co: jeden obiekt opisujący projekt dla wszystkich dalszych etapów; zapisany jako project_map.json
    pozwala obejrzeć wynik skanera bez wywoływania modelu.

    Uwaga: treść trzyma tylko dla plików tekstowych (text_files) - kod czyta się z dysku przy analizie.
    """

    project_name: str
    root: str  # ścieżka bezwzględna do katalogu projektu
    technology: str  # np. python; "" = nie rozpoznano technologii
    entrypoints: list[str]  # ścieżki względne plików startowych
    files: list[FileEntry]
    code_units: list[CodeUnit]  # kod projektu do analizy (bez plików frameworku)
    text_files: list[TextFile] = []  # zależności, konfiguracja i pliki uruchamiające robota - dosłownie
    source_files: list[SourceFile] = []  # fakty o plikach źródłowych robota (bez plików frameworku)
    dependency_edges: list[list[str]] = []  # [plik, plik, z którego korzysta] - tylko między plikami robota
    reading_order: list[str] = []  # kolejność czytania plików źródłowych: od punktów wejścia w głąb
    frameworks: list[str] = []  # frameworki wykryte po ścieżkach i importach; [] = robot bez frameworku


# --- Plan (wynik plannera) ---


class AnalysisTask(pydantic.BaseModel):
    """Zadanie dla jednego analityka: jednostka kodu do opisania i wskazówka plannera.

    Po co: planner widzi cały projekt, a analityk tylko swoją jednostkę - wskazówka przekazuje to, co planner
    wie o miejscu jednostki w całości (np. "główna funkcja, długa, czytaj po kawałkach").
    """

    unit: str = pydantic.Field(
        description="Nazwa jednostki kodu dokładnie tak, jak w mapie projektu (code_units), np. przetwarzanie.py."
    )
    hint: str = pydantic.Field(
        default="",
        description="Wskazówka dla analityka: na co zwrócić uwagę w tej jednostce albo jaką ma rolę w robocie. Puste, gdy nie ma nic szczególnego.",
    )


class Plan(pydantic.BaseModel):
    """Plan przebiegu: podsumowanie projektu, zadania analizy i pliki wiedzy dla kolejnych agentów.

    Po co: wynik plannera, na którym opierają się dalsze etapy - analitycy (jedno zadanie na jednostkę), autor
    diagramu i pisarze zakładek dostają ze spisu bazy wiedzy tylko te pliki, których potrzebują.

    Uwaga: analizujemy wszystkie jednostki z mapy projektu - planner ustala kolejność i wskazówki, a brakujące
    jednostki dopisze kod (krok 47). Pliki wiedzy technologii i frameworków dołącza kod, nie planner.
    """

    summary: str = pydantic.Field(
        description="2-4 zdania: co robi robot, jakiej technologii i frameworku używa, od czego się zaczyna. Czytają je wszyscy agenci."
    )
    tasks: list[AnalysisTask] = pydantic.Field(
        description="Zadania analizy w kolejności czytania kodu: od punktów wejścia w głąb. Każda jednostka z mapy projektu najwyżej raz."
    )
    analyst_knowledge: list[str] = pydantic.Field(
        default=[],
        description="Pliki wiedzy ze spisu (index.md) dla analityków - dokładne nazwy plików. Puste, gdy żaden się nie przyda.",
    )
    flow_knowledge: list[str] = pydantic.Field(
        default=[],
        description="Pliki wiedzy ze spisu (index.md) dla autora diagramu przepływu - dokładne nazwy plików. Puste, gdy żaden się nie przyda.",
    )
    writer_knowledge: list[str] = pydantic.Field(
        default=[],
        description="Pliki wiedzy ze spisu (index.md) dla pisarzy zakładek - dokładne nazwy plików. Puste, gdy żaden się nie przyda.",
    )


# --- Test ręczny ---

if __name__ == "__main__":
    import json

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
        text_files = [
            TextFile(path="requirements.txt", role="dependency", text="openpyxl\nrequests\n"),
            TextFile(path="run.bat", role="launcher", text="@echo off\ncd /d %~dp0\npython przetwarzanie.py\n"),
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
            text_files=text_files,
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

    def _build_example_plan() -> Plan:
        """Składa ręcznie przykładowy plan robota 02: dwa zadania (jedno ze wskazówką, drugie bez) i różne listy wiedzy.

        Po co: dane do testu zapisu i odczytu JSON bez uruchamiania plannera; jedna lista wiedzy jest pusta,
        żeby test objął także ten przypadek.

        Uwaga: treść jest ułożona ręcznie - prawdziwy plan zwraca planner (krok 47).
        """
        zadania = [
            AnalysisTask(
                unit="przetwarzanie.py",
                hint="Funkcja run ma ok. 370 linii i zawiera większość logiki - czytaj ją po kawałkach; zwróć uwagę na kontakty z systemami i obsługę błędów.",
            ),
            AnalysisTask(unit="raport.py"),
        ]
        przykladowy_plan = Plan(
            summary="Robot w Pythonie bez frameworku, uruchamiany z run.bat: przetwarzanie.py wykonuje główną pracę, raport.py składa raport z wyników.",
            tasks=zadania,
            analyst_knowledge=[],
            flow_knowledge=["diagram_rules.md"],
            writer_knowledge=["guide_goals.md"],
        )
        return przykladowy_plan

    def _schema_problems(
        model_class,
    ) -> list[str]:
        """Zwraca listę problemów schematu JSON klasy dla modelu: wariant anyOf albo pole bez opisu (pusta lista = schemat poprawny).

        Po co: model widzi tylko schemat JSON; wariant anyOf nie był sprawdzony na bramce na mieście, a pole bez
        opisu model wypełnia po omacku.
        """
        schemat = model_class.model_json_schema()
        problemy = []
        if "anyOf" in json.dumps(schemat):
            problemy.append("schemat zawiera wariant anyOf")
        obiekty = [schemat]
        for definicja in schemat.get("$defs", {}).values():
            obiekty.append(definicja)
        for obiekt in obiekty:
            for nazwa_pola, pole in obiekt.get("properties", {}).items():
                if not pole.get("description"):
                    problemy.append(f"{obiekt.get('title')}.{nazwa_pola}: brak opisu")
        return problemy

    def _plan_missing_fields_rejected() -> bool:
        """Zwraca True, gdy plan bez wymaganych pól (summary, tasks) jest odrzucony przy odczycie z JSON.

        Po co: odpowiedź modelu bez podsumowania albo zadań ma dać błąd walidacji, a nie pusty plan.
        """
        odrzucony = False
        try:
            Plan.model_validate_json('{"analyst_knowledge": []}')
        except pydantic.ValidationError:
            odrzucony = True
        return odrzucony

    def manual_test():
        """Składa przykładową mapę robota 02 i przykładowy plan, zapisuje je do JSON, wczytuje z powrotem, sprawdza schemat planu i wypisuje wynik.

        Po co: potwierdzenie, że mapa projektu i plan przechodzą zapis i odczyt bez utraty danych, a schemat planu nadaje się dla modelu.
        """
        project_map = _build_example_project_map()
        project_map_json, is_equal = _round_trip(project_map)
        _print_round_trip("ProjectMap (robot 02)", project_map_json, is_equal)
        plan = _build_example_plan()
        plan_json = plan.model_dump_json(indent=2)
        plan_zgodny = Plan.model_validate_json(plan_json) == plan
        _print_round_trip("Plan (robot 02, ułożony ręcznie)", plan_json, plan_zgodny)
        problemy_planu = _schema_problems(Plan)
        brakujace_odrzucone = _plan_missing_fields_rejected()
        print(f"\nProblemy schematu JSON klasy Plan (anyOf, pola bez opisu): {problemy_planu}")
        print(f"Plan bez wymaganych pól odrzucony przy odczycie: {brakujace_odrzucone}")
        zgodne = is_equal and plan_zgodny and not problemy_planu and brakujace_odrzucone
        print(f"\nzgodne z oczekiwaniem: {zgodne}")

    manual_test()
