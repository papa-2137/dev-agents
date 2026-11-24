# Wiadomość startowa dla inżyniera dev-agents

Cześć. Budujemy razem **dev-agents**: narzędzie, które na podstawie kodu robota RPA (na razie w Pythonie) tworzy przewodnik dla dewelopera w postaci jednego pliku HTML. Ty piszesz kod, ja zatwierdzam każdy krok i wykonuję testy ręczne. Ta wiadomość mówi, od czego zacząć i jak pracujemy. Szczegóły są w plikach, do których odsyłam - one są ważniejsze niż ta wiadomość.

## 1. Przeczytaj najpierw, w tej kolejności

1. **`AGENTS.md`** (katalog główny repo) - zasady pracy i kodu. Obowiązują od pierwszej linii. Szczególnie: sposób pracy (pkt 1-8), reguły kodu 1-14, styl kodu 1-8 i lista „Nie proponuj bez wyraźnej prośby”.
2. **`dev_log/plan.md`** - po co jest narzędzie: wymagania produktu W1-W8 (sekcja 1), ustalenia projektowe (sekcja 2), docelowa struktura (sekcja 3), szkic `config.yaml` (sekcja 6), otwarte sprawy (sekcja 7).
3. **`dev_log/plan_kroki.md`** - 68 kroków w fazach A-H. Każdy krok ma **Funkcję** (co i po co), **Robimy** i **Sprawdzamy**.
4. **`dev_log/raport_wykonania.md`** - dziennik prac. Na razie pusty; uzupełniasz go po każdym kroku.
5. **`dev_log/guide_mockup.html`** - makieta przewodnika. Na razie wystarczy, że wiesz, że istnieje; będzie wzorcem wyglądu w fazie D (od kroku 30).

Po przeczytaniu napisz mi w kilku zdaniach, jak rozumiesz cel narzędzia i sposób pracy, oraz zadaj pytania, jeśli coś jest niejasne albo sprzeczne. Dopiero potem przejdziemy do kroku 1.

## 2. Gdzie co leży

| Co | Ścieżka |
|---|---|
| Repo dev-agents (tu pracujesz) | `C:\Users\jankiwoj_box\Documents\projects\claude\development\dev-agents` |
| doc-agents (źródło modułów do przeniesienia, tylko do odczytu) | `C:\Users\jankiwoj_box\Documents\projects\claude\development\doc-agents` |
| Robot testowy 01 (Roboforge, tylko do odczytu) | `C:\Users\jankiwoj_box\Documents\projects\claude\tests\01_rpa_challange_roboforge` |
| Robot testowy 02 (tworzysz go w kroku 9) | `C:\Users\jankiwoj_box\Documents\projects\claude\tests\02_robot_bez_frameworku` |

Stan repo na start: są `.git` (bez commitów), `venv` z Pythonem 3.14, `AGENTS.md` i `dev_log/`. Nic więcej - kod zaczynamy od kroku 1.

Środowisko: Windows, PowerShell, Python 3.14, venv w katalogu `venv` (bez kropki). Wszystko uruchamiamy z katalogu głównego repo; moduły przez `python -m ...`.

## 3. Jak przebiega każdy krok

1. **Propozycja.** Napisz, który krok robimy, jaką funkcję realizuje i po co, które pliki powstaną lub się zmienią. Jeśli coś da się zrobić na kilka sposobów - przedstaw warianty z zaletami i wadami (z punktu widzenia czytelności i utrzymania) i wskaż, który polecasz. **Czekaj na moją zgodę.**
2. **Wykonanie.** Tylko to, co obejmuje krok. Żadnych plików, abstrakcji ani bibliotek „na zapas” z kolejnych kroków.
3. **Test.** Podaj dokładne polecenia PowerShell do testu ręcznego i oczekiwany wynik. Testy uruchamiam ja. **Czekaj na moje potwierdzenie.**
4. **Dziennik.** Po potwierdzeniu uzupełnij `dev_log/raport_wykonania.md` według wzoru w pliku: co zrobione, wynik testu, odstępstwa od planu z uzasadnieniem (tabela decyzji na końcu). Zaktualizuj status fazy i kamienia milowego w podsumowaniu.
5. **Commit robię ja.** Nie wykonuj żadnych operacji git (także `git add`). Na końcu kroku możesz zaproponować treść commita.

Jeden krok = jedna rzecz = jeden test = jeden commit. Nie łącz kroków, nawet jeśli wydają się małe.

## 4. Kiedy się zatrzymać i zapytać

- Plan wydaje się błędny, niewykonalny albo sprzeczny z `AGENTS.md` - zaproponuj zmianę z uzasadnieniem i czekaj. **Plan (`plan.md`, `plan_kroki.md`) zmieniamy tylko po mojej decyzji**; nie zmieniaj kierunku po cichu.
- Krok wymaga biblioteki, pliku albo uprawnienia, których plan nie przewiduje.
- Test nie przechodzi, a przyczyna nie jest oczywista - opisz, co sprawdziłeś, zamiast próbować w kółko.
- Masz zapisać cokolwiek poza repo dev-agents i poza katalogiem robota 02 (w krokach z testami na robotach - tylko w ich `dev_agents_doc/`, zgodnie z regułą 12).

## 5. Bezpieczeństwo - bez wyjątków

- Klucze i adresy endpointów modelu są w zmiennych środowiskowych użytkownika (na Kwadracie `LLM_API_KEY`, `LLM_BASE_URL`). Config trzyma **wyłącznie nazwy zmiennych**, nigdy wartości. Odczyt zmiennych tylko przez `os`.
- Pliki sekretów (`*.pfx`, `*.p12`, `*.pem`, `*.key`, `*.crt`, `.env*`) trafiają do modelu wyłącznie jako metadane, nigdy jako treść. Wartości haseł w plikach konfiguracyjnych i w stałych w kodzie robota - maskowane (`***`).
- W analizowanym projekcie narzędzie pisze wyłącznie do `dev_agents_doc/` i czyści tylko katalog ze znacznikiem `.dev_agents_output`.
- Nie otwieraj, nie wypisuj i nie kopiuj treści `certs/client.pfx` robota 01 - jest tam celowo jako test wykrywania sekretów.

## 6. Na co szczególnie uważać

- **Krok 9 (robot 02) ma być naprawdę nieuporządkowany**: bez frameworku, start z `run.bat`, ustawienia w stałych, jedna funkcja `run()` na kilkaset linii z warunkami zagnieżdżonymi na 4-5 poziomów, bez docstringów. Nie poprawiaj go „odruchowo” - jego brzydota jest materiałem testowym. To jedyne miejsce, gdzie reguły stylu z `AGENTS.md` **nie obowiązują** (to nie jest kod narzędzia). Robot musi jednak naprawdę działać na lokalnych plikach.
- **Kroki „Przenieś z doc-agents”** - przenosisz zachowanie, ale kod dostosowujesz do reguł z `AGENTS.md` (podłogi, aliasy importów, docstringi z `Po co:` i `Uwaga:`, testy pod `if __name__ == "__main__":`, `os.path` zamiast `pathlib`). Nie kopiuj 1:1.
- **Przed krokiem 30 zatrzymaj się.** Faza D odtwarza wygląd z makiety `dev_log/guide_mockup.html`, która musi być wcześniej zaktualizowana i zaakceptowana przeze mnie (otwarta sprawa w `plan.md`, sekcja 7).
- **Krok 51 (analiza długich funkcji po kawałkach) jest najbardziej ryzykowny.** Jeśli złożona notatka gubi gałęzie z szkieletu sterowania, zgłoś to, zamiast iść dalej.
- **Pole, którego nie da się wypełnić z kodu, zostaje puste albo „nie wynika z kodu”.** Dotyczy schematów, promptów i recenzenta. Zmyślona treść jest gorsza niż brak treści.
- Przy pierwszym użyciu każdego mechanizmu LangGraph (stan, reducery, `Send`, krawędzie warunkowe) wyjaśnij mi krótko, jak działa.

## 7. Komunikacja

- Po polsku.
- Krótko i konkretnie: co zrobione, co sprawdzić, na co czekasz.
- W kodzie i plikach repo zwykły myślnik `-`, bez półpauz i pauz.

Zaczynamy od punktu 1: przeczytaj pliki i napisz, jak rozumiesz zadanie.
