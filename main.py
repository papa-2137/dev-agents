"""Punkt wejścia towaru (dev-agents): argumenty -> config -> graf agentów -> zapis w dev_agents_doc/.

Co robi: odczytuje argumenty wiersza poleceń, wczytuje config.yaml i sprawdza szybkim skanem, czy technologia
projektu jest rozpoznana. Potem zakłada magazyn wyników (dev_agents_doc/) i uruchamia graf agentów
(graph.build_graph) z kontekstem (context.build_context: modele, spis bazy wiedzy, szablon). Mapa projektu
(pliki z rolami, punkty wejścia, jednostki kodu z zakresami linii, frameworki, pliki tekstowe, graf zależności
i kolejność czytania) pochodzi z węzła scan grafu; w trakcie pracy węzły wypisują linie postępu z godziną
i czasem (progress.py), po grafie main.py wypisuje "razem: X s", zapisuje mapę jako dev_agents_doc/project_map.json
i wypisuje krótkie podsumowanie, a w trybie pełnym także linię o planie (liczba zadań i pliki wiedzy;
plan zapisuje węzeł planner jako dev_agents_doc/plan.json). Z opcją --render-only graf i modele nie są używane: mapa pochodzi z samego
skanu, a program składa przewodnik bez modelu (sekcje z kodu prawdziwe, sekcje agentów to zaślepki, diagram
przykładowy) - wynik to dev_agents_doc/guide.html, podgląd wyglądu bez wydawania tokenów i bez kluczy.
Kolejne etapy (analitycy, pisarze) dochodzą do grafu, a nie tutaj.

Dlaczego istnieje: jedno polecenie uruchamia całe narzędzie. Domyślny config jest szukany obok main.py,
a nie w bieżącym katalogu, więc program działa tak samo bez względu na to, skąd go uruchomiono
(np. z katalogu analizowanego robota). Nierozpoznana technologia, katalog wyników, którego nie wolno użyć,
albo brak zmiennej środowiskowej z kluczem modelu kończą program czytelnym komunikatem (kod wyjścia 1).
Szybki skan przed grafem sprawia, że dla nierozpoznanej technologii nie powstaje nawet katalog dev_agents_doc/.

Rola: samodzielny skrypt - nikt go nie importuje; jego uruchomienie jest testem ręcznym.

Uruchomienie z katalogu głównego repo:
    python main.py --project <ścieżka do katalogu robota>
    python main.py --project <ścieżka do katalogu robota> --config <ścieżka do config.yaml>
    python main.py --project <ścieżka do katalogu robota> --render-only
        bez grafu i bez kluczy modeli: zapisuje project_map.json i dev_agents_doc/guide.html
        (zaślepki zamiast tekstu agentów)
Tryb pełny wymaga zmiennych środowiskowych z kluczem i adresem modeli (nazwy w config.yaml, sekcja llm).
"""

import argparse
import datetime
import os
import sys
import time

import dev_agents.config as _config
import dev_agents.context as _context
import dev_agents.graph as _graph
import dev_agents.guide_placeholders as _placeholders
import dev_agents.guide_template as _template
import dev_agents.output as _output
import dev_agents.progress as _progress
import dev_agents.render as _render
import dev_agents.scanner as _scanner
import dev_agents.schemas as _schemas


# --- Podsumowanie ---


def _role_summary(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca liczbę plików w każdej roli jako tekst, np. "source: 2, launcher: 2, dependency: 1".

    Po co: jedna linia podsumowania zamiast pełnej listy plików.
    """
    licznik = {}
    for wpis in project_map.files:
        licznik[wpis.role] = licznik.get(wpis.role, 0) + 1
    czesci = []
    for rola, liczba in licznik.items():
        czesci.append(f"{rola}: {liczba}")
    tekst = ", ".join(czesci)
    return tekst


def _longest_unit(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca najdłuższą jednostkę kodu robota jako "plik:nazwa początek-koniec (N linii)" albo "brak".

    Po co: od razu widać największy kawałek kodu - kandydata do "Ryzykownych miejsc".
    """
    opis = "brak"
    najwiecej_linii = 0
    for plik_zrodlowy in project_map.source_files:
        for jednostka in plik_zrodlowy.units:
            linie = jednostka.end_line - jednostka.start_line + 1
            if linie > najwiecej_linii:
                najwiecej_linii = linie
                opis = f"{plik_zrodlowy.path}:{jednostka.name} {jednostka.start_line}-{jednostka.end_line} ({linie} linii)"
    return opis


def _print_header(
    config_path: str,
    app_config: _config.AppConfig,
) -> None:
    """Wypisuje nagłówek: plik configu i agentów z modelem w jednej linii.

    Po co: widać, z jakim configiem i modelami działa przebieg, także po przełączeniu linii na miejskie.
    """
    agenci = []
    for agent_name, profile_name in app_config.llm.agents.items():
        agenci.append(f"{agent_name}={app_config.llm.profiles[profile_name].model}")
    print("dev-agents")
    print(f"  config:  {os.path.abspath(config_path)}")
    print(f"  agenci:  {', '.join(agenci)}")


def _print_scan_summary(
    project_map: _schemas.ProjectMap,
    saved_path: str,
) -> None:
    """Wypisuje podsumowanie mapy projektu i ścieżkę zapisanego project_map.json.

    Po co: widoczny efekt przebiegu bez otwierania JSON-a; tylko formatuje gotowe dane.
    """
    jednostki = 0
    for plik_zrodlowy in project_map.source_files:
        jednostki = jednostki + len(plik_zrodlowy.units)
    pliki_tekstowe = []
    for plik_tekstowy in project_map.text_files:
        pliki_tekstowe.append(f"{plik_tekstowy.path} ({plik_tekstowy.role})")
    print(f"  projekt: {project_map.root}")
    print(f"  technologia: {project_map.technology}, plików: {len(project_map.files)} ({_role_summary(project_map)})")
    print(f"  punkty wejścia: {project_map.entrypoints}")
    print(f"  frameworki: {project_map.frameworks}")
    print(f"  pliki źródłowe robota: {len(project_map.source_files)}, jednostki: {jednostki}")
    print(f"  najdłuższa jednostka: {_longest_unit(project_map)}")
    print(f"  pliki tekstowe: {pliki_tekstowe}")
    print(f"  zapisano: {saved_path}")


# --- Przewodnik bez modelu ---


def _render_placeholder_guide(
    project_map: _schemas.ProjectMap,
    app_config: _config.AppConfig,
    store: _output.RunStore,
) -> str:
    """Składa przewodnik z zaślepkami (sekcje z kodu prawdziwe, sekcje agentów zaślepki), zapisuje guide.html i zwraca ścieżkę.

    Po co: podgląd wyglądu przewodnika na prawdziwym robocie przed pierwszym wywołaniem modelu (krok 39); nie woła modelu.
    """
    szablon = _template.load_template(app_config.paths.guide_template)
    tresc = _placeholders.build_placeholder_content(szablon, project_map)
    wygenerowano = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = _render.render_guide(
        tresc,
        szablon,
        project_map,
        os.path.dirname(app_config.paths.guide_template),
        f"{wygenerowano} (podgląd bez modelu)",
        app_config.analysis.long_unit_lines,
        app_config.flow,
    )
    zapisany_plik = store.save_text("guide.html", html)
    return zapisany_plik


# --- Graf agentów ---


def _run_graph(
    project_root: str,
    app_config: _config.AppConfig,
    store: _output.RunStore,
) -> tuple[_schemas.ProjectMap, _schemas.Plan]:
    """Buduje kontekst, uruchamia graf agentów na projekcie i zwraca (mapa projektu, plan) ze stanu końcowego.

    Po co: jedyne miejsce w main.py, które zna graf; kolejne węzły nie zmieniają tej funkcji, bo dochodzą do grafu.
    Węzły zgłaszają postęp liniami na ekran (progress.print_line podane w kontekście), a po grafie wypisana
    jest linia "razem: X s".

    Uwaga: błąd budowy kontekstu (brak zmiennej środowiskowej z kluczem albo adresem modelu, błędny spis bazy wiedzy
    lub szablon) kończy program komunikatem z nazwą przyczyny, zanim graf ruszy.
    """
    try:
        kontekst = _context.build_context(app_config, store, _progress.print_line)
    except (RuntimeError, ValueError, OSError) as blad:
        sys.exit(f"BŁĄD: {blad}")
    graf = _graph.build_graph()
    czas_startu = time.monotonic()
    stan_koncowy = graf.invoke({"project_path": project_root}, context=kontekst)
    razem = _progress.format_seconds(time.monotonic() - czas_startu)
    _progress.print_line(_progress.format_line("razem", razem))
    wynik = (stan_koncowy["project_map"], stan_koncowy["plan"])
    return wynik


# --- Uruchomienie ---


def _print_plan_summary(
    plan: _schemas.Plan,
) -> None:
    """Wypisuje jedną linię o planie: liczba zadań analityków i liczby plików wiedzy dla analityków, autora diagramu i pisarzy.

    Po co: po przebiegu widać od razu, że planner coś zaplanował; pełny plan jest w dev_agents_doc/plan.json.
    """
    print(
        f"  plan: zadań {len(plan.tasks)}, pliki wiedzy: analitycy {len(plan.analyst_knowledge)}, "
        f"autor diagramu {len(plan.flow_knowledge)}, pisarze {len(plan.writer_knowledge)}"
    )


def _parse_args() -> argparse.Namespace:
    """Odczytuje argumenty: --project (wymagany, sprawdzany), --config (domyślnie config.yaml obok main.py), --render-only.

    Po co: jedno miejsce z opcjami programu. Domyślna ścieżka configu liczona względem main.py
    sprawia, że program działa z dowolnego katalogu; literówka w ścieżce projektu daje czytelny błąd.
    """
    default_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    parser = argparse.ArgumentParser(description="Przewodnik dla dewelopera z kodu robota RPA, tworzony przez zespół agentów.")
    parser.add_argument("--project", required=True, help="ścieżka do katalogu analizowanego projektu")
    parser.add_argument("--config", default=default_config, help="ścieżka do pliku konfiguracyjnego (domyślnie: config.yaml obok main.py)")
    parser.add_argument("--render-only", action="store_true", help="zapisz też dev_agents_doc/guide.html z zaślepkami zamiast tekstu agentów (bez wywołań modelu)")
    args = parser.parse_args()
    if not os.path.isdir(args.project):
        parser.error(f"--project: katalog nie istnieje: {args.project}")
    return args


def main() -> None:
    """Uruchamia program: argumenty -> config -> kontrola technologii -> magazyn -> graf (albo sam skan) -> project_map.json -> podsumowanie.

    Po co: spis treści całego przebiegu; kolejne etapy narzędzia dopisujemy do grafu, tutaj zmienia się tylko to, co dotyczy uruchomienia.

    Uwaga: nierozpoznana technologia kończy program przed założeniem dev_agents_doc/ - w cudzym katalogu
    nic nie zostaje. Katalog wyników bez znacznika albo brak prawa zapisu - komunikat z output.py.
    Z --render-only mapa pochodzi z szybkiego skanu (bez grafu i bez modeli); w trybie pełnym graf skanuje
    projekt jeszcze raz w węźle scan (skan nie woła modelu, więc kosztuje ułamek sekundy).
    """
    args = _parse_args()
    app_config = _config.load_config(args.config)
    _print_header(args.config, app_config)
    mapa_wstepna = _scanner.build_project_map(args.project, app_config.scan)
    if not mapa_wstepna.technology:
        sys.exit(f"BŁĄD: nie rozpoznano technologii projektu {mapa_wstepna.root} - brak kodu obsługiwanej technologii. Nic nie zapisano.")
    try:
        magazyn = _output.create_run_store(mapa_wstepna.root)
    except (ValueError, OSError) as blad:
        sys.exit(f"BŁĄD: {blad}")
    plan = None
    if args.render_only:
        project_map = mapa_wstepna
    else:
        project_map, plan = _run_graph(mapa_wstepna.root, app_config, magazyn)
    zapisany_plik = magazyn.save_json("project_map.json", project_map)
    _print_scan_summary(project_map, zapisany_plik)
    if plan is not None:
        _print_plan_summary(plan)
    if args.render_only:
        zapisany_przewodnik = _render_placeholder_guide(project_map, app_config, magazyn)
        print(f"  zapisano: {zapisany_przewodnik} (zaślepki zamiast tekstu agentów, diagram przykładowy)")


if __name__ == "__main__":
    main()
