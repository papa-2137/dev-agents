"""Udawane modele do testów agentów: odpowiadają gotowym obiektem schematu, bez sieci i kluczy.

Co robi: udostępnia FakeStructuredModel - obiekt, który udaje model czatu ze structured output w takim zakresie,
w jakim używa go llm.invoke_structured: with_structured_output() i invoke() zwracające słownik
{"raw", "parsed", "parsing_error"}. Model zwraca ten sam gotowy obiekt albo - gdy podano funkcję - obiekt
policzony z wiadomości (np. odpowiedź zależna od analizowanej jednostki). Zapamiętuje liczbę wywołań i ostatnie
wiadomości, więc test może sprawdzić, co agent wysłał do modelu.

Dlaczego istnieje: testy planner, grafu i kolejnych agentów (analityk, autor diagramu, pisarze, recenzent) potrzebują
modelu, który odpowiada przewidywalnie - jedna wspólna klasa zamiast kopii w każdym teście.

Rola: moduł pomocniczy tylko dla testów; kod produkcyjny go nie importuje.

Test ręczny (z katalogu głównego repo; bez sieci i kluczy):
    python -m dev_agents.fakes
        sprawdza, że przez llm.invoke_structured udawany model zwraca gotowy obiekt, zapamiętuje wiadomości,
        liczy wywołania i potrafi odpowiedzieć funkcją od wiadomości; na końcu "zgodne z oczekiwaniem: True".
"""

import typing

from langchain_core.messages import AIMessage


class FakeStructuredModel:
    """Udawany model ze structured output: zwraca gotowy obiekt schematu (albo wynik funkcji od wiadomości).

    Po co: test agenta bez sieci i kluczy; pola calls i messages mówią, ile razy i z czym agent zawołał model.
    """

    def __init__(
        self,
        answer: typing.Any,
    ):
        """Zapamiętuje odpowiedź (obiekt schematu albo funkcja wiadomości -> obiekt schematu) i zeruje liczniki.

        Po co: jedna instancja obsługuje cały test; funkcja pozwala odpowiadać różnie dla różnych wiadomości.
        """
        self.answer = answer
        self.calls = 0
        self.messages = []

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
        """Zlicza wywołanie, zapamiętuje wiadomości i zwraca odpowiedź w kształcie wyniku modelu z include_raw=True.

        Po co: odtwarza kształt odpowiedzi prawdziwego modelu, który invoke_structured rozpakowuje.
        """
        self.calls += 1
        self.messages = messages
        odpowiedz = self.answer
        if callable(odpowiedz):
            odpowiedz = odpowiedz(messages)
        wynik = {"raw": AIMessage(content="{}"), "parsed": odpowiedz, "parsing_error": None}
        return wynik


# --- Test ręczny ---

if __name__ == "__main__":
    import pydantic
    from langchain_core.messages import HumanMessage

    import dev_agents.llm as _llm

    class _Answer(pydantic.BaseModel):
        """Mały schemat odpowiedzi do testu: jedno pole tekstowe.

        Po co: sprawdzenie FakeStructuredModel przez invoke_structured.
        """

        text: str

    def _run_cases() -> list[tuple[str, bool]]:
        """Sprawdza udawany model przez llm.invoke_structured: gotowy obiekt, wiadomości, licznik i odpowiedź funkcją; zwraca (opis, zgodne).

        Po co: wspólny udawany model musi działać dokładnie tak, jak używają go testy agentów.
        """
        wiadomosci = [HumanMessage(content="pytanie")]
        staly = FakeStructuredModel(_Answer(text="gotowa"))
        odpowiedz_stala = _llm.invoke_structured(staly, _Answer, "json_schema", wiadomosci)
        odpowiedz_stala_2 = _llm.invoke_structured(staly, _Answer, "json_schema", wiadomosci)
        funkcyjny = FakeStructuredModel(lambda messages: _Answer(text=messages[0].content.upper()))
        odpowiedz_funkcji = _llm.invoke_structured(funkcyjny, _Answer, "json_schema", wiadomosci)
        wyniki = [
            ("gotowy obiekt zwrócony", odpowiedz_stala.text == "gotowa"),
            ("licznik wywołań", staly.calls == 2 and odpowiedz_stala_2.text == "gotowa"),
            ("ostatnie wiadomości zapamiętane", staly.messages == wiadomosci),
            ("odpowiedź policzona funkcją od wiadomości", odpowiedz_funkcji.text == "PYTANIE"),
        ]
        return wyniki

    def manual_test():
        """Uruchamia sprawdzenia udawanego modelu i wypisuje werdykt.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że udawany model nadaje się do testów agentów.
        """
        wszystkie_zgodne = True
        for opis, zgodne in _run_cases():
            print(f"  {opis}: {zgodne}")
            if not zgodne:
                wszystkie_zgodne = False
        print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")

    manual_test()
