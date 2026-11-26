"""Agent recenzent: ocenia gotowy przewodnik (diagram i zakładki) z notatkami analityków i wskazuje, co poprawić.

Co robi: review_guide() składa prompt (podsumowanie plannera, kontekst projektu, pełne notatki analityków w kolejności
czytania, diagram, treść zakładek od pisarzy, wiedza: zasady pisania i diagramu, technologia, framework), woła model
agenta reviewer ze schematem ReviewResult i sprawdza odpowiedź kodem: adresat każdej uwagi musi być diagramem albo
zakładką z treścią, sekcja uwagi sekcją tej zakładki, opis niepusty. Gdy są problemy, woła model jeszcze raz - z poprzednią
recenzją i listą problemów w prompcie; drugą wersję bierze, chyba że ma więcej problemów niż pierwsza. Uwagi, których nie
da się przypisać (nieznany adresat, pusty opis), są odrzucane z uwagą w linii postępu; błędną sekcję kod czyści. Flagę
approved ustawia kod: prawda tylko wtedy, gdy uwag nie ma. reviewer_node() to węzeł grafu: zapisuje review_NN.json
(historia rund) i dopisuje do stanu review, review_round i fixes_pending (są uwagi i limit rund nie jest wyczerpany).

Dlaczego istnieje: braki formalne (brak sekcji, liczba komórek, odwołania do klocków) sprawdza kod w pisarzach i w assemble,
ale prawdziwość i konkretność może ocenić tylko model, który widzi notatki i treść razem: zdanie niepoparte notatkami,
sprzeczność, brak kroku lub ścieżki, diagram zbyt ogólny albo przeładowany, ogólnik zamiast konkretu, sekret w złym miejscu,
wymysł tam, gdzie notatki mówią „nie wynika z kodu”. Puste pole nie jest uwagą - luka jest lepsza niż wymysł. Uwagi mają
adresata, żeby pętla recenzji (krok 59) przepisywała tylko diagram albo zakładki, których dotyczą.

Rola: agent grafu (faza F); w grafie stoi po assemble, a po nim pętla poprawek celowanych (krok 59, review_loop.py).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.agents.reviewer
        offline, na udawanym modelu: adresaci uwag (diagram i zakładki pisarzy), prompt (pełne notatki, diagram, treść
        zakładek, zasady pisania i diagramu, adresaci, brak ścieżki dysku, brak poprawki), flaga approved ustawiana przez kod,
        uwagi i sugestie zachowane, ponowienie przy nieznanym adresacie z poprzednią recenzją i listą problemów, odrzucenie
        uwag bez adresata po ponowieniu, wybór lepszej z dwóch wersji, czyszczenie błędnej sekcji, pusty opis, sekcja
        diagramu, odmowa bez notatek i bez treści, węzeł grafu (review_NN.json, numer rundy, fixes_pending, linie postępu); na końcu "zgodne z oczekiwaniem: True"
    python -m dev_agents.agents.reviewer <katalog robota>
        dodatkowo woła PRAWDZIWY model: skanuje robota w pamięci, czyta <katalog robota>/dev_agents_doc/guide_content.json,
        notes/*.json i plan.json (najpierw pełny przebieg: python main.py --project <katalog robota>), wypisuje uwagi
        z przypisaniem do zakładek i sugestie, zapisuje review_01.json w katalogu wyników robota.
        Wymaga zmiennych środowiskowych z kluczem i adresem modeli (nazwy w config.yaml).
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

import dev_agents.agents.common as _common
import dev_agents.agents.flow_writer as _flow_writer
import dev_agents.agents.writer as _writer
import dev_agents.context as _context
import dev_agents.guide_content as _content
import dev_agents.guide_template as _template
import dev_agents.llm as _llm
import dev_agents.progress as _progress
import dev_agents.prompts as _prompts
import dev_agents.schemas as _schemas
import dev_agents.state as _state

_AGENT_NAME = "reviewer"
_FLOW_TARGET = "flow"


# --- Adresaci uwag ---


def review_targets(
    template: _template.GuideTemplate,
    technology: str,
) -> list[tuple[str, str]]:
    """Zwraca adresatów uwag jako (id, tytuł): najpierw diagram ("flow"), potem zakładki, które piszą pisarze, w kolejności szablonu technologii.

    Po co: uwaga trafia do tego, kto może ją poprawić - do autora diagramu albo do pisarza zakładki; zakładki bez
    sekcji dla pisarza (np. sam diagram) nie są adresatami.
    """
    szablon_technologii = _template.sections_for_technology(template, technology)
    adresaci = [(_FLOW_TARGET, "Diagram przepływu")]
    for zakladka in szablon_technologii.tabs:
        if _writer.writer_sections(zakladka):
            adresaci.append((zakladka.id, zakladka.title))
    return adresaci


def review_sections(
    content: _content.GuideContent,
    targets: list[tuple[str, str]],
) -> dict[str, set[str]]:
    """Zwraca dla każdego adresata zbiór id sekcji, które mogą być przedmiotem uwagi: dla diagramu pusty, dla zakładki - sekcje jej bloków w treści; zakładka bez treści ma pusty zbiór.

    Po co: kod sprawdza, czy uwaga wskazuje sekcję, która naprawdę jest w treści zakładki.
    """
    bloki_wedlug_zakladek = {}
    for zakladka in content.tabs:
        identyfikatory = set()
        for blok in zakladka.blocks:
            identyfikatory.add(blok.section_id)
        bloki_wedlug_zakladek[zakladka.tab_id] = identyfikatory
    wynik = {}
    for identyfikator, _ in targets:
        wynik[identyfikator] = bloki_wedlug_zakladek.get(identyfikator, set())
    return wynik


# --- Dane dla promptu ---


def format_targets(
    targets: list[tuple[str, str]],
) -> str:
    """Zwraca listę adresatów uwag do promptu: linie "- id: tytuł" (diagram jako "flow").

    Po co: recenzent widzi dokładne id, których może użyć jako target.
    """
    linie = []
    for identyfikator, tytul in targets:
        linie.append(f"- {identyfikator}: {tytul}")
    tekst = "\n".join(linie)
    return tekst


def format_tabs(
    content: _content.GuideContent,
    targets: list[tuple[str, str]],
) -> str:
    """Zwraca treść zakładek pisarzy do promptu: każda w znaczniku <zakladka id="..." tytul="...">, w treści JSON bez pustych pól; kolejność jak u adresatów.

    Po co: recenzent widzi to, co napisali pisarze, a pola puste (luki) nie zajmują tokenów; zakładki spoza adresatów
    (bez pisarza) nie są oceniane.
    """
    wedlug_id = {}
    for zakladka in content.tabs:
        wedlug_id[zakladka.tab_id] = zakladka
    bloki = []
    for identyfikator, tytul in targets:
        if identyfikator in wedlug_id:
            tresc = wedlug_id[identyfikator].model_dump_json(indent=1, exclude_defaults=True)
            bloki.append(f'<zakladka id="{identyfikator}" tytul="{tytul}">\n{tresc}\n</zakladka>')
    tekst = "\n\n".join(bloki)
    return tekst


def build_review_variables(
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    notes: list[_schemas.ModuleNote],
    content: _content.GuideContent,
    targets: list[tuple[str, str]],
    knowledge_text: str,
    previous_review: _schemas.ReviewResult | None,
    problems: list[str],
) -> dict:
    """Zwraca zmienne do szablonu prompts/reviewer/user.md; przy ponowieniu (poprzednia recenzja i problemy) także sekcję poprawki.

    Po co: w jednym miejscu widać, co dokładnie recenzent dostaje. Argumenty: notes - notatki w kolejności czytania,
    targets - wynik review_targets, knowledge_text - gotowy tekst wiedzy (common.format_knowledge), previous_review
    i problems - poprzednia recenzja i lista problemów albo None i pusta lista przy pierwszym wywołaniu.
    """
    poprzedni_tekst = ""
    if previous_review is not None:
        poprzedni_tekst = previous_review.model_dump_json(indent=1)
    linie_problemow = []
    for problem in problems:
        linie_problemow.append(f"- {problem}")
    zmienne = {
        "project_name": project_map.project_name,
        "plan_summary": plan.summary,
        "targets": format_targets(targets),
        "project_context": _flow_writer.build_project_context(project_map),
        "notes": _writer.format_notes(notes),
        "flow": _writer.format_flow(content.flow),
        "tabs": format_tabs(content, targets),
        "knowledge": knowledge_text,
        "previous_review": poprzedni_tekst,
        "problems_text": "\n".join(linie_problemow),
    }
    return zmienne


# --- Sprawdzanie odpowiedzi ---


def _issue_problem(
    number: int,
    issue: _schemas.ReviewIssue,
    sections: dict[str, set[str]],
) -> str:
    """Zwraca opis problemu uwagi o danym numerze (od 1) albo pusty tekst, gdy uwaga jest poprawna: nieznany adresat, pusty opis albo sekcja spoza zakładki.

    Po co: jedno miejsce reguł dla sprawdzenia odpowiedzi i dla oczyszczenia recenzji. Dla diagramu sekcja jest zawsze
    pusta, więc błędna wartość nie jest problemem (czyści ją sanitize_review).
    """
    problem = ""
    if issue.target not in sections:
        dozwolone = ", ".join(sections)
        problem = f'uwaga {number}: nieznany adresat "{issue.target}" (dozwolone: {dozwolone})'
    elif issue.description.strip() == "":
        problem = f'uwaga {number} (adresat "{issue.target}"): pusty opis'
    elif issue.target != _FLOW_TARGET and issue.section_id != "" and issue.section_id not in sections[issue.target]:
        problem = f'uwaga {number} (adresat "{issue.target}"): sekcja "{issue.section_id}" nie istnieje w tej zakładce (dozwolone: {", ".join(sorted(sections[issue.target]))} albo pusty tekst)'
    return problem


def check_review(
    review: _schemas.ReviewResult,
    sections: dict[str, set[str]],
) -> list[str]:
    """Zwraca listę problemów recenzji (pusta, gdy poprawna): uwagi z nieznanym adresatem, pustym opisem albo błędną sekcją.

    Po co: kod pilnuje tego, co da się sprawdzić; problemy wracają do modelu w ponowieniu.
    """
    problemy = []
    for numer, uwaga in enumerate(review.issues, start=1):
        problem = _issue_problem(numer, uwaga, sections)
        if problem != "":
            problemy.append(problem)
    return problemy


def sanitize_review(
    review: _schemas.ReviewResult,
    sections: dict[str, set[str]],
) -> tuple[_schemas.ReviewResult, list[str]]:
    """Zwraca (recenzja po oczyszczeniu, uwagi kodu): odrzuca uwagi z nieznanym adresatem i pustym opisem, czyści błędną sekcję, ustawia approved = brak uwag.

    Po co: po ponowieniu do pętli poprawek trafiają tylko uwagi z adresatem; to, co kod odrzucił albo poprawił, jest
    zgłoszone w uwagach (nic nie znika po cichu). Uwaga o diagramie zawsze ma pustą sekcję.
    """
    uwagi_kodu = []
    zachowane = []
    for numer, uwaga in enumerate(review.issues, start=1):
        problem = _issue_problem(numer, uwaga, sections)
        adresat_znany = uwaga.target in sections
        opis_niepusty = uwaga.description.strip() != ""
        if not adresat_znany or not opis_niepusty:
            uwagi_kodu.append(f"odrzucona {problem}")
        elif uwaga.target == _FLOW_TARGET:
            zachowane.append(uwaga.model_copy(update={"section_id": ""}))
        elif problem != "":
            uwagi_kodu.append(f"poprawiona {problem}; sekcja wyczyszczona")
            zachowane.append(uwaga.model_copy(update={"section_id": ""}))
        else:
            zachowane.append(uwaga)
    oczyszczona = _schemas.ReviewResult(approved=len(zachowane) == 0, issues=zachowane, suggestions=review.suggestions)
    wynik = (oczyszczona, uwagi_kodu)
    return wynik


# --- Wywołanie modelu ---


def _ask_model(
    context: _context.RunContext,
    variables: dict,
) -> _schemas.ReviewResult:
    """Składa prompt z podanych zmiennych, woła model agenta reviewer ze schematem ReviewResult i zwraca recenzję.

    Po co: jedno wywołanie modelu - pierwsze i ponowione różnią się tylko zmiennymi. Brak odpowiedzi zgodnej ze
    schematem kończy się RuntimeError z przyczyną (llm.invoke_structured).
    """
    tekst_system, tekst_user = _prompts.render_prompt(context.config.paths.prompts, _AGENT_NAME, variables)
    odpowiedz = _llm.invoke_structured(
        context.models[_AGENT_NAME],
        _schemas.ReviewResult,
        _llm.get_structured_output_method(context.config, _AGENT_NAME),
        [SystemMessage(content=tekst_system), HumanMessage(content=tekst_user)],
    )
    return odpowiedz


def review_guide(
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    notes: list[_schemas.ModuleNote],
    content: _content.GuideContent,
    context: _context.RunContext,
) -> tuple[_schemas.ReviewResult, list[str], int]:
    """Recenzuje przewodnik: zwraca (recenzja po oczyszczeniu, uwagi kodu o odrzuconych i poprawionych uwagach, liczba wywołań modelu - 1 albo 2).

    Po co: cała logika recenzenta w jednej funkcji, z której korzystają węzeł grafu i test ręczny. Pierwsza wersja z promptu
    z notatkami w kolejności czytania, diagramem i treścią zakładek; gdy kod zgłosi problemy (adresat, sekcja, opis), model
    dostaje jedno ponowienie z poprzednią recenzją i listą problemów. Druga wersja wygrywa, chyba że ma więcej problemów niż
    pierwsza. Zwrócona recenzja ma tylko uwagi z adresatem, a approved ustawia kod.

    Uwaga: brak notatek albo brak treści zakładek pisarzy to ValueError - nie ma czego recenzować. Wiedza: pliki plannera
    dla pisarzy i dla autora diagramu (recenzent ocenia jedno i drugie), bez powtórzeń.
    """
    if not notes:
        komunikat_bledu = "Brak notatek analityków - nie ma z czym porównać przewodnika"
        raise ValueError(komunikat_bledu)
    adresaci = review_targets(context.template, project_map.technology)
    sekcje = review_sections(content, adresaci)
    jest_tresc = False
    for identyfikator, _ in adresaci:
        if identyfikator != _FLOW_TARGET and sekcje[identyfikator]:
            jest_tresc = True
    if not jest_tresc:
        komunikat_bledu = "Brak treści zakładek od pisarzy - nie ma czego recenzować"
        raise ValueError(komunikat_bledu)
    uporzadkowane = _flow_writer.order_notes(notes, plan)
    pliki_wiedzy = _common.collect_knowledge_files(context.config, project_map, plan.writer_knowledge + plan.flow_knowledge)
    tekst_wiedzy = _common.format_knowledge(context.config, pliki_wiedzy)
    zmienne = build_review_variables(project_map, plan, uporzadkowane, content, adresaci, tekst_wiedzy, None, [])
    recenzja = _ask_model(context, zmienne)
    problemy = check_review(recenzja, sekcje)
    wywolania = 1
    if problemy:
        zmienne_poprawki = build_review_variables(project_map, plan, uporzadkowane, content, adresaci, tekst_wiedzy, recenzja, problemy)
        druga_recenzja = _ask_model(context, zmienne_poprawki)
        wywolania = 2
        problemy_2 = check_review(druga_recenzja, sekcje)
        if len(problemy_2) <= len(problemy):
            recenzja = druga_recenzja
    oczyszczona, uwagi_kodu = sanitize_review(recenzja, sekcje)
    wynik = (oczyszczona, uwagi_kodu, wywolania)
    return wynik


# --- Węzeł grafu ---


def reviewer_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Węzeł reviewer: recenzuje treść ze stanu, zapisuje review_NN.json i zwraca zmienione pola stanu: review, review_round i fixes_pending.

    Po co: etap po złożeniu treści - kontrola prawdziwości i konkretności. Numer rundy to poprzedni review_round + 1;
    fixes_pending to "są uwagi i limits.max_review_rounds nie jest wyczerpany" - krawędź warunkowa grafu widzi tylko stan,
    więc decyzję o limicie podejmuje węzeł. Praca jest owinięta w Stage: start, uwagi kodu o odrzuconych i poprawionych
    uwagach, każda uwaga recenzenta z adresatem, koniec z czasem, numerem rundy, liczbą uwag i sugestii, werdyktem i liczbą
    wywołań modelu. Każda runda zostaje w historii (review_01.json, review_02.json, ...).
    """
    kontekst = runtime.context
    numer_rundy = state.get("review_round", 0) + 1
    with _progress.Stage(kontekst.report, _AGENT_NAME) as etap:
        recenzja, uwagi_kodu, wywolania = review_guide(state["project_map"], state["plan"], state["notes"], state["content"], kontekst)
        for uwaga_kodu in uwagi_kodu:
            etap.note(uwaga_kodu)
        for uwaga in recenzja.issues:
            etap.note(f"uwaga [{uwaga.target}] {uwaga.section_id}: {uwaga.description}".replace("]  :", "]:"))
        zapisany_plik = kontekst.store.save_json(f"review_{numer_rundy:02d}.json", recenzja)
        poprawki_potrzebne = len(recenzja.issues) > 0 and numer_rundy < kontekst.config.limits.max_review_rounds
        etap.set_result(
            f"runda {numer_rundy}, uwag: {len(recenzja.issues)}, sugestii: {len(recenzja.suggestions)}, zatwierdzone: {recenzja.approved}, "
            f"wywołań modelu: {wywolania}, zapisano {zapisany_plik}"
        )
    zmiana_stanu = {"review": recenzja, "review_round": numer_rundy, "fixes_pending": poprawki_potrzebne}
    return zmiana_stanu


# --- Test ręczny ---

if __name__ == "__main__":
    import glob
    import os
    import sys
    import tempfile
    import types

    import dev_agents.config as _config
    import dev_agents.fakes as _fakes
    import dev_agents.output as _output
    import dev_agents.scanner as _scanner

    _GOALS_MARKER = "Jak piszemy przewodnik po robocie"
    _RULES_MARKER = "Zasady diagramu przepływu"

    def _note(
        unit_name: str,
        purpose: str,
    ) -> _schemas.ModuleNote:
        """Zwraca notatkę z jedną czynnością, ustawieniem i ryzykiem - tyle, by sprawdzić, że recenzent dostaje pełną notatkę.

        Po co: w odróżnieniu od autora diagramu recenzent musi widzieć ustawienia i ryzyka, żeby sprawdzić zakładki.
        """
        notatka = _schemas.ModuleNote.model_validate(
            {
                "unit_name": unit_name,
                "purpose": purpose,
                "flow_role": "Główna jednostka.",
                "automated_application": "",
                "key_functions": [],
                "actions": [{"title": f"Czynność {unit_name}", "kind": "step", "function": "run", "line": 5, "description": "", "reads": [], "writes": [], "certain": True}],
                "process_steps": [],
                "error_handling": [],
                "inputs": [],
                "outputs": [],
                "settings": [{"file": "config.yaml", "group": "", "key": "WIDOCZNE_USTAWIENIE", "value": "x", "kind": "other", "location": "", "used_in": [], "plain_password": False, "meaning": "", "certain": True}],
                "requirements": [],
                "external_dependencies": [],
                "risky_places": [{"place": "run", "location": "a.py:1-2", "kind": "test", "reason": "WIDOCZNE_RYZYKO"}],
                "possible_failures": [],
                "extension_points": [],
                "conventions": [],
                "maintainer_hints": [],
                "glossary_candidates": [],
            }
        )
        return notatka

    def _diagram() -> _content.FlowGraph:
        """Zwraca prosty poprawny diagram: start, jeden krok i koniec.

        Po co: recenzent dostaje diagram w treści; test sprawdza tylko, że trafia do promptu.
        """
        klocki = [
            _content.FlowNode(id="s0", kind="start", label="Start"),
            _content.FlowNode(id="n0", kind="step", label="KLOCEK_TESTOWY", module="main.py", functions=["run:5"]),
            _content.FlowNode(id="k", kind="end", label="Koniec"),
        ]
        strzalki = [_content.FlowEdge(source="s0", target="n0"), _content.FlowEdge(source="n0", target="k")]
        diagram = _content.FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    def _content_for(
        template: _template.GuideTemplate,
        technology: str,
    ) -> _content.GuideContent:
        """Zwraca treść przewodnika: diagram i po jednej zakładce na adresata-pisarza, z jednym blokiem pierwszej sekcji pisarza i akapitem TRESC_<id zakładki>.

        Po co: kontrolowana treść do sprawdzenia promptu i adresatów.
        """
        zakladki = []
        for identyfikator, _ in review_targets(template, technology):
            if identyfikator == _FLOW_TARGET:
                continue
            for szablon_zakladki in _template.sections_for_technology(template, technology).tabs:
                if szablon_zakladki.id == identyfikator:
                    sekcje_pisarza = _writer.writer_sections(szablon_zakladki)
            pierwsza = sekcje_pisarza[0]
            blok = _content.GuideBlock(section_id=pierwsza.id, paragraphs=[f"TRESC_{identyfikator}"])
            zakladki.append(_content.GuideTab(tab_id=identyfikator, blocks=[blok]))
        tresc = _content.GuideContent(project_name="robot_testowy", flow=_diagram(), tabs=zakladki)
        return tresc

    def _model(
        answers: list[_schemas.ReviewResult],
        seen_prompts: list[str],
    ) -> _fakes.FakeStructuredModel:
        """Zwraca udawany model, który kolejnymi wywołaniami odpowiada kolejnymi recenzjami z listy i zapamiętuje prompty użytkownika.

        Po co: test steruje tym, co model odpowie przy pierwszym i ponowionym wywołaniu.
        """

        def answer(
            messages,
        ):
            """Zapamiętuje prompt użytkownika i zwraca recenzję o numerze równym liczbie dotychczasowych promptów (ostatnia powtarza się).

            Po co: odpowiedź udawanego modelu zależna od numeru wywołania.
            """
            numer = len(seen_prompts)
            seen_prompts.append(messages[1].content)
            odpowiedz = answers[min(numer, len(answers) - 1)]
            return odpowiedz

        model = _fakes.FakeStructuredModel(answer)
        return model

    def _context_for(
        app_config: _config.AppConfig,
        template: _template.GuideTemplate,
        model,
        report,
        store,
    ) -> types.SimpleNamespace:
        """Zwraca uproszczony kontekst (config, szablon, model reviewer, report, magazyn) - tyle, ile czytają review_guide i węzeł.

        Po co: test offline nie buduje prawdziwych modeli wszystkich agentów i nie wymaga kluczy.
        """
        kontekst = types.SimpleNamespace(config=app_config, template=template, models={_AGENT_NAME: model}, report=report, store=store)
        return kontekst

    def _issue(
        target: str,
        section_id: str = "",
        description: str = "Uwaga testowa.",
    ) -> _schemas.ReviewIssue:
        """Zwraca uwagę o podanym adresacie, sekcji i opisie.

        Po co: skrót w testach.
        """
        uwaga = _schemas.ReviewIssue(target=target, section_id=section_id, description=description)
        return uwaga

    def _review(
        issues: list[_schemas.ReviewIssue],
        approved: bool = False,
        suggestions: list[str] | None = None,
    ) -> _schemas.ReviewResult:
        """Zwraca recenzję z podanymi uwagami; flaga approved jest taka, jak podano (test sprawdza, że kod ją poprawia).

        Po co: skrót w testach.
        """
        recenzja = _schemas.ReviewResult(approved=approved, issues=issues, suggestions=suggestions or [])
        return recenzja

    def _offline_checks(
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza recenzenta na udawanym modelu; zwraca (opis, zgodne).

        Po co: adresaci, prompt, flaga approved, ponowienia, odrzucanie uwag bez adresata, czyszczenie sekcji, brak notatek
        i treści oraz węzeł grafu bez sieci i kosztu.
        """
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _schemas.ProjectMap(
            project_name="robot_testowy",
            root=os.path.join(temp_dir, "ukryty_katalog_uzytkownika"),
            technology="python",
            entrypoints=["main.py"],
            files=[],
            code_units=[],
            reading_order=["main.py", "helper.py"],
            dependency_edges=[["main.py", "helper.py"]],
        )
        plan = _schemas.Plan(
            summary="Plan testowy.",
            tasks=[_schemas.AnalysisTask(unit="main.py"), _schemas.AnalysisTask(unit="helper.py")],
            flow_knowledge=["diagram_rules.md"],
            writer_knowledge=["guide_goals.md"],
        )
        notatki = [_note("helper.py", "CEL_POMOCNIKA"), _note("main.py", "CEL_GLOWNEJ")]
        tresc = _content_for(szablon, "python")
        adresaci = review_targets(szablon, "python")
        identyfikatory = []
        for identyfikator, _ in adresaci:
            identyfikatory.append(identyfikator)
        sekcje = review_sections(tresc, adresaci)
        zakladka = identyfikatory[1]
        sekcja_zakladki = sorted(sekcje[zakladka])[0]
        magazyn = _output.RunStore(os.path.join(temp_dir, "wyniki"))
        wyniki = []

        oczekiwani = ["flow"]
        for zakladka_szablonu in szablon.tabs:
            if _writer.writer_sections(zakladka_szablonu):
                oczekiwani.append(zakladka_szablonu.id)
        wyniki.append((f"review_targets: diagram i zakładki pisarzy ({identyfikatory})", identyfikatory == oczekiwani and identyfikatory[0] == "flow"))
        wyniki.append(("review_sections: diagram bez sekcji, zakładka z sekcją z treści", sekcje["flow"] == set() and len(sekcje[zakladka]) == 1))

        prompty = []
        model = _model([_review([], approved=False, suggestions=["Powtórzenie w opisie."])], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        pierwszy = prompty[0]
        wyniki.append(("bez uwag: jedno wywołanie, approved ustawione przez kod na True", model.calls == 1 and wywolania == 1 and recenzja.approved is True and recenzja.issues == [] and uwagi_kodu == []))
        wyniki.append(("sugestie zachowane", recenzja.suggestions == ["Powtórzenie w opisie."]))
        wyniki.append(("prompt: pełne notatki (ustawienia i ryzyka też)", "CEL_GLOWNEJ" in pierwszy and "WIDOCZNE_USTAWIENIE" in pierwszy and "WIDOCZNE_RYZYKO" in pierwszy))
        wyniki.append(("prompt: notatki w kolejności czytania", 0 < pierwszy.index("CEL_GLOWNEJ") < pierwszy.index("CEL_POMOCNIKA")))
        wyniki.append(("prompt: diagram jako lista klocków", "KLOCEK_TESTOWY" in pierwszy and "n0 | step" in pierwszy))
        wyniki.append(("prompt: treść zakładek w znacznikach z id i tytułem", f'<zakladka id="{zakladka}"' in pierwszy and f"TRESC_{zakladka}" in pierwszy))
        wyniki.append(("prompt: adresaci uwag z id", "- flow: Diagram przepływu" in pierwszy and f"- {zakladka}: " in pierwszy))
        wyniki.append(("prompt: zasady pisania i zasady diagramu", _GOALS_MARKER in pierwszy and _RULES_MARKER in pierwszy))
        wyniki.append(("prompt: kontekst projektu, bez ścieżki dysku i bez poprawki", '"reading_order"' in pierwszy and "ukryty_katalog_uzytkownika" not in pierwszy and "<poprawka>" not in pierwszy))

        model = _model([_review([_issue("flow", "", "Brak klocka wysyłki."), _issue(zakladka, sekcja_zakladki, "Wymysł w zdaniu.")], approved=True)], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("uwagi poprawne: zachowane, approved ustawione przez kod na False", model.calls == 1 and len(recenzja.issues) == 2 and recenzja.approved is False and uwagi_kodu == []))

        prompty = []
        pierwsza_zla = _review([_issue("nie_ma_takiej", "", "Uwaga do nikogo.")])
        poprawna = _review([_issue(zakladka, sekcja_zakladki, "Uwaga do zakładki.")])
        model = _model([pierwsza_zla, poprawna], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("nieznany adresat: ponowienie, druga recenzja poprawna", model.calls == 2 and wywolania == 2 and recenzja.issues == poprawna.issues and uwagi_kodu == []))
        wyniki.append(("ponowienie: prompt z poprzednią recenzją i listą problemów", "<poprawka>" in prompty[1] and "Uwaga do nikogo." in prompty[1] and 'nieznany adresat "nie_ma_takiej"' in prompty[1]))

        model = _model([pierwsza_zla], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("nieznany adres po ponowieniu: uwaga odrzucona z uwagą kodu, approved True", model.calls == 2 and recenzja.issues == [] and recenzja.approved is True and len(uwagi_kodu) == 1 and "odrzucona" in uwagi_kodu[0] and "nie_ma_takiej" in uwagi_kodu[0]))

        dwie_zle = _review([_issue("x1"), _issue("x2")])
        jedna_zla_i_dobra = _review([_issue("x1"), _issue("flow", "", "Dobra.")])
        model = _model([jedna_zla_i_dobra, dwie_zle], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("druga wersja gorsza (więcej problemów): zostaje pierwsza, z dobrą uwagą", model.calls == 2 and len(recenzja.issues) == 1 and recenzja.issues[0].description == "Dobra." and len(uwagi_kodu) == 1))

        model = _model([_review([_issue(zakladka, "nie_ma_sekcji", "Uwaga.")])], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("błędna sekcja po ponowieniu: uwaga zostaje, sekcja wyczyszczona, uwaga kodu", model.calls == 2 and len(recenzja.issues) == 1 and recenzja.issues[0].section_id == "" and len(uwagi_kodu) == 1 and "poprawiona" in uwagi_kodu[0]))

        model = _model([_review([_issue("flow", "", "   ")])], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("pusty opis: ponowienie i odrzucenie uwagi", model.calls == 2 and recenzja.issues == [] and len(uwagi_kodu) == 1 and "pusty opis" in uwagi_kodu[0]))

        model = _model([_review([_issue("flow", "cokolwiek", "Brak klocka.")])], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        recenzja, uwagi_kodu, wywolania = review_guide(mapa, plan, notatki, tresc, kontekst)
        wyniki.append(("uwaga o diagramie z sekcją: bez ponowienia, sekcja wyczyszczona po cichu", model.calls == 1 and recenzja.issues[0].section_id == "" and uwagi_kodu == []))

        blad = ""
        try:
            review_guide(mapa, plan, [], tresc, kontekst)
        except ValueError as wyjatek:
            blad = str(wyjatek)
        wyniki.append(("brak notatek: ValueError", "Brak notatek" in blad))

        blad = ""
        pusta_tresc = tresc.model_copy(update={"tabs": []})
        try:
            review_guide(mapa, plan, notatki, pusta_tresc, kontekst)
        except ValueError as wyjatek:
            blad = str(wyjatek)
        wyniki.append(("brak treści zakładek: ValueError", "Brak treści zakładek" in blad))

        linie = []
        model = _model([_review([_issue(zakladka, sekcja_zakladki, "Uwaga węzła.")], suggestions=["Sugestia."])], [])
        kontekst = _context_for(app_config, szablon, model, linie.append, magazyn)
        stan = {"project_map": mapa, "plan": plan, "notes": notatki, "content": tresc}
        zmiana = reviewer_node(stan, types.SimpleNamespace(context=kontekst))
        zapisana = magazyn.load_json("review_01.json", _schemas.ReviewResult)
        wyniki.append(("węzeł: zwraca review, numer rundy 1 i fixes_pending, zapisuje review_01.json", sorted(zmiana) == ["fixes_pending", "review", "review_round"] and zmiana["review"] == zapisana and zmiana["review_round"] == 1 and zmiana["fixes_pending"] is True and len(zapisana.issues) == 1 and zapisana.approved is False))
        wyniki.append(("węzeł: linie postępu start, uwaga z adresatem i koniec z liczbami", len(linie) == 3 and linie[0].endswith("] reviewer: start") and f"uwaga [{zakladka}] {sekcja_zakladki}: Uwaga węzła." in linie[1] and "runda 1, uwag: 1, sugestii: 1, zatwierdzone: False, wywołań modelu: 1" in linie[2]))

        linie = []
        model = _model([_review([_issue(zakladka, sekcja_zakladki, "Uwaga drugiej rundy.")])], [])
        kontekst = _context_for(app_config, szablon, model, linie.append, magazyn)
        druga_runda = reviewer_node({**stan, "review_round": app_config.limits.max_review_rounds - 1}, types.SimpleNamespace(context=kontekst))
        wyniki.append(("węzeł: ostatnia dozwolona runda - uwagi zostają, fixes_pending False, review_NN.json", druga_runda["review_round"] == app_config.limits.max_review_rounds and druga_runda["fixes_pending"] is False and len(druga_runda["review"].issues) == 1 and os.path.isfile(magazyn.path(f"review_{app_config.limits.max_review_rounds:02d}.json"))))

        linie = []
        model = _model([_review([])], [])
        kontekst = _context_for(app_config, szablon, model, linie.append, magazyn)
        bez_uwag = reviewer_node(stan, types.SimpleNamespace(context=kontekst))
        wyniki.append(("węzeł: bez uwag - fixes_pending False, approved True", bez_uwag["fixes_pending"] is False and bez_uwag["review"].approved is True))
        return wyniki

    def _real_model_run(
        project_dir: str,
        app_config: _config.AppConfig,
    ) -> None:
        """Czyta treść i notatki robota z dev_agents_doc, woła prawdziwy model recenzenta, wypisuje uwagi z adresatami i zapisuje review.json.

        Po co: sprawdzenie recenzenta na prawdziwej treści z poprzedniego przebiegu (guide_content.json), bez ponownej
        analizy i pisania. Robota nie zmienia poza katalogiem wyników (review.json).
        """
        project_map = _scanner.build_project_map(project_dir, app_config.scan)
        katalog_wynikow = os.path.join(project_dir, _output.OUTPUT_DIR_NAME)
        sciezka_tresci = os.path.join(katalog_wynikow, "guide_content.json")
        if not os.path.isfile(sciezka_tresci):
            sys.exit(f"BŁĄD: brak {sciezka_tresci} - najpierw pełny przebieg: python main.py --project {project_dir}")
        with open(sciezka_tresci, encoding="utf-8") as plik:
            tresc = _content.GuideContent.model_validate_json(plik.read())
        pliki_notatek = sorted(glob.glob(os.path.join(katalog_wynikow, "notes", "**", "*.json"), recursive=True))
        if not pliki_notatek:
            sys.exit(f"BŁĄD: brak notatek w {os.path.join(katalog_wynikow, 'notes')} - najpierw pełny przebieg: python main.py --project {project_dir}")
        notatki = []
        for plik_notatki in pliki_notatek:
            with open(plik_notatki, encoding="utf-8") as plik:
                notatki.append(_schemas.ModuleNote.model_validate_json(plik.read()))
        sciezka_planu = os.path.join(katalog_wynikow, "plan.json")
        if os.path.isfile(sciezka_planu):
            with open(sciezka_planu, encoding="utf-8") as plik:
                plan = _schemas.Plan.model_validate_json(plik.read())
        else:
            plan = _schemas.Plan(summary=f"Robot {project_map.project_name} (technologia: {project_map.technology}); plan minimalny.", tasks=[])
            print("Plan minimalny (brak plan.json w katalogu wyników robota).")
        magazyn = _output.RunStore(katalog_wynikow)
        try:
            kontekst = _context.build_context(app_config, magazyn, _progress.print_line)
        except (RuntimeError, ValueError, OSError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        print(f"\n=== Prawdziwy model recenzenta: {project_map.project_name}, notatek: {len(notatki)}, zakładek w treści: {len(tresc.tabs)} ===")
        stan = {"project_map": project_map, "plan": plan, "notes": notatki, "content": tresc}
        try:
            zmiana = reviewer_node(stan, types.SimpleNamespace(context=kontekst))
        except (ValueError, RuntimeError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        recenzja = zmiana["review"]
        print(f"\nZatwierdzone: {recenzja.approved}, uwag: {len(recenzja.issues)}, sugestii: {len(recenzja.suggestions)}")
        adresaci = set()
        for uwaga in recenzja.issues:
            adresaci.add(uwaga.target)
        for adresat in sorted(adresaci):
            print(f"\n[{adresat}]")
            for uwaga in recenzja.issues:
                if uwaga.target == adresat:
                    print(f"  - ({uwaga.section_id or 'cała zakładka'}) {uwaga.description}")
        if recenzja.suggestions:
            print("\nSugestie:")
            for sugestia in recenzja.suggestions:
                print(f"  - {sugestia}")
        print(f"\nZapisano review_{zmiana['review_round']:02d}.json w {katalog_wynikow}")

    def manual_test():
        """Uruchamia sprawdzenia offline recenzenta i wypisuje werdykt; z argumentem <katalog robota> woła też prawdziwy model.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że recenzent składa prompt, ponawia i oczyszcza uwagi poprawnie;
        część z prawdziwym modelem pokazuje uwagi do prawdziwej treści.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        temp_dir = tempfile.mkdtemp()
        try:
            wyniki = _offline_checks(app_config, temp_dir)
            print("=== Sprawdzenia offline ===")
            wszystkie_zgodne = True
            for opis, zgodne in wyniki:
                print(f"  {opis}: {zgodne}")
                if not zgodne:
                    wszystkie_zgodne = False
            print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
            if len(sys.argv) > 1:
                _real_model_run(sys.argv[1], app_config)
        finally:
            import shutil

            shutil.rmtree(temp_dir)

    manual_test()
