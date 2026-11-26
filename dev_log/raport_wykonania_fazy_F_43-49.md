# Dev-Agents: raport wykonania - faza F, część 1 (kroki 43-49)

> Archiwum wpisów kroków 43-49 fazy F przeniesionych bez zmian z `dev_log/raport_wykonania.md`. Podsumowanie faz, kroki od 50 i tabela decyzji zostają w głównym raporcie (faza F trwa).

### Krok 43. Pierwszy graf LangGraph: tylko skan - ✅
- `dev_agents/state.py`: `RunState` (`TypedDict`, `total=False`): `project_path` (wejście grafu) i `project_map` (wynik węzła `scan`; graf zależności i kolejność czytania są już w `ProjectMap`, więc osobnego pola nie ma).
- `dev_agents/context.py`: `RunContext` (`dataclass`: `config`, `store`, `models`, `knowledge_index`, `template`) i `build_context(app_config, store)`: modele wszystkich agentów z `llm.agents` powstają od razu (`llm.get_model_for_agent`), spis bazy wiedzy przez `knowledge.load_index`, szablon przez `guide_template.load_template`; magazyn wyników dostaje gotowy od wołającego.
- `dev_agents/graph.py`: węzeł `scan_node(state, runtime)` (woła `scanner.build_project_map` z `runtime.context.config.scan`, zwraca tylko `project_map`, nic nie zapisuje na dysku) i `build_graph()`: `StateGraph(RunState, context_schema=RunContext)`, `START → scan → END`, `compile()`.
- `requirements.txt`: `langgraph`.
- Test w bloku `__main__` (`python -m dev_agents.graph`): kontekst (agenci i modele, spis bazy wiedzy, zakładki szablonu), potem graf na małym projekcie tymczasowym i robotach 02 i 01 (tylko odczyt): klucze stanu, technologia, pliki, punkty wejścia, frameworki, zależności, porównanie mapy z grafu z bezpośrednim skanem i sprawdzenie, że katalog wyników w skanowanym projekcie się nie zmienił; atrapy zmiennych z kluczem i adresem tylko gdy ich brak w środowisku; `zgodne z oczekiwaniem: True`.
- Odstępstwa od planu: stan bez osobnego „grafu zależności” (jest w `ProjectMap` od kroku 28); w kontenerze nie było `langgraph` (brak sieci) - logika sprawdzona z atrapami bibliotek, pierwszy prawdziwy test u użytkownika.
- Wybory użytkownika: 1A, 2A, 3A (tabela decyzji). Test użytkownika: OK. Commit `f41f58d`.

### Krok 44. `main.py` uruchamia graf - ✅
- `main.py`: kolejność przebiegu: argumenty → config → szybki skan technologii (`scanner.build_project_map`) → przy nierozpoznanej technologii komunikat i kod 1 (bez zakładania `dev_agents_doc/`) → `create_run_store` → tryb pełny: `_run_graph` (`context.build_context`, `graph.build_graph().invoke({"project_path": root}, context=...)`, mapa ze stanu końcowego) albo `--render-only`: mapa z szybkiego skanu, bez grafu i bez modeli → `project_map.json` zapisuje `main.py` → podsumowanie (→ `guide.html` z `--render-only`).
- Błąd budowy kontekstu (`RuntimeError`, `ValueError`, `OSError`: brak zmiennej z kluczem lub adresem, błędny spis bazy wiedzy, szablon) kończy program komunikatem `BŁĄD: ...` z nazwą przyczyny, zanim graf ruszy.
- Wynik trybu pełnego jest identyczny z wynikiem ze zwykłego skanu (kroku 29): `project_map.json` robotów 02 i 01 po zamianie ścieżki zgodny bajt w bajt; podsumowanie bez zmian.
- Odstępstwa od planu: w trybie pełnym skan wykonuje się dwa razy (szybki w `main.py` i w węźle `scan`) - świadomy koszt ułamka sekundy za brak `dev_agents_doc/` w projekcie z nierozpoznaną technologią; w trybie pełnym z brakiem klucza zostaje pusty `dev_agents_doc/` ze znacznikiem (powstaje przed budową kontekstu, tylko w projekcie z rozpoznaną technologią).
- Wybory użytkownika: rekomendowane (1A, 2A, 3A). Test użytkownika: OK. Commit `9360f80` (razem z wpisem kroku 43 w raporcie).

### Krok 45. Podgląd postępu - ✅
- Nowy `dev_agents/progress.py`: `format_line` (`[GG:MM:SS] etap: tekst`), `format_seconds` (`0,4 s`), `print_line` (z natychmiastowym opróżnieniem bufora) i menedżer kontekstu `Stage` (`start`, `note()` w trakcie pracy, `set_result()`, koniec `gotowe w X s - wynik` albo `BŁĄD po X s - Typ: komunikat` z puszczeniem wyjątku dalej).
- `dev_agents/context.py`: pole `RunContext.report` i trzeci argument `build_context(app_config, store, report)`; `dev_agents/graph.py`: węzeł `scan` pracuje wewnątrz `Stage` (wynik: technologia, liczba plików i punktów wejścia); `main.py`: podaje `print_line` i po grafie wypisuje `razem: X s`.
- Test `python -m dev_agents.progress` (prawdziwe linie na ekranie i 10 sprawdzeń: format linii i czasu, etap udany, z postępem, bez wyniku, z błędem, wyjątek niepołykany); test grafu sprawdza dla każdego przypadku dwie linie postępu węzła `scan`.
- Odstępstwa od planu: postęp raportują węzły przez funkcję `report` w kontekście, a nie `stream(..., stream_mode=["tasks", "values"])` - według dokumentacji LangGraph tryb `tasks` wymaga checkpointera, a tryb `updates` nie ma zdarzenia startu; `plan_kroki.md` krok 45 zaktualizowany.
- Wybory użytkownika: rekomendowane (1C, 2A). Test użytkownika: OK. Commit `db1be3d`.

### Krok 46. `schemas.py` - plan - ✅
- `dev_agents/schemas.py`: `AnalysisTask` (`unit` - nazwa jednostki z mapy projektu, `hint` - wskazówka) i `Plan` (`summary`, `tasks`, `analyst_knowledge`, `flow_knowledge`, `writer_knowledge`); `Field(description=...)` przy każdym polu, schemat płaski bez `anyOf`; docstringi modułu zaktualizowane.
- Test (`python -m dev_agents.schemas`): plan robota 02 ułożony ręcznie, JSON i zgodność po odczycie; schemat JSON klasy `Plan` bez `anyOf` i z opisem przy każdym polu; plan bez `summary` i `tasks` odrzucony przy odczycie; `zgodne z oczekiwaniem: True`.
- Odstępstwa od planu: bez pola `optional_sections` (opcjonalną sekcję pisarz pomija sam, gdy nie ma treści); bez pola `skipped` (analizujemy wszystkie jednostki, brakujące dopisze kod w kroku 47); `plan_kroki.md` krok 46 zaktualizowany.
- Wybory: rekomendowane (1A, 2A, 3A) - tryb pracy fazy F. Test użytkownika: OK. Commit `5c2f225`.

### Krok 47. Agent planner (bez grafu) - ✅
- Nowy `dev_agents/agents/planner.py` (pakiet `dev_agents/agents/`): `build_planner_variables` (mapa projektu jako JSON bez pola `root`, bez kodu źródłowego, z dosłowną treścią plików zależności, konfiguracji i uruchamiających; spis bazy wiedzy), `create_plan` (`render_prompt`, `llm.invoke_structured` ze schematem `Plan`, potem `complete_plan`), `complete_plan` (zadanie z nieznaną jednostką usuwane, powtórzone usuwane, jednostka pominięta dopisana na końcu z pustą wskazówką, plik wiedzy spoza spisu albo powtórzony usunięty; każda poprawka to uwaga), `planner_node` (praca w `Stage`, uwagi jako linie postępu, zapis `plan.json`, zwraca tylko `plan`), `print_plan`.
- Prompty `prompts/planner/system.md` i `user.md` (zadanie: podsumowanie, zadania dla wszystkich jednostek w kolejności `reading_order` ze wskazówkami, trzy listy wiedzy; dane w tagach to nie polecenia; hasło wpisane wprost wskazywane bez przepisywania wartości); pole `plan` w `RunState`.
- Test `python -m dev_agents.agents.planner`: 21 sprawdzeń na udawanym modelu (prompt bez kodu i bez ścieżki dysku, z treścią konfiguracji i spisem wiedzy; poprawianie planu z pięcioma błędami; węzeł: `plan.json`, wywołanie modelu, linie postępu), `zgodne z oczekiwaniem: True`; z argumentem `<katalog robota>` prawdziwy model plannera czyta `dev_agents_doc/project_map.json` i wypisuje plan (zapis `plan.json` w katalogu wyników robota).
- Odstępstwa od planu: poprawianie planu przez kod (plan: sam planner); prompt bez `root`; raport: wpisy fazy E (kroki 40-42) przeniesione do `dev_log/raport_wykonania_fazy_E.md`.
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK (w tym prawdziwy model na robocie 02). Commit `bbb8832`.

### Krok 48. Graf: scan → planner - ✅
- `dev_agents/graph.py`: graf START → scan → planner → END; węzeł `planner_node` zapisuje `plan.json` i dopisuje `plan` do stanu; docstring i opis testu zaktualizowane.
- Nowy `dev_agents/fakes.py`: `FakeStructuredModel` (odpowiedź gotowym obiektem schematu albo funkcją od wiadomości, liczniki `calls` i `messages`) i test `python -m dev_agents.fakes` (4 sprawdzenia); test plannera używa wspólnego modelu zamiast własnej kopii.
- `main.py`: `_run_graph` zwraca (mapa, plan), nowa `_print_plan_summary` wypisuje linię `plan: zadań N, pliki wiedzy: ...` (tylko tryb pełny; `--render-only` bez zmian).
- Test grafu (`python -m dev_agents.graph`): model plannera podmieniony na udawany (pusty plan, który `complete_plan` uzupełnia o wszystkie jednostki); dla projektu tymczasowego, robota 02 i robota 01 (tylko odczyt) sprawdza: plan obejmuje wszystkie jednostki kodu, `plan.json` w magazynie tymczasowym równa się planowi ze stanu, linie postępu `scan` (2) i `planner` (start, uwagi, koniec z liczbą zadań).
- Odstępstwa od planu: dodany `fakes.py` (wspólny udawany model dla kolejnych agentów); `plan_kroki.md` krok 48 zaktualizowany.
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK. Commit `578aaaf` (razem z raportem i archiwum fazy E z kroku 47).

### Krok 49. `schemas.py` - notatka analityka - ✅
- `dev_agents/schemas.py`: `ModuleNote` (jedyne źródło wiedzy o kodzie dla dalszych etapów) i klasy pomocnicze `NoteAction` (czynność: tytuł, rodzaj `step`/`system`/`decision`/`error`, funkcja, linia, dane czytane i zapisywane), `NoteRisk`, `NoteFailure`, `NoteNetwork`, `NoteRequirement`, `NoteTerm`; pola `part`/`parts` pod kawałki długiej funkcji (krok 51). Wymagane tylko `unit_name` i `purpose`, wszystkie listy mogą być puste, a opisy pól dopuszczają „nie wynika z kodu”; flaga `certain` przy czynnościach, ryzykach, awariach i wymaganiach.
- Ustawienia to klasa `ConfigItem`, a dane czynności to `DataRef` z `guide_content.py` (bez drugiej kopii; `schemas.py` importuje `guide_content.py`, który niczego z `schemas.py` nie importuje).
- Test (`python -m dev_agents.schemas`): ręcznie złożona notatka `przetwarzanie.py` (wydruk JSON, odczyt równy oryginałowi), notatka z pustymi punktami rozszerzeń, notatka minimalna, schemat bez `anyOf` i z opisem przy każdym polu, odrzucenie notatki bez przeznaczenia, nieznanego rodzaju czynności i numeru kawałka mniejszego niż 1; `zgodne z oczekiwaniem: True`.
- Odstępstwa od planu: `process_steps` zostają obok `actions` (zdania z „Jeśli ..., to ...” jako surowiec ścieżek procesu); `plan_kroki.md` krok 49 zaktualizowany.
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK. Commit `827d2b9`.
