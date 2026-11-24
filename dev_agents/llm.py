"""Fabryka modeli i wspólne wywołanie modelu ze schematem odpowiedzi.

Co robi: na podstawie profilu z config.yaml tworzy model czatu (ChatOpenAI z nazwą modelu, kluczem
i adresem endpointu ze zmiennych środowiskowych wskazanych w profilu oraz tylko z parametrami podanymi
w `params`), podaje metodę structured output z profilu i udostępnia invoke_structured() - jedną funkcję,
przez którą wszyscy agenci wołają model ze schematem odpowiedzi (Pydantic).

Dlaczego istnieje: to jedyny moduł, który importuje langchain_openai i wie, jak powstaje model - zmiana
modelu, endpointu albo parametrów to zmiana w config.yaml, nie w kodzie. invoke_structured() pilnuje,
żeby błąd modelu nie przeszedł po cichu (LangChain potrafi zwrócić None zamiast odpowiedzi):
    - odpowiedź niezgodną ze schematem ponawia (domyślnie łącznie 2 próby), a potem rzuca RuntimeError
      z nazwą schematu, liczbą prób, powodem zakończenia odpowiedzi (finish_reason), tokenami i przyczyną,
    - przy metodzie json_schema odpowiedź sprawdza już biblioteka openai i sama rzuca wyjątki:
      pydantic.ValidationError (odpowiedź niezgodna, np. pusty obiekt {} z firmowej bramki) - ponawiany
      jak każda niezgodna odpowiedź; openai.LengthFinishReasonError (odpowiedź ucięta na limicie
      max_tokens) - bez ponawiania, jako błąd z końcówką uciętej odpowiedzi (widać, czy model się zapętlił).
Do modelu trafiają tylko parametry z profilu, bo część modeli odrzuca np. temperature; co dany endpoint
obsługuje, sprawdza scripts/probe_llm.py.

Rola: moduł używany przez agentów i skrypty diagnostyczne. Klucze czyta tylko w chwili tworzenia modelu.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.llm
Część 1 - udawany model, bez sieci i kluczy: cztery przypadki invoke_structured z liczbą wywołań modelu
i wynikiem albo komunikatem błędu. Część 2 - profil z nieistniejącą zmienną środowiskową: czytelny błąd
z nazwą zmiennej. Część 3 - prawdziwy model agenta `planner` (wymaga zmiennych z profilu): krótka
odpowiedź z czasem i tokenami, potem odpowiedź zgodna z małym schematem.
"""

import os

import pydantic
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from openai import LengthFinishReasonError

import dev_agents.config as _config


# --- Zmienne środowiskowe ---


def _read_env(
    name: str,
) -> str:
    """Zwraca wartość zmiennej środowiskowej o podanej nazwie; gdy jej brak albo jest pusta, rzuca RuntimeError z nazwą zmiennej.

    Po co: klucze i adresy endpointów nie mogą być zapisane w repo ani w configu, więc czytamy je
    ze zmiennych środowiskowych; komunikat z nazwą zmiennej mówi od razu, co trzeba ustawić.

    Uwaga: zmienna użytkownika ustawiona w Windows jest widoczna dopiero w nowo otwartym oknie terminala.
    """
    wartosc = os.environ.get(name)
    if not wartosc:
        komunikat_bledu = (
            f"Brak zmiennej środowiskowej '{name}'. "
            f"Ustaw ją jako zmienną użytkownika i otwórz nowe okno terminala."
        )
        raise RuntimeError(komunikat_bledu)
    return wartosc


# --- Tworzenie modeli ---


def create_chat_model(
    profile: _config.LLMProfile,
) -> BaseChatModel:
    """Tworzy ChatOpenAI dla profilu: model z profilu, klucz i adres endpointu ze wskazanych zmiennych środowiskowych, tylko parametry z params.

    Po co: zarówno warstwa zgodności OpenAI na Kwadracie, jak i firmowa bramka na mieście mówią protokołem
    OpenAI Chat Completions, więc jedna funkcja obsługuje oba endpointy - zmienia się tylko config.

    Uwaga: obsługiwany jest wyłącznie provider 'openai_compatible' (zasada repo: modele tylko przez
    bibliotekę OpenAI); inny provider daje ValueError zamiast cichego użycia ChatOpenAI.
    """
    if profile.provider != "openai_compatible":
        komunikat_bledu = f"Nieznany provider '{profile.provider}'. Obsługiwany: 'openai_compatible'."
        raise ValueError(komunikat_bledu)

    model = ChatOpenAI(
        model=profile.model,
        api_key=_read_env(profile.api_key_env),
        base_url=_read_env(profile.base_url_env),
        **profile.params,
    )
    return model


def get_model_for_agent(
    app_config: _config.AppConfig,
    agent_name: str,
) -> BaseChatModel:
    """Tworzy model z profilu, który config przypisuje wskazanemu agentowi (np. planner -> small).

    Po co: agenci nie znają nazw modeli ani profili - proszą o model po swojej nazwie, a przełączenie
    agenta na inny model to zmiana jednej linii w sekcji llm.agents.
    """
    if agent_name not in app_config.llm.agents:
        komunikat_bledu = (
            f"Agent '{agent_name}' nie ma przypisanego profilu. Agenci w configu: {list(app_config.llm.agents)}"
        )
        raise ValueError(komunikat_bledu)
    profile = app_config.llm.profiles[app_config.llm.agents[agent_name]]
    model = create_chat_model(profile)
    return model


def get_structured_output_method(
    app_config: _config.AppConfig,
    agent_name: str,
) -> str:
    """Zwraca metodę structured output (json_schema, function_calling albo json_mode) z profilu przypisanego agentowi.

    Po co: to, która metoda działa, zależy od endpointu - ustala ją probe_llm i zapisuje się ją
    w profilu, a nie w kodzie agenta.
    """
    profile = app_config.llm.profiles[app_config.llm.agents[agent_name]]
    metoda = profile.structured_output_method
    return metoda


# --- Wywołanie ze schematem odpowiedzi ---


def _build_schema_error_message(
    schema_name: str,
    attempts_used: int,
    finish_reason: str,
    usage: str,
    cause: str,
) -> str:
    """Składa komunikat błędu dla odpowiedzi niezgodnej ze schematem: schemat, liczba prób, finish_reason, tokeny, przyczyna.

    Po co: jeden format komunikatu dla odpowiedzi odrzuconych przez LangChain i przez bibliotekę openai;
    przy ucięciu na limicie (finish_reason=length) dodaje podpowiedź o max_tokens.
    """
    podpowiedz = ""
    if finish_reason == "length":
        podpowiedz = " Odpowiedź ucięta na limicie - zwiększ max_tokens w profilu modelu w config.yaml."
    komunikat = (
        f"Model nie zwrócił odpowiedzi zgodnej ze schematem {schema_name} (próby: {attempts_used}). "
        f"finish_reason={finish_reason}, tokeny={usage}, przyczyna={cause}.{podpowiedz}"
    )
    return komunikat


def _build_length_error_message(
    schema_name: str,
    attempt: int,
    completion,
) -> str:
    """Składa komunikat błędu dla odpowiedzi uciętej na limicie max_tokens: schemat, numer próby, tokeny, podpowiedź i ostatnie 300 znaków odpowiedzi.

    Po co: komunikat biblioteki openai (LengthFinishReasonError) podaje tylko liczby tokenów. Końcówka
    odpowiedzi pokazuje przyczynę: powtarzający się fragment oznacza zapętlenie modelu (większy limit nie
    pomoże), zwykły tekst - odpowiedź po prostu dłuższą niż limit.

    Argumenty: completion - obiekt ChatCompletion z pola completion wyjątku.
    """
    tresc = ""
    if len(completion.choices) > 0 and completion.choices[0].message.content is not None:
        tresc = completion.choices[0].message.content
    koncowka = tresc[-300:]
    komunikat = (
        f"Odpowiedź modelu ucięta na limicie max_tokens - schemat {schema_name} (próba {attempt}). "
        f"tokeny={completion.usage}. Zwiększ max_tokens w profilu modelu w config.yaml. "
        f"Końcówka uciętej odpowiedzi (powtarzający się fragment = model się zapętlił): ...{koncowka}"
    )
    return komunikat


def invoke_structured(
    model: BaseChatModel,
    schema: type[pydantic.BaseModel],
    method: str,
    messages: list[BaseMessage],
    attempts: int = 2,
) -> pydantic.BaseModel:
    """Wywołuje model z wiadomościami i schematem odpowiedzi i zwraca odpowiedź jako obiekt schematu; niezgodną odpowiedź ponawia, łącznie najwyżej attempts razy.

    Po co: jedno miejsce wywołania modelu dla wszystkich agentów - zamiast cichego None zawsze jest albo
    obiekt schematu, albo RuntimeError z przyczyną. Pomyłka formatu jest zwykle losowa, więc ponowna próba
    przeważnie przechodzi i jeden taki błąd nie przerywa całego przebiegu.

    Uwaga: odpowiedzi uciętej na limicie max_tokens nie ponawiamy - przy tym samym limicie skończyłaby się
    tak samo. Przy metodzie json_schema błędy zgłasza biblioteka openai jako wyjątki (ValidationError,
    LengthFinishReasonError), a nie przez pole parsing_error - obsługiwane są obie drogi.

    Argumenty: method - metoda structured output z profilu (get_structured_output_method).
    """
    model_ze_schematem = model.with_structured_output(schema, method=method, include_raw=True)

    numer_proby = 0
    while True:
        numer_proby += 1
        try:
            wynik = model_ze_schematem.invoke(messages)
        except LengthFinishReasonError as blad_limitu:
            komunikat_bledu = _build_length_error_message(schema.__name__, numer_proby, blad_limitu.completion)
            raise RuntimeError(komunikat_bledu) from blad_limitu
        except pydantic.ValidationError as blad_schematu:
            if numer_proby >= attempts:
                komunikat_bledu = _build_schema_error_message(
                    schema.__name__,
                    numer_proby,
                    "brak danych (odrzucone przez bibliotekę openai)",
                    "brak danych",
                    str(blad_schematu),
                )
                raise RuntimeError(komunikat_bledu) from blad_schematu
            continue

        if wynik["parsed"] is not None:
            break

        finish_reason = wynik["raw"].response_metadata.get("finish_reason")
        if finish_reason == "length" or numer_proby >= attempts:
            komunikat_bledu = _build_schema_error_message(
                schema.__name__,
                numer_proby,
                finish_reason,
                str(wynik["raw"].usage_metadata),
                str(wynik["parsing_error"]),
            )
            raise RuntimeError(komunikat_bledu)

    odpowiedz = wynik["parsed"]
    return odpowiedz


# --- Test ręczny ---

if __name__ == "__main__":
    import time

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
    from openai.types.chat import ChatCompletion

    class _CityPopulation(pydantic.BaseModel):
        """Mały schemat odpowiedzi do testu: miasto i liczba mieszkańców.

        Po co: sprawdzenie invoke_structured na udawanym i prawdziwym modelu.
        """

        city: str = pydantic.Field(description="Nazwa miasta.")
        population_millions: float = pydantic.Field(description="Liczba mieszkańców w milionach.")

    def _make_validation_error() -> pydantic.ValidationError:
        """Zwraca prawdziwy ValidationError schematu testowego (jak przy pustym obiekcie {} z bramki).

        Po co: udawany model rzuca ten sam wyjątek, który rzuca biblioteka openai przy json_schema.
        """
        try:
            _CityPopulation.model_validate({})
        except pydantic.ValidationError as blad:
            return blad

    def _make_length_error() -> LengthFinishReasonError:
        """Zwraca LengthFinishReasonError z uciętą, zapętloną odpowiedzią.

        Po co: udawany model rzuca ten sam wyjątek, który rzuca biblioteka openai przy ucięciu na limicie.
        """
        zapetlona_tresc = '{"city": "Warszawa", "note": "' + "powtarzam ten sam fragment, " * 30
        completion = ChatCompletion.model_validate({
            "id": "test", "object": "chat.completion", "created": 0, "model": "udawany",
            "choices": [{"index": 0, "finish_reason": "length",
                         "message": {"role": "assistant", "content": zapetlona_tresc}}],
            "usage": {"completion_tokens": 16000, "prompt_tokens": 500, "total_tokens": 16500},
        })
        blad = LengthFinishReasonError(completion=completion)
        return blad

    class _FakeModel:
        """Udawany model: kolejne wywołania wykonują kolejne akcje z listy ('ok', 'validation', 'length', 'none_length').

        Po co: sprawdzenie wszystkich dróg invoke_structured bez sieci i kluczy.
        """

        def __init__(
            self,
            actions: list[str],
        ):
            """Zapamiętuje listę akcji i zeruje licznik wywołań.

            Po co: test liczy, ile razy invoke_structured zawołał model.
            """
            self.actions = actions
            self.calls = 0

        def with_structured_output(
            self,
            schema,
            method=None,
            include_raw=False,
        ):
            """Zwraca samego siebie - udaje model ze schematem odpowiedzi.

            Po co: invoke_structured woła with_structured_output, a potem invoke.
            """
            return self

        def invoke(
            self,
            messages,
        ):
            """Wykonuje kolejną akcję: zwraca poprawną odpowiedź, None z finish_reason=length albo rzuca wyjątek.

            Po co: odtwarza zachowanie prawdziwego modelu w czterech sytuacjach z testu.
            """
            akcja = self.actions[self.calls]
            self.calls += 1
            if akcja == "validation":
                raise _make_validation_error()
            if akcja == "length":
                raise _make_length_error()
            if akcja == "none_length":
                surowa = AIMessage(
                    content="",
                    response_metadata={"finish_reason": "length"},
                    usage_metadata={"input_tokens": 500, "output_tokens": 16000, "total_tokens": 16500},
                )
                odpowiedz_none = {"raw": surowa, "parsed": None, "parsing_error": None}
                return odpowiedz_none
            odpowiedz_ok = {
                "raw": AIMessage(content="{}"),
                "parsed": _CityPopulation(city="Warszawa", population_millions=1.86),
                "parsing_error": None,
            }
            return odpowiedz_ok

    def _run_fake_scenario(
        actions: list[str],
    ) -> tuple[int, str]:
        """Uruchamia invoke_structured na udawanym modelu z podanymi akcjami i zwraca (liczba wywołań, wynik albo komunikat błędu).

        Po co: jeden przypadek testowy części 1.
        """
        fake_model = _FakeModel(actions)
        try:
            odpowiedz = invoke_structured(fake_model, _CityPopulation, "json_schema", [])
            opis_wyniku = f"OK: {odpowiedz.city}, {odpowiedz.population_millions} mln"
        except RuntimeError as blad:
            opis_wyniku = f"RuntimeError: {blad}"
        wynik_przypadku = (fake_model.calls, opis_wyniku)
        return wynik_przypadku

    def _test_fake_model() -> list[str]:
        """Część 1: cztery przypadki invoke_structured na udawanym modelu; zwraca linie wyniku do wypisania.

        Po co: sprawdzenie ponawiania i komunikatów błędów bez sieci.
        """
        przypadki = [
            ("ValidationError, potem poprawna odpowiedź (oczekiwane: OK po 2 wywołaniach)", ["validation", "ok"]),
            ("Dwa razy ValidationError (oczekiwane: błąd po 2 wywołaniach)", ["validation", "validation"]),
            ("LengthFinishReasonError (oczekiwane: błąd z końcówką po 1 wywołaniu)", ["length", "ok"]),
            ("None z finish_reason=length (oczekiwane: błąd z podpowiedzią po 1 wywołaniu)", ["none_length", "ok"]),
        ]
        linie_wyniku = []
        for tytul, akcje in przypadki:
            liczba_wywolan, opis_wyniku = _run_fake_scenario(akcje)
            linie_wyniku.append(f"--- {tytul} ---")
            linie_wyniku.append(f"wywołań modelu: {liczba_wywolan}")
            linie_wyniku.append(opis_wyniku)
        return linie_wyniku

    def _test_missing_env(
        app_config: _config.AppConfig,
    ) -> list[str]:
        """Część 2: tworzy model z kopii profilu wskazującej nieistniejącą zmienną środowiskową; zwraca linie wyniku.

        Po co: sprawdzenie komunikatu, który zobaczy osoba bez ustawionego klucza.
        """
        zepsuty_profil = app_config.llm.profiles["small"].model_copy(
            update={"api_key_env": "DEV_AGENTS_BRAK_TAKIEJ_ZMIENNEJ"}
        )
        try:
            create_chat_model(zepsuty_profil)
            linie_wyniku = ["BŁĄD TESTU: model powstał mimo braku zmiennej"]
        except RuntimeError as blad:
            linie_wyniku = [f"RuntimeError: {blad}"]
        return linie_wyniku

    def _test_real_model(
        app_config: _config.AppConfig,
    ) -> list[str]:
        """Część 3: krótkie wywołanie prawdziwego modelu agenta planner i odpowiedź zgodna z małym schematem; zwraca linie wyniku.

        Po co: sprawdzenie, że klucz, adres, nazwa modelu i metoda structured output z configu działają.

        Uwaga: gdy brakuje zmiennej środowiskowej z profilu, część jest pomijana z komunikatem (bez przerywania testu).
        """
        try:
            model = get_model_for_agent(app_config, "planner")
        except RuntimeError as blad:
            linie_pominiecia = [f"Pominięte - {blad}"]
            return linie_pominiecia

        start = time.time()
        odpowiedz = model.invoke("Powiedz: test")
        czas_s = time.time() - start

        metoda = get_structured_output_method(app_config, "planner")
        wiadomosci = [
            SystemMessage(content="Odpowiadasz wyłącznie w formacie wskazanym przez schemat odpowiedzi."),
            HumanMessage(content="Podaj stolicę Polski i przybliżoną liczbę jej mieszkańców w milionach."),
        ]
        miasto = invoke_structured(model, _CityPopulation, metoda, wiadomosci)

        linie_wyniku = [
            f"Model: {model.model_name}",
            f"Odpowiedź: {odpowiedz.content} ({czas_s:.1f} s)",
            f"Tokeny: {odpowiedz.usage_metadata}",
            f"invoke_structured ({metoda}): {miasto.city}, {miasto.population_millions} mln",
        ]
        return linie_wyniku

    def _print_section(
        title: str,
        lines: list[str],
    ) -> None:
        """Wypisuje nagłówek części testu i jej linie wyniku.

        Po co: logika testów zwraca dane, a wypisywanie jest tylko tutaj.
        """
        print(f"\n=== {title} ===")
        for linia in lines:
            print(linia)

    def manual_test():
        """Uruchamia trzy części testu: udawany model, brak zmiennej środowiskowej, prawdziwy model.

        Po co: pełne sprawdzenie modułu - części 1 i 2 działają bez sieci, część 3 wymaga kluczy.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        _print_section("Część 1: udawany model", _test_fake_model())
        _print_section("Część 2: brak zmiennej środowiskowej", _test_missing_env(app_config))
        _print_section("Część 3: prawdziwy model agenta 'planner'", _test_real_model(app_config))

    manual_test()
