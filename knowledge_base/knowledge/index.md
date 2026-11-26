# Baza wiedzy - spis plików do wyboru

Planner czyta ten spis i wybiera pliki potrzebne dla danego projektu i agenta.
Nowy plik: dodaj go do tego katalogu i dopisz wpis poniżej - nazwa pliku, „Kiedy użyć:” i „Tagi:”,
wpisy oddzielone pustą linią. „Kiedy użyć” pisz tak, żeby model mógł zdecydować, czy plik się przyda.

Pliki technologii (`technologies/`) i wykrytych frameworków (`frameworks/`) dostają agenci zawsze, gdy
technologię lub framework wykryto w projekcie - nie wpisujemy ich tutaj (technologia: metoda
`knowledge_file()`, framework: pole `knowledge` w `config.yaml`).

guide_goals.md
Kiedy użyć: zawsze przy pisaniu tekstu przewodnika (opis robota, metryczka, wejście i wyjście, ścieżki, zmiany, błędy, dla dewelopera) - dla kogo piszemy, ton, poziom szczegółów, jak oznaczać informacje wywnioskowane i brak danych, jak traktować sekrety i ryzykowne miejsca.
Tagi: przewodnik, styl, pisarz, recenzent

diagram_rules.md
Kiedy użyć: przy tworzeniu i poprawianiu diagramu przepływu (graf klocków i strzałek) oraz przy ścieżkach procesu, które odwołują się do jego klocków - rodzaje klocków, jeden klocek na czynność widoczną dla biznesu, kontakty z systemami, decyzje biznesowe, pętle, limit rozmiaru.
Tagi: diagram, przepływ, autor diagramu, ścieżki
