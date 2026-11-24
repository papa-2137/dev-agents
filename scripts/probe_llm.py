"""Diagnostyka profilu modelu z config.yaml: co dany model i endpoint naprawdę obsługują.

Co robi: dla wskazanego profilu tworzy model tą samą fabryką, z której korzystają agenci, i uruchamia
serię niezależnych testów (błąd jednego nie przerywa pozostałych):
    1. Proste wywołanie - czy działają klucz, adres, nazwa modelu i params.
    2. Wiadomości system + user - czy model trzyma się instrukcji systemowej (tak działają agenci).
    3. Structured output - każda z trzech metod (json_schema, function_calling, json_mode) na dwóch
       schematach: płaskim (kilka pól) i zagnieżdżonym (lista obiektów z listą w środku, jak plan
       agenta). Wywołanie idzie przez invoke_structured() z jedną próbą - tą samą drogą co u agentów.
    4. Tool calling - czy model potrafi poprosić o wywołanie narzędzia (narzędzie nie jest uruchamiane).
Na końcu diagnoza: metody działające na obu schematach, rekomendowana wartość structured_output_method
(pierwsza działająca w kolejności json_schema, function_calling, json_mode), metody działające tylko na
schemacie płaskim (fałszywe "OK") i ocena wartości ustawionej obecnie w profilu.

Dlaczego istnieje: różne modele i bramki API zachowują się inaczej, a to, że jeden profil działa, nie znaczy,
że zadziała drugi. Na mieście płaski schemat dawał "OK", a agenci i tak się wywracali: Claude za bramką
zwracał przy zagnieżdżonym schemacie pusty obiekt {} (json_schema) albo listę jako tekst
(function_calling). Dlatego każda metoda jest sprawdzana także na schemacie zagnieżdżonym.

Rola: samodzielny skrypt diagnostyczny (nikt go nie importuje). Uruchamiany dla każdego profilu osobno -
zawsze po zmianie modelu, endpointu albo parametrów w profilu i jako pierwszy krok po przerzuceniu
towaru na miasto. Wartości kluczy i adresów nie są wypisywane, tylko nazwy zmiennych.

Uruchomienie (z katalogu głównego repo; uruchomienie jest testem skryptu):
    python -m scripts.probe_llm --profile small
Wynik: nagłówek profilu, linia OK/FAIL na każdy test (z czasem i opisem albo błędem), na końcu diagnoza.
FAIL przy którejś metodzie structured output nie jest błędem skryptu - to informacja, że ten model
albo endpoint jej nie obsługuje.
"""

import argparse
import os
import time

import pydantic
from langchain_core.messages import HumanMessage, SystemMessage

import dev_agents.config as _config
import dev_agents.llm as _llm


# --- Stałe ---

# Metody structured output w kolejności preferencji przy rekomendacji. Wspólne dla testów,
# wyświetlania i diagnozy - kolejność jest w jednym miejscu.
_STRUCTURED_METHODS = ["json_schema", "function_calling", "json_mode"]


# --- Schematy używane w testach ---


class _Capital(pydantic.BaseModel):
    """Płaski schemat testowy: kraj, stolica i liczba mieszkańców stolicy.

    Po co: najprostszy przypadek structured output - jeśli nie przechodzi, metoda nie działa wcale.
    """

    country: str = pydantic.Field(description="Nazwa kraju.")
    capital: str = pydantic.Field(description="Nazwa stolicy kraju.")
    population_millions: float = pydantic.Field(description="Liczba mieszkańców stolicy w milionach.")


class _Neighbour(pydantic.BaseModel):
    """Element schematu zagnieżdżonego: kraj sąsiedni, jego stolica i miasta przy granicy z Polską.

    Po co: obiekt z listą w środku - taki kształt mają elementy planu agentów (sekcja z listą plików).
    """

    country: str = pydantic.Field(description="Nazwa kraju sąsiadującego z Polską.")
    capital: str = pydantic.Field(description="Nazwa stolicy tego kraju.")
    border_cities: list[str] = pydantic.Field(description="Dwa miasta tego kraju położone blisko granicy z Polską.")


class _Neighbours(pydantic.BaseModel):
    """Zagnieżdżony schemat testowy: lista krajów sąsiadujących z Polską.

    Po co: lista obiektów z listą w środku - na takim schemacie bramka na mieście psuła odpowiedzi,
    choć płaski schemat przechodził.
    """

    neighbours: list[_Neighbour] = pydantic.Field(description="Trzy kraje sąsiadujące z Polską.")


class _CountLegs(pydantic.BaseModel):
    """Zwraca liczbę nóg podanego zwierzęcia."""

    animal: str = pydantic.Field(description="Nazwa zwierzęcia.")


# --- Funkcje pomocnicze ---


def _tokens(
    response,
) -> str:
    """Zwraca zużycie tokenów z odpowiedzi modelu w formie 'X in / Y out'.

    Po co: przy testach widać koszt wywołania - przydatne przy porównywaniu modeli.

    Uwaga: testy structured output idą przez invoke_structured(), który zwraca sam obiekt schematu,
    więc przy nich tokenów nie ma.
    """
    usage = response.usage_metadata
    if usage is None:
        usage = {}
    komunikat_zuzycie_tokenow = f"{usage.get('input_tokens', '?')} in / {usage.get('output_tokens', '?')} out"
    return komunikat_zuzycie_tokenow


def _short_error(
    error: Exception,
) -> str:
    """Zwraca nazwę wyjątku i jego treść spłaszczoną do jednej linii (linie oddzielone ' | '), najwyżej 500 znaków.

    Po co: komunikat błędu structured output ma kilka linii, a najważniejsza bywa dalsza (np. input_value={}
    przy pustym obiekcie z bramki) - spłaszczenie pokazuje ją w jednej linii raportu.
    """
    linie = []
    for linia in str(error).splitlines():
        if linia.strip():
            linie.append(linia.strip())
    tresc_bledu = " | ".join(linie)[:500]
    opis_bledu = f"{type(error).__name__}: {tresc_bledu}"
    return opis_bledu


def _check(
    func,
    *args,
) -> tuple[bool, float, str]:
    """Uruchamia jeden test, mierzy czas i łapie każdy wyjątek; niczego nie wypisuje. Zwraca (czy_ok, czas_s, opis).

    Po co: błąd jednego testu (np. nieobsługiwana metoda) nie może przerwać pozostałych - diagnoza
    ma pokazać pełny obraz możliwości modelu, łącznie z tym, czego nie potrafi.

    Argumenty: opis to wynik testu albo - przy błędzie - nazwa i treść wyjątku.
    """
    start = time.time()
    try:
        opis_wyniku = func(*args)
    except Exception as blad:
        czas_s = time.time() - start
        wynik_bledu = (False, czas_s, _short_error(blad))
        return wynik_bledu
    czas_s = time.time() - start
    wynik_ok = (True, czas_s, opis_wyniku)
    return wynik_ok


# --- Testy (każdy zwraca opis wyniku albo rzuca wyjątek) ---


def _test_simple(
    model,
) -> str:
    """Wysyła do modelu najprostsze zapytanie i zwraca opis odpowiedzi z tokenami.

    Po co: podstawowy test połączenia - jeśli nie przejdzie, problem jest w kluczu, adresie,
    nazwie modelu albo params, a nie w bardziej złożonych funkcjach.
    """
    response = model.invoke("Odpowiedz jednym słowem: test")
    opis_odpowiedzi = f"odpowiedź: {response.content!r}, tokeny: {_tokens(response)}"
    return opis_odpowiedzi


def _test_system_user(
    model,
) -> str:
    """Wysyła wiadomość systemową (odpowiadaj WIELKIMI LITERAMI) i wiadomość użytkownika; rzuca ValueError, gdy model zignoruje instrukcję.

    Po co: agenci działają na parze prompt systemowy + prompt użytkownika - trzeba mieć pewność,
    że endpoint przekazuje wiadomość systemową, a model się jej trzyma.
    """
    response = model.invoke([
        SystemMessage("Odpowiadasz wyłącznie WIELKIMI LITERAMI."),
        HumanMessage("Napisz słowo: kot"),
    ])
    text = str(response.content).strip()
    if not text.isupper():
        raise ValueError(f"model zignorował instrukcję systemową, odpowiedź: {text!r}")
    opis_odpowiedzi = f"odpowiedź: {text!r}, tokeny: {_tokens(response)}"
    return opis_odpowiedzi


def _test_structured_flat(
    model,
    method: str,
) -> str:
    """Prosi model wskazaną metodą o dane w płaskim schemacie _Capital (przez invoke_structured, jedna próba) i zwraca opis wyniku.

    Po co: pokazuje, czy metoda structured output w ogóle działa na tym modelu i endpoincie.
    """
    messages = [
        HumanMessage(
            "Podaj stolicę Polski i przybliżoną liczbę mieszkańców tego miasta (samej stolicy) w milionach. "
            "Odpowiedz w formacie JSON z polami: country, capital, population_millions."
        ),
    ]
    capital = _llm.invoke_structured(model, _Capital, method, messages, attempts=1)
    opis_danych_ze_schematu = f"{capital.capital}, {capital.population_millions} mln"
    return opis_danych_ze_schematu


def _test_structured_nested(
    model,
    method: str,
) -> str:
    """Prosi model wskazaną metodą o dane w zagnieżdżonym schemacie _Neighbours (przez invoke_structured, jedna próba) i zwraca opis wyniku; pusta lista to błąd.

    Po co: odróżnia metodę, która działa naprawdę, od fałszywego "OK" na płaskim schemacie - agenci
    zwracają listy obiektów.
    """
    messages = [
        HumanMessage(
            "Wymień trzy kraje sąsiadujące z Polską. Dla każdego podaj stolicę i dwa miasta tego kraju "
            "położone blisko granicy z Polską. Odpowiedz w formacie JSON z polem neighbours - listą obiektów "
            "z polami: country, capital, border_cities."
        ),
    ]
    neighbours = _llm.invoke_structured(model, _Neighbours, method, messages, attempts=1)
    if len(neighbours.neighbours) == 0:
        raise ValueError("model zwrócił pustą listę neighbours")
    kraje = []
    for neighbour in neighbours.neighbours:
        kraje.append(f"{neighbour.country} ({len(neighbour.border_cities)} miasta)")
    opis_danych_ze_schematu = f"{len(neighbours.neighbours)} kraje: {', '.join(kraje)}"
    return opis_danych_ze_schematu


def _test_tools(
    model,
) -> str:
    """Udostępnia modelowi narzędzie _CountLegs i sprawdza, czy model poprosi o jego wywołanie; narzędzie nie jest uruchamiane.

    Po co: tool calling to osobna funkcja endpointu (na firmowej bramce może nie działać) - wiedza o niej
    przyda się, gdyby agenci mieli kiedyś korzystać z narzędzi.
    """
    response = model.bind_tools([_CountLegs]).invoke("Ile nóg ma stonoga? Użyj narzędzia.")
    if not response.tool_calls:
        raise ValueError(f"model nie wywołał narzędzia, odpowiedź: {str(response.content)[:100]!r}")
    call = response.tool_calls[0]
    opis_wywolania_narzedzia = f"{call['name']}({call['args']}), tokeny: {_tokens(response)}"
    return opis_wywolania_narzedzia


# --- Logika: uruchomienie testów i diagnoza (bez wypisywania) ---


def _run_tests(
    model,
) -> dict:
    """Uruchamia wszystkie testy przez _check(). Zwraca słownik: nazwa testu -> (czy_ok, czas_s, opis).

    Po co: oddziela wykonanie testów od wyświetlania - wyniki trafiają najpierw do danych,
    a dopiero potem do diagnozy i na ekran.

    Uwaga: testy structured output mają nazwy '<metoda> / płaski' i '<metoda> / zagnieżdżony'.
    """
    wyniki = {}
    wyniki["invoke"] = _check(_test_simple, model)
    wyniki["system + user"] = _check(_test_system_user, model)
    for metoda in _STRUCTURED_METHODS:
        wyniki[f"{metoda} / płaski"] = _check(_test_structured_flat, model, metoda)
        wyniki[f"{metoda} / zagnieżdżony"] = _check(_test_structured_nested, model, metoda)
    wyniki["bind_tools"] = _check(_test_tools, model)
    return wyniki


def _diagnose(
    wyniki: dict,
    obecna_metoda: str,
) -> dict:
    """Ustala metody działające na obu schematach, rekomendowaną metodę, metody działające tylko na schemacie płaskim i czy metoda z configu działa.

    Po co: cała decyzja o rekomendacji jest w jednym miejscu, bez wypisywania - wynik mówi wprost,
    jaką wartość structured_output_method wpisać w profilu w config.yaml.

    Uwaga: metoda działająca tylko na płaskim schemacie nie jest rekomendowana - agenci zwracają
    listy obiektów, więc wywracaliby się na niej.
    """
    dzialajace_metody = []
    tylko_plaski = []
    for metoda in _STRUCTURED_METHODS:
        plaski_ok = wyniki[f"{metoda} / płaski"][0]
        zagniezdzony_ok = wyniki[f"{metoda} / zagnieżdżony"][0]
        if plaski_ok and zagniezdzony_ok:
            dzialajace_metody.append(metoda)
        elif plaski_ok:
            tylko_plaski.append(metoda)

    rekomendowana = None
    if len(dzialajace_metody) > 0:
        rekomendowana = dzialajace_metody[0]

    diagnoza = {
        "polaczenie_ok": wyniki["invoke"][0],
        "dzialajace_metody": dzialajace_metody,
        "tylko_plaski": tylko_plaski,
        "rekomendowana": rekomendowana,
        "obecna": obecna_metoda,
        "obecna_dziala": obecna_metoda in dzialajace_metody,
    }
    return diagnoza


# --- Wyświetlanie (tylko print, bez logiki) ---


def _print_header(
    nazwa_profilu: str,
    profile: _config.LLMProfile,
) -> None:
    """Wypisuje nagłówek: nazwę profilu, model, nazwy zmiennych środowiskowych, params i metodę z configu.

    Po co: widać, jaki profil jest testowany i z jakimi ustawieniami - bez wypisywania wartości kluczy.
    """
    print(f"Profil: {nazwa_profilu}")
    print(f"  model:    {profile.model} ({profile.provider})")
    print(f"  endpoint: zmienna {profile.base_url_env}, klucz: zmienna {profile.api_key_env}")
    print(f"  params:   {profile.params}")
    print(f"  structured_output_method w configu: {profile.structured_output_method}")
    print("\nTestuję (kilkanaście-kilkadziesiąt sekund)...")


def _print_results(
    wyniki: dict,
) -> None:
    """Wypisuje wyniki testów w sekcjach, jedna linia na test: OK/FAIL, nazwa, czas, opis.

    Po co: czytelny raport dla człowieka; tylko formatuje gotowe dane z _run_tests().
    """
    testy_structured = []
    for metoda in _STRUCTURED_METHODS:
        testy_structured.append(f"{metoda} / płaski")
        testy_structured.append(f"{metoda} / zagnieżdżony")

    sekcje = [
        ("1. Proste wywołanie", ["invoke"]),
        ("2. Wiadomości system + user", ["system + user"]),
        ("3. Structured output (zawsze wszystkie trzy metody, schemat płaski i zagnieżdżony)", testy_structured),
        ("4. Tool calling", ["bind_tools"]),
    ]
    for tytul, nazwy_testow in sekcje:
        print(f"\n{tytul}")
        for nazwa in nazwy_testow:
            czy_ok, czas_s, opis = wyniki[nazwa]
            status = "FAIL"
            if czy_ok:
                status = "OK  "
            print(f"  {status}  {nazwa} ({czas_s:.1f} s) - {opis}")


def _print_diagnosis(
    diagnoza: dict,
) -> None:
    """Wypisuje diagnozę: brak połączenia, brak działających metod albo działające metody z rekomendacją, ostrzeżeniem o fałszywym "OK" i oceną wartości z configu.

    Po co: końcowa odpowiedź skryptu - co wpisać w config.yaml dla tego profilu; tylko formatuje gotową diagnozę.
    """
    print("\nDiagnoza")
    if not diagnoza["polaczenie_ok"]:
        print("  Brak podstawowego połączenia - sprawdź zmienne środowiskowe, nazwę modelu i params (patrz błąd w punkcie 1).")
        return

    if len(diagnoza["tylko_plaski"]) > 0:
        print(
            f"  Uwaga: tylko na schemacie płaskim działa: {', '.join(diagnoza['tylko_plaski'])} "
            f"(fałszywe OK - agenci wywracaliby się na listach obiektów)."
        )

    if len(diagnoza["dzialajace_metody"]) == 0:
        print("  Żadna metoda structured output nie działa na schemacie zagnieżdżonym - agenci nie będą mogli zwracać obiektów.")
        return

    obecna = diagnoza["obecna"]
    print(f"  Metody działające na obu schematach: {', '.join(diagnoza['dzialajace_metody'])}")
    print(f"  Rekomendacja: structured_output_method: {diagnoza['rekomendowana']}")
    if obecna == diagnoza["rekomendowana"]:
        print("  Config już ma tę wartość.")
    elif diagnoza["obecna_dziala"]:
        print(f"  Obecna wartość ({obecna}) też działa - zmiana nie jest konieczna.")
    else:
        print(f"  Obecna wartość ({obecna}) NIE działa - zmień ją w config.yaml.")


# --- Uruchomienie ---


def _parse_args():
    """Odczytuje argumenty: --profile (wymagany) i --config (domyślnie config.yaml w katalogu głównym repo).

    Po co: skrypt testuje jeden profil naraz, żeby wyniki różnych modeli się nie mieszały;
    domyślna ścieżka configu działa niezależnie od katalogu uruchomienia.
    """
    katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    domyslny_config = os.path.join(katalog_repo, "config.yaml")
    parser = argparse.ArgumentParser(description="Diagnostyka profilu modelu z config.yaml.")
    parser.add_argument("--profile", required=True, help="nazwa profilu z sekcji llm.profiles")
    parser.add_argument(
        "--config",
        default=domyslny_config,
        help="ścieżka do config.yaml (domyślnie: config.yaml w katalogu głównym repo)",
    )
    argumenty = parser.parse_args()
    return argumenty


def _load_profile(
    config_path: str,
    nazwa_profilu: str,
) -> _config.LLMProfile:
    """Wczytuje config i zwraca wskazany profil; przy złej nazwie kończy program z listą dostępnych profili.

    Po co: literówka w nazwie profilu ma dać od razu czytelny komunikat, a nie wyjątek w środku testów.
    """
    app_config = _config.load_config(config_path)
    if nazwa_profilu not in app_config.llm.profiles:
        raise SystemExit(f"Nie ma profilu '{nazwa_profilu}'. Dostępne profile: {list(app_config.llm.profiles)}")
    profile = app_config.llm.profiles[nazwa_profilu]
    return profile


def _create_model(
    profile: _config.LLMProfile,
):
    """Tworzy model dla profilu fabryką z dev_agents.llm; przy braku zmiennej środowiskowej kończy program z jej nazwą.

    Po co: brak klucza albo adresu to najczęstszy problem przy pierwszym uruchomieniu - ma dać jedną
    czytelną linię zamiast tracebacku.
    """
    try:
        model = _llm.create_chat_model(profile)
    except RuntimeError as blad:
        raise SystemExit(str(blad)) from blad
    return model


def main() -> None:
    """Uruchamia diagnostykę: argumenty -> profil -> model -> nagłówek -> testy -> diagnoza -> wyniki.

    Po co: spis treści skryptu - kolejność kroków widać w kilku liniach, szczegóły są w osobnych funkcjach.
    """
    argumenty = _parse_args()
    profile = _load_profile(argumenty.config, argumenty.profile)
    model = _create_model(profile)
    _print_header(argumenty.profile, profile)

    wyniki = _run_tests(model)
    diagnoza = _diagnose(wyniki, profile.structured_output_method)

    _print_results(wyniki)
    _print_diagnosis(diagnoza)


if __name__ == "__main__":
    main()
