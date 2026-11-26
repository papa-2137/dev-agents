"""Kontrakt obsługi technologii: minimalne fakty o projekcie, które każda technologia podaje bez modelu.

Co robi: definiuje klasę Technology - zestaw metod, przez które rdzeń towaru (skaner, agenci) pyta o projekt:
    wymagane (bez nich technologia nie ma sensu - w klasie bazowej NotImplementedError):
        detect           - czy projekt jest w tej technologii,
        is_source        - czy plik jest kodem do analizy,
        find_entrypoints - pliki, od których startuje projekt,
    opcjonalne (w klasie bazowej domyślna odpowiedź "brak danych"):
        units            - jednostki pliku (funkcje, klasy, workflowy...) z zakresami linii,
        references       - pliki projektu i pakiety, do których plik się odwołuje.

Dlaczego istnieje: rdzeń towaru nie zna żadnego języka ani frameworku (AGENTS.md, reguła 7). Kod podaje tylko
proste, pewne fakty - numery linii, powiązania między plikami i punkty startu - a rozumienie kodu (struktura,
logika, konfiguracja, ryzyka) należy do agentów. Dzięki temu obsługa nowej technologii (UiPath, Robot
Framework, NICE) to kilkadziesiąt linii plus plik wiedzy dla agentów.

Zasada dla każdej metody: mieści się w ok. 40 liniach prostego kodu, bez drzewa warunków. Jeśli tak się nie da,
ta wiedza należy do agenta, a nie do technologii.

Jak dodać technologię:
    1. Utwórz plik dev_agents/technologies/<nazwa>.py z podklasą Technology.
    2. Ustaw atrybut `name` i zaimplementuj metody wymagane; opcjonalne - gdy da się je napisać prosto.
    3. Dopisz technologię do rejestru w dev_agents/technologies/registry.py.

Umowy wspólne dla wszystkich metod:
    - `root` to ścieżka bezwzględna katalogu analizowanego projektu,
    - `files` i `path` to ścieżki WZGLĘDNE do `root`, z separatorem "/" (tak jak w schemas.FileEntry.path),
    - metody niczego nie wypisują - tylko zwracają wartości,
    - pliki projektu czytamy wyłącznie przez files.read_text_safe() (BOM, UTF-16, cp1250),
    - plik, którego nie da się przeczytać jako kod (np. błąd składni), daje odpowiedź "brak danych",
      a nie wyjątek - opisze go agent.

Rola: kontrakt dla modułów technologii; rdzeń towaru korzysta wyłącznie z jego metod.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.technologies.base
Wypisuje wyniki metod demonstracyjnej podklasy (pliki .demo; units i references z domyślnym zachowaniem),
a na końcu komunikat NotImplementedError klasy bazowej.
"""

import dev_agents.schemas as _schemas


# --- Kontrakt ---


class Technology:
    """Obsługa jednej technologii; podklasa ustawia `name` i implementuje metody kontraktu.

    Po co: jeden interfejs dla wszystkich technologii - rdzeń towaru woła te same metody niezależnie
    od tego, czy projekt jest w Pythonie, UiPath czy Robot Framework.
    """

    name = ""  # krótka nazwa technologii, np. "python"; trafia do ProjectMap.technology

    def detect(
        self,
        root: str,
        files: list[str],
    ) -> bool:
        """Sprawdza, czy projekt jest napisany w tej technologii.

        Po co: rejestr wybiera na tej podstawie obsługę technologii dla całego projektu (ProjectMap.technology).

        Argumenty: files - wszystkie pliki projektu (względne do root), już po odfiltrowaniu ignorowanych.
        """
        raise NotImplementedError(f"{type(self).__name__}.detect() - do implementacji")

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Sprawdza, czy plik jest kodem źródłowym tej technologii, czyli kandydatem do analizy.

        Po co: tylko pliki kodu trafiają do analityków jako jednostki kodu - reszta jest opisywana metadanymi.
        """
        raise NotImplementedError(f"{type(self).__name__}.is_source() - do implementacji")

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Znajduje pliki, od których startuje projekt (punkty wejścia).

        Po co: przewodnik zaczyna opis robota od miejsca uruchomienia, a kolejność czytania kodu - od punktu wejścia.

        Wynik: ścieżki względne, najbardziej prawdopodobny start na początku; pusta lista, gdy brak.
        """
        raise NotImplementedError(f"{type(self).__name__}.find_entrypoints() - do implementacji")

    def units(
        self,
        root: str,
        path: str,
    ) -> list[_schemas.SourceUnit]:
        """Zwraca jednostki pliku (funkcje, klasy, metody, workflowy, zadania) z nazwami i zakresami linii, w kolejności w pliku.

        Po co: pewne numery linii dla analityka i przewodnika, granice podziału długich plików na kawałki
        i długość jednostek do tabeli "Ryzykowne miejsca".

        Wynik: domyślnie (technologia bez implementacji) pusta lista - "brak danych".
        """
        jednostki = []
        return jednostki

    def references(
        self,
        root: str,
        path: str,
    ) -> _schemas.References:
        """Zwraca odwołania pliku: ścieżki innych plików projektu i nazwy pakietów spoza projektu.

        Po co: z plików powstaje graf zależności i kolejność czytania, z pakietów - wykrywanie frameworków.

        Wynik: domyślnie (technologia bez implementacji) puste listy - "brak danych".
        """
        odwolania = _schemas.References()
        return odwolania


# --- Test ręczny ---

if __name__ == "__main__":

    class _DemoTechnology(Technology):
        """Minimalna podklasa tylko do testu: kodem są pliki .demo; implementuje tylko metody wymagane.

        Po co: pokazuje autorowi nowej technologii, jak mało trzeba, żeby technologia działała.
        """

        name = "demo"

        def detect(
            self,
            root,
            files,
        ):
            """Uznaje projekt za 'demo', gdy jest w nim choć jeden plik .demo.

            Po co: przykład realizacji detect().
            """
            for path in files:
                if self.is_source(path):
                    return True
            return False

        def is_source(
            self,
            path,
        ):
            """Traktuje jako kod tylko pliki .demo.

            Po co: przykład odróżniania kodu od pozostałych plików projektu.
            """
            czy_plik_demo = path.endswith(".demo")
            return czy_plik_demo

        def find_entrypoints(
            self,
            root,
            files,
        ):
            """Zwraca start.demo jako jedyny punkt wejścia, jeśli istnieje.

            Po co: przykład formatu wyniku - lista ścieżek względnych.
            """
            punkty_wejscia = []
            if "start.demo" in files:
                punkty_wejscia.append("start.demo")
            return punkty_wejscia

    def _run_demo(
        technology: Technology,
        root: str,
        files: list[str],
    ) -> dict:
        """Wywołuje wszystkie metody kontraktu na podanej technologii i zwraca wyniki (nazwa metody -> wynik).

        Po co: zbiera wyniki do wypisania; ten sam przebieg pokazuje, czego rdzeń oczekuje od technologii.
        """
        pliki_zrodlowe = []
        for path in files:
            pliki_zrodlowe.append((path, technology.is_source(path)))
        wyniki = {
            "name": technology.name,
            "detect": technology.detect(root, files),
            "is_source": pliki_zrodlowe,
            "find_entrypoints": technology.find_entrypoints(root, files),
            "units": technology.units(root, "start.demo"),
            "references": technology.references(root, "start.demo"),
        }
        return wyniki

    def _base_class_error(
        root: str,
        files: list[str],
    ) -> str:
        """Wywołuje detect() na samej klasie bazowej i zwraca komunikat NotImplementedError.

        Po co: pokazuje, że metody wymagane trzeba zaimplementować w podklasie.
        """
        komunikat_bledu = ""
        try:
            Technology().detect(root, files)
        except NotImplementedError as blad:
            komunikat_bledu = str(blad)
        return komunikat_bledu

    def _print_demo(
        results: dict,
        error_message: str,
    ) -> None:
        """Wypisuje wyniki metod podklasy demo i komunikat błędu klasy bazowej.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        for method_name, result in results.items():
            print(f"{method_name + ':':<18}{result!r}")
        print(f"\nKlasa bazowa bez implementacji: NotImplementedError: {error_message}")

    def manual_test():
        """Uruchamia metody kontraktu na podklasie demo i pokazuje błąd klasy bazowej.

        Po co: sprawdzenie kontraktu Technology na minimalnym przykładzie, bez prawdziwej technologii.
        """
        root = r"C:\projekt_demo"
        files = ["start.demo", "helpers.demo", "config.yml", "dane.xlsx"]
        results = _run_demo(_DemoTechnology(), root, files)
        error_message = _base_class_error(root, files)
        _print_demo(results, error_message)

    manual_test()
