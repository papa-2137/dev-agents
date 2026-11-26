"""Wyniki w analizowanym projekcie: katalog dev_agents_doc/ ze znacznikiem oraz zapis i odczyt plików wyników.

Co robi:
    - create_run_store() przygotowuje <projekt>/dev_agents_doc/ i zwraca RunStore: katalog bez znacznika
      zakłada razem ze znacznikiem .dev_agents_output; katalog ze znacznikiem czyści (clear=True) albo zostawia
      (clear=False); pusty katalog bez znacznika przejmuje; niepusty katalog bez znacznika - błąd, nic nie usuwa,
    - RunStore zapisuje i czyta pliki wyników (tekst i JSON z klas Pydantic) po nazwach względnych do katalogu
      wyników, np. "project_map.json" albo "notes/main.py.json"; brakujące podkatalogi tworzy sam.

Dlaczego istnieje: dokumentacja leży obok kodu robota, w cudzym repozytorium - narzędzie może tam pisać
wyłącznie do dev_agents_doc/ i usuwać wyłącznie katalog, który samo oznaczyło. Brak prawa zapisu wychodzi
od razu przy starcie (przy zapisie znacznika), a nie po kilku minutach pracy agentów. Pliki pośrednie
(mapa, notatki, plan) pozwalają obejrzeć każdy etap i powtórzyć go bez ponownego wywoływania modelu.

Rola: moduł rdzenia towaru - jedyne miejsce, przez które towar zapisuje cokolwiek w analizowanym projekcie.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.output
        na kopii robota testowego 02 w katalogu tymczasowym (bez robota - na małym projekcie tymczasowym):
        zapis i odczyt mapy projektu, czyszczenie przy drugim starcie, clear=False, katalog obcy (niepusty
        i pusty bez znacznika), zwykły plik w miejscu dev_agents_doc, nazwa wychodząca poza katalog wyników.
        Prawdziwe roboty nie są zmieniane; robot 01 nie jest kopiowany (zawiera plik sekretu).
"""

import os
import shutil

import pydantic

OUTPUT_DIR_NAME = "dev_agents_doc"
_MARKER_NAME = ".dev_agents_output"
_MARKER_TEXT = "Katalog wyników narzędzia dev-agents. Zawartość jest usuwana przy każdym uruchomieniu.\n"


# --- Katalog wyników ---


class RunStore:
    """Dostęp do plików w katalogu wyników: zapis i odczyt tekstu oraz JSON (klasy Pydantic), nazwy względne do katalogu.

    Po co: etapy towaru podają tylko nazwę pliku i nie muszą wiedzieć, gdzie leżą wyniki ani jak je zapisać.
    """

    def __init__(
        self,
        output_dir: str,
    ):
        """Zapamiętuje ścieżkę bezwzględną katalogu wyników (katalog przygotowuje create_run_store).

        Po co: wszystkie metody budują ścieżki od tego katalogu.
        """
        self.output_dir = output_dir

    def path(
        self,
        name: str,
    ) -> str:
        """Zwraca ścieżkę bezwzględną pliku o nazwie względnej; nazwa wychodząca poza katalog wyników - ValueError.

        Po co: jedno miejsce składania ścieżek, które pilnuje, żeby zapis nigdy nie wyszedł poza dev_agents_doc/
        (np. nazwa z "..", zbudowana z cudzej ścieżki pliku).
        """
        sciezka = os.path.normpath(os.path.join(self.output_dir, name))
        if os.path.commonpath([sciezka, self.output_dir]) != self.output_dir:
            komunikat_bledu = f"Nazwa pliku wyników '{name}' wychodzi poza katalog {self.output_dir}"
            raise ValueError(komunikat_bledu)
        return sciezka

    def save_text(
        self,
        name: str,
        text: str,
    ) -> str:
        """Zapisuje tekst do pliku w katalogu wyników (UTF-8, nadpisuje istniejący) i zwraca ścieżkę pliku.

        Po co: wyniki tekstowe, np. guide.html; brakujący podkatalog (np. notes/) jest tworzony.
        """
        sciezka = self.path(name)
        os.makedirs(os.path.dirname(sciezka), exist_ok=True)
        with open(sciezka, "w", encoding="utf-8") as plik:
            plik.write(text)
        return sciezka

    def save_json(
        self,
        name: str,
        model: pydantic.BaseModel,
    ) -> str:
        """Zapisuje obiekt Pydantic jako JSON z wcięciami (UTF-8) i zwraca ścieżkę pliku.

        Po co: wyniki etapów to klasy ze schemas.py - JSON da się obejrzeć w edytorze i wczytać w kolejnym etapie.
        """
        sciezka = self.save_text(name, model.model_dump_json(indent=2))
        return sciezka

    def load_json(
        self,
        name: str,
        model_class: type[pydantic.BaseModel],
    ) -> pydantic.BaseModel:
        """Wczytuje plik JSON z katalogu wyników jako obiekt podanej klasy Pydantic.

        Po co: kolejny albo powtórzony etap czyta wynik poprzedniego zamiast liczyć go od nowa.

        Uwaga: plik niezgodny ze schematem kończy się błędem walidacji Pydantica.
        """
        with open(self.path(name), encoding="utf-8") as plik:
            tekst_json = plik.read()
        obiekt = model_class.model_validate_json(tekst_json)
        return obiekt


def _has_marker(
    output_dir: str,
) -> bool:
    """Zwraca True, gdy katalog wyników ma znacznik narzędzia.

    Po co: tylko oznaczony katalog wolno wyczyścić.
    """
    czy_znacznik = os.path.isfile(os.path.join(output_dir, _MARKER_NAME))
    return czy_znacznik


def create_run_store(
    project_root: str,
    clear: bool = True,
) -> RunStore:
    """Przygotowuje <projekt>/dev_agents_doc/ ze znacznikiem i zwraca RunStore; katalog obcy albo brak zapisu - błąd.

    Po co: w katalogu wyników są tylko pliki z ostatniego uruchomienia (clear=True), a cudze pliki nigdy nie
    są usuwane. clear=False zostawia poprzednie wyniki - do pracy na wynikach poprzedniego przebiegu.

    Uwaga: niepusty katalog bez znacznika → ValueError i nic nie usunięte; pusty katalog bez znacznika
    jest przejmowany. Brak możliwości zapisu (uprawnienia, plik w miejscu katalogu) → OSError z czytelnym
    opisem i ścieżką.
    """
    katalog = os.path.join(os.path.abspath(project_root), OUTPUT_DIR_NAME)
    if os.path.isdir(katalog) and not _has_marker(katalog) and os.listdir(katalog):
        komunikat_bledu = (
            f"Katalog {katalog} istnieje, nie ma znacznika {_MARKER_NAME} i nie jest pusty - "
            "nie należy do dev-agents, niczego w nim nie usuwam. Przenieś go albo usuń ręcznie."
        )
        raise ValueError(komunikat_bledu)
    if clear and _has_marker(katalog):
        shutil.rmtree(katalog)
    try:
        os.makedirs(katalog, exist_ok=True)
        with open(os.path.join(katalog, _MARKER_NAME), "w", encoding="utf-8") as plik:
            plik.write(_MARKER_TEXT)
    except OSError as blad:
        komunikat_bledu = f"Nie mogę zapisać wyników w {katalog}: {blad}"
        raise OSError(komunikat_bledu) from blad
    magazyn = RunStore(katalog)
    return magazyn


# --- Test ręczny ---

if __name__ == "__main__":
    import tempfile

    import dev_agents.config as _config
    import dev_agents.scanner as _scanner
    import dev_agents.schemas as _schemas

    def _make_project_copy(
        temp_dir: str,
        repo_dir: str,
    ) -> tuple[str, str]:
        """Kopiuje robota 02 do katalogu tymczasowego (bez robota - tworzy mały projekt). Zwraca (ścieżka, opis źródła).

        Po co: test zapisuje w kopii, nigdy w prawdziwym robocie.
        """
        robot_02 = os.path.normpath(os.path.join(repo_dir, "..", "..", "tests", "02_robot_bez_frameworku"))
        kopia = os.path.join(temp_dir, "robot")
        if os.path.isdir(robot_02):
            shutil.copytree(robot_02, kopia)
            wynik = (kopia, f"kopia {robot_02}")
            return wynik
        os.makedirs(kopia)
        with open(os.path.join(kopia, "main.py"), "w", encoding="utf-8") as plik:
            plik.write("print('robot')\n")
        wynik = (kopia, "brak robota 02 - mały projekt tymczasowy")
        return wynik

    def _list_output(
        output_dir: str,
    ) -> list[str]:
        """Zwraca posortowane ścieżki względne plików w katalogu wyników (separator "/").

        Po co: wynik testu widać jako listę plików.
        """
        pliki = []
        for katalog, _podkatalogi, nazwy in os.walk(output_dir):
            for nazwa in nazwy:
                sciezka = os.path.relpath(os.path.join(katalog, nazwa), output_dir)
                pliki.append(sciezka.replace(os.sep, "/"))
        posortowane = sorted(pliki)
        return posortowane

    def _error_text(
        function,
        *args,
    ) -> str:
        """Wywołuje funkcję i zwraca "brak błędu" albo nazwę i treść zgłoszonego wyjątku.

        Po co: przypadki błędne testu pokazują komunikat zamiast przerywać test.
        """
        try:
            function(*args)
        except (OSError, ValueError) as blad:
            opis = f"{type(blad).__name__}: {blad}"
            return opis
        opis = "BŁĄD TESTU: brak błędu"
        return opis

    def _run_cases(
        temp_dir: str,
        repo_dir: str,
    ) -> list[tuple[str, str]]:
        """Wykonuje przypadki testu i zwraca listę (tytuł, wynik).

        Po co: logika testu oddzielona od wypisywania.
        """
        wyniki = []
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        projekt, zrodlo = _make_project_copy(temp_dir, repo_dir)
        wyniki.append(("Projekt testowy", zrodlo))

        magazyn = create_run_store(projekt)
        mapa = _scanner.build_project_map(projekt, app_config.scan)
        magazyn.save_json("project_map.json", mapa)
        magazyn.save_text("notes/przyklad.txt", "notatka\n")
        odczytana = magazyn.load_json("project_map.json", _schemas.ProjectMap)
        wyniki.append(("1. Zapis i odczyt mapy", f"pliki: {_list_output(magazyn.output_dir)}; odczyt zgodny: {odczytana == mapa}"))

        magazyn.save_text("stary.txt", "z poprzedniego uruchomienia\n")
        create_run_store(projekt, clear=False)
        wyniki.append(("2. Start z clear=False", f"pliki: {_list_output(magazyn.output_dir)}"))
        create_run_store(projekt)
        wyniki.append(("3. Drugi start (clear=True)", f"pliki: {_list_output(magazyn.output_dir)}"))

        obcy = os.path.join(temp_dir, "obcy")
        os.makedirs(os.path.join(obcy, OUTPUT_DIR_NAME))
        cudzy_plik = os.path.join(obcy, OUTPUT_DIR_NAME, "moj_plik.txt")
        with open(cudzy_plik, "w", encoding="utf-8") as plik:
            plik.write("cudze\n")
        opis_bledu = _error_text(create_run_store, obcy)
        wyniki.append(("4. Niepusty katalog bez znacznika", f"{opis_bledu}; cudzy plik nadal jest: {os.path.isfile(cudzy_plik)}"))

        pusty = os.path.join(temp_dir, "pusty")
        os.makedirs(os.path.join(pusty, OUTPUT_DIR_NAME))
        magazyn_pusty = create_run_store(pusty)
        wyniki.append(("5. Pusty katalog bez znacznika", f"przejęty, pliki: {_list_output(magazyn_pusty.output_dir)}"))

        zablokowany = os.path.join(temp_dir, "zablokowany")
        os.makedirs(zablokowany)
        with open(os.path.join(zablokowany, OUTPUT_DIR_NAME), "w", encoding="utf-8") as plik:
            plik.write("zwykły plik zamiast katalogu\n")
        wyniki.append(("6. Plik w miejscu dev_agents_doc (brak zapisu)", _error_text(create_run_store, zablokowany)))

        wyniki.append(("7. Nazwa wychodząca poza katalog wyników", _error_text(magazyn.save_text, "../poza.txt", "x")))
        return wyniki

    def _print_cases(
        cases: list[tuple[str, str]],
    ) -> None:
        """Wypisuje wyniki przypadków testu.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        for tytul, wynik in cases:
            print(f"--- {tytul} ---\n  {wynik}\n")

    def manual_test():
        """Uruchamia przypadki testu w katalogu tymczasowym i usuwa go na końcu.

        Po co: sprawdzenie zapisu, czyszczenia i ochrony cudzych plików bez dotykania prawdziwych robotów.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        temp_dir = tempfile.mkdtemp()
        try:
            _print_cases(_run_cases(temp_dir, repo_dir))
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
