"""Obsługa technologii NICE APA - PUSTA KLASA do implementacji (miejsce przygotowane pod rozszerzenie).

Stan: klasa jest w rejestrze technologii (registry.py), ale detect() zawsze zwraca False, więc towar nigdy
jej nie wybierze; is_source() i find_entrypoints() rzucają NotImplementedError z nazwą technologii, a units()
i references() dziedziczą z klasy bazowej odpowiedź "brak danych".

Uwaga: formaty plików projektu NICE APA (Advanced Process Automation) NIE są tu ustalone - potwierdzi je osoba,
która będzie implementować tę technologię, na prawdziwym projekcie zespołu.

Otwarte pytania do rozstrzygnięcia przed implementacją:
    1. Jak wygląda projekt NICE APA na dysku: jeden plik czy katalog, jakie rozszerzenia, tekst (XML, JSON)
       czy format binarny?
    2. Po czym pewnie rozpoznać projekt NICE (detect)?
    3. Które pliki są kodem (is_source), a gdzie jest punkt wejścia (find_entrypoints)?
    4. Czy da się prosto (ok. 40 linii) wypisać jednostki z zakresami linii (units) i wywołania innych plików
       projektu (references)? Jeśli nie - zostają domyślne "brak danych", a strukturę opiszą agenci.
    5. Czy projekt zawiera kod w innych językach (C#, VB.NET, skrypty) - jeśli tak, czy delegować go do
       istniejących technologii, jak Robot Framework deleguje pliki .py do PythonTechnology?

Jak zaimplementować: po odpowiedzi na pytania wypełnij metody (kontrakt: base.py, wzorzec: python.py), usuń
z detect() stałe False, dopisz plik wiedzy knowledge_base/knowledge/technologies/nice.md, test ręczny
i sprawdź rejestr: python -m dev_agents.technologies.registry

Zasady (AGENTS.md): kod projektu tylko czytamy, nigdy nie uruchamiamy; pliki tekstowe przez
files.read_text_safe(); metody nic nie wypisują.

Rola: moduł technologii (pusta klasa), używany przez rejestr technologii.

Test ręczny: brak - klasa nie ma logiki; jej zachowanie sprawdza test rejestru:
    python -m dev_agents.technologies.registry
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

        Po co: klasa może być w rejestrze bez wpływu na działanie towaru.
        """
        czy_nice = False
        return czy_nice

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Do implementacji: czy plik jest kodem projektu NICE (otwarte pytanie 3).

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
