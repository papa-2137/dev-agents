# Dev-Agents: raport wykonania, faza F, kroki 50-54 (archiwum)

> Wpisy przeniesione z `dev_log/raport_wykonania.md`.

### Krok 50. Agent analityk (bez grafu) - ✅
- `dev_agents/agents/analyst.py`: `analyze_unit()` czyta kod jednostki z numerami linii, pliki tekstowe robota, fakty ze skanu i wiedzę (technologia, frameworki, pliki plannera), woła model `analyst` i poprawia odpowiedź (`fix_note`: nazwa jednostki z zadania, linia spoza pliku -> 0, każda poprawka jako uwaga); pliki `secret` nigdy nie są czytane, plik większy niż `analysis.max_file_size_kb` (100) - `ValueError`. Nowe: `agents/common.py` (wybór i skład plików wiedzy, numerowanie linii), prompty `analyst/system.md`, `user.md`, `part_flow.md`, `part_details.md`.
- Pierwsze prawdziwe wywołania odrzuciła bramka: 400 `minimum is not supported`, potem `compiled grammar is too large`. Hipoteza o polach opcjonalnych była błędna; `scripts/probe_schema.py` zmierzył limit: **48 pól schematu po rozwinięciu klas** przechodzi, 49 nie; osobno max 16 pól "tekst albo null"; głębokość, enumy, ponowne użycie klasy i pola domyślne nie mają znaczenia (zmierzone na profilu small).
- Rozwiązanie: notatka zwracana w **dwóch odpowiedziach** (`NoteFlow` 22 pola, `NoteDetails` 32 pola), `merge_note()` składa `ModuleNote` (54 pola, nie idzie do modelu); `schemas.count_schema_properties()` i limit testowy `MAX_MODEL_SCHEMA_PROPERTIES` = 40. Test schematów ostrzega, że `GuideBlock` (45) i `GuideTab` (47) przekroczą limit - do odchudzenia przed krokiem 55.
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK (prawdziwy model, `main.py` robota 01). Commit `cc62725`.

### Krok 51. Analityk: długie pliki po kawałkach - ✅
- Nowy `dev_agents/agents/chunks.py` (zwykły kod, własny test): `split_ranges` (cięcie po końcach funkcji i klas z `units()`, bez granicy - w środku z zakładem), `plan_chunks` (krótkie pliki razem, długi plik w kawałkach), `build_previous_summary`, `merge_chunk_notes` (cele połączone, rola z pierwszego niepustego kawałka, listy bez powtórzeń, ustawienia łączą `used_in`). `analyst.analyze_unit` analizuje kawałki po kolei (każdy: dwa wywołania modelu, kod z bezwzględnymi numerami linii, podsumowanie poprzednich kawałków, sekcja `<kawalek>` w `user.md`) i zgłasza postęp "kawałek k/n" przez funkcję `note`. Config: `analysis.chunk_lines` (300) i `chunk_overlap_lines` (10) z walidacją. `common.number_lines` z numeracją od podanej linii, `cut_lines`.
- Poprawka z testu: tytuły czynności w trybie rozkazującym (opis pola `title` w `NoteAction`; poszła w commicie kroku 52).
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK (robot 01 `main.py` jednym kawałkiem, numery linii zgodne z kodem; robot 02 po kawałkach). Commit `eaa1289`.

### Krok 52. Graf: równolegli analitycy - ✅
- Graf: `scan -> planner -> analyst x N -> END`. Krawędź warunkowa `graph.dispatch_analysts` wysyła `Send("analyst", {project_map, plan, task})` na każde zadanie planu; węzeł `analyst_node` (w `agents/analyst.py`) woła `analyze_unit` z `Stage.note`, zapisuje `notes/<jednostka>.json` i zwraca `notes` z jedną notatką. Stan: pola `task` i `notes` (reducer `operator.add`). `analysis.max_concurrency` (4, z walidacją) trafia do `invoke` przez `graph.run_config()`; `main.py` wypisuje liczbę notatek.
- Test grafu na udawanym analitykach: notatek tyle co zadań, każda jednostka raz, `notes/*.json` zgodne ze stanem, start i koniec z czasem każdego analityka (robot 01: 8 równolegle).
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK. Commit `6da5c2b`.

### Krok 53. Agent autor diagramu (bez grafu) - ✅
- Nowy `dev_agents/agents/flow_writer.py`: `write_flow()` składa prompt (podsumowanie plannera, kontekst projektu z kolejnością czytania i powiązaniami plików, notatki w kolejności zadań planu tylko z polami przebiegu `NoteFlow`, wiedza: `diagram_rules.md`, technologia, framework, limity z `flow`), woła model `flow_writer` ze schematem `FlowGraph` i sprawdza `validate_flow`; przy problemach albo ostrzeżeniu o rozmiarze jedno ponowienie z poprzednią wersją i listą uwag, druga wersja wygrywa, chyba że ma więcej problemów. `flow_writer_node()` zapisuje `flow.json` i dopisuje `flow` do stanu. Prompty `prompts/flow_writer/system.md` i `user.md`. `order_notes()`, `format_notes()`.
- Niespójny diagram po ponowieniu nie przerywa przebiegu: jest zapisany z listą problemów jako uwagi (renderer pokaże listę zamiast rysunku). Brak notatek - `ValueError`.
- Test ręczny: offline 18 sprawdzeń na udawanym modelu; z argumentem `<katalog robota>` prawdziwy model na notatkach z `dev_agents_doc/notes/` robota 02, zapis `flow.json` i podgląd w `guide_test.html`. Robot 01 pominięty (notatki z hasłami dosłownie, zapis w jego katalogu niezgodny z zasadą tylko do odczytu).
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK (pełny przebieg `main.py` na robocie 02 z prawdziwym LangGraph i modelami, diagram z notatek). Commit `96984e9`.

### Krok 54. Graf: autor diagramu po analitykach - ✅
- `graph.py`: węzeł `flow_writer` po wszystkich analitykach (krawędź analyst -> flow_writer czeka na komplet notatek), wynik w `state.flow`, zapis `flow.json`. Test grafu z udawanymi modelami planisty, analityka i autora diagramu. `main.py` wypisuje liczbę notatek i podsumowanie diagramu.
- Wybory: rekomendowane (tryb pracy fazy F). Test użytkownika: OK. Commit `603f5f9`.
