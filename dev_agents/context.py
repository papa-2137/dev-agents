"""Kontekst przebiegu grafu agentów: niezmienne zależności, które każdy węzeł dostaje od LangGraph.

Co robi: definiuje RunContext (config, magazyn wyników, modele agentów, spis bazy wiedzy, szablon przewodnika,
funkcja raportująca postęp) i build_context(), która go składa:
    - modele tworzy od razu dla każdego agenta z config.llm.agents (llm.get_model_for_agent),
    - spis bazy wiedzy wczytuje przez knowledge.load_index (błędny spis przerywa start),
    - szablon przewodnika wczytuje przez guide_template.load_template.
Magazyn wyników (RunStore) i funkcję raportującą postęp (report, patrz progress.py) dostaje gotowe od wołającego -
to wołający decyduje, gdzie zapisują się wyniki i dokąd trafiają linie postępu (ekran w main.py, lista w teście).

Dlaczego istnieje: węzły grafu nie powinny same czytać configu, tworzyć modeli ani otwierać plików -
dostają wszystko z kontekstu (w węźle: runtime.context). Zmiana modelu agenta to zmiana w config.yaml,
a węzeł testuje się z atrapą kontekstu. Konsekwencja: modele powstają przy starcie, więc brakująca zmienna
środowiskowa z kluczem albo adresem (nazwy w profilu llm) wychodzi od razu, z nazwą zmiennej, a nie w połowie przebiegu.

Rola: moduł rdzenia towaru, wołany przez main.py (krok 44) i test grafu; węzły czytają tylko RunContext.

Test ręczny: brak własnego - kontekst jest budowany i wypisywany w teście grafu (python -m dev_agents.graph).
"""

import dataclasses
import typing

from langchain_core.language_models import BaseChatModel

import dev_agents.config as _config
import dev_agents.guide_template as _template
import dev_agents.knowledge as _knowledge
import dev_agents.llm as _llm
import dev_agents.output as _output


@dataclasses.dataclass
class RunContext:
    """Niezmienne zależności przebiegu: config, magazyn wyników, modele agentów, spis bazy wiedzy, szablon przewodnika, funkcja raportująca.

    Po co: jeden obiekt przekazywany do grafu przy uruchomieniu (graph.invoke(..., context=...)); węzeł czyta go przez runtime.context.
    """

    config: _config.AppConfig
    store: _output.RunStore
    models: dict[str, BaseChatModel]  # nazwa agenta (jak w config.llm.agents) -> model
    knowledge_index: list[_knowledge.KBEntry]
    template: _template.GuideTemplate
    report: typing.Callable[[str], None]  # przyjmuje gotową linię postępu (progress.format_line); main.py: progress.print_line


def build_context(
    app_config: _config.AppConfig,
    store: _output.RunStore,
    report: typing.Callable[[str], None],
) -> RunContext:
    """Składa RunContext: tworzy modele wszystkich agentów z configu, wczytuje spis bazy wiedzy i szablon przewodnika.

    Po co: jedno miejsce, w którym powstają zależności przebiegu; błąd configu, brak zmiennej środowiskowej z kluczem,
    błędny spis bazy wiedzy albo szablon wychodzą przy starcie, z nazwą przyczyny.

    Argumenty: app_config - wynik config.load_config(), store - magazyn wyników projektu (output.create_run_store),
    report - funkcja przyjmująca linię postępu (progress.print_line na ekranie, list.append w teście).
    """
    modele = {}
    for agent_name in app_config.llm.agents:
        modele[agent_name] = _llm.get_model_for_agent(app_config, agent_name)
    spis = _knowledge.load_index(app_config.paths.knowledge_base)
    szablon = _template.load_template(app_config.paths.guide_template)
    kontekst = RunContext(
        config=app_config,
        store=store,
        models=modele,
        knowledge_index=spis,
        template=szablon,
        report=report,
    )
    return kontekst
