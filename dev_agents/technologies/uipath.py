"""Obsługa technologii UiPath - PUSTA KLASA do implementacji (miejsce przygotowane pod rozszerzenie).

Stan: klasa jest w rejestrze technologii (registry.py), ale detect() zawsze zwraca False, więc towar nigdy
jej nie wybierze; is_source() i find_entrypoints() rzucają NotImplementedError z nazwą technologii, a units()
i references() dziedziczą z klasy bazowej odpowiedź "brak danych".

Jak zaimplementować (kontrakt: base.py, wzorzec: python.py; każda metoda ok. 40 linii prostego kodu):
    - detect: project.json w katalogu głównym z kluczami typowymi dla UiPatha ("main", "dependencies",
      "studioVersion") - project.json występuje też w innych technologiach,
    - is_source: .xaml (workflowy) i .cs (coded workflows); NIE: project.json, .objects/, .local/, .settings/,
      .screenshots/, .tmh, Data/Config.xlsx,
    - find_entrypoints: pole "main" z project.json na początku listy, potem "entryPoints"; bez project.json -
      Main.xaml w katalogu głównym,
    - units (opcjonalnie): jeden workflow = jedna jednostka (nazwa pliku, linie od 1 do końca pliku);
      ewentualnie stany maszyny stanów z numerami linii,
    - references (opcjonalnie): files - atrybuty WorkflowFileName aktywności Invoke Workflow File (ścieżki
      względne do root, separator "/"); packages - klucze "dependencies" z project.json.
    Usuń z detect() stałe False, dopisz test ręczny pod `if __name__ == "__main__":` i sprawdź rejestr:
        python -m dev_agents.technologies.registry

Zasady (AGENTS.md): kod projektu tylko czytamy, nigdy nie uruchamiamy; pliki przez files.read_text_safe()
(pliki UiPatha często mają BOM); XAML przez `xml.etree.ElementTree` z obsługą przestrzeni nazw, nie wyrażeniami
regularnymi; metody nic nie wypisują. Wszystko ponad te proste fakty (drzewo aktywności, argumenty, adnotacje,
selektory, Config.xlsx, Orchestrator) opisują agenci - wiedzę o UiPath dostają z pliku
knowledge_base/knowledge/technologies/uipath.md.

Czym jest projekt UiPath (dla kontekstu): project.json (name, main, entryPoints, dependencies, projectType,
targetFramework, expressionLanguage), workflowy .xaml (Sequence, Flowchart, StateMachine), coded workflows .cs,
REFramework (Framework/InitAllSettings.xaml, GetTransactionData.xaml, Process.xaml..., Main.xaml jako maszyna
stanów, Data/Config.xlsx z arkuszami Settings / Constants / Assets).

Rola: moduł technologii (pusta klasa), używany przez rejestr technologii.

Test ręczny: brak - klasa nie ma logiki; jej zachowanie sprawdza test rejestru:
    python -m dev_agents.technologies.registry
"""

import dev_agents.technologies.base as _base


class UiPathTechnology(_base.Technology):
    """Projekty UiPath (Studio) - pusta klasa do implementacji.

    Po co: miejsce przygotowane pod obsługę UiPatha - rejestr ją zna, a docstring modułu mówi, co zrobić.
    """

    name = "uipath"

    def detect(
        self,
        root: str,
        files: list[str],
    ) -> bool:
        """Na razie zawsze zwraca False - technologia nie jest zaimplementowana, więc towar nigdy jej nie wybiera.

        Po co: klasa może być w rejestrze bez wpływu na działanie towaru.

        Uwaga: rejestr sprawdza UiPatha przed Pythonem - po implementacji detect() musi być pewny (project.json),
        bo projekt UiPath z pomocniczym skryptem .py ma być rozpoznany jako UiPath.
        """
        czy_uipath = False
        return czy_uipath

    def is_source(
        self,
        path: str,
    ) -> bool:
        """Do implementacji: czy plik jest kodem UiPath (.xaml, .cs) - opis w docstringu modułu.

        Po co: tylko pliki kodu trafią do analityków.
        """
        raise NotImplementedError(f"{type(self).__name__}.is_source() - do implementacji")

    def find_entrypoints(
        self,
        root: str,
        files: list[str],
    ) -> list[str]:
        """Do implementacji: pliki startowe procesu z project.json - opis w docstringu modułu.

        Po co: przewodnik zaczyna opis od miejsca uruchomienia procesu.
        """
        raise NotImplementedError(f"{type(self).__name__}.find_entrypoints() - do implementacji")
