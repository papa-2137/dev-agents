"""Wspólne narzędzia agentów: wybór i składanie plików wiedzy oraz numerowanie linii kodu.

Co robi:
    - collect_knowledge_files() zwraca nazwy plików wiedzy dla agenta: najpierw plik technologii projektu, potem pliki
      wykrytych frameworków (z config.scan.frameworks), na końcu pliki wybrane przez plannera - bez powtórzeń,
    - format_knowledge() składa treść tych plików w jeden tekst do promptu (każdy plik w znaczniku <plik_wiedzy>),
    - number_lines() dopisuje do każdej linii tekstu jej numer (od podanej linii - przy kawałku pliku), żeby odwołania
      agenta do linii były dokładne,
    - cut_lines() wycina zakres linii (kawałek długiego pliku),
    - count_lines() podaje liczbę linii tekstu (do sprawdzenia, czy numer linii od agenta mieści się w pliku).

Dlaczego istnieje: analityk, autor diagramu i pisarze dostają wiedzę i kod tak samo - jedna implementacja zamiast
trzech kopii. Pliki technologii i frameworków dołącza kod (planner ich nie wybiera), pliki planera sprawdza już
complete_plan, a read_kb_file nie wypuści nazwy spoza bazy wiedzy.

Rola: moduł pomocniczy agentów (planner nie korzysta - dostaje spis, a nie treść).

Test ręczny (z katalogu głównego repo; bez sieci i kluczy):
    python -m dev_agents.agents.common
        sprawdza wybór plików wiedzy (technologia, framework, plik plannera, bez powtórzeń, brak pliku technologii),
        skład tekstu wiedzy z prawdziwych plików bazy oraz numerowanie i liczenie linii; na końcu "zgodne z oczekiwaniem: True".
"""

import dev_agents.config as _config
import dev_agents.knowledge as _knowledge
import dev_agents.schemas as _schemas
import dev_agents.technologies.registry as _registry


def collect_knowledge_files(
    app_config: _config.AppConfig,
    project_map: _schemas.ProjectMap,
    planner_files: list[str],
) -> list[str]:
    """Zwraca nazwy plików wiedzy dla agenta: technologia projektu, wykryte frameworki, pliki plannera - bez powtórzeń, w tej kolejności.

    Po co: ogólna wiedza (technologia, framework) idzie przed wyborem plannera i nie zależy od niego; powtórzony
    plik (np. wybrany przez plannera drugi raz) trafia do promptu tylko raz.
    """
    nazwy = []
    technologia = _registry.get_technology(project_map.technology)
    if technologia is not None:
        plik_technologii = technologia.knowledge_file()
        if plik_technologii != "":
            nazwy.append(plik_technologii)
    for nazwa_frameworku in project_map.frameworks:
        wpis_frameworku = app_config.scan.frameworks.get(nazwa_frameworku)
        if wpis_frameworku is not None:
            nazwy.append(wpis_frameworku.knowledge)
    for plik_plannera in planner_files:
        nazwy.append(plik_plannera)
    bez_powtorzen = []
    for nazwa in nazwy:
        if nazwa not in bez_powtorzen:
            bez_powtorzen.append(nazwa)
    return bez_powtorzen


def format_knowledge(
    app_config: _config.AppConfig,
    filenames: list[str],
) -> str:
    """Zwraca treść plików wiedzy jako jeden tekst do promptu: każdy plik w znaczniku <plik_wiedzy nazwa="...">; bez plików - zdanie o braku.

    Po co: jedno miejsce, które składa wiedzę dla wszystkich agentów. Odczyt idzie przez knowledge.read_kb_file,
    więc nazwa wskazująca poza bazę wiedzy kończy się ValueError, a nie odczytem cudzego pliku.
    """
    if not filenames:
        tekst_braku = "(brak plików wiedzy)"
        return tekst_braku
    bloki = []
    for nazwa in filenames:
        tresc = _knowledge.read_kb_file(app_config.paths.knowledge_base, nazwa)
        bloki.append(f'<plik_wiedzy nazwa="{nazwa}">\n{tresc.strip()}\n</plik_wiedzy>')
    tekst_wiedzy = "\n\n".join(bloki)
    return tekst_wiedzy


def number_lines(
    text: str,
    first_line: int = 1,
) -> str:
    """Zwraca tekst z numerem przed każdą linią w formacie "   12| treść" (pierwsza linia ma numer first_line); pusty tekst daje pusty tekst.

    Po co: model nie liczy linii wiarygodnie - numer podany w kodzie pozwala mu wskazać funkcję i linię dokładnie.
    Przy kawałku długiego pliku numeracja zaczyna się od numeru pierwszej linii kawałka, więc numery są bezwzględne.
    """
    if text == "":
        return ""
    linie = text.split("\n")
    if linie[-1] == "":
        linie = linie[:-1]
    ponumerowane = []
    for numer, linia in enumerate(linie, start=first_line):
        ponumerowane.append(f"{numer:5d}| {linia}")
    wynik = "\n".join(ponumerowane)
    return wynik


def cut_lines(
    text: str,
    first_line: int,
    last_line: int,
) -> str:
    """Zwraca linie od first_line do last_line włącznie (numeracja od 1, liczona jak w number_lines) jako tekst bez końcowego znaku nowej linii.

    Po co: kawałek długiego pliku to zakres linii; ta sama zasada liczenia linii co przy numerowaniu sprawia,
    że numery w kawałku zgadzają się z numerami w pliku.
    """
    linie = text.split("\n")
    if linie[-1] == "":
        linie = linie[:-1]
    fragment = "\n".join(linie[first_line - 1:last_line])
    return fragment


def count_lines(
    text: str,
) -> int:
    """Zwraca liczbę linii tekstu liczoną tak jak numerowanie (końcowy znak nowej linii nie tworzy pustej linii); pusty tekst - 0.

    Po co: numer linii od agenta ma mieścić się w pliku - wołający porównuje go z tą liczbą.
    """
    if text == "":
        return 0
    liczba = len(text.split("\n"))
    if text.endswith("\n"):
        liczba = liczba - 1
    return liczba


# --- Test ręczny ---

if __name__ == "__main__":
    import os

    def _empty_map(
        technology: str,
        frameworks: list[str],
    ) -> _schemas.ProjectMap:
        """Zwraca pustą mapę projektu z podaną technologią i frameworkami.

        Po co: wybór plików wiedzy zależy tylko od technologii i frameworków, reszta mapy nie jest potrzebna.
        """
        pusta_mapa = _schemas.ProjectMap(
            project_name="test",
            root="",
            technology=technology,
            entrypoints=[],
            files=[],
            code_units=[],
            frameworks=frameworks,
        )
        return pusta_mapa

    def _checks() -> list[tuple[str, bool]]:
        """Sprawdza wybór plików wiedzy, składanie tekstu wiedzy i numerowanie linii; zwraca (opis, zgodne).

        Po co: wspólne narzędzia agentów muszą dawać przewidywalny wynik, zanim oprze się na nich analityk.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        z_frameworkiem = collect_knowledge_files(app_config, _empty_map("python", ["roboforge"]), ["diagram_rules.md", "technologies/python.md"])
        bez_frameworku = collect_knowledge_files(app_config, _empty_map("python", []), [])
        bez_technologii = collect_knowledge_files(app_config, _empty_map("", []), ["guide_goals.md"])
        tekst = format_knowledge(app_config, ["technologies/python.md"])
        tekst_pusty = format_knowledge(app_config, [])
        zly_plik_odrzucony = False
        try:
            format_knowledge(app_config, ["../config.yaml"])
        except ValueError:
            zly_plik_odrzucony = True
        wyniki = [
            (
                f"technologia, framework, plik plannera - bez powtórzeń: {z_frameworkiem}",
                z_frameworkiem == ["technologies/python.md", "frameworks/roboforge.md", "diagram_rules.md"],
            ),
            (f"bez frameworku i plannera: tylko technologia: {bez_frameworku}", bez_frameworku == ["technologies/python.md"]),
            (f"bez technologii: tylko plik plannera: {bez_technologii}", bez_technologii == ["guide_goals.md"]),
            ("tekst wiedzy w znaczniku z nazwą pliku", tekst.startswith('<plik_wiedzy nazwa="technologies/python.md">') and tekst.endswith("</plik_wiedzy>")),
            ("brak plików wiedzy: zdanie o braku", tekst_pusty == "(brak plików wiedzy)"),
            ("nazwa poza bazą wiedzy odrzucona (ValueError)", zly_plik_odrzucony),
            ("numerowanie: numery od 1, bez pustej linii na końcu", number_lines("a\nb\n") == "    1| a\n    2| b"),
            ("numerowanie: pusty tekst", number_lines("") == ""),
            ("numerowanie od podanej linii (kawałek pliku)", number_lines("a\nb\n", 10) == "   10| a\n   11| b"),
            ("cut_lines: zakres linii włącznie, bez końcowego znaku nowej linii", cut_lines("a\nb\nc\nd\n", 2, 3) == "b\nc"),
            ("cut_lines: cały tekst i pusty tekst", cut_lines("a\nb\n", 1, 2) == "a\nb" and cut_lines("", 1, 0) == ""),
            ("liczenie linii: z końcowym znakiem nowej linii, bez niego i pusty tekst", count_lines("a\nb\n") == 2 and count_lines("a\nb") == 2 and count_lines("") == 0),
        ]
        return wyniki

    def manual_test():
        """Uruchamia sprawdzenia wspólnych narzędzi agentów i wypisuje werdykt.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że wiedza i numeracja są gotowe dla analityka.
        """
        wszystkie_zgodne = True
        for opis, zgodne in _checks():
            print(f"  {opis}: {zgodne}")
            if not zgodne:
                wszystkie_zgodne = False
        print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")

    manual_test()
