# Dev-Agents: plan wytwarzania

Zespół agentów (LangGraph), który na podstawie kodu projektu RPA (głównie robota w Pythonie) tworzy **przewodnik dla dewelopera** w postaci jednego, samowystarczalnego pliku HTML. Wzorem stylu jest przewodnik `docs/doc-agents-dokumentacja.html` z projektu doc-agents, a wzorem układu - makieta `dev_log/guide_mockup.html` (otwórz w przeglądarce).

Projekt jest **bliźniakiem doc-agents pisanym od zera**: sprawdzone moduły przenosimy krok po kroku i dostosowujemy do nowych reguł kodu, resztę projektujemy na nowo. Zasady pracy i kodu: `AGENTS.md` w katalogu głównym (kopia: `dev_log/zasady_pracy.md`). Kroki: `dev_log/plan_kroki.md`. Notatki inżyniera: `dev_log/raport_wykonania.md`.

Gryps: **„towar”** = ten projekt (dev-agents), **„Kwadrat”** = miejsce, w którym towar powstaje, **„miasto”** = praca (środowisko firmowe, w którym towar będzie używany). Towar powstaje na Kwadracie i jest wypychany na miasto.

---

## 1. Wymagania produktu (MUST)

Przewodnik musi pozwolić deweloperowi **zainstalować i uruchomić robota, opowiedzieć, co robot robi krok po kroku, wprowadzić typową zmianę i naprawić typową awarię** - bez czytania całego kodu.

| # | Wymaganie | Gdzie w przewodniku | Skąd dane | Kroki planu |
|---|---|---|---|---|
| W1 | **Diagram przepływu (MUST):** start, strzałki, kolejne klocki do końca; decyzje, pętle i ścieżki błędów. Szczegółowość: z samego diagramu da się opowiedzieć na poziomie biznesowo-technicznym, co robot robi po kolei (np. klocek „Wysyłka wiersza do bazy raportowej”, bez wyliczania pól). | zakładka **Przepływ działania**, góra | model (graf kroków) + kod (sprawdzenie spójności i układ) | 32, 36, 42, 53, 54, 58 |
| W2 | **Przegląd i uruchomienie:** wymagania (Python, system, aplikacje, sterowniki), **dostępy sieciowe** (np. „wymaga otwarcia ruchu do…”), konta i nazwy zmiennych z hasłami, **pełne zależności do skopiowania**, instalacja i uruchomienie krok po kroku, jak sprawdzić, że działa. | zakładka **Przegląd i uruchomienie** | skaner (pliki zależności, sekrety jako metadane) + konfiguracja jako tekst + notatki analityków | 23, 24, 34, 35, 49, 55 |
| W3 | **Przepływ krok po kroku pod diagramem:** dla każdego klocka co czyta, co się dzieje (moduł, funkcje w kolejności), co zapisuje lub zwraca; szczegóły także po najechaniu na klocek; kliknięcie przenosi do kroku. | zakładka **Przepływ działania**, dół | te same dane co W1 (jedno źródło - diagram i wiersze nie mogą się rozjechać) | 36, 37 |
| W4 | **Zmiany i rozszerzenia:** przepisy dopasowane do robota (np. nowa strona, nowy format pliku wsadowego, zmiana algorytmu wyszukiwania maila) oraz tabela „gdzie co zmienić”. | zakładka **Zmiany i rozszerzenia** | notatki analityków (punkty rozszerzeń) | 34, 49, 55 |
| W5 | **Jak czytać przewodnik** - na samym początku. | zakładka **Przegląd i uruchomienie**, zaraz po metryczce | kod (karty z opisów zakładek w szablonie) | 33 |
| W6 | **Potencjalne błędy i naprawa:** objaw, przyczyna, gdzie szukać, jak naprawić; znane ograniczenia i pułapki; **ryzykowne miejsca w kodzie** (najdłuższe jednostki - długość liczy kod, komentarz pisze model z notatek). | zakładka **Błędy i naprawa** | notatki analityków (obsługa błędów, pułapki, trudne miejsca) + kod (długość jednostek) | 13, 34, 35, 49, 55 |
| W7 | **Wszystkie ścieżki procesu** jako listy punktowane (główna, alternatywne, błędy), z odwołaniem do numerów klocków diagramu. | zakładka **Ścieżki procesu** | model, na podstawie gotowego diagramu | 34, 55, 56 |
| W8 | **Metryczka robota** (z pliku konfiguracyjnego, a gdy go nie ma albo nie wszystko w nim jest - także ze stałych w kodzie, np. `URL = "https://..."`): plik i miejsce jego wczytania w kodzie, systemy zewnętrzne (adresy), pliki wejściowe i wyjściowe, logi, konta i zmienne środowiskowe, przełączniki; pod spodem pełna konfiguracja: klucz, wartość (hasło wpisane wprost widoczne i oznaczone jako ryzykowne), znaczenie, gdzie używany w kodzie. Ustawienia ze stałych oznaczone „w kodzie” z plikiem i linią. Brak pliku i stałych → jedno zdanie, że robot nie ma konfiguracji. | zakładka **Przegląd i uruchomienie**, zaraz pod tytułem | skaner (pliki konfiguracyjne jako tekst) + model (wpisy, rodzaje, znaczenie, miejsca użycia i ustawienia ze stałych - z notatek analityków) + kod (układ) | 24, 30, 31, 35, 49, 55, 56 |

Dodatkowo (ze wzorca): **Struktura projektu** (drzewo z opisami po najechaniu, graf zależności modułów) i **Dla dewelopera** (architektura w pięciu zdaniach, warstwy, kolejność czytania kodu, konwencje, zależności zewnętrzne).

**Styl:** identyczny ze wzorcem - minimalizm, biały papier, czarne linie, **czerwień tylko dla decyzji, pętli i ostrzeżeń**, szarości dla opisów. Informacje wywnioskowane (niezapisane wprost w kodzie) oznaczone znacznikiem „wywnioskowane”.

---

## 2. Ustalenia (decyzje projektowe)

| Obszar | Decyzja |
|---|---|
| Python | **3.14**, venv w katalogu `venv` (bez kropki). Zależności dopisywane ręcznie do `requirements.txt`, krok po kroku. |
| Orkiestracja | **LangGraph**. Graf: `scan → planner → analyst × N (Send) → flow_writer → writer × pozostałe zakładki (Send) → assemble → reviewer ⇄ writer (tylko zakładki z uwagami) → finalize`. |
| Diagram jako kręgosłup | Graf kroków procesu (`FlowGraph`) powstaje **najpierw**, osobnym wywołaniem; pozostałe zakładki (ścieżki, błędy, zmiany) piszą się na jego podstawie i odwołują do numerów klocków. Spójność diagramu (jeden start, koniec, osiągalność, poprawne krawędzie) sprawdza **kod**, układ (wiersze, kolumny, pętle) też wylicza **kod**. |
| Modele | Biblioteka OpenAI (`ChatOpenAI` z `base_url`), jeden provider `openai_compatible`. Na Kwadracie Claude przez warstwę zgodności OpenAI, na mieście firmowa bramka. **Structured output: `json_schema` od początku.** |
| Konfiguracja | Jeden `config.yaml`. Każda wartość inna na mieście ma pod spodem zakomentowaną linię z wartością miejską (`BAZOOKA_KEY`, `BAZOOKA_URL`, `azure/genai4all/gpt-5-no-filter`). |
| Wynik | `dev_agents_doc/guide.html` w **katalogu głównym analizowanego projektu**, razem z artefaktami pośrednimi. HTML samowystarczalny: CSS i JS w środku, fonty systemowe, bez zasobów z internetu (na mieście sieć może je blokować). |
| Treść a forma | **Model zwraca treść, nie HTML.** Treść przewodnika to structured output z ogólnych bloków; układ HTML składa kod z szablonu Jinja2, wygląd według makiety. |
| Szablon przewodnika | Zakładki i sekcje w `knowledge_base/templates/guide_template.yaml` (id, tytuł, typ bloku, źródło `llm`/`scanner`/`code`, wymagane, instrukcja). Kod zna tylko **typy bloków**, nie konkretne sekcje - nowa sekcja to edycja YAML. |
| Podział pracy kod - agenci | **Kod robi tylko to, co musi być pewne i jest proste dla każdej technologii:** drzewo projektu, role plików, sekrety (tylko metadane), punkty wejścia, **jednostki plików z zakresami linii**, **odwołania między plikami** (graf zależności, kolejność czytania), **pliki zależności, konfiguracyjne i uruchamiające dosłownie**, sprawdzenie spójności i układ diagramu, składanie HTML, karty „jak czytać”. **Rozumienie kodu należy do agentów:** struktura i logika, sposób uruchomienia z `.bat`/`.ps1`, metryczka (znaczenie kluczy, miejsca użycia, ustawienia w stałych), komentarze do ryzykownych miejsc. Metoda technologii, której nie da się napisać w ok. 40 liniach prostego kodu, oznacza wiedzę dla agenta - przewaga prostoty kodu nad oszczędnością tokenów. |
| Konfiguracja robota a sekrety | Pliki konfiguracyjne i uruchamiające robota trafiają do modelu **dosłownie, bez maskowania** - hasło wpisane wprost to błąd dewelopera, który ma wyjść w przewodniku jako ryzykowne miejsce (decyzja użytkownika). Pliki sekretów (certyfikaty, klucze, `.env`) - tylko metadane. |
| Rozszerzalność | Rdzeń (skaner, graf, renderer) **nie zna żadnej technologii**. Technologia z rejestru podaje tylko minimalne fakty: czy projekt jest w tej technologii, pliki źródłowe, punkty wejścia, opcjonalnie jednostki z zakresami linii i odwołania do plików i pakietów. Nowa technologia (UiPath, NICE, Robot Framework) = nowa klasa na kilkadziesiąt linii + plik wiedzy dla agentów + ewentualnie sekcje szablonu z filtrem `technologies`. Nowy framework Pythona (także instalowany jako paczka w venv) = wpis w `scan.frameworks` + plik wiedzy, **bez zmian w kodzie**. W MVP implementujemy tylko Pythona; pozostałe technologie mają puste klasy z opisanym kontraktem. |
| Różne style robotów | Narzędzie nie zakłada porządku w kodzie robota. Robot bez frameworku, uruchamiany z `.bat`/`.ps1`, z ustawieniami w stałych w kodzie albo napisany jako „spaghetti” (funkcje na setki linii, warunki w warunkach) ma być opisany równie rzetelnie. Pomaga temu: **kod z numerami linii** dla analityka, **długość jednostek** liczona przez kod, **analiza długich plików po kawałkach** wzdłuż granic jednostek, **limit szczegółowości diagramu** (szczegóły techniczne schodzą do wierszy „krok po kroku”). Pole, którego nie da się wypełnić z kodu, zostaje uczciwie puste („nie wynika z kodu”) - recenzent nie karze za brak, karze za wymysł. Najdłuższe jednostki i trudne miejsca wskazane przez analityków trafiają do przewodnika jako „ryzykowne miejsca”. |
| Bezpieczeństwo zapisu | W analizowanym projekcie zapisujemy wyłącznie w `dev_agents_doc/`; czyszczenie tylko katalogu ze znacznikiem narzędzia; skaner zawsze pomija `dev_agents_doc/`. |
| Testy | Ręczne, pod `if __name__ == "__main__":` w każdym module. Biblioteka testów poza zakresem MVP. |
| Dobór modeli | Planner i analityk na `small`; autor diagramu, pisarze i recenzent na `medium`. |
| Materiał testowy | Dwa roboty poza repo, w `C:\Users\jankiwoj_box\Documents\projects\claude\tests\`: **`01_rpa_challange_roboforge`** (Roboforge instalowany edytowalnie, `test-venv` w projekcie, `requirements.txt` w UTF-16, fałszywy `certs/client.pfx`) i **`02_robot_bez_frameworku`** (powstaje w kroku 9: bez frameworku, start z `.bat`, ustawienia w stałych, jedna funkcja „spaghetti” na kilkaset linii). Każdy kamień milowy od M3 sprawdzamy na obu. |

### Lekcje z doc-agents, które ukształtowały ten plan

- `function_calling` na małym modelu losowo psuł schemat odpowiedzi - od początku `json_schema` i jedna wspólna funkcja wywołania modelu z czytelnym błędem i ponawianiem.
- Model generujący układ dokumentu był niestabilny - układ zawsze składa kod z szablonu, a wygląd przewodnika zatwierdzamy na danych przykładowych i prawdziwym skanie **przed** podłączeniem modeli (faza D).
- Kilkuminutowy przebieg bez wydruku wyglądał jak zawieszenie - podgląd postępu od pierwszego grafu.
- Recenzent wymagający zera uwag zależał od losu - powtórzenia i sformułowania to sugestie, nie problemy blokujące akceptację.
- Framework zainstalowany edytowalnie nie leży w projekcie ani w venv - rozpoznajemy go także po nazwach importowanych pakietów.
- venv o niestandardowej nazwie rozpoznajemy po `pyvenv.cfg`; obce pliki mogą być w UTF-16 z BOM.

---

## 3. Docelowa struktura projektu

```
dev-agents/
├── main.py                       # argumenty → config → graf → uruchomienie
├── config.yaml                   # jedyny plik konfiguracyjny
├── requirements.txt              # rośnie krok po kroku
├── README.md
├── AGENTS.md                     # zasady pracy i kodu (obowiązujące)
├── .gitignore
│
├── dev_log/
│   ├── plan.md                   # ten plik: wymagania, ustalenia, struktura, config, otwarte sprawy
│   ├── plan_kroki.md             # kroki planu z fazami i kamieniami milowymi
│   ├── raport_wykonania.md       # notatki inżyniera po każdym kroku
│   ├── zasady_pracy.md           # kopia AGENTS.md do wglądu
│   └── guide_mockup.html         # makieta przewodnika - wzorzec wyglądu dla fazy D
│
├── prompts/
│   ├── planner/      system.md, user.md
│   ├── analyst/      system.md, user.md
│   ├── flow_writer/  system.md, user.md
│   ├── writer/       system.md, user.md
│   └── reviewer/     system.md, user.md
│
├── knowledge_base/
│   ├── knowledge/                # wiedza wybierana przez plannera
│   │   ├── index.md
│   │   ├── guide_goals.md        # dla kogo i jak piszemy przewodnik
│   │   ├── technologies/         # po jednym pliku na technologię (python.md; później uipath.md, robotframework.md, nice.md)
│   │   └── frameworks/           # po jednym pliku na framework (roboforge.md; później kolejne)
│   └── templates/                # wczytywane zawsze przez kod
│       ├── guide_template.yaml   # zakładki i sekcje przewodnika
│       ├── guide.html.j2         # układ HTML
│       ├── guide.css
│       └── guide.js              # zakładki, podpowiedzi, kopiowanie, rysowanie diagramów
│
├── scripts/
│   └── probe_llm.py              # diagnostyka endpointu modelu
│
├── dev_agents/
│   ├── __init__.py
│   ├── config.py                 # modele Pydantic configu + load_config()
│   ├── files.py                  # bezpieczny odczyt obcych plików (BOM, UTF-16, cp1250)
│   ├── llm.py                    # fabryka modeli + wspólne wywołanie structured output
│   ├── prompts.py                # renderowanie promptów
│   ├── knowledge.py              # spis i odczyt bazy wiedzy
│   ├── guide_template.py         # wczytanie i sprawdzenie guide_template.yaml
│   ├── schemas.py                # mapa projektu (z grafem zależności), plan, notatka, recenzja
│   ├── guide_content.py          # treść przewodnika i diagram przepływu (wyjście agentów, wejście renderera)
│   ├── scanner.py                # pliki, role, sekrety, frameworki, jednostki i odwołania, zależności, konfiguracja i pliki uruchamiające jako tekst → ProjectMap
│   ├── dependencies.py           # graf zależności modułów i kolejność czytania (bez modelu)
│   ├── flow.py                   # sprawdzenie spójności diagramu i wyliczenie układu (bez modelu)
│   ├── output.py                 # RunStore: dev_agents_doc/ w analizowanym projekcie
│   ├── render.py                 # treść przewodnika → guide.html
│   ├── context.py                # RunContext
│   ├── state.py                  # stan grafu
│   ├── graph.py                  # budowa i uruchomienie grafu, podgląd postępu
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── planner.py
│   │   ├── analyst.py
│   │   ├── flow_writer.py        # autor diagramu przepływu
│   │   ├── writer.py             # pisarz zakładki
│   │   └── reviewer.py
│   └── technologies/
│       ├── __init__.py           # pakiet (bez importów)
│       ├── registry.py           # rejestr technologii: kolejność sprawdzania, detect_technology(), get_technology()
│       ├── base.py               # kontrakt technologii
│       ├── python.py             # detect, is_source, punkty wejścia, jednostki z zakresami linii, odwołania (jedyny moduł z `ast`)
│       ├── robotframework.py     # pusta klasa z opisem kontraktu (.robot + biblioteki .py przez delegację)
│       ├── uipath.py             # pusta klasa z opisem kontraktu (XAML, project.json, Config.xlsx)
│       └── nice.py               # pusta klasa z opisem kontraktu (NICE APA)
│
└── venv/                         # (git-ignored)

<analizowany projekt>/dev_agents_doc/       # wynik ostatniego uruchomienia
    .dev_agents_output                      # znacznik: katalog należy do narzędzia
    project_map.json (z grafem zależności i kolejnością czytania), plan.json, notes/*.json, flow.json,
    tabs/*.json, guide_content.json, review_NN.json, usage.json, guide.html
```

---

## 4. Zasady wykonania planu

1. Każdy krok to **jedna testowalna zmiana**: opis funkcji, „Robimy”, „Sprawdzamy”. Nie przechodzimy dalej, dopóki test kroku nie działa.
2. Kroki **„Przenieś z doc-agents”** to kopiowanie modułu z `development/doc-agents` i dostosowanie go do reguł z `AGENTS.md` (podłogi, aliasy importów, testy pod `if __name__ == "__main__":`, docstring modułu, akapity `Uwaga:`), bez zmiany zachowania - chyba że krok mówi inaczej.
3. Po każdym kroku inżynier uzupełnia `dev_log/raport_wykonania.md`: co zrobione, wynik testu, odstępstwa od planu z uzasadnieniem.
4. Moduły uruchamiamy przez `python -m dev_agents.<moduł>` z katalogu głównego repo.
5. Wygląd i układ przewodnika odtwarzamy z `dev_log/guide_mockup.html` (CSS, struktura HTML, skrypty); zmiany wyglądu względem makiety tylko po decyzji użytkownika.

---

## 5. Plan krok po kroku

Kroki są w osobnym pliku **`dev_log/plan_kroki.md`** (68 kroków w fazach A-H, faza I to rozwój po MVP). Kamienie milowe: **M1** szkielet uruchamia się (krok 5) · **M2** model gotowy (krok 8) · **M3** mapa projektu, konfiguracja i pliki uruchamiające jako tekst oraz graf zależności bez modelu, na obu robotach testowych (krok 29) · **M4** wygląd przewodnika zatwierdzony na danych bez modelu (krok 39) · **M5** pierwszy pełny przewodnik z modelu (krok 59) · **M6** działa na mieście (krok 68).

---

## 6. Docelowy `config.yaml` (szkic)

Krok 4 zaczyna od sekcji `llm` i `paths`. Pozostałe sekcje dochodzą w krokach, które ich potrzebują.

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
    medium:
      provider: openai_compatible
      model: claude-sonnet-5-5
      # model: azure/genai4all/gpt-5-no-filter
      api_key_env: LLM_API_KEY
      # api_key_env: BAZOOKA_KEY
      base_url_env: LLM_BASE_URL
      # base_url_env: BAZOOKA_URL
      structured_output_method: json_schema
      params: { max_tokens: 32000 }
  agents:
    planner: small
    analyst: small
    flow_writer: medium
    writer: medium
    reviewer: medium

paths:
  prompts: prompts
  knowledge_base: knowledge_base
  guide_template: knowledge_base/templates/guide_template.yaml   # od kroku 30

scan:                     # od kroku 18
  ignore: [".git", "__pycache__", ".pytest_cache", ".idea", ".vscode", "node_modules", "venv", ".venv", "*.pyc", "Thumbs.db", "desktop.ini", "~$*"]
  secret_patterns: ["*.pfx", "*.p12", "*.pem", "*.key", "*.crt", ".env*"]
  role_patterns:          # od kroku 19
    dependency: ["requirements*.txt", "pyproject.toml"]   # od kroku 23: przepisywane dosłownie
    config: ["*.yml", "*.yaml", "*.toml", "*.ini", "*.cfg", "config*.json", "settings*.json", "appsettings*.json", "*.config.json"]
    docs: ["*.md", "*.rst", "README*", "*.docx", "*.pdf"]
    data: ["*.csv", "*.txt", "*.json", "*.xlsx", "*.xls", "*.db", "*.sqlite", "*.xml", "*.log"]
    launcher: ["*.bat", "*.cmd", "*.ps1"]
    binary: ["*.png", "*.jpg", "*.ico", "*.exe", "*.dll", "*.zip", "*.whl"]
  frameworks:             # od kroku 21
    roboforge:
      technology: python
      paths: ["roboforge_framework/*"]
      packages: ["roboforge"]
      knowledge: frameworks/roboforge.md
  text_roles: [dependency, config, launcher]  # od kroku 23, role plików przepisywanych dosłownie (TextFile)
  max_text_file_kb: 100    # od kroku 23, większy plik tekstowy - tylko metadane

analysis:                 # od kroku 50
  max_file_size_kb: 100
  max_concurrency: 5
  long_unit_lines: 150    # od kroku 35: jednostka dłuższa trafia do „Ryzykownych miejsc”
  chunk_lines: 250        # od kroku 51: rozmiar kawałka długiego pliku

flow:                     # od kroku 32
  max_nodes: 30
  max_decisions: 8

limits:                   # od kroku 59
  max_review_rounds: 2

pricing:                  # od kroku 61, USD za 1M tokenów
  claude-haiku-5-5:  { input: 0.10, output: 0.50 }
  claude-sonnet-5-5: { input: 2.00, output: 10.00 }
```

---

## 7. Otwarte sprawy

- [x] Akceptacja makiety `dev_log/guide_mockup.html` (zakładki, sekcje, wygląd diagramu) - przed krokiem 30 (2026-11-26; zmiany wyglądu ewentualnie po zobaczeniu prawdziwych przewodników).
- [ ] Język przewodnika (domyślnie polski) - sterowany promptami i bazą wiedzy, nie kodem.
- [ ] Drugi projekt do przebiegu kontrolnego (krok 62).
- [ ] Firmowa bramka: obsługa `json_schema` (krok 66).
- [ ] NICE APA: jakie pliki zawiera projekt (proces, konfiguracja, zależności) - do opisu kontraktu w `technologies/nice.py` (krok 17); bez tego klasa ma tylko ogólny opis.
