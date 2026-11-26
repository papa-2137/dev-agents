"""Oznaczanie terminów słowniczka w tekście przewodnika: termin dostaje podpowiedź z definicją po najechaniu.

Co robi: build_index() składa z listy terminów słowniczka indeks (wzór wyszukiwania i definicje), mark_terms()
zamienia zwykły tekst na bezpieczny HTML, w którym każde wystąpienie terminu jest owinięte w <span class="tm"> z
atrybutami data-t (termin) i data-d (definicja); skrypt przewodnika pokazuje z nich dymek. Dopasowanie jest dokładne
(bez odmiany), nie rozróżnia wielkości liter i oznacza tylko całe słowa: „kolejka” nie jest oznaczana w „kolejkarz”.
Przy kilku pasujących terminach wygrywa najdłuższy („kolejka zadań” przed „kolejka”).

Dlaczego istnieje: definicje słowniczka mają być pod ręką tam, gdzie termin pada w tekście, a nie tylko w sekcji
Pojęcia. Wyszukiwanie działa na tekście przed escapowaniem, a każdy kawałek jest escapowany osobno, więc tekst od
agentów (np. "<script>", cudzysłów, "&#39;") nigdy nie trafia do strony jako znaczniki, a termin zbudowany z cyfr nie
zostanie znaleziony wewnątrz encji HTML.

Czego NIE robi: nie oznacza tekstu budowanego w przeglądarce (opisy klocków diagramu, wiersze „Krok po kroku”,
dymki), nie oznacza samego słowniczka, kodu, nazw plików ani wartości konfiguracji - te miejsca renderer w ogóle nie
przepuszcza przez filtr.

Rola: moduł rdzenia towaru, wołany przez render.py (filtr szablonu „terms”).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.glossary
        wypisuje wyniki oznaczania dla przypadków granicznych (termin wewnątrz słowa, wielkość liter, najdłuższy termin,
        HTML i cudzysłów w tekście i definicji, znaki specjalne wyrażeń regularnych, termin z cyfr obok encji, brak
        terminów) i na końcu „zgodne z oczekiwaniem: True” albo wypisuje, który przypadek się nie zgadza
"""

import re

import markupsafe

import dev_agents.guide_content as _content

_SPAN_TEMPLATE = '<span class="tm" tabindex="0" data-t="{}" data-d="{}">{}</span>'
_WORD_START = r"(?<!\w)"
_WORD_END = r"(?!\w)"


def build_index(
    terms: list[_content.GlossaryTerm],
) -> dict:
    """Zwraca indeks terminów {pattern: skompilowany wzór albo None, definitions: {termin małymi literami: {term, definition}}}.

    Po co: wzór kompilujemy raz na przewodnik; termin pusty albo bez definicji pomijamy (dymek bez treści nic nie
    daje), a powtórzony termin (bez względu na wielkość liter) liczy się pierwszy.
    """
    definicje = {}
    for pojecie in terms:
        nazwa = pojecie.term.strip()
        opis = pojecie.definition.strip()
        klucz = nazwa.casefold()
        if nazwa and opis and klucz not in definicje:
            definicje[klucz] = {"term": nazwa, "definition": opis}
    wzor = None
    if definicje:
        nazwy = []
        for pozycja in definicje.values():
            nazwy.append(pozycja["term"])
        nazwy.sort(key=len, reverse=True)
        alternatywy = []
        for nazwa in nazwy:
            alternatywy.append(re.escape(nazwa))
        wzor = re.compile(_WORD_START + "(?:" + "|".join(alternatywy) + ")" + _WORD_END, re.IGNORECASE)
    indeks = {"pattern": wzor, "definitions": definicje}
    return indeks


def mark_terms(
    text: str,
    index: dict,
) -> markupsafe.Markup:
    """Zwraca bezpieczny HTML tekstu z oznaczonymi terminami słowniczka (każde wystąpienie osobno).

    Po co: filtr szablonu „terms”; wyszukiwanie na tekście surowym, escapowanie osobno dla każdego kawałka i dla
    atrybutów (markupsafe), więc wynik nie wymaga dalszego escapowania. Bez terminów zwraca sam escapowany tekst.
    """
    tekst = str(text)
    wzor = index["pattern"]
    kawalki = []
    pozycja = 0
    if wzor is not None:
        for trafienie in wzor.finditer(tekst):
            definicja = index["definitions"].get(trafienie.group(0).casefold())
            if definicja is not None:
                kawalki.append(markupsafe.escape(tekst[pozycja : trafienie.start()]))
                kawalki.append(markupsafe.Markup(_SPAN_TEMPLATE).format(definicja["term"], definicja["definition"], trafienie.group(0)))
                pozycja = trafienie.end()
    kawalki.append(markupsafe.escape(tekst[pozycja:]))
    wynik = markupsafe.Markup("").join(kawalki)
    return wynik


# --- Test ręczny ---

if __name__ == "__main__":

    def _term(
        term: str,
        definition: str,
    ) -> _content.GlossaryTerm:
        """Składa pojęcie słowniczka do testu.

        Po co: krótszy zapis przypadków testowych.
        """
        pojecie = _content.GlossaryTerm(term=term, definition=definition)
        return pojecie

    def _span(
        term: str,
        definition: str,
        shown: str,
    ) -> str:
        """Zwraca oczekiwany znacznik terminu (bez escapowania - tylko dla znaków bezpiecznych).

        Po co: oczekiwane wyniki testu bez powielania szablonu w każdym przypadku.
        """
        wynik = f'<span class="tm" tabindex="0" data-t="{term}" data-d="{definition}">{shown}</span>'
        return wynik

    def manual_test():
        """Wypisuje oznaczanie dla przypadków granicznych i porównuje z oczekiwaniem.

        Po co: sprawdzenie bezpieczeństwa (HTML, cudzysłów, encje) i granic słów bez uruchamiania przeglądarki.
        """
        indeks = build_index(
            [
                _term("kolejka", "lista zadań do wykonania"),
                _term("kolejka zadań", "kolejka z priorytetami"),
                _term("C++", "język; znak + nie jest znakiem specjalnym"),
                _term("a.b", "kropka nie jest dowolnym znakiem"),
                _term("39", "liczba z cyfr"),
                _term("pułapka", "def z \"cudzysłowem\" i <b>znacznikiem</b> & znakiem"),
                _term("pusty", ""),
                _term("  ", "termin pusty"),
                _term("Kolejka", "powtórzony termin - liczy się pierwszy"),
            ]
        )
        przypadki = [
            ("termin w zdaniu", "Robot czyta kolejka z pliku.", "Robot czyta " + _span("kolejka", "lista zadań do wykonania", "kolejka") + " z pliku."),
            ("wewnątrz słowa", "kolejkarz i prekolejka oraz kolejkaX", "kolejkarz i prekolejka oraz kolejkaX"),
            ("wielkość liter", "Kolejka na początku.", _span("kolejka", "lista zadań do wykonania", "Kolejka") + " na początku."),
            ("najdłuższy termin", "Wchodzi do kolejka zadań dziś.", "Wchodzi do " + _span("kolejka zadań", "kolejka z priorytetami", "kolejka zadań") + " dziś."),
            ("interpunkcja", "(kolejka), kolejka.", "(" + _span("kolejka", "lista zadań do wykonania", "kolejka") + "), " + _span("kolejka", "lista zadań do wykonania", "kolejka") + "."),
            ("znak specjalny wyrażenia", "Napisano w C++ lub w C--.", "Napisano w " + _span("C++", "język; znak + nie jest znakiem specjalnym", "C++") + " lub w C--."),
            ("kropka nie jest dowolnym znakiem", "a.b oraz axb", _span("a.b", "kropka nie jest dowolnym znakiem", "a.b") + " oraz axb"),
            ("termin z cyfr obok encji", "it's 39", "it&#39;s " + _span("39", "liczba z cyfr", "39")),
            ("HTML w tekście", "<b>kolejka</b> & \"x\"", "&lt;b&gt;" + _span("kolejka", "lista zadań do wykonania", "kolejka") + "&lt;/b&gt; &amp; &#34;x&#34;"),
            (
                "HTML w definicji",
                "To pułapka.",
                "To " + _span("pułapka", "def z &#34;cudzysłowem&#34; i &lt;b&gt;znacznikiem&lt;/b&gt; &amp; znakiem", "pułapka") + ".",
            ),
            ("termin bez definicji pominięty", "pusty tekst", "pusty tekst"),
            ("pusty tekst", "", ""),
        ]
        wszystkie_zgodne = True
        for nazwa, tekst, oczekiwane in przypadki:
            wynik = str(mark_terms(tekst, indeks))
            zgodny = wynik == oczekiwane
            znacznik = "OK"
            if not zgodny:
                wszystkie_zgodne = False
                znacznik = "BŁĄD"
            print(f"[{znacznik}] {nazwa}")
            print(f"    tekst:    {tekst!r}")
            print(f"    wynik:    {wynik}")
            if not zgodny:
                print(f"    oczekiwane: {oczekiwane}")
        bez_terminow = build_index([])
        wynik = str(mark_terms("Tekst <i>bez</i> terminów", bez_terminow))
        zgodny = wynik == "Tekst &lt;i&gt;bez&lt;/i&gt; terminów"
        znacznik = "OK"
        if not zgodny:
            wszystkie_zgodne = False
            znacznik = "BŁĄD"
        print(f"[{znacznik}] brak terminów: {wynik}")
        print(f"Terminów w indeksie: {len(indeks['definitions'])} (oczekiwane 6: kolejka, kolejka zadań, c++, a.b, 39, pułapka)")
        print(f"zgodne z oczekiwaniem: {wszystkie_zgodne}")

    manual_test()
