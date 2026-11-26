"""Punkt wejścia towaru (dev-agents): argumenty -> config -> mapa projektu -> zapis w dev_agents_doc/.

Co robi: odczytuje argumenty wiersza poleceń, wczytuje config.yaml, buduje mapę analizowanego projektu
(scanner.build_project_map - pliki z rolami, punkty wejścia, jednostki kodu z zakresami linii, frameworki,
pliki tekstowe, graf zależności i kolejność czytania), zapisuje ją jako dev_agents_doc/project_map.json
w katalogu projektu i wypisuje krótkie podsumowanie. Kolejne etapy (graf agentów, przewodnik HTML) dochodzą
tutaj w kolejnych krokach planu.

Dlaczego istnieje: jedno polecenie uruchamia całe narzędzie. Domyślny config jest szukany obok main.py,
a nie w bieżącym katalogu, więc program działa tak samo bez względu na to, skąd go uruchomiono
(np. z katalogu analizowanego robota). Nierozpoznana technologia albo katalog wyników, którego nie wolno
użyć, kończą program czytelnym komunikatem (kod wyjścia 1), zanim cokolwiek zostanie zapisane.

Rola: samodzielny skrypt - nikt go nie importuje; jego uruchomienie jest testem ręcznym.

Uruchomienie z katalogu głównego repo:
    python main.py --project <ścieżka do katalogu robota>
    python main.py --project <ścieżka do katalogu robota> --config <ścieżka do config.yaml>
"""

import argparse
import os
import sys

import dev_agents.config as _config
import dev_agents.output as _output
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


# --- Uruchomienie ---


def _parse_args() -> argparse.Namespace:
    """Odczytuje argumenty: --project (wymagany, sprawdzany) i --config (domyślnie config.yaml obok main.py).

    Po co: jedno miejsce z opcjami programu. Domyślna ścieżka configu liczona względem main.py
    sprawia, że program działa z dowolnego katalogu; literówka w ścieżce projektu daje czytelny błąd.
    """
    default_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    parser = argparse.ArgumentParser(description="Przewodnik dla dewelopera z kodu robota RPA, tworzony przez zespół agentów.")
    parser.add_argument("--project", required=True, help="ścieżka do katalogu analizowanego projektu")
    parser.add_argument("--config", default=default_config, help="ścieżka do pliku konfiguracyjnego (domyślnie: config.yaml obok main.py)")
    args = parser.parse_args()
    if not os.path.isdir(args.project):
        parser.error(f"--project: katalog nie istnieje: {args.project}")
    return args


def main() -> None:
    """Uruchamia program: argumenty -> config -> mapa projektu -> zapis project_map.json -> podsumowanie.

    Po co: spis treści całego przebiegu; kolejne etapy narzędzia dopisujemy tu jako kolejne wywołania.

    Uwaga: nierozpoznana technologia kończy program przed założeniem dev_agents_doc/ - w cudzym katalogu
    nic nie zostaje. Katalog wyników bez znacznika albo brak prawa zapisu - komunikat z output.py.
    """
    args = _parse_args()
    app_config = _config.load_config(args.config)
    _print_header(args.config, app_config)
    project_map = _scanner.build_project_map(args.project, app_config.scan)
    if not project_map.technology:
        sys.exit(f"BŁĄD: nie rozpoznano technologii projektu {project_map.root} - brak kodu obsługiwanej technologii. Nic nie zapisano.")
    try:
        magazyn = _output.create_run_store(project_map.root)
    except (ValueError, OSError) as blad:
        sys.exit(f"BŁĄD: {blad}")
    zapisany_plik = magazyn.save_json("project_map.json", project_map)
    _print_scan_summary(project_map, zapisany_plik)


if __name__ == "__main__":
    main()
