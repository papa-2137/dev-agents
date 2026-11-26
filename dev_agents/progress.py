"""Podgląd postępu: linie "[godzina] etap: co się dzieje" wypisywane w trakcie przebiegu grafu.

Co robi: udostępnia trzy rzeczy.
    - format_line / format_seconds - skład jednej linii (godzina, nazwa etapu, tekst) i czasu po polsku ("0,4 s"),
    - print_line - funkcja drukująca linię na ekranie z natychmiastowym opróżnieniem bufora; to ją main.py
      podaje grafowi jako RunContext.report,
    - Stage - menedżer kontekstu owijający pracę węzła: wypisuje "start", po zakończeniu "gotowe w X s - wynik",
      a gdy węzeł rzuci wyjątek - "BŁĄD po X s - Typ: komunikat" i puszcza wyjątek dalej (przebieg i tak się przerywa).
      W trakcie pracy węzeł może dopisać linię postępu (note), np. "analiza 3/7".

Dlaczego istnieje: węzły planner, analityk i pisarz będą pracować po minucie lub więcej, bo wołają model; bez linii
na ekranie nie widać, czy program działa, czy się zawiesił. Linie powstają w węzłach i płyną przez funkcję report
z kontekstu, a nie przez strumieniowanie LangGraph: tryb tasks wymaga checkpointera, tryb updates nie ma zdarzenia
startu, a funkcja report da się podstawić w teście (lista zamiast ekranu) i działa tak samo dla węzłów równoległych.

Rola: moduł pomocniczy rdzenia towaru; Stage używają węzły grafu (graph.py), print_line podaje main.py.

Test ręczny (z katalogu głównego repo; bez sieci, bez modeli, bez LangGraph):
    python -m dev_agents.progress
        pokazuje na ekranie prawdziwe linie (etap udany z postępem i etap z błędem), potem sprawdza format linii,
        format czasu, liczbę i treść linii oraz to, że wyjątek z etapu nie jest połykany; na końcu "zgodne z oczekiwaniem: True".
"""

import datetime
import time
import typing


# --- Skład linii ---


def format_seconds(
    seconds: float,
) -> str:
    """Zwraca czas z jednym miejscem po przecinku i jednostką po polsku, np. 0,4 s albo 75,3 s.

    Po co: jeden zapis czasu we wszystkich liniach postępu.
    """
    liczba = f"{seconds:.1f}"
    tekst = liczba.replace(".", ",") + " s"
    return tekst


def format_line(
    stage: str,
    text: str,
    now: datetime.datetime | None = None,
) -> str:
    """Składa linię "[GG:MM:SS] etap: tekst"; bez podanego czasu bierze bieżący.

    Po co: jeden zapis linii postępu; parametr now istnieje po to, żeby test mógł podać stałą godzinę.
    """
    if now is None:
        now = datetime.datetime.now()
    godzina = now.strftime("%H:%M:%S")
    linia = f"[{godzina}] {stage}: {text}"
    return linia


def print_line(
    line: str,
) -> None:
    """Wypisuje gotową linię na ekranie i od razu opróżnia bufor.

    Po co: to jest funkcja report, którą main.py podaje grafowi; opróżnienie bufora sprawia, że linia pojawia się
    w chwili zdarzenia, także gdy wyjście jest przekierowane do pliku albo potoku.
    """
    print(line, flush=True)


# --- Etap ---


class Stage:
    """Menedżer kontekstu jednego etapu pracy: wypisuje start, koniec z czasem albo błąd z czasem.

    Po co: każdy węzeł grafu owija swoją pracę w "with Stage(report, nazwa) as etap:" i ma za darmo start, czas,
    wynik i widoczny błąd, bez powtarzania tego kodu w każdym węźle.
    """

    def __init__(
        self,
        report: typing.Callable[[str], None],
        name: str,
    ) -> None:
        """Zapamiętuje funkcję raportującą i nazwę etapu; czas startu ustawia dopiero wejście do bloku with.

        Po co: obiekt jest tani w tworzeniu i niczego nie wypisuje, dopóki blok nie ruszy.
        """
        self._report = report
        self._name = name
        self._started = 0.0
        self._result = ""

    def __enter__(
        self,
    ) -> "Stage":
        """Wypisuje linię startu i zaczyna odmierzać czas.

        Po co: linia startu pojawia się, zanim zacznie się długa praca - ekran nie stoi pusty.
        """
        self._started = time.monotonic()
        self._report(format_line(self._name, "start"))
        return self

    def note(
        self,
        text: str,
    ) -> None:
        """Wypisuje linię postępu w trakcie pracy etapu, np. "analiza 3/7".

        Po co: długi etap może meldować, na jakim kawałku pracy jest.
        """
        self._report(format_line(self._name, text))

    def set_result(
        self,
        text: str,
    ) -> None:
        """Zapamiętuje krótki wynik, który trafi do linii zakończenia, np. "python, 3 pliki".

        Po co: koniec etapu mówi nie tylko "gotowe", ale i co powstało.
        """
        self._result = text

    def __exit__(
        self,
        exc_type,
        exc_value,
        exc_traceback,
    ) -> bool:
        """Wypisuje linię zakończenia albo błędu z czasem trwania; wyjątku nie połyka.

        Po co: błąd węzła jest widoczny w chwili, gdy nastąpił, z nazwą etapu i czasem; sam wyjątek leci dalej
        i przerywa przebieg (zwrócone False znaczy: nie obsłużyłem go).
        """
        czas = format_seconds(time.monotonic() - self._started)
        if exc_type is None:
            tekst = f"gotowe w {czas}"
            if self._result:
                tekst = f"{tekst} - {self._result}"
        else:
            tekst = f"BŁĄD po {czas} - {exc_type.__name__}: {exc_value}"
        self._report(format_line(self._name, tekst))
        return False


# --- Test ręczny ---

if __name__ == "__main__":
    import re

    def _show_real_lines() -> None:
        """Pokazuje na ekranie prawdziwe linie postępu: etap udany z postępem i etap z błędem.

        Po co: widać, jak to wygląda w konsoli, zanim sprawdzimy szczegóły.
        """
        print("=== Linie na ekranie ===")
        with Stage(print_line, "scan") as etap:
            time.sleep(0.2)
            etap.note("połowa plików")
            time.sleep(0.2)
            etap.set_result("python, 3 plików, 2 punkty wejścia")
        try:
            with Stage(print_line, "analyst") as etap:
                time.sleep(0.1)
                raise ValueError("model zwrócił pustą odpowiedź")
        except ValueError:
            print("(wyjątek doleciał do wołającego - przebieg by się tu przerwał)")

    def _run_cases() -> list[tuple[str, bool]]:
        """Sprawdza format linii i czasu oraz zachowanie etapu (udany, z postępem, bez wyniku, z błędem); zwraca (opis, zgodne).

        Po co: wynik testu to lista przypadków z werdyktem, bez zgadywania z wydruku.
        """
        przypadki = []
        stala_godzina = datetime.datetime(2026, 11, 26, 21, 52, 7)
        przypadki.append(("format_line ze stałą godziną", format_line("scan", "start", stala_godzina) == "[21:52:07] scan: start"))
        przypadki.append(("format_seconds 0,04 s", format_seconds(0.04) == "0,0 s"))
        przypadki.append(("format_seconds 75,26 s", format_seconds(75.26) == "75,3 s"))

        linie = []
        with Stage(linie.append, "scan") as etap:
            etap.note("połowa")
            etap.set_result("python, 3 pliki")
        przypadki.append(("etap udany: 3 linie (start, postęp, koniec)", len(linie) == 3))
        przypadki.append(("linia startu", linie[0].endswith("] scan: start")))
        przypadki.append(("linia postępu", linie[1].endswith("] scan: połowa")))
        wzorzec_konca = re.compile(r"^\[\d\d:\d\d:\d\d\] scan: gotowe w \d+,\d s - python, 3 pliki$")
        przypadki.append(("linia końca z czasem i wynikiem", wzorzec_konca.match(linie[2]) is not None))

        linie_bez_wyniku = []
        with Stage(linie_bez_wyniku.append, "writer"):
            pass
        wzorzec_bez_wyniku = re.compile(r"^\[\d\d:\d\d:\d\d\] writer: gotowe w \d+,\d s$")
        przypadki.append(("koniec bez wyniku nie ma myślnika", wzorzec_bez_wyniku.match(linie_bez_wyniku[1]) is not None))

        linie_bledu = []
        wyjatek_dolecial = False
        try:
            with Stage(linie_bledu.append, "analyst"):
                raise ValueError("zepsute")
        except ValueError:
            wyjatek_dolecial = True
        przypadki.append(("wyjątek nie jest połykany", wyjatek_dolecial))
        wzorzec_bledu = re.compile(r"^\[\d\d:\d\d:\d\d\] analyst: BŁĄD po \d+,\d s - ValueError: zepsute$")
        przypadki.append(("linia błędu z czasem, typem i komunikatem", len(linie_bledu) == 2 and wzorzec_bledu.match(linie_bledu[1]) is not None))
        return przypadki

    def manual_test():
        """Pokazuje linie na ekranie, sprawdza przypadki i wypisuje werdykt.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że podgląd postępu działa zgodnie z opisem.
        """
        _show_real_lines()
        print("\n=== Sprawdzenia ===")
        wszystkie_zgodne = True
        for opis, zgodne in _run_cases():
            print(f"  {opis}: {zgodne}")
            if not zgodne:
                wszystkie_zgodne = False
        print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")

    manual_test()
