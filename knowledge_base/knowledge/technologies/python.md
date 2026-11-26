# Python - konwencje projektów RPA

> Pierwsza wersja - ogólne dobre praktyki. Do zastąpienia konwencjami zespołu.

Plik dostają wszyscy agenci przy projekcie w Pythonie. Opisuje, jak wygląda dobrze zbudowany robot, żeby było widać, gdzie konkretny robot się trzyma tych zasad, a gdzie od nich odstępuje. Odstępstwa to ważne wskazówki utrzymaniowe i kandydaci do „Ryzykownych miejsc”. Robot nie musi spełniać żadnej z tych zasad - opisujemy go takim, jaki jest.

## Struktura projektu
- Punkt wejścia w `main.py` w katalogu głównym albo plik uruchamiany z `.bat` / `.ps1`; logika w pakiecie (np. `src/`), podzielona według odpowiedzialności: obsługa stron lub aplikacji, odczyt danych, raport, logowanie.
- Obsługa każdej strony lub aplikacji w osobnym module lub klasie (wzorzec page object) - selektory w jednym miejscu.
- Dane wejściowe i wyniki w osobnych katalogach (np. `resources/in`, `resources/out`); pliki wynikowe nie są częścią kodu.
- Zależności w `requirements.txt` (uwaga: plik bywa w kodowaniu UTF-16) albo `pyproject.toml`; środowisko wirtualne (`venv`, `.venv` lub inna nazwa) nie jest częścią projektu.

## Konfiguracja i sekrety
- Konfiguracja w pliku (`config.yml`, `.json`, `.ini`) albo w stałych na górze modułu; adresy i ścieżki nie rozsiane po kodzie.
- Hasła i klucze tylko w zmiennych środowiskowych albo magazynie poświadczeń; w konfiguracji sama nazwa zmiennej (np. `password_env`).
- Odstępstwa do opisania: hasło wpisane w kod lub plik konfiguracyjny (podajemy je dosłownie i oznaczamy), certyfikat lub klucz w repozytorium, adres systemu produkcyjnego na sztywno.

## Logowanie i obsługa błędów
- Logowanie przez moduł `logging` (albo logger frameworku), z informacją, który element jest przetwarzany; logi trafiają do pliku w znanym katalogu.
- Rozróżnienie błędów biznesowych (zły element danych - pomijamy i raportujemy) od technicznych (awaria systemu - ponowienie lub zatrzymanie).
- Odstępstwa do opisania: puste `except`, `except Exception` z samym `pass`, połykanie wyjątków, brak logu przy błędzie, `print` zamiast logowania.

## Sygnały kruchości
- Stałe ścieżki bezwzględne (`C:\...`), opóźnienia na sztywno (`time.sleep`), selektory zależne od wyglądu strony lub kolejności elementów, założenia o formacie pliku (nazwy kolumn, kodowanie, separator).
- Bardzo długie funkcje i warunki w warunkach: opisujemy je według czynności biznesowych, a w „Ryzykownych miejscach” podajemy plik i zakres linii.
- Skrypty uruchamiające (`.bat`, `.ps1`) ustawiają środowisko i parametry - ich treść jest częścią instrukcji uruchomienia.

## Co ma wskazać agent
- Gdzie projekt trzyma się tych zasad, a gdzie od nich odstępuje.
- Jak robot jest uruchamiany (punkt wejścia, argumenty, zmienne środowiskowe, skrypt startowy) i skąd bierze konfigurację.
- Jakie pakiety spoza biblioteki standardowej są potrzebne i czy są wpisane do pliku zależności.
