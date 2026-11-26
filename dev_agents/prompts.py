"""Prompty agentów: wczytanie z plików prompts/<agent>/ i wstawienie danych do szablonu.

Co robi: render_prompt() zwraca dla wskazanego agenta gotową parę tekstów (system, user):
    - system.md - stałe polecenie agenta, zwracane bez zmian (to nie jest szablon),
    - user.md   - szablon Jinja2 z miejscami na dane, np. {{ project_map }}; kod wstawia tam dane konkretnego
                  projektu przy każdym wywołaniu modelu.

Dlaczego istnieje:
    - polecenia dla agentów poprawia się w plikach Markdown, bez zmian w kodzie - tym stroi się jakość przewodnika,
    - dane z analizowanego robota (w tym jego kod) trafiają zawsze do części user, opakowane w tagi - ochrona przed
      prompt injection z cudzego kodu; stały system może być cache'owany przez dostawcę modelu,
    - brak zmiennej w danych kończy się błędem z nazwą agenta i zmiennej (StrictUndefined), a nie pustym miejscem w
      poleceniu, za które zapłacilibyśmy słabą odpowiedzią modelu.

Czego NIE robi: nie escapuje tekstu (prompt to Markdown, nie HTML), nie wykonuje składni Jinja2 z wartości zmiennych
(kod robota z "{{ ... }}" trafia do promptu dosłownie), nie zgłasza błędu dla zmiennych podanych, a nieużytych w
szablonie (ten sam słownik można podać kilku agentom), nie wybiera plików bazy wiedzy (to knowledge.py).

Rola: moduł rdzenia towaru, wołany przez agentów w grafie (faza F). Katalog promptów to paths.prompts z config.yaml.

Test ręczny (z katalogu głównego repo; prompty tworzone w katalogu tymczasowym, który jest sprzątany):
    python -m dev_agents.prompts
        wypisuje wyrenderowany przykładowy prompt (system bez zmian, user z danymi), wynik dla zmiennej podanej
        nadmiarowo, dla wartości ze składnią Jinja2 i znakiem "<", oczekiwane błędy (brak zmiennej, brak pliku) i na
        końcu „zgodne z oczekiwaniem: True” albo wypisuje, który przypadek się nie zgadza
"""

import os

import jinja2

_SYSTEM_FILE = "system.md"
_USER_FILE = "user.md"


def read_prompt_file(
    prompts_dir: str,
    agent: str,
    filename: str,
) -> str:
    """Zwraca treść pliku prompts_dir/<agent>/<filename> (UTF-8); brak pliku - FileNotFoundError ze ścieżką.

    Po co: jedno miejsce odczytu plików promptów; od razu widać, którego promptu brakuje.
    """
    sciezka_pliku = os.path.join(prompts_dir, agent, filename)
    with open(sciezka_pliku, encoding="utf-8") as plik:
        tresc = plik.read()
    return tresc


def render_prompt(
    prompts_dir: str,
    agent: str,
    variables: dict,
) -> tuple[str, str]:
    """Zwraca parę (system, user) dla agenta: system.md bez zmian i user.md z wstawionymi zmiennymi.

    Po co: agent przed wywołaniem modelu potrzebuje obu tekstów naraz. Brak zmiennej użytej w user.md - ValueError z
    nazwą agenta i zmiennej; brak pliku - FileNotFoundError ze ścieżką. Argumenty: prompts_dir - katalog promptów
    (config.paths.prompts), agent - nazwa podkatalogu, variables - dane do wstawienia w szablon user.md.
    """
    tekst_system = read_prompt_file(prompts_dir, agent, _SYSTEM_FILE)
    szablon_user = read_prompt_file(prompts_dir, agent, _USER_FILE)
    srodowisko = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    try:
        tekst_user = srodowisko.from_string(szablon_user).render(variables)
    except jinja2.UndefinedError as blad:
        komunikat = f"Prompt {agent}/{_USER_FILE}: brak zmiennej w danych - {blad}"
        raise ValueError(komunikat) from blad
    prompt = (tekst_system, tekst_user)
    return prompt


# --- Test ręczny ---

if __name__ == "__main__":
    import shutil
    import tempfile

    _TEST_AGENT = "przyklad"
    _TEST_SYSTEM = "Jesteś pisarzem przewodnika.\nZmienne jak {{ project_name }} w tym pliku zostają bez zmian.\n"
    _TEST_USER = "Opisz robota „{{ project_name }}”.\n\n<kod>\n{{ code }}\n</kod>\n"

    def _write_prompts(
        prompts_dir: str,
    ) -> None:
        """Zapisuje przykładowy prompt agenta „przyklad” (system.md i user.md) w katalogu promptów.

        Po co: test działa na prawdziwych plikach, ale w katalogu tymczasowym - w repo nie zostaje nic zbędnego.
        """
        katalog_agenta = os.path.join(prompts_dir, _TEST_AGENT)
        os.makedirs(katalog_agenta)
        with open(os.path.join(katalog_agenta, _SYSTEM_FILE), "w", encoding="utf-8") as plik:
            plik.write(_TEST_SYSTEM)
        with open(os.path.join(katalog_agenta, _USER_FILE), "w", encoding="utf-8") as plik:
            plik.write(_TEST_USER)

    def _print_prompt(
        title: str,
        system_text: str,
        user_text: str,
    ) -> None:
        """Wypisuje oba teksty promptu z nagłówkiem.

        Po co: w teście widać dokładnie to, co dostanie model.
        """
        print(f"=== {title} / system ===")
        print(system_text)
        print(f"=== {title} / user ===")
        print(user_text)

    def _error_text(
        prompts_dir: str,
        agent: str,
        variables: dict,
    ) -> str:
        """Zwraca tekst błędu zgłoszonego przez render_prompt (ValueError albo FileNotFoundError); brak błędu - pusty tekst.

        Po co: przypadki z oczekiwanym błędem sprawdzane tym samym zapisem, bez powielania try/except.
        """
        tekst = ""
        try:
            render_prompt(prompts_dir, agent, variables)
        except (ValueError, FileNotFoundError) as blad:
            tekst = f"{type(blad).__name__}: {blad}"
        return tekst

    def manual_test():
        """Renderuje przykładowy prompt, sprawdza przypadki graniczne i wypisuje, czy wszystkie zgadzają się z oczekiwaniem.

        Po co: ręczne sprawdzenie wczytywania promptów, wstawiania zmiennych i wykrywania braków bez modelu.
        """
        katalog = tempfile.mkdtemp()
        try:
            _write_prompts(katalog)
            dane = {"project_name": "robot_faktur", "code": "print('x')"}
            system_text, user_text = render_prompt(katalog, _TEST_AGENT, dane)
            _print_prompt("przyklad", system_text, user_text)
            oczekiwany_user = "Opisz robota „robot_faktur”.\n\n<kod>\nprint('x')\n</kod>\n"

            nadmiarowe = dict(dane)
            nadmiarowe["nieuzywana"] = "wartość, której szablon nie używa"
            _, user_nadmiarowe = render_prompt(katalog, _TEST_AGENT, nadmiarowe)

            niebezpieczne = dict(dane)
            niebezpieczne["code"] = "{{ 1 + 1 }} {% if x %}a{% endif %} <b>&</b>"
            _, user_niebezpieczne = render_prompt(katalog, _TEST_AGENT, niebezpieczne)
            print("=== wartość ze składnią Jinja2 i znakami < & (user) ===")
            print(user_niebezpieczne)

            bez_zmiennej = dict(dane)
            del bez_zmiennej["code"]
            blad_zmiennej = _error_text(katalog, _TEST_AGENT, bez_zmiennej)
            blad_pliku = _error_text(katalog, "nie_ma_takiego_agenta", dane)
            print("=== oczekiwane błędy ===")
            print(blad_zmiennej)
            print(blad_pliku)

            przypadki = [
                ("system bez zmian (zmienne w nim nie są podstawiane)", system_text == _TEST_SYSTEM),
                ("user z wstawionymi danymi", user_text == oczekiwany_user),
                ("zmienna nadmiarowa nie szkodzi", user_nadmiarowe == oczekiwany_user),
                ("składnia Jinja2 i znaki < & z wartości dosłownie", "{{ 1 + 1 }} {% if x %}a{% endif %} <b>&</b>" in user_niebezpieczne),
                ("brak zmiennej: ValueError z agentem i zmienną", blad_zmiennej.startswith("ValueError: Prompt przyklad/user.md") and "'code'" in blad_zmiennej),
                ("brak pliku: FileNotFoundError ze ścieżką", blad_pliku.startswith("FileNotFoundError") and "nie_ma_takiego_agenta" in blad_pliku),
            ]
            zgodne = True
            for opis, wynik in przypadki:
                if not wynik:
                    zgodne = False
                    print(f"  niezgodne: {opis}")
            print(f"Przypadków: {len(przypadki)}, zgodne z oczekiwaniem: {zgodne}")
        finally:
            shutil.rmtree(katalog)

    manual_test()
