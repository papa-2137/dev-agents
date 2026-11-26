"""Długie jednostki po kawałkach: podział kodu na kawałki i składanie notatek kawałków w jedną notatkę.

Co robi: udostępnia cztery funkcje zwykłego kodu (bez modelu), z których korzysta analityk.
    - split_ranges() dzieli plik na zakresy linii nie dłuższe niż chunk_lines: cięcie po granicy jednostki (koniec
      funkcji albo klasy z units()), a gdy żadna granica nie jest w zasięgu - w środku, z zakładem kilku linii,
    - plan_chunks() układa z plików jednostki kawałki: krótkie pliki trafiają razem do jednego kawałka (aż do limitu
      linii), długi plik jest cięty split_ranges(); jednostka krótsza niż limit to jeden kawałek,
    - build_previous_summary() składa z notatek poprzednich kawałków krótkie podsumowanie dla następnego kawałka,
    - merge_chunk_notes() składa notatki kawałków w jedną ModuleNote: teksty łączone, listy bez powtórzeń (zakład
      kawałków nie duplikuje czynności), ustawienia z tym samym kluczem łączą miejsca użycia.

Dlaczego istnieje: robot "spaghetti" ma funkcje na setki linii; model czytający całość naraz gubi szczegóły. Kawałki
czytane po kolei, każdy z podsumowaniem poprzednich, dają opis oparty na całym kodzie, a granice cięć liczy kod
(nie model), więc zakresy linii są pewne.

Czego NIE robi: nie woła modelu, nie czyta plików (dostaje liczby linii i granice), nie zna promptów.

Rola: moduł pomocniczy analityka (analyst.py); w kroku 52 analitycy z grafu korzystają z niego przez analyze_unit().

Test ręczny (z katalogu głównego repo; bez sieci i kluczy):
    python -m dev_agents.agents.chunks
        sprawdza podział na zakresy (granice jednostek, cięcie w środku z zakładem, pokrycie wszystkich linii, brak
        zakresu dłuższego niż limit), układanie kawałków z kilku plików, opis kawałka, podsumowanie poprzednich
        kawałków oraz składanie notatek (powtórzenia, łączenie miejsc użycia, komplet pól ModuleNote);
        na końcu "zgodne z oczekiwaniem: True".
"""

import dev_agents.schemas as _schemas

# Najwięcej tytułów czynności z jednego poprzedniego kawałka w podsumowaniu dla następnego.
_MAX_SUMMARY_ACTIONS = 8

# Pola ModuleNote składane przez merge_chunk_notes: listy tekstów bez powtórzeń.
_STRING_LIST_FIELDS = [
    "key_functions",
    "process_steps",
    "error_handling",
    "inputs",
    "outputs",
    "external_dependencies",
    "extension_points",
    "conventions",
    "maintainer_hints",
]

# Listy obiektów bez powtórzeń: pole -> pola tworzące klucz powtórzenia.
_OBJECT_LIST_FIELDS = {
    "actions": ["title", "function", "line"],
    "requirements": ["kind", "name"],
    "risky_places": ["place", "location", "kind"],
    "possible_failures": ["symptom", "where"],
    "glossary_candidates": ["term"],
}


# --- Podział na kawałki ---


def split_ranges(
    total_lines: int,
    cut_points: list[int],
    chunk_lines: int,
    overlap_lines: int,
) -> list[tuple[int, int]]:
    """Zwraca zakresy linii (od, do) pokrywające plik o total_lines liniach, każdy nie dłuższy niż chunk_lines.

    Po co: kawałek ma kończyć się na końcu funkcji albo klasy, żeby model nie dostał pół funkcji. Cięcie wypada na
    najdalszej granicy z cut_points (koniec jednostki) leżącej w drugiej połowie kawałka; gdy takiej granicy nie
    ma (jednostka dłuższa niż kawałek), plik jest cięty w środku, a następny kawałek zaczyna się overlap_lines
    linii wcześniej (zakład, żeby przerwana funkcja nie urwała kontekstu).

    Uwaga: overlap_lines musi być mniejszy niż połowa chunk_lines (pilnuje config), inaczej cięcie w środku
    nie posuwałoby się naprzód.
    """
    zakresy = []
    poczatek = 1
    while poczatek <= total_lines:
        limit = poczatek + chunk_lines - 1
        if limit >= total_lines:
            zakresy.append((poczatek, total_lines))
            break
        najmniejsza_granica = poczatek + chunk_lines // 2
        koniec = 0
        for punkt in cut_points:
            if najmniejsza_granica <= punkt <= limit and punkt > koniec:
                koniec = punkt
        if koniec > 0:
            zakresy.append((poczatek, koniec))
            poczatek = koniec + 1
        else:
            zakresy.append((poczatek, limit))
            poczatek = limit + 1 - overlap_lines
    return zakresy


def plan_chunks(
    files: list[tuple[str, int]],
    cut_points: dict[str, list[int]],
    chunk_lines: int,
    overlap_lines: int,
) -> list[list[tuple[str, int, int]]]:
    """Zwraca kawałki jednostki: listę kawałków, każdy to lista segmentów (plik, od linii, do linii); zawsze co najmniej jeden kawałek.

    Po co: jednostka krótsza niż chunk_lines to jeden kawałek (jak dotąd, jedna para wywołań modelu). Plik krótszy niż
    limit jest niepodzielny i dzieli kawałek z innymi krótkimi plikami; dłuższy jest cięty przez split_ranges().

    Argumenty: files - (ścieżka, liczba linii) w kolejności jednostki; cut_points - ścieżka -> końce jednostek pliku.
    """
    segmenty = []
    for sciezka, liczba_linii in files:
        if liczba_linii <= chunk_lines:
            segmenty.append((sciezka, 1, liczba_linii))
        else:
            for poczatek, koniec in split_ranges(liczba_linii, cut_points.get(sciezka, []), chunk_lines, overlap_lines):
                segmenty.append((sciezka, poczatek, koniec))
    kawalki = []
    biezacy = []
    suma_linii = 0
    for segment in segmenty:
        dlugosc = segment[2] - segment[1] + 1
        if len(biezacy) > 0 and suma_linii + dlugosc > chunk_lines:
            kawalki.append(biezacy)
            biezacy = []
            suma_linii = 0
        biezacy.append(segment)
        suma_linii += dlugosc
    kawalki.append(biezacy)
    return kawalki


def describe_chunk(
    chunk: list[tuple[str, int, int]],
) -> str:
    """Zwraca opis kawałka do promptu i postępu, np. "przetwarzanie.py: linie 301-580; raport.py: linie 1-40".

    Po co: model i człowiek widzą, który fragment kodu jest teraz analizowany.
    """
    czesci = []
    for sciezka, od_linii, do_linii in chunk:
        czesci.append(f"{sciezka}: linie {od_linii}-{do_linii}")
    opis = "; ".join(czesci)
    return opis


# --- Podsumowanie poprzednich kawałków ---


def build_previous_summary(
    notes: list[_schemas.ModuleNote],
    descriptions: list[str],
) -> str:
    """Zwraca podsumowanie poprzednich kawałków: dla każdego opis zakresu, cel i tytuły pierwszych czynności; bez poprzednich kawałków - zdanie o braku.

    Po co: kolejny kawałek wie, co robot zrobił do tej pory (np. że plik został już wczytany), więc opisuje swoją
    część w kontekście całości. Podsumowanie składa kod z notatek - bez dodatkowego wywołania modelu.
    """
    if len(notes) == 0:
        tekst_braku = "(brak - to pierwszy kawałek)"
        return tekst_braku
    linie = []
    for numer, notatka in enumerate(notes, start=1):
        linia = f"Kawałek {numer} ({descriptions[numer - 1]}): {notatka.purpose}"
        tytuly = []
        for czynnosc in notatka.actions[:_MAX_SUMMARY_ACTIONS]:
            tytuly.append(czynnosc.title)
        if len(tytuly) > 0:
            linia = f"{linia} Czynności: {'; '.join(tytuly)}."
        linie.append(linia)
    tekst = "\n".join(linie)
    return tekst


# --- Składanie notatek kawałków ---


def _unique(
    items: list,
    key_fields: list[str],
) -> list:
    """Zwraca elementy bez powtórzeń z zachowaniem kolejności; klucz powtórzenia to wartości pól key_fields (puste key_fields - sam element).

    Po co: zakład kawałków i powtarzające się opisy nie mogą dublować wpisów w złożonej notatce.
    """
    wynik = []
    widziane = set()
    for element in items:
        klucz = element
        if len(key_fields) > 0:
            czesci = []
            for nazwa in key_fields:
                czesci.append(getattr(element, nazwa))
            klucz = tuple(czesci)
        if klucz in widziane:
            continue
        widziane.add(klucz)
        wynik.append(element)
    return wynik


def _join_unique_texts(
    texts: list[str],
    separator: str,
) -> str:
    """Zwraca niepuste teksty bez powtórzeń połączone separatorem; same puste teksty dają pusty tekst.

    Po co: pola tekstowe notatki (cel, aplikacje) składają się z fragmentów z kolejnych kawałków.
    """
    niepuste = []
    for tekst in texts:
        if tekst != "":
            niepuste.append(tekst)
    polaczony = separator.join(_unique(niepuste, []))
    return polaczony


def _merge_settings(
    settings: list[_schemas.NoteSetting],
) -> list[_schemas.NoteSetting]:
    """Zwraca ustawienia bez powtórzeń; wpisy z tym samym plikiem, sekcją, kluczem, miejscem i wartością łączą miejsca użycia.

    Po co: to samo ustawienie bywa użyte w kilku kawałkach - w notatce ma być jednym wpisem ze wszystkimi miejscami użycia.
    """
    wynik = []
    indeksy = {}
    for ustawienie in settings:
        klucz = (ustawienie.file, ustawienie.group, ustawienie.key, ustawienie.location, ustawienie.value)
        if klucz not in indeksy:
            indeksy[klucz] = len(wynik)
            wynik.append(ustawienie)
            continue
        istniejace = wynik[indeksy[klucz]]
        miejsca = list(istniejace.used_in)
        for miejsce in ustawienie.used_in:
            if miejsce not in miejsca:
                miejsca.append(miejsce)
        wynik[indeksy[klucz]] = istniejace.model_copy(update={"used_in": miejsca})
    return wynik


def _collect_field(
    notes: list[_schemas.ModuleNote],
    field_name: str,
) -> list:
    """Zwraca wartości jednego pola ze wszystkich notatek w kolejności kawałków (dla pola listowego - listy złączone w jedną).

    Po co: składanie każdego pola zaczyna się od zebrania wartości z kawałków.
    """
    wartosci = []
    for notatka in notes:
        wartosc = getattr(notatka, field_name)
        if isinstance(wartosc, list):
            wartosci.extend(wartosc)
        else:
            wartosci.append(wartosc)
    return wartosci


def merge_chunk_notes(
    notes: list[_schemas.ModuleNote],
) -> _schemas.ModuleNote:
    """Składa notatki kolejnych kawałków w jedną ModuleNote; jedna notatka wraca bez zmian.

    Po co: dalsze etapy dostają jedną notatkę o jednostce, bez względu na to, w ilu kawałkach ją analizowano.
    Cel i aplikacje to teksty kawałków połączone bez powtórzeń, rola w przepływie - pierwsza niepusta, listy tekstów
    i obiektów - złączone w kolejności kawałków (czyli linii) bez powtórzeń, ustawienia - z łączeniem miejsc użycia.

    Uwaga: notes nie może być puste. Test pilnuje, że każde pole ModuleNote jest obsłużone.
    """
    pierwsza = notes[0]
    if len(notes) == 1:
        return pierwsza
    dane = {}
    dane["unit_name"] = pierwsza.unit_name
    dane["purpose"] = _join_unique_texts(_collect_field(notes, "purpose"), " ")
    dane["automated_application"] = _join_unique_texts(_collect_field(notes, "automated_application"), "; ")
    rola = ""
    for tekst in _collect_field(notes, "flow_role"):
        if rola == "" and tekst != "":
            rola = tekst
    dane["flow_role"] = rola
    for nazwa in _STRING_LIST_FIELDS:
        dane[nazwa] = _unique(_collect_field(notes, nazwa), [])
    for nazwa, pola_klucza in _OBJECT_LIST_FIELDS.items():
        dane[nazwa] = _unique(_collect_field(notes, nazwa), pola_klucza)
    dane["settings"] = _merge_settings(_collect_field(notes, "settings"))
    polaczona = _schemas.ModuleNote(**dane)
    return polaczona


# --- Test ręczny ---

if __name__ == "__main__":

    def _note(
        purpose: str,
        flow_role: str,
        action_titles: list[str],
        action_line: int,
        used_in: list[str],
    ) -> _schemas.ModuleNote:
        """Składa małą notatkę testową: cel, rola, czynności o podanych tytułach (linia action_line), jedno ustawienie URL z miejscami użycia i wspólne wpisy list.

        Po co: dane do sprawdzenia składania notatek kawałków.
        """
        czynnosci = []
        for tytul in action_titles:
            czynnosci.append(_schemas.NoteAction(title=tytul, kind="step", function="run", line=action_line, description="", reads=[], writes=[], certain=True))
        ustawienie = _schemas.NoteSetting(
            file="",
            location="main.py:3",
            group="",
            key="URL",
            value="http://x",
            kind="system",
            plain_password=False,
            meaning="Adres.",
            used_in=used_in,
            certain=True,
        )
        notatka = _schemas.ModuleNote(
            unit_name="main.py",
            purpose=purpose,
            flow_role=flow_role,
            automated_application="strona x",
            key_functions=["run:10 - robot"],
            actions=czynnosci,
            process_steps=[f"Krok z {purpose}"],
            error_handling=[],
            inputs=[],
            outputs=[],
            settings=[ustawienie],
            requirements=[_schemas.NoteRequirement(kind="network", name="http://x:80", detail="Adres.")],
            external_dependencies=["requests - żądania"],
            risky_places=[],
            possible_failures=[],
            extension_points=[],
            conventions=[],
            maintainer_hints=[],
            glossary_candidates=[],
        )
        return notatka

    def _covers_all_lines(
        total_lines: int,
        ranges: list[tuple[int, int]],
        chunk_lines: int,
    ) -> bool:
        """Zwraca True, gdy zakresy pokrywają linie 1..total_lines i żaden nie jest dłuższy niż chunk_lines.

        Po co: żadna linia kodu nie może wypaść z analizy, a kawałek musi mieścić się w limicie.
        """
        pokryte = set()
        for od_linii, do_linii in ranges:
            if do_linii - od_linii + 1 > chunk_lines:
                return False
            for numer in range(od_linii, do_linii + 1):
                pokryte.add(numer)
        wszystkie = set(range(1, total_lines + 1))
        zgodne = pokryte == wszystkie
        return zgodne

    def _checks() -> list[tuple[str, bool]]:
        """Sprawdza podział na zakresy, układanie kawałków, opis, podsumowanie i składanie notatek; zwraca (opis, zgodne).

        Po co: cała logika modułu bez modelu i bez plików.
        """
        granice = [100, 250, 280, 500, 640]
        wszystkie_zakresy_ok = True
        for razem in (1, 299, 300, 301, 700, 1500):
            zakresy_testowe = split_ranges(razem, granice, 300, 10)
            if not _covers_all_lines(razem, zakresy_testowe, 300):
                wszystkie_zakresy_ok = False
            zakresy_bez_granic = split_ranges(razem, [], 300, 10)
            if not _covers_all_lines(razem, zakresy_bez_granic, 300):
                wszystkie_zakresy_ok = False
        kawalki = plan_chunks([("a.py", 700), ("b.py", 40)], {"a.py": granice}, 300, 10)
        kawalki_krotkie = plan_chunks([("a.py", 100), ("b.py", 150)], {}, 300, 10)
        kawalki_pustego = plan_chunks([("pusty.py", 0)], {}, 300, 10)
        brak_plikow = plan_chunks([], {}, 300, 10)
        notatka_1 = _note("Pierwszy kawałek.", "", ["Wczytaj plik", "Wyślij"], 5, ["main.py:20"])
        notatka_2 = _note("Drugi kawałek.", "Wołana z run.bat.", ["Wyślij", "Zapisz wynik"], 5, ["main.py:20", "main.py:300"])
        notatka_3 = _note("Trzeci kawałek.", "Inna rola.", ["Wyślij"], 400, [])
        polaczona = merge_chunk_notes([notatka_1, notatka_2, notatka_3])
        tytuly = []
        for czynnosc in polaczona.actions:
            tytuly.append(f"{czynnosc.title}@{czynnosc.line}")
        pola_obsluzone = ["unit_name", "purpose", "flow_role", "automated_application", "settings"] + _STRING_LIST_FIELDS + list(_OBJECT_LIST_FIELDS)
        podsumowanie = build_previous_summary([notatka_1, notatka_2], ["main.py: linie 1-280", "main.py: linie 281-500"])
        wyniki = [
            ("zakresy: granice jednostek w drugiej połowie kawałka", split_ranges(700, granice, 300, 10) == [(1, 280), (281, 500), (501, 700)]),
            ("zakresy: bez granic cięcie w środku z zakładem 10 linii", split_ranges(700, [], 300, 10) == [(1, 300), (291, 590), (581, 700)]),
            ("zakresy: granica za wcześnie (przed połową kawałka) jest pomijana", split_ranges(700, [5], 300, 10)[0] == (1, 300)),
            ("zakresy: krótki plik to jeden zakres", split_ranges(250, granice, 300, 10) == [(1, 250)]),
            ("zakresy: każda linia pokryta, żaden zakres dłuższy niż limit", wszystkie_zakresy_ok),
            ("kawałki: długi plik w trzech kawałkach, krótki plik dołączony do ostatniego", kawalki == [[("a.py", 1, 280)], [("a.py", 281, 500)], [("a.py", 501, 700), ("b.py", 1, 40)]]),
            ("kawałki: dwa krótkie pliki razem w jednym kawałku", kawalki_krotkie == [[("a.py", 1, 100), ("b.py", 1, 150)]]),
            ("kawałki: pusty plik i brak plików dają jeden kawałek", kawalki_pustego == [[("pusty.py", 1, 0)]] and brak_plikow == [[]]),
            ("opis kawałka z dwóch plików", describe_chunk(kawalki[2]) == "a.py: linie 501-700; b.py: linie 1-40"),
            ("podsumowanie: bez poprzednich kawałków zdanie o braku", "pierwszy kawałek" in build_previous_summary([], [])),
            ("podsumowanie: opis zakresu, cel i czynności poprzednich kawałków", "Kawałek 2 (main.py: linie 281-500): Drugi kawałek. Czynności: Wyślij; Zapisz wynik." in podsumowanie and "Kawałek 1 (main.py: linie 1-280): Pierwszy kawałek." in podsumowanie),
            ("składanie: jedna notatka wraca bez zmian", merge_chunk_notes([notatka_1]) is notatka_1),
            ("składanie: cele połączone, rola pierwsza niepusta (późniejsze kawałki jej nie nadpisują)", polaczona.purpose == "Pierwszy kawałek. Drugi kawałek. Trzeci kawałek." and polaczona.flow_role == "Wołana z run.bat."),
            (f"składanie: czynności bez powtórzeń (ten sam tytuł i linia), ten sam tytuł w innej linii zostaje ({tytuly})", tytuly == ["Wczytaj plik@5", "Wyślij@5", "Zapisz wynik@5", "Wyślij@400"]),
            ("składanie: ustawienie z tym samym kluczem to jeden wpis z sumą miejsc użycia", len(polaczona.settings) == 1 and polaczona.settings[0].used_in == ["main.py:20", "main.py:300"]),
            ("składanie: listy tekstów i wymagania bez powtórzeń", polaczona.key_functions == ["run:10 - robot"] and len(polaczona.requirements) == 1 and polaczona.external_dependencies == ["requests - żądania"] and len(polaczona.process_steps) == 3),
            ("składanie: obsłużone są wszystkie pola ModuleNote", sorted(pola_obsluzone) == sorted(_schemas.ModuleNote.model_fields)),
        ]
        return wyniki

    def manual_test():
        """Uruchamia sprawdzenia i wypisuje werdykt.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że podział na kawałki i składanie notatek działają.
        """
        wszystkie_zgodne = True
        for opis, zgodne in _checks():
            print(f"  {opis}: {zgodne}")
            if not zgodne:
                wszystkie_zgodne = False
        print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")

    manual_test()
