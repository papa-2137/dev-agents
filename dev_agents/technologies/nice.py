"""Obsługa technologii NICE APA - PUSTA KLASA do implementacji (miejsce przygotowane pod rozszerzenie).

Stan: klasa jest w rejestrze technologii (dev_agents/technologies/registry.py), ale nic nie robi - detect()
zawsze zwraca False, więc towar nigdy jej nie wybierze, a metody kontraktu rzucają NotImplementedError
z nazwą technologii. control_outline() i metrics() dziedziczą z klasy bazowej odpowiedź "brak danych".

Uwaga: formaty plików projektu NICE APA (Advanced Process Automation) NIE są tu ustalone - potwierdzi je
osoba, która będzie implementować tę technologię, na prawdziwym projekcie zespołu. Opisy metod mówią,
JAKIE informacje kontrakt ma dostarczyć, a nie skąd je wziąć.

Otwarte pytania do rozstrzygnięcia przed implementacją:
    1. Jak wygląda projekt NICE APA na dysku: jeden plik czy katalog, jakie rozszerzenia (eksport projektu,
       pliki workflowów, skrypty), czy to tekst (XML, JSON), czy format binarny?
    2. Po czym pewnie rozpoznać projekt NICE (plik opisu projektu, charakterystyczne rozszerzenie)?
    3. Gdzie jest punkt wejścia (główny workflow, zdarzenie startowe, harmonogram)?
    4. Jak jeden workflow wywołuje inny (odpowiednik importu - do grupy internal jako ścieżki plików)?
    5. Gdzie jest konfiguracja (ustawienia, adresy systemów, poświadczenia - tylko nazwy, nigdy wartości)?
    6. Czy projekt zawiera kod w innych językach (np. C#, VB.NET, skrypty) - jeśli tak, czy delegować go
       do istniejących technologii, jak Robot Framework deleguje pliki .py do PythonTechnology?

Jak zaimplementować: po odpowiedzi na pytania wypełnij metody poniżej (kontrakt: base.py, wzorzec: python.py),
usuń z detect() stałe `return False`, dopisz test ręczny i sprawdź rejestr:
    python -m dev_agents.technologies.registry

Zasady wspólne z resztą towaru (AGENTS.md): kod projektu tylko czytamy, nigdy nie uruchamiamy; pliki tekstowe
czytamy przez files.read_text_safe(); ścieżki przez os.path; metody nic nie wypisują.

Rola: moduł technologii (pusta klasa), używany przez rejestr technologii.

Test ręczny: brak - klasa nie ma logiki; jej zachowanie (detect -> False, NotImplementedError z nazwą
technologii) sprawdza test rejestru: python -m dev_agents.technologies.registry
"""

import dev_agents.technologies.base as _base


class NiceTechnology(_base.Technology):
    """Projekty NICE APA - pusta klasa do implementacji; formaty plików do potwierdzenia.

    Po co: miejsce przygotowane pod obsługę NICE - rejestr ją zna, a docstring modułu zbiera otwarte pytania.
    """

    name = "nice"

    def detect(
        self,
        root: str,
        files: list[str],
    ) -> bool:
        """Na razie zawsze zwraca False - technologia nie jest zaimplementowana, więc towar nigdy jej nie wybiera.

        Po co: stałe False pozwala trzymać klasę w rejestrze bez wpływu na działanie towaru.

        Do uchwycenia: pewny znak projektu NICE (otwarte pytanie 2 w docstringu modułu).
        """
        czy_nice = False
        return czy_nice

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Do implementacji: czy plik jest kodem projektu NICE (workflow, skrypt), a nie konfiguracją albo danymi.

        Po co: tylko pliki kodu trafią do analityków.
        """
        raise NotImplementedError(f"{type(self).__name__}.is_source() - do implementacji")

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Do implementacji: pliki, od których startuje proces NICE (otwarte pytanie 3).

        Po co: przewodnik zaczyna opis od miejsca uruchomienia.
        """
        raise NotImplementedError(f"{type(self).__name__}.find_entrypoints() - do implementacji")

    def outline(
        self,
        root: str,
        path: str,
    ) -> str:
        """Do implementacji: szkielet workflowu NICE - kroki, decyzje, wywołania innych workflowów i systemów, bez pełnej treści.

        Po co: analityk widzi logikę procesu bez czytania całego pliku.
        """
        raise NotImplementedError(f"{type(self).__name__}.outline() - do implementacji")

    def imports(
        self,
        root: str,
        path: str,
    ) -> dict[str, list[str]]:
        """Do implementacji: zależności w trzech grupach - internal (ŚCIEŻKI wywoływanych plików projektu), external, stdlib.

        Po co: z grupy internal powstaje graf zależności (otwarte pytanie 4), a external pokazuje używane
        moduły i systemy.
        """
        raise NotImplementedError(f"{type(self).__name__}.imports() - do implementacji")
