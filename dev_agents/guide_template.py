"""Szablon przewodnika: zakładki i sekcje z pliku YAML (paths.guide_template), sprawdzone przy wczytaniu.

Co robi:
    - load_template() wczytuje szablon do klas Pydantic (GuideTemplate -> TemplateTab -> TemplateSection) i sprawdza
      go zwykłym kodem: typ i źródło sekcji z zamkniętej listy, unikalne id zakładek i sekcji, kolumny przy
      tabelach, znane technologie w filtrze sekcji; każdy błąd to czytelny komunikat z id sekcji,
    - sections_for_technology() zwraca kopię szablonu tylko z sekcjami dla technologii projektu (pole technologies).

Dlaczego istnieje: struktura przewodnika (zakładki, sekcje, polecenia dla pisarzy) leży poza kodem - zespół zmienia
ją w YAML-u bez programowania. Z jednego szablonu korzystają renderer (co i jakim typem narysować), pisarze
(co napisać) i karty „jak czytać”. Błąd w szablonie wychodzi przy starcie, zanim agenci zużyją tokeny.

Rola: moduł rdzenia towaru, używany przez renderer (faza D) i pisarzy (faza F).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.guide_template
        zakładki i sekcje szablonu z configu dla technologii python; filtr technologii na kopii szablonu w pamięci
        (sekcja z technologies: [python] jest dla python, znika dla uipath); błędy dla czterech zepsutych kopii
        (nieznany typ, zdublowane id, nieznana technologia, tabela bez kolumn)
"""

import yaml
from pydantic import BaseModel

import dev_agents.technologies.registry as _registry

SECTION_TYPES = [
    "text",
    "list",
    "steps",
    "code",
    "table",
    "glossary",
    "io",
    "cards",
    "config",
    "tree",
    "dependency_graph",
    "flow",
    "paths",
    "recipes",
]
SECTION_SOURCES = ["llm", "scanner", "code"]


# --- Schemat szablonu ---


class TemplateSection(BaseModel):
    """Sekcja przewodnika: id, tytuł, typ wyświetlania, źródło treści, czy wymagana, polecenie, kolumny i filtr technologii.

    Po co: renderer wie, jak narysować sekcję, a pisarz - co w niej napisać.
    """

    id: str
    title: str
    type: str  # jeden z SECTION_TYPES
    source: str  # llm | scanner | code
    required: bool  # True = zawsze widoczna („nie wynika z kodu” zamiast pustki)
    instruction: str = ""  # polecenie dla pisarza albo opis danych
    columns: list[str] = []  # kolumny tabeli (wymagane przy type: table)
    technologies: list[str] = []  # [] = sekcja dla wszystkich technologii
    writer_adds: bool = False  # True = sekcja ze źródłem scanner/code, do której pisarz dokłada wiersze albo zdania


class TemplateTab(BaseModel):
    """Zakładka przewodnika: id, tytuł, karta „jak czytać”, stałe zdanie pod tytułem i sekcje w kolejności.

    Po co: kolejność i opis zakładek w jednym miejscu - także dla kart na stronie startowej.
    """

    id: str
    title: str
    card_label: str  # np. "6 · awaria"
    card_text: str
    lead: str = ""
    sections: list[TemplateSection]


class GuideTemplate(BaseModel):
    """Cały szablon przewodnika: zakładki w kolejności wyświetlania.

    Po co: jeden typowany obiekt zamiast surowego słownika z YAML-a.
    """

    tabs: list[TemplateTab]


# --- Sprawdzanie ---


def _check_section(
    section: TemplateSection,
    known_technologies: list[str],
) -> None:
    """Sprawdza typ, źródło, kolumny i filtr technologii jednej sekcji; przy błędzie rzuca ValueError z id sekcji.

    Po co: literówka w szablonie (np. typ "tabela") wychodzi przy starcie z listą dozwolonych wartości.
    """
    if section.type not in SECTION_TYPES:
        komunikat_bledu = f"Sekcja '{section.id}': nieznany typ '{section.type}'. Dozwolone: {SECTION_TYPES}"
        raise ValueError(komunikat_bledu)
    if section.source not in SECTION_SOURCES:
        komunikat_bledu = f"Sekcja '{section.id}': nieznane źródło '{section.source}'. Dozwolone: {SECTION_SOURCES}"
        raise ValueError(komunikat_bledu)
    if section.type == "table" and not section.columns:
        komunikat_bledu = f"Sekcja '{section.id}': tabela bez kolumn (pole columns)"
        raise ValueError(komunikat_bledu)
    for technologia in section.technologies:
        if technologia not in known_technologies:
            komunikat_bledu = f"Sekcja '{section.id}': nieznana technologia '{technologia}'. Dozwolone: {known_technologies}"
            raise ValueError(komunikat_bledu)


def _check_unique_ids(
    template: GuideTemplate,
) -> None:
    """Sprawdza, czy id zakładek są unikalne wśród zakładek, a id sekcji w całym szablonie; przy powtórzeniu rzuca ValueError.

    Po co: renderer i pisarze odwołują się do sekcji po id - dwie sekcje o tym samym id nadpisałyby sobie treść.
    """
    id_zakladek = []
    id_sekcji = []
    for zakladka in template.tabs:
        if zakladka.id in id_zakladek:
            komunikat_bledu = f"Zdublowane id zakładki: '{zakladka.id}'"
            raise ValueError(komunikat_bledu)
        id_zakladek.append(zakladka.id)
        for sekcja in zakladka.sections:
            if sekcja.id in id_sekcji:
                komunikat_bledu = f"Zdublowane id sekcji: '{sekcja.id}' (zakładka '{zakladka.id}')"
                raise ValueError(komunikat_bledu)
            id_sekcji.append(sekcja.id)


def _build_template(
    raw_template: dict,
) -> GuideTemplate:
    """Zamienia słownik z YAML-a na GuideTemplate i sprawdza każdą sekcję oraz unikalność id.

    Po co: oddziela budowę szablonu od czytania pliku - test sprawdza na niej zepsute kopie w pamięci.

    Uwaga: brak wymaganego pola (np. type) zgłasza Pydantic jako ValidationError ze ścieżką pola.
    """
    szablon = GuideTemplate(**raw_template)
    znane_technologie = []
    for technologia in _registry.available_technologies():
        znane_technologie.append(technologia.name)
    for zakladka in szablon.tabs:
        for sekcja in zakladka.sections:
            _check_section(sekcja, znane_technologie)
    _check_unique_ids(szablon)
    return szablon


def load_template(
    path: str,
) -> GuideTemplate:
    """Wczytuje szablon przewodnika z pliku YAML i zwraca sprawdzony GuideTemplate.

    Po co: jedyne wejście do szablonu dla renderera i pisarzy.
    """
    with open(path, encoding="utf-8") as plik:
        surowy_szablon = yaml.safe_load(plik)
    szablon = _build_template(surowy_szablon)
    return szablon


def sections_for_technology(
    template: GuideTemplate,
    technology: str,
) -> GuideTemplate:
    """Zwraca kopię szablonu tylko z sekcjami dla podanej technologii (sekcje bez filtra zostają zawsze).

    Po co: np. sekcja tylko dla Pythona nie pojawia się w przewodniku robota UiPath.

    Uwaga: zakładka zostaje także wtedy, gdy po filtrowaniu nie ma sekcji - jej usunięcie to decyzja renderera.
    """
    kopia = template.model_copy(deep=True)
    for zakladka in kopia.tabs:
        sekcje = []
        for sekcja in zakladka.sections:
            if not sekcja.technologies or technology in sekcja.technologies:
                sekcje.append(sekcja)
        zakladka.sections = sekcje
    return kopia


# --- Test ręczny ---

if __name__ == "__main__":
    import copy
    import os

    import dev_agents.config as _config

    def _section_ids(
        template: GuideTemplate,
    ) -> list[str]:
        """Zwraca id wszystkich sekcji szablonu w kolejności.

        Po co: porównanie szablonu przed i po filtrowaniu.
        """
        identyfikatory = []
        for zakladka in template.tabs:
            for sekcja in zakladka.sections:
                identyfikatory.append(sekcja.id)
        return identyfikatory

    def _error_text(
        raw_template: dict,
    ) -> str:
        """Buduje szablon z kopii i zwraca treść zgłoszonego błędu albo informację, że błędu nie było.

        Po co: przypadki błędne testu pokazują komunikat zamiast przerywać test.
        """
        try:
            _build_template(raw_template)
        except ValueError as blad:
            opis = f"{type(blad).__name__}: {blad}"
            return opis
        opis = "BŁĄD TESTU: zepsuty szablon przeszedł bez błędu"
        return opis

    def _print_template(
        template: GuideTemplate,
        technology: str,
    ) -> None:
        """Wypisuje zakładki i sekcje szablonu: id, typ, źródło, czy wymagana, kolumny i filtr technologii.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"=== Szablon dla technologii: {technology} ===")
        for zakladka in template.tabs:
            print(f"  [{zakladka.id}] {zakladka.title}  ({zakladka.card_label})")
            for sekcja in zakladka.sections:
                wymagana = "wymagana"
                if not sekcja.required:
                    wymagana = "opcjonalna"
                dodatki = ""
                if sekcja.columns:
                    dodatki = f"  kolumny: {sekcja.columns}"
                if sekcja.technologies:
                    dodatki = f"{dodatki}  technologie: {sekcja.technologies}"
                print(f"      {sekcja.id:<22} {sekcja.type:<17} {sekcja.source:<8} {wymagana}{dodatki}")
        print()

    def manual_test():
        """Wczytuje szablon z configu, pokazuje go dla python, sprawdza filtr technologii i cztery zepsute kopie.

        Po co: szybkie sprawdzenie szablonu i czytelności błędów bez renderowania przewodnika.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        szablon = load_template(app_config.paths.guide_template)
        _print_template(sections_for_technology(szablon, "python"), "python")

        with open(app_config.paths.guide_template, encoding="utf-8") as plik:
            surowy = yaml.safe_load(plik)
        z_filtrem = copy.deepcopy(surowy)
        z_filtrem["tabs"][0]["sections"][6]["technologies"] = ["python"]
        szablon_z_filtrem = _build_template(z_filtrem)
        print("--- Filtr technologii (kopia: sekcja 'instalacja' tylko dla python) ---")
        print(f"  python: 'instalacja' w sekcjach = {'instalacja' in _section_ids(sections_for_technology(szablon_z_filtrem, 'python'))}")
        print(f"  uipath: 'instalacja' w sekcjach = {'instalacja' in _section_ids(sections_for_technology(szablon_z_filtrem, 'uipath'))}\n")

        zly_typ = copy.deepcopy(surowy)
        zly_typ["tabs"][0]["sections"][4]["type"] = "tabela"
        print(f"--- Nieznany typ ('tabela') ---\n  {_error_text(zly_typ)}\n")

        zdublowane = copy.deepcopy(surowy)
        zdublowane["tabs"][6]["sections"][0]["id"] = "metryczka"
        print(f"--- Zdublowane id sekcji ('metryczka') ---\n  {_error_text(zdublowane)}\n")

        zla_technologia = copy.deepcopy(surowy)
        zla_technologia["tabs"][0]["sections"][6]["technologies"] = ["pyton"]
        print(f"--- Nieznana technologia w filtrze ('pyton') ---\n  {_error_text(zla_technologia)}\n")

        bez_kolumn = copy.deepcopy(surowy)
        del bez_kolumn["tabs"][5]["sections"][0]["columns"]
        print(f"--- Tabela bez kolumn ('awarie') ---\n  {_error_text(bez_kolumn)}\n")

    manual_test()
