"""Konfiguracja towaru: opis config.yaml jako klasy Pydantic i funkcja load_config().

Co robi: wczytuje config.yaml, zamienia go na obiekty Pythona (podpowiedzi w edytorze, dostęp przez
atrybuty, np. app_config.llm.profiles["small"].model), sprawdza, czy każdy agent wskazuje istniejący
profil modelu i czy metoda structured output w każdym profilu jest znana, a ścieżki z sekcji `paths`
zamienia na bezwzględne.

Dlaczego istnieje: to jedyne wejście do ustawień narzędzia. Pozostałe moduły dostają już sprawdzony,
typowany obiekt zamiast surowego słownika z YAML-a, a błędy w configu (literówka w nazwie profilu albo
metody) wychodzą przy starcie, zanim narzędzie zużyje czas i tokeny na wcześniejsze etapy. Przełączenie
na miasto to zamiana zakomentowanych linii w config.yaml, bez zmian w tym module.

Czego NIE robi: nie czyta kluczy ani adresów endpointów - config trzyma tylko NAZWY zmiennych
środowiskowych (np. LLM_API_KEY); wartości odczytuje dopiero fabryka modeli.

Rola: moduł używany przez punkt wejścia programu i przez warstwy, które potrzebują ustawień
(modele, skaner, prompty). Kolejne sekcje configu dochodzą jako kolejne klasy w krokach, które ich potrzebują.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.config
Najpierw wypisuje wczytany config jako JSON (ścieżki w `paths` mają być bezwzględne), potem komunikaty
błędów dla trzech celowo zepsutych kopii configu w pamięci (plik config.yaml nie jest zmieniany).
"""

import os

import yaml
from pydantic import BaseModel


# --- Modele configu ---


class LLMProfile(BaseModel):
    """Profil modelu: dostawca, nazwa modelu, nazwy zmiennych środowiskowych, metoda structured output i parametry wywołania.

    Po co: agenci nie znają konkretnych modeli - wskazują profil, a profil mówi, jak model utworzyć
    i jak prosić go o odpowiedź zgodną ze schematem.

    Uwaga: structured_output_method nie ma wartości domyślnej - każdy profil musi ją podać jawnie,
    bo to, która metoda działa, zależy od endpointu (ustala ją scripts/probe_llm.py).
    """

    provider: str
    model: str
    api_key_env: str  # nazwa zmiennej środowiskowej z kluczem, nie klucz
    base_url_env: str  # nazwa zmiennej środowiskowej z adresem endpointu, nie adres
    structured_output_method: str  # json_schema | function_calling | json_mode
    params: dict = {}  # do modelu trafiają tylko parametry podane tutaj


class LLMConfig(BaseModel):
    """Sekcja `llm`: nazwane profile modeli i przypisanie agent -> nazwa profilu.

    Po co: zmiana modelu dla agenta to zmiana jednej linii w sekcji `agents`, bez zmian w kodzie agenta.
    """

    profiles: dict[str, LLMProfile]
    agents: dict[str, str]


class PathsConfig(BaseModel):
    """Sekcja `paths`: katalogi z promptami i bazą wiedzy.

    Po co: prompty i wiedza leżą poza kodem; po wczytaniu configu ścieżki są bezwzględne,
    więc działają niezależnie od katalogu, z którego uruchomiono narzędzie.
    """

    prompts: str
    knowledge_base: str


class AppConfig(BaseModel):
    """Cały config.yaml.

    Po co: jeden obiekt z wszystkimi ustawieniami, przekazywany dalej zamiast surowego słownika.
    """

    llm: LLMConfig
    paths: PathsConfig


# --- Sprawdzenia i przetwarzanie ---


def _check_agent_profiles(
    app_config: AppConfig,
) -> None:
    """Sprawdza, czy każdy agent z llm.agents wskazuje profil istniejący w llm.profiles; przy błędzie rzuca ValueError.

    Po co: literówka w nazwie profilu wyszłaby inaczej dopiero przy tworzeniu modelu dla agenta,
    w środku przebiegu; tak wychodzi przy starcie, z listą dostępnych profili w komunikacie.
    """
    for agent_name, profile_name in app_config.llm.agents.items():
        if profile_name not in app_config.llm.profiles:
            komunikat_bledu = (
                f"Agent '{agent_name}' wskazuje nieistniejący profil '{profile_name}'. "
                f"Dostępne profile: {list(app_config.llm.profiles)}"
            )
            raise ValueError(komunikat_bledu)


def _check_structured_output_methods(
    app_config: AppConfig,
) -> None:
    """Sprawdza, czy metoda structured output każdego profilu jest jedną z obsługiwanych; przy błędzie rzuca ValueError.

    Po co: literówka w nazwie metody (np. 'json_shema') wyszłaby inaczej dopiero przy pierwszym
    wywołaniu modelu, po skanie projektu; tak wychodzi przy starcie, z listą dozwolonych metod.
    """
    dozwolone_metody = ["json_schema", "function_calling", "json_mode"]
    for profile_name, profile in app_config.llm.profiles.items():
        if profile.structured_output_method not in dozwolone_metody:
            komunikat_bledu = (
                f"Profil '{profile_name}' ma nieznaną metodę structured output "
                f"'{profile.structured_output_method}'. Dozwolone: {dozwolone_metody}"
            )
            raise ValueError(komunikat_bledu)


def _resolve_paths(
    paths: PathsConfig,
    config_dir: str,
) -> None:
    """Zamienia ścieżki z sekcji paths na bezwzględne: względne liczy od katalogu configu, bezwzględne zostawia.

    Po co: reszta narzędzia dostaje jednoznaczne ścieżki i działa tak samo bez względu na to,
    z którego katalogu uruchomiono program.

    Uwaga: zmienia przekazany obiekt w miejscu (nic nie zwraca).
    """
    paths.prompts = os.path.abspath(os.path.join(config_dir, paths.prompts))
    paths.knowledge_base = os.path.abspath(os.path.join(config_dir, paths.knowledge_base))


def _build_config(
    raw_config: dict,
    config_dir: str,
) -> AppConfig:
    """Zamienia słownik wczytany z YAML-a na AppConfig, sprawdza profile agentów i metody, rozwiązuje ścieżki.

    Po co: oddziela budowę configu od czytania pliku - test ręczny sprawdza na niej celowo zepsute
    kopie configu w pamięci, bez zmieniania config.yaml.

    Uwaga: brak wymaganego pola (np. structured_output_method w profilu) zgłasza Pydantic jako
    ValidationError z nazwą pola i ścieżką do niego (np. llm.profiles.small.structured_output_method).
    """
    app_config = AppConfig(**raw_config)
    _check_agent_profiles(app_config)
    _check_structured_output_methods(app_config)
    _resolve_paths(app_config.paths, config_dir)
    return app_config


# --- Wczytywanie ---


def load_config(
    path: str,
) -> AppConfig:
    """Wczytuje config.yaml z podanej ścieżki i zwraca sprawdzony AppConfig ze ścieżkami bezwzględnymi.

    Po co: jedyne wejście do konfiguracji dla całego narzędzia - zamiast surowego słownika każdy moduł
    dostaje typowany obiekt z podpowiedziami w edytorze.
    """
    config_path = os.path.abspath(path)
    with open(config_path, encoding="utf-8") as config_file:
        raw_config = yaml.safe_load(config_file)

    app_config = _build_config(raw_config, os.path.dirname(config_path))
    return app_config


# --- Test ręczny ---

if __name__ == "__main__":
    import copy

    def _print_config(
        app_config: AppConfig,
    ) -> None:
        """Wypisuje config jako JSON z wcięciami.

        Po co: widać dokładnie to, co dostaje reszta narzędzia, w tym ścieżki bezwzględne.
        """
        print(app_config.model_dump_json(indent=2))

    def _print_error(
        title: str,
        error: Exception,
    ) -> None:
        """Wypisuje tytuł przypadku testowego i komunikat błędu, który zgłosił config.

        Po co: test pokazuje, czy komunikat jest czytelny dla osoby, która popełniła błąd w configu.
        """
        print(f"\n--- {title} ---")
        print(f"{type(error).__name__}: {error}")

    def _try_broken_config(
        title: str,
        raw_config: dict,
        config_dir: str,
    ) -> None:
        """Buduje config z celowo zepsutej kopii i wypisuje zgłoszony błąd (albo informację, że błędu nie było).

        Po co: sprawdzenie komunikatów błędów bez ręcznego psucia config.yaml.
        """
        try:
            _build_config(raw_config, config_dir)
            print(f"\n--- {title} ---\nBŁĄD TESTU: zepsuty config przeszedł bez błędu")
        except ValueError as blad:  # pydantic.ValidationError też dziedziczy po ValueError
            _print_error(title, blad)

    def manual_test():
        """Wczytuje config.yaml z katalogu repo i wypisuje go, potem pokazuje błędy dla trzech zepsutych kopii.

        Po co: szybkie sprawdzenie, czy config się wczytuje, ścieżki są bezwzględne, a błędy w configu
        dają czytelne komunikaty.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(repo_dir, "config.yaml")
        app_config = load_config(config_path)
        _print_config(app_config)

        with open(config_path, encoding="utf-8") as config_file:
            raw_config = yaml.safe_load(config_file)

        zly_profil_agenta = copy.deepcopy(raw_config)
        zly_profil_agenta["llm"]["agents"]["planner"] = "smal"
        _try_broken_config("Agent wskazuje nieistniejący profil ('smal')", zly_profil_agenta, repo_dir)

        zla_metoda = copy.deepcopy(raw_config)
        zla_metoda["llm"]["profiles"]["small"]["structured_output_method"] = "json_shema"
        _try_broken_config("Nieznana metoda structured output ('json_shema')", zla_metoda, repo_dir)

        brak_metody = copy.deepcopy(raw_config)
        del brak_metody["llm"]["profiles"]["medium"]["structured_output_method"]
        _try_broken_config("Profil bez structured_output_method", brak_metody, repo_dir)

    manual_test()
