# Dev-Agents: raport wykonania

> Postęp względem `dev_log/plan_kroki.md` (kroki) i `dev_log/plan.md` (wymagania i ustalenia). Uzupełniany przez inżyniera po każdym kroku.
> Legenda: ✅ zrobione · 🟡 w toku / częściowo · ⬜ nie zaczęte

## Podsumowanie

| Faza | Status |
|---|---|
| A - Fundament (kroki 1-5) | 🟡 w toku |
| B - Dostęp do modelu (6-8) | ⬜ |
| C - Mapa projektu bez modelu (9-29) | ⬜ |
| D - Szablon przewodnika i HTML bez modelu (30-39) | ⬜ |
| E - Prompty i baza wiedzy (40-42) | ⬜ |
| F - Graf i agenci (43-59) | ⬜ |
| G - Ergonomia (60-63) | ⬜ |
| H - Miasto (64-68) | ⬜ |

Kamienie milowe: M1 (krok 5) ⬜ · M2 (8) ⬜ · M3 (29) ⬜ · M4 (39) ⬜ · M5 (59) ⬜ · M6 (68) ⬜

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
