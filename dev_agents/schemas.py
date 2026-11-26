"""Schematy danych przekazywanych między etapami towaru (klasy Pydantic, bez logiki).

Co zawiera: opis kształtu danych, które jeden etap produkuje, a następny odbiera. Na tym etapie:
minimalne fakty o pliku źródłowym podawane przez technologię - jednostki z zakresami linii (SourceUnit),
odwołania do innych plików i pakietów (References), razem dla jednego pliku (SourceFile) - oraz mapa
projektu - wynik skanera: pliki z rolami (FileEntry), jednostki kodu do analizy (CodeUnit), pliki
przepisane dosłownie (TextFile: zależności, konfiguracja, pliki uruchamiające) i całość (ProjectMap) - także
z grafem zależności między plikami robota i kolejnością czytania kodu. Dalej plan - wynik plannera
(AnalysisTask: jednostka kodu i wskazówka; Plan: podsumowanie, zadania analizy i pliki wiedzy dla analityków,
autora diagramu i pisarzy) oraz notatka analityka - wynik analizy jednostki kodu i surowiec dla wszystkich
zakładek (ModuleNote z klasami pomocniczymi NoteAction, NoteSetting, NoteRisk, NoteFailure, NoteRequirement,
NoteTerm; dane czynności używają klasy DataRef z guide_content.py). Treść przewodnika i diagram
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
ręcznie złożona notatka robota 02 (wydruk JSON, odczyt równy oryginałowi), notatka z pustymi listami (w tym punkty
rozszerzeń), schemat JSON bez anyOf, bez ograniczeń liczbowych (minimum, maksimum), bez pól opcjonalnych i z opisem
przy każdym polu (bramka na Kwadracie odrzuca zbyt duże gramatyki), odrzucenie notatki bez wymaganych pól i
odrzucenie nieznanego rodzaju czynności; wypisuje liczbę pól opcjonalnych w schematach Plan i ModuleNote; na końcu "zgodne z oczekiwaniem: True".
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
#
# Uwaga dla wszystkich klas tej sekcji: to schematy odpowiedzi modelu na bramce Kwadratu (tryb strict). Bramka odrzuca
# schemat, którego gramatyka jest zbyt duża ("The compiled grammar is too large"). Pomiar na prawdziwej bramce
# (scripts/probe_schema.py, model small): przechodzi schemat do 48 pól liczonych po rozwinięciu klas zagnieżdżonych
# (pole klasy użytej dwa razy liczy się dwa razy), 49 pól już nie; płaski obiekt przechodzi przy 40 polach, nie przechodzi
# przy 80. Osobne limity: najwyżej 16 pól typu "tekst albo null", brak ograniczeń liczbowych (minimum, maximum - błąd 400).
# NIE mają znaczenia: głębokość zagnieżdżenia (5 poziomów przeszło), enumy Literal (40 pól przeszło), wielokrotne użycie tej
# samej klasy i pola z wartością domyślną (biblioteka openai wysyła wszystkie pola jako wymagane). Dlatego notatka
# analityka jest zwracana w dwóch odpowiedziach (NoteFlow i NoteDetails), a kod składa je w ModuleNote; każdy schemat dla
# modelu ma najwyżej MAX_MODEL_SCHEMA_PROPERTIES pól (zapas względem 48). Pozostałe zasady: wszystkie pola są wymagane
# ("puste" znaczy [] albo ""), a niepewność wniosków w tabelach oznacza tekst "[wywnioskowane]", a nie osobna flaga.

MAX_MODEL_SCHEMA_PROPERTIES = 40


def _count_properties(
    node: typing.Any,
    defs: dict,
) -> int:
    """Zwraca liczbę pól w węźle schematu JSON po rozwinięciu odwołań $ref (pole klasy użytej dwa razy liczy się dwa razy).

    Po co: bramka liczy pola schematu po rozwinięciu klas zagnieżdżonych - ta sama miara co w scripts/probe_schema.py.
    """
    liczba = 0
    if not isinstance(node, dict):
        return liczba
    if "$ref" in node:
        liczba = _count_properties(defs[node["$ref"].split("/")[-1]], defs)
        return liczba
    for wariant in node.get("anyOf", []):
        liczba += _count_properties(wariant, defs)
    if "items" in node:
        liczba += _count_properties(node["items"], defs)
    for pole in node.get("properties", {}).values():
        liczba += 1 + _count_properties(pole, defs)
    return liczba


def count_schema_properties(
    model_class,
) -> int:
    """Zwraca liczbę pól schematu JSON klasy po rozwinięciu klas zagnieżdżonych (miara limitu bramki).

    Po co: schemat odpowiedzi modelu nie może przekroczyć limitu bramki (MAX_MODEL_SCHEMA_PROPERTIES z zapasem);
    testy pilnują tego dla każdego schematu wysyłanego do modelu.
    """
    schemat = model_class.model_json_schema()
    liczba = _count_properties(schemat, schemat.get("$defs", {}))
    return liczba


class NoteAction(pydantic.BaseModel):
    """Jedna czynność robota w jednostce kodu: co robi, w której funkcji i linii, jakie dane czyta i zapisuje.

    Po co: surowiec diagramu przepływu (klocki z funkcją i linią, kafelki danych) i wierszy "Krok po kroku";
    czynność to jeden rozpoznawalny krok procesu, a nie linia kodu.
    """

    title: str = pydantic.Field(description="Krótki tytuł czynności językiem biznesowo-technicznym, kilka słów, zawsze w trybie rozkazującym (Wczytaj, Otwórz, Zapisz), nie w bezokoliczniku, np. Wczytaj listę plików zamówień.")
    kind: typing.Literal["step", "system", "decision", "error"] = pydantic.Field(
        description="Rodzaj: step (zwykły krok), system (kontakt z systemem poza robotem: strona, API, baza, plik na serwerze), decision (rozgałęzienie), error (obsługa błędu)."
    )
    function: str = pydantic.Field(description="Funkcja, metoda albo klasa, w której dzieje się czynność, np. run. Pusty tekst, gdy kod jest poza funkcją.")
    line: int = pydantic.Field(description="Numer linii pierwszej instrukcji czynności w pliku jednostki (od 1); 0, gdy nie da się wskazać.")
    description: str = pydantic.Field(description="Jedno-dwa zdania: co robot robi i po co. Pusty tekst, gdy tytuł wystarcza.")
    reads: list[_guide_content.DataRef] = pydantic.Field(description="Co czynność czyta: pliki, zmienne środowiskowe, systemy, dane w pamięci - każde z rodzajem. Pusta lista, gdy nic.")
    writes: list[_guide_content.DataRef] = pydantic.Field(description="Co czynność zapisuje albo zwraca - każde z rodzajem. Pusta lista, gdy nic.")
    certain: bool = pydantic.Field(description="False, gdy czynność wywnioskowano, a nie zapisano wprost w kodzie.")


class NoteSetting(pydantic.BaseModel):
    """Ustawienie używane przez jednostkę: wpis z pliku konfiguracyjnego albo stała w kodzie.

    Po co: surowiec metryczki robota; pola odpowiadają guide_content.ConfigItem, więc pisarz przepisuje wpis bez zmian.
    """

    file: str = pydantic.Field(description="Plik konfiguracyjny, np. config.yml; pusty tekst, gdy ustawienie jest stałą w kodzie.")
    location: str = pydantic.Field(description="Plik i linia, np. przetwarzanie.py:14: dla stałej w kodzie zawsze; dla wpisu z pliku konfiguracyjnego tylko przy haśle wpisanym wprost (np. config.yml:12), inaczej pusty tekst.")
    group: str = pydantic.Field(description="Sekcja pliku konfiguracyjnego, np. parabank; pusty tekst, gdy brak.")
    key: str = pydantic.Field(description="Nazwa klucza albo stałej, np. url, INPUT_DIR.")
    value: str = pydantic.Field(description="Wartość przepisana dosłownie z pliku albo kodu.")
    kind: typing.Literal["system", "account", "env_var", "input_file", "output_file", "log", "switch", "other"] = pydantic.Field(
        description="Rodzaj: system (adres systemu zewnętrznego), account (konto), env_var (nazwa zmiennej środowiskowej), input_file, output_file, log, switch (przełącznik), other."
    )
    plain_password: bool = pydantic.Field(description="True, gdy wartość to hasło, klucz albo token wpisany wprost.")
    meaning: str = pydantic.Field(description="Znaczenie ustawienia w jednym zdaniu - z kodu, który go używa.")
    used_in: list[str] = pydantic.Field(description="Miejsca użycia w kodzie, każde jako plik:linia, np. main.py:139.")
    certain: bool = pydantic.Field(description="False, gdy znaczenie wywnioskowano, a nie wynika wprost z kodu.")


class NoteRisk(pydantic.BaseModel):
    """Trudne miejsce w kodzie: gdzie jest, jakiego rodzaju i dlaczego jest ryzykowne.

    Po co: surowiec tabeli "Ryzykowne miejsca" (kolumny: miejsce, plik i linie, rodzaj, dlaczego ryzykowne).
    """

    place: str = pydantic.Field(description="Nazwa miejsca: funkcja, stała, selektor albo krótki opis, np. run albo selektor przycisku Zapisz.")
    location: str = pydantic.Field(description="Plik i linia albo zakres, np. przetwarzanie.py:120-135.")
    kind: str = pydantic.Field(description="Rodzaj ryzyka w kilku słowach, np. sztywna ścieżka, kruchy selektor, stały czas oczekiwania, brak obsługi błędu, długa funkcja.")
    reason: str = pydantic.Field(description="Jedno-dwa zdania: dlaczego to ryzykowne i co może się stać. Wniosek niewidoczny wprost w kodzie zakończ tekstem [wywnioskowane].")


class NoteFailure(pydantic.BaseModel):
    """Możliwa awaria: objaw, przyczyna, gdzie szukać i jak naprawić.

    Po co: surowiec tabeli "Typowe awarie" w zakładce Błędy i naprawa.
    """

    symptom: str = pydantic.Field(description="Objaw widoczny dla operatora albo w logu, np. robot kończy pracę bez raportu.")
    cause: str = pydantic.Field(description="Prawdopodobna przyczyna wynikająca z kodu. Wniosek niewidoczny wprost w kodzie zakończ tekstem [wywnioskowane].")
    where: str = pydantic.Field(description="Gdzie szukać: plik i funkcja albo linia, np. raport.py:main:40.")
    fix: str = pydantic.Field(description="Jak naprawić albo co sprawdzić w pierwszej kolejności.")


class NoteRequirement(pydantic.BaseModel):
    """Wymaganie uruchomieniowe lub dostęp sieciowy: czego robot potrzebuje, by działać.

    Po co: surowiec sekcji "Wymagania i dostępy" - aplikacje, sterowniki, konta, uprawnienia, zmienne środowiskowe
    oraz adresy i porty, do których robot musi mieć dostęp.
    """

    kind: typing.Literal["application", "driver", "account", "env_var", "permission", "network", "other"] = pydantic.Field(
        description="Rodzaj: application (zainstalowana aplikacja), driver (sterownik, np. przeglądarki), account (konto lub certyfikat), env_var (zmienna środowiskowa), permission (uprawnienie, dostęp do katalogu), network (adres, host albo port, z którym robot się łączy), other."
    )
    name: str = pydantic.Field(description="Nazwa wymagania, np. Microsoft Excel, chromedriver, ROBOT_PASSWORD albo adres z portem, np. https://api.example.test:443.")
    detail: str = pydantic.Field(description="Jedno zdanie: do czego jest potrzebne, z miejscem w kodzie (plik:linia), gdy jest. Wniosek niewidoczny wprost w kodzie zakończ tekstem [wywnioskowane].")


class NoteTerm(pydantic.BaseModel):
    """Kandydat do słowniczka: termin z kodu i jego krótkie wyjaśnienie.

    Po co: surowiec słowniczka przewodnika - pisarz wybiera z kandydatów wszystkich notatek terminy, które czytelnik
    może źle zrozumieć.
    """

    term: str = pydantic.Field(description="Termin dokładnie w takiej formie, w jakiej pojawia się w kodzie albo konfiguracji (słowniczek dopasowuje formę dokładnie).")
    definition: str = pydantic.Field(description="Wyjaśnienie w jednym zdaniu, zrozumiałe dla opiekuna bez znajomości kodu.")


class NoteFlow(pydantic.BaseModel):
    """Część 1 notatki analityka (odpowiedź modelu): rola i przebieg jednostki - cel, aplikacje, funkcje, czynności, kroki, błędy, wejścia i wyjścia.

    Po co: pełna notatka ma więcej pól, niż przyjmuje bramka (MAX_MODEL_SCHEMA_PROPERTIES), więc model zwraca ją w dwóch
    odpowiedziach: NoteFlow (przebieg) i NoteDetails (ustawienia, wymagania, ryzyka); kod składa je w ModuleNote.
    Wszystkie pola są wymagane, ale listy mogą być puste, a pola tekstowe przyjmują zdanie "nie wynika z kodu":
    schemat nie zmusza modelu do wymyślania.
    """

    unit_name: str = pydantic.Field(description="Nazwa analizowanej jednostki kodu dokładnie tak, jak w zadaniu, np. przetwarzanie.py.")
    purpose: str = pydantic.Field(description="2-4 zdania zwykłego tekstu: do czego służy jednostka i jaką rolę ma w procesie robota. Jeśli nie wynika z kodu, napisz: nie wynika z kodu.")
    flow_role: str = pydantic.Field(
        description="Rola jednostki w przepływie, np. punkt wejścia uruchamiany z run.bat, funkcja wołana przez framework po nazwie, moduł pomocniczy. Pusty tekst, gdy nie wynika z kodu.",
    )
    automated_application: str = pydantic.Field(description="Aplikacje, strony i systemy, z którymi jednostka pracuje, np. przeglądarka Edge, https://www.rpachallenge.com. Pusty tekst, gdy żadnych.")
    key_functions: list[str] = pydantic.Field(description="Najważniejsze funkcje, metody i klasy, każda jako: nazwa:linia - co robi.")
    actions: list[NoteAction] = pydantic.Field(description="Czynności robota w jednostce w kolejności wykonania, z funkcją, linią i danymi czytanymi oraz zapisywanymi.")
    process_steps: list[str] = pydantic.Field(
        description="Ten sam przebieg jako krótkie zdania z konkretami (aplikacje, adresy, pola, pliki). Decyzje jako: Jeśli ..., to ...; pętle jako: Dla każdego ...: z krokami wciętymi pod spodem.",
    )
    error_handling: list[str] = pydantic.Field(description="Obsługiwane wyjątki i sytuacje błędne oraz to, co robot wtedy robi (ponowienie, pominięcie, zatrzymanie, zapis do logu).")
    inputs: list[str] = pydantic.Field(description="Dane wejściowe jednostki: pliki, arkusze, kolumny, parametry, dane ze stron.")
    outputs: list[str] = pydantic.Field(description="Wyniki jednostki: zapisywane pliki, tabele, raporty, logi, dane przekazywane dalej.")


class NoteDetails(pydantic.BaseModel):
    """Część 2 notatki analityka (odpowiedź modelu): ustawienia, wymagania, zależności, ryzyka, awarie, rozszerzenia, konwencje, wskazówki i słowniczek.

    Po co: druga połowa notatki (patrz NoteFlow) - model dostaje ten sam kod i zwraca te pola osobno, bo oba schematy razem
    przekraczałyby limit bramki. Wszystkie pola są wymagane, listy mogą być puste.
    """

    settings: list[NoteSetting] = pydantic.Field(
        description="Ustawienia używane przez jednostkę: wpisy z plików konfiguracyjnych i stałe w kodzie, wartość dosłownie, z miejscami użycia (plik:linia). Hasło wpisane wprost oznacz plain_password=true.",
    )
    requirements: list[NoteRequirement] = pydantic.Field(description="Wymagania uruchomieniowe i dostęp sieciowy: aplikacje, sterowniki, konta, uprawnienia, nazwy zmiennych środowiskowych, adresy i porty.")
    external_dependencies: list[str] = pydantic.Field(
        description="Biblioteki spoza projektu i biblioteki standardowej, z krótkim: do czego (tylko to, co trzeba zainstalować).",
    )
    risky_places: list[NoteRisk] = pydantic.Field(description="Trudne miejsca: sztywne ścieżki i czasy, kruche selektory, sekrety w kodzie, brak obsługi błędów, niejasny kod.")
    possible_failures: list[NoteFailure] = pydantic.Field(description="Możliwe awarie z objawem, przyczyną, miejscem szukania i naprawą.")
    extension_points: list[str] = pydantic.Field(description="Punkty rozszerzeń: gdzie dodać nową stronę, nowy format pliku albo nową regułę, każdy jako: miejsce w kodzie - co tam dodać. Pusta lista, gdy kod ich nie ma.")
    conventions: list[str] = pydantic.Field(description="Konwencje widoczne w kodzie: nazewnictwo, układ plików, sposób logowania i obsługi błędów, których warto się trzymać.")
    maintainer_hints: list[str] = pydantic.Field(description="Wskazówki dla opiekuna: co zmienić przy zmianie strony lub danych, gdzie szukać przyczyny błędu, czego nie ruszać.")
    glossary_candidates: list[NoteTerm] = pydantic.Field(description="Kandydaci do słowniczka: terminy, które opiekun może źle zrozumieć. Pusta lista, gdy żadnych.")


class ModuleNote(NoteDetails, NoteFlow):
    """Notatka analityka o jednej jednostce kodu: jedyne źródło wiedzy o kodzie dla autora diagramu i pisarzy zakładek.

    Po co: analityk czyta kod jednostki i zapisuje wszystko, czego potrzebują kolejne etapy - nikt dalej nie czyta kodu.
    ModuleNote to połączenie NoteFlow i NoteDetails (pola przebiegu pierwsze); model zwraca je w dwóch odpowiedziach,
    a analityk składa notatkę w kodzie, bo cały schemat ma więcej pól, niż przyjmuje bramka. Notatka jest zapisywana
    i czytana przez kolejne etapy jako jeden obiekt; w tabelach niepewność oznacza tekst [wywnioskowane].

    Uwaga: notatki z kawałków długiej funkcji (krok 51) składa kod w jedną notatkę - numer kawałka nie jest polem
    schematu. Schemat nie ma ograniczeń liczbowych (minimum, maksimum): bramka odrzuca je w json_schema (400:
    property 'minimum' is not supported) - zakresy liczb sprawdza kod wołający. ModuleNote nie jest wysyłany do modelu.
    """


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

    _UNSUPPORTED_KEYWORDS = ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "minItems", "maxItems", "minLength", "maxLength", "pattern", "multipleOf"]

    def _build_example_note() -> ModuleNote:
        """Składa ręcznie notatkę analityka o pliku przetwarzanie.py robota 02: czynności, ustawienia, ryzyka, awarie i reszta pól.

        Po co: dane do testu zapisu i odczytu JSON bez uruchamiania analityka (krok 50); notatka ma po jednym
        przykładzie każdego rodzaju wpisu, w tym hasło wpisane wprost i wniosek z flagą pewności.

        Uwaga: treść jest ułożona ręcznie - prawdziwą notatkę zwraca analityk.
        """
        dane_wejsciowe = _guide_content.DataRef(name="dane/wejscie/*.csv", kind="file")
        dane_wyjsciowe = _guide_content.DataRef(name="dane/wyjscie/wyniki_*.json", kind="file")
        czynnosci = [
            NoteAction(title="Wczytaj listę plików zamówień", kind="step", function="run", line=45, description="", reads=[dane_wejsciowe], writes=[], certain=True),
            NoteAction(title="Nagłówek poprawny?", kind="decision", function="run", line=88, description="", reads=[], writes=[], certain=True),
            NoteAction(title="Wyślij zamówienia do API", kind="system", function="run", line=300, description="", reads=[], writes=[], certain=False),
            NoteAction(title="Zapisz wyniki", kind="step", function="run", line=380, description="", reads=[], writes=[dane_wyjsciowe], certain=True),
        ]
        ustawienia = [
            NoteSetting(
                file="",
                location="przetwarzanie.py:14",
                group="",
                key="URL",
                value="https://api.example.test/zamowienia",
                kind="system",
                plain_password=False,
                meaning="Adres API zamówień; stała w kodzie.",
                used_in=["przetwarzanie.py:300"],
                certain=True,
            ),
            NoteSetting(
                file="",
                location="przetwarzanie.py:15",
                group="",
                key="HASLO",
                value="Haslo123!",
                kind="account",
                plain_password=True,
                meaning="Hasło do API wpisane wprost w kod.",
                used_in=["przetwarzanie.py:301"],
                certain=True,
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
            requirements=[
                NoteRequirement(kind="network", name="https://api.example.test:443", detail="Wysłanie zamówień (przetwarzanie.py:300)."),
                NoteRequirement(kind="env_var", name="ROBOT_KATALOG", detail="Katalog roboczy robota. [wywnioskowane]"),
            ],
            external_dependencies=["requests - wywołania API"],
            risky_places=[NoteRisk(place="run", location="przetwarzanie.py:41-411", kind="długa funkcja", reason="Cała logika w jednej funkcji - trudno zmieniać bez ryzyka.")],
            possible_failures=[
                NoteFailure(
                    symptom="Robot kończy pracę bez pliku wyników.",
                    cause="API nie odpowiada. [wywnioskowane]",
                    where="przetwarzanie.py:run:300",
                    fix="Sprawdź dostęp do adresu API.",
                )
            ],
            extension_points=[],
            conventions=["Komunikaty logu zaczynają się od nazwy etapu."],
            maintainer_hints=["Zmiana adresu API: stała URL w przetwarzanie.py:14."],
            glossary_candidates=[NoteTerm(term="odrzucone", definition="Katalog na pliki z błędnym nagłówkiem.")],
        )
        return przykladowa_notatka

    def _empty_note() -> ModuleNote:
        """Zwraca notatkę z wypełnionymi tylko dwoma polami tekstowymi i pustą resztą (puste teksty i puste listy).

        Po co: sprawdzenie, że "nic nie wynika z kodu" jest poprawną notatką - wszystkie listy mogą być puste.
        """
        pusta_notatka = ModuleNote(
            unit_name="raport.py",
            purpose="nie wynika z kodu",
            flow_role="",
            automated_application="",
            key_functions=[],
            actions=[],
            process_steps=[],
            error_handling=[],
            inputs=[],
            outputs=[],
            settings=[],
            requirements=[],
            external_dependencies=[],
            risky_places=[],
            possible_failures=[],
            extension_points=[],
            conventions=[],
            maintainer_hints=[],
            glossary_candidates=[],
        )
        return pusta_notatka

    def _note_checks(
        note: ModuleNote,
    ) -> list[tuple[str, bool]]:
        """Sprawdza notatkę: odczyt z JSON, notatka pusta, składanie z dwóch części, schematy dla modelu (limit pól bramki), odrzucenia błędnych danych; zwraca (opis, zgodne).

        Po co: model zwraca notatkę w dwóch odpowiedziach - test pilnuje, że każdy schemat dla modelu mieści się
        w limicie pól bramki, że części dają razem dokładnie pola ModuleNote i że błędne dane są odrzucane.
        """
        pusta = _empty_note()
        problemy = _schema_problems(ModuleNote) + _schema_problems(NoteFlow) + _schema_problems(NoteDetails)
        za_duze = []
        for klasa in (Plan, NoteFlow, NoteDetails):
            if count_schema_properties(klasa) > MAX_MODEL_SCHEMA_PROPERTIES:
                za_duze.append(klasa.__name__)
        pola_czesci = list(NoteFlow.model_fields) + list(NoteDetails.model_fields)
        bez_wymaganych = False
        try:
            ModuleNote.model_validate_json('{"unit_name": "raport.py", "purpose": "x"}')
        except pydantic.ValidationError:
            bez_wymaganych = True
        zly_rodzaj = False
        try:
            NoteAction.model_validate_json('{"title": "x", "kind": "magia"}')
        except pydantic.ValidationError:
            zly_rodzaj = True
        dane_polaczone = NoteFlow.model_validate(note.model_dump(include=set(NoteFlow.model_fields))).model_dump()
        dane_polaczone.update(NoteDetails.model_validate(note.model_dump(include=set(NoteDetails.model_fields))).model_dump())
        puste_listy = pusta.actions == [] and pusta.extension_points == [] and pusta.settings == []
        wyniki = [
            ("odczyt notatki z JSON równy oryginałowi", ModuleNote.model_validate_json(note.model_dump_json()) == note),
            ("notatka z pustymi punktami rozszerzeń przechodzi walidację", note.extension_points == []),
            ("notatka z pustymi listami i tekstami przechodzi walidację i odczyt z JSON", puste_listy and ModuleNote.model_validate_json(pusta.model_dump_json()) == pusta),
            (f"schematy notatki bez anyOf, bez ograniczeń i z opisem przy każdym polu (problemy: {problemy})", not problemy),
            (f"schematy dla modelu (Plan, NoteFlow, NoteDetails) mają najwyżej {MAX_MODEL_SCHEMA_PROPERTIES} pól (za duże: {za_duze})", not za_duze),
            ("pola NoteFlow i NoteDetails dają razem dokładnie pola ModuleNote, przebieg pierwszy", pola_czesci == list(ModuleNote.model_fields)),
            ("notatka złożona z dwóch części jest równa oryginałowi", ModuleNote.model_validate(dane_polaczone) == note),
            ("notatka bez wymaganych pól odrzucona", bez_wymaganych),
            ("nieznany rodzaj czynności odrzucony", zly_rodzaj),
        ]
        return wyniki

    def _schema_problems(
        model_class,
    ) -> list[str]:
        """Zwraca listę problemów schematu JSON klasy dla modelu: wariant anyOf, ograniczenie liczbowe lub długościowe albo pole bez opisu (pusta lista = schemat poprawny).

        Po co: model widzi tylko schemat JSON; wariant anyOf nie był sprawdzony na bramce na mieście, bramka na Kwadracie
        odrzuca ograniczenia (np. minimum dla liczb całkowitych: błąd 400 przy pierwszym prawdziwym wywołaniu), a pole bez
        opisu model wypełnia po omacku.
        """
        schemat = model_class.model_json_schema()
        problemy = []
        if "anyOf" in json.dumps(schemat):
            problemy.append("schemat zawiera wariant anyOf")
        for slowo in _UNSUPPORTED_KEYWORDS:
            if f'"{slowo}"' in json.dumps(schemat):
                problemy.append(f"schemat zawiera ograniczenie {slowo} (bramka na Kwadracie go odrzuca)")
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
        print(f"\nProblemy schematu JSON klasy Plan (anyOf, ograniczenia, pola bez opisu): {problemy_planu}")
        print(f"Plan bez wymaganych pól odrzucony przy odczycie: {brakujace_odrzucone}")
        notatka = _build_example_note()
        print("=== ModuleNote (przetwarzanie.py, ułożona ręcznie) ===\n")
        print(notatka.model_dump_json(indent=2))
        print()
        sprawdzenia_notatki = _note_checks(notatka)
        for klasa in (Plan, NoteFlow, NoteDetails, ModuleNote):
            print(f"  pola schematu {klasa.__name__} po rozwinięciu klas: {count_schema_properties(klasa)} (limit testu {MAX_MODEL_SCHEMA_PROPERTIES}, bramka odrzuca od 49)")
        for klasa in (_guide_content.FlowGraph, _guide_content.GuideBlock, _guide_content.GuideTab):
            liczba_pol = count_schema_properties(klasa)
            if liczba_pol > MAX_MODEL_SCHEMA_PROPERTIES:
                print(f"  UWAGA: schemat {klasa.__name__} ma {liczba_pol} pól - przed wysłaniem do modelu (kroki 53-55) trzeba go rozbić albo odchudzić")
            else:
                print(f"  schemat {klasa.__name__}: {liczba_pol} pól (mieści się w limicie)")
        notatka_zgodna = True
        for opis, zgodne_sprawdzenie in sprawdzenia_notatki:
            print(f"  {opis}: {zgodne_sprawdzenie}")
            if not zgodne_sprawdzenie:
                notatka_zgodna = False
        zgodne = is_equal and plan_zgodny and not problemy_planu and brakujace_odrzucone and notatka_zgodna
        print(f"\nzgodne z oczekiwaniem: {zgodne}")

    manual_test()
