"""Kontrakt obsługi technologii: co musi dostarczyć każda technologia analizowanych projektów.

Co robi: definiuje klasę Technology - zestaw metod, przez które rdzeń towaru (skaner, agenci) pyta
o projekt: czy jest w tej technologii, które pliki są kodem, gdzie są punkty wejścia, jak wygląda
szkielet pliku i jakie ma zależności. Klasa bazowa niczego nie implementuje - każda metoda rzuca
NotImplementedError z nazwą technologii i metody.

Dlaczego istnieje: rdzeń towaru nie zna żadnego języka ani frameworku (AGENTS.md, reguła 7). Cała wiedza
o technologii siedzi w podklasie, więc dodanie kolejnej technologii (UiPath, Robot Framework, NICE) nie
wymaga zmian w skanerze ani w agentach.

Jak dodać technologię:
    1. Utwórz plik dev_agents/technologies/<nazwa>.py z podklasą Technology.
    2. Ustaw atrybut `name` i zaimplementuj metody kontraktu.
    3. Zarejestruj technologię w dev_agents/technologies/__init__.py.

Umowy wspólne dla wszystkich metod:
    - `root` to ścieżka bezwzględna katalogu analizowanego projektu,
    - `files` i `path` to ścieżki WZGLĘDNE do `root` (tak jak w schemas.FileEntry.path),
    - metody niczego nie wypisują - tylko zwracają wartości,
    - pliki projektu czytamy wyłącznie przez files.read_text_safe() (BOM, UTF-16, cp1250).

Rozwój kontraktu: nowa metoda dopisywana do kontraktu dostaje w klasie bazowej domyślne zachowanie ogólne
(np. wspólny parser), żeby technologia nadpisywała tylko to, co ma inaczej. NotImplementedError zostaje
tylko w metodach, bez których technologia nie ma sensu.

Rola: kontrakt dla modułów technologii; rdzeń towaru korzysta wyłącznie z jego metod.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.technologies.base
Wypisuje wyniki wszystkich metod demonstracyjnej podklasy (pliki .demo) - control_outline i metrics
z domyślnym zachowaniem klasy bazowej - a na końcu komunikat NotImplementedError klasy bazowej.
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

        Po co: na tej podstawie towar wybiera obsługę technologii dla całego projektu (ProjectMap.technology) -
        od niej zależy, które pliki są kodem i jak je analizować.

        Argumenty: files - wszystkie pliki projektu (względne do root), już po odfiltrowaniu ignorowanych.
        """
        raise NotImplementedError(f"{type(self).__name__}.detect() - do implementacji")

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Sprawdza, czy plik jest kodem źródłowym tej technologii, czyli kandydatem do analizy.

        Po co: skaner nadaje plikom role, a tylko pliki z rolą source trafiają do analityków jako jednostki
        kodu - reszta jest opisywana wyłącznie metadanymi.

        Wynik: True dla plików kodu (np. .py, .xaml); False dla konfiguracji, danych, binarek itp.
        """
        raise NotImplementedError(f"{type(self).__name__}.is_source() - do implementacji")

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Znajduje pliki, od których startuje projekt (punkty wejścia).

        Po co: przewodnik zaczyna opis robota od miejsca uruchomienia - punkt wejścia pokazuje, jak robot
        jest startowany i od którego modułu zaczyna się przepływ.

        Wynik: ścieżki względne punktów wejścia, np. ["main.py"] albo ["Main.xaml"]; pusta lista, gdy brak.
        """
        raise NotImplementedError(f"{type(self).__name__}.find_entrypoints() - do implementacji")

    def outline(
        self,
        root: str,
        path: str,
    ) -> str:
        """Buduje szkielet pliku dla modelu językowego - strukturę bez pełnej treści (np. klasy, funkcje, sygnatury, opisy).

        Po co: analityk widzi strukturę pliku przed lekturą całego kodu, a przy dużych plikach szkielet
        pozwala modelowi się zorientować bez czytania wszystkiego.

        Wynik: czytelny tekst (wiele linii); gdy szkieletu nie da się zbudować (np. błąd składni) - jedna linia
        z przyczyną, żeby analityk wiedział, dlaczego szkieletu brak.
        """
        raise NotImplementedError(f"{type(self).__name__}.outline() - do implementacji")

    def imports(
        self,
        root: str,
        path: str,
    ) -> dict[str, list[str]]:
        """Zwraca zależności pliku w trzech grupach: z projektu, zewnętrzne i standardowe.

        Po co: z importów powstaje graf zależności modułów i kolejność czytania, wykrywanie frameworków
        i sekcja zależności w przewodniku - także dla frameworków spoza plików projektu.

        Wynik: słownik z trzema kluczami (wartości bez powtórzeń, posortowane):
            "internal" - ŚCIEŻKI WZGLĘDNE plików tego projektu, od których plik zależy (np. "src/report.py",
                         "Framework/InitAllSettings.xaml") - technologia sama zamienia swoje odwołania na pliki,
                         dzięki czemu graf zależności w rdzeniu łączy pliki bez wiedzy o technologii,
            "external" - pełne nazwy bibliotek i frameworków spoza projektu (np. "selenium.webdriver.common.by"),
            "stdlib"   - elementy standardowo dostępne w technologii (w Pythonie biblioteka standardowa,
                         np. "os"); pusta lista, gdy w danej technologii to rozróżnienie nie ma sensu.
        """
        raise NotImplementedError(f"{type(self).__name__}.imports() - do implementacji")

    def control_outline(
        self,
        root: str,
        path: str,
        function_name: str,
    ) -> str:
        """Buduje szkielet sterowania jednej funkcji: same rozgałęzienia, pętle, obsługę błędów, wyjścia i wywołania, z numerami linii, bez treści gałęzi.

        Po co: mapa logiki długiej funkcji dla analityka i podstawa podziału funkcji na kawałki - liczona przez
        kod, tania w tokenach, bez zgadywania.

        Argumenty: function_name - nazwa funkcji ("run"), metody ("Klasa.metoda") albo "" dla kodu poza funkcjami.

        Wynik: czytelny tekst (wiele linii). Domyślnie (technologia bez implementacji) - jedna linia "niedostępny".
        """
        komunikat = f"Szkielet sterowania niedostępny dla technologii '{self.name}'"
        return komunikat

    def metrics(
        self,
        root: str,
        path: str,
    ) -> list[_schemas.FunctionMetrics]:
        """Zwraca miary złożoności każdej funkcji pliku (i kodu poza funkcjami): długość, głębokość zagnieżdżenia, rozgałęzienia.

        Po co: liczby wskazują najtrudniejsze miejsca kodu - tabela "Ryzykowne miejsca" i decyzja o analizie
        po kawałkach opierają się na nich, a nie na opinii modelu.

        Wynik: lista schemas.FunctionMetrics. Domyślnie (technologia bez implementacji) - pusta lista, czyli "brak danych".
        """
        miary = []
        return miary


# --- Test ręczny ---

if __name__ == "__main__":

    class _DemoTechnology(Technology):
        """Minimalna podklasa tylko do testu: kodem są pliki .demo.

        Po co: pokazuje autorowi nowej technologii, jak podklasa realizuje kontrakt - bez prawdziwego języka.
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
            czy_sa_pliki_demo = False
            for path in files:
                if path.endswith(".demo"):
                    czy_sa_pliki_demo = True
                    break
            return czy_sa_pliki_demo

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

        def outline(
            self,
            root,
            path,
        ):
            """Zwraca stały, przykładowy szkielet pliku.

            Po co: przykład, że outline() zwraca zwykły tekst dla modelu.
            """
            szkielet = f"plik {path}: (demo - brak struktury)"
            return szkielet

        def imports(
            self,
            root,
            path,
        ):
            """Zwraca stałe, przykładowe zależności w trzech grupach.

            Po co: przykład wymaganego kształtu wyniku - słownik z kluczami internal, external, stdlib.
            """
            zaleznosci = {"internal": ["helpers.demo"], "external": ["biblioteka_x"], "stdlib": []}
            return zaleznosci

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
            "outline": technology.outline(root, "start.demo"),
            "imports": technology.imports(root, "start.demo"),
            "control_outline": technology.control_outline(root, "start.demo", "start"),
            "metrics": technology.metrics(root, "start.demo"),
        }
        return wyniki

    def _base_class_error(
        root: str,
        files: list[str],
    ) -> str:
        """Wywołuje detect() na samej klasie bazowej i zwraca komunikat NotImplementedError.

        Po co: pokazuje, że klasa bazowa jest tylko kontraktem.
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
            print(f"{method_name + ':':<18}{result}")
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
