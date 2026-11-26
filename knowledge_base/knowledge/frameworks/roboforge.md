# Roboforge (Python) - wiedza dla agentów

> **MAKIETA** - plik istnieje, żeby wpis frameworku w `config.yaml` (`scan.frameworks.roboforge.knowledge`) wskazywał prawdziwy plik. Docelowa treść powstaje w kroku 42 (na podstawie `rpa_framework.md` z doc-agents i cyklu życia Roboforge). Poniżej tylko układ rozdziałów i najważniejsze fakty.

## Jak rozpoznać
- Importy `roboforge.*`; klasa robota dziedziczy po `_Worker` (`roboforge.processing._worker`); w `main.py` uruchamiany jest `Launcher`.
- Zwykle zainstalowany jako pakiet (także edytowalnie) - jego kodu nie ma w projekcie, widać go tylko w importach.

## Cykl życia - metody wołane przez framework
- `initialization()` - raz na początku.
- `get_data()` - lista elementów do przetworzenia.
- `automation_process(transaction_item)` - raz dla każdego elementu.
- `on_error(transaction_item, error_instance)` - reakcja na błąd przy elemencie.
- `end_process(transaction_data)` - raz na końcu.

## Błędy
- `BusinessRuleException` - błąd biznesowy: element pomijany, bez ponawiania; inne wyjątki - ponawiane.

## Konfiguracja
- `get_config` (`roboforge.processing.utilities`), zwykle z pliku `config.yml`.

## Na co zwrócić uwagę w przewodniku
- Do uzupełnienia w kroku 42.
