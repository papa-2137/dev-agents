"""Punkt wejścia towaru (dev-agents): argumenty -> config -> podsumowanie.

Co robi: odczytuje argumenty wiersza poleceń, wczytuje config.yaml i wypisuje podsumowanie: plik configu,
dla każdego agenta profil, model i metodę structured output, katalogi z promptami i bazą wiedzy oraz
analizowany projekt, jeśli go podano. Kolejne etapy (skan projektu, graf agentów, przewodnik HTML)
dochodzą tutaj w kolejnych krokach planu.

Dlaczego istnieje: jedno polecenie uruchamia całe narzędzie. Domyślny config jest szukany obok main.py,
a nie w bieżącym katalogu, więc program działa tak samo bez względu na to, skąd go uruchomiono
(np. z katalogu analizowanego robota).

Rola: samodzielny skrypt - nikt go nie importuje; jego uruchomienie jest testem ręcznym.

Uruchomienie z katalogu głównego repo:
    python main.py
    python main.py --project <ścieżka do katalogu robota>
    python main.py --config <ścieżka do config.yaml>
"""

import argparse
import os

import dev_agents.config as _config


# --- Wyświetlanie ---


def _print_summary(
    config_path: str,
    app_config: _config.AppConfig,
    project_path: str,
) -> None:
    """Wypisuje podsumowanie: plik configu, agentów z profilem, modelem i metodą, katalogi i projekt (jeśli podany).

    Po co: widoczny efekt uruchomienia - od razu widać, który model dostanie który agent,
    także po przełączeniu linii configu na miejskie.
    """
    print("dev-agents")
    print(f"  config: {os.path.abspath(config_path)}")
    print("  agenci (agent: profil -> model, metoda structured output):")
    for agent_name, profile_name in app_config.llm.agents.items():
        profile = app_config.llm.profiles[profile_name]
        print(f"    {agent_name}: {profile_name} -> {profile.model}, {profile.structured_output_method}")
    print(f"  prompty:      {app_config.paths.prompts}")
    print(f"  baza wiedzy:  {app_config.paths.knowledge_base}")
    if project_path != "":
        print(f"  projekt:      {os.path.abspath(project_path)}")


# --- Uruchomienie ---


def _parse_args() -> argparse.Namespace:
    """Odczytuje argumenty: --config (domyślnie config.yaml obok main.py) i --project (opcjonalny, sprawdzany).

    Po co: jedno miejsce z opcjami programu. Domyślna ścieżka configu liczona względem main.py
    sprawia, że program działa z dowolnego katalogu; podany katalog projektu jest od razu sprawdzany,
    więc literówka w ścieżce daje czytelny błąd zamiast cichego zignorowania.

    Uwaga: --project jest na razie opcjonalny (pusty tekst = nie podano); stanie się wymagany,
    gdy main.py zacznie skanować projekt.
    """
    default_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")
    parser = argparse.ArgumentParser(description="Przewodnik dla dewelopera z kodu robota RPA, tworzony przez zespół agentów.")
    parser.add_argument("--config", default=default_config, help="ścieżka do pliku konfiguracyjnego (domyślnie: config.yaml obok main.py)")
    parser.add_argument("--project", default="", help="ścieżka do katalogu analizowanego projektu")
    args = parser.parse_args()
    if args.project != "" and not os.path.isdir(args.project):
        parser.error(f"--project: katalog nie istnieje: {args.project}")
    return args


def main() -> None:
    """Uruchamia program: argumenty -> config -> podsumowanie.

    Po co: spis treści całego przebiegu; kolejne etapy narzędzia dopisujemy tu jako kolejne wywołania.
    """
    args = _parse_args()
    app_config = _config.load_config(args.config)
    _print_summary(args.config, app_config, args.project)


if __name__ == "__main__":
    main()
