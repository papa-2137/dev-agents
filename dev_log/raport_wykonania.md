# Dev-Agents: raport wykonania

> Postęp względem `dev_log/plan_kroki.md` (kroki) i `dev_log/plan.md` (wymagania i ustalenia). Uzupełniany przez inżyniera po każdym kroku.
> Legenda: ✅ zrobione · 🟡 w toku / częściowo · ⬜ nie zaczęte

## Podsumowanie

| Faza | Status |
|---|---|
| A - Fundament (kroki 1-5) | ✅ zakończona (M1) |
| B - Dostęp do modelu (6-8) | ✅ zakończona (M2) |
| C - Mapa projektu bez modelu (9-29) | 🟡 w toku |
| D - Szablon przewodnika i HTML bez modelu (30-39) | ⬜ |
| E - Prompty i baza wiedzy (40-42) | ⬜ |
| F - Graf i agenci (43-59) | ⬜ |
| G - Ergonomia (60-63) | ⬜ |
| H - Miasto (64-68) | ⬜ |

Kamienie milowe: M1 (krok 5) ✅ 2026-11-24 · M2 (8) ✅ 2026-11-24 · M3 (29) ⬜ · M4 (39) ⬜ · M5 (59) ⬜ · M6 (68) ⬜

Wymagania produktu W1-W8 (plan, sekcja 1): ⬜ makieta `dev_log/guide_mockup.html` zaakceptowana

---

## Kroki

<!-- Wzór wpisu:
### Krok N. Tytuł - ✅
- Co zrobione (pliki, najważniejsze funkcje).
- Odstępstwa od planu i powód.
- Test użytkownika: wynik.
-->

### Krok 1. `.gitignore`, README i dziennik prac - ✅
- `.gitignore`: standardowy szablon Pythona z GitHuba (odtworzony bez pobierania z sieci) + sekcja `# --- dev-agents ---`: `venv/`, wzorce sekretów (`*.pfx`, `*.p12`, `*.pem`, `*.key`, `*.crt`, `.env*`), pliki systemowe (`Thumbs.db`, `desktop.ini`, `~$*`).
- `README.md`: tytuł i jedno zdanie, pisane grypsem (rozbudowa w kroku 63).
- `dev_log/` i `AGENTS.md` na miejscu; w `dev_log/` dodatkowo `wiadomosc_startowa.md` (wiadomość startowa architekta, zostaje dla potomnych).
- Przed krokiem, na prośbę użytkownika: gryps „towar” / „Kwadrat” / „miasto” wprowadzony do plików repo, lekcje z uruchomienia doc-agents na mieście dopisane do kroków 4, 7, 8, 13, poprawki nazw w planie (tabela decyzji). Uwaga użytkownika: gryps obowiązuje także, a nawet zwłaszcza, w README.
- Test użytkownika: `git status` tylko z zamierzonymi plikami, `venv` i `*.pfx` ignorowane - OK.

### Krok 2. venv - ✅
- Weryfikacja istniejącego `venv` (utworzony z Pythona 3.14.10, `pythoncore-3.14-64`), aktualizacja `pip`. Bez zmian w plikach repo.
- Test użytkownika: `python --version` → 3.14.10, `sys.executable` → `...\dev-agents\venv\Scripts\python.exe` - OK.

### Krok 3. Pierwsze biblioteki - ✅
- `requirements.txt`: `pyyaml`, `pydantic` (bez wersji, tylko zależności bezpośrednie). Instalacja przez `pip install -r requirements.txt` - od razu sprawdza plik.
- Test użytkownika: `yaml 6.0.4`, `pydantic 2.14.4` - OK.

### Krok 4. Przenieś z doc-agents: `config.yaml` + `config.py` - ✅
- `dev_agents/__init__.py` (docstring), `config.yaml` (sekcje `llm` i `paths`; profile `small`/`medium` na `json_schema`; pod `model`, `api_key_env`, `base_url_env` i `params` zakomentowane linie miejskie; agenci `planner`, `analyst`, `flow_writer`, `writer`, `reviewer`).
- `dev_agents/config.py`: publiczne `load_config` i klasy `LLMProfile`, `LLMConfig`, `PathsConfig`, `AppConfig`; pomocnicze z podłogą: `_check_agent_profiles`, `_check_structured_output_methods`, `_resolve_paths`, `_build_config` (budowa configu oddzielona od czytania pliku - test psuje kopie w pamięci). Test pod `if __name__ == "__main__":`.
- Odstępstwa od doc-agents (wybory użytkownika): `structured_output_method` bez wartości domyślnej - wymagane w każdym profilu (1A); nazwa metody sprawdzana zwykłym `if` przy wczytaniu, z listą dozwolonych (2A).
- Test użytkownika: `python -m dev_agents.config` - JSON ze ścieżkami bezwzględnymi; trzy zepsute kopie dają czytelne błędy (nieistniejący profil z listą profili, nieznana metoda z listą dozwolonych, brak metody jako `Field required` ze ścieżką pola) - OK.

### Krok 5. Przenieś z doc-agents: `main.py` czyta config - ✅ (M1)
- `main.py`: `_parse_args` (`--config` domyślnie obok `main.py`; `--project` opcjonalny, a podany - sprawdzany, czy istnieje), `_print_summary` (config, agent → profil → model i metoda, katalogi, projekt), `main()` jako spis treści; config importowany jako moduł z aliasem `_config`.
- Wybór użytkownika: `--project` opcjonalny, ale sprawdzany (A) - w kroku 29 zmieni się tylko na wymagany.
- Test użytkownika: podsumowanie z 5 agentami, błąd dla nieistniejącego katalogu, uruchomienie spoza katalogu repo (`python .\dev-agents\main.py --project .\dev-agents`) z tym samym wynikiem - OK. **M1 osiągnięty: szkielet uruchamia się.**

### Krok 6. Biblioteki LLM - ✅
- `requirements.txt`: dopisane `langchain-core` (importowany bezpośrednio: wiadomości, structured output) i `langchain-openai` (`ChatOpenAI`; ciągnie pakiet `openai`).
- Test użytkownika: `langchain_core 1.8.4`, `openai 3.58.0`, import `langchain_openai` bez błędu - OK.
- Uwaga: commit `eb86a41` powstał, zanim dwie linie trafiły do `requirements.txt` (biblioteki były już zainstalowane w venv) - plik uzupełniony po commicie, do osobnego commita.
- Commit uzupełniający: `e46ef32`.

### Krok 7. Przenieś z doc-agents: fabryka modeli `llm.py` - ✅
- `dev_agents/llm.py`: publiczne `get_model_for_agent`, `get_structured_output_method`, `invoke_structured`; pomocnicze z podłogą: `_read_env` (brak zmiennej → błąd z nazwą zmiennej), `_create_chat_model` (`ChatOpenAI` tylko z `params` profilu), `_build_schema_error_message`, `_build_length_error_message`.
- Rozszerzenie względem doc-agents (lekcja z miasta): przy `json_schema` biblioteka openai sama rzuca `pydantic.ValidationError` i `openai.LengthFinishReasonError`, z pominięciem `include_raw` - pierwszy jest ponawiany jak każda niezgodna odpowiedź, drugi daje od razu czytelny błąd z końcówką uciętej odpowiedzi (widać zapętlenie modelu) i podpowiedzią o `max_tokens`.
- Test w bloku `__main__`: udawany model (4 scenariusze: `ValidationError` → ponowienie → OK; dwa razy `ValidationError` → błąd po 2 próbach; `LengthFinishReasonError` → błąd po 1 wywołaniu; `None` z `finish_reason=length` → błąd po 1 wywołaniu), brak zmiennej środowiskowej, prawdziwy model agenta `planner`.
- Test użytkownika: wszystkie scenariusze zgodne z oczekiwanymi; prawdziwy model `claude-haiku-5-5` odpowiada (0.6 s, `usage_metadata` obecne), `invoke_structured` z `json_schema` zwraca obiekt w schemacie - OK.
- Commit: zbiorczy `c349949` razem z regułą stylu 9 (tabela decyzji).

### Krok 8. Przenieś z doc-agents: `scripts/probe_llm.py` - ✅ (M2)
- `scripts/probe_llm.py` (bez `__init__.py`, uruchamiany przez `python -m`): testy proste wywołanie, system + user, trzy metody structured output, `bind_tools`; na końcu diagnoza z rekomendacją. Kod przepisany pod reguły repo (podłogi, parametry w osobnych liniach, bez wyrażeń warunkowych i list z warunkiem, logika oddzielona od wypisywania). Brak `manual_test()` - moduł z `main()`, jego uruchomienie jest testem (AGENTS.md, Styl kodu pkt 8).
- Rozszerzenia względem doc-agents (lekcja z miasta): każda metoda testowana na schemacie płaskim i **zagnieżdżonym** (lista obiektów z listą w środku); rekomendowana jest tylko metoda działająca na obu, w kolejności `json_schema`, `function_calling`, `json_mode`; metoda działająca tylko na płaskim dostaje ostrzeżenie o fałszywym „OK”; structured output przez `invoke_structured` z jedną próbą (ta sama droga co u agentów); błąd spłaszczony do jednej linii (widać np. `input_value={}`); brak zmiennej środowiskowej i zła nazwa profilu dają jedną czytelną linię.
- Wybory użytkownika: 1A - `_create_chat_model` w `dev_agents/llm.py` przemianowane na `create_chat_model` (świadoma zmiana interfejsu, reguła 13), skrypt testuje profil; 2A - structured output przez `invoke_structured`.
- Test użytkownika: `--help` i literówka w profilu - OK; `small` (`claude-haiku-5-5`): `json_schema` i `function_calling` OK na obu schematach, `json_mode` FAIL (400: endpoint przyjmuje tylko `response_format.type` = `json_schema`), `bind_tools` OK, rekomendacja `json_schema` = config; `medium` (`claude-sonnet-5-5`): tylko `json_schema` OK, `function_calling` FAIL (400: wymuszony `tool_choice` nieobsługiwany przez model), `json_mode` FAIL jak wyżej, rekomendacja `json_schema` = config; `python -m dev_agents.llm` po zmianie nazwy - bez zmian - OK. **M2 osiągnięty: model gotowy.**
- Wniosek: na Kwadracie `json_schema` to jedyna metoda działająca na obu profilach - potwierdza domyślną metodę z configu; różnica `function_calling` między Haiku a Sonnetem pokazuje, że skrypt trzeba uruchamiać dla każdego profilu osobno.

### Krok 9. Drugi robot testowy: bez frameworku, „spaghetti” - ✅
- `C:\Users\jankiwoj_box\Documents\projects\claude\tests\02_robot_bez_frameworku` (poza repo, jak robot 01): przetwarzanie zamówień z plików CSV - sprawdzanie wierszy, rabaty, duplikaty, odrzuty, archiwum, wyniki JSON/CSV, raport `.xlsx`.
- `run.bat` (`python przetwarzanie.py`, potem `python raport.py`, domyślny Python z PATH; przy błędzie przetwarzania bez raportu), `przygotuj_dane.bat` (kopiuje `dane\przyklady\` do `dane\wejscie\` - powtarzalne uruchomienia; drugi plik uruchamiający dla kroku 20).
- `przetwarzanie.py`: 17 stałych na górze (m.in. `URL`, `INPUT_DIR`, `OUTPUT_DIR`, `ENV_PASSWORD = "ROBOT02_PASS"`, przełącznik `WYSYLKA_DO_API = False`), funkcja pomocnicza `log()` i **`run()` na 371 linii** (zagnieżdżenie do 8 poziomów, pętla po plikach, kilkanaście `try/except`, wysyłka przez `requests` z ponawianiem tylko po włączeniu przełącznika). `raport.py`: `openpyxl`, 4 arkusze, zdublowana stała `OUTPUT_DIR`. Bez pliku konfiguracyjnego, docstringów i README; `requirements.txt`: `openpyxl`, `requests` (UTF-8 - UTF-16 sprawdza robot 01).
- Przykłady: plik poprawny, plik z 6 błędnymi wierszami i duplikatem, pusty plik, zły nagłówek, `notatka.txt` (złe rozszerzenie).
- Celowo zostawione „ryzykowne miejsca” do sprawdzenia przewodnika: ścieżki względne (robot działa tylko uruchomiony z własnego katalogu - pilnuje tego `cd /d %~dp0` w `run.bat`); `0.10 + 0.02` daje `0.12000000000000001`, więc dla VIP z produktem PROMO robot loguje „przekracza limit” i obcina do 0.12 (wynik poprawny, komunikat mylący); mieszane separatory ścieżek w logu (`dane/odrzucone\...`).
- Wybór użytkownika: A - obie paczki naprawdę używane (instalacja w domyślnym Pythonie).
- Test użytkownika: domyślny Python z PATH to 3.12 (inny niż venv towaru - dobrze, robot nie zależy od towaru); `run.bat` → `KONIEC: plikow przetworzonych 2, odrzuconych 3, zamowien 10, blednych wierszy 7, duplikatow 1`, raport `.xlsx`; katalogi `archiwum`, `odrzucone`, `wyjscie` zgodne z oczekiwanymi, `wejscie` puste; `run()` = 371 linii - OK.

### Krok 10. Odczyt obcych plików: `files.py` - ✅
- `dev_agents/files.py`: publiczne `read_text_safe(path)`; pomocnicze `_decode_bytes` (BOM UTF-8 / UTF-16 LE / UTF-16 BE; bez BOM ścisły UTF-8, potem cp1250, na końcu UTF-8 z zamianą złych bajtów - nigdy nie rzuca błędu dekodowania), `_normalize_newlines` (`\r\n` i `\r` → `\n`, numery linii bez zmian), `_read_text_with_encoding` (zwraca też użyte kodowanie - dla testu). Błędy systemu plików (brak pliku, uprawnienia) nie są łapane - wołający dostaje `OSError`; limity rozmiaru sprawdza wołający.
- Odstępstwo od planu (wybór użytkownika B): fallback cp1250 przed zamianą błędów (tabela decyzji, `plan_kroki.md` krok 10).
- Test w bloku `__main__`: pliki tymczasowe UTF-8 bez BOM i z BOM, UTF-16 BE z BOM, cp1250 (tworzone i usuwane w teście), `requirements.txt` robota 01 (tylko ten plik - bez `certs`), `przetwarzanie.py` robota 02.
- Test użytkownika: wszystkie przypadki z czytelnymi polskimi znakami, robot 01 `utf-16-le (BOM)` z czytelnymi nazwami paczek, robot 02 `utf-8` - OK.

### Krok 11. Przenieś z doc-agents: `schemas.py` - mapa projektu - ✅
- `dev_agents/schemas.py`: `FileEntry` (`path`, `role`, `size_bytes`, `framework_name` - domyślnie `""` = kod projektu), `CodeUnit` (`name`, `files`), `ProjectMap` (`project_name`, `root`, `technology`, `entrypoints`, `files`, `code_units` i nowe `frameworks: list[str] = []` - frameworki wykryte po importach, `[]` = robot bez frameworku). Same typy i komentarze, bez `Field(description=...)` - to nie są schematy odpowiedzi modelu. Lista ról w docstringu `FileEntry` (`Uwaga:` - `launcher` dochodzi w kroku 20).
- Odstępstwo od planu (wybór użytkownika A): bez pól `dependency_files` i `config_files` - dochodzą ze swoimi klasami w krokach 23-24 (tabela decyzji).
- Test w bloku `__main__`: ręcznie złożona mapa robota 02 (7 plików, 2 jednostki kodu, `frameworks=[]`), zapis do JSON i odczyt.
- Test użytkownika: JSON zgodny z oczekiwanym, `Odczyt z JSON zgodny z oryginałem: True` - OK. Commit wykonany przez użytkownika (wpis do raportu trafia do commita kroku 12).

### Krok 12. Przenieś z doc-agents: `technologies/base.py` - ✅
- `dev_agents/technologies/__init__.py` (sam docstring - rejestr w kroku 17), `dev_agents/technologies/base.py`: klasa `Technology` z sześcioma metodami z doc-agents (`name`, `detect`, `is_source`, `find_entrypoints`, `outline`, `imports`), w klasie bazowej `NotImplementedError` z nazwą klasy i metody; zwykłe metody, bez `abc` (zasada prostoty).
- Zmiany względem doc-agents: w umowach wspólnych pliki projektu czytane wyłącznie przez `files.read_text_safe()` (zamiast `utf-8` + `errors="replace"`); w docstringu zasada rozwoju kontraktu (nowa metoda z domyślnym zachowaniem ogólnym w klasie bazowej); klasa demonstracyjna i funkcje testu w bloku `__main__`.
- Odstępstwo od planu (wybór użytkownika A): nowe metody kontraktu dochodzą w swoich krokach (tabela decyzji).
- Test użytkownika: wyniki klasy `demo` zgodne z oczekiwanymi, `NotImplementedError: Technology.detect() - do implementacji` - OK. Commit `fe14cc8`.

### Krok 13. Przenieś z doc-agents: `technologies/python.py` - szkielet pliku - ✅ (zmieniony przy uproszczeniu)
- `dev_agents/technologies/python.py`: `PythonTechnology(_base.Technology)` z `outline()` (pozostałe metody w krokach 14-16); `_parse_python()` - jedyne miejsce parsowania cudzego kodu, wycisza `SyntaxWarning` (napisy typu `"C:\folder"` bez `r`); szkielet: liczba linii, opis modułu, stałe, zmienne modułu, kod poza funkcjami (instrukcje, odcinki linii, pętle, `try`), klasy z bazami i metodami, funkcje z sygnaturą, dekoratorami, pierwszym akapitem docstringu i zakresem linii. Plik czytany przez `files.read_text_safe`. Pomocnicze funkcje z doc-agents przepisane bez wyrażeń warunkowych, generatorów i list z warunkiem. Jedyny moduł towaru z `import ast`.
- Odstępstwo od doc-agents (wybór użytkownika A): przy błędzie składni `outline()` zwraca linię `Szkielet niedostępny: błąd składni w linii N (...)` zamiast pustego tekstu; zdanie o wyniku w kontrakcie `base.py` poprawione (tabela decyzji).
- Test w bloku `__main__`: robot 01 (`Main.py`, `src/parabank_page.py`), robot 02 (`przetwarzanie.py` - `run()` 371 linii), plik tymczasowy ze ścieżką Windows w zwykłym napisie (0 ostrzeżeń, zwykłe `ast.parse` - 2), plik w składni Pythona 2 (linia z przyczyną); tryb z argumentami `<katalog> <plik>` dla dowolnego pliku - do użycia na mieście (bez robotów testowych przypadki 1-3 są pomijane, 4-5 działają).
- Test użytkownika: OK. Commit `6d49f30`.

### Krok 14. Przenieś z doc-agents: `technologies/python.py` - importy - ✅ (zmieniony przy uproszczeniu)
- `PythonTechnology.imports()` i pomocnicze `_imported_modules` (importy także w funkcjach i w `try`), `_resolve_relative` (import względny → pełna nazwa), `_is_project_module`, `_classify_module` (najpierw projekt, potem `sys.stdlib_module_names` + 25 modułów usuniętych w Pythonie 3.12-3.13, reszta `external`), `_module_file` (nazwa modułu → ścieżka pliku: `src.report` → `src/report.py`, pakiet → `__init__.py`). Odczyt przez `files.read_text_safe`, parsowanie przez `_parse_python`; przy błędzie składni puste grupy; importy dynamiczne niewykrywane (`Uwaga:`).
- Odstępstwa od doc-agents (wybory użytkownika: wariant 1 i A): `internal` to ścieżki względne plików projektu (kontrakt w `base.py` zaktualizowany - graf w kroku 28 łączy pliki bez wiedzy o technologii; UiPath i Robot Framework dają ścieżki naturalnie); moduły usunięte ze stdlib liczone jako `stdlib` (tabela decyzji, `plan_kroki.md` kroki 14 i 28).
- Test w bloku `__main__`: pod każdym szkieletem z kroku 13 importy; nowy przypadek - pakiet tymczasowy (import względny, import w funkcji, `telnetlib` w `try`).
- Test użytkownika: robot 01 `Main.py` - 6 plików `src/*.py` w `internal`, 4 moduły `roboforge.*` w `external`, `os, pathlib, time` w `stdlib`; robot 02 - `requests` / `csv, datetime, json, os, shutil, sys`; pakiet - `pakiet/narzedzia.py`, `requests`, `os, telnetlib`; Python 2 - puste grupy; wszędzie 0 ostrzeżeń - OK. Kosmetyka testu: w nagłówku przypadku mieszane separatory (`...\src/parabank_page.py`) - tylko wyświetlanie w teście.

### Krok 15. `technologies/python.py` - szkielet sterowania i miary złożoności - ✅, potem wycofany (uproszczenie)
- `schemas.FunctionMetrics` (`path`, `name`, `start_line`, `end_line`, `lines`, `max_depth`, `branches` - same liczby). W kontrakcie `base.py` dwie nowe metody z domyślną odpowiedzią „brak danych”: `control_outline(root, path, function_name)` (linia „niedostępny dla technologii”) i `metrics(root, path)` (pusta lista).
- `python.py`: `control_outline` - nagłówek z zakresem linii, potem `if`/`elif`/`else` (elif na jednym poziomie), pętle (z `else`), `try`/`except`/`else`/`finally`, `with`, `match`, wyjścia (`raise` z nazwą wyjątku) i wywołania funkcji po nazwie, funkcji modułów i `self` (bez metod na danych); prosty blok w jednej linii `[wywołania; -> wyjście]`; `function_name` = `run`, `Klasa.metoda` albo `""` (kod poza funkcjami); nieznana nazwa → linia z listą dostępnych funkcji. `metrics` - kod poza funkcjami (`<kod poza funkcjami>`) i każda funkcja oraz metoda: długość, głębokość (elif na poziomie swojego `if`), rozgałęzienia (if/elif, pętle, except, wyrażenia warunkowe, and/or, warunki w wyrażeniach listowych, case). Funkcje zagnieżdżone liczą się do funkcji, w której leżą.
- Odstępstwa od planu (wybory użytkownika A, tak, A): wywołania bez metod na danych; kryterium testu „ok. 1/3 długości funkcji” zamiast „jeden ekran”; progi `analysis.complexity` w configu dopiero w kroku 35 (tabela decyzji, `plan_kroki.md` kroki 15 i 35).
- Test w bloku `__main__`: szkielet sterowania `run()` i kodu poza funkcjami robota 02, miary robotów 01 i 02 (także `raport.py`) i pliku w Pythonie 2; tryb `<katalog> <plik> <funkcja>`.
- Test użytkownika: `run()` - 129 linii szkieletu z 371 linii kodu, wszystkie poziomy; miary `run` 371 / głębokość 6 / 80 rozgałęzień, funkcje robota 01 do 19 linii i głębokości 1; Python 2 - brak danych - OK. Uwaga: głębokość `run()` wynosi 6 (w kroku 9 szacunek „do 8” liczył `elif` jako zagnieżdżenie). Commit `21f57f4`.

### Krok 16. Przenieś z doc-agents: `technologies/python.py` - wykrywanie i punkty wejścia - ✅
- `PythonTechnology.is_source()` (`.py`, `.pyw`), `detect()` (choć jeden plik źródłowy), `find_entrypoints()` (blok `if __name__ == "__main__":` na poziomie modułu oraz `main.py`/`__main__.py`; kolejność: `main.py`/`__main__.py`, potem płytsze, potem alfabetycznie); pomocnicze `_is_main_guard`, `_has_main_guard` (plik z błędem składni → `False`), `_entrypoint_sort_key`. Nazwa `main.py` porównywana bez względu na wielkość liter (Windows). Odczyt przez `files.read_text_safe`, parsowanie przez `_parse_python`; funkcje z doc-agents bez `any(...)`, wyrażeń warunkowych i generatorów.
- Wybór użytkownika B (jak w doc-agents): bez zapasowego wyszukiwania bloku `__main__` w plikach, których nie da się sparsować - zespół nie ma robotów w Pythonie 2.
- Test w bloku `__main__`: sekcja `=== Projekt ===` dla robotów 01 i 02, katalogu tymczasowego (moduł z blokiem `__main__`) i katalogu bez kodu; lista plików budowana w teście z pominięciem katalogów z `pyvenv.cfg` i `__pycache__` (skaner dopiero w kroku 18). Poprawiona nazwa przypadku robota 01: `main.py` (wcześniej `Main.py` - działało tylko dzięki Windows).
- Test użytkownika: OK. Commit `75d1043`.

### Krok 17. Przenieś z doc-agents: `technologies/uipath.py` + rejestr; puste klasy Robot Framework i NICE - ✅
- `dev_agents/technologies/registry.py`: `available_technologies()` (kolejność: uipath, robotframework, nice, python), `detect_technology()`, `get_technology()`; importy technologii na górze pliku. `__init__.py` pakietu bez importów (opis w docstringu).
- Puste klasy `uipath.py`, `robotframework.py`, `nice.py`: `detect` → `False`, metody → `NotImplementedError` z nazwą klasy; opis, co trzeba uchwycić (w Robot Framework delegacja plików `.py` do `PythonTechnology`, w NICE otwarte pytania o formaty plików). Bez `manual_test()` - brak logiki, zachowanie sprawdza test rejestru.
- Odstępstwo od planu (wybór użytkownika B): rejestr w osobnym module zamiast w `__init__.py` (tabela decyzji).
- Test użytkownika: rejestr z 4 technologiami (3 puste), `detect_technology` → `python` dla robota i dla projektu UiPath z plikiem `.py` (UiPath pusty), `None` dla samych danych, `get_technology` i `NotImplementedError` pustej klasy - OK. Commit `a3e551b`.

### Uproszczenie analizy deterministycznej (po kroku 17) - ✅
- Powód (użytkownik): `python.py` (1111 linii kodu) i funkcje z wieloma warunkami byłyby trudne w utrzymaniu; ciężar analizy kodu przechodzi na agentów, „nawet kosztem przyszłych tokenów”. Wybrany wariant pośredni: kod podaje tylko proste, pewne fakty, łatwe do napisania dla każdej technologii.
- Kontrakt `technologies/base.py`: metody wymagane `detect`, `is_source`, `find_entrypoints` (`NotImplementedError`); opcjonalne `units` (jednostki z zakresami linii) i `references` (pliki projektu i pakiety) z odpowiedzią „brak danych”. Zasada: każda metoda ok. 40 linii prostego kodu, bez drzewa warunków. Usunięte: `outline`, `imports`, `control_outline`, `metrics`.
- `schemas.py`: zamiast `FunctionMetrics` - `SourceUnit` (`name`, `start_line`, `end_line`) i `References` (`files`, `packages`).
- `technologies/python.py`: z 1111 do 271 linii kodu (test 143): `_parse_python` (odczyt + `ast` z wyciszonym `SyntaxWarning`, błąd składni → `None`), `units` (funkcje i metody), `references` (pliki projektu jako ścieżki, pakiety bez biblioteki standardowej - bez listy modułów usuniętych w 3.12-3.13), `detect`, `is_source`, `find_entrypoints`. Usunięte: szkielet pliku, szkielet sterowania, miary złożoności, podział importów na trzy grupy.
- Puste klasy UiPath, Robot Framework, NICE i test rejestru dostosowane do nowego kontraktu (opis w docstringu modułu, jak prosto zrealizować każdą metodę).
- Plan: kroki 15, 25, 26 wycofane (numeracja bez zmian); 12-14, 16, 17, 19-24, 28, 29, 31, 35, 47, 49-51, 55, 56 przepisane - nowy `masking.py` (krok 20, maskowanie liniowe zamiast parserów konfiguracji), pliki zależności bez metody technologii (rola `dependency`), konfiguracja i pliki uruchamiające jako zamaskowany tekst dla agentów (krok 24), metryczka i komentarze do „Ryzykownych miejsc” od agentów, długie pliki dzielone po granicach jednostek; `plan.md` (podział pracy kod - agenci, rozszerzalność, style robotów, struktura, sekcje configu `scan` i `analysis`); `AGENTS.md` reguła 7 i `zasady_pracy.md`.
- Test użytkownika: OK. Commit `ea5323d`. Nazwy `CodeUnit` (jednostka kodu do analizy - plik) i `SourceUnit` (funkcja/metoda w pliku) zostają bez zmian.

### Krok 18. Przenieś z doc-agents: `scanner.py` - lista plików - ✅
- `dev_agents/scanner.py`: `list_files(root, scan_config)` - posortowane ścieżki względne z separatorem `/`; pomocnicze `_is_ignored` (wzorce `fnmatch`) i `_is_skipped_directory` (zawsze `dev_agents_doc/` i katalogi z `pyvenv.cfg`, poza tym `scan.ignore`). Skaner tylko listuje nazwy, nie otwiera plików.
- `config.yaml`: sekcja `scan.ignore`; `config.py`: `ScanConfig`, `AppConfig.scan` wymagane (wybór użytkownika A - bez wartości domyślnych w kodzie); test configu z czwartym przypadkiem (brak sekcji `scan`).
- Test w bloku `__main__`: roboty 01 i 02, katalog tymczasowy z `dev_agents_doc`, `.git`, `__pycache__` i środowiskiem wirtualnym o własnej nazwie; tryb `<katalog>`.
- Test użytkownika: OK. Commit `16c5208`.

### Krok 19. Przenieś z doc-agents: `scanner.py` - role plików i sekrety - ✅
- `scanner.build_file_entries(root, files, scan_config, technology)` → `FileEntry` (ścieżka, rola, rozmiar); `_file_role` (najpierw `secret` z `scan.secret_patterns`, potem `source` wg technologii, potem `_role_from_patterns` - pierwsza pasująca rola z `scan.role_patterns`, bez dopasowania `other`). Skaner nie otwiera plików.
- `config.yaml`: `scan.secret_patterns`, `scan.role_patterns` (kolejność: dependency, config, launcher, docs, data, binary); `config.py`: pola w `ScanConfig`, `_check_role_names` (nieznana rola → błąd przy starcie, piąty przypadek w teście configu); `schemas.py`: pełna lista ról w opisie `FileEntry`, przykładowa mapa z rolami `launcher` i `dependency`.
- Odstępstwo od doc-agents (wybór użytkownika A): bez wykrywania binarek po treści (tabela decyzji).
- Test użytkownika: OK. Commit `1212c51`.

---

## Odstępstwa i decyzje poza planem

| Data | Decyzja | Powód |
|---|---|---|
| 2026-11-24 | Plan przebudowany pod wymagania W1-W7 (diagram przepływu jako MUST, 62 kroki) | Wymagania użytkownika co do zawartości przewodnika |
| 2026-11-24 | Dodana metryczka robota z pliku konfiguracyjnego (W8): rozszerzony krok 21, nowy krok 22, plan ma 63 kroki | Prośba użytkownika |
| 2026-11-24 | Rozszerzalność zapisana w planie: konfiguracja i zależności przez kontrakt technologii, puste klasy UiPath / Robot Framework / NICE, filtr `technologies` w szablonie, frameworki z plikiem wiedzy w configu (kroki 11, 15, 18, 20-22, 26, 38, 58) | Kolejne technologie i frameworki bez zmian w rdzeniu |
| 2026-11-24 | Obsługa robotów bez frameworku i „spaghetti”: robot testowy 02 (krok 9), szkielet sterowania i miary (15), pliki uruchamiające (20), ustawienia w kodzie (26), analiza długich funkcji po kawałkach (51), limit diagramu, puste pola zamiast wymysłu, „Ryzykowne miejsca”; plan podzielony na `plan.md` i `plan_kroki.md`, 68 kroków | Roboty zespołu są pisane bardzo różnie |
| 2026-11-24 | Gryps w plikach repo: „towar” = ten projekt, „Kwadrat” = miejsce, w którym towar powstaje, „miasto” = praca; wzmianki o miejscu powstawania kodu zastąpione „Kwadratem” (`AGENTS.md`, `zasady_pracy.md`, `plan.md`, `plan_kroki.md`, `wiadomosc_startowa.md`) | Decyzja użytkownika: repo trafia na miasto (krok 64) |
| 2026-11-24 | Lekcje z uruchomienia doc-agents na mieście dopisane do planu: krok 4 (format linii miejskich), krok 7 (łapanie `ValidationError` i `LengthFinishReasonError` rzucanych przez bibliotekę openai przy `json_schema`), krok 8 (`probe_llm` testuje schemat zagnieżdżony, rekomendacja od `json_schema`), krok 13 (wyciszenie `SyntaxWarning` przy parsowaniu cudzego kodu) | Na mieście płaski schemat w `probe_llm` dawał fałszywe „OK”, wyjątki biblioteki omijały ponawianie, ostrzeżenia zasypywały ekran; decyzja użytkownika |
| 2026-11-24 | Plan: zakładka nazywana w W5 i W8 „Przegląd i uruchomienie” (jak w W2); w kroku 30 usunięta zdublowana „Błędy i naprawa”; w kroku 9 robot 02 uruchamiany domyślnym Pythonem z PATH | Ujednolicenie nazw i decyzja użytkownika |
| 2026-11-24 | Krok 4: `structured_output_method` wymagane w każdym profilu (doc-agents: domyślnie `function_calling`) i sprawdzane przy wczytaniu configu | Metoda zależy od endpointu i decydowała na mieście o działaniu - ma być widoczna w configu, a literówka wychodzić przy starcie; wybór użytkownika |
| 2026-11-24 | Nowa reguła stylu (AGENTS.md, Styl kodu pkt 9): każdy parametr definicji funkcji w osobnej linii, także pojedynczy (`self`/`cls` też), przecinek po ostatnim; funkcja bez parametrów w jednej linii. Przeformatowane wszystkie definicje w `main.py`, `dev_agents/config.py`, `dev_agents/llm.py` (bez zmian zachowania). Reguła dopisana też do `dev_log/zasady_pracy.md`, `architecture/02_dev-agents/reguly-kodu.md` (pkt 7) i `development/doc-agents/AGENTS.md` (reguły z 2026-11-24, pkt 6) | Decyzja użytkownika: czytelność sygnatur i czytelne diffy |
| 2026-11-24 | Krok 10: `read_text_safe` bez BOM czyta najpierw ścisłym UTF-8, potem cp1250, a dopiero na końcu UTF-8 z zamianą błędów (plan: od razu UTF-8 z `errors="replace"`); `plan_kroki.md` krok 10 zaktualizowany | Na mieście będą pliki z polskiego Windows w cp1250 (`.bat`, `.ini`) - bez tego polskie znaki trafiałyby do modelu jako `�`; wybór użytkownika (B) |
| 2026-11-24 | Krok 11: `ProjectMap` bez pól `dependency_files` i `config_files` - dochodzą razem ze swoimi klasami w krokach 23-24 (plan: pola od razu); `plan_kroki.md` krok 11 zaktualizowany | Bez pustych zaślepek i typów zgadywanych na zapas (AGENTS.md, Sposób pracy pkt 4); nowe pola będą miały wartość domyślną, więc nic się nie zepsuje; wybór użytkownika (A) |
| 2026-11-26 | Krok 12: w `Technology` tylko sześć przenoszonych metod; nowe metody kontraktu (kroki 15, 23-26, 42) dochodzą w swoich krokach razem z domyślnym zachowaniem i typem wyniku (plan: wszystkie od razu); `plan_kroki.md` krok 12 zaktualizowany | Jak w kroku 11 - bez zaślepek i sygnatur do zmiany; każda metoda powstaje razem z testem; wybór użytkownika (A) |
| 2026-11-26 | Krok 13: `outline()` przy błędzie składni zwraca jedną linię z przyczyną (np. kod w Pythonie 2) zamiast pustego tekstu (doc-agents); zdanie o wyniku `outline` w kontrakcie `technologies/base.py` poprawione | Analityk i przewodnik wiedzą, dlaczego szkieletu brak - informacja do „Ryzykownych miejsc” zamiast cichej dziury; wybór użytkownika (A) |
| 2026-11-26 | Krok 14: (1) kontrakt `imports()` - grupa `internal` to ścieżki względne plików projektu, nie nazwy modułów (doc-agents: `src.report`); (2) moduły usunięte z biblioteki standardowej w Pythonie 3.12-3.13 (PEP 594, `distutils`, `imp`) liczone jako `stdlib`; `plan_kroki.md` kroki 14 i 28 zaktualizowane | (1) Graf zależności (krok 28) łączy pliki bez wiedzy o technologii - UiPath (*Invoke Workflow File*) i Robot Framework (`Resource`) dają ścieżki naturalnie, Python zamienia nazwę na plik u siebie (reguła 7); (2) robot na starszym Pythonie nie dostaje fałszywych zależności „do zainstalowania”; wybór użytkownika (wariant 1, A) |
| 2026-11-26 | Krok 15: (1) w szkielecie sterowania tylko wywołania funkcji po nazwie, funkcji modułów i `self` (bez metod na danych), prosty blok w jednej linii; (2) kryterium testu „mieści się na jednym ekranie” zmienione na „ok. 1/3 długości funkcji, wszystkie poziomy warunków z liniami”; (3) `metrics()` zwraca same liczby (`FunctionMetrics`), progi `analysis.complexity` w configu dochodzą w kroku 35; `plan_kroki.md` kroki 15 i 35 zaktualizowane | (1) widać kontakty z systemami (`requests.post`, `shutil.move`) potrzebne do diagramu, bez szumu `.strip()`/`.append()`; (2) funkcja z ok. 100 punktami decyzji nie mieści się na ekranie bez gubienia poziomów (prototyp: `run()` - 129 linii z 371); (3) progi powstają razem z pierwszym użytkownikiem, technologia nie zależy od configu; wybór użytkownika (A, tak, A) |
| 2026-11-26 | **Warunkowo, do zmiany później:** testy ręczne (`dev_agents.files`, `technologies.python`) szukają robotów testowych w `<repo>/../../tests/<robot>`; brak robota → przypadek pomijany z komunikatem. Sposób przeróbki do omówienia z użytkownikiem (np. argument `--tests-dir`) | Decyzja użytkownika: zostaje na razie, ale trzeba będzie to zmienić |
| 2026-11-26 | Krok 17: rejestr technologii w osobnym module `technologies/registry.py` zamiast w `technologies/__init__.py` (plan, doc-agents); `__init__.py` bez importów; `plan.md` (struktura) i `plan_kroki.md` krok 17 zaktualizowane | `__init__.py` uruchamia się przy każdym `python -m dev_agents.technologies.<technologia>` - importy technologii w nim ładowałyby moduł dwa razy (`RuntimeWarning`); osobny moduł ma importy na górze (reguła 14) i test przez `-m` jak wszędzie; wybór użytkownika (B) |
| 2026-11-26 | **Uproszczenie analizy deterministycznej:** kod podaje tylko proste fakty (role, sekrety, punkty wejścia, jednostki z zakresami linii, odwołania między plikami, zależności dosłownie, maskowanie haseł), rozumienie kodu robią agenci; kontrakt technologii: wymagane `detect`/`is_source`/`find_entrypoints`, opcjonalne `units`/`references`, każda metoda ok. 40 linii; usunięte szkielet pliku, szkielet sterowania, miary, `FunctionMetrics`; kroki 15, 25, 26 wycofane, pozostałe dotknięte kroki przepisane; konfiguracja maskowana liniowo (`masking.py`) zamiast parserów z typami wpisów; `AGENTS.md` reguła 7 | Decyzja użytkownika: kod ma być prosty w utrzymaniu, nawet kosztem tokenów w czasie działania; wariant pośredni (minimalna analiza deterministyczna łatwa dla każdej technologii) i maskowanie liniowe zgodnie z rekomendacją |
| 2026-11-26 | Krok 19: bez wykrywania plików binarnych po treści (doc-agents: 8 KB i bajt zerowy) - binarne tylko po wzorcach, nieznany plik → `other`; `plan_kroki.md` krok 19 zaktualizowany | Skaner nie otwiera plików; do modelu trafiają tylko pliki o rolach rozpoznanych po wzorcach, więc ryzyko wysłania binarki znika bez dodatkowego kodu; wybór użytkownika (A) |
| 2026-11-26 | **Bez maskowania haseł:** pliki konfiguracyjne i uruchamiające trafiają do agentów dosłownie; krok 20 (`masking.py`) wycofany, krok 24 i wzmianki o `***` w krokach 26, 31, 35, 47, 50, 55, 56 przepisane; `scan.sensitive_keys` usunięte z planu; `plan.md` (W2, W8, podział pracy, „Konfiguracja robota a sekrety”, struktura), `AGENTS.md` reguła 7. Pliki sekretów (`*.pfx`, `.env*`...) nadal tylko jako metadane | Decyzja użytkownika: hasło wpisane wprost to błąd dewelopera, który ma wyjść w przewodniku (agent wskazuje je jako ryzykowne miejsce), a nie zostać ukryty |
