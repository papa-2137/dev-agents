"""Stan przebiegu grafu agentów: dane, które węzły przekazują sobie nawzajem.

Co robi: definiuje RunState - słownik (TypedDict) z polami wspólnymi dla całego przebiegu:
    project_path - ścieżka katalogu analizowanego projektu (wejście grafu),
    project_map  - mapa projektu z skanera (wynik węzła scan; zawiera też graf zależności i kolejność czytania),
    plan         - plan przebiegu (wynik węzła planner),
    task         - zadanie jednego analityka; wpisuje je do ładunku Send graf (graph.dispatch_analysts), nie węzły,
    notes        - notatki analityków (wynik równoległych węzłów analyst); pole z reducerem operator.add:
                   każdy analityk zwraca listę z jedną notatką, a LangGraph skleja listy w jedną,
    flow         - diagram przepływu całego procesu (wynik węzła flow_writer, krok 53),
    tab_ids      - id zakładek do napisania przez pisarzy (wynik węzła plan_tabs: zakładki szablonu z sekcjami dla pisarza),
    tab_id       - id zakładki do napisania; wpisuje je do ładunku Send graf (krok 56), nie węzły; czyta writer_node,
    tabs         - zakładki napisane przez pisarzy (wynik węzłów writer, krok 55); pole z reducerem operator.add:
                   każdy pisarz zwraca listę z jedną zakładką, a LangGraph skleja listy w jedną,
    content      - cała treść przewodnika (wynik węzła assemble, krok 56): diagram i zakładki w kolejności szablonu,
    guide_path   - ścieżka zapisanego guide.html (wynik węzła finalize, krok 57),
    review       - recenzja treści przewodnika (wynik węzła reviewer, kroki 58-59): uwagi oczyszczone przez kod,
    review_round - numer ostatniej recenzji (1, 2, ...; wpisuje go reviewer, historia w review_NN.json),
    fixes_pending - czy po tej recenzji trzeba poprawek: są uwagi, a limits.max_review_rounds nie jest wyczerpany
                   (wpisuje reviewer, bo krawędź warunkowa widzi tylko stan, a limit jest w configu),
    previous_tab - poprzednia wersja zakładki do poprawy; wpisuje ją do ładunku Send graf (krok 59), nie węzły; czyta writer_node,
    review_issues - uwagi recenzenta (linie tekstu) dla poprawianej zakładki albo diagramu; w ładunku Send (writer_node) albo
                   wyliczane przez flow_fix_node ze stanu; kolejne rundy nadpisują zakładki: w tabs wygrywa ostatnia wersja.
Kolejne etapy (diagram, treść przewodnika) dopisują tu swoje pola w swoich krokach.

Dlaczego istnieje: w LangGraph węzeł dostaje stan i zwraca tylko te pola, które zmienia - słownik z polami
opcjonalnymi (total=False) pasuje do tego wprost. Stan trzyma tylko dane, które się zmieniają w trakcie
przebiegu; niezmienne zależności (config, magazyn wyników, modele) są w RunContext (context.py).

Rola: moduł rdzenia towaru, importowany przez graph.py i kolejne węzły.

Test ręczny: brak własnego - stan jest sprawdzany w teście grafu (python -m dev_agents.graph).
"""

import operator
import typing

import dev_agents.guide_content as _content
import dev_agents.schemas as _schemas


class RunState(typing.TypedDict, total=False):
    """Stan przebiegu: ścieżka projektu na wejściu i wyniki kolejnych węzłów.

    Po co: jeden typ opisujący, co węzły grafu czytają i co dopisują; pola są opcjonalne,
    bo przy starcie grafu istnieje tylko project_path.
    """

    project_path: str
    project_map: _schemas.ProjectMap
    plan: _schemas.Plan
    task: _schemas.AnalysisTask
    notes: typing.Annotated[list[_schemas.ModuleNote], operator.add]
    flow: _content.FlowGraph
    tab_ids: list[str]
    tab_id: str
    tabs: typing.Annotated[list[_content.GuideTab], operator.add]
    content: _content.GuideContent
    guide_path: str
    review: _schemas.ReviewResult
    review_round: int
    fixes_pending: bool
    previous_tab: _content.GuideTab
    review_issues: list[str]
