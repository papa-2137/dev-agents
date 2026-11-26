"""Obsługa technologii Robot Framework - PUSTA KLASA do implementacji (miejsce przygotowane pod rozszerzenie).

Stan: klasa jest w rejestrze technologii (registry.py), ale detect() zawsze zwraca False, więc towar nigdy
jej nie wybierze; is_source() i find_entrypoints() rzucają NotImplementedError z nazwą technologii, a units()
i references() dziedziczą z klasy bazowej odpowiedź "brak danych".

Jak zaimplementować (kontrakt: base.py, wzorzec: python.py; każda metoda ok. 40 linii prostego kodu):
    - detect: choć jeden plik .robot z sekcją *** Tasks *** albo *** Test Cases ***,
    - is_source: .robot, .resource i .py (własne biblioteki i pliki zmiennych),
    - find_entrypoints: pliki .robot z sekcją *** Tasks *** / *** Test Cases *** (to je uruchamia `robot`),
      najpierw z katalogu głównego; .resource nie są punktami wejścia,
    - units (opcjonalnie): nazwy zadań, testów i słów kluczowych z zakresami linii - nazwą jest linia bez
      wcięcia w sekcjach Tasks / Test Cases / Keywords, koniec to linia przed następną nazwą,
    - references (opcjonalnie): files - ścieżki z `Resource`, `Variables` i `Library` wskazujących pliki
      projektu; packages - pozostałe `Library` (SeleniumLibrary, Browser, RPA.*).
    Pliki .py obsługuje PythonTechnology przez delegację: klasa tworzy jej obiekt i przekazuje mu units()
    i references() dla plików .py - bez kopiowania kodu z python.py.
    Usuń z detect() stałe False, dopisz test ręczny pod `if __name__ == "__main__":` i sprawdź rejestr:
        python -m dev_agents.technologies.registry

Zasady (AGENTS.md): kod projektu tylko czytamy, nigdy nie uruchamiamy; pliki przez files.read_text_safe();
pliki .robot zwykłym kodem po liniach (sekcje *** ... ***, kolumny oddzielone co najmniej dwiema spacjami albo
tabulatorem); metody nic nie wypisują. Treść zadań, zmienne i konfigurację opisują agenci - wiedzę o Robot
Framework dostają z pliku knowledge_base/knowledge/technologies/robotframework.md.

Rola: moduł technologii (pusta klasa), używany przez rejestr technologii.

Test ręczny: brak - klasa nie ma logiki; jej zachowanie sprawdza test rejestru:
    python -m dev_agents.technologies.registry
"""

import dev_agents.technologies.base as _base


class RobotFrameworkTechnology(_base.Technology):
    """Projekty Robot Framework (.robot, .resource, biblioteki .py) - pusta klasa do implementacji.

    Po co: miejsce przygotowane pod obsługę Robot Framework - rejestr ją zna, a docstring modułu mówi, co zrobić.
    """

    name = "robotframework"

    def detect(
        self,
        root: str,
        files: list[str],
    ) -> bool:
        """Na razie zawsze zwraca False - technologia nie jest zaimplementowana, więc towar nigdy jej nie wybiera.

        Po co: klasa może być w rejestrze bez wpływu na działanie towaru.

        Uwaga: rejestr sprawdza Robot Framework przed Pythonem - projekt z bibliotekami .py ma być rozpoznany
        jako Robot Framework.
        """
        czy_robot_framework = False
        return czy_robot_framework

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Do implementacji: czy plik jest kodem projektu (.robot, .resource, .py) - opis w docstringu modułu.

        Po co: tylko pliki kodu trafią do analityków.
        """
        raise NotImplementedError(f"{type(self).__name__}.is_source() - do implementacji")

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Do implementacji: pliki .robot z zadaniami albo testami - opis w docstringu modułu.

        Po co: przewodnik zaczyna opis od miejsca uruchomienia.
        """
        raise NotImplementedError(f"{type(self).__name__}.find_entrypoints() - do implementacji")
