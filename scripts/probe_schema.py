"""Diagnostyka rozmiaru schematu odpowiedzi: jaki schemat structured output przyjmuje bramka modelu.

Co robi: dla wskazanego profilu z config.yaml wysyła do modelu serię trywialnych zapytań, każde z innym
schematem odpowiedzi, i dla każdego pokazuje wynik oraz miary schematu (obiekty, pola po rozwinięciu
odwołań $ref, enumy, głębokość, rozmiar w KB). Schematy są sztuczne (rosnąca liczba pól płaskich, lista
obiektów o rosnącej liczbie pól, rosnące zagnieżdżenie, enumy, ten sam obiekt użyty wiele razy, wiele różnych
typów obiektów, pola "tekst albo null", pola z wartością domyślną) i prawdziwe (Plan, ModuleNote, ModuleNote
budowany pole po polu oraz każda lista obiektów z notatki osobno). Na końcu diagnoza: dla każdej grupy
największy przyjęty i najmniejszy odrzucony schemat oraz pole, od którego ModuleNote przestaje przechodzić.

Dlaczego istnieje: bramka odrzuca część schematów komunikatem "The compiled grammar is too large" albo
"property 'minimum' is not supported", a komunikat nie mówi, co dokładnie jest za duże. Zgadywanie (np. liczby
pól opcjonalnych) nie zadziałało, więc limit trzeba zmierzyć na prawdziwej bramce.

Rola: samodzielny skrypt diagnostyczny (nikt go nie importuje), siostra probe_llm. Uruchamiany dla profilu
agenta, który ma dostać duży schemat (analityk: small), i powtórzony dla innych profili (medium), bo limit
może zależeć od modelu. Niczego nie zapisuje; wartości kluczy i adresów nie są wypisywane.

Uruchomienie (z katalogu głównego repo; uruchomienie jest testem skryptu):
    python -m scripts.probe_schema --profile small
    python -m scripts.probe_schema --profile small --only plan,real_cum
    python -m scripts.probe_schema --dry-run        (bez modelu: tylko lista schematów i ich miary)
Wynik: nagłówek, linia na schemat (status, parametr, miary, czas, przyczyna), na końcu diagnoza.
Statusy: OK (przyjęty i wypełniony), ODP (schemat przyjęty, ale odpowiedź modelu niezgodna), GRAM (za duża
gramatyka), NIE (nieobsługiwane słowo kluczowe), FAIL (inny błąd, z treścią).
"""

import argparse
import json
import os
import time
import typing

import pydantic
from langchain_core.messages import HumanMessage

import dev_agents.config as _config
import dev_agents.llm as _llm
import dev_agents.schemas as _schemas

try:
    from openai.lib._pydantic import to_strict_json_schema as _to_strict_json_schema
except ImportError:
    _to_strict_json_schema = None


# --- Stałe ---

# Grupy schematów: klucz (do --only), tytuł w raporcie. Kolejność = kolejność uruchamiania.
_GROUPS = [
    ("flat", "A. Płaski obiekt z N polami tekstowymi"),
    ("list", "B. Lista obiektów, każdy obiekt ma K pól tekstowych"),
    ("nested", "C. Zagnieżdżenie: obiekt w obiekcie, głębokość D (po 3 pola na poziom)"),
    ("enum", "D. N pól typu Literal (po 4 wartości)"),
    ("ref", "E. Ten sam obiekt (tekst + Literal) użyty w N listach"),
    ("types", "F. N różnych typów obiektów (po 3 pola), każdy w osobnej liście"),
    ("union", "G. N pól typu 'tekst albo null'"),
    ("default", "H. N pól z wartością domyślną (biblioteka openai i tak robi je wymaganymi)"),
    ("plan", "I. Schemat Plan (przechodził w prawdziwych przebiegach)"),
    ("real_cum", "J. ModuleNote budowany pole po polu: pierwsze K pól notatki"),
    ("real_alone", "K. Każda lista obiektów z ModuleNote osobno (jedno pole)"),
]

_PROMPT = (
    "To jest test rozmiaru schematu odpowiedzi. Wypełnij każde pole tekstowe jednym krótkim słowem, "
    "każde pole wyboru dowolną dozwoloną wartością, każde pole typu null wartością null, "
    "a wszystkie listy zostaw puste."
)

_LITERAL_FOUR = typing.Literal["a", "b", "c", "d"]


# --- Budowanie schematów sztucznych ---


def _text_field() -> typing.Any:
    """Zwraca pole tekstowe z opisem, takie jak w prawdziwych schematach (każde pole ma description).

    Po co: wszystkie schematy testowe mają opisy pól jak schematy agentów - wynik nie zależy od ich braku.
    """
    pole = pydantic.Field(description="Pole tekstowe do testu rozmiaru schematu.")
    return pole


def _make_item(
    name: str,
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy model obiektu z count polami tekstowymi o nazwach pole_000, pole_001, ...

    Po co: cegiełka dla schematów płaskich, list obiektów i wielu typów obiektów.
    """
    fields = {}
    for index in range(count):
        fields[f"pole_{index:03d}"] = (str, _text_field())
    model = pydantic.create_model(name, **fields)
    return model


def _make_flat(
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy płaski schemat z count polami tekstowymi.

    Po co: grupa A - sprawdza, czy sama liczba pól w jednym obiekcie ma limit.
    """
    schema = _make_item(f"Flat{count}", count)
    return schema


def _make_list(
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy schemat z jedną listą obiektów, każdy obiekt ma count pól tekstowych.

    Po co: grupa B - prawdziwe schematy to listy obiektów (czynności, ustawienia), więc liczy się
    rozmiar obiektu w liście.
    """
    item = _make_item(f"Item{count}", count)
    schema = pydantic.create_model(
        f"List{count}",
        rows=(list[item], pydantic.Field(description="Lista obiektów testowych.")),
    )
    return schema


def _make_nested(
    depth: int,
) -> type[pydantic.BaseModel]:
    """Tworzy łańcuch obiektów zagnieżdżonych: depth poziomów, każdy z trzema polami tekstowymi i (oprócz ostatniego) polem child.

    Po co: grupa C - sprawdza, czy limit zależy od głębokości zagnieżdżenia, a nie od liczby pól.
    """
    child = None
    level = depth
    while level >= 1:
        fields = {}
        fields["a"] = (str, _text_field())
        fields["b"] = (str, _text_field())
        fields["c"] = (str, _text_field())
        if child is not None:
            fields["child"] = (child, pydantic.Field(description="Obiekt zagnieżdżony."))
        child = pydantic.create_model(f"Level{depth}_{level}", **fields)
        level -= 1
    return child


def _make_enums(
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy płaski schemat z count polami typu Literal (cztery wartości każde).

    Po co: grupa D - sprawdza, czy to enumy zwiększają gramatykę.
    """
    fields = {}
    for index in range(count):
        fields[f"wybor_{index:03d}"] = (_LITERAL_FOUR, pydantic.Field(description="Pole wyboru."))
    schema = pydantic.create_model(f"Enums{count}", **fields)
    return schema


def _make_shared(
    times: int,
) -> type[pydantic.BaseModel]:
    """Tworzy schemat z times listami tego samego obiektu (pole tekstowe + Literal), jak DataRef w czynnościach.

    Po co: grupa E - sprawdza, czy wielokrotne użycie jednego obiektu (odwołanie $ref) rośnie w gramatyce.
    """
    shared = pydantic.create_model(
        f"Shared{times}",
        name=(str, _text_field()),
        kind=(_LITERAL_FOUR, pydantic.Field(description="Rodzaj.")),
    )
    fields = {}
    for index in range(times):
        fields[f"lista_{index:03d}"] = (list[shared], pydantic.Field(description="Lista obiektów."))
    schema = pydantic.create_model(f"Shared{times}Root", **fields)
    return schema


def _make_types(
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy schemat z count listami, każda z innym typem obiektu (po trzy pola tekstowe).

    Po co: grupa F - sprawdza, czy limit dotyczy liczby różnych typów obiektów w schemacie.
    """
    fields = {}
    for index in range(count):
        item = _make_item(f"Typ{count}_{index:03d}", 3)
        fields[f"lista_{index:03d}"] = (list[item], pydantic.Field(description="Lista obiektów."))
    schema = pydantic.create_model(f"Types{count}", **fields)
    return schema


def _make_unions(
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy płaski schemat z count polami typu 'tekst albo null'.

    Po co: grupa G - pola z unią (anyOf) bywają osobno limitowane w gramatykach strict.
    """
    fields = {}
    for index in range(count):
        fields[f"pole_{index:03d}"] = (str | None, _text_field())
    schema = pydantic.create_model(f"Unions{count}", **fields)
    return schema


def _make_defaults(
    count: int,
) -> type[pydantic.BaseModel]:
    """Tworzy płaski schemat z count polami z wartością domyślną (pusty tekst).

    Po co: grupa H - sprawdza dawną tezę o polach opcjonalnych; biblioteka openai zamienia je w pola
    wymagane, więc wynik powinien być taki sam jak dla grupy A o tej samej liczbie pól.
    """
    fields = {}
    for index in range(count):
        fields[f"pole_{index:03d}"] = (str, pydantic.Field(default="", description="Pole z wartością domyślną."))
    schema = pydantic.create_model(f"Defaults{count}", **fields)
    return schema


def _make_real_subset(
    name: str,
    field_names: list[str],
) -> type[pydantic.BaseModel]:
    """Tworzy model z podzbioru pól prawdziwego ModuleNote (typy i opisy bez zmian).

    Po co: grupy J i K - pokazują, które pola notatki (a więc które zagnieżdżone obiekty) przesuwają
    schemat ponad limit.
    """
    fields = {}
    for field_name in field_names:
        info = _schemas.ModuleNote.model_fields[field_name]
        fields[field_name] = (info.annotation, pydantic.Field(description=info.description))
    schema = pydantic.create_model(name, **fields)
    return schema


# --- Lista przypadków ---


def _build_cases(
    only: list[str],
) -> list[tuple[str, str, type[pydantic.BaseModel]]]:
    """Buduje listę przypadków (grupa, parametr, schemat) w kolejności grup; only = klucze grup do uruchomienia, pusta lista = wszystkie.

    Po co: jedno miejsce, w którym widać wszystkie testowane schematy i ich parametry.
    """
    cases = []
    for count in [10, 20, 40, 80, 160]:
        cases.append(("flat", f"{count} pól", _make_flat(count)))
    for count in [5, 10, 20, 40]:
        cases.append(("list", f"{count} pól w obiekcie", _make_list(count)))
    for depth in [1, 2, 3, 4, 5]:
        cases.append(("nested", f"głębokość {depth}", _make_nested(depth)))
    for count in [2, 5, 10, 20, 40]:
        cases.append(("enum", f"{count} enumów", _make_enums(count)))
    for times in [1, 2, 4, 8, 16]:
        cases.append(("ref", f"{times} użyć obiektu", _make_shared(times)))
    for count in [2, 4, 8, 16]:
        cases.append(("types", f"{count} typów obiektów", _make_types(count)))
    for count in [4, 8, 16, 24]:
        cases.append(("union", f"{count} pól z null", _make_unions(count)))
    for count in [8, 24, 40]:
        cases.append(("default", f"{count} pól domyślnych", _make_defaults(count)))
    cases.append(("plan", "Plan", _schemas.Plan))

    note_fields = list(_schemas.ModuleNote.model_fields)
    for count in range(1, len(note_fields) + 1):
        ostatnie_pole = note_fields[count - 1]
        cases.append(("real_cum", f"{count:2d} pól (ostatnie: {ostatnie_pole})", _make_real_subset(f"Note{count}", note_fields[:count])))
    for field_name in note_fields:
        info = _schemas.ModuleNote.model_fields[field_name]
        if "Note" in str(info.annotation):
            cases.append(("real_alone", field_name, _make_real_subset(f"Alone_{field_name}", [field_name])))

    wybrane = []
    for case in cases:
        if len(only) == 0 or case[0] in only:
            wybrane.append(case)
    return wybrane


# --- Miary schematu ---


def _strict_schema(
    schema: type[pydantic.BaseModel],
) -> dict:
    """Zwraca schemat JSON w postaci wysyłanej do bramki (strict z biblioteki openai); bez biblioteki openai zwykły schemat pydantic.

    Po co: miary mają dotyczyć tego, co faktycznie trafia do bramki (wszystkie pola wymagane,
    additionalProperties=false), a nie surowego schematu pydantic.
    """
    if _to_strict_json_schema is not None:
        wynik = _to_strict_json_schema(schema)
        return wynik
    wynik = schema.model_json_schema()
    return wynik


def _walk(
    node: typing.Any,
    defs: dict,
    depth: int,
    counters: dict,
) -> None:
    """Przechodzi schemat JSON rekurencyjnie, rozwijając odwołania $ref, i zlicza obiekty, pola, enumy, unie oraz największą głębokość obiektów.

    Po co: gramatyka powstaje z rozwiniętego schematu, więc pola obiektu użytego pięć razy liczą się pięć razy.
    """
    if not isinstance(node, dict):
        return
    if "$ref" in node:
        nazwa = node["$ref"].split("/")[-1]
        _walk(defs[nazwa], defs, depth, counters)
        return
    if "enum" in node:
        counters["enums"] += 1
    if "anyOf" in node:
        counters["unions"] += 1
        for wariant in node["anyOf"]:
            _walk(wariant, defs, depth, counters)
    if "items" in node:
        _walk(node["items"], defs, depth, counters)
    if "properties" in node:
        glebokosc_obiektu = depth + 1
        counters["objects"] += 1
        counters["max_depth"] = max(counters["max_depth"], glebokosc_obiektu)
        for nazwa_pola in node["properties"]:
            counters["properties"] += 1
            _walk(node["properties"][nazwa_pola], defs, glebokosc_obiektu, counters)


def _measure(
    schema: type[pydantic.BaseModel],
) -> dict:
    """Zwraca miary schematu: objects, properties (po rozwinięciu $ref), enums, unions, max_depth, kb (rozmiar JSON wysyłanego do bramki).

    Po co: do wyników dopisujemy liczby, żeby po teście było widać, jaka miara dzieli schematy przyjęte od odrzuconych.
    """
    strict = _strict_schema(schema)
    counters = {"objects": 0, "properties": 0, "enums": 0, "unions": 0, "max_depth": 0}
    _walk(strict, strict.get("$defs", {}), 0, counters)
    counters["kb"] = len(json.dumps(strict, ensure_ascii=False)) / 1024
    return counters


def _format_measures(
    measures: dict,
) -> str:
    """Zwraca miary w jednej linii: obiekty, pola, enumy, unie, głębokość, KB.

    Po co: stały, zwięzły format miar w raporcie.
    """
    opis = (
        f"obiekty {measures['objects']}, pola {measures['properties']}, enumy {measures['enums']}, "
        f"unie {measures['unions']}, głębokość {measures['max_depth']}, {measures['kb']:.1f} KB"
    )
    return opis


# --- Wywołanie modelu i klasyfikacja wyniku ---


def _classify(
    error: Exception,
) -> str:
    """Zwraca status błędu: GRAM (za duża gramatyka), NIE (nieobsługiwane słowo kluczowe), ODP (schemat przyjęty, odpowiedź zła) albo FAIL (inny).

    Po co: tylko GRAM i NIE mówią o limicie schematu; ODP oznacza, że bramka schemat przyjęła - dla pytania
    o rozmiar to sukces, choć model odpowiedział źle.
    """
    tresc = str(error).lower()
    if "grammar" in tresc:
        return "GRAM"
    if "not supported" in tresc:
        return "NIE"
    if "nie zwrócił odpowiedzi zgodnej ze schematem" in tresc or "ucięta na limicie" in tresc:
        return "ODP"
    return "FAIL"


def _short_error(
    error: Exception,
) -> str:
    """Zwraca nazwę wyjątku i jego treść w jednej linii, najwyżej 300 znaków.

    Po co: komunikaty bramki są wielolinijkowe; jedna linia mieści się w raporcie.
    """
    linie = []
    for linia in str(error).splitlines():
        if linia.strip():
            linie.append(linia.strip())
    tresc = " | ".join(linie)[:300]
    opis = f"{type(error).__name__}: {tresc}"
    return opis


def _run_case(
    model,
    method: str,
    schema: type[pydantic.BaseModel],
) -> tuple[str, float, str]:
    """Wysyła trywialne zapytanie ze schematem (jedna próba) i zwraca (status, czas_s, opis błędu albo pusty tekst); nie rzuca wyjątków.

    Po co: błąd jednego schematu nie może przerwać serii - właśnie błędy są wynikiem testu.
    """
    start = time.time()
    try:
        _llm.invoke_structured(model, schema, method, [HumanMessage(_PROMPT)], attempts=1)
    except Exception as blad:
        czas_s = time.time() - start
        wynik_bledu = (_classify(blad), czas_s, _short_error(blad))
        return wynik_bledu
    czas_s = time.time() - start
    wynik_ok = ("OK", czas_s, "")
    return wynik_ok


# --- Diagnoza ---


def _is_accepted(
    status: str,
) -> bool:
    """Zwraca True, gdy bramka przyjęła schemat (status OK albo ODP).

    Po co: jedno miejsce definiuje, co znaczy "schemat przyjęty" w diagnozie.
    """
    przyjety = status in ("OK", "ODP")
    return przyjety


def _diagnose(
    results: list[dict],
) -> list[str]:
    """Zwraca linie diagnozy: dla każdej grupy największy przyjęty i najmniejszy odrzucony parametr oraz miary na granicy; dla grupy J pole, od którego notatka przestaje przechodzić.

    Po co: z kilkudziesięciu linii wynika kilka zdań - gdzie leży granica i która miara ją wyznacza.
    """
    linie = []
    for klucz, tytul in _GROUPS:
        przyjete = []
        odrzucone = []
        for wynik in results:
            if wynik["group"] != klucz:
                continue
            if _is_accepted(wynik["status"]):
                przyjete.append(wynik)
            else:
                odrzucone.append(wynik)
        if len(przyjete) == 0 and len(odrzucone) == 0:
            continue
        linie.append(tytul)
        if len(przyjete) > 0:
            ostatni = przyjete[-1]
            linie.append(f"    największy przyjęty:    {ostatni['name']} ({_format_measures(ostatni['measures'])})")
        else:
            linie.append("    przyjętych: brak")
        if len(odrzucone) > 0:
            pierwszy = odrzucone[0]
            linie.append(
                f"    najmniejszy odrzucony: {pierwszy['name']} [{pierwszy['status']}] ({_format_measures(pierwszy['measures'])})"
            )
        else:
            linie.append("    odrzuconych: brak (limit nie został osiągnięty)")
    return linie


# --- Wyświetlanie ---


def _print_header(
    nazwa_profilu: str,
    profile: _config.LLMProfile,
    method: str,
) -> None:
    """Wypisuje nagłówek: profil, model, nazwy zmiennych środowiskowych (bez wartości), params i użytą metodę.

    Po co: widać, jaki profil i jaka metoda są testowane.
    """
    print(f"Profil: {nazwa_profilu}")
    print(f"  model:    {profile.model} ({profile.provider})")
    print(f"  endpoint: zmienna {profile.base_url_env}, klucz: zmienna {profile.api_key_env}")
    print(f"  params:   {profile.params}")
    print(f"  metoda structured output: {method}")
    print("\nTestuję (kilka minut; wynik każdego schematu pojawia się od razu)...")


def _print_group_title(
    group_key: str,
) -> None:
    """Wypisuje tytuł grupy schematów z listy _GROUPS.

    Po co: raport jest podzielony na grupy; tytuł mówi, co dana grupa sprawdza.
    """
    for klucz, tytul in _GROUPS:
        if klucz == group_key:
            print(f"\n{tytul}")


def _print_case(
    status: str,
    name: str,
    measures: dict,
    czas_s: float,
    error_text: str,
) -> None:
    """Wypisuje jedną linię raportu: status, parametr, miary, czas, a przy błędzie jego treść.

    Po co: wynik każdego schematu jest widoczny od razu po jego sprawdzeniu.
    """
    print(f"  {status:<4}  {name:<44} {_format_measures(measures)} ({czas_s:.1f} s)", flush=True)
    if status in ("FAIL", "ODP"):
        print(f"        {error_text}", flush=True)


# --- Uruchomienie ---


def _parse_args():
    """Odczytuje argumenty: --profile, --config, --only (klucze grup po przecinku), --dry-run.

    Po co: skrypt testuje jeden profil naraz; --only skraca serię, a --dry-run pozwala obejrzeć schematy bez modelu.
    """
    katalog_repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    domyslny_config = os.path.join(katalog_repo, "config.yaml")
    parser = argparse.ArgumentParser(description="Diagnostyka rozmiaru schematu structured output.")
    parser.add_argument("--profile", default="small", help="nazwa profilu z sekcji llm.profiles (domyślnie small)")
    parser.add_argument("--config", default=domyslny_config, help="ścieżka do config.yaml (domyślnie config.yaml w katalogu głównym repo)")
    parser.add_argument("--only", default="", help="klucze grup po przecinku, np. plan,real_cum (domyślnie wszystkie)")
    parser.add_argument("--method", default="", help="metoda structured output (domyślnie ta z profilu)")
    parser.add_argument("--dry-run", action="store_true", help="bez modelu: tylko lista schematów i ich miary")
    argumenty = parser.parse_args()
    return argumenty


def _parse_only(
    text: str,
) -> list[str]:
    """Zamienia tekst 'a,b' z --only na listę kluczy grup; zły klucz kończy program z listą dozwolonych.

    Po co: literówka w nazwie grupy ma dać czytelny komunikat zamiast pustego raportu.
    """
    klucze = []
    dozwolone = []
    for klucz, tytul in _GROUPS:
        dozwolone.append(klucz)
    for kawalek in text.split(","):
        nazwa = kawalek.strip()
        if nazwa == "":
            continue
        if nazwa not in dozwolone:
            raise SystemExit(f"Nieznana grupa '{nazwa}'. Dozwolone: {dozwolone}")
        klucze.append(nazwa)
    return klucze


def _create_model(
    config_path: str,
    profile_name: str,
):
    """Wczytuje config, tworzy model dla profilu i zwraca (profil, model); zła nazwa profilu albo brak zmiennej środowiskowej kończą program jedną linią.

    Po co: najczęstsze problemy pierwszego uruchomienia mają dać czytelny komunikat, a nie traceback.
    """
    app_config = _config.load_config(config_path)
    if profile_name not in app_config.llm.profiles:
        raise SystemExit(f"Nie ma profilu '{profile_name}'. Dostępne profile: {list(app_config.llm.profiles)}")
    profile = app_config.llm.profiles[profile_name]
    try:
        model = _llm.create_chat_model(profile)
    except RuntimeError as blad:
        raise SystemExit(str(blad)) from blad
    wynik = (profile, model)
    return wynik


def _run_dry(
    cases: list[tuple[str, str, type[pydantic.BaseModel]]],
) -> None:
    """Wypisuje przypadki z miarami bez wołania modelu.

    Po co: sprawdzenie, że wszystkie schematy się budują, i podgląd ich rozmiarów przed użyciem bramki.
    """
    ostatnia_grupa = ""
    for group, name, schema in cases:
        if group != ostatnia_grupa:
            _print_group_title(group)
            ostatnia_grupa = group
        print(f"  ----  {name:<44} {_format_measures(_measure(schema))}")


def main() -> None:
    """Uruchamia diagnostykę: argumenty -> schematy -> (model) -> seria zapytań -> diagnoza.

    Po co: spis treści skryptu - kolejność kroków widać w kilku liniach.
    """
    argumenty = _parse_args()
    cases = _build_cases(_parse_only(argumenty.only))
    if argumenty.dry_run:
        _run_dry(cases)
        return

    profile, model = _create_model(argumenty.config, argumenty.profile)
    method = argumenty.method
    if method == "":
        method = profile.structured_output_method
    _print_header(argumenty.profile, profile, method)

    results = []
    ostatnia_grupa = ""
    for group, name, schema in cases:
        if group != ostatnia_grupa:
            _print_group_title(group)
            ostatnia_grupa = group
        measures = _measure(schema)
        status, czas_s, error_text = _run_case(model, method, schema)
        _print_case(status, name, measures, czas_s, error_text)
        results.append({"group": group, "name": name, "measures": measures, "status": status})

    print("\nDiagnoza (granica przyjęty / odrzucony w każdej grupie)")
    for linia in _diagnose(results):
        print(f"  {linia}")


if __name__ == "__main__":
    main()
