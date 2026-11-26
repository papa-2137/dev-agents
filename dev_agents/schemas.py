"""Schematy danych przekazywanych między etapami towaru (klasy Pydantic, bez logiki).

Co zawiera: opis kształtu danych, które jeden etap produkuje, a następny odbiera. Na tym etapie:
minimalne fakty o pliku źródłowym podawane przez technologię - jednostki z zakresami linii (SourceUnit),
odwołania do innych plików i pakietów (References), razem dla jednego pliku (SourceFile) - oraz mapa
projektu - wynik skanera: pliki z rolami (FileEntry), jednostki kodu do analizy (CodeUnit), pliki
przepisane dosłownie (TextFile: zależności, konfiguracja, pliki uruchamiające) i całość (ProjectMap) - także
z grafem zależności między plikami robota i kolejnością czytania kodu. Dalej plan - wynik plannera
(AnalysisTask: jednostka kodu i wskazówka; Plan: podsumowanie, zadania analizy i pliki wiedzy dla analityków,
autora diagramu i pisarzy) oraz notatka analityka - wynik analizy jednostki kodu i surowiec dla wszystkich
zakładek (ModuleNote z klasami pomocniczymi NoteAction, NoteRisk, NoteFailure, NoteNetwork, NoteRequirement,
NoteTerm; dane i ustawienia używają klas DataRef i ConfigItem z guide_content.py). Treść przewodnika i diagram
są w guide_content.py. Kolejny schemat (recenzja) dochodzi w kroku, który go potrzebuje.

Dlaczego istnieje: jasna umowa między skanerem, technologiami, agentami i rendererem - każdy wie, co
dostaje i co oddaje. Każdy obiekt da się zapisać do JSON (model_dump_json) i wczytać z powrotem
(model_validate_json) - tak powstają pliki w dev_agents_doc/ analizowanego projektu (np. project_map.json).
Mapa projektu zawiera ścieżki i metadane, a nie treść kodu - kod czytamy z dysku dopiero przy analizie,
dzięki czemu stan grafu pozostaje chudy; dosłownie trzymamy tylko małe pliki tekstowe (TextFile).

Uwaga: schematy odpowiedzi modelu (Plan i AnalysisTask, ModuleNote i jej klasy pomocnicze, dalej recenzja) mają przy polach
Field(description="...") - model widzi tylko schemat JSON - i są płaskie, bez wariantów anyOf. Schematy faktów
o projekcie (SourceUnit ... ProjectMap) modelowi nie są podawane jako format odpowiedzi, więc mają same typy
i komentarze.

Rola: moduł używany przez wszystkie warstwy towaru (skaner, technologie, agenci, zapis wyników, renderer).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.schemas
Składa ręcznie przykładową mapę robota 02 i przykładowy plan, wypisuje je jako JSON i sprawdza, czy odczyt
z JSON daje obiekt równy oryginałowi (oczekiwane: True). Dla planu sprawdza też schemat JSON dla modelu:
brak wariantów anyOf i opis przy każdym polu oraz odrzucenie planu bez wymaganych pól. Dla notatki analityka:
ręcznie złożona notatka robota 02 (wydruk JSON, odczyt równy oryginałowi), notatka minimalna (tylko nazwa
jednostki i przeznaczenie - wszystkie listy puste, w tym punkty rozszerzeń), schemat JSON bez anyOf i z opisem
przy każdym polu, odrzucenie notatki bez przeznaczenia, odrzucenie nieznanego rodzaju czynności i numeru
kawałka mniejszego niż 1; na końcu "zgodne z oczekiwaniem: True".
"""

import typing

import pydantic

import dev_agents.guide_content as _guide_content


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


# --- Notatka analityka (wynik analityka) ---


class NoteAction(pydantic.BaseModel):
    """Jedna czynność robota w jednostce kodu: co robi, w której funkcji i linii, jakie dane czyta i zapisuje.

    Po co: surowiec diagramu przepływu (klocki z funkcją i linią, kafelki danych) i wierszy "Krok po kroku";
    czynność to jeden rozpoznawalny krok procesu, a nie linia kodu.
    """

    title: str = pydantic.Field(description="Krótki tytuł czynności językiem biznesowo-technicznym, kilka słów, np. Wczytaj listę plików zamówień.")
    kind: typing.Literal["step", "system", "decision", "error"] = pydantic.Field(
        description="Rodzaj: step (zwykły krok), system (kontakt z systemem poza robotem: strona, API, baza, plik na serwerze), decision (rozgałęzienie), error (obsługa błędu)."
    )
    function: str = pydantic.Field(default="", description="Funkcja, metoda albo klasa, w której dzieje się czynność, np. run. Puste, gdy kod jest poza funkcją.")
    line: int = pydantic.Field(default=0, ge=0, description="Numer linii pierwszej instrukcji czynności w pliku jednostki; 0, gdy nie da się wskazać.")
    description: str = pydantic.Field(default="", description="Jedno-dwa zdania: co robot robi i po co. Puste, gdy tytuł wystarcza.")
    reads: list[_guide_content.DataRef] = pydantic.Field(default=[], description="Co czynność czyta: pliki, zmienne środowiskowe, systemy, dane w pamięci - każde z rodzajem. Puste, gdy nic.")
    writes: list[_guide_content.DataRef] = pydantic.Field(default=[], description="Co czynność zapisuje albo zwraca - każde z rodzajem. Puste, gdy nic.")
    certain: bool = pydantic.Field(default=True, description="False, gdy czynność wywnioskowano, a nie zapisano wprost w kodzie.")


class NoteRisk(pydantic.BaseModel):
    """Trudne miejsce w kodzie: gdzie jest, jakiego rodzaju i dlaczego jest ryzykowne.

    Po co: surowiec tabeli "Ryzykowne miejsca" (kolumny: miejsce, plik i linie, rodzaj, dlaczego ryzykowne).
    """

    place: str = pydantic.Field(description="Nazwa miejsca: funkcja, stała, selektor albo krótki opis, np. run albo selektor przycisku Zapisz.")
    location: str = pydantic.Field(description="Plik i linia albo zakres, np. przetwarzanie.py:120-135.")
    kind: str = pydantic.Field(description="Rodzaj ryzyka w kilku słowach, np. sztywna ścieżka, kruchy selektor, stały czas oczekiwania, brak obsługi błędu, długa funkcja.")
    reason: str = pydantic.Field(description="Jedno-dwa zdania: dlaczego to ryzykowne i co może się stać.")
    certain: bool = pydantic.Field(default=True, description="False, gdy ryzyko wywnioskowano, a nie widać go wprost w kodzie.")


class NoteFailure(pydantic.BaseModel):
    """Możliwa awaria: objaw, przyczyna, gdzie szukać i jak naprawić.

    Po co: surowiec tabeli "Typowe awarie" w zakładce Błędy i naprawa.
    """

    symptom: str = pydantic.Field(description="Objaw widoczny dla operatora albo w logu, np. robot kończy pracę bez raportu.")
    cause: str = pydantic.Field(description="Prawdopodobna przyczyna wynikająca z kodu.")
    where: str = pydantic.Field(description="Gdzie szukać: plik i funkcja albo linia, np. raport.py:main:40.")
    fix: str = pydantic.Field(description="Jak naprawić albo co sprawdzić w pierwszej kolejności.")
    certain: bool = pydantic.Field(default=True, description="False, gdy awarię wywnioskowano, a kod jej wprost nie obsługuje ani nie opisuje.")


class NoteNetwork(pydantic.BaseModel):
    """Dostęp sieciowy robota: dokąd się łączy i po co.

    Po co: surowiec sekcji "Wymagania i dostępy" - administrator wie, jakie adresy i porty odblokować.
    """

    target: str = pydantic.Field(description="Adres, nazwa hosta albo nazwa systemu, np. https://api.example.test albo serwer SMTP.")
    port: str = pydantic.Field(default="", description="Port albo protokół, gdy wynika z kodu, np. 443 albo SMTP 587. Puste, gdy nie wynika.")
    purpose: str = pydantic.Field(description="Jedno zdanie: po co robot się tam łączy.")
    location: str = pydantic.Field(default="", description="Plik i linia, w której robot się łączy, np. przetwarzanie.py:300.")


class NoteRequirement(pydantic.BaseModel):
    """Wymaganie uruchomieniowe: czego robot potrzebuje na maszynie, by działać.

    Po co: surowiec sekcji "Wymagania i dostępy" - aplikacje, sterowniki, konta, uprawnienia i zmienne środowiskowe.
    """

    kind: typing.Literal["application", "driver", "account", "env_var", "permission", "other"] = pydantic.Field(
        description="Rodzaj: application (zainstalowana aplikacja), driver (sterownik, np. przeglądarki), account (konto lub certyfikat), env_var (zmienna środowiskowa), permission (uprawnienie, dostęp do katalogu), other."
    )
    name: str = pydantic.Field(description="Nazwa wymagania, np. Microsoft Excel, chromedriver, ROBOT_PASSWORD.")
    detail: str = pydantic.Field(default="", description="Jedno zdanie: do czego jest potrzebne albo w jakiej wersji. Puste, gdy nazwa wystarcza.")
    certain: bool = pydantic.Field(default=True, description="False, gdy wymaganie wywnioskowano, a kod go wprost nie wymienia.")


class NoteTerm(pydantic.BaseModel):
    """Kandydat do słowniczka: termin z kodu i jego krótkie wyjaśnienie.

    Po co: surowiec słowniczka przewodnika - pisarz wybiera z kandydatów wszystkich notatek terminy, które czytelnik
    może źle zrozumieć.
    """

    term: str = pydantic.Field(description="Termin dokładnie w takiej formie, w jakiej pojawia się w kodzie albo konfiguracji (słowniczek dopasowuje formę dokładnie).")
    definition: str = pydantic.Field(description="Wyjaśnienie w jednym zdaniu, zrozumiałe dla opiekuna bez znajomości kodu.")


class ModuleNote(pydantic.BaseModel):
    """Notatka analityka o jednej jednostce kodu: jedyne źródło wiedzy o kodzie dla autora diagramu i pisarzy zakładek.

    Po co: analityk czyta kod jednostki raz i zapisuje wszystko, czego potrzebują kolejne etapy - nikt dalej nie czyta
    kodu. Wszystkie listy mogą być puste, a pola tekstowe przyjmują zdanie "nie wynika z kodu": schemat nie zmusza
    modelu do wymyślania. Przy wnioskach, których kod nie mówi wprost, jest flaga pewności (certain=False).

    Uwaga: part i parts służą notatkom składanym z kawałków długiej funkcji (krok 51): part to numer kawałka,
    parts to liczba kawałków; zwykła notatka ma part=1 i parts=1.
    """

    unit_name: str = pydantic.Field(description="Nazwa analizowanej jednostki kodu dokładnie tak, jak w zadaniu, np. przetwarzanie.py.")
    part: int = pydantic.Field(default=1, ge=1, description="Numer kawałka, gdy jednostkę analizowano po kawałkach; 1, gdy w całości.")
    parts: int = pydantic.Field(default=1, ge=1, description="Liczba kawałków, na które podzielono jednostkę; 1, gdy w całości.")
    purpose: str = pydantic.Field(description="2-4 zdania zwykłego tekstu: do czego służy jednostka i jaką rolę ma w procesie robota. Jeśli nie wynika z kodu, napisz: nie wynika z kodu.")
    flow_role: str = pydantic.Field(
        default="",
        description="Rola jednostki w przepływie, np. punkt wejścia uruchamiany z run.bat, funkcja wołana przez framework po nazwie, moduł pomocniczy. Puste, gdy nie wynika z kodu.",
    )
    automated_application: str = pydantic.Field(
        default="",
        description="Aplikacje, strony i systemy, z którymi jednostka pracuje, np. przeglądarka Edge, https://www.rpachallenge.com. Puste, gdy żadnych.",
    )
    key_functions: list[str] = pydantic.Field(default=[], description="Najważniejsze funkcje, metody i klasy, każda jako: nazwa:linia - co robi.")
    actions: list[NoteAction] = pydantic.Field(default=[], description="Czynności robota w jednostce w kolejności wykonania, z funkcją, linią i danymi czytanymi oraz zapisywanymi.")
    process_steps: list[str] = pydantic.Field(
        default=[],
        description="Ten sam przebieg jako krótkie zdania z konkretami (aplikacje, adresy, pola, pliki). Decyzje jako: Jeśli ..., to ...; pętle jako: Dla każdego ...: z krokami wciętymi pod spodem.",
    )
    error_handling: list[str] = pydantic.Field(default=[], description="Obsługiwane wyjątki i sytuacje błędne oraz to, co robot wtedy robi (ponowienie, pominięcie, zatrzymanie, zapis do logu).")
    inputs: list[str] = pydantic.Field(default=[], description="Dane wejściowe jednostki: pliki, arkusze, kolumny, parametry, dane ze stron.")
    outputs: list[str] = pydantic.Field(default=[], description="Wyniki jednostki: zapisywane pliki, tabele, raporty, logi, dane przekazywane dalej.")
    settings: list[_guide_content.ConfigItem] = pydantic.Field(
        default=[],
        description="Ustawienia używane przez jednostkę: wpisy z plików konfiguracyjnych i stałe w kodzie, wartość dosłownie, z miejscami użycia (plik:linia). Hasło wpisane wprost oznacz plain_password=True.",
    )
    network: list[NoteNetwork] = pydantic.Field(default=[], description="Adresy, porty i systemy, z którymi jednostka się łączy. Puste, gdy żadnych.")
    requirements: list[NoteRequirement] = pydantic.Field(default=[], description="Wymagania uruchomieniowe: aplikacje, sterowniki, konta, uprawnienia, nazwy zmiennych środowiskowych.")
    external_dependencies: list[str] = pydantic.Field(
        default=[],
        description="Biblioteki spoza projektu i biblioteki standardowej, z krótkim: do czego (tylko to, co trzeba zainstalować).",
    )
    risky_places: list[NoteRisk] = pydantic.Field(default=[], description="Trudne miejsca: sztywne ścieżki i czasy, kruche selektory, sekrety w kodzie, brak obsługi błędów, niejasny kod.")
    possible_failures: list[NoteFailure] = pydantic.Field(default=[], description="Możliwe awarie z objawem, przyczyną, miejscem szukania i naprawą.")
    extension_points: list[str] = pydantic.Field(default=[], description="Punkty rozszerzeń: gdzie dodać nową stronę, nowy format pliku albo nową regułę, każdy jako: miejsce w kodzie - co tam dodać. Puste, gdy kod ich nie ma.")
    conventions: list[str] = pydantic.Field(default=[], description="Konwencje widoczne w kodzie: nazewnictwo, układ plików, sposób logowania i obsługi błędów, których warto się trzymać.")
    maintainer_hints: list[str] = pydantic.Field(default=[], description="Wskazówki dla opiekuna: co zmienić przy zmianie strony lub danych, gdzie szukać przyczyny błędu, czego nie ruszać.")
    glossary_candidates: list[NoteTerm] = pydantic.Field(default=[], description="Kandydaci do słowniczka: terminy, które opiekun może źle zrozumieć. Puste, gdy żadnych.")


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

    def _build_example_note() -> ModuleNote:
        """Składa ręcznie notatkę analityka o pliku przetwarzanie.py robota 02: czynności, ustawienia, ryzyka, awarie i reszta pól.

        Po co: dane do testu zapisu i odczytu JSON bez uruchamiania analityka (krok 50); notatka ma po jednym
        przykładzie każdego rodzaju wpisu, w tym hasło wpisane wprost i wniosek z flagą pewności.

        Uwaga: treść jest ułożona ręcznie - prawdziwą notatkę zwraca analityk.
        """
        dane_wejsciowe = _guide_content.DataRef(name="dane/wejscie/*.csv", kind="file")
        dane_wyjsciowe = _guide_content.DataRef(name="dane/wyjscie/wyniki_*.json", kind="file")
        czynnosci = [
            NoteAction(title="Wczytaj listę plików zamówień", kind="step", function="run", line=45, reads=[dane_wejsciowe]),
            NoteAction(title="Nagłówek poprawny?", kind="decision", function="run", line=88),
            NoteAction(title="Wyślij zamówienia do API", kind="system", function="run", line=300, certain=False),
            NoteAction(title="Zapisz wyniki", kind="step", function="run", line=380, writes=[dane_wyjsciowe]),
        ]
        ustawienia = [
            _guide_content.ConfigItem(
                location="przetwarzanie.py:14",
                key="URL",
                value="https://api.example.test/zamowienia",
                kind="system",
                meaning="Adres API zamówień; stała w kodzie.",
                used_in=["przetwarzanie.py:300"],
            ),
            _guide_content.ConfigItem(
                location="przetwarzanie.py:15",
                key="HASLO",
                value="Haslo123!",
                kind="account",
                plain_password=True,
                meaning="Hasło do API wpisane wprost w kod.",
                used_in=["przetwarzanie.py:301"],
            ),
        ]
        przykladowa_notatka = ModuleNote(
            unit_name="przetwarzanie.py",
            purpose="Wczytuje pliki zamówień z katalogu wejściowego, sprawdza nagłówki, wysyła zamówienia do API i zapisuje wyniki do JSON.",
            flow_role="Punkt wejścia uruchamiany z run.bat.",
            automated_application="API zamówień https://api.example.test",
            key_functions=["run:41 - cała logika robota", "log:31 - zapis linii do logu"],
            actions=czynnosci,
            process_steps=["Wczytaj listę plików zamówień.", "Jeśli nagłówek jest błędny, to przenieś plik do odrzuconych.", "Wyślij zamówienia do API."],
            error_handling=["Błąd odczytu pliku: zapis do logu i przejście do następnego pliku."],
            inputs=["dane/wejscie/*.csv - zamówienia, nagłówek w pierwszej linii"],
            outputs=["dane/wyjscie/wyniki_*.json - wyniki przetwarzania"],
            settings=ustawienia,
            network=[NoteNetwork(target="https://api.example.test", port="443", purpose="Wysłanie zamówień.", location="przetwarzanie.py:300")],
            requirements=[NoteRequirement(kind="env_var", name="ROBOT_KATALOG", detail="Katalog roboczy robota.", certain=False)],
            external_dependencies=["requests - wywołania API"],
            risky_places=[NoteRisk(place="run", location="przetwarzanie.py:41-411", kind="długa funkcja", reason="Cała logika w jednej funkcji - trudno zmieniać bez ryzyka.")],
            possible_failures=[
                NoteFailure(
                    symptom="Robot kończy pracę bez pliku wyników.",
                    cause="API nie odpowiada.",
                    where="przetwarzanie.py:run:300",
                    fix="Sprawdź dostęp do adresu API.",
                    certain=False,
                )
            ],
            extension_points=[],
            conventions=["Komunikaty logu zaczynają się od nazwy etapu."],
            maintainer_hints=["Zmiana adresu API: stała URL w przetwarzanie.py:14."],
            glossary_candidates=[NoteTerm(term="odrzucone", definition="Katalog na pliki z błędnym nagłówkiem.")],
        )
        return przykladowa_notatka

    def _note_checks(
        note: ModuleNote,
    ) -> list[tuple[str, bool]]:
        """Sprawdza notatkę: odczyt z JSON, notatka minimalna, schemat dla modelu, odrzucenia błędnych danych; zwraca (opis, zgodne).

        Po co: schemat notatki jest duży - test pilnuje, że wszystkie listy mogą być puste, a błędne dane są odrzucane.
        """
        minimalna = ModuleNote.model_validate_json('{"unit_name": "raport.py", "purpose": "nie wynika z kodu"}')
        problemy = _schema_problems(ModuleNote)
        bez_przeznaczenia = False
        try:
            ModuleNote.model_validate_json('{"unit_name": "raport.py"}')
        except pydantic.ValidationError:
            bez_przeznaczenia = True
        zly_rodzaj = False
        try:
            NoteAction.model_validate_json('{"title": "x", "kind": "magia"}')
        except pydantic.ValidationError:
            zly_rodzaj = True
        zly_kawalek = False
        try:
            ModuleNote.model_validate_json('{"unit_name": "raport.py", "purpose": "x", "part": 0}')
        except pydantic.ValidationError:
            zly_kawalek = True
        puste_listy = minimalna.actions == [] and minimalna.extension_points == [] and minimalna.settings == []
        wyniki = [
            ("odczyt notatki z JSON równy oryginałowi", ModuleNote.model_validate_json(note.model_dump_json()) == note),
            ("notatka z pustymi punktami rozszerzeń przechodzi walidację", note.extension_points == []),
            ("notatka minimalna: wszystkie listy puste, part=1, parts=1", puste_listy and minimalna.part == 1 and minimalna.parts == 1),
            (f"schemat ModuleNote bez anyOf i z opisem przy każdym polu (problemy: {problemy})", not problemy),
            ("notatka bez przeznaczenia odrzucona", bez_przeznaczenia),
            ("nieznany rodzaj czynności odrzucony", zly_rodzaj),
            ("numer kawałka mniejszy niż 1 odrzucony", zly_kawalek),
        ]
        return wyniki

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
        """Składa przykładową mapę robota 02, plan i notatkę analityka, zapisuje je do JSON, wczytuje z powrotem, sprawdza schematy i wypisuje wynik.

        Po co: potwierdzenie, że mapa projektu, plan i notatka przechodzą zapis i odczyt bez utraty danych, a schematy planu i notatki nadają się dla modelu.
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
        notatka = _build_example_note()
        print("=== ModuleNote (przetwarzanie.py, ułożona ręcznie) ===\n")
        print(notatka.model_dump_json(indent=2))
        print()
        sprawdzenia_notatki = _note_checks(notatka)
        notatka_zgodna = True
        for opis, zgodne_sprawdzenie in sprawdzenia_notatki:
            print(f"  {opis}: {zgodne_sprawdzenie}")
            if not zgodne_sprawdzenie:
                notatka_zgodna = False
        zgodne = is_equal and plan_zgodny and not problemy_planu and brakujace_odrzucone and notatka_zgodna
        print(f"\nzgodne z oczekiwaniem: {zgodne}")

    manual_test()
