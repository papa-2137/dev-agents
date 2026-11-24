# Dev-Agents: kroki planu

Część planu z krokami. Wymagania (W1-W8), ustalenia, docelowa struktura, zasady wykonania, szkic `config.yaml` i otwarte sprawy: **`dev_log/plan.md`** - przeczytaj przed pierwszym krokiem. Postęp i notatki: `dev_log/raport_wykonania.md`.

Każdy krok: **Funkcja** (co i po co), **Robimy**, **Sprawdzamy**. Roboty testowe: **01** = `tests\01_rpa_challange_roboforge`, **02** = `tests\02_robot_bez_frameworku` (powstaje w kroku 9).

---

Kamienie milowe: **M1** szkielet uruchamia się (krok 5) · **M2** model gotowy (krok 8) · **M3** mapa projektu, metryczka i graf zależności bez modelu (krok 29) · **M4** wygląd przewodnika zatwierdzony na danych bez modelu (krok 39) · **M5** pierwszy pełny przewodnik z modelu (krok 59) · **M6** działa na mieście (krok 68).

### Faza A - Fundament

**Krok 1. `.gitignore`, README i dziennik prac**
- **Funkcja:** repozytorium gotowe do pierwszego commita, z miejscem na notatki inżyniera. Bez `.gitignore` do repo trafiłby venv albo klucze.
- **Robimy:** `.gitignore` (szablon Pythona z GitHuba + `venv/`, `*.pfx`, `*.p12`, `*.pem`, `*.key`, `*.crt`, `.env*`, `Thumbs.db`, `desktop.ini`, `~$*`); krótki `README.md` (jedno zdanie o projekcie, rozbudowa w kroku 63); sprawdzenie, że pliki w `dev_log/` i `AGENTS.md` są na miejscu.
- **Sprawdzamy:** `git status` pokazuje tylko zamierzone pliki, `venv/` jest ignorowany.

**Krok 2. venv**
- **Funkcja:** izolowane środowisko Pythona 3.14 dla projektu (venv już istnieje - krok to weryfikacja).
- **Robimy:** `.\venv\Scripts\Activate.ps1`, `python -m pip install --upgrade pip`. Gdyby venv był uszkodzony: usunąć i `py -V:3.14 -m venv venv`.
- **Sprawdzamy:** `python --version` → 3.14.x; `python -c "import sys; print(sys.executable)"` → `...\dev-agents\venv\Scripts\python.exe`.

**Krok 3. Pierwsze biblioteki**
- **Funkcja:** biblioteki do wczytywania konfiguracji (YAML) i opisywania danych typami (Pydantic).
- **Robimy:** `pip install pyyaml pydantic`, dopisanie do `requirements.txt` (bez wersji, bez `pip freeze`).
- **Sprawdzamy:** `python -c "import yaml, pydantic; print(pydantic.VERSION)"`.

**Krok 4. Przenieś z doc-agents: `config.yaml` + `config.py`**
- **Funkcja:** jedno miejsce ustawień narzędzia, wczytywane do obiektów z podpowiedziami w edytorze; przełączanie Kwadrat/miasto bez zmian w kodzie.
- **Robimy:** pakiet `dev_agents/` (`__init__.py`); `config.yaml` z sekcjami `llm` (profile `small`/`medium` z liniami miejskimi pod spodem, `json_schema`, przypisanie agentów: `planner`, `analyst`, `flow_writer`, `writer`, `reviewer`) i `paths`; `config.py` przeniesiony i dostosowany (`load_config`, sprawdzenie profili agentów, ścieżki względne od położenia configu). Linie miejskie według diagnostyki doc-agents na mieście: model w formacie `dostawca/wdrożenie/model` (np. `azure/genai4all/gpt-5-no-filter`, bez `/` na początku), w `BAZOOKA_URL` pełny adres bramki z `http(s)://`, przy modelach GPT-5 zakomentowany `reasoning_effort` w `params`. Pozostałe sekcje dochodzą w krokach, które ich potrzebują.
- **Sprawdzamy:** `python -m dev_agents.config` wypisuje config jako JSON; zła nazwa profilu u agenta → czytelny błąd z listą profili.

**Krok 5. Przenieś z doc-agents: `main.py` czyta config**
- **Funkcja:** punkt wejścia programu uruchamiany z PowerShella.
- **Robimy:** `main.py` z `argparse` (`--config`, domyślnie `config.yaml` obok `main.py`; `--project` na razie opcjonalny), wczytanie configu, podsumowanie.
- **Sprawdzamy:** `python main.py` - także uruchomiony spoza katalogu repo. ✅ **M1**

### Faza B - Dostęp do modelu

**Krok 6. Biblioteki LLM**
- **Funkcja:** klient modeli w protokole OpenAI, używany na Kwadracie i na mieście.
- **Robimy:** `pip install langchain-core langchain-openai`, dopisanie do `requirements.txt`.
- **Sprawdzamy:** `python -c "import langchain_openai"`.

**Krok 7. Przenieś z doc-agents: fabryka modeli `llm.py`**
- **Funkcja:** jedyne miejsce, które tworzy modele z profili configu, oraz wspólne wywołanie structured output dla wszystkich agentów - czytelny błąd zamiast cichego `None`, ponowienie odpowiedzi niezgodnej ze schematem.
- **Robimy:** odczyt zmiennych przez `os.environ` (brak → błąd z nazwą zmiennej), `ChatOpenAI` tylko z podanymi `params`, model dla agenta, metoda structured output z profilu, `invoke_structured` (ponawianie, bez ponawiania przy ucięciu na limicie, podpowiedź o `max_tokens`). Przy `json_schema` odpowiedź sprawdza już biblioteka openai i sama rzuca `pydantic.ValidationError` (odpowiedź niezgodna ze schematem, np. pusty obiekt `{}` z bramki) albo `openai.LengthFinishReasonError` (ucięcie) - oba wyjątki łapane: pierwszy ponawiany jak każda niezgodna odpowiedź, drugi jako czytelny błąd z końcówką uciętej odpowiedzi (widać zapętlenie modelu).
- **Sprawdzamy:** `python -m dev_agents.llm` - krótka odpowiedź z `usage_metadata` i wywołanie `invoke_structured` z małym schematem; nieistniejąca zmienna w `api_key_env` → czytelny błąd; udawany model rzucający `ValidationError` → ponowienie, a po wyczerpaniu prób czytelny błąd; udawany model rzucający `LengthFinishReasonError` → jedno wywołanie i błąd z końcówką odpowiedzi.

**Krok 8. Przenieś z doc-agents: `scripts/probe_llm.py`**
- **Funkcja:** diagnostyka endpointu - które metody structured output działają na danym profilu. Kluczowe na mieście.
- **Robimy:** przeniesienie i dostosowanie (testy: proste wywołanie, system + user, trzy metody structured output, `bind_tools`, tokeny; diagnoza z rekomendacją metody). Rozszerzenie względem doc-agents: każda metoda structured output testowana także na **schemacie zagnieżdżonym** (lista obiektów, jak w planie i notatce) - płaski schemat dawał fałszywe „OK” (na mieście Claude za bramką zwracał przy zagnieżdżeniu `{}` przy `json_schema` albo listę jako tekst przy `function_calling`); rekomendacja w kolejności `json_schema`, `function_calling`, `json_mode`.
- **Sprawdzamy:** `python -m scripts.probe_llm --help`; jedno uruchomienie na `small` daje wyniki zgodne z doc-agents (potwierdzenie poprawnego przeniesienia). ✅ **M2**

### Faza C - Mapa projektu bez modelu

**Krok 9. Drugi robot testowy: bez frameworku, „spaghetti”**
- **Funkcja:** materiał do sprawdzania narzędzia na robocie bez porządku - bez niego ścieżki „brak frameworku”, „start z `.bat`”, „ustawienia w kodzie” i „funkcja na setki linii” nie zostałyby przetestowane przed miastem.
- **Robimy:** `C:\Users\jankiwoj_box\Documents\projects\claude\tests\02_robot_bez_frameworku` (poza repo narzędzia, jak robot 01): `run.bat` wołający `python przetwarzanie.py`, potem `python raport.py` - domyślnym Pythonem z PATH (robot nie ma własnego venv); w `przetwarzanie.py` stałe na górze (`URL`, `INPUT_DIR`, `OUTPUT_DIR`, `ENV_PASSWORD = "ROBOT02_PASS"`) i **jedna funkcja `run()` na ok. 400 linii** z warunkami zagnieżdżonymi na 4-5 poziomów, pętlą po plikach i kilkoma `try/except`; bez pliku konfiguracyjnego, bez docstringów, `requirements.txt` z dwiema paczkami. Robot ma faktycznie działać na lokalnych plikach (bez sieci), żeby jego opis dało się sprawdzić.
- **Sprawdzamy:** `run.bat` przetwarza przykładowe pliki wejściowe i tworzy raport; `python -c "import ast, sys; ..."` (polecenie w raporcie) pokazuje długość `run()` powyżej 300 linii.

**Krok 10. Odczyt obcych plików: `files.py`**
- **Funkcja:** jedna wspólna funkcja do czytania plików analizowanego projektu, odporna na kodowania - problem UTF-16 nie wraca w każdym module z osobna.
- **Robimy:** `read_text_safe(path)`: rozpoznanie BOM (UTF-8, UTF-16 LE/BE), domyślnie UTF-8, zawsze `errors="replace"`.
- **Sprawdzamy:** odczyt `requirements.txt` robota testowego (UTF-16) daje czytelny tekst; zwykły plik `.py` bez zmian.

**Krok 11. Przenieś z doc-agents: `schemas.py` - mapa projektu**
- **Funkcja:** wspólny opis danych o projekcie, przekazywany między skanerem, agentami i rendererem.
- **Robimy:** `FileEntry` (ścieżka, rola, rozmiar, `framework_name`), `CodeUnit`, `ProjectMap` (nazwa, katalog, technologia, punkty wejścia, pliki, jednostki kodu, frameworki wykryte po importach, pliki zależności, pliki konfiguracyjne - dwa ostatnie wypełniane w krokach 23-24).
- **Sprawdzamy:** test składa mapę ręcznie, wypisuje JSON i sprawdza zgodność po odczycie z JSON.

**Krok 12. Przenieś z doc-agents: `technologies/base.py`**
- **Funkcja:** kontrakt technologii - rdzeń nie zna żadnego języka, pyta technologię o pliki źródłowe, punkty wejścia, szkielet i importy.
- **Robimy:** klasa `Technology` z docstringiem-kontraktem: `name`, `detect`, `is_source`, `find_entrypoints`, `outline`, `imports` (przeniesione) oraz nowe, dochodzące w kolejnych krokach: `dependency_files` (krok 23), `config_files` i `parse_config` (krok 24), `config_usages` (krok 25), `control_outline` i `metrics` (krok 15), `code_settings` (krok 26), `knowledge_file` (nazwa pliku wiedzy o technologii, krok 42). Metody nowe mają w klasie bazowej **domyślne zachowanie ogólne** (np. `parse_config` korzysta ze wspólnych parserów), żeby nowa technologia mogła nadpisać tylko to, co ma inaczej. Klasa demonstracyjna przeniesiona do bloku testowego.
- **Sprawdzamy:** test wypisuje wyniki klasy demonstracyjnej i `NotImplementedError` klasy bazowej.

**Krok 13. Przenieś z doc-agents: `technologies/python.py` - szkielet pliku**
- **Funkcja:** „spis treści” pliku Pythona bez treści funkcji - podstawa dla plannera i analityka, tania w tokenach.
- **Robimy:** `outline()` przez `ast` (klasy, metody, funkcje, sygnatury, pierwszy akapit docstringu, zakresy linii, kod poza funkcjami); odczyt przez `files.read_text_safe`; parsowanie cudzego kodu przez jedną funkcję modułu, która wycisza `SyntaxWarning` (Python 3.12+ ostrzega przy każdym parsowaniu napisów typu `"C:\folder"` bez `r` - na mieście zasypywało to ekran).
- **Sprawdzamy:** szkielet `src/parabank_page.py` i `main.py` robota testowego; plik ze ścieżką Windows w zwykłym napisie parsowany bez ostrzeżeń.

**Krok 14. Przenieś z doc-agents: `technologies/python.py` - importy**
- **Funkcja:** podział importów na moduły projektu, biblioteki zewnętrzne i standardowe - źródło grafu zależności i rozpoznawania frameworków.
- **Robimy:** `imports()` z trzema grupami i pełnymi nazwami modułów.
- **Sprawdzamy:** importy `main.py` robota (`roboforge` w zewnętrznych, `src.*` w modułach projektu).

**Krok 15. `technologies/python.py` - szkielet sterowania i miary złożoności**
- **Funkcja:** mapa rozgałęzień długich funkcji i liczby mówiące, gdzie kod jest trudny - liczone przez kod, tanie w tokenach, bez zgadywania. Podstawa obsługi robotów „spaghetti”.
- **Robimy:** `control_outline(path, function)` przez `ast`: drzewo samych `if`/`elif`/`else`, `for`/`while`, `try`/`except`/`finally`, `with`, `return`/`raise`/`break`/`continue` i wywołań funkcji, z numerami linii i tekstem warunku (`ast.unparse`, skrócony), **bez treści gałęzi**; `metrics(path)` dla każdej funkcji: liczba linii, maksymalna głębokość zagnieżdżenia, liczba rozgałęzień; sekcja `analysis.complexity` w configu z progami. Obie metody w kontrakcie `base.py` z opisem i domyślną odpowiedzią „brak danych”.
- **Sprawdzamy:** szkielet sterowania `run()` robota 02 mieści się na jednym ekranie i pokazuje wszystkie poziomy warunków z liniami; miary oznaczają `run()` jako długą; funkcje robota 01 poniżej progów.

**Krok 16. Przenieś z doc-agents: `technologies/python.py` - wykrywanie i punkty wejścia**
- **Funkcja:** rozpoznanie projektu Pythona i miejsc, od których zaczyna się wykonanie.
- **Robimy:** `detect()`, `is_source()`, `find_entrypoints()` (`if __name__ == "__main__":` i pliki wołane z plików uruchamiających - te dochodzą w kroku 20).
- **Sprawdzamy:** dla robota 01 `detect` → `True`, punkt wejścia `main.py`; dla robota 02 - kilka skryptów z `__main__`, każdy wypisany.

**Krok 17. Przenieś z doc-agents: `technologies/uipath.py` + rejestr; puste klasy Robot Framework i NICE**
- **Funkcja:** przygotowane, dobrze opisane miejsca na kolejne technologie (implementacja osobno) i wybór technologii dla projektu.
- **Robimy:** puste klasy z opisem w każdej metodzie, czego technologia ma dostarczyć: `uipath.py` (pliki `.xaml`, `project.json` jako punkt wejścia i zależności, `Config.xlsx` jako konfiguracja - arkusze Settings/Constants/Assets), `robotframework.py` (pliki `.robot`/`.resource`, sekcje Settings/Variables/Keywords, pliki zmiennych; biblioteki `.py` przez **delegację do `PythonTechnology`**, bez kopiowania kodu), `nice.py` (NICE APA - formaty plików do potwierdzenia przez osobę, która będzie ją implementować; opis kontraktu i otwarte pytania w docstringu). `technologies/__init__.py` z rejestrem i `detect_technology()`: technologie sprawdzane w ustalonej kolejności (bardziej szczegółowe przed ogólnymi - Robot Framework przed Pythonem), wygrywa pierwsza pasująca; puste klasy mają `detect` zwracające `False`, dopóki nie są zaimplementowane.
- **Sprawdzamy:** `detect_technology(robot)` → `python`; wypisanie rejestru pokazuje cztery technologie, w tym trzy niezaimplementowane; wywołanie metody pustej klasy → `NotImplementedError` z nazwą technologii.

**Krok 18. Przenieś z doc-agents: `scanner.py` - lista plików**
- **Funkcja:** lista plików projektu bez śmieci (cache, venv, repozytorium gita) i bez wyników narzędzia.
- **Robimy:** sekcja `scan.ignore` w configu; pomijanie katalogów z `pyvenv.cfg`; **zawsze pomijany `dev_agents_doc/`** (niezależnie od configu).
- **Sprawdzamy:** lista plików robota bez `test-venv`, `__pycache__`; ręcznie utworzony `dev_agents_doc/` w kopii robota nie pojawia się na liście.

**Krok 19. Przenieś z doc-agents: `scanner.py` - role plików i sekrety**
- **Funkcja:** każdy plik dostaje rolę (kod, config, uruchamianie, dane, dokumentacja, binarny, sekret); sekrety nigdy nie są otwierane.
- **Robimy:** `scan.secret_patterns`, `scan.role_patterns` w configu; wykrywanie plików binarnych.
- **Sprawdzamy:** tabela `ścieżka | rola | rozmiar`; `client.pfx` → `secret`, `config.yml` → `config`; w robocie 02 `run.bat` → `launcher`.

**Krok 20. `scanner.py` - pliki uruchamiające i prawdziwe punkty wejścia**
- **Funkcja:** diagram i instrukcja uruchomienia zaczynają się od tego, jak robot jest naprawdę startowany (np. `run.bat`, skrypt z Harmonogramu zadań), a nie od zgadywania, który z kilku skryptów jest główny.
- **Robimy:** pliki o roli `launcher` (`.bat`, `.cmd`, `.ps1` - treść czytana przez `files.read_text_safe`, są krótkie i tekstowe; do limitu rozmiaru) przeszukiwane zwykłym kodem pod kątem wywołań `python`/`py`/`pythonw` i ścieżek `.py`; w `ProjectMap` lista uruchomień: plik uruchamiający, linia, wołany skrypt, kolejność. Punkty wejścia z technologii są oznaczane, jeśli wołają je pliki uruchamiające. Wartości wyglądające na hasła w liniach `set`/`$env:` - maskowane jak w konfiguracji (krok 24).
- **Sprawdzamy:** robot 02: `run.bat` → `przetwarzanie.py` (1), `raport.py` (2); robot 01 bez plików uruchamiających → pusta lista, punkt wejścia `main.py` bez zmian.

**Krok 21. `scanner.py` - frameworki po ścieżkach i po importach**
- **Funkcja:** odróżnienie kodu frameworku od kodu robota - także gdy framework jest zainstalowany jako pakiet (np. edytowalnie) i nie leży w projekcie. Rozszerzenie względem doc-agents.
- **Robimy:** `scan.frameworks` w configu: dla każdego frameworku `technology` (do której technologii należy), `paths` (wzorce ścieżek, gdy skopiowany do projektu), `packages` (nazwy importowanych pakietów - działa także dla paczek w venv i instalowanych edytowalnie) i `knowledge` (plik wiedzy o frameworku, przekazywany agentom zawsze, gdy framework wykryto); oznaczanie plików `framework_name`; lista frameworków wykrytych po importach. **Nowy framework Pythona = nowy wpis w configu + plik wiedzy, bez zmian w kodzie.**
- **Sprawdzamy:** robot testowy z `roboforge: {packages: [roboforge]}` → Roboforge wykryty po importach, żaden plik robota nie jest oznaczony jako framework; dopisany w configu sztuczny framework z pakietem `selenium` → wykryty bez zmiany kodu.

**Krok 22. Przenieś z doc-agents: `scanner.py` - `build_project_map()`**
- **Funkcja:** kompletna mapa projektu w jednym obiekcie.
- **Robimy:** złożenie `ProjectMap`: technologia, punkty wejścia, pliki, jednostki kodu (pliki źródłowe spoza frameworku), frameworki.
- **Sprawdzamy:** JSON mapy robota testowego.

**Krok 23. `scanner.py` - pliki zależności (W2)**
- **Funkcja:** pełna lista zależności robota przepisana dosłownie, do skopiowania z zakładki Przegląd - bez udziału modelu, więc bez ryzyka przekłamania.
- **Robimy:** metoda technologii `dependency_files(project, files)` - dla Pythona wzorce z `scan.dependency_files` w configu (np. `requirements*.txt`, `pyproject.toml`); skaner tylko woła technologię i zapisuje wynik; odczyt przez `files.read_text_safe` (UTF-16!); treść w `ProjectMap.dependency_files` (ścieżka + tekst).
- **Sprawdzamy:** mapa robota zawiera czytelną treść `requirements.txt` z linią `-e git+...roboforge`.

**Krok 24. `scanner.py` - pliki konfiguracyjne: wpisy z typami i maskowaniem (W2, W8)**
- **Funkcja:** konfiguracja robota rozłożona na wpisy, z których kod składa metryczkę, a model opisuje uruchomienie i dostępy. **Hasło wpisane wprost w plik nigdy nie trafi do modelu ani do przewodnika.**
- **Robimy:** metody technologii `config_files()` (domyślnie: pliki o roli `config` bez plików zależności, do `scan.max_config_size_kb`) i `parse_config()` (domyślnie: wspólne parsery z `technologies/config_parsers.py` według rozszerzenia - YAML, JSON, TOML, INI/CFG; UiPath nadpisze to odczytem `Config.xlsx`, Robot Framework - sekcją Variables). Skaner tylko woła technologię. Schemat `ConfigEntry` w `schemas.py`: plik, klucz z pełną ścieżką (np. `parabank.url`; dla arkusza albo sekcji - `arkusz.nazwa`), wartość, komentarz z końca linii (jeśli parser go daje - YAML przez odczyt linii), `kind` wyliczany zwykłym kodem: `url` (http/https), `path` (separator albo rozszerzenie), `env_var` (klucz kończy się na `_env` albo wartość wygląda jak nazwa zmiennej i klucz to sugeruje), `flag` (bool), `number`, `account` (klucze typu `user`, `username`, `login`), `secret` (klucz pasuje do `scan.sensitive_keys` - wartość → `***`), `text`. Wynik w `ProjectMap.config_files` (plik + lista wpisów albo `parsed=false` z samymi metadanymi).
- **Sprawdzamy:** `config.yml` robota: `parabank.url` → `url`, `input.excel_path` → `path`, `parabank.password_env` → `env_var` z wartością `FAKE_PASSWD`, `logger.debug` → `flag`, `parabank.username` → `account`; w kopii robota dopisany `password: abc123` → `secret` z `***`; uszkodzony YAML → `parsed=false`, bez błędu przebiegu; robot 02 (bez pliku konfiguracyjnego) → pusta lista, bez błędu.

**Krok 25. `technologies/python.py` - gdzie używane są klucze konfiguracji (W8)**
- **Funkcja:** przy każdym kluczu metryczki widać, w którym pliku i linii kod go czyta - deweloper od razu wie, co zmiana wartości ruszy. Liczone przez kod, więc bez ryzyka zmyślenia.
- **Robimy:** metoda kontraktu `config_usages(path, keys)` (w `base.py` z opisem i domyślną odpowiedzią „brak danych”; w `python.py` przez `ast`): stałe tekstowe równe nazwie klucza w indeksowaniu (`cfg["excel_path"]`) i w wywołaniach `.get("excel_path")`; dodatkowo nazwy zmiennych środowiskowych czytanych w kodzie (`os.environ[...]`, `os.environ.get(...)`, `os.getenv(...)`) jako stałe tekstowe. Skaner dopisuje do każdego `ConfigEntry` listę `used_in` (`plik:linia`) i do `ProjectMap` listę zmiennych środowiskowych czytanych w kodzie z miejscami odczytu.
- **Sprawdzamy:** dla robota `input.excel_path` → `main.py:57`, `parabank.url` → `main.py:139`; zmienna odczytywana przez `os.environ.get(bank_cfg["password_env"])` - nazwy nie da się wyliczyć ze stałej, więc wpis `password_env` ma `used_in` = `main.py:135` (klucz), a lista zmiennych z kodu jej nie zawiera (bez zgadywania); klucz nieużywany w kodzie → pusta lista.

**Krok 26. `technologies/python.py` - ustawienia zaszyte w kodzie (W8)**
- **Funkcja:** metryczka nie jest pusta, gdy robot trzyma ustawienia w stałych zamiast w pliku konfiguracyjnym - deweloper widzi adresy, ścieżki i nazwy zmiennych środowiskowych z plikiem i linią.
- **Robimy:** `code_settings(path)` przez `ast`: przypisania na poziomie modułu (i atrybuty klas na poziomie klasy) do stałych tekstowych, liczbowych i logicznych; typ (`url`, `path`, `env_var`, `flag`, `number`, `secret`...) wyliczany **tą samą funkcją co w kroku 24**; nazwy zmiennych środowiskowych ze stałych w `os.environ`/`os.getenv` z kroku 25; wynik jako `ConfigEntry` ze źródłem `code` (plik, linia, nazwa stałej). Hasło wpisane w stałą → `secret` z `***`. Stałe bez związku z ustawieniami (np. krotki komunikatów) odfiltrowane prostą regułą: zostają tylko wpisy o typie innym niż `text` albo o nazwie pisanej WIELKIMI_LITERAMI.
- **Sprawdzamy:** robot 02: `URL` → `url`, `INPUT_DIR` → `path`, `ENV_PASSWORD` → `env_var` (`ROBOT02_PASS`), każdy z plikiem i linią; dopisana w kopii stała `PASSWORD = "abc"` → `secret` z `***`; robot 01 → stałe ścieżek z `main.py` (np. `CONFIG_FILE`) jako `path`.

**Krok 27. `output.py` - wyniki w `dev_agents_doc/` analizowanego projektu**
- **Funkcja:** bezpieczny zapis wyników w cudzym repozytorium: dokumentacja leży obok kodu, a narzędzie nigdy nie skasuje cudzych plików.
- **Robimy:** `RunStore` tworzący `<projekt>/dev_agents_doc/` ze znacznikiem `.dev_agents_output`; czyszczenie przy starcie tylko katalogu ze znacznikiem (bez znacznika → błąd, nic nie kasujemy); sprawdzenie prawa zapisu na początku; `save_text`, `save_json`, `load_json`, podkatalogi (`notes/`, `tabs/`).
- **Sprawdzamy:** na kopii robota: zapis i odczyt JSON; drugi start czyści katalog; katalog bez znacznika → błąd i nic nie usunięte; katalog tylko do odczytu → czytelny błąd.

**Krok 28. `dependencies.py` - graf zależności i kolejność czytania**
- **Funkcja:** dane do grafu zależności między modułami i szkic kolejności czytania kodu, z importów, bez modelu.
- **Robimy:** schemat `DependencyGraph` (węzły = moduły projektu, punkt wejścia oznaczony; krawędzie = importy wewnętrzne) w `schemas.py`; kolejność czytania: od punktu wejścia w głąb, cykle bez zawieszenia.
- **Sprawdzamy:** graf robota (`main.py` → moduły `src/`) i lista kolejności; sztuczny cykl dwóch modułów nie zawiesza obliczeń.

**Krok 29. `main.py` - skan i zapis wyników**
- **Funkcja:** pierwszy użyteczny przebieg: mapa projektu i graf zależności w katalogu wyników robota.
- **Robimy:** `--project` wymagany; config → skan → graf zależności → `dev_agents_doc/project_map.json` i `dependency_graph.json`.
- **Sprawdzamy:** `python main.py --project <robot>` tworzy oba pliki w `<robot>\dev_agents_doc\` - dla robota 01 i 02; w mapie robota 02 widać punkt wejścia z `run.bat`, ustawienia ze stałych i długą funkcję z miarami. ✅ **M3**

### Faza D - Szablon przewodnika i HTML bez modelu

**Krok 30. `guide_template.yaml` + `guide_template.py`**
- **Funkcja:** struktura przewodnika (zakładki i sekcje) opisana poza kodem, żeby zespół mógł ją zmieniać bez programowania.
- **Robimy:** `knowledge_base/templates/guide_template.yaml` odwzorowujący makietę: 7 zakładek (Przegląd i uruchomienie - na górze metryczka typu `config`, Przepływ działania, Ścieżki procesu, Struktura projektu, Zmiany i rozszerzenia, Błędy i naprawa - z sekcją „Ryzykowne miejsca” typu `table` ze źródłem `code`, Dla dewelopera), przy każdej opis do kart „jak czytać”; dla sekcji: `id`, `title`, `type` z zamkniętej listy (`text`, `list`, `steps`, `code`, `table`, `glossary`, `io`, `cards`, `config`, `tree`, `dependency_graph`, `flow`, `paths`, `recipes`), `source` (`llm`/`scanner`/`code`), `required` (sekcja zawsze widoczna; gdy z kodu nic nie wynika, pokazuje „nie wynika z kodu”, nigdy wymyśloną treść), `instruction`, przy `table` kolumny, opcjonalnie `technologies` (lista technologii, dla których sekcja się pojawia, np. „venv i pip” tylko dla `python`; brak pola = wszystkie); `guide_template.py`: wczytanie, sprawdzenie zwykłym kodem i wybór sekcji dla technologii projektu.
- **Sprawdzamy:** wydruk zakładek i sekcji dla `python` i dla `uipath` (sekcje z filtrem znikają); nieznany typ, zdublowane `id` albo nieznana technologia w filtrze → czytelny błąd.

**Krok 31. `schemas.py` - treść przewodnika i diagram**
- **Funkcja:** ogólny kształt treści, niezależny od konkretnych sekcji, oraz osobny, ścisły schemat diagramu przepływu.
- **Robimy:** `FlowNode` (`id`, `kind`: `start`/`end`/`step`/`system`/`decision`, `label` - krótki opis biznesowo-techniczny, `description`, `module`, `functions`, `reads`, `writes`, `certain`), `FlowEdge` (`from`, `to`, `label`, `kind`: `normal`/`branch`/`loop`), `FlowGraph`; `GuideBlock` (`section_id` + pola zależne od typu: `paragraphs`, `items`, `steps`, `rows`, `terms`, `paths`, `recipes`, `code`, `config_meanings` - znaczenie klucza konfiguracji: klucz → jedno zdanie), `GuideTab`, `GuideContent`; `Field(description=...)` dla modelu.
- **Sprawdzamy:** przykładowa treść i diagram (dane z makiety) złożone ręcznie, wydruk JSON i zgodność po odczycie.

**Krok 32. `flow.py` - spójność i układ diagramu (W1)**
- **Funkcja:** gwarancja, że diagram jest poprawnym grafem, oraz układ liczony przez kod, nie przez model.
- **Robimy:** `validate_flow()` zwracająca listę problemów i ostrzeżeń (ostrzeżenie: więcej niż `flow.max_nodes` klocków albo decyzja w decyzji głębiej niż 2 poziomy - znak, że szczegóły techniczne powinny zejść do wierszy „krok po kroku”; dokładnie jeden start, co najmniej jeden koniec, każdy klocek osiągalny ze startu, z każdego klocka poza końcem wychodzi krawędź, decyzja ma co najmniej dwa wyjścia z etykietami, krawędzie wskazują istniejące klocki, `step`/`system` mają moduł); `layout_flow()` → wiersz i kolumna każdego klocka (główna ścieżka w pionie, gałęzie decyzji z boku, pętle jako krawędzie powrotne).
- **Sprawdzamy:** diagram z makiety: zero problemów i układ jak w makiecie; zepsuty diagram (klocek bez wyjścia, krawędź do nieistniejącego klocka) → czytelna lista problemów.

**Krok 33. `render.py` - szkielet HTML, zakładki, „jak czytać” (W5)**
- **Funkcja:** zamiana treści na samowystarczalny HTML w stylu makiety; pierwszy widoczny efekt.
- **Robimy:** `pip install jinja2` (+ `requirements.txt`); `guide.html.j2`, `guide.css`, `guide.js` przeniesione z makiety (router zakładek, podpowiedzi, kopiowanie); CSS i JS wstawiane do pliku; bloki `text`, `list`, `io`; blok `cards` („Jak czytać ten przewodnik”) generowany z opisów zakładek w `guide_template.yaml`; test zapisuje HTML z przykładową treścią do katalogu tymczasowego.
- **Sprawdzamy:** HTML otwiera się bez internetu, zakładki się przełączają, karty prowadzą do zakładek, polskie znaki poprawne, wygląd zgodny z makietą.

**Krok 34. `render.py` - bloki `steps`, `code`, `table`, `glossary`, `paths`, `recipes` (W2, W4, W6, W7)**
- **Funkcja:** pozostałe bloki tekstowe: instalacja krok po kroku z kodem do skopiowania, tabele wymagań i błędów, słowniczek, ścieżki procesu z odwołaniami do klocków, przepisy zmian.
- **Robimy:** szablony bloków; kolumny tabel z `guide_template.yaml`; odwołania `paths` do numerów klocków diagramu (link do zakładki Przepływ); oznaczenie „wywnioskowane” dla wpisów z `certain = false`.
- **Sprawdzamy:** przykładowa treść z każdym typem bloku wyświetla się jak w makiecie; tekst z `<script>` wyświetlany jako tekst (escapowanie); przycisk „Kopiuj” kopiuje blok kodu.

**Krok 35. `render.py` - bloki ze skanera: metryczka, drzewo i zależności do skopiowania (W2, W8)**
- **Funkcja:** fakty o projekcie wstawiane przez kod: metryczka z pliku konfiguracyjnego, drzewo plików z rolami i dosłowna treść plików zależności.
- **Robimy:** blok `config` (metryczka jak w makiecie): nagłówek z plikiem i miejscem wczytania w kodzie, kafelki pogrupowane po `kind` (systemy zewnętrzne, pliki wejściowe i wyjściowe, logi, konta i zmienne środowiskowe, przełączniki), pod spodem tabela wszystkich wpisów pogrupowana po sekcjach (klucz, wartość, znaczenie, używany w); `secret` jako `***` z czerwonym znacznikiem, `env_var` ze znacznikiem „zmienna środowiskowa”; znaczenie na razie zaślepka (wypełnia pisarz w kroku 55); brak pliku konfiguracyjnego → jedno zdanie; kilka plików → osobna tabela na plik. Blok `tree` z `ProjectMap` (oznaczenia ról, sekrety „tylko metadane”, opisy po najechaniu - na razie zaślepki, treść z modelu w fazie F); blok `code` ze `scanner` dla plików zależności; tabela „Ryzykowne miejsca” z miar złożoności (funkcja, plik:linie, długość, zagnieżdżenie, rozgałęzienia; próg z `analysis.complexity`); w metryczce ustawienia ze stałych w kodzie ze znacznikiem „w kodzie”.
- **Sprawdzamy:** robot 02: metryczka ze stałych, „Ryzykowne miejsca” z funkcją spaghetti; robot 01: metryczka, drzewo i `requirements.txt` robota testowego z prawdziwej `project_map.json` z kroku 29; kopia robota bez `config.yml` → zdanie o braku konfiguracji zamiast pustej tabeli.

**Krok 36. Diagram przepływu w HTML (W1, W3)**
- **Funkcja:** czytelny diagram całego procesu: start, klocki, strzałki, decyzje, pętle - z podpowiedzią po najechaniu (moduł, funkcje, czyta, zapisuje).
- **Robimy:** blok `flow`: dane `FlowGraph` + układ z `flow.py` wstawione do HTML jako JSON; rysowanie SVG w `guide.js` jak w makiecie (kształty wg `kind`, numery klocków, etykiety „tak/nie”, czerwone przerywane powroty pętli, zawijanie długich napisów, widok na telefonie).
- **Sprawdzamy:** diagram z makiety i diagram 25+ klocków (sztuczny) są czytelne na laptopie i w wąskim oknie; podpowiedź pokazuje dane klocka.

**Krok 37. Przepływ krok po kroku pod diagramem (W3)**
- **Funkcja:** dla każdego klocka wiersz „czyta - co się dzieje - zapisuje”, z tych samych danych co diagram, więc nie mogą się rozjechać.
- **Robimy:** wiersze generowane z `FlowGraph` (moduł, funkcje w kolejności, wejścia i wyjścia jako oznaczone „kafelki”: plik, zmienna, system, dane w pamięci); wyjścia decyzji; strzałki z powrotem pętli; kliknięcie klocka przewija do wiersza i go wyróżnia.
- **Sprawdzamy:** kliknięcie klocka 9 w diagramie przewija do wiersza kroku 9; liczba wierszy = liczba klocków.

**Krok 38. Graf zależności modułów i podpowiedzi słowniczka**
- **Funkcja:** rysunek, który moduł importuje który, oraz definicje pojęć po najechaniu na nie w tekście.
- **Robimy:** blok `dependency_graph` z `dependency_graph.json` (warstwy od punktu wejścia, jak w makiecie); oznaczanie wystąpień terminów słowniczka w tekście (bezpiecznie, po escapowaniu) i dymek z definicją.
- **Sprawdzamy:** graf robota testowego czytelny; termin pokazuje dymek; termin wewnątrz innego słowa nie jest oznaczany.

**Krok 39. Przewodnik z prawdziwego robota, sekcje modelu jako zaślepki**
- **Funkcja:** zatwierdzenie wyglądu i układu na prawdziwych danych, zanim wydamy pierwszy token na treść.
- **Robimy:** `main.py --render-only`: skan → sekcje `scanner` i `code` wypełnione, sekcje `llm` z zaślepką, diagram z danych przykładowych → `dev_agents_doc/guide.html`.
- **Sprawdzamy:** przewodniki robotów 01 i 02 otwierają się offline; metryczka, drzewo, zależności do skopiowania, graf zależności i karty „jak czytać” prawdziwe; uwagi do wyglądu poprawione przed fazą E. ✅ **M4**

### Faza E - Prompty i baza wiedzy

**Krok 40. Przenieś z doc-agents: `prompts.py`**
- **Funkcja:** prompty poza kodem - zmiana polecenia dla agenta bez programowania.
- **Robimy:** `render_prompt(prompts_dir, agent, variables)` → `(system, user)`, Jinja2 ze `StrictUndefined`.
- **Sprawdzamy:** wyrenderowanie przykładowego promptu; brak zmiennej → błąd.

**Krok 41. Przenieś z doc-agents: `knowledge.py`**
- **Funkcja:** spis bazy wiedzy, z którego planner wybiera pliki, i bezpieczny odczyt tylko wewnątrz bazy.
- **Robimy:** parser `index.md` (plik, „Kiedy użyć:”, „Tagi:”), `read_kb_file` z blokadą ścieżek spoza bazy.
- **Sprawdzamy:** wydruk wpisów; próba odczytu `..\config.yaml` → odrzucona.

**Krok 42. Treść bazy wiedzy**
- **Funkcja:** wiedza, której nie ma w kodzie: dla kogo piszemy przewodnik, poziom szczegółów diagramu, konwencje zespołu, cykl życia frameworku.
- **Robimy:** `guide_goals.md` (nowy: odbiorca, ton, **zasady diagramu** - jeden klocek na czynność widoczną dla biznesu, każdy kontakt z systemem zewnętrznym jako osobny klocek, pętle i decyzje jawnie, nazwy klocków czasownikiem, **na diagramie tylko decyzje widoczne dla biznesu - warunki techniczne i zagnieżdżone schodzą do opisu kroku**, limit ok. 30 klocków; oznaczanie informacji wywnioskowanych); `technologies/python.md` (z `python_conventions.md` z doc-agents) i `frameworks/roboforge.md` (z `rpa_framework.md` z doc-agents, z cyklem życia Roboforge) - po jednym pliku na technologię i framework, żeby dodanie kolejnych było dopisaniem pliku; pliki technologii i wykrytych frameworków trafiają do agentów zawsze, niezależnie od wyboru plannera; `index.md`.
- **Sprawdzamy:** `python -m dev_agents.knowledge` wypisuje wszystkie wpisy indeksu.

### Faza F - Graf i agenci

**Krok 43. Pierwszy graf: tylko skan**
- **Funkcja:** szkielet przepływu LangGraph, do którego kolejno dołączamy agentów.
- **Robimy:** `pip install langgraph` (+ `requirements.txt`); `context.py` (`RunContext`: config, `RunStore`, modele agentów, spis bazy wiedzy, szablon przewodnika); `state.py` (ścieżka projektu, mapa, graf zależności); `graph.py`: `START → scan → END`.
- **Sprawdzamy:** `python -m dev_agents.graph` wypisuje stan końcowy z mapą projektu.
- **Uczymy się:** `StateGraph`, węzeł jako funkcja, częściowa aktualizacja stanu, `Runtime[RunContext]`.

**Krok 44. `main.py` uruchamia graf**
- **Funkcja:** jeden sposób uruchamiania narzędzia - przez graf.
- **Robimy:** zamiana bezpośredniego skanu na wywołanie grafu (zostaje `--render-only`).
- **Sprawdzamy:** wynik taki sam jak w kroku 29.

**Krok 45. Podgląd postępu**
- **Funkcja:** na ekranie widać, który etap trwa i ile trwał - kilkuminutowy przebieg nie wygląda jak zawieszenie.
- **Robimy:** `run_graph` przez `stream(..., stream_mode=["tasks", "values"])`; linie postępu z godziną, nazwą etapu, czasem i krótkim wynikiem; błąd węzła widoczny od razu.
- **Sprawdzamy:** przebieg skanu wypisuje start i koniec węzła `scan` z czasem.

**Krok 46. `schemas.py` - plan**
- **Funkcja:** wynik pracy plannera: co analizować i jaką wiedzę dać agentom.
- **Robimy:** `AnalysisTask` (jednostka kodu, wskazówka), `Plan` (podsumowanie, zadania, pliki wiedzy dla analityków, autora diagramu i pisarzy, wybrane sekcje opcjonalne); `Field(description=...)`.
- **Sprawdzamy:** ręcznie złożony plan, wydruk JSON.

**Krok 47. Agent planner (bez grafu)**
- **Funkcja:** decyzja, które jednostki kodu analizować i które pliki wiedzy są potrzebne.
- **Robimy:** `agents/planner.py` (czysta funkcja `plan()` + węzeł), prompty `planner/*`.
- **Sprawdzamy:** `python -m dev_agents.agents.planner` czyta `project_map.json` z `dev_agents_doc/` robota i wypisuje plan.

**Krok 48. Graf: scan → planner**
- **Funkcja:** planner jako etap przepływu.
- **Robimy:** węzeł planner w grafie, zapis `plan.json`.
- **Sprawdzamy:** przebieg tworzy `plan.json`; podgląd postępu pokazuje liczbę zadań.

**Krok 49. `schemas.py` - notatka analityka (W1-W7)**
- **Funkcja:** ustrukturyzowana wiedza o jednej jednostce kodu - surowiec dla wszystkich zakładek.
- **Robimy:** `ModuleNote` przeniesiony z doc-agents (przeznaczenie, automatyzowana aplikacja, kroki procesu, obsługa błędów, wejścia/wyjścia, konfiguracja, zależności, pułapki, wskazówki) i rozszerzony o: **czynności z odwołaniem do funkcji, z danymi czytanymi i zapisywanymi** (surowiec diagramu), **rolę w przepływie** (np. metoda wołana przez framework), **dostęp sieciowy** (adresy, porty, systemy), **wymagania uruchomieniowe** (aplikacje, sterowniki, konta, nazwy zmiennych), **punkty rozszerzeń**, **możliwe błędy z objawem i naprawą**, **konwencje**, **kandydatów do słowniczka**; przy wnioskach flaga pewności. Wszystkie listy mogą być puste, a pola tekstowe przyjmują „nie wynika z kodu” - schemat nie zmusza modelu do wymyślania. Dodatkowo `part`/`parts` dla notatek z kawałków długiej funkcji (krok 51).
- **Sprawdzamy:** ręcznie złożona notatka, wydruk JSON; notatka z pustymi punktami rozszerzeń przechodzi walidację.

**Krok 50. Agent analityk (bez grafu)**
- **Funkcja:** zrozumienie jednej jednostki kodu: kod jednostki + szkielety całego projektu + zamaskowana konfiguracja + wybrana wiedza → notatka.
- **Robimy:** `agents/analyst.py` przeniesiony z doc-agents i dostosowany do nowej notatki; analityk dostaje też **szkielet sterowania i miary** swojej jednostki; limit `analysis.max_file_size_kb` (większy plik - szkielet plus analiza po kawałkach z kroku 51); prompty `analyst/*`.
- **Sprawdzamy:** notatka dla `main.py` robota: cykl życia Roboforge jako przepływ wołany przez framework, adresy stron w dostępie sieciowym, sensowne punkty rozszerzeń i błędy, niepewność oznaczona.

**Krok 51. Analityk: długie funkcje po kawałkach**
- **Funkcja:** funkcja na setki linii jest przeczytana w całości, w porcjach, zamiast zastąpiona szkieletem - opis robota „spaghetti” opiera się na kodzie, nie na domysłach.
- **Robimy:** w `agents/analyst.py`: funkcja dłuższa niż `analysis.complexity.long_function_lines` dzielona zwykłym kodem na kawałki wzdłuż szkieletu sterowania (granice na blokach najwyższego poziomu, rozmiar do `analysis.chunk_lines`; za długi blok dzielony na jego podblokach); kawałki analizowane **po kolei**, każdy z: szkieletem sterowania całej funkcji (gdzie jest), krótkim podsumowaniem poprzednich kawałków i swoim kodem; notatki kawałków (`part`/`parts`) składane zwykłym kodem w jedną notatkę o jednostce (czynności w kolejności linii, błędy, wejścia i wyjścia bez duplikatów). Podgląd postępu pokazuje „kawałek 3/7”.
- **Sprawdzamy:** robot 02: `run()` analizowana w kilku kawałkach; złożona notatka zawiera czynności ze wszystkich gałęzi szkieletu sterowania (porównanie ręczne: każda gałąź najwyższego poziomu ma odpowiednik w notatce); krótkie funkcje robota 01 analizowane jak dotąd, jednym wywołaniem.

**Krok 52. Graf: równolegli analitycy**
- **Funkcja:** analiza wszystkich jednostek naraz.
- **Robimy:** `Send` na każde zadanie z planu, reducer listy notatek w stanie, `analysis.max_concurrency` w configu, zapis `notes/*.json`.
- **Sprawdzamy:** liczba notatek = liczba zadań; podgląd postępu pokazuje analityków z czasami.
- **Uczymy się:** `Send`, reducery, równoległe węzły.

**Krok 53. Agent autor diagramu (bez grafu) (W1)**
- **Funkcja:** diagram całego procesu od startu do końca, z notatek wszystkich analityków - kręgosłup przewodnika.
- **Robimy:** `agents/flow_writer.py` (czysta funkcja `write_flow()` + węzeł); odpowiedź jako `FlowGraph`; po odpowiedzi `flow.validate_flow()` - przy problemach albo ostrzeżeniu o rozmiarze jedno ponowne wywołanie z listą problemów w prompcie; prompty `flow_writer/*` z zasadami diagramu z `guide_goals.md`.
- **Sprawdzamy:** diagramy robotów 01 i 02 z notatek z `dev_agents_doc/notes/` (bez ponownej analizy): spójne według `validate_flow`, diagram robota 02 mieści się w limicie mimo funkcji spaghetti, podgląd HTML zakładki Przepływ; z samego diagramu da się opowiedzieć proces (ocena użytkownika).

**Krok 54. Graf: autor diagramu po analitykach**
- **Funkcja:** diagram jako etap przepływu, zanim powstaną pozostałe zakładki.
- **Robimy:** węzeł `flow` po analitykach, zapis `flow.json`, diagram w stanie.
- **Sprawdzamy:** przebieg tworzy `flow.json`; podgląd postępu pokazuje liczbę klocków i wynik sprawdzenia spójności.

**Krok 55. Agent pisarz zakładki (bez grafu) (W2, W4, W6, W7)**
- **Funkcja:** treść jednej zakładki: sekcje z `guide_template.yaml`, napisane z notatek, mapy projektu, zamaskowanej konfiguracji i **gotowego diagramu** (ścieżki, błędy i przepisy odwołują się do numerów klocków).
- **Robimy:** `agents/writer.py` (czysta funkcja `write_tab()` + węzeł); odpowiedź jako `GuideTab`; sekcje `scanner`/`code` wypełnia kod, model tylko sekcje `llm`; pisarz zakładki Przegląd dostaje listę kluczy metryczki (bez wartości `secret`) i zwraca `config_meanings` - po jednym zdaniu na klucz, z oznaczeniem „wywnioskowane”, gdy znaczenie nie wynika wprost z kodu lub komentarza; prompty `writer/*`.
- **Sprawdzamy:** zakładki „Przegląd i uruchomienie” i „Ścieżki procesu” z istniejących notatek i `flow.json` - wydruk JSON i podgląd HTML; ścieżki odwołują się do istniejących klocków; każdy klucz metryczki ma znaczenie.

**Krok 56. Graf: równolegli pisarze + składanie treści**
- **Funkcja:** wszystkie pozostałe zakładki pisane naraz, potem złożone w jedną treść ze sprawdzeniem kompletności.
- **Robimy:** drugi `Send` (po jednym pisarzu na zakładkę poza Przepływem), zapis `tabs/<zakładka>.json`; węzeł `assemble` (kod): `GuideContent` z diagramem i blokami skanera, braki wymaganych sekcji, odwołania do nieistniejących klocków, klucze metryczki bez znaczenia, `guide_content.json`.
- **Sprawdzamy:** wszystkie zakładki w `tabs/`, `guide_content.json` kompletny, braki (jeśli są) wypisane.

**Krok 57. Graf: render i finalize**
- **Funkcja:** gotowy przewodnik HTML na końcu przebiegu.
- **Robimy:** węzeł `finalize`: render `guide_content.json` → `dev_agents_doc/guide.html`.
- **Sprawdzamy:** pełne przebiegi na robotach 01 i 02 tworzą `guide.html` z treścią we wszystkich zakładkach; w robocie 02 przepływ funkcji spaghetti opisany kawałek po kawałku, bez zgadywania.

**Krok 58. Agent recenzent (bez grafu)**
- **Funkcja:** kontrola jakości: braki i spójność sprawdza kod, prawdziwość i konkretność ocenia model.
- **Robimy:** `ReviewResult` (`approved`, `issues` z identyfikatorem zakładki lub `flow`, `suggestions`); `agents/reviewer.py`; prompt: `issues` = zdanie niepoparte notatkami, sprzeczność, brak kroku lub ścieżki, **diagram zbyt ogólny** (czynność widoczna w notatkach bez klocka), ogólnik zamiast wskazówki, sekret, **treść wymyślona tam, gdzie notatki mówią „nie wynika z kodu”**, diagram przeładowany szczegółami technicznymi; `suggestions` = powtórzenia, sformułowania, styl. **Puste pole albo „nie wynika z kodu” nie jest uwagą.**
- **Sprawdzamy:** recenzja `guide_content.json` z poprzedniego przebiegu, wydruk uwag z przypisaniem do zakładek.

**Krok 59. Graf: pętla recenzji tylko dla części z uwagami**
- **Funkcja:** poprawki celowane: przepisywany jest diagram lub tylko zakładki, których dotyczą uwagi.
- **Robimy:** krawędź warunkowa po recenzencie; `Send` do autora diagramu i/lub pisarzy zakładek z uwagami (dostają poprzednią wersję i uwagi); po zmianie diagramu przepisywane są też zakładki odwołujące się do klocków; `limits.max_review_rounds`; historia `review_NN.json`.
- **Sprawdzamy:** przy limicie 2 widać jedną rundę poprawek, przepisane tylko części z uwagami, końcowy `guide.html`; ręczna weryfikacja kilku stwierdzeń z kodem i ocena diagramów obu robotów przez użytkownika. ✅ **M5**
- **Uczymy się:** krawędzie warunkowe, cykl w grafie, `Send` z krawędzi warunkowej.

### Faza G - Ergonomia

**Krok 60. Opisy w drzewie projektu**
- **Funkcja:** podpowiedzi „czym jest / rola” przy plikach drzewa wypełnione treścią, nie zaślepkami.
- **Robimy:** opisy jednostek kodu z notatek analityków (przeznaczenie), opisy plików niebędących kodem z roli i notatek (np. kto używa `config.yml`); bez nowych wywołań modelu.
- **Sprawdzamy:** najechanie na `src/report.py` i `config.yml` w przewodniku robota pokazuje sensowny opis.

**Krok 61. Licznik kosztów**
- **Funkcja:** koszt i zużycie tokenów każdego przebiegu, per agent - przed dokumentowaniem wielu robotów.
- **Robimy:** callback zliczający tokeny, sekcja `pricing` w configu, `usage.json` i podsumowanie na końcu przebiegu.
- **Sprawdzamy:** koszt przebiegu zgadza się z grubsza z Claude Console.

**Krok 62. Przebieg kontrolny na drugim projekcie**
- **Funkcja:** sprawdzenie na prawdziwym projekcie, większym i mniej uporządkowanym niż roboty testowe (najlepiej taki, który zespół uważa za trudny w utrzymaniu).
- **Robimy:** pełny przebieg; obserwacje (jakość diagramu, czas, koszt, limity kontekstu) w `dev_log/raport_wykonania.md`. Poprawki zgłaszamy jako nowe kroki planu.
- **Sprawdzamy:** przewodnik powstaje; lista obserwacji i proponowanych kroków w raporcie.

**Krok 63. README**
- **Funkcja:** instrukcja dla kolejnego dewelopera: instalacja, uruchomienie, przełączenie na miasto, co jest w `dev_agents_doc/`, **jak dodać technologię i framework**.
- **Robimy:** `README.md` z rozdziałami „Dodanie frameworku Pythona” (wpis w `scan.frameworks` + plik w `knowledge/frameworks/`) i „Dodanie technologii” (klasa w `technologies/`, rejestracja, plik w `knowledge/technologies/`, ewentualne sekcje szablonu z filtrem `technologies`, test na przykładowym projekcie).
- **Sprawdzamy:** wykonanie instrukcji od zera na świeżym klonie (na Kwadracie) kończy się działającym przebiegiem.

### Faza H - Miasto

**Krok 64. Klon i środowisko na mieście**
- **Funkcja:** narzędzie zainstalowane w środowisku firmowym.
- **Robimy:** `git clone`, `py -V:3.14 -m venv venv`, `pip install -r requirements.txt`.
- **Sprawdzamy:** `python main.py --help`.

**Krok 65. Konfiguracja miejska**
- **Funkcja:** przełączenie na firmową bramkę bez zmian w kodzie.
- **Robimy:** zmienne użytkownika `BAZOOKA_KEY`, `BAZOOKA_URL`; w `config.yaml` zakomentowanie linii z Kwadratu i odkomentowanie miejskich.
- **Sprawdzamy:** `python -m dev_agents.config` pokazuje miejskie nazwy zmiennych i modeli; `python -m dev_agents.llm` zwraca odpowiedź firmowego modelu.

**Krok 66. `probe_llm` na mieście**
- **Funkcja:** sprawdzenie, czy firmowa bramka obsługuje `json_schema`.
- **Robimy:** `python -m scripts.probe_llm --profile small` i `--profile medium`; jeśli `json_schema` nie działa - metoda z rekomendacji w profilu.
- **Sprawdzamy:** diagnoza zapisana w raporcie, config zgodny z rekomendacją.

**Krok 67. Przebieg `--render-only` na mieście**
- **Funkcja:** sprawdzenie skanu, zapisu w `dev_agents_doc/` i otwierania HTML w firmowym środowisku, zanim pójdą wywołania modelu.
- **Robimy:** `python main.py --project <robot> --render-only`.
- **Sprawdzamy:** `guide.html` otwiera się w firmowej przeglądarce bez internetu; drzewo i zależności poprawne.

**Krok 68. Pełny przebieg na mieście**
- **Funkcja:** przewodnik dla prawdziwego robota z pracy.
- **Robimy:** `python main.py --project <robot>`.
- **Sprawdzamy:** `guide.html` w `<robot>\dev_agents_doc\`, diagram pozwala opowiedzieć proces, treść zweryfikowana wyrywkowo. ✅ **M6**

### Faza I - Później (poza MVP)

- Implementacje technologii na podstawie kontraktu z `technologies/base.py`: UiPath (kolega), Robot Framework, NICE APA - każda jako osobna seria kroków według rozdziału „Dodanie technologii” z README.
- Kolejne frameworki Pythona: wpisy w `scan.frameworks` i pliki wiedzy.
- Opcjonalnie: odczyt kodu frameworku z venv (`site-packages` albo ścieżka instalacji edytowalnej) dla funkcji wołanych przez robota, gdy plik wiedzy nie wystarcza.
- Wznawianie przerwanego przebiegu (checkpointer) i log do pliku.
- Testy automatyczne (pytest) dla skanera, `flow.py` i renderera; `ruff` z `target-version = "py314"`.
- Eksport przewodnika do Markdown (ten sam `GuideContent`, drugi szablon).
- Batch API przy dokumentowaniu wielu projektów naraz.
