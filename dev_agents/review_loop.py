"""Pętla recenzji: kto i co ma być poprawiony po recenzji - czysta logika bez modelu i bez LangGraph.

Co robi:
    - issue_lines() zamienia uwagi recenzji o danym adresacie (diagram "flow" albo id zakładki) na linie tekstu do promptu
      poprawki ("[sekcja] opis" albo sam opis, z prefiksem "recenzent: "),
    - has_flow_issues() mówi, czy recenzent ma uwagi do diagramu,
    - tabs_referencing_flow() wskazuje zakładki, których treść odwołuje się do klocków diagramu (ścieżki procesu z node_id),
    - tabs_to_rewrite() wybiera zakładki do przepisania w rundzie: te z uwagami, a po zmianie diagramu także te, które
      odwołują się do jego klocków; kolejność jak w tab_ids (kolejność szablonu),
    - flow_changed_line() podaje stałe zdanie poprawki dla zakładki, która nie ma własnych uwag, a diagram się zmienił.

Dlaczego istnieje: krawędzie warunkowe grafu widzą tylko stan, a decyzje o poprawkach (kto, na jakiej podstawie) warto
testować bez grafu i modeli. Poprawki są celowane: przepisywany jest diagram albo zakładki, których dotyczą uwagi - reszta
zostaje bez zmian i bez kosztu tokenów. Zakładki bez uwag, ale zależne od zmienionego diagramu, dostają poprawkę o zmianie diagramu.

Rola: moduł rdzenia towaru (faza F); używa go graph.py (krawędzie warunkowe po reviewer i po flow_fix).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.review_loop
        linie uwag dla diagramu i zakładki (z sekcją i bez), zakładki odwołujące się do klocków, wybór zakładek do przepisania
        (same uwagi, uwagi i zmiana diagramu, kolejność jak w tab_ids, zakładka spoza tab_ids pominięta); na końcu
        "zgodne z oczekiwaniem: True"
"""

import dev_agents.guide_content as _content
import dev_agents.schemas as _schemas

FLOW_TARGET = "flow"
_ISSUE_PREFIX = "recenzent: "


def issue_lines(
    review: _schemas.ReviewResult,
    target: str,
) -> list[str]:
    """Zwraca uwagi recenzji dla adresata (diagram "flow" albo id zakładki) jako linie tekstu: "recenzent: [sekcja] opis" albo "recenzent: opis" bez sekcji.

    Po co: pisarz i autor diagramu dostają uwagi w <poprawka> obok problemów z kodu; prefiks mówi, kto je zgłosił.
    """
    linie = []
    for uwaga in review.issues:
        if uwaga.target != target:
            continue
        if uwaga.section_id != "":
            linie.append(f"{_ISSUE_PREFIX}[{uwaga.section_id}] {uwaga.description}")
        else:
            linie.append(f"{_ISSUE_PREFIX}{uwaga.description}")
    return linie


def has_flow_issues(
    review: _schemas.ReviewResult,
) -> bool:
    """Zwraca True, gdy recenzja ma co najmniej jedną uwagę do diagramu.

    Po co: uwagi do diagramu uruchamiają najpierw autora diagramu, a dopiero potem pisarzy.
    """
    wynik = len(issue_lines(review, FLOW_TARGET)) > 0
    return wynik


def tabs_referencing_flow(
    content: _content.GuideContent,
) -> list[str]:
    """Zwraca id zakładek, w których choć jeden krok ścieżki procesu odwołuje się do klocka diagramu (node_id niepusty), w kolejności treści.

    Po co: zmiana diagramu (inne id klocków, inne czynności) psuje tylko te zakładki, które się do niego odwołują - pozostałe
    nie wymagają przepisania.
    """
    wynik = []
    for zakladka in content.tabs:
        odwoluje_sie = False
        for blok in zakladka.blocks:
            for sciezka in blok.paths:
                for krok in sciezka.steps:
                    if krok.node_id != "":
                        odwoluje_sie = True
        if odwoluje_sie:
            wynik.append(zakladka.tab_id)
    return wynik


def tabs_to_rewrite(
    review: _schemas.ReviewResult,
    content: _content.GuideContent,
    tab_ids: list[str],
    flow_changed: bool,
) -> list[str]:
    """Zwraca id zakładek do przepisania w tej rundzie, w kolejności tab_ids: zakładki z uwagami recenzji i - gdy diagram się zmienił - zakładki odwołujące się do jego klocków.

    Po co: poprawki celowane. Zakładka spoza tab_ids (bez pisarza) nigdy nie jest wybrana.
    """
    wybrane = set()
    for uwaga in review.issues:
        wybrane.add(uwaga.target)
    if flow_changed:
        for identyfikator in tabs_referencing_flow(content):
            wybrane.add(identyfikator)
    wynik = []
    for identyfikator in tab_ids:
        if identyfikator in wybrane:
            wynik.append(identyfikator)
    return wynik


def flow_changed_line() -> str:
    """Zwraca zdanie poprawki dla zakładki bez własnych uwag, którą trzeba przepisać, bo recenzja zmieniła diagram.

    Po co: pisarz widzi nowy diagram w prompcie, ale musi wiedzieć, że ma dostosować do niego odwołania do klocków i opis kroków.
    """
    return "Diagram przepływu został poprawiony po recenzji: dostosuj odwołania do klocków (node_id) i opis kroków do nowego diagramu; resztę zostaw bez zmian."


# --- Test ręczny ---

if __name__ == "__main__":

    def _review() -> _schemas.ReviewResult:
        """Zwraca recenzję z uwagą do diagramu, do zakładki z sekcją i do zakładki bez sekcji.

        Po co: dane do sprawdzenia linii uwag i wyboru zakładek.
        """
        recenzja = _schemas.ReviewResult(
            approved=False,
            issues=[
                _schemas.ReviewIssue(target="flow", section_id="", description="Brak klocka wysyłki."),
                _schemas.ReviewIssue(target="bledy", section_id="awarie", description="Awaria bez przyczyny."),
                _schemas.ReviewIssue(target="zmiany", section_id="", description="Ogólnik."),
            ],
            suggestions=[],
        )
        return recenzja

    def _content_with_paths(
        tab_ids: list[str],
    ) -> _content.GuideContent:
        """Zwraca treść, w której zakładka "sciezki" ma krok z node_id, a pozostałe podane zakładki mają pusty blok.

        Po co: tylko ścieżki odwołują się do klocków diagramu.
        """
        zakladki = []
        for identyfikator in tab_ids:
            blok = _content.GuideBlock(section_id="s")
            if identyfikator == "sciezki":
                krok = _content.PathStep(text="Krok.", node_id="n1")
                blok = _content.GuideBlock(section_id="sciezki", paths=[_content.ProcessPath(name="Główna", kind="main", steps=[krok])])
            zakladki.append(_content.GuideTab(tab_id=identyfikator, blocks=[blok]))
        diagram = _content.FlowGraph(nodes=[_content.FlowNode(id="n1", kind="start", label="Start")], edges=[])
        tresc = _content.GuideContent(project_name="robot", flow=diagram, tabs=zakladki)
        return tresc

    def manual_test():
        """Sprawdza linie uwag, zakładki odwołujące się do diagramu i wybór zakładek do przepisania; wypisuje werdykt.

        Po co: logika decyzji pętli recenzji bez modelu i bez grafu.
        """
        tab_ids = ["przeglad", "sciezki", "zmiany", "bledy"]
        recenzja = _review()
        tresc = _content_with_paths(tab_ids)
        wyniki = []
        wyniki.append(("issue_lines: diagram bez sekcji", issue_lines(recenzja, "flow") == ["recenzent: Brak klocka wysyłki."]))
        wyniki.append(("issue_lines: zakładka z sekcją", issue_lines(recenzja, "bledy") == ["recenzent: [awarie] Awaria bez przyczyny."]))
        wyniki.append(("issue_lines: zakładka bez uwag", issue_lines(recenzja, "przeglad") == []))
        wyniki.append(("has_flow_issues: z uwagą do diagramu i bez", has_flow_issues(recenzja) and not has_flow_issues(recenzja.model_copy(update={"issues": recenzja.issues[1:]}))))
        wyniki.append(("tabs_referencing_flow: tylko zakładka z node_id", tabs_referencing_flow(tresc) == ["sciezki"]))
        wyniki.append(("tabs_to_rewrite: bez zmiany diagramu tylko zakładki z uwagami, w kolejności tab_ids", tabs_to_rewrite(recenzja, tresc, tab_ids, False) == ["zmiany", "bledy"]))
        wyniki.append(("tabs_to_rewrite: po zmianie diagramu dochodzą zakładki odwołujące się do klocków", tabs_to_rewrite(recenzja, tresc, tab_ids, True) == ["sciezki", "zmiany", "bledy"]))
        tylko_diagram = recenzja.model_copy(update={"issues": recenzja.issues[:1]})
        wyniki.append(("tabs_to_rewrite: uwaga tylko do diagramu - po jego zmianie sama zakładka ze ścieżkami", tabs_to_rewrite(tylko_diagram, tresc, tab_ids, True) == ["sciezki"]))
        wyniki.append(("tabs_to_rewrite: uwaga tylko do diagramu bez zmiany diagramu - nic", tabs_to_rewrite(tylko_diagram, tresc, tab_ids, False) == []))
        obca = recenzja.model_copy(update={"issues": [_schemas.ReviewIssue(target="obca", section_id="", description="x")]})
        wyniki.append(("tabs_to_rewrite: zakładka spoza tab_ids pominięta", tabs_to_rewrite(obca, tresc, tab_ids, False) == []))
        wyniki.append(("flow_changed_line: niepuste zdanie o diagramie", "Diagram przepływu został poprawiony" in flow_changed_line()))
        zgodne = True
        for opis, wynik in wyniki:
            print(f"  {opis}: {wynik}")
            if not wynik:
                zgodne = False
        print(f"\nzgodne z oczekiwaniem: {zgodne}")

    manual_test()
