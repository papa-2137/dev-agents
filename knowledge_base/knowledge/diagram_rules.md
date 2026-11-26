# Zasady diagramu przepływu

> Pierwsza wersja - do uzupełnienia przez zespół. Dotyczy autora diagramu; diagram jest kręgosłupem przewodnika, a pozostałe zakładki odwołują się do numerów jego klocków.

## Cel
Z samego diagramu czytelnik ma umieć opowiedzieć, co robot robi po kolei, na poziomie biznesowo-technicznym - bez czytania kodu i bez wyliczania pól. Przykład dobrego klocka: „Wysyłka wiersza do bazy raportowej”. Zły klocek: „Wywołanie insert_row z 14 parametrami”.

## Klocki (rodzaje)
- `start` - dokładnie jeden; `end` - co najmniej jeden (koniec poprawny, a przy ścieżkach błędów także koniec z błędem).
- `step` - czynność robota widoczna dla biznesu: jeden klocek na jedną taką czynność, w kolejności wykonania.
- `system` - każdy kontakt z systemem zewnętrznym (aplikacja, strona, baza, poczta, API, dysk sieciowy) to osobny klocek, nawet gdy kod robi to jedną linią. Napis wskazuje, z czym robot rozmawia i po co.
- `decision` - rozgałęzienie. Na diagramie tylko decyzje, które mają znaczenie dla biznesu („czy faktura już była przetworzona?”). Warunki techniczne (`if x is None`, sprawdzenia formatu, zagnieżdżone warunki) schodzą do opisu kroku, nie na diagram. Każda decyzja ma co najmniej dwa wyjścia, każde z opisem („tak”, „nie”, „błąd biznesowy”).
- Napisy klocków: czasownik albo rzeczownik odczasownikowy, kilka słów („Pobranie listy zleceń”, „Zapis wyniku do pliku”). Bez nazw funkcji w napisie - nazwy funkcji idą do pola `functions`.

## Strzałki
- Pętle jawnie: powrót do wcześniejszego klocka to strzałka `loop`, z opisem warunku („następny element”, „ponowienie”). Cykl bez strzałki `loop` jest błędem.
- Gałęzie decyzji to strzałki `branch` z opisem; zwykłe przejścia - `normal`.
- Ścieżki błędów rysujemy, gdy robot coś z nimi robi (pomija element, ponawia, wysyła powiadomienie, kończy z błędem). Błąd, który tylko przerywa działanie bez reakcji, jest jednym klockiem `end`.

## Rozmiar
- Cel: ok. 30 klocków, nie więcej (limit w `config.yaml`, sekcja `flow`). Jeśli diagram rośnie, łącz kolejne czynności tego samego rodzaju w jeden klocek, a szczegóły przenoś do opisu klocka i pól `functions`, `reads`, `writes`.
- Robot z długimi funkcjami po kilkaset linii też ma dać czytelny diagram: dziel go według czynności biznesowych, nie według funkcji w kodzie.

## Dane klocka
- `module` - plik, w którym dzieje się krok (wymagany przy `step` i `system`); `functions` - funkcje w kolejności wywołania, z linią (`run:120`).
- `reads` i `writes` - co krok czyta i zapisuje albo zwraca; każda pozycja ma rodzaj: `file` (plik), `env` (zmienna środowiskowa), `system` (system zewnętrzny), `memory` (dane w pamięci).
- `certain = false` dla klocka, który wywnioskowano, a kod nie mówi o nim wprost (np. krok wykonywany przez framework).

## Frameworki
- Gdy robot działa pod frameworkiem, kolejność wywołań ustala framework (plik wiedzy frameworku). Klocki odpowiadają czynnościom robota w tej kolejności, a wywołania frameworku (np. inicjalizacja, pobranie elementów, koniec) pokazujemy tak, jak widzi je biznes, nie jak nazywają się metody.

## Spójność (sprawdza kod)
- Jeden start, osiągalność każdego klocka ze startu, strzałki wskazują istniejące klocki, każdy klocek poza `end` ma wyjście, decyzja ma co najmniej dwa opisane wyjścia. Przy problemach dostajesz ich listę i poprawiasz diagram.
- Układ (wiersze, kolumny, objazdy) wylicza kod. Kolejność klocków na liście to kolejność przepływu: numer klocka w przewodniku to jego pozycja na liście.
