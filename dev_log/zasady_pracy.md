> Kopia `AGENTS.md` z katalogu głównego repozytorium, do wglądu. **Obowiązuje `AGENTS.md`** - przy każdej zmianie zasad zaktualizuj oba pliki.

# AGENTS.md - zasady pracy w repozytorium dev-agents

Instrukcje dla modeli i asystentów AI, które piszą kod w tym repozytorium. Przeczytaj przed pierwszą zmianą.

## Projekt w skrócie

Bliźniak projektu doc-agents, pisany od zera: zespół agentów (LangGraph), który na podstawie kodu projektów RPA (głównie robotów w Pythonie) tworzy **przewodnik dla dewelopera**. Zakres i ustalenia: `dev_log/plan.md`, kroki: `dev_log/plan_kroki.md`; tu są zasady obowiązujące od pierwszej linii kodu. Zasady przeniesione z doc-agents są sprawdzone w praktyce; zasady dodane 2026-11-24 wynikają z doświadczeń z tamtym projektem.

Gryps: **„towar”** = ten projekt (dev-agents), **„Kwadrat”** = miejsce, w którym towar powstaje, **„miasto”** = praca (środowisko firmowe, w którym towar będzie używany). Towar powstaje na Kwadracie i jest wypychany na miasto.

### Konwencje struktury (przeniesione z doc-agents)

| Miejsce | Zawartość |
|---|---|
| `main.py` | argumenty → config → graf → uruchomienie |
| `config.yaml` | jedyny plik konfiguracyjny (sekcje) |
| `dev_agents/` | rdzeń: config, fabryka modeli, prompty, baza wiedzy, schematy, stan, graf, skaner, zapis wyników |
| `dev_agents/agents/` | agenci, każdy w osobnym pliku |
| `dev_agents/technologies/` | obsługa technologii analizowanych projektów (Python; UiPath, Robot Framework i NICE tylko jako puste klasy z kontraktem) |
| `prompts/<agent>/` | `system.md` + `user.md` |
| `knowledge_base/knowledge/` | baza wiedzy (Markdown) wybierana przez agentów; spis w `index.md` - zwykły tekst: nazwa pliku, „Kiedy użyć:”, „Tagi:”, wpisy oddzielone pustą linią |
| `knowledge_base/templates/` | szablony dokumentu wynikowego, wczytywane zawsze przez kod |
| `scripts/` | narzędzia diagnostyczne (np. `probe_llm.py`) |
| `dev_log/` | `plan.md` (wymagania i ustalenia), `plan_kroki.md` (kroki planu), `raport_wykonania.md` (notatki inżyniera), `zasady_pracy.md` (kopia tego pliku do wglądu - obowiązuje `AGENTS.md`) |
| `<projekt analizowany>/dev_agents_doc/` | wyniki ostatniego uruchomienia - zawsze w katalogu głównym **analizowanego projektu** (nie w repo narzędzia i nie w configu), czyszczony przy każdym starcie; szczegóły w regule 12 |

## Sposób pracy

1. **Jeden krok = jedna rzecz = jeden test ręczny = jeden commit.** Nie przechodź dalej, dopóki test bieżącego kroku nie działa.
2. **Przed każdym krokiem: co, po co i zgoda użytkownika.** Każdy krok planu ma krótki opis funkcjonalności, którą realizuje, i celu. Zanim zaczniesz krok, napisz, co w nim zrobimy, jaką funkcjonalność realizuje, po co i które pliki się zmienią - i poczekaj na zatwierdzenie. Bez zgody nie pisz kodu.
   Gdy coś da się zrobić na kilka sposobów, przedstaw warianty z zaletami i wadami każdego - zawsze z punktu widzenia utrzymywalności i czytelności kodu - i wskaż, który polecasz i dlaczego. Decyzję podejmuje użytkownik.
3. Po zakończeniu kroku podaj dokładne polecenia PowerShell do ręcznego testu i oczekiwany wynik. Potem zatrzymaj się i poczekaj na potwierdzenie.
4. Nie dodawaj plików, abstrakcji ani zależności spoza bieżącego kroku. Jeśli coś wydaje się potrzebne - zaproponuj i zapytaj.
5. Jeśli plan wymaga zmiany, zaproponuj ją z uzasadnieniem i poczekaj na decyzję. Nie zmieniaj kierunku po cichu.
6. Git (commit, push) obsługuje użytkownik. Nie wykonuj operacji git.
7. **Dziennik prac:** po każdym kroku uzupełnij `dev_log/raport_wykonania.md` - co zrobione, wynik testu, odstępstwa od planu z uzasadnieniem (tabela decyzji na końcu raportu). Gdy raport się rozrośnie, zamknięte fazy przenieś do osobnych plików w `dev_log/`. Plan (`dev_log/plan.md`, `dev_log/plan_kroki.md`) zmieniaj tylko po decyzji użytkownika.
8. Komunikacja z użytkownikiem po polsku. Przy pierwszym użyciu mechanizmu LangGraph (stan, reducery, `Send`, krawędzie warunkowe, checkpointer) wyjaśnij, jak działa.

## Środowisko

- **Python 3.14.** Zakaz składni spoza 3.14 (np. leniwe importy, `frozendict`, `sentinel` z 3.15).
- Środowisko wirtualne w katalogu **`venv`** (bez kropki): `py -V:3.14 -m venv venv`.
- Windows, PowerShell. Wszystko uruchamiamy z katalogu głównego repo.
- Zależności dopisujemy ręcznie do `requirements.txt`: tylko bezpośrednie, bez `pip freeze`, każda dochodzi w kroku, który jej potrzebuje.
- Pliki tekstowe w repo zapisujemy w UTF-8.

## Konfiguracja

Jeden `config.yaml` w katalogu głównym, podzielony na sekcje. **Każda wartość, która na mieście jest inna, ma pod spodem zakomentowaną linię z wartością na miasto** - przejście Kwadrat → miasto to zakomentowanie jednej linii i odkomentowanie drugiej:

```yaml
llm:
  profiles:
    small:
      provider: openai_compatible
      model: claude-haiku-5-5
      # model: azure/genai4all/gpt-5-no-filter
      api_key_env: LLM_API_KEY
      # api_key_env: BAZOOKA_KEY
      base_url_env: LLM_BASE_URL
      # base_url_env: BAZOOKA_URL
      structured_output_method: json_schema
      params: { max_tokens: 16000 }
```

- Alternatywa zawsze w osobnej linii, nigdy w komentarzu za wartością.
- Config trzyma wyłącznie *nazwy* zmiennych środowiskowych (`api_key_env`, `base_url_env`) i nazwy modeli, nigdy wartości kluczy.
- **Domyślna metoda structured output: `json_schema`** we wszystkich profilach. Metoda jest ustawiana per profil; `function_calling` i `json_mode` zostają obsługiwane jako alternatywy.
- Parametry modelu (`params`) są opcjonalne - kod przekazuje tylko te, które są podane w profilu (aktualne modele Claude odrzucają np. `temperature`).
- Ustawienia, które zespół może chcieć zmieniać (np. wzorce ról plików, wzorce sekretów, limity), trzymamy w configu, a nie w kodzie.
- Na mieście pierwszą rzeczą po przerzuceniu kodu jest `python -m scripts.probe_llm` na profilu miejskim.

## Reguły kodu

**Zasada nadrzędna: prostota zamiast formalizmów.** Nie stosuj przesadnych formalizmów tam, gdzie nie chronią przed poważnym ryzykiem. Wybieraj konstrukcje czytelne dla każdego programisty Pythona: zwykłe funkcje, pętle, `if`, jawne przypisania. Modele Pydantic - tylko klasy z typami pól (dla podpowiedzi edytora i zamiany danych na obiekty); sprawdzenia piszemy zwykłym kodem zamiast walidatorów, dekoratorów i opcji konfiguracji modelu (`model_validator`, `field_validator`, `ConfigDict`, `extra="forbid"`, `Literal`, `Field(...)` itp.). Formalizm jest uzasadniony tylko wtedy, gdy bez niego realnie grozi np. wyciek sekretu, utrata danych albo kosztowny, trudny do wykrycia błąd - wtedy zaproponuj go i krótko uzasadnij. Ustalony wyjątek: w schematach odpowiedzi modelu (structured output) pola mają `Field(description="...")` - model widzi tylko schemat JSON, a opis jedzie razem z polem i nie rozjedzie się z kodem.

1. **Moduły uruchamiamy przez `-m`** z katalogu głównego, np. `python -m dev_agents.config`. Wtedy importy modułów projektu działają bez instalowania pakietu.
2. **Agent = czysta funkcja + cienki węzeł.** Logikę da się wywołać bez grafu; węzeł grafu tylko ją opakowuje:
   ```python
   def plan(                                  # logika
       project_map: _schemas.ProjectMap,
       ctx: _context.RunContext,
   ) -> _schemas.Plan: ...

   def run(                                   # węzeł
       state: _state.DocState,
       runtime: Runtime[_context.RunContext],
   ) -> dict:
       return {"plan": plan(state["project_map"], runtime.context)}
   ```
3. **Pliki czytamy zawsze z `encoding="utf-8"`**; obce pliki (analizowane projekty) dodatkowo z `errors="replace"` i z rozpoznawaniem BOM (UTF-8 i UTF-16 - np. `requirements.txt` z `pip freeze` w Windows PowerShell 5.1 jest w UTF-16). W kodzie i plikach repo używamy zwykłego myślnika `-` (bez typograficznych półpauz i pauz).
4. **Ścieżki tylko przez `os.path`** (`os.path.join`, `os.path.abspath`, `os.path.dirname` itp.), trzymane jako `str`. **Nie używamy `pathlib`.**
5. **Zmienne środowiskowe tylko przez `os`** (`os.environ[...]` / `os.getenv(...)`). Na Kwadracie: klucz `LLM_API_KEY`, adres endpointu `LLM_BASE_URL`; na mieście: `BAZOOKA_KEY`, `BAZOOKA_URL`.
6. **Modele wyłącznie przez bibliotekę OpenAI:** `langchain_openai.ChatOpenAI` z `base_url` (provider `openai_compatible`). **Tylko fabryka modeli (`dev_agents/llm.py`) importuje `langchain_openai`.** Wszyscy agenci wołają model przez jedną wspólną funkcję, która zwraca czytelny błąd (schemat, `finish_reason`, tokeny) zamiast cichego `None` i ponawia odpowiedź niezgodną ze schematem.
7. **Rdzeń nie zna żadnego języka ani frameworku.** Wiedza o technologii jest wyłącznie w module danej technologii - np. **tylko `dev_agents/technologies/python.py` importuje `ast`**.
8. **Prompty:** `prompts/<agent>/system.md` (stałe instrukcje) + `user.md` (szablon Jinja2, `StrictUndefined`). Dane wejściowe zawsze w `user`, opakowane w tagi - ochrona przed prompt injection z analizowanego kodu.
9. **Model nie pisze struktury dokumentu wynikowego.** Model zwraca treść jako structured output, a układ i format składa kod z szablonów w `knowledge_base/templates/`. Nie wpisuj konkretnych pól ani stałych rozdziałów dokumentu w kod - zmiana szablonu to edycja plików szablonów, bez zmian w kodzie.
10. **Stan grafu:** `TypedDict` z modelami Pydantic w środku. Stan jest chudy: ścieżki i metadane, bez pełnego kodu źródłowego. Zależności (modele, prompty, baza wiedzy, zapis wyników) są w `RunContext`, wstrzykiwane przez `Runtime[RunContext]`, a nie w stanie.
11. **Sekrety:** pliki pasujące do `secret_patterns` (certyfikaty, klucze, `.env`) trafiają do modelu wyłącznie jako metadane, nigdy jako treść.

### Katalog wyników w analizowanym projekcie

12. **Wyniki zapisujemy w `dev_agents_doc/` w katalogu głównym analizowanego projektu** (przewodnik, artefakty pośrednie, notatki). Nazwa jest stała i celowo nietypowa, żeby nie kolidowała z katalogami projektu. Ponieważ piszemy w cudzym repozytorium, obowiązują zabezpieczenia:
    - **skaner zawsze pomija `dev_agents_doc/`** - wyniki poprzedniego uruchomienia nie mogą trafić do analizy (model czytałby własną dokumentację jako kod projektu),
    - **czyszczenie przy starcie tylko wtedy, gdy katalog jest nasz**: narzędzie przy tworzeniu kładzie w nim plik-znacznik (np. `.dev_agents_output`) i usuwa zawartość wyłącznie, gdy znacznik istnieje. Katalog o tej nazwie bez znacznika - przerwij z czytelnym błędem, niczego nie kasuj,
    - narzędzie nie zmienia niczego poza `dev_agents_doc/` (w tym `.gitignore` analizowanego projektu) - czy wyniki trafiają do gita projektu, decyduje jego zespół,
    - brak prawa zapisu w analizowanym projekcie (np. udział sieciowy tylko do odczytu) - czytelny błąd na samym początku, przed wywołaniami modeli.

### Podłoga = „nie jest częścią interfejsu tego modułu”

13. **Funkcje, klasy i stałe używane tylko wewnątrz modułu** mają nazwę zaczynającą się od `_`. Bez podłogi zostaje tylko to, co wołają inne moduły. Gdy funkcja z podłogą okazuje się potrzebna w innym module, przemianuj ją (usuń podłogę) - to świadoma zmiana interfejsu.
14. **Moduły własnego projektu importujemy w całości, z aliasem z podłogą**, i wołamy przez nazwę modułu:
    ```python
    import dev_agents.data_operations as _data_operations

    rows = _data_operations.get_data(path)
    ```
    - Nie importujemy pojedynczych nazw z modułów projektu (`from dev_agents.data_operations import get_data`).
    - Adnotacje typów też przez alias: `def f(project_map: _schemas.ProjectMap)`.
    - **Tylko moduły własnego projektu.** Biblioteka standardowa i biblioteki zewnętrzne importujemy normalnie (`import os`, `import yaml`, `from langchain_openai import ChatOpenAI`).

## Styl kodu

1. **Oddzielaj logikę od wyświetlania.** Funkcje liczące i testujące zwracają wartości i niczego nie wypisują. Wypisywanie (`print`) jest wyłącznie w osobnych funkcjach wyświetlających (np. `_print_results`), które dostają gotowe dane i tylko je formatują.
2. **`main()` jako spis treści.** `main()` wywołuje kolejne kroki po kolei (argumenty → dane → logika → wyświetlenie) i nie zawiera szczegółów ani długich bloków `print`. `main()` istnieje tylko wtedy, gdy moduł jest uruchamiany w programie i z całego modułu z zewnątrz wołana jest wyłącznie ta funkcja, a pozostałe funkcje modułu służą tylko jej (np. `main.py`, skrypty w `scripts/`). Moduł, którego funkcje woła reszta narzędzia (np. skaner, prompty), nie ma `main()`. Funkcja testowa `manual_test()` też jest spisem treści.
3. **Plik podzielony na sekcje** z komentarzami-nagłówkami, np. `# --- Logika ---`, `# --- Wyświetlanie ---`, `# --- Uruchomienie ---`, a w modułach `# --- Test ręczny ---` na końcu, w kolejności od elementów podstawowych do `main()` / bloku testowego.
4. **Wynik przed `return` przypisuj do zmiennej o opisowej nazwie**, zamiast zwracać długie wyrażenie lub f-string wprost:
   ```python
   opis_danych_ze_schematu = f"{capital.capital}, {capital.population_millions} mln"
   return opis_danych_ze_schematu
   ```
5. **Bez stałych na poziomie modułu, jeśli używa ich tylko jedna funkcja.** Taka wartość (słownik, domyślna ścieżka itp.) jest zmienną lokalną tej funkcji - nie da się jej wtedy przypadkiem zmienić ani zaimportować z zewnątrz.
6. **Obszerny docstring modułu** na początku pliku, dla innego programisty:
   - co moduł robi i **dlaczego istnieje** (jaki problem rozwiązuje w narzędziu),
   - **jaką ma rolę**: samodzielny skrypt (nikt go nie importuje) albo moduł używany przez inne części narzędzia - opisana **na poziomie warstwy** (np. „używany przez agentów”), **bez listy konkretnych wywołujących**, bo taka lista się starzeje,
   - jak uruchomić test ręczny i jak czytać wynik.
7. **Docstring w każdej funkcji, klasie i metodzie** (także pomocniczej, `main()` i `manual_test()`), w stałym formacie:
   - **pierwszy akapit - CO robi**: jedno-dwa zdania, bez powtarzania nazwy (ten akapit trafia też do szkieletu pliku, więc ma być samodzielnie zrozumiały),
   - akapit zaczynający się od **`Po co:`** - jaką rolę pełni w narzędziu i jaki problem rozwiązuje,
   - opcjonalnie akapit zaczynający się od **`Uwaga:`** - niuans, który może wprowadzić w błąd przyszłego dewelopera-utrzymaniowca (np. „może zgłaszać ostrzeżenie przy ścieżkach Windows z polskimi znakami”, „przy błędzie składni zwraca pusty tekst zamiast rzucać wyjątek”),
   - dalej, gdy potrzebne: argumenty i wynik, jeśli nie są oczywiste z nazw i typów.
   **Nie piszemy w docstringach, gdzie funkcja jest wołana.**
   ```python
   def _is_project_module(
       root: str,
       module: str,
   ) -> bool:
       """Sprawdza, czy moduł o podanej pełnej nazwie (np. 'src.report') istnieje w katalogu projektu jako plik .py lub folder.

       Po co: od tego zależy, czy import trafi do grupy modułów projektu, czy bibliotek.

       Uwaga: nie rozpoznaje modułów instalowanych w trybie edytowalnym (pip install -e) -
       takie moduły trafiają do bibliotek zewnętrznych.
       """
   ```
   Cel: każdy kawałek kodu ma być zrozumiały dla osoby, która widzi go pierwszy raz, bez szukania kontekstu w innych plikach.
8. **Testy ręczne wyłącznie pod `if __name__ == "__main__":`** na końcu modułu. Dopiero wewnątrz tego bloku są: definicje funkcji testujących, dane pomocnicze, importy potrzebne tylko do testu i wywołanie testu. Przy imporcie modułu kod testowy nie istnieje. Test wywołuje kod i wypisuje wynik (`print`) do obejrzenia - to test ręczny, nie automatyczny.
   ```python
   # --- Test ręczny ---

   if __name__ == "__main__":
       import dev_agents.config as _config

       def manual_test():
           """Wczytuje config i wypisuje mapę projektu robota testowego.

           Po co: szybki podgląd wyniku skanera bez uruchamiania całego grafu.
           """
           app_config = _config.load_config("config.yaml")
           project_map = build_project_map(app_config, r"C:\...\robot")
           print(project_map.model_dump_json(indent=2))

       manual_test()
   ```
   - Funkcja testowa nazywa się `manual_test()` i nie ma podłogi (i tak nie da się jej zaimportować). Każdy moduł powinien taką mieć.
   - Wyjątki zgłasza inżynier: `__init__.py` i pliki bez logiki, w których test byłby sztuczny. Moduł z `main()` nie potrzebuje osobnego testu - jego uruchomienie jest testem.
   - **Kod w bloku testowym nie importuje własnego modułu.** Uruchomiony moduł działa jako `__main__`; ponowny import pod prawdziwą nazwą tworzy drugą kopię modułu, a klasy z obu kopii są dla Pythona różne (np. `isinstance` daje `False`).
9. **Każdy parametr definicji funkcji w osobnej linii** - także wtedy, gdy parametr jest jeden. Po każdym parametrze przecinek (także po ostatnim), nawias zamykający z typem wyniku w osobnej linii:
   ```python
   def invoke_structured(
       model: BaseChatModel,
       schema: type[pydantic.BaseModel],
       method: str,
       messages: list[BaseMessage],
       attempts: int = 2,
   ) -> pydantic.BaseModel:
   ```
   - Dotyczy funkcji, metod (`self` i `cls` też w osobnej linii) i funkcji w bloku testowym. Funkcja bez parametrów zostaje w jednej linii: `def main() -> None:`.
   - Dotyczy tylko definicji - wywołania funkcji piszemy normalnie.
   - Po co: sygnatura czyta się jak lista, każdy parametr ma miejsce na adnotację typu i wartość domyślną, a dodanie lub usunięcie parametru zmienia w diffie jedną linię.

## Nie proponuj bez wyraźnej prośby

- Rezygnacji z LangGraph na rzecz własnego pipeline'u.
- `pathlib` - ścieżki obsługujemy przez `os.path`.
- Walidatorów i dekoratorów Pydantic, `Literal`, `ConfigDict` itp. „dla porządku” - patrz zasada nadrzędna w regułach kodu.
- Wielu plików konfiguracyjnych, plików `.env`, `python-dotenv` ani innych bibliotek do zmiennych środowiskowych.
- Natywnych SDK dostawców modeli (`anthropic`, `langchain-anthropic` itp.) - modele tylko przez bibliotekę OpenAI.
- `.venv` z kropką.
- Testów automatycznych (pytest) przed działającym MVP.
- `src/` layoutu, `pyproject.toml`, instalowania pakietu (`pip install -e .`).
- Podgrafów, pętli ReAct i tool callingu analityka w MVP.
- Wektorowej bazy danych ani embeddingów dla bazy wiedzy.
- Całego stanu jako modelu Pydantic.
- Instalowania bibliotek „na zapas”.
- Generowania przez model struktury dokumentu wynikowego (HTML, układ Markdowna) - model zwraca treść, układ składa kod z szablonu.
- Implementacji UiPath, Robot Framework ani NICE - `technologies/uipath.py`, `robotframework.py` i `nice.py` zostają pustymi klasami z opisem kontraktu; implementacje powstaną osobno na podstawie kontraktu z `technologies/base.py`.
