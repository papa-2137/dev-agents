"""Stan przebiegu grafu agentów: dane, które węzły przekazują sobie nawzajem.

Co robi: definiuje RunState - słownik (TypedDict) z polami wspólnymi dla całego przebiegu:
    project_path - ścieżka katalogu analizowanego projektu (wejście grafu),
    project_map  - mapa projektu z skanera (wynik węzła scan; zawiera też graf zależności i kolejność czytania).
Kolejne etapy (plan, notatki analityków, diagram, treść przewodnika) dopisują tu swoje pola w swoich krokach.

Dlaczego istnieje: w LangGraph węzeł dostaje stan i zwraca tylko te pola, które zmienia - słownik z polami
opcjonalnymi (total=False) pasuje do tego wprost. Stan trzyma tylko dane, które się zmieniają w trakcie
przebiegu; niezmienne zależności (config, magazyn wyników, modele) są w RunContext (context.py).

Rola: moduł rdzenia towaru, importowany przez graph.py i kolejne węzły.

Test ręczny: brak własnego - stan jest sprawdzany w teście grafu (python -m dev_agents.graph).
"""

import typing

import dev_agents.schemas as _schemas


class RunState(typing.TypedDict, total=False):
    """Stan przebiegu: ścieżka projektu na wejściu i wyniki kolejnych węzłów.

    Po co: jeden typ opisujący, co węzły grafu czytają i co dopisują; pola są opcjonalne,
    bo przy starcie grafu istnieje tylko project_path.
    """

    project_path: str
    project_map: _schemas.ProjectMap
