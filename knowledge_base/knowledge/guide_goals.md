# Jak piszemy przewodnik po robocie

> Pierwsza wersja - do uzupełnienia przez zespół (standard przewodników, przykłady dobrych przewodników).

## Dla kogo piszemy
- Osoba, która przejmuje robota w utrzymanie albo ma go rozbudować. Zna Pythona i podstawy RPA, ale nie zna tego robota ani procesu, który obsługuje.
- Model językowy, który w przyszłości będzie czytał przewodnik, żeby pomóc w zmianach - dlatego nazwy plików, funkcji, parametrów i zmiennych środowiskowych podajemy dokładnie, tak jak w kodzie.
- Po przeczytaniu przewodnika czytelnik ma umieć: opowiedzieć, co robot robi krok po kroku, uruchomić go, znaleźć przyczynę typowej awarii i wiedzieć, od którego pliku zacząć zmianę.

## Ton i styl
- Po polsku, rzeczowo, krótkimi zdaniami. Bez marketingu i ogólników („robot usprawnia procesy”).
- Konkret zamiast opisu ogólnego: nazwa pliku, funkcji, parametru, adres, ścieżka. Nie przepisujemy kodu - wskazujemy, gdzie co jest.
- Język biznesowo-techniczny: „robot wysyła wiersz do bazy raportowej”, nie „wywołuje metodę execute na kursorze” i nie „przetwarza dane”.

## Czego nie wiemy
- Gdy czegoś nie da się ustalić z kodu, piszemy to wprost („Nie wynika z kodu.”) albo zostawiamy pole puste. Wymysł jest gorszy niż luka.
- Informację, która nie jest zapisana w kodzie wprost, tylko z niego wynika (np. cel kroku, znaczenie klucza konfiguracji), oznaczamy jako wywnioskowaną: w komórce tabeli dopisujemy na końcu znacznik [wywnioskowane], przy klocku diagramu i wpisie metryczki ustawiamy certain = false.
- Nie zgadujemy nazw, adresów ani wartości. Jeśli nazwy nie widać w dostarczonym kodzie, nie ma jej w przewodniku.

## Sekrety i ryzykowne miejsca
- Hasło, klucz albo token wpisany wprost w kod lub w plik konfiguracyjny podajemy dosłownie, tak jak jest w pliku, i oznaczamy jako hasło wpisane wprost (plain_password). To błąd, który przewodnik ma ujawnić, nie ukryć.
- Plików sekretów (certyfikaty, klucze, pliki `.env`) nie dostajemy w całości - znamy tylko ich nazwę, rolę i rozmiar. Opisujemy, do czego służą i gdzie kod je wczytuje; nigdy nie zgadujemy ich treści.
- Ryzykowne miejsce to: sekret w kodzie lub repozytorium, bardzo długa funkcja, połknięty wyjątek, stała ścieżka, opóźnienie na sztywno, selektor zależny od wyglądu strony. Przy każdym podajemy powód i miejsce (plik, linie).

## Poziom szczegółów
- Przegląd i uruchomienie: tylko fakty potrzebne, by robota uruchomić - wymagania, dostępy sieciowe, konta i nazwy zmiennych, instalacja, sprawdzenie, że działa.
- Przepływ i ścieżki: tyle, żeby z diagramu dało się opowiedzieć, co robot robi po kolei (zasady diagramu: `diagram_rules.md`). Szczegóły techniczne (moduły, funkcje, dane) idą do wierszy „krok po kroku”, nie na klocki.
- Zmiany i błędy: tyle, żeby znaleźć przyczynę awarii i bezpiecznie wprowadzić zmianę - gdzie robot jest kruchy, co sprawdzić najpierw, gdzie są logi, od którego pliku zacząć nowy krok lub nowy typ danych.

## Ścieżki procesu
- Opisujemy wszystkie: główną i alternatywne (błąd biznesowy, błąd techniczny, inne rozgałęzienia).
- Kroki to numerowane zdania w kolejności wykonania, z konkretami z kodu (aplikacja, adres, przycisk, pole, plik, decyzja, pętla) i z numerem klocka diagramu, którego dotyczą.

## Czego nie robimy
- Nie opisujemy szczegółowo kodu frameworku - wystarczy, które metody robota framework wywołuje i kiedy (plik wiedzy frameworku).
- Nie powtarzamy tej samej informacji w kilku sekcjach - jeśli coś jest w metryczce, w innych miejscach odsyłamy do niej.
- Nie oceniamy jakości kodu poza ryzykownymi miejscami; opisujemy robota takim, jaki jest.
