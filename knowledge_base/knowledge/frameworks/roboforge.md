# Roboforge (Python) - wiedza dla agentów

> Pierwsza wersja - opis na podstawie robota testowego i znanego cyklu życia frameworku. Do uzupełnienia przez zespół.

Plik dostają agenci tylko wtedy, gdy kod skanera wykrył w projekcie framework Roboforge.

## Ukryty przepływ sterowania
Robot oparty na frameworku nie ma pętli głównej we własnym kodzie. Framework sam wywołuje metody robota w ustalonej kolejności. Przewodnik musi to powiedzieć wprost - inaczej czytelnik nie znajdzie miejsca, w którym „wszystko się zaczyna”. Diagram przepływu odpowiada czynnościom robota w kolejności, w jakiej woła je framework.

## Jak rozpoznać
- Importy `roboforge.*`; klasa robota dziedziczy po `_Worker` (`roboforge.processing._worker`); w `main.py` uruchamiany jest `Launcher`.
- Zwykle zainstalowany jako pakiet (także edytowalnie) - kodu frameworku nie ma w projekcie, widać go tylko w importach. Gdy jest skopiowany do projektu (katalog `roboforge_framework/`), jego pliki są w mapie projektu oznaczone nazwą frameworku i nie wymagają analizy ani opisu.

## Cykl życia - metody robota wołane przez framework
- `initialization()` - raz na początku: logowanie, otwarcie aplikacji, przygotowanie zasobów.
- `get_data()` - zwraca listę elementów do przetworzenia (transakcji).
- `automation_process(transaction_item)` - przetworzenie jednego elementu, wołane osobno dla każdego elementu z `get_data()`; to tu leży główna logika procesu.
- `on_error(transaction_item, error_instance)` - reakcja na błąd przy jednym elemencie.
- `end_process(transaction_data)` - raz na końcu: raport, zamknięcie aplikacji, sprzątanie.

Kolejność: `initialization` -> `get_data` -> pętla `automation_process` dla każdego elementu (przy błędzie `on_error`) -> `end_process`. Pętla po elementach należy do frameworku, więc na diagramie jest jawną pętlą (strzałka `loop`: „następny element”), choć w kodzie robota nie ma żadnego `for`.

## Błędy
- `BusinessRuleException` (`roboforge.processing.exceptions`) oznacza błąd biznesowy: element jest pomijany bez ponawiania, robot działa dalej. Inne wyjątki są traktowane jako techniczne i ponawiane.
- Gdzie robot rzuca `BusinessRuleException`, a gdzie pozwala wyjątkowi przejść - to osobna decyzja na diagramie i osobna ścieżka procesu.

## Konfiguracja
- `get_config` (`roboforge.processing.utilities`), zwykle z pliku `config.yml`. Plik i miejsce jego wczytania wskazujemy w metryczce robota.

## Co ma wskazać agent
- Które metody cyklu robot implementuje, a które zostawia frameworkowi, i co robi w każdej.
- Skąd `get_data()` bierze elementy i co jest jednym elementem.
- Gdzie robot rozróżnia błąd biznesowy od technicznego i co się dzieje z elementem w obu przypadkach.
- Których metod cyklu w robocie nie ma (framework pomija je albo używa wersji domyślnej) - opisujemy tylko to, co jest w kodzie robota, bez zgadywania zachowania frameworku.
