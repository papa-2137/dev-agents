"""Schematy treści przewodnika i diagramu przepływu - to, co zwracają agenci i co renderer zamienia na HTML.

Co zawiera:
    - diagram przepływu: FlowNode (klocek), FlowEdge (strzałka), FlowGraph (całość) - układ na rysunku liczy kod,
      model zwraca tylko graf,
    - treść sekcji: GuideBlock - jedna klasa z polami dla wszystkich typów sekcji szablonu (text -> paragraphs,
      list -> items, steps -> steps, table -> rows, glossary -> terms, io -> inputs/outputs, paths -> paths,
      recipes -> recipes, config -> config_items, code -> code); pola nieużywane przez typ sekcji zostają puste,
      a pusty blok wymaganej sekcji renderer pokazuje jako „nie wynika z kodu”,
    - klasy pomocnicze bloków: Step, GlossaryTerm, IoItem, PathStep, ProcessPath, RecipeFile, Recipe, ConfigItem
      (wpis metryczki),
    - całość: GuideTab (odpowiedź jednego pisarza - bloki jednej zakładki) i GuideContent (diagram + zakładki).

Dlaczego istnieje: umowa między agentami a rendererem. Jedna klasa bloku daje jeden prosty schemat JSON dla
structured output (bez wariantów anyOf, których nie sprawdzaliśmy na bramce na mieście). Każde pole wypełniane
przez model ma Field(description=...) - model widzi tylko schemat JSON. Typy cards, tree i dependency_graph składa
kod z mapy projektu i szablonu, więc nie mają tu pól.

Rola: moduł używany przez renderer (faza D, na treści przykładowej) i przez agentów (faza F).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.guide_content
        składa ręcznie przykładową treść z makiety (diagram z decyzją i pętlą, metryczka z hasłem w pliku i wpisem
        „w kodzie”, ryzykowne miejsca), wypisuje JSON i sprawdza zgodność po odczycie (oczekiwane: True)
"""

import typing

import pydantic


# --- Diagram przepływu ---


class FlowNode(pydantic.BaseModel):
    """Klocek diagramu przepływu: jedna czynność robota z modułem, funkcjami i danymi.

    Po co: diagram i lista „Krok po kroku” pod nim powstają z tych samych klocków.
    """

    id: str = pydantic.Field(description="Krótki, unikalny identyfikator klocka, np. n1, n2.")
    kind: typing.Literal["start", "end", "step", "system", "decision"] = pydantic.Field(
        description="Rodzaj: start, end (koniec), step (czynność), system (kontakt z systemem zewnętrznym), decision (rozgałęzienie)."
    )
    label: str = pydantic.Field(description="Napis na klocku: kilka słów językiem biznesowo-technicznym.")
    description: str = pydantic.Field(default="", description="Jedno-dwa zdania: co robot robi w tym kroku i po co.")
    module: str = pydantic.Field(default="", description="Plik kodu, w którym dzieje się krok, np. przetwarzanie.py.")
    functions: list[str] = pydantic.Field(default=[], description="Funkcje w kolejności wywołania, z linią, np. run:120.")
    reads: list[str] = pydantic.Field(default=[], description="Co krok czyta: pliki, zmienne, systemy, dane w pamięci.")
    writes: list[str] = pydantic.Field(default=[], description="Co krok zapisuje albo zwraca.")
    certain: bool = pydantic.Field(default=True, description="False, gdy krok wywnioskowano, a nie zapisano wprost w kodzie.")


class FlowEdge(pydantic.BaseModel):
    """Strzałka diagramu: przejście z klocka do klocka, z opisem gałęzi albo pętli.

    Po co: kolejność, rozgałęzienia i pętle procesu.
    """

    source: str = pydantic.Field(description="Id klocka, z którego wychodzi strzałka.")
    target: str = pydantic.Field(description="Id klocka, do którego prowadzi strzałka.")
    label: str = pydantic.Field(default="", description="Opis przejścia, np. warunek gałęzi: tak / nie / błąd.")
    kind: typing.Literal["normal", "branch", "loop"] = pydantic.Field(
        default="normal", description="normal (zwykłe przejście), branch (gałąź decyzji), loop (powrót pętli)."
    )


class FlowGraph(pydantic.BaseModel):
    """Diagram przepływu: klocki i strzałki; układ na rysunku liczy kod.

    Po co: zakładka Przepływ działania i odwołania z zakładki Ścieżki procesu.
    """

    nodes: list[FlowNode] = pydantic.Field(description="Klocki diagramu: dokładnie jeden start, co najmniej jeden end.")
    edges: list[FlowEdge] = pydantic.Field(description="Strzałki między klockami.")


# --- Elementy bloków ---


class Step(pydantic.BaseModel):
    """Krok instrukcji: tytuł, opis i opcjonalne polecenia do skopiowania.

    Po co: sekcje typu steps (np. Instalacja i uruchomienie).
    """

    title: str = pydantic.Field(description="Krótki tytuł kroku, np. Środowisko Python.")
    text: str = pydantic.Field(default="", description="Jedno-dwa zdania wyjaśnienia.")
    code: str = pydantic.Field(default="", description="Polecenia do skopiowania (puste, gdy brak).")


class GlossaryTerm(pydantic.BaseModel):
    """Pojęcie ze słowniczka: termin i definicja.

    Po co: sekcje typu glossary i dymki z definicją w tekście przewodnika.
    """

    term: str = pydantic.Field(description="Termin dokładnie w formie użytej w przewodniku.")
    definition: str = pydantic.Field(description="Definicja w jednym zdaniu.")


class IoItem(pydantic.BaseModel):
    """Wejście albo wyjście robota: co, gdzie w kodzie i opis.

    Po co: sekcje typu io (Wejście i wyjście).
    """

    name: str = pydantic.Field(description="Co: plik, system albo dane, np. dane/wejscie/*.csv.")
    location: str = pydantic.Field(default="", description="Gdzie w kodzie, np. przetwarzanie.py:52.")
    description: str = pydantic.Field(default="", description="Jedno zdanie: format, kto dostarcza, co zawiera.")


class PathStep(pydantic.BaseModel):
    """Krok ścieżki procesu z odwołaniem do klocka diagramu.

    Po co: numery w kółkach w zakładce Ścieżki procesu prowadzą do klocków diagramu.
    """

    text: str = pydantic.Field(description="Opis kroku na tej ścieżce.")
    node_id: str = pydantic.Field(default="", description="Id klocka diagramu, którego dotyczy krok (puste, gdy żaden).")


class ProcessPath(pydantic.BaseModel):
    """Ścieżka procesu: nazwa, rodzaj i kroki.

    Po co: sekcje typu paths - wszystkie drogi, którymi może pójść robot.
    """

    name: str = pydantic.Field(description="Nazwa ścieżki, np. Poprawny plik zamówień.")
    kind: typing.Literal["main", "alternative", "error"] = pydantic.Field(
        description="main (ścieżka główna), alternative (alternatywna), error (błąd)."
    )
    steps: list[PathStep] = pydantic.Field(description="Kroki ścieżki w kolejności.")


class RecipeFile(pydantic.BaseModel):
    """Plik w przepisie: ścieżka, co zmienić i czy to nowy plik.

    Po co: przepisy pokazują pliki do zmiany (nowy plik w czerwonej ramce).
    """

    path: str = pydantic.Field(description="Ścieżka pliku względem katalogu projektu.")
    change: str = pydantic.Field(description="Co zmienić albo dodać w tym pliku.")
    is_new: bool = pydantic.Field(default=False, description="True, gdy plik trzeba utworzyć.")


class Recipe(pydantic.BaseModel):
    """Przepis na zmianę w robocie: kiedy użyć, pliki i kroki.

    Po co: sekcje typu recipes (Zmiany i rozszerzenia).
    """

    title: str = pydantic.Field(description="Tytuł przepisu, np. Nowy format pliku wsadowego.")
    when: str = pydantic.Field(description="Kiedy użyć przepisu - jedno zdanie.")
    files: list[RecipeFile] = pydantic.Field(default=[], description="Pliki do zmiany albo utworzenia.")
    steps: list[str] = pydantic.Field(default=[], description="Kroki w kolejności.")


class ConfigItem(pydantic.BaseModel):
    """Wpis metryczki: ustawienie robota z pliku konfiguracyjnego albo ze stałej w kodzie.

    Po co: kafelki i tabela „Pełna konfiguracja” w zakładce Przegląd i uruchomienie.

    Uwaga: hasło wpisane wprost jest pokazane dosłownie (plain_password=True daje czerwony znacznik „hasło w pliku”
    i trafia do „Ryzykownych miejsc”) - decyzja użytkownika: niczego nie ukrywamy.
    """

    file: str = pydantic.Field(default="", description="Plik konfiguracyjny, np. config.yml; puste, gdy ustawienie jest stałą w kodzie.")
    location: str = pydantic.Field(default="", description="Dla stałej w kodzie: plik i linia, np. przetwarzanie.py:14.")
    group: str = pydantic.Field(default="", description="Sekcja pliku konfiguracyjnego, np. parabank; puste, gdy brak.")
    key: str = pydantic.Field(description="Nazwa klucza albo stałej, np. url, INPUT_DIR.")
    value: str = pydantic.Field(description="Wartość przepisana dosłownie z pliku albo kodu.")
    kind: typing.Literal["system", "account", "env_var", "input_file", "output_file", "log", "switch", "other"] = pydantic.Field(
        description="Rodzaj: system (adres systemu zewnętrznego), account (konto), env_var (nazwa zmiennej środowiskowej), input_file, output_file, log, switch (przełącznik), other."
    )
    plain_password: bool = pydantic.Field(default=False, description="True, gdy wartość to hasło albo token wpisany wprost.")
    meaning: str = pydantic.Field(description="Znaczenie ustawienia w jednym zdaniu - z kodu, który go używa.")
    used_in: list[str] = pydantic.Field(default=[], description="Miejsca użycia w kodzie, np. main.py:139.")
    certain: bool = pydantic.Field(default=True, description="False, gdy znaczenie wywnioskowano, a nie wynika wprost z kodu.")


# --- Bloki, zakładki, całość ---


class GuideBlock(pydantic.BaseModel):
    """Treść jednej sekcji szablonu: section_id i pole właściwe dla typu sekcji (pozostałe puste).

    Po co: jeden prosty schemat JSON dla wszystkich typów sekcji - renderer wybiera pole po typie z szablonu.
    """

    section_id: str = pydantic.Field(description="Id sekcji z szablonu przewodnika, np. wymagania.")
    paragraphs: list[str] = pydantic.Field(default=[], description="Typ text: akapity. W sekcji opis_robota pierwszy akapit to jedno zdanie, co robi robot.")
    items: list[str] = pydantic.Field(default=[], description="Typ list: punkty listy.")
    steps: list[Step] = pydantic.Field(default=[], description="Typ steps: kroki instrukcji.")
    rows: list[list[str]] = pydantic.Field(default=[], description="Typ table: wiersze, każdy z tyloma komórkami, ile kolumn ma sekcja w szablonie.")
    terms: list[GlossaryTerm] = pydantic.Field(default=[], description="Typ glossary: pojęcia.")
    inputs: list[IoItem] = pydantic.Field(default=[], description="Typ io: wejścia robota.")
    outputs: list[IoItem] = pydantic.Field(default=[], description="Typ io: wyjścia robota.")
    paths: list[ProcessPath] = pydantic.Field(default=[], description="Typ paths: ścieżki procesu.")
    recipes: list[Recipe] = pydantic.Field(default=[], description="Typ recipes: przepisy.")
    config_items: list[ConfigItem] = pydantic.Field(default=[], description="Typ config: wpisy metryczki.")
    code: str = pydantic.Field(default="", description="Typ code: tekst do wyświetlenia bez zmian.")


class GuideTab(pydantic.BaseModel):
    """Treść jednej zakładki: id z szablonu i bloki jej sekcji - odpowiedź jednego pisarza.

    Po co: pisarze pracują równolegle, każdy nad jedną zakładką.
    """

    tab_id: str = pydantic.Field(description="Id zakładki z szablonu, np. bledy.")
    blocks: list[GuideBlock] = pydantic.Field(description="Bloki sekcji zakładki, po jednym na sekcję.")


class GuideContent(pydantic.BaseModel):
    """Cała treść przewodnika: nazwa projektu, diagram przepływu i zakładki - wejście renderera.

    Po co: renderer dostaje jeden obiekt; zapisany jako guide_content.json pozwala powtórzyć renderowanie bez modelu.
    """

    project_name: str
    flow: FlowGraph
    tabs: list[GuideTab]


# --- Test ręczny ---

if __name__ == "__main__":

    def _example_flow() -> FlowGraph:
        """Składa przykładowy diagram z makiety: start, kroki, system, decyzja z gałęziami i pętla po plikach.

        Po co: dane do testu zapisu i odczytu oraz później do renderera bez modelu.
        """
        klocki = [
            FlowNode(id="n1", kind="start", label="Start z run.bat"),
            FlowNode(id="n2", kind="step", label="Wczytaj listę plików", module="przetwarzanie.py", functions=["run:45"], reads=["dane/wejscie/*.csv"]),
            FlowNode(id="n3", kind="decision", label="Nagłówek poprawny?", module="przetwarzanie.py", functions=["run:88"]),
            FlowNode(id="n4", kind="step", label="Przelicz zamówienia", module="przetwarzanie.py", functions=["run:120"], writes=["dane/wyjscie/wyniki_*.json"]),
            FlowNode(id="n5", kind="system", label="Wyślij do API", module="przetwarzanie.py", functions=["run:300"], certain=False),
            FlowNode(id="n6", kind="end", label="Raport Excel", module="raport.py", functions=["main:13"]),
        ]
        strzalki = [
            FlowEdge(source="n1", target="n2"),
            FlowEdge(source="n2", target="n3"),
            FlowEdge(source="n3", target="n4", label="tak", kind="branch"),
            FlowEdge(source="n3", target="n2", label="nie - plik do odrzuconych", kind="loop"),
            FlowEdge(source="n4", target="n5"),
            FlowEdge(source="n5", target="n6"),
        ]
        diagram = FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    def _example_content() -> GuideContent:
        """Składa przykładową treść: metryczka z hasłem w pliku i stałą w kodzie, wymagania, ryzykowne miejsca, ścieżka.

        Po co: pokrycie najważniejszych pól bloków jednym przykładem.
        """
        metryczka = GuideBlock(
            section_id="metryczka",
            config_items=[
                ConfigItem(file="config.yml", group="parabank", key="url", value="https://parabank.parasoft.com/parabank/", kind="system", meaning="Adres aplikacji bankowej.", used_in=["main.py:139"]),
                ConfigItem(file="config.yml", group="parabank", key="password", value="Haslo123!", kind="account", plain_password=True, meaning="Hasło wpisane wprost w plik.", used_in=["main.py:140"]),
                ConfigItem(location="przetwarzanie.py:14", key="URL", value="https://api.example.test/zamowienia", kind="system", meaning="Adres API zamówień; stała w kodzie.", used_in=["przetwarzanie.py:300"], certain=False),
            ],
        )
        wymagania = GuideBlock(section_id="wymagania", rows=[["Python", "3.12", "domyślny Python z PATH (run.bat)"]])
        ryzykowne = GuideBlock(
            section_id="ryzykowne_miejsca",
            rows=[["run", "przetwarzanie.py:41-411", "długa jednostka (371 linii)", "Cały proces w jednej funkcji."]],
        )
        sciezki = GuideBlock(
            section_id="sciezki",
            paths=[ProcessPath(name="Poprawny plik", kind="main", steps=[PathStep(text="Wczytanie pliku", node_id="n2"), PathStep(text="Przeliczenie", node_id="n4")])],
        )
        tresc = GuideContent(
            project_name="02_robot_bez_frameworku",
            flow=_example_flow(),
            tabs=[
                GuideTab(tab_id="przeglad", blocks=[metryczka, wymagania]),
                GuideTab(tab_id="sciezki", blocks=[sciezki]),
                GuideTab(tab_id="bledy", blocks=[ryzykowne]),
            ],
        )
        return tresc

    def _round_trip(
        content: GuideContent,
    ) -> tuple[str, bool]:
        """Zapisuje treść do JSON, wczytuje z powrotem i zwraca (JSON, czy odczyt jest równy oryginałowi).

        Po co: guide_content.json zapisany przez towar musi wczytać się bez utraty danych.
        """
        tekst_json = content.model_dump_json(indent=2)
        odczytana = GuideContent.model_validate_json(tekst_json)
        wynik = (tekst_json, odczytana == content)
        return wynik

    def manual_test():
        """Składa przykładową treść, wypisuje ją jako JSON i wynik porównania po odczycie.

        Po co: sprawdzenie schematów bez modelu i bez renderera.
        """
        tekst_json, czy_rowne = _round_trip(_example_content())
        print(tekst_json)
        print(f"\nOdczyt z JSON zgodny z oryginałem: {czy_rowne}")

    manual_test()
