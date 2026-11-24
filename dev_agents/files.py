"""Bezpieczny odczyt plików analizowanego projektu jako tekstu, niezależnie od kodowania.

Co robi: czyta plik w trybie binarnym i sam ustala kodowanie:
    - plik z BOM (znacznik kodowania na początku): UTF-8, UTF-16 LE albo UTF-16 BE,
    - plik bez BOM: najpierw ścisły UTF-8; gdy się nie da - cp1250 (polski Windows); gdy i to się nie da -
      UTF-8 z zamianą złych bajtów na znak zastępczy.
Końce linii są ujednolicane do "\\n", tak jak przy zwykłym otwarciu pliku w trybie tekstowym.

Dlaczego istnieje: towar czyta cudze pliki - kod robota, requirements.txt, pliki .bat, konfigurację. Bywają
w UTF-16 (np. requirements.txt z `pip freeze` w Windows PowerShell 5.1) albo w cp1250 (starsze pliki
z polskiego Windows, zwłaszcza .bat i .ini). Zwykłe open(..., encoding="utf-8") przerywa wtedy działanie
albo psuje polskie znaki. Jedna funkcja rozwiązuje ten problem raz dla wszystkich modułów.

Rola: moduł używany przez skaner, moduły technologii i czytniki plików projektu (zależności, pliki
uruchamiające, konfiguracja). Nie zna znaczenia plików - zwraca tylko tekst.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.files
Dla każdego przypadku jedna linia: nazwa, wykryte kodowanie i początek tekstu. Pliki tymczasowe
(UTF-8 bez BOM i z BOM, UTF-16 BE, cp1250) powinny dać czytelne polskie znaki; requirements.txt
robota 01 (UTF-16) - czytelne nazwy paczek; przetwarzanie.py robota 02 - zwykły kod.
"""


# --- Rozpoznanie kodowania ---


def _decode_bytes(
    data: bytes,
) -> tuple[str, str]:
    """Zamienia bajty pliku na tekst i zwraca (tekst, użyte kodowanie); nigdy nie rzuca błędu dekodowania.

    Po co: cała decyzja o kodowaniu jest w jednym miejscu i da się ją sprawdzić na bajtach z pamięci,
    bez plików na dysku.

    Uwaga: plik bez BOM, który nie jest poprawnym UTF-8, jest czytany jako cp1250 - plik w innym
    kodowaniu 8-bitowym (np. cp1252) też przeczyta się jako cp1250 i pojedyncze znaki mogą być inne.
    Ścisły UTF-8 jest sprawdzany pierwszy, więc plik UTF-8 z polskimi znakami nigdy nie trafi do cp1250.
    Kodowanie "utf-8 (zamiana błędów)" oznacza, że w tekście są znaki zastępcze.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        wynik_bom_utf8 = (data[3:].decode("utf-8", errors="replace"), "utf-8 (BOM)")
        return wynik_bom_utf8
    if data.startswith(b"\xff\xfe"):
        wynik_utf16_le = (data[2:].decode("utf-16-le", errors="replace"), "utf-16-le (BOM)")
        return wynik_utf16_le
    if data.startswith(b"\xfe\xff"):
        wynik_utf16_be = (data[2:].decode("utf-16-be", errors="replace"), "utf-16-be (BOM)")
        return wynik_utf16_be

    try:
        wynik_utf8 = (data.decode("utf-8"), "utf-8")
        return wynik_utf8
    except UnicodeDecodeError:
        pass
    try:
        wynik_cp1250 = (data.decode("cp1250"), "cp1250")
        return wynik_cp1250
    except UnicodeDecodeError:
        pass
    wynik_zastepczy = (data.decode("utf-8", errors="replace"), "utf-8 (zamiana błędów)")
    return wynik_zastepczy


def _normalize_newlines(
    text: str,
) -> str:
    """Zamienia końce linii Windows ("\\r\\n") i stare Mac ("\\r") na "\\n".

    Po co: plik czytany binarnie zachowuje "\\r\\n"; po ujednoliceniu tekst wygląda tak samo jak przy
    zwykłym open() w trybie tekstowym, a numery linii się nie zmieniają.
    """
    tekst_bez_crlf = text.replace("\r\n", "\n")
    tekst_ujednolicony = tekst_bez_crlf.replace("\r", "\n")
    return tekst_ujednolicony


# --- Odczyt pliku ---


def _read_text_with_encoding(
    path: str,
) -> tuple[str, str]:
    """Czyta plik binarnie i zwraca (tekst z ujednoliconymi końcami linii, użyte kodowanie).

    Po co: wspólny środek read_text_safe() i testu ręcznego, który pokazuje także wykryte kodowanie.

    Uwaga: błędy systemu plików (brak pliku, brak uprawnień) nie są łapane - wołający dostaje zwykły
    OSError z nazwą pliku.
    """
    with open(path, "rb") as plik:
        data = plik.read()
    tekst, kodowanie = _decode_bytes(data)
    wynik = (_normalize_newlines(tekst), kodowanie)
    return wynik


def read_text_safe(
    path: str,
) -> str:
    """Zwraca treść pliku analizowanego projektu jako tekst: kodowanie rozpoznane z BOM albo z treści, końce linii "\\n".

    Po co: jedyne miejsce, przez które towar czyta cudze pliki tekstowe - UTF-16 i cp1250 nie psują
    odczytu w żadnym module, a zły bajt nigdy nie przerywa analizy.

    Uwaga: funkcja czyta cały plik do pamięci - limity rozmiaru (np. pomijanie dużych plików) sprawdza
    wołający przed odczytem.
    """
    tekst, _kodowanie = _read_text_with_encoding(path)
    return tekst


# --- Test ręczny ---

if __name__ == "__main__":
    import os
    import tempfile

    def _make_temp_file(
        data: bytes,
    ) -> str:
        """Zapisuje bajty do pliku tymczasowego i zwraca jego ścieżkę.

        Po co: przypadki kodowań (cp1250, UTF-16 BE, BOM) są tworzone w teście, bez dokładania plików do repo.
        """
        deskryptor, sciezka = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(deskryptor, "wb") as plik:
            plik.write(data)
        return sciezka

    def _describe_file(
        name: str,
        path: str,
    ) -> str:
        """Czyta plik przez _read_text_with_encoding() i zwraca linię opisu: nazwa, kodowanie, początek tekstu.

        Po co: jedna linia na przypadek - od razu widać, czy kodowanie zostało rozpoznane, a polskie znaki są czytelne.
        """
        if not os.path.exists(path):
            opis_braku = f"{name}: brak pliku {path} - pomijam"
            return opis_braku
        tekst, kodowanie = _read_text_with_encoding(path)
        poczatek = tekst[:70].replace("\n", " | ")
        opis = f"{name}: kodowanie={kodowanie}, początek: {poczatek!r}"
        return opis

    def _collect_descriptions() -> list[str]:
        """Tworzy pliki tymczasowe w czterech kodowaniach, opisuje je razem z plikami robotów testowych i usuwa pliki tymczasowe.

        Po co: logika testu bez wypisywania - wynik to gotowe linie do pokazania.

        Uwaga: z robota 01 czytany jest wyłącznie requirements.txt - katalog certs nie jest otwierany.
        """
        tekst_polski = "rem Wysyłka do księgowości\r\nrem zażółć gęślą jaźń\r\n"
        przypadki_tymczasowe = [
            ("tymczasowy UTF-8 bez BOM", tekst_polski.encode("utf-8")),
            ("tymczasowy UTF-8 z BOM", b"\xef\xbb\xbf" + tekst_polski.encode("utf-8")),
            ("tymczasowy UTF-16 BE z BOM", b"\xfe\xff" + tekst_polski.encode("utf-16-be")),
            ("tymczasowy cp1250", tekst_polski.encode("cp1250")),
        ]
        linie = []
        for nazwa, data in przypadki_tymczasowe:
            sciezka = _make_temp_file(data)
            try:
                linie.append(_describe_file(nazwa, sciezka))
            finally:
                os.remove(sciezka)

        katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        katalog_testow = os.path.normpath(os.path.join(katalog_repo, "..", "..", "tests"))
        robot_01 = os.path.join(katalog_testow, "01_rpa_challange_roboforge", "requirements.txt")
        robot_02 = os.path.join(katalog_testow, "02_robot_bez_frameworku", "przetwarzanie.py")
        linie.append(_describe_file("robot 01 requirements.txt", robot_01))
        linie.append(_describe_file("robot 02 przetwarzanie.py", robot_02))
        return linie

    def _print_lines(
        lines: list[str],
    ) -> None:
        """Wypisuje gotowe linie opisu, każdą w osobnym wierszu.

        Po co: wypisywanie oddzielone od logiki testu.
        """
        for linia in lines:
            print(linia)

    def manual_test():
        """Sprawdza odczyt plików w różnych kodowaniach i wypisuje wynik dla każdego przypadku.

        Po co: szybkie potwierdzenie, że UTF-16, cp1250 i BOM dają czytelny tekst.
        """
        linie = _collect_descriptions()
        _print_lines(linie)

    manual_test()
