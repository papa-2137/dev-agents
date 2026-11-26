# Dev-Agents: kroki planu

Część planu z krokami. Wymagania (W1-W8), ustalenia, docelowa struktura, zasady wykonania, szkic `config.yaml` i otwarte sprawy: **`dev_log/plan.md`** - przeczytaj przed pierwszym krokiem. Postęp i notatki: `dev_log/raport_wykonania.md`.

Każdy krok: **Funkcja** (co i po co), **Robimy**, **Sprawdzamy**. Roboty testowe: **01** = `tests\01_rpa_challange_roboforge`, **02** = `tests\02_robot_bez_frameworku` (powstaje w kroku 9).

---

Kamienie milowe: **M1** szkielet uruchamia się (krok 5) · **M2** model gotowy (krok 8) · **M3** mapa projektu, konfiguracja i pliki uruchamiające jako tekst oraz graf zależności bez modelu (krok 29) · **M4** wygląd przewodnika zatwierdzony na danych bez modelu (krok 39) · **M5** pierwszy pełny przewodnik z modelu (krok 59) · **M6** działa na mieście (krok 68).

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
- **Robimy:** `read_text_safe(path)`: rozpoznanie BOM (UTF-8, UTF-16 LE/BE); bez BOM najpierw ścisły UTF-8, potem cp1250 (starsze pliki z polskiego Windows, zwłaszcza `.bat` i `.ini`), na końcu UTF-8 z `errors="replace"` - zły bajt nigdy nie przerywa odczytu; końce linii ujednolicone do `\n`.
- **Sprawdzamy:** odczyt `requirements.txt` robota testowego (UTF-16) daje czytelny tekst; zwykły plik `.py` bez zmian; pliki tymczasowe w cp1250, UTF-16 BE i UTF-8 z BOM i bez - czytelne polskie znaki.

**Krok 11. Przenieś z doc-agents: `schemas.py` - mapa projektu**
- **Funkcja:** wspólny opis danych o projekcie, przekazywany między skanerem, agentami i rendererem.
- **Robimy:** `FileEntry` (ścieżka, rola, rozmiar, `framework_name`), `CodeUnit`, `ProjectMap` (nazwa, katalog, technologia, punkty wejścia, pliki, jednostki kodu, frameworki wykryte po importach). Pola plików zależności i plików konfiguracyjnych dochodzą razem ze swoimi klasami w krokach 23-24.
- **Sprawdzamy:** test składa mapę ręcznie, wypisuje JSON i sprawdza zgodność po odczycie z JSON.

**Krok 12. Przenieś z doc-agents: `technologies/base.py`**
- **Funkcja:** kontrakt technologii - rdzeń nie zna żadnego języka, pyta technologię tylko o proste, pewne fakty; rozumienie kodu należy do agentów.
- **Robimy:** klasa `Technology` z docstringiem-kontraktem. Metody **wymagane** (w klasie bazowej `NotImplementedError`): `name`, `detect`, `is_source`, `find_entrypoints`. Metody **opcjonalne** (w klasie bazowej odpowiedź „brak danych”): `units` (jednostki pliku z zakresami linii, krok 13) i `references` (pliki projektu i pakiety, krok 14); później `knowledge_file` (krok 42). **Zasada: każda metoda mieści się w ok. 40 liniach prostego kodu, bez drzewa warunków** - jeśli się nie da, ta wiedza należy do agenta. Pusty `technologies/__init__.py`. Klasa demonstracyjna w bloku testowym implementuje tylko metody wymagane.
- **Sprawdzamy:** test wypisuje wyniki klasy demonstracyjnej (metody opcjonalne - „brak danych”) i `NotImplementedError` klasy bazowej.

**Krok 13. `technologies/python.py` - parsowanie i jednostki kodu**
- **Funkcja:** pewne numery linii funkcji i metod - analityk, przewodnik i podział długich plików nie zgadują, gdzie jest kod.
- **Robimy:** `_parse_python(root, path)` - odczyt przez `files.read_text_safe`, parsowanie przez `ast` z wyciszonym `SyntaxWarning` (Python 3.12+ ostrzega przy każdym napisie typu `"C:\folder"` bez `r` - na mieście zasypywało to ekran), błąd składni → „brak danych”; `units()` - funkcje i metody (`Klasa.metoda`) z zakresami linii; schemat `SourceUnit` (`name`, `start_line`, `end_line`) w `schemas.py`.
- **Sprawdzamy:** jednostki `main.py` robota 01 i `przetwarzanie.py` robota 02 (`run` - linie 41-411); plik ze ścieżką Windows w zwykłym napisie bez ostrzeżeń; plik z błędem składni → brak danych.

**Krok 14. `technologies/python.py` - odwołania do plików i pakietów**
- **Funkcja:** powiązania między plikami projektu (źródło grafu zależności i kolejności czytania) i pakiety spoza projektu (źródło wykrywania frameworków).
- **Robimy:** `references()` - importy z całego pliku (także w funkcjach i `try`), importy względne zamienione na pełne nazwy; `files` jako **ścieżki względne plików projektu** (`src.report` → `src/report.py`), `packages` jako nazwy główne pakietów spoza projektu bez biblioteki standardowej (`sys.stdlib_module_names`); schemat `References` w `schemas.py`. Podział pakietów na „do zainstalowania” i inne oraz ich opis robią agenci.
- **Sprawdzamy:** `main.py` robota 01 → 6 plików `src/*.py`, pakiet `roboforge`; robot 02 → pakiet `requests`; pakiet tymczasowy - import względny i import w funkcji.

**Krok 15. (wycofany 2026-11-26) Szkielet sterowania i miary złożoności**
- **Funkcja:** przejęta przez agentów - analityk czyta pełny kod z numerami linii; do „Ryzykownych miejsc” i podziału długich plików wystarcza długość jednostek z `units()` (krok 13). Kod z tego kroku usunięty przy uproszczeniu analizy deterministycznej (tabela decyzji w raporcie).

**Krok 16. Przenieś z doc-agents: `technologies/python.py` - wykrywanie i punkty wejścia**
- **Funkcja:** rozpoznanie projektu Pythona i miejsc, od których zaczyna się wykonanie.
- **Robimy:** `detect()`, `is_source()` (`.py`, `.pyw`), `find_entrypoints()` (blok `if __name__ == "__main__":` i `main.py`/`__main__.py`, najpierw najbardziej prawdopodobny start). Prawdziwe uruchomienia z plików `.bat`/`.ps1` rozpoznaje agent z ich treści (kroki 24, 47-50).
- **Sprawdzamy:** dla robota 01 `detect` → `True`, punkt wejścia `main.py`; dla robota 02 - oba skrypty z `__main__`.

**Krok 17. Przenieś z doc-agents: `technologies/uipath.py` + rejestr (`technologies/registry.py`); puste klasy Robot Framework i NICE**
- **Funkcja:** przygotowane, dobrze opisane miejsca na kolejne technologie (implementacja osobno) i wybór technologii dla projektu.
- **Robimy:** puste klasy (`detect` → `False`, metody wymagane → `NotImplementedError` z nazwą technologii, opcjonalne → „brak danych”) z opisem w docstringu modułu, jak prosto zrealizować każdą metodę kontraktu: `uipath.py` (`project.json`: `main`, `entryPoints`, `dependencies`; `.xaml`; *Invoke Workflow File* jako `files`), `robotframework.py` (`.robot`/`.resource`, sekcje Tasks/Keywords, `Resource`/`Library`; pliki `.py` przez **delegację do `PythonTechnology`**), `nice.py` (NICE APA - otwarte pytania o formaty plików w docstringu). `technologies/registry.py` z rejestrem, `detect_technology()` i `get_technology()` (osobny moduł, nie `__init__.py` - importy technologii na górze pliku bez podwójnego ładowania modułu uruchamianego przez `-m`): technologie bardziej szczegółowe przed Pythonem, wygrywa pierwsza pasująca.
- **Sprawdzamy:** `detect_technology` dla listy plików robota → `python`; rejestr pokazuje cztery technologie, w tym trzy puste; metoda wymagana pustej klasy → `NotImplementedError`, opcjonalne → „brak danych”.

**Krok 18. Przenieś z doc-agents: `scanner.py` - lista plików**
- **Funkcja:** lista plików projektu bez śmieci (cache, venv, repozytorium gita) i bez wyników narzędzia.
- **Robimy:** sekcja `scan.ignore` w configu; pomijanie katalogów z `pyvenv.cfg`; **zawsze pomijany `dev_agents_doc/`** (niezależnie od configu).
- **Sprawdzamy:** lista plików robota bez `test-venv`, `__pycache__`; ręcznie utworzony `dev_agents_doc/` w kopii robota nie pojawia się na liście.

**Krok 19. Przenieś z doc-agents: `scanner.py` - role plików i sekrety**
- **Funkcja:** każdy plik dostaje rolę (kod, config, zależności, uruchamianie, dane, dokumentacja, binarny, sekret); sekrety nigdy nie są otwierane.
- **Robimy:** `scan.secret_patterns`, `scan.role_patterns` w configu (w tym rola `dependency` - np. `requirements*.txt`, `pyproject.toml`); kod wg technologii (`is_source`); pliki binarne tylko po wzorcach (rola `binary`), plik bez dopasowania → `other` - skaner nie otwiera żadnego pliku; nieznana nazwa roli w configu → błąd przy starcie.
- **Sprawdzamy:** tabela `ścieżka | rola | rozmiar`; `client.pfx` → `secret`, `config.yml` → `config`, `requirements.txt` → `dependency`; w robocie 02 `run.bat` → `launcher`.

**Krok 20. (wycofany 2026-11-26) Maskowanie haseł w tekście**
- **Funkcja:** wycofana decyzją użytkownika - hasło wpisane wprost w plik konfiguracyjny, uruchamiający albo w kod to błąd dewelopera, który ma być widoczny w przewodniku (agent wskazuje je jako ryzykowne miejsce), a nie ukryty. Pliki sekretów (`*.pfx`, `*.key`, `.env*`...) nadal trafiają do modelu wyłącznie jako metadane.

**Krok 21. `scanner.py` - frameworki po ścieżkach i po pakietach**
- **Funkcja:** odróżnienie kodu frameworku od kodu robota - także gdy framework jest zainstalowany jako pakiet (np. edytowalnie) i nie leży w projekcie. Rozszerzenie względem doc-agents.
- **Robimy:** `scan.frameworks` w configu: dla każdego frameworku `technology`, `paths` (wzorce ścieżek, gdy skopiowany do projektu), `packages` (nazwy pakietów porównywane z `references().packages` - działa także dla paczek w venv i instalowanych edytowalnie) i `knowledge` (plik wiedzy o frameworku w `knowledge_base/knowledge/`, przekazywany agentom zawsze, gdy framework wykryto; `load_config` sprawdza, że plik istnieje); oznaczanie plików `framework_name`; `project_packages()` i `detect_frameworks()` - lista wykrytych frameworków. W tym kroku powstaje makieta `knowledge_base/knowledge/frameworks/roboforge.md` (pełna treść w kroku 42). **Nowy framework = nowy wpis w configu + plik wiedzy, bez zmian w kodzie.**
- **Sprawdzamy:** robot testowy z `roboforge: {packages: [roboforge]}` → Roboforge wykryty, żaden plik robota nie jest oznaczony jako framework; dopisany w configu sztuczny framework z pakietem `requests` → wykryty w robocie 02 bez zmiany kodu.

**Krok 22. Przenieś z doc-agents: `scanner.py` - `build_project_map()`**
- **Funkcja:** kompletna mapa projektu w jednym obiekcie.
- **Robimy:** złożenie `ProjectMap`: technologia (`registry.detect_technology`), punkty wejścia (bez plików frameworku), pliki, jednostki kodu do analizy (pliki źródłowe spoza frameworku), frameworki; dla każdego pliku źródłowego robota `units()` i `references()` w nowej klasie `SourceFile` (pole `ProjectMap.source_files`); pakiety do wykrywania frameworków tylko z kodu robota (`_project_packages`). Nierozpoznana technologia - mapa z samą listą plików, bez błędu.
- **Sprawdzamy:** skrót map robotów 01 i 02 i katalogu tymczasowego (plik skopiowanego frameworku z importem `requests` nie wykrywa sztucznego frameworku z pakietem `requests`, robot 02 - wykrywa); pełny JSON mapy dowolnego katalogu.

**Krok 23. `scanner.py` - pliki zależności, konfiguracyjne i uruchamiające przepisane dosłownie (W2, W8)**
- **Funkcja:** pełna lista zależności robota do skopiowania z zakładki Przegląd oraz konfiguracja i sposób uruchamiania (np. `run.bat`) jako tekst dla agentów (metryczka, uruchomienie, dostępy) - przepisane przez kod, bez udziału modelu, więc bez ryzyka przekłamania.
- **Robimy:** `schemas.TextFile` (`path`, `role`, `text`) i pole `ProjectMap.text_files`; w configu `scan.text_roles` (`dependency`, `config`, `launcher`) i `scan.max_text_file_kb` (100), `config.py` dopuszcza w `text_roles` tylko role z `role_patterns` (nigdy `secret` ani `source`); `scanner._read_text_files` czyta pliki robota (bez plików frameworku) przez `files.read_text_safe` (UTF-16!); większy plik - tylko wpis w `files`. Bez parserów, typów wpisów i maskowania - znaczenie kluczy opisują agenci, a hasło wpisane wprost wskazują jako ryzykowne miejsce. Renderer bierze zależności filtrem `role == "dependency"`.
- **Sprawdzamy:** mapa robota 01 zawiera czytelną treść `requirements.txt` z linią `-e git+...roboforge` i `config.yml`; robot 02 - `requirements.txt` (`openpyxl`, `requests`) i `run.bat`; plik większy niż limit i `.env` poza `text_files`; rola `secret` w `text_roles` → błąd przy starcie.

**Krok 24. (połączony z krokiem 23, 2026-11-26) Pliki konfiguracyjne i uruchamiające jako tekst**
- **Funkcja:** zrealizowana w kroku 23 - ten sam mechanizm (`text_files`, `scan.text_roles`) obejmuje role `config` i `launcher`.

**Krok 25. (wycofany 2026-11-26) Gdzie używane są klucze konfiguracji**
- **Funkcja:** przejęta przez agentów - analityk wskazuje miejsca użycia kluczy w notatce (plik:linia z kodu z numerami linii, krok 49).

**Krok 26. (wycofany 2026-11-26) Ustawienia zaszyte w kodzie**
- **Funkcja:** przejęta przez agentów - analityk wypisuje w notatce ustawienia ze stałych w kodzie (adresy, ścieżki, nazwy zmiennych środowiskowych) z plikiem i linią (krok 49); hasło wpisane wprost w stałą wskazuje jako ryzykowne miejsce.

**Krok 27. `output.py` - wyniki w `dev_agents_doc/` analizowanego projektu**
- **Funkcja:** bezpieczny zapis wyników w cudzym repozytorium: dokumentacja leży obok kodu, a narzędzie nigdy nie skasuje cudzych plików.
- **Robimy:** `create_run_store(project_root, clear)` i `RunStore` dla `<projekt>/dev_agents_doc/` ze znacznikiem `.dev_agents_output`; czyszczenie przy starcie tylko katalogu ze znacznikiem; niepusty katalog bez znacznika → błąd, nic nie kasujemy; pusty katalog bez znacznika - przejmowany; prawo zapisu sprawdzane na początku (zapis znacznika); `path` (nazwa wychodząca poza katalog wyników → błąd), `save_text`, `save_json`, `load_json`, podkatalogi (`notes/`, `tabs/`) tworzone same.
- **Sprawdzamy:** na kopii robota 02 w katalogu tymczasowym (robot 01 nie jest kopiowany - plik sekretu): zapis i odczyt JSON; `clear=False` zostawia pliki; drugi start czyści katalog; niepusty katalog bez znacznika → błąd i nic nie usunięte; pusty - przejęty; zwykły plik w miejscu `dev_agents_doc` → czytelny błąd zapisu (atrybut „tylko do odczytu” katalogu na Windows nie blokuje zapisu); nazwa z `..` → błąd.

**Krok 28. `dependencies.py` - graf zależności i kolejność czytania**
- **Funkcja:** dane do grafu zależności między plikami i szkic kolejności czytania kodu, bez modelu.
- **Robimy:** `dependencies.build_dependencies(project_map)` bez nowych klas: pola `ProjectMap.dependency_edges` (pary ścieżek `[plik, plik, z którego korzysta]` z `references.files`, tylko między plikami źródłowymi robota - bez frameworku; bez wiedzy o technologii; węzły i punkty wejścia już są w mapie) i `ProjectMap.reading_order` (od punktów wejścia w głąb, alfabetycznie na każdym poziomie, każdy plik raz - cykle bez zawieszenia; pliki nieosiągalne na końcu); wołane na końcu `scanner.build_project_map`.
- **Sprawdzamy:** graf robota 01 (`main.py` → moduły `src/`) i lista kolejności (`src/__init__.py` na końcu); robot 02 - dwa punkty wejścia bez krawędzi; sztuczny cykl dwóch plików nie zawiesza obliczeń, krawędź do skopiowanego frameworku odpada.

**Krok 29. `main.py` - skan i zapis wyników**
- **Funkcja:** pierwszy użyteczny przebieg: mapa projektu (z grafem zależności i kolejnością czytania) w katalogu wyników robota.
- **Robimy:** `--project` wymagany; config → skan (`build_project_map`, graf w środku) → `output.create_run_store` → `dev_agents_doc/project_map.json`; podsumowanie na ekranie (technologia, role, punkty wejścia, frameworki, jednostki, najdłuższa jednostka, pliki tekstowe, ścieżka zapisu); nierozpoznana technologia → błąd (kod 1) przed założeniem `dev_agents_doc/`; katalog wyników obcy albo bez prawa zapisu → komunikat z `output.py`.
- **Sprawdzamy:** `python main.py --project <robot 02>` tworzy `project_map.json` w `<robot 02>\dev_agents_doc\` (w mapie `run.bat` z treścią, `run` - linie 41-411, `requirements.txt`); drugi start - ten sam wynik, katalog wyczyszczony; bez `--project` - błąd argparse; katalog bez kodu - błąd, nic nie zapisane. Robot 01 tylko do odczytu - jego mapę pokazuje `python -m dev_agents.scanner` (bez zapisu). ✅ **M3**

### Faza D - Szablon przewodnika i HTML bez modelu

**Krok 30. `guide_template.yaml` + `guide_template.py`**
- **Funkcja:** struktura przewodnika (zakładki i sekcje) opisana poza kodem, żeby zespół mógł ją zmieniać bez programowania.
- **Robimy:** `knowledge_base/templates/guide_template.yaml` odwzorowujący makietę: 7 zakładek (Przegląd i uruchomienie - na górze metryczka typu `config`, Przepływ działania, Ścieżki procesu, Struktura projektu, Zmiany i rozszerzenia, Błędy i naprawa - z sekcją „Ryzykowne miejsca” typu `table` ze źródłem `code`, Dla dewelopera), przy każdej opis do kart „jak czytać”; dla sekcji: `id`, `title`, `type` z zamkniętej listy (`text`, `list`, `steps`, `code`, `table`, `glossary`, `io`, `cards`, `config`, `tree`, `dependency_graph`, `flow`, `paths`, `recipes`), `source` (`llm`/`scanner`/`code`), `required` (sekcja zawsze widoczna; gdy z kodu nic nie wynika, pokazuje „nie wynika z kodu”, nigdy wymyśloną treść), `instruction`, przy `table` kolumny, opcjonalnie `technologies` (lista technologii, dla których sekcja się pojawia, np. „venv i pip” tylko dla `python`; brak pola = wszystkie); `guide_template.py`: klasy Pydantic (`GuideTemplate`, `TemplateTab`, `TemplateSection`) i sprawdzenie zwykłym kodem (typ i źródło z zamkniętej listy, unikalne `id`, kolumny tabel, znane technologie z rejestru), `load_template`, `sections_for_technology`; ścieżka szablonu w configu: `paths.guide_template` (sprawdzana przy starcie). Prawdziwy szablon na razie bez filtrów technologii (makieta nie ma sekcji tylko dla Pythona).
- **Sprawdzamy:** wydruk zakładek i sekcji dla `python`; filtr technologii na kopii szablonu w pamięci (sekcja z `technologies: [python]` znika dla `uipath`); nieznany typ, zdublowane `id`, nieznana technologia w filtrze albo tabela bez kolumn → czytelny błąd; brak pliku szablonu → błąd przy wczytaniu configu.

**Krok 31. `guide_content.py` - treść przewodnika i diagram**
- **Funkcja:** ogólny kształt treści, niezależny od konkretnych sekcji, oraz osobny, ścisły schemat diagramu przepływu.
- **Robimy:** nowy moduł `dev_agents/guide_content.py` (mapa projektu zostaje w `schemas.py`): `FlowNode` (`id`, `kind`: `start`/`end`/`step`/`system`/`decision`, `label` - krótki opis biznesowo-techniczny, `description`, `module`, `functions`, `reads`, `writes`, `certain`), `FlowEdge` (`source`, `target`, `label`, `kind`: `normal`/`branch`/`loop`), `FlowGraph`; jedna klasa `GuideBlock` (`section_id` + pola zależne od typu: `paragraphs`, `items`, `steps`, `rows`, `terms`, `inputs`/`outputs`, `paths`, `recipes`, `code`, `config_items`) - jeden schemat JSON bez wariantów `anyOf`; klasy pomocnicze `Step`, `GlossaryTerm`, `IoItem`, `PathStep`, `ProcessPath`, `RecipeFile`, `Recipe`, `ConfigItem` (wpis metryczki: plik albo stała w kodzie z plikiem i linią, grupa, klucz, wartość dosłownie, rodzaj - `system`, `account`, `env_var`, `input_file`, `output_file`, `log`, `switch`, `other` -, `plain_password` - hasło wpisane wprost, czerwony znacznik -, znaczenie, miejsca użycia, `certain`); `GuideTab`, `GuideContent`; `Field(description=...)` dla modelu.
- **Sprawdzamy:** przykładowa treść i diagram (dane z makiety) złożone ręcznie, wydruk JSON i zgodność po odczycie.

**Krok 32. `flow.py` - spójność i układ diagramu (W1)**
- **Funkcja:** gwarancja, że diagram jest poprawnym grafem, oraz układ liczony przez kod, nie przez model.
- **Robimy:** `validate_flow()` zwracająca (problemy, ostrzeżenia): problemy - dokładnie jeden start, co najmniej jeden koniec, unikalne id, strzałki do istniejących klocków, każdy klocek osiągalny ze startu, z każdego klocka poza końcem wychodzi strzałka, decyzja ma co najmniej dwa wyjścia z etykietami, `step`/`system` mają moduł, cykl bez strzałki `loop`; ostrzeżenia - więcej niż `flow.max_nodes` klocków albo `flow.max_decisions` decyzji (znak, że szczegóły techniczne powinny zejść do wierszy „krok po kroku”); nowa sekcja `flow` w configu. `layout_flow()` → `{id: [wiersz, kolumna]}` w formacie skryptu z makiety: wiersze - porządek od startu w dół bez strzałek pętli (remis - kolejność klocków od agenta), kolumna 1 - objazd z decyzji (wchodzą tylko gałęzie, jedno wyjście do klocka, do którego prowadzi też inna strzałka), pętle jako strzałki powrotne rysowane przez skrypt.
- **Sprawdzamy:** diagram z makiety: zero problemów i układ identyczny z makietą; przykładowy diagram robota 02; zepsute kopie (klocek bez wyjścia, strzałka do nieistniejącego klocka, decyzja z jednym wyjściem, dwa starty, cykl bez `loop`) → czytelna lista problemów; 31 klocków → ostrzeżenie o rozmiarze.

**Krok 33. `render.py` - szkielet HTML, zakładki, „jak czytać” (W5)**
- **Funkcja:** zamiana treści na samowystarczalny HTML w stylu makiety; pierwszy widoczny efekt.
- **Robimy:** `pip install jinja2` (+ `requirements.txt`); `guide.css` i `guide.js` przeniesione z makiety jeden do jednego (cały skrypt: router zakładek, podpowiedzi, kopiowanie, rysowanie diagramu i grafu - diagram i graf rysują się tylko, gdy są ich dane), `guide.html.j2` (menu, stopka, zakładki, sekcje w kolejności z szablonu); CSS i JS wstawiane do pliku; `render_guide(content, template, project_map, templates_dir, generated_at)`; bloki `text`, `list`, `io`; blok `cards` z kart zakładek w `guide_template.yaml`; sekcja wymagana bez treści - „nie wynika z kodu”, opcjonalna bez treści - pominięta, typ z kolejnych kroków - widoczny znacznik; zakładka bez `lead` z pierwszą sekcją typu `text` - nagłówek „nazwa projektu: pierwszy akapit”, reszta jako lead; escapowanie zawsze włączone; test zapisuje HTML z przykładową treścią do `guide_test.html` w katalogu głównym repo (stała nazwa, w `.gitignore`).
- **Sprawdzamy:** HTML otwiera się bez internetu (zero odwołań do zasobów zewnętrznych), zakładki się przełączają, karty prowadzą do zakładek, polskie znaki poprawne, `<script>` z treści widoczny jako tekst, wygląd zgodny z makietą.

**Krok 34. `render.py` - bloki `steps`, `code`, `table`, `glossary`, `paths`, `recipes` (W2, W4, W6, W7)**
- **Funkcja:** pozostałe bloki tekstowe: instalacja krok po kroku z kodem do skopiowania, tabele wymagań i błędów, słowniczek, ścieżki procesu z odwołaniami do klocków, przepisy zmian.
- **Robimy:** szablony bloków; kolumny tabel z `guide_template.yaml` (także etykiety kart na telefonie); odwołania `paths` do numerów klocków diagramu (numer = pozycja w `flow.nodes`, link do zakładki Przepływ); oznaczenie „wywnioskowane” dla komórki tabeli zakończonej znacznikiem `[wywnioskowane]` (zdanie o znaczniku w poleceniach sekcji tabel w `guide_template.yaml`); nowy plik w przepisie w czerwonej ramce, opis zmiany pliku po najechaniu.
- **Sprawdzamy:** przykładowa treść z każdym typem bloku wyświetla się jak w makiecie; tekst z `<script>` wyświetlany jako tekst (escapowanie); przycisk „Kopiuj” kopiuje blok kodu.

**Krok 35. `render.py` - bloki: metryczka, drzewo, zależności do skopiowania, ryzykowne miejsca (W2, W6, W8)**
- **Funkcja:** fakty o projekcie wstawiane przez kod (drzewo, zależności, długość jednostek) i metryczka w stałym układzie.
- **Podział (decyzja użytkownika):** dwie części w ramach kroku 35, każda z własnym testem i commitem. Część 1: metryczka (`config`). Część 2: drzewo, zależności do skopiowania, ryzykowne miejsca (`analysis.long_unit_lines: 100`). Opisy po najechaniu w drzewie: fakty z kodu (rola, rozmiar, funkcje), wiersze `[ścieżka, czym jest, rola]` od pisarza mają pierwszeństwo. Hasła wpisane wprost (`plain_password`) kod sam dodaje do „Ryzykownych miejsc”, pisarz dopisuje komentarz.
- **Część 1 (metryczka):** nagłówek z nazwami plików konfiguracyjnych albo „Ustawienia w kodzie” + zdanie od pisarza (pierwszy akapit bloku, np. gdzie i czym plik jest wczytywany); kafelki w stałej kolejności (pusty kafelek pominięty, rodzaj `other` tylko w tabeli); rozwijana tabela „Pełna konfiguracja” z wierszami grupującymi (sekcja pliku, nazwa pliku albo „w kodzie”); hasło wpisane wprost z czerwonym znacznikiem „hasło w pliku” / „hasło w kodzie”; pusta lista wpisów → „Robot nie ma konfiguracji - nie wynika z kodu.”
- **Część 2 (drzewo, zależności do skopiowania, ryzykowne miejsca):** nowy moduł `guide_facts.py` (`build_tree`, `dependency_text`, `risky_rows`, `password_mark`), wołany przez `render.py`. Drzewo (`tree`): znaczniki ról jak w legendzie makiety (punkt wejścia, kod robota, konfiguracja, sekret), opis po najechaniu z faktów kodu (rola, rozmiar, funkcje z liniami), wiersze pisarza `[ścieżka, czym jest, rola]` mają pierwszeństwo, pliki frameworku pominięte z adnotacją. Zależności (`code` ze źródłem `scanner`): treść plików zależności bez zmian, przy kilku plikach z nagłówkami „# --- ścieżka ---”, bez pliku zdanie o braku. Ryzykowne miejsca (tabela ze źródłem `code`): najpierw hasła wpisane wprost, potem jednostki dłuższe niż `analysis.long_unit_lines` od najdłuższej; komentarz pisarza dopasowany po Miejscu i Pliku i liniach (bez komentarza zdanie domyślne), dodatkowe wiersze pisarza na końcu, brak wierszy → zdanie z progiem. `config.yaml`: sekcja `analysis` (`long_unit_lines: 100`, sprawdzana `> 0`, dziewiąty przypadek testowy configu).
- **Robimy:** blok `config` (metryczka jak w makiecie) z `config_items` - w tej fazie na danych przykładowych, w fazie F od pisarza (krok 55): kafelki pogrupowane po rodzaju (systemy zewnętrzne, pliki, konta i zmienne środowiskowe, przełączniki), pod spodem tabela (klucz, wartość, znaczenie, używany w), hasło wpisane wprost z czerwonym znacznikiem „hasło w pliku”, „w kodzie” z plikiem i linią; brak konfiguracji → jedno zdanie. Blok `tree` z `ProjectMap` (role, sekrety „tylko metadane”, opisy po najechaniu - zaślepki do fazy F); blok `code` dla plików zależności; tabela „Ryzykowne miejsca” z jednostek dłuższych niż `analysis.long_unit_lines` (nowa sekcja w configu - tu po raz pierwszy potrzebna): jednostka, plik:linie, długość, komentarz (zaślepka - w fazie F od pisarza).
- **Sprawdzamy:** robot 02: „Ryzykowne miejsca” z `run()`, drzewo z `run.bat`; robot 01: drzewo i `requirements.txt` z prawdziwej `project_map.json` z kroku 29; metryczka z danych przykładowych jak w makiecie; pusta lista wpisów → zdanie o braku konfiguracji.

**Krok 36. Diagram przepływu w HTML (W1, W3)**
- **Funkcja:** czytelny diagram całego procesu: start, klocki, strzałki, decyzje, pętle - z podpowiedzią po najechaniu (moduł, funkcje, czyta, zapisuje).
- **Decyzje użytkownika (1A, 2A, 3A):** krok 36 to sam diagram (wiersze „Krok po kroku” w kroku 37, który skurczy się do typowanych kafelków wejść i wyjść, bo skrypt z makiety buduje wiersze z tych samych danych); diagram, który nie przechodzi `validate_flow`, nie jest rysowany (zamiast niego lista problemów, bo brakujący układ przerywa skrypt na całej stronie); klocek wywnioskowany (`certain = false`) z oznaczeniem „wywnioskowane” w podpowiedzi. Zrobione: `flow_view_data()` w `flow.py` (format skryptu z makiety: `term/step/sys/dec`, `from/to`, `func`, `desc`, flaga `unc`, `layout`), blok `flow` w `render.py` i szablonie (legenda, `<svg id="flow">`, JSON przez `tojson`, bez `h2` nad diagramem), podpowiedź w `guide.js` bez pustego „Moduł i funkcja”.
- **Robimy:** blok `flow`: dane `FlowGraph` + układ z `flow.py` wstawione do HTML jako JSON; rysowanie SVG w `guide.js` jak w makiecie (kształty wg `kind`, numery klocków, etykiety „tak/nie”, czerwone przerywane powroty pętli, zawijanie długich napisów, widok na telefonie).
- **Sprawdzamy:** diagram z makiety i diagram 25+ klocków (sztuczny) są czytelne na laptopie i w wąskim oknie; podpowiedź pokazuje dane klocka.

**Krok 37. Przepływ krok po kroku pod diagramem (W3)**
- **Funkcja:** dla każdego klocka wiersz „czyta - co się dzieje - zapisuje”, z tych samych danych co diagram, więc nie mogą się rozjechać.
- **Decyzje użytkownika (1A, 2A, 3 tak):** wiersze rysuje skrypt (`guide.js`) z tych samych danych co diagram, a krok dokłada markup (nagłówek „Krok po kroku”, legenda rodzajów kafelków, nagłówki kolumn, kontener `#flowrows`); rodzaj kafelka (plik, zmienna środowiskowa, system zewnętrzny, dane w pamięci) jako pole schematu: `FlowNode.reads` i `writes` to listy `DataRef` (`name` i `kind`: `file`, `env`, `system`, `memory`), do skryptu trafia klasa kafelka `f`/`env`/`sys`/`mem`; funkcje klocka jako lista numerowana (`funcs` w danych skryptu). Zrobione: `guide_content.py` (`DataRef`), `flow.py` (`_view_ref`, `_view_refs`, `funcs`), szablon i `guide.js` (wiersze, kafelki z rodzaju, znacznik „wywnioskowane” w wierszu), polecenie dla pisarza w `guide_template.yaml`.
- **Robimy:** wiersze generowane z `FlowGraph` (moduł, funkcje w kolejności, wejścia i wyjścia jako oznaczone „kafelki”: plik, zmienna, system, dane w pamięci); wyjścia decyzji; strzałki z powrotem pętli; kliknięcie klocka przewija do wiersza i go wyróżnia.
- **Sprawdzamy:** kliknięcie klocka 9 w diagramie przewija do wiersza kroku 9; liczba wierszy = liczba klocków.

**Krok 38. Graf zależności modułów i podpowiedzi słowniczka**
- **Funkcja:** rysunek, który moduł importuje który, oraz definicje pojęć po najechaniu na nie w tekście.
- **Robimy:** blok `dependency_graph` z `ProjectMap.dependency_edges` i `entrypoints` (warstwy od punktu wejścia, jak w makiecie); oznaczanie wystąpień terminów słowniczka w tekście (bezpiecznie, po escapowaniu) i dymek z definicją.
- **Sprawdzamy:** graf robota testowego czytelny; termin pokazuje dymek; termin wewnątrz innego słowa nie jest oznaczany.
- **Decyzje użytkownika (1B, 2A, 3A):** graf, kolejność czytania i dymki słowniczka w jednym kroku; węzłami grafu są punkty wejścia i moduły z krawędziami, pliki bez powiązań tylko w zdaniu pod grafem („Pliki bez powiązań z innymi plikami robota: 1 (src/__init__.py)”), robot bez importów dostaje zdanie zamiast rysunku; kolejność czytania: listę i kolejność daje kod (`reading_order`), pisarz dopisuje w `items` zdania „plik: zdanie” dopasowane po ścieżce (pozycja bez pasującego pliku trafia na koniec w całości). Zrobione: `guide_facts.py` (`dependency_graph_data`, `reading_items`), nowy `glossary.py` (indeks terminów, dopasowanie całych słów bez względu na wielkość liter, najdłuższy termin wygrywa, escapowanie kawałkami), filtr szablonu `terms` w akapitach, listach, krokach, opisach wejść i wyjść, komórkach tabel poza kodem, ścieżkach, przepisach i kolejności czytania, `guide.js` (dymek terminu: najechanie, fokus, kliknięcie przypina, Enter/spacja; poprawiony `drawDeps`), `guide.css` (`.tm`), instrukcje w `guide_template.yaml`, wariant testu `render robot01`.

**Krok 39. Przewodnik z prawdziwego robota, sekcje modelu jako zaślepki**
- **Funkcja:** zatwierdzenie wyglądu i układu na prawdziwych danych, zanim wydamy pierwszy token na treść.
- **Robimy:** `main.py --render-only`: skan → sekcje `scanner` i `code` wypełnione, sekcje `llm` z zaślepką, diagram z danych przykładowych → `dev_agents_doc/guide.html`.
- **Sprawdzamy:** przewodniki robotów 01 i 02 otwierają się offline; metryczka, drzewo, zależności do skopiowania, graf zależności i karty „jak czytać” prawdziwe; uwagi do wyglądu poprawione przed fazą E. ✅ **M4**
- **Decyzje użytkownika (rekomendowane: A, A, A):** zaślepki składa nowy moduł `guide_placeholders.py` (tekst w nawiasach kwadratowych w kształcie typu sekcji, zdania „plik: [dlaczego…]” w kolejności czytania, wpisy metryczki z wartością „[wartość]” - bez haseł); diagram przykładowy ogólny, każdy napis z „[przykład]”; robot 01 tylko do odczytu: jego przewodnik w pamięci (`python -m dev_agents.guide_placeholders robot01` zapisuje `guide_test.html` w repo), prawdziwy zapis `dev_agents_doc/` przez `main.py --render-only` tylko na robocie 02. Metryczka ma zaślepki, a nie prawdziwe wartości: wartości pliku konfiguracyjnego przepisuje agent (kod ich nie parsuje).

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
- **Robimy:** `guide_goals.md` (nowy: odbiorca, ton, poziom szczegółów, oznaczanie informacji wywnioskowanych i braków, sekrety wpisane wprost dosłownie i oznaczone, ryzykowne miejsca, ścieżki procesu); `diagram_rules.md` (osobny plik dla autora diagramu: **zasady diagramu** - jeden klocek na czynność widoczną dla biznesu, każdy kontakt z systemem zewnętrznym jako osobny klocek, pętle i decyzje jawnie, nazwy klocków czasownikiem, **na diagramie tylko decyzje widoczne dla biznesu - warunki techniczne i zagnieżdżone schodzą do opisu kroku**, limit ok. 30 klocków); `technologies/python.md` (z `python_conventions.md` z doc-agents) i `frameworks/roboforge.md` (z `rpa_framework.md` z doc-agents, z cyklem życia Roboforge) - po jednym pliku na technologię i framework, żeby dodanie kolejnych było dopisaniem pliku; metoda opcjonalna `Technology.knowledge_file()` wskazuje plik technologii; pliki technologii i wykrytych frameworków trafiają do agentów zawsze, niezależnie od wyboru plannera, dlatego `index.md` zawiera tylko pliki do wyboru (`guide_goals.md`, `diagram_rules.md`).
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
- **Decyzje użytkownika (1C, 2A):** postęp raportują same węzły przez funkcję `report` w `RunContext`, a nie strumień LangGraph (tryb `tasks` wymaga checkpointera, tryb `updates` nie ma zdarzenia startu); linie tylko na ekran, bez pliku.
- **Robimy:** nowy `dev_agents/progress.py`: `format_line` (`[GG:MM:SS] etap: tekst`), `format_seconds` (`0,4 s`), `print_line` (z natychmiastowym opróżnieniem bufora) i menedżer kontekstu `Stage` (start, `note()` w trakcie pracy, koniec `gotowe w X s - wynik` albo `BŁĄD po X s - Typ: komunikat` z puszczeniem wyjątku dalej); `RunContext.report` i `build_context(app_config, store, report)`; węzeł `scan` owinięty w `Stage`; `main.py` podaje `print_line` i po grafie wypisuje `razem: X s`. Każdy kolejny węzeł owija pracę w `Stage` i dopisuje `note()` tam, gdzie praca jest długa.
- **Sprawdzamy:** `python -m dev_agents.progress` (etap udany, z postępem, bez wyniku, z błędem, format czasu); test grafu sprawdza dwie linie postępu węzła `scan`; przebieg `main.py` wypisuje start i koniec węzła `scan` z czasem i `razem`.

**Krok 46. `schemas.py` - plan**
- **Funkcja:** wynik pracy plannera: kolejność i wskazówki dla analityków oraz wiedza dla agentów.
- **Decyzje (rekomendowane, tryb pracy fazy F: 1A, 2A, 3A):** analizujemy wszystkie jednostki z mapy (planner ustala kolejność i wskazówki, brakujące jednostki dopisze kod w kroku 47; bez pola `skipped`); pliki wiedzy w trzech listach (analitycy, autor diagramu, pisarze); bez pola `optional_sections` (opcjonalną sekcję pisarz pomija sam, gdy nie ma treści - zasada szablonu).
- **Robimy:** w `schemas.py` `AnalysisTask` (`unit` - nazwa jednostki z mapy, `hint` - wskazówka) i `Plan` (`summary`, `tasks`, `analyst_knowledge`, `flow_knowledge`, `writer_knowledge`); `Field(description=...)`, schemat płaski bez `anyOf`.
- **Sprawdzamy:** ręcznie złożony plan robota 02, wydruk JSON i zgodność po odczycie; schemat JSON klasy `Plan` bez `anyOf` i z opisem przy każdym polu; plan bez `summary` i `tasks` odrzucony przy odczycie.

**Krok 47. Agent planner (bez grafu)**
- **Funkcja:** podsumowanie robota, kolejność i wskazówki dla analityków oraz wiedza dla kolejnych agentów.
- **Decyzje (rekomendowane, tryb pracy fazy F):** poprawki planu zwykłym kodem po odpowiedzi modelu (`complete_plan`): zadanie z nieznaną jednostką usuwane, powtórzone usuwane, jednostka pominięta przez plannera dopisywana na końcu z pustą wskazówką (analizujemy wszystko), plik wiedzy spoza spisu albo powtórzony usuwany; każda poprawka to uwaga w linii postępu; mapa projektu w prompcie bez pola `root` (ścieżka dysku niepotrzebna modelowi), z dosłowną treścią plików zależności, konfiguracji i uruchamiających, bez kodu źródłowego.
- **Robimy:** `dev_agents/agents/planner.py` (`build_planner_variables`, `complete_plan`, `create_plan`, `planner_node` w `Stage`, `print_plan`), prompty `prompts/planner/system.md` i `user.md`, pole `plan` w `RunState`; węzeł dołącza do grafu krok 48.
- **Sprawdzamy:** `python -m dev_agents.agents.planner` bez modelu (prompt bez kodu i bez ścieżki, z treścią konfiguracji i spisem wiedzy; poprawianie planu z pięcioma błędami; węzeł z udawanym modelem: `plan.json`, linie postępu); `python -m dev_agents.agents.planner <katalog robota>` z prawdziwym modelem czyta `dev_agents_doc/project_map.json` i wypisuje plan - dla robota 02 zadania `przetwarzanie.py`, potem `raport.py`, `run.bat` w podsumowaniu jako start, wiedza: `diagram_rules.md` dla autora diagramu i `guide_goals.md` dla pisarzy.

**Krok 48. Graf: scan → planner**
- **Funkcja:** planner jako etap przepływu.
- **Robimy:** węzeł planner w grafie (START → scan → planner → END), zapis `plan.json`; wspólny udawany model `dev_agents/fakes.py` (`FakeStructuredModel`) do testów agentów bez sieci; `main.py` wypisuje linię o planie (liczba zadań, pliki wiedzy).
- **Sprawdzamy:** przebieg tworzy `plan.json`; podgląd postępu pokazuje liczbę zadań; test grafu na udawanym modelu sprawdza pełność planu, zapis `plan.json` i linie postępu.

**Krok 49. `schemas.py` - notatka analityka (W1-W7)**
- **Funkcja:** ustrukturyzowana wiedza o jednej jednostce kodu - surowiec dla wszystkich zakładek.
- **Robimy:** `ModuleNote` przeniesiony z doc-agents (przeznaczenie, automatyzowana aplikacja, kroki procesu, obsługa błędów, wejścia/wyjścia, konfiguracja, zależności, pułapki, wskazówki) i rozszerzony o: **czynności z odwołaniem do funkcji i linii, z danymi czytanymi i zapisywanymi** (surowiec diagramu), **ustawienia z konfiguracji i ze stałych w kodzie z miejscami użycia (plik:linia)** (surowiec metryczki), **trudne miejsca z uzasadnieniem** (surowiec „Ryzykownych miejsc”), **rolę w przepływie** (np. metoda wołana przez framework), **dostęp sieciowy** (adresy, porty, systemy), **wymagania uruchomieniowe** (aplikacje, sterowniki, konta, nazwy zmiennych), **punkty rozszerzeń**, **możliwe błędy z objawem i naprawą**, **konwencje**, **kandydatów do słowniczka**; przy wnioskach flaga pewności. Wszystkie listy mogą być puste, a pola tekstowe przyjmują „nie wynika z kodu” - schemat nie zmusza modelu do wymyślania. Dodatkowo `part`/`parts` dla notatek z kawałków długiej funkcji (krok 51).
- **Decyzje (krok zrobiony, poprawione w kroku 50):** pierwsza wersja schematu (z polami domyślnymi i `ge=1`) nie przeszła na bramce Kwadratu przy pierwszym prawdziwym wywołaniu analityka: najpierw 400 `property 'minimum' is not supported` (ograniczenia liczbowe), potem 400 `The compiled grammar is too large`. Pierwsza hipoteza (koszt rośnie z liczbą pól opcjonalnych) była błędna - biblioteka openai i tak wysyła wszystkie pola jako wymagane. **Limit zmierzony** skryptem `scripts/probe_schema.py` na prawdziwej bramce (model small, `json_schema`): przechodzi schemat do **48 pól po rozwinięciu klas zagnieżdżonych** (pole klasy użytej dwa razy liczy się dwa razy), 49 już nie (płaski obiekt: 40 OK, 80 odpada; `ModuleNote` od 16. pola, 49 pól); osobny limit: najwyżej **16 pól typu `tekst albo null`**; brak ograniczeń liczbowych. Bez znaczenia: głębokość zagnieżdżenia (5 poziomów OK), enumy `Literal` (40 pól OK), wielokrotne użycie tej samej klasy (16 razy OK), pola z wartością domyślną. Wersja końcowa: schemat notatki rozbity na dwie odpowiedzi modelu - `NoteFlow` (przebieg: 22 pola) i `NoteDetails` (ustawienia, wymagania, ryzyka: 32 pola) - a `ModuleNote(NoteDetails, NoteFlow)` to ich złożenie (54 pola, nie jest wysyłany do modelu); wszystkie pola wymagane (model zwraca `[]` albo `""`), bez ograniczeń liczbowych i długościowych, bez `part`/`parts` (notatki kawałków z kroku 51 składa kod), ustawienia w klasie `NoteSetting`, dostęp sieciowy w `NoteRequirement` (rodzaj `network`), flaga `certain` tylko przy czynnościach i ustawieniach (w tabelach niepewność to tekst `[wywnioskowane]`); dane czynności to `DataRef` z `guide_content.py`; `process_steps` obok `actions`. Test pilnuje: schematy dla modelu (`Plan`, `NoteFlow`, `NoteDetails`) mają najwyżej `MAX_MODEL_SCHEMA_PROPERTIES` = 40 pól (`count_schema_properties()`, zapas względem 48), brak `anyOf`, brak ograniczeń, opis przy każdym polu, części dają razem dokładnie pola `ModuleNote`.
- **Uwaga na kroki 53-56 (zmierzone):** liczba pól po rozwinięciu klas: `FlowGraph` 19 (mieści się), `GuideBlock` 45 i `GuideTab` 47 (tuż pod limitem 48 bramki, ponad limitem testu 40), `GuideContent` 69 (nie idzie do modelu). Przed pierwszym prawdziwym wywołaniem pisarzy (krok 55) schemat odpowiedzi musi mieć najwyżej 40 pól: osobny, wąski schemat na typ sekcji zamiast jednego `GuideBlock` ze wszystkimi typami, albo kilka wywołań na zakładkę; test grafu/pisarza dodaje `count_schema_properties()` dla każdego schematu wysyłanego do modelu. Test `python -m dev_agents.schemas` już wypisuje UWAGĘ dla schematów ponad limitem.
- **Sprawdzamy:** ręcznie złożona notatka, wydruk JSON; notatka z pustymi punktami rozszerzeń przechodzi walidację; notatka minimalna; schemat bez `anyOf` i z opisem przy każdym polu; odrzucenie błędnych danych.

**Krok 50. Agent analityk (bez grafu)**
- **Funkcja:** zrozumienie jednej jednostki kodu: pełny kod z numerami linii + jednostki z zakresami + konfiguracja i pliki uruchamiające + wybrana wiedza → notatka.
- **Robimy:** `agents/analyst.py` przeniesiony z doc-agents i dostosowany do nowej notatki; kod podawany z numerami linii (żeby odwołania w notatce były dokładne); limit `analysis.max_file_size_kb` (większy plik - analiza po kawałkach z kroku 51); prompty `analyst/*`.
- **Decyzje (krok zrobiony):** `analysis.max_file_size_kb: 100` w `config.yaml` (plik większy - `ValueError` z nazwą pliku, po kawałkach dopiero krok 51); wspólne `agents/common.py` (wybór i skład plików wiedzy: technologia, frameworki, pliki plannera; numerowanie linii) zamiast kopii w każdym agencie; kod i pliki tekstowe z numerami linii `   12| kod`; pliki `secret` nigdy nie są czytane; kod poprawia odpowiedź modelu (nazwa jednostki z zadania, linia czynności spoza pliku → 0, `part`/`parts` = 1) i zgłasza uwagi; test z argumentami `<katalog robota> <jednostka>` woła prawdziwy model, niczego nie zapisuje (można podać robota 01 - czytany jest tylko kod jednostki i pliki tekstowe). **Notatka w dwóch wywołaniach modelu na jednostkę** (`NoteFlow` i `NoteDetails`, ten sam kod, opis części w `prompts/analyst/part_flow.md` i `part_details.md`, składanie `merge_note()`), bo cała notatka ma więcej pól niż przyjmuje bramka; koszt: kod jednostki wysyłany dwa razy.
- **Sprawdzamy:** notatka dla `main.py` robota 01: cykl życia Roboforge jako przepływ wołany przez framework, adresy stron w dostępie sieciowym, sensowne punkty rozszerzeń i błędy, odwołania do linii zgodne z kodem, niepewność oznaczona.

**Krok 51. Analityk: długie pliki po kawałkach**
- **Funkcja:** plik na setki linii jest przeczytany w całości, w porcjach - opis robota „spaghetti” opiera się na kodzie, nie na domysłach.
- **Robimy:** w `agents/analyst.py`: plik dłuższy niż `analysis.chunk_lines` dzielony zwykłym kodem po granicach jednostek z `units()`; jednostka dłuższa niż limit dzielona po liczbie linii (z małym zakładem); kawałki analizowane **po kolei**, każdy z: listą jednostek pliku (gdzie jest), krótkim podsumowaniem poprzednich kawałków i swoim kodem z numerami linii; notatki kawałków (`part`/`parts`) składane zwykłym kodem w jedną notatkę (czynności w kolejności linii, błędy, wejścia i wyjścia bez duplikatów). Podgląd postępu pokazuje „kawałek 3/7”.
- **Decyzje (krok zrobiony):** logika podziału i składania w osobnym module `agents/chunks.py` (bez modelu, własny test): `split_ranges` tnie po końcach jednostek z `units()` leżących w drugiej połowie kawałka, a bez takiej granicy w środku z zakładem `analysis.chunk_overlap_lines` (10); `plan_chunks` pakuje krótkie pliki jednostki razem, długi plik tnie (jednostka krótsza niż `analysis.chunk_lines` = 300 to jeden kawałek, jak dotąd); każdy kawałek to dwa wywołania modelu (`NoteFlow`, `NoteDetails`) z tym samym kodem z **bezwzględnymi numerami linii**, listą jednostek pliku z kontekstu projektu i podsumowaniem poprzednich kawałków składanym przez kod z ich notatek (cel i tytuły pierwszych 8 czynności); sekcja `<kawalek>` w `prompts/analyst/user.md` (warunkowa, tylko gdy kawałków więcej niż jeden); `merge_chunk_notes`: cele połączone, rola w przepływie z pierwszego niepustego kawałka, listy bez powtórzeń (czynności po tytule, funkcji i linii - zakład nie dubluje), ustawienia z tym samym kluczem łączą `used_in`; `analyze_unit` dostaje funkcję `note` do linii postępu "kawałek 3/7: zakres" (węzeł z kroku 52 poda `Stage.note`); `analysis.max_file_size_kb` zostaje twardym limitem pliku (błąd z nazwą pliku), a o podziale decyduje `analysis.chunk_lines`; test configu sprawdza dwa nowe pola. Koszt: kod jednostki idzie do modelu dwa razy na kawałek.
- **Sprawdzamy:** robot 02: `run()` analizowana w kilku kawałkach; złożona notatka zawiera czynności z całego zakresu linii (porównanie ręczne z kodem); krótkie pliki robota 01 analizowane jednym wywołaniem.

**Krok 52. Graf: równolegli analitycy**
- **Funkcja:** analiza wszystkich jednostek naraz.
- **Robimy:** krawędź warunkowa `dispatch_analysts` za plannerem: `Send("analyst", {project_map, plan, task})` na każde zadanie; węzeł `analyst_node` (w `agents/analyst.py`) woła `analyze_unit` z `Stage.note` i zapisuje `notes/<jednostka>.json`; w stanie pola `task` i `notes` (reducer `operator.add`); `analysis.max_concurrency` (4) w configu, przekazane jako `config={"max_concurrency": n}` przez `graph.run_config()` (main.py i test); test na udawanym analitykach (dwa wywołania na kawałek).
- **Sprawdzamy:** liczba notatek = liczba zadań; podgląd postępu pokazuje analityków z czasami.
- **Uczymy się:** `Send`, reducery, równoległe węzły.

**Krok 53. Agent autor diagramu (bez grafu) (W1)**
- **Funkcja:** diagram całego procesu od startu do końca, z notatek wszystkich analityków - kręgosłup przewodnika.
- **Robimy:** `agents/flow_writer.py` (czysta funkcja `write_flow()` + węzeł); odpowiedź jako `FlowGraph`; po odpowiedzi `flow.validate_flow()` - przy problemach albo ostrzeżeniu o rozmiarze jedno ponowne wywołanie z listą problemów w prompcie; prompty `flow_writer/*`; zasady diagramu (`diagram_rules.md`) i wiedza technologii/frameworka idą w `<baza_wiedzy>`; do promptu tylko pola przebiegu notatek (`NoteFlow`), w kolejności zadań planu; ponowienie wybiera lepszą z dwóch wersji (mniej problemów), niespójny diagram jest zwracany z listą problemów, nie przerywa przebiegu; `state.flow`; bez podpinania do grafu (krok 54).
- **Sprawdzamy:** diagram robota 02 z notatek z `dev_agents_doc/notes/` (bez ponownej analizy; robot 01 dopiero, gdy będzie sposób zapisu wyników poza jego katalogiem - notatki zawierają hasła dosłownie): spójne według `validate_flow`, diagram robota 02 mieści się w limicie mimo funkcji spaghetti, podgląd HTML zakładki Przepływ; z samego diagramu da się opowiedzieć proces (ocena użytkownika).

**Krok 54. Graf: autor diagramu po analitykach**
- **Funkcja:** diagram jako etap przepływu, zanim powstaną pozostałe zakładki.
- **Robimy:** węzeł `flow_writer` (z kroku 53) po analitykach (krawędź `analyst -> flow_writer` czeka na wszystkich), zapis `flow.json`, diagram w stanie; test grafu z udawanym autorem diagramu; `main.py` wypisuje liczbę klocków.
- **Sprawdzamy:** przebieg tworzy `flow.json`; podgląd postępu pokazuje liczbę klocków i wynik sprawdzenia spójności.

**Krok 55. Agent pisarz zakładki (bez grafu) (W2, W4, W6, W7)**
- **Funkcja:** treść jednej zakładki: sekcje z `guide_template.yaml`, napisane z notatek, mapy projektu, konfiguracji i **gotowego diagramu** (ścieżki, błędy i przepisy odwołują się do numerów klocków).
- **Robimy:** `agents/writer.py` (czysta funkcja `write_tab()` + węzeł `writer_node`, pola stanu `tab_id`, `tabs`); odpowiedź modelu w schemacie zakładki budowanym z sekcji zakładki (`tab_response_model`, tylko pola potrzebne sekcjom, ≤40 pól) i zamienianym na `GuideTab`; pole szablonu `writer_adds` dla sekcji `scanner`/`code`, do których pisarz dokłada wiersze lub zdania (drzewo, ryzykowne miejsca, kolejność czytania); kod sprawdza wynik (`check_tab`: brak wymaganej sekcji, liczba komórek wiersza, wpis metryczki bez znaczenia, ścieżka główna, odwołania do klocków) i raz ponawia; sekcje `scanner`/`code` wypełnia kod, model tylko sekcje `llm`; pisarz zakładki Przegląd dostaje pliki konfiguracyjne i ustawienia z notatek i zwraca `config_items` (metryczkę) - znaczenie po jednym zdaniu na klucz, z oznaczeniem „wywnioskowane”, gdy nie wynika wprost z kodu lub komentarza; pisarz zakładki Błędy - komentarze do „Ryzykownych miejsc” z trudnych miejsc w notatkach; prompty `writer/*`.
- **Sprawdzamy:** zakładki „Przegląd i uruchomienie” i „Ścieżki procesu” z istniejących notatek i `flow.json` - wydruk JSON i podgląd HTML; ścieżki odwołują się do istniejących klocków; każdy klucz metryczki ma znaczenie.

**Krok 56. Graf: równolegli pisarze + składanie treści**
- **Funkcja:** wszystkie pozostałe zakładki pisane naraz, potem złożone w jedną treść ze sprawdzeniem kompletności.
- **Robimy:** drugi `Send` (po jednym pisarzu na zakładkę poza Przepływem), zapis `tabs/<zakładka>.json`; węzeł `assemble` (kod): `GuideContent` z diagramem i blokami skanera, braki wymaganych sekcji, odwołania do nieistniejących klocków, wpisy metryczki bez znaczenia, `guide_content.json`.
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
