"""Agent pisarz zakładki: z notatek, diagramu i plików robota pisze treść jednej zakładki przewodnika (GuideTab).

Co robi: write_tab() składa prompt (sekcje zakładki z szablonu, kontekst projektu, notatki analityków, gotowy diagram,
pliki konfiguracyjne i uruchamiające - tylko dla zakładki z metryczką, fakty kodu o długich jednostkach - tylko dla
zakładki z ryzykownymi miejscami, wiedza dla pisarzy), woła model agenta writer i zamienia odpowiedź na GuideTab.
Kod sprawdza wynik (check_tab): brak wymaganej sekcji, wiersz tabeli o złej liczbie komórek, wpis metryczki bez
znaczenia, ścieżka bez głównej albo odwołująca się do nieistniejącego klocka. Gdy są problemy, model dostaje jedno
ponowienie z poprzednią wersją i listą problemów; druga wersja wygrywa, chyba że ma więcej problemów. Odwołania do
nieistniejących klocków zostają na końcu wyczyszczone (problem zostaje w wyniku). writer_node() to węzeł grafu:
zapisuje tabs/<zakładka>.json i dopisuje zakładkę do stanu (tabs).

Dlaczego istnieje: pisarze piszą zakładki niezależnie (w kroku 56 równolegle), każdy z gotowym diagramem, żeby ścieżki,
błędy i przepisy odwoływały się do jego klocków. Schemat odpowiedzi budowany jest osobno dla każdej zakładki
(tab_response_model): zawiera tylko pola potrzebne jej sekcjom, dzięki czemu mieści się w limicie bramki
(schemas.MAX_MODEL_SCHEMA_PROPERTIES); pełny GuideBlock ma 45 pól i do modelu nie idzie. Sekcje ze źródłem scanner
i code wypełnia kod; pisarz dostaje tylko te z nich, które w szablonie mają writer_adds (drzewo, ryzykowne miejsca,
kolejność czytania) - dopisuje do nich wiersze albo zdania.

Rola: agent grafu (faza F); do grafu jako drugi Send (jeden pisarz na zakładkę) dołącza go krok 56.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.agents.writer
        offline, na udawanym modelu: wybór sekcji dla pisarza, liczba pól schematu każdej zakładki szablonu (limit
        bramki), prompt (sekcje, notatki, diagram, pliki robota tylko dla metryczki, fakty kodu tylko dla ryzykownych
        miejsc, wiedza, brak ścieżki dysku), jedno wywołanie dla poprawnej zakładki, ponowienie przy nieistniejącym
        klocku, wpisie bez znaczenia, złej liczbie komórek i braku sekcji, wybór lepszej z dwóch wersji, czyszczenie
        odwołań po ponowieniu, odmowa dla zakładki bez sekcji pisarza, węzeł grafu (tabs/<zakładka>.json, linie
        postępu); na końcu "zgodne z oczekiwaniem: True"
    python -m dev_agents.agents.writer <katalog robota> [id zakładki ...]
        dodatkowo woła PRAWDZIWY model: czyta <katalog robota>/dev_agents_doc/notes/*.json, flow.json i plan.json
        (najpierw pełny przebieg: python main.py --project <katalog robota>), pisze podane zakładki (domyślnie przeglad
        i sciezki), wypisuje je jako JSON z listą problemów, zapisuje tabs/<zakładka>.json w katalogu wyników robota
        i podgląd przewodnika (napisane zakładki, reszta zaślepki) w guide_test.html w katalogu głównym repo.
        Wymaga zmiennych środowiskowych z kluczem i adresem modeli (nazwy w config.yaml).
"""

import json

import pydantic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.runtime import Runtime

import dev_agents.agents.common as _common
import dev_agents.agents.flow_writer as _flow_writer
import dev_agents.context as _context
import dev_agents.guide_content as _content
import dev_agents.guide_facts as _facts
import dev_agents.guide_template as _template
import dev_agents.llm as _llm
import dev_agents.progress as _progress
import dev_agents.prompts as _prompts
import dev_agents.schemas as _schemas
import dev_agents.state as _state

_AGENT_NAME = "writer"

# Pola GuideBlock, które pisarz wypełnia dla sekcji danego typu. Typy bez wpisu (flow, cards, code,
# dependency_graph) pisarz pomija; tree dostaje tylko wiersze (opisy plików), gdy sekcja ma writer_adds.
_FIELDS_BY_TYPE = {
    "text": ["paragraphs"],
    "list": ["items"],
    "steps": ["steps"],
    "table": ["rows"],
    "glossary": ["terms"],
    "io": ["inputs", "outputs"],
    "config": ["paragraphs", "config_items"],
    "paths": ["paths"],
    "recipes": ["recipes"],
    "tree": ["rows"],
}
_TREE_COLUMNS = 3


# --- Sekcje i schemat odpowiedzi ---


def writer_sections(
    tab: _template.TemplateTab,
) -> list[_template.TemplateSection]:
    """Zwraca sekcje zakładki, które pisze model: źródło llm albo writer_adds, o typie z _FIELDS_BY_TYPE; w kolejności szablonu.

    Po co: sekcje ze źródłem scanner i code wypełnia kod, pisarz dostaje tylko te, do których ma coś dodać.
    """
    wynik = []
    for sekcja in tab.sections:
        dla_pisarza = sekcja.source == "llm" or sekcja.writer_adds
        if dla_pisarza and sekcja.type in _FIELDS_BY_TYPE:
            wynik.append(sekcja)
    return wynik


def block_fields(
    sections: list[_template.TemplateSection],
) -> list[str]:
    """Zwraca nazwy pól bloku (GuideBlock) potrzebne podanym sekcjom, bez powtórzeń, w kolejności pierwszego użycia.

    Po co: schemat odpowiedzi zawiera tylko te pola, więc liczba pól zależy od typów sekcji zakładki, a nie od
    wszystkich typów naraz.
    """
    nazwy = []
    for sekcja in sections:
        for nazwa in _FIELDS_BY_TYPE[sekcja.type]:
            if nazwa not in nazwy:
                nazwy.append(nazwa)
    return nazwy


def tab_response_model(
    sections: list[_template.TemplateSection],
) -> type[pydantic.BaseModel]:
    """Buduje klasę odpowiedzi modelu dla zakładki: tab_id i blocks, a blok to section_id i pola z block_fields (wszystkie wymagane).

    Po co: bramka przyjmuje schemat do 48 pól (limit testu 40), a GuideBlock ma ich 45 - zakładka dostaje schemat tylko
    z polami swoich sekcji, z tymi samymi opisami co w GuideBlock. Odpowiedź zamienia convert_tab na GuideTab.
    """
    pola = {"section_id": (str, pydantic.Field(description="Id sekcji z listy sekcji, dokładnie jak podano."))}
    for nazwa in block_fields(sections):
        informacja = _content.GuideBlock.model_fields[nazwa]
        pola[nazwa] = (informacja.annotation, pydantic.Field(description=informacja.description))
    klasa_bloku = pydantic.create_model("WriterBlock", **pola)
    klasa_zakladki = pydantic.create_model(
        "WriterTab",
        tab_id=(str, pydantic.Field(description="Id zakładki, dokładnie jak w zadaniu.")),
        blocks=(list[klasa_bloku], pydantic.Field(description="Bloki sekcji zakładki: po jednym na sekcję, w kolejności z listy sekcji.")),
    )
    return klasa_zakladki


def convert_tab(
    answer: pydantic.BaseModel,
    tab_id: str,
) -> _content.GuideTab:
    """Zamienia odpowiedź modelu (klasa z tab_response_model) na GuideTab z podanym tab_id; pola, których schemat nie miał, są puste.

    Po co: reszta towaru (renderer, składanie treści) zna tylko GuideTab i GuideBlock; id zakładki bierzemy z kodu,
    nie z odpowiedzi modelu.
    """
    bloki = []
    for blok in answer.blocks:
        bloki.append(_content.GuideBlock.model_validate(blok.model_dump()))
    zakladka = _content.GuideTab(tab_id=tab_id, blocks=bloki)
    return zakladka


# --- Dane dla promptu ---


def describe_sections(
    sections: list[_template.TemplateSection],
) -> str:
    """Zwraca opis sekcji do promptu: id, tytuł, typ, wymagana, pole odpowiedzi, kolumny i polecenie; sekcje writer_adds z dopiskiem „dopisujesz”.

    Po co: pisarz widzi dokładnie, co ma napisać w każdej sekcji i w którym polu bloku to zwrócić.
    """
    bloki = []
    for sekcja in sections:
        wymagana = "nie"
        if sekcja.required:
            wymagana = "tak"
        linie = [f"- id: {sekcja.id}", f"  tytuł: {sekcja.title}", f"  typ: {sekcja.type}", f"  wymagana: {wymagana}"]
        linie.append(f"  pola odpowiedzi: {', '.join(_FIELDS_BY_TYPE[sekcja.type])}")
        if sekcja.writer_adds:
            linie.append("  dopisujesz: kod ma własne dane tej sekcji, Ty dodajesz tylko to, co mówi polecenie")
        if sekcja.columns:
            linie.append(f"  kolumny: {' | '.join(sekcja.columns)}")
        linie.append(f"  polecenie: {sekcja.instruction.strip()}")
        bloki.append("\n".join(linie))
    tekst = "\n\n".join(bloki)
    return tekst


def format_notes(
    notes: list[_schemas.ModuleNote],
) -> str:
    """Zwraca notatki jako tekst do promptu: każda w znaczniku <notatka jednostka="...">, w treści pełny JSON notatki.

    Po co: pisarz potrzebuje wszystkich pól (ustawienia, wymagania, ryzyka, awarie, rozszerzenia, konwencje, kandydaci
    do słowniczka) - nie tylko pól przebiegu jak autor diagramu. JSON bez zamiany polskich znaków na kody.
    """
    bloki = []
    for notatka in notes:
        tresc = json.dumps(notatka.model_dump(), ensure_ascii=False, indent=1)
        bloki.append(f'<notatka jednostka="{notatka.unit_name}">\n{tresc}\n</notatka>')
    tekst = "\n\n".join(bloki)
    return tekst


def format_flow(
    flow: _content.FlowGraph,
) -> str:
    """Zwraca diagram jako zwarty tekst: klocki "id | rodzaj | napis | moduł | funkcje" i strzałki "źródło -> cel [rodzaj] etykieta".

    Po co: pisarz odwołuje się do klocków po id, więc potrzebuje ich listy i kolejności, a nie pełnego JSON-a
    (reads i writes klocków są w notatkach).
    """
    linie = ["Klocki:"]
    for klocek in flow.nodes:
        funkcje = ", ".join(klocek.functions)
        linie.append(f"{klocek.id} | {klocek.kind} | {klocek.label} | {klocek.module} | {funkcje}")
    linie.append("Strzałki:")
    for strzalka in flow.edges:
        linie.append(f"{strzalka.source} -> {strzalka.target} [{strzalka.kind}] {strzalka.label}".rstrip())
    tekst = "\n".join(linie)
    return tekst


def format_text_files(
    project_map: _schemas.ProjectMap,
) -> str:
    """Zwraca pliki robota przepisane dosłownie (zależności, konfiguracja, uruchamiające) w znacznikach <plik sciezka="..." rola="...">, z numerami linii.

    Po co: pisarz metryczki i instalacji widzi pliki dokładnie takie, jakie są; numery linii pozwalają wskazać
    miejsce (używa ich też analityk). Pusty tekst, gdy robot nie ma takich plików.
    """
    bloki = []
    for plik in project_map.text_files:
        numerowany = _common.number_lines(plik.text)
        bloki.append(f'<plik sciezka="{plik.path}" rola="{plik.role}">\n{numerowany}\n</plik>')
    tekst = "\n\n".join(bloki)
    return tekst


def format_risky_facts(
    project_map: _schemas.ProjectMap,
    long_unit_lines: int,
) -> str:
    """Zwraca fakty kodu o długich jednostkach jako linie "Miejsce | Plik i linie | Rodzaj" (bez haseł - te dopisuje kod z metryczki); pusty tekst, gdy nie ma długich.

    Po co: pisarz ryzykownych miejsc dopisuje komentarz do miejsc, które kod już wskazał, powtarzając dwie pierwsze komórki.
    """
    wiersze, _ = _facts.risky_rows(project_map, [], long_unit_lines, [])
    linie = []
    for wiersz in wiersze:
        linie.append(f"{wiersz['place']} | {wiersz['where']} | {wiersz['badge']} ({wiersz['detail']})")
    tekst = "\n".join(linie)
    return tekst


def build_writer_variables(
    tab: _template.TemplateTab,
    sections: list[_template.TemplateSection],
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    notes: list[_schemas.ModuleNote],
    flow: _content.FlowGraph,
    knowledge_text: str,
    long_unit_lines: int,
    previous_tab: _content.GuideTab | None,
    problems: list[str],
) -> dict:
    """Zwraca zmienne do szablonu prompts/writer/user.md; pliki robota tylko dla zakładki z sekcją config, fakty kodu tylko dla zakładki z tabelą writer_adds, poprawka przy ponowieniu.

    Po co: w jednym miejscu widać, co dokładnie pisarz dostaje. Argumenty: sections - wynik writer_sections,
    knowledge_text - gotowy tekst wiedzy, long_unit_lines - próg długiej jednostki z config.analysis, previous_tab
    i problems - poprzednia wersja zakładki i lista problemów albo None i pusta lista przy pierwszym wywołaniu.
    """
    typy = []
    tabele_pisarza = False
    for sekcja in sections:
        typy.append(sekcja.type)
        if sekcja.writer_adds and sekcja.type == "table":
            tabele_pisarza = True
    pliki_robota = ""
    if "config" in typy:
        pliki_robota = format_text_files(project_map)
    fakty_kodu = ""
    if tabele_pisarza:
        fakty_kodu = format_risky_facts(project_map, long_unit_lines)
    poprzedni_tekst = ""
    if previous_tab is not None:
        poprzedni_tekst = previous_tab.model_dump_json(indent=1, exclude_defaults=True)
    linie_problemow = []
    for problem in problems:
        linie_problemow.append(f"- {problem}")
    zmienne = {
        "project_name": project_map.project_name,
        "tab_id": tab.id,
        "tab_title": tab.title,
        "tab_lead": tab.lead.strip(),
        "plan_summary": plan.summary,
        "sections": describe_sections(sections),
        "project_context": _flow_writer.build_project_context(project_map),
        "notes": format_notes(notes),
        "flow": format_flow(flow),
        "text_files": pliki_robota,
        "risky_facts": fakty_kodu,
        "knowledge": knowledge_text,
        "previous_tab": poprzedni_tekst,
        "problems_text": "\n".join(linie_problemow),
    }
    return zmienne


# --- Sprawdzanie i poprawianie ---


def normalize_blocks(
    tab: _content.GuideTab,
    sections: list[_template.TemplateSection],
) -> tuple[_content.GuideTab, list[str]]:
    """Zwraca (zakładka z blokami tylko znanych sekcji, bez powtórzeń, w kolejności szablonu; uwagi o usuniętych blokach).

    Po co: model może zwrócić blok z nieznanym id, powtórzony albo w innej kolejności; renderer szuka bloków po id,
    a uwagi trafiają na listę problemów (nic nie znika po cichu).
    """
    wedlug_id = {}
    uwagi = []
    for blok in tab.blocks:
        znana = False
        for sekcja in sections:
            if sekcja.id == blok.section_id:
                znana = True
        if znana and blok.section_id not in wedlug_id:
            wedlug_id[blok.section_id] = blok
        else:
            uwagi.append(f"usunięto blok '{blok.section_id}': nieznana albo powtórzona sekcja")
    uporzadkowane = []
    for sekcja in sections:
        if sekcja.id in wedlug_id:
            uporzadkowane.append(wedlug_id[sekcja.id])
    zakladka = _content.GuideTab(tab_id=tab.tab_id, blocks=uporzadkowane)
    wynik = (zakladka, uwagi)
    return wynik


def _check_block(
    block: _content.GuideBlock,
    section: _template.TemplateSection,
    node_ids: list[str],
) -> list[str]:
    """Zwraca problemy jednego bloku: liczba komórek wierszy, wpisy metryczki bez klucza albo znaczenia, ścieżki (brak głównej, puste, nieistniejący klocek).

    Po co: to, co da się sprawdzić kodem, sprawdza kod - model dostaje listę przy ponowieniu.
    """
    problemy = []
    oczekiwane_komorki = len(section.columns)
    if section.type == "tree":
        oczekiwane_komorki = _TREE_COLUMNS
    if oczekiwane_komorki:
        for numer, wiersz in enumerate(block.rows, start=1):
            if len(wiersz) != oczekiwane_komorki:
                problemy.append(f"sekcja '{section.id}': wiersz {numer} ma {len(wiersz)} komórek, a ma mieć {oczekiwane_komorki}")
    for wpis in block.config_items:
        if not wpis.key.strip():
            problemy.append(f"sekcja '{section.id}': wpis metryczki bez klucza (wartość '{wpis.value}')")
        elif not wpis.meaning.strip():
            problemy.append(f"sekcja '{section.id}': wpis metryczki '{wpis.key}' bez znaczenia (meaning)")
    if section.type == "paths":
        rodzaje = []
        for sciezka in block.paths:
            rodzaje.append(sciezka.kind)
            if not sciezka.steps:
                problemy.append(f"sekcja '{section.id}': ścieżka '{sciezka.name}' bez kroków")
            for numer, krok in enumerate(sciezka.steps, start=1):
                if krok.node_id and krok.node_id not in node_ids:
                    problemy.append(f"sekcja '{section.id}': ścieżka '{sciezka.name}', krok {numer} odwołuje się do nieistniejącego klocka '{krok.node_id}'")
        if block.paths and "main" not in rodzaje:
            problemy.append(f"sekcja '{section.id}': brak ścieżki głównej (kind main)")
    return problemy


def check_tab(
    tab: _content.GuideTab,
    sections: list[_template.TemplateSection],
    flow: _content.FlowGraph,
) -> list[str]:
    """Zwraca problemy zakładki: brak bloku wymaganej sekcji pisarza (źródło llm) i problemy bloków (_check_block).

    Po co: sprawdzenie zwykłym kodem - lista problemów steruje ponowieniem i trafia do uwag w linii postępu.
    Zakładka powinna być już po normalize_blocks (tylko znane sekcje).
    """
    id_klockow = []
    for klocek in flow.nodes:
        id_klockow.append(klocek.id)
    bloki = {}
    for blok in tab.blocks:
        bloki[blok.section_id] = blok
    problemy = []
    for sekcja in sections:
        if sekcja.id not in bloki:
            if sekcja.source == "llm" and sekcja.required:
                problemy.append(f"brak bloku wymaganej sekcji '{sekcja.id}'")
        else:
            problemy.extend(_check_block(bloki[sekcja.id], sekcja, id_klockow))
    return problemy


def clear_missing_nodes(
    tab: _content.GuideTab,
    flow: _content.FlowGraph,
) -> _content.GuideTab:
    """Zwraca zakładkę, w której odwołania kroków ścieżek do nieistniejących klocków mają puste node_id (reszta bez zmian).

    Po co: ostatnia deska ratunku po ponowieniu - krok bez klocka jest poprawny (renderer nie robi z niego odnośnika),
    a odwołanie donikąd nie. Problem zostaje w wyniku write_tab, więc nie jest ukryty.
    """
    id_klockow = []
    for klocek in flow.nodes:
        id_klockow.append(klocek.id)
    kopia = tab.model_copy(deep=True)
    for blok in kopia.blocks:
        for sciezka in blok.paths:
            for krok in sciezka.steps:
                if krok.node_id and krok.node_id not in id_klockow:
                    krok.node_id = ""
    return kopia


# --- Wywołanie modelu ---


def _ask_model(
    context: _context.RunContext,
    response_model: type[pydantic.BaseModel],
    variables: dict,
) -> pydantic.BaseModel:
    """Składa prompt z podanych zmiennych, woła model agenta writer ze schematem zakładki i zwraca odpowiedź w klasie response_model.

    Po co: jedno wywołanie modelu - pierwsze i ponowione różnią się tylko zmiennymi. Brak odpowiedzi zgodnej ze
    schematem kończy się RuntimeError z przyczyną (llm.invoke_structured).
    """
    tekst_system, tekst_user = _prompts.render_prompt(context.config.paths.prompts, _AGENT_NAME, variables)
    odpowiedz = _llm.invoke_structured(
        context.models[_AGENT_NAME],
        response_model,
        _llm.get_structured_output_method(context.config, _AGENT_NAME),
        [SystemMessage(content=tekst_system), HumanMessage(content=tekst_user)],
    )
    return odpowiedz


def _finish(
    answer: pydantic.BaseModel,
    tab_id: str,
    sections: list[_template.TemplateSection],
    flow: _content.FlowGraph,
) -> tuple[_content.GuideTab, list[str]]:
    """Zamienia odpowiedź modelu na uporządkowaną GuideTab i zwraca (zakładka, problemy: uwagi o usuniętych blokach i wyniki check_tab).

    Po co: jedno miejsce obróbki pierwszej i ponowionej wersji.
    """
    zakladka = convert_tab(answer, tab_id)
    zakladka, uwagi = normalize_blocks(zakladka, sections)
    problemy = uwagi + check_tab(zakladka, sections, flow)
    wynik = (zakladka, problemy)
    return wynik


def write_tab(
    tab: _template.TemplateTab,
    project_map: _schemas.ProjectMap,
    plan: _schemas.Plan,
    notes: list[_schemas.ModuleNote],
    flow: _content.FlowGraph,
    context: _context.RunContext,
) -> tuple[_content.GuideTab, list[str], int]:
    """Pisze zakładkę: zwraca (zakładka, problemy, liczba wywołań modelu - 1 albo 2).

    Po co: cała logika pisarza w jednej funkcji, z której korzystają węzeł grafu i test ręczny. Pierwsza wersja z promptu
    z notatkami w kolejności czytania i diagramem; gdy kod zgłosi problemy, model dostaje jedno ponowienie z poprzednią
    wersją i listą problemów. Druga wersja wygrywa, chyba że ma więcej problemów niż pierwsza. Zwrócone problemy dotyczą
    wybranej wersji (niepuste znaczą, że zakładka ma braki - decyduje o tym wołający); odwołania do nieistniejących
    klocków są w zwróconej zakładce wyczyszczone.

    Uwaga: zakładka bez sekcji dla pisarza (np. sam diagram) albo brak notatek to ValueError. Argument tab to zakładka
    z szablonu po filtrze technologii (guide_template.sections_for_technology).
    """
    sekcje = writer_sections(tab)
    if not sekcje:
        komunikat_bledu = f"Zakładka '{tab.id}' nie ma sekcji do napisania przez pisarza"
        raise ValueError(komunikat_bledu)
    if not notes:
        komunikat_bledu = "Brak notatek analityków - nie ma z czego pisać zakładki"
        raise ValueError(komunikat_bledu)
    uporzadkowane = _flow_writer.order_notes(notes, plan)
    pliki_wiedzy = _common.collect_knowledge_files(context.config, project_map, plan.writer_knowledge)
    tekst_wiedzy = _common.format_knowledge(context.config, pliki_wiedzy)
    prog = context.config.analysis.long_unit_lines
    klasa_odpowiedzi = tab_response_model(sekcje)
    zmienne = build_writer_variables(tab, sekcje, project_map, plan, uporzadkowane, flow, tekst_wiedzy, prog, None, [])
    odpowiedz = _ask_model(context, klasa_odpowiedzi, zmienne)
    zakladka, problemy = _finish(odpowiedz, tab.id, sekcje, flow)
    wywolania = 1
    if problemy:
        zmienne_poprawki = build_writer_variables(tab, sekcje, project_map, plan, uporzadkowane, flow, tekst_wiedzy, prog, zakladka, problemy)
        druga_odpowiedz = _ask_model(context, klasa_odpowiedzi, zmienne_poprawki)
        wywolania = 2
        druga_zakladka, problemy_2 = _finish(druga_odpowiedz, tab.id, sekcje, flow)
        if len(problemy_2) <= len(problemy):
            zakladka = druga_zakladka
            problemy = problemy_2
    zakladka = clear_missing_nodes(zakladka, flow)
    wynik = (zakladka, problemy, wywolania)
    return wynik


# --- Węzeł grafu ---


def writer_node(
    state: _state.RunState,
    runtime: Runtime[_context.RunContext],
) -> dict:
    """Węzeł writer: pisze zakładkę o id ze stanu (tab_id), zapisuje tabs/<tab_id>.json i zwraca zmienione pole stanu: tabs z jedną zakładką.

    Po co: etap pisarzy - po jednym węźle na zakładkę (krok 56 uruchomi je równolegle przez Send z tab_id). Praca jest
    owinięta w Stage "writer <tab_id>": start, uwagi o problemach zakładki, koniec z czasem, liczbą bloków i wywołań
    modelu. Zakładka z problemami nie przerywa przebiegu - kompletność sprawdzi składanie treści (krok 56).
    """
    kontekst = runtime.context
    tab_id = state["tab_id"]
    szablon_technologii = _template.sections_for_technology(kontekst.template, state["project_map"].technology)
    szablon_zakladki = None
    for zakladka_szablonu in szablon_technologii.tabs:
        if zakladka_szablonu.id == tab_id:
            szablon_zakladki = zakladka_szablonu
    if szablon_zakladki is None:
        komunikat_bledu = f"Zakładka '{tab_id}' nie istnieje w szablonie przewodnika"
        raise ValueError(komunikat_bledu)
    with _progress.Stage(kontekst.report, f"{_AGENT_NAME} {tab_id}") as etap:
        zakladka, problemy, wywolania = write_tab(szablon_zakladki, state["project_map"], state["plan"], state["notes"], state["flow"], kontekst)
        for problem in problemy:
            etap.note(f"problem: {problem}")
        zapisany_plik = kontekst.store.save_json(f"tabs/{tab_id}.json", zakladka)
        etap.set_result(f"bloków: {len(zakladka.blocks)}, problemów: {len(problemy)}, wywołań modelu: {wywolania}, zapisano {zapisany_plik}")
    zmiana_stanu = {"tabs": [zakladka]}
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
    import dev_agents.guide_placeholders as _placeholders
    import dev_agents.output as _output
    import dev_agents.render as _render
    import dev_agents.scanner as _scanner

    def _note(
        unit_name: str,
        purpose: str,
    ) -> _schemas.ModuleNote:
        """Zwraca notatkę z ustawieniem, ryzykiem i awarią - pola, które pisarz ma dostać (w przeciwieństwie do autora diagramu).

        Po co: test sprawdza, że pisarz widzi pełną notatkę, także ustawienia i ryzyka.
        """
        notatka = _schemas.ModuleNote.model_validate(
            {
                "unit_name": unit_name,
                "purpose": purpose,
                "flow_role": "Główna jednostka.",
                "automated_application": "",
                "key_functions": [],
                "actions": [],
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

    def _flow_graph() -> _content.FlowGraph:
        """Zwraca diagram z klockami s0 (start), n0 i n1 (kroki) i k (koniec) - id, do których odwołują się ścieżki w teście.

        Po co: pisarz dostaje gotowy diagram, a test sprawdza odwołania do jego klocków.
        """
        klocki = [
            _content.FlowNode(id="s0", kind="start", label="Start"),
            _content.FlowNode(id="n0", kind="step", label="Wczytaj pliki", module="main.py", functions=["run:5"]),
            _content.FlowNode(id="n1", kind="step", label="Zapisz wyniki", module="main.py", functions=["run:50"]),
            _content.FlowNode(id="k", kind="end", label="Koniec"),
        ]
        strzalki = [
            _content.FlowEdge(source="s0", target="n0"),
            _content.FlowEdge(source="n0", target="n1"),
            _content.FlowEdge(source="n1", target="k"),
        ]
        diagram = _content.FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    def _map(
        root: str,
    ) -> _schemas.ProjectMap:
        """Zwraca mapę projektu z plikiem konfiguracyjnym, jedną długą jednostką i kontekstem; root tylko po to, by sprawdzić, że nie trafia do promptu.

        Po co: pisarz czyta z mapy pliki robota, fakty o długich jednostkach i kontekst projektu.
        """
        dluga = _schemas.SourceUnit(name="dluga_funkcja", start_line=10, end_line=400)
        mapa = _schemas.ProjectMap(
            project_name="robot_testowy",
            root=root,
            technology="python",
            entrypoints=["main.py"],
            files=[],
            code_units=[],
            text_files=[_schemas.TextFile(path="config.yaml", role="config", text="PLIK_KONFIG_TEKST: 1\n")],
            source_files=[_schemas.SourceFile(path="main.py", units=[dluga])],
            reading_order=["main.py"],
            dependency_edges=[],
        )
        return mapa

    def _blank_block(
        sections: list[_template.TemplateSection],
        section_id: str,
        **values,
    ) -> dict:
        """Zwraca słownik bloku odpowiedzi: section_id, wszystkie pola schematu puste (listy) i podane wartości.

        Po co: pola odpowiedzi modelu są wymagane, więc odpowiedź udawanego modelu musi mieć je wszystkie.
        """
        blok = {"section_id": section_id}
        for nazwa in block_fields(sections):
            blok[nazwa] = []
        for nazwa, wartosc in values.items():
            blok[nazwa] = wartosc
        return blok

    def _answer(
        tab: _template.TemplateTab,
        tab_id: str,
        blocks: list[dict],
    ) -> pydantic.BaseModel:
        """Zwraca odpowiedź w klasie schematu zakładki (tab_response_model) z podanym tab_id i blokami.

        Po co: udawany model odpowiada obiektem takiej samej klasy, jakiej używa agent.
        """
        klasa = tab_response_model(writer_sections(tab))
        odpowiedz = klasa.model_validate({"tab_id": tab_id, "blocks": blocks})
        return odpowiedz

    def _model(
        answers: list,
        seen_prompts: list[str],
    ) -> _fakes.FakeStructuredModel:
        """Zwraca udawany model, który kolejnymi wywołaniami odpowiada kolejnymi odpowiedziami z listy i zapamiętuje prompty użytkownika.

        Po co: test steruje tym, co model odpowie przy pierwszym i ponowionym wywołaniu.
        """

        def answer(
            messages,
        ):
            """Zapamiętuje prompt użytkownika i zwraca odpowiedź o numerze równym liczbie dotychczasowych promptów (ostatnia powtarza się).

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
        """Zwraca uproszczony kontekst (config, model writer, szablon, report, magazyn) - tyle, ile czytają write_tab i węzeł.

        Po co: test offline nie buduje prawdziwych modeli wszystkich agentów i nie wymaga kluczy.
        """
        kontekst = types.SimpleNamespace(config=app_config, models={_AGENT_NAME: model}, template=template, report=report, store=store)
        return kontekst

    def _find_tab(
        template: _template.GuideTemplate,
        tab_id: str,
    ) -> _template.TemplateTab:
        """Zwraca zakładkę szablonu o podanym id.

        Po co: test pracuje na prawdziwym szablonie z configu.
        """
        wynik = None
        for zakladka in template.tabs:
            if zakladka.id == tab_id:
                wynik = zakladka
        return wynik

    def _good_paths(
        tab: _template.TemplateTab,
        node_id: str,
    ) -> pydantic.BaseModel:
        """Zwraca poprawną odpowiedź dla zakładki Ścieżki procesu: ścieżka główna z dwoma krokami, pierwszy odwołuje się do klocka node_id.

        Po co: wspólny wzorzec odpowiedzi w testach ponowienia.
        """
        sekcje = writer_sections(tab)
        sciezka = {
            "name": "Główna",
            "kind": "main",
            "steps": [{"text": "Wczytanie plików.", "node_id": node_id}, {"text": "Zapis.", "node_id": "n1"}],
        }
        blok = _blank_block(sekcje, "sciezki", paths=[sciezka])
        odpowiedz = _answer(tab, tab.id, [blok])
        return odpowiedz

    def _offline_checks(
        app_config: _config.AppConfig,
        temp_dir: str,
    ) -> list[tuple[str, bool]]:
        """Sprawdza pisarza na udawanym modelu; zwraca (opis, zgodne).

        Po co: wybór sekcji, schematy, prompt, ponowienia, czyszczenie odwołań i węzeł grafu bez sieci i kosztu.
        """
        szablon = _template.load_template(app_config.paths.guide_template)
        mapa = _map(os.path.join(temp_dir, "ukryty_katalog_uzytkownika"))
        plan = _schemas.Plan(summary="Plan testowy.", tasks=[_schemas.AnalysisTask(unit="main.py")], writer_knowledge=["guide_goals.md"])
        notatki = [_note("main.py", "CEL_GLOWNEJ")]
        diagram = _flow_graph()
        magazyn = _output.RunStore(os.path.join(temp_dir, "wyniki"))
        przeglad = _find_tab(szablon, "przeglad")
        sciezki = _find_tab(szablon, "sciezki")
        bledy = _find_tab(szablon, "bledy")
        wyniki = []

        for zakladka, oczekiwane in (
            (przeglad, ["opis_robota", "metryczka", "wejscie_wyjscie", "wymagania", "instalacja", "jak_sprawdzic", "pojecia"]),
            (bledy, ["awarie", "ryzykowne_miejsca", "ograniczenia"]),
            (_find_tab(szablon, "struktura"), ["drzewo"]),
            (_find_tab(szablon, "przeplyw"), []),
        ):
            identyfikatory = []
            for sekcja in writer_sections(zakladka):
                identyfikatory.append(sekcja.id)
            wyniki.append((f"sekcje pisarza zakładki {zakladka.id}: {identyfikatory}", identyfikatory == oczekiwane))

        najwiecej = 0
        for zakladka in szablon.tabs:
            sekcje = writer_sections(zakladka)
            if sekcje:
                liczba = _schemas.count_schema_properties(tab_response_model(sekcje))
                najwiecej = max(najwiecej, liczba)
                print(f"  pola schematu zakładki {zakladka.id}: {liczba}")
        wyniki.append((f"schemat każdej zakładki ma najwyżej {_schemas.MAX_MODEL_SCHEMA_PROPERTIES} pól (największy: {najwiecej})", najwiecej <= _schemas.MAX_MODEL_SCHEMA_PROPERTIES))
        polaprzeglad = block_fields(writer_sections(przeglad))
        wyniki.append(("pola bloku zakładki przeglad: są config_items i terms, nie ma paths", "config_items" in polaprzeglad and "terms" in polaprzeglad and "paths" not in polaprzeglad))

        prompty = []
        model = _model([_good_paths(sciezki, "n0")], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(sciezki, mapa, plan, notatki, diagram, kontekst)
        pierwszy = prompty[0]
        wyniki.append(("poprawna zakładka ścieżek: jedno wywołanie, bez problemów", model.calls == 1 and wywolania == 1 and problemy == []))
        wyniki.append(("zakładka: tab_id z szablonu, jeden blok sciezki z odwołaniem n0", zakladka_wynik.tab_id == "sciezki" and zakladka_wynik.blocks[0].paths[0].steps[0].node_id == "n0"))
        wyniki.append(("prompt: sekcja, jej polecenie i pole odpowiedzi", "id: sciezki" in pierwszy and "pola odpowiedzi: paths" in pierwszy and "odwołujących się do klocków diagramu" in pierwszy))
        wyniki.append(("prompt: pełna notatka (ustawienia i ryzyka też)", "CEL_GLOWNEJ" in pierwszy and "WIDOCZNE_USTAWIENIE" in pierwszy and "WIDOCZNE_RYZYKO" in pierwszy))
        wyniki.append(("prompt: diagram z id klocków i strzałkami", "n0 | step | Wczytaj pliki | main.py | run:5" in pierwszy and "n0 -> n1 [normal]" in pierwszy))
        wyniki.append(("prompt: bez plików robota i faktów kodu (zakładka bez metryczki i ryzyk)", "<pliki_robota>" not in pierwszy and "<fakty_kodu>" not in pierwszy))
        wyniki.append(("prompt: wiedza dla pisarzy, bez ścieżki dysku i bez poprawki", "Jak piszemy przewodnik" in pierwszy and "ukryty_katalog_uzytkownika" not in pierwszy and "<poprawka>" not in pierwszy))

        prompty = []
        model = _model([_answer(przeglad, "przeglad", [_blank_block(writer_sections(przeglad), "opis_robota", paragraphs=["Opis."])])], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        write_tab(przeglad, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("prompt zakładki z metryczką: pliki robota z numerami linii", "<pliki_robota>" in prompty[0] and "PLIK_KONFIG_TEKST: 1" in prompty[0] and '<plik sciezka="config.yaml" rola="config">' in prompty[0]))

        prompty = []
        model = _model([_answer(bledy, "bledy", [_blank_block(writer_sections(bledy), "awarie")])], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        write_tab(bledy, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("prompt zakładki z ryzykownymi miejscami: fakty kodu o długiej jednostce", "<fakty_kodu>" in prompty[0] and "dluga_funkcja | main.py:10-400" in prompty[0]))
        wyniki.append(("prompt ryzykownych miejsc: sekcja z dopiskiem dopisujesz", "dopisujesz" in prompty[0]))

        prompty = []
        model = _model([_good_paths(sciezki, "n99"), _good_paths(sciezki, "n0")], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(sciezki, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("nieistniejący klocek: ponowienie, druga wersja poprawna", model.calls == 2 and wywolania == 2 and problemy == [] and zakladka_wynik.blocks[0].paths[0].steps[0].node_id == "n0"))
        wyniki.append(("ponowienie: prompt z poprzednią wersją i listą problemów", "<poprawka>" in prompty[1] and "n99" in prompty[1] and "nieistniejącego klocka" in prompty[1]))

        prompty = []
        model = _model([_good_paths(sciezki, "n99")], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(sciezki, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("odwołanie złe także po ponowieniu: wyczyszczone w zakładce, problem w wyniku", wywolania == 2 and len(problemy) == 1 and zakladka_wynik.blocks[0].paths[0].steps[0].node_id == ""))

        sekcje_przegladu = writer_sections(przeglad)
        bez_znaczenia = {"file": "config.yaml", "location": "", "group": "", "key": "klucz", "value": "x", "kind": "other", "plain_password": False, "meaning": "", "used_in": [], "certain": True}
        z_znaczeniem = dict(bez_znaczenia)
        z_znaczeniem["meaning"] = "Znaczenie."
        poczatek = _blank_block(sekcje_przegladu, "opis_robota", paragraphs=["Opis."])
        wejscie = _blank_block(sekcje_przegladu, "wejscie_wyjscie")
        wymagania = _blank_block(sekcje_przegladu, "wymagania", rows=[["Python", "3.12"]])
        instalacja = _blank_block(sekcje_przegladu, "instalacja")
        sprawdzenie = _blank_block(sekcje_przegladu, "jak_sprawdzic")
        zle = _answer(przeglad, "zly_id", [poczatek, _blank_block(sekcje_przegladu, "metryczka", config_items=[bez_znaczenia]), wejscie, wymagania, instalacja, sprawdzenie])
        dobre = _answer(
            przeglad,
            "przeglad",
            [poczatek, _blank_block(sekcje_przegladu, "metryczka", config_items=[z_znaczeniem]), wejscie, _blank_block(sekcje_przegladu, "wymagania", rows=[["Python", "3.12", "PATH"]]), instalacja, sprawdzenie],
        )
        prompty = []
        model = _model([zle, dobre], prompty)
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(przeglad, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("metryczka bez znaczenia i wiersz o złej liczbie komórek: ponowienie, poprawna wersja bez problemów", wywolania == 2 and problemy == [] and zakladka_wynik.tab_id == "przeglad"))
        wyniki.append(("ponowienie: lista problemów w prompcie (znaczenie, komórki)", "bez znaczenia (meaning)" in prompty[1] and "ma 2 komórek, a ma mieć 3" in prompty[1]))

        zle_id = _answer(
            przeglad,
            "przeglad",
            [poczatek, _blank_block(sekcje_przegladu, "metryczka", config_items=[z_znaczeniem]), _blank_block(sekcje_przegladu, "metryczka"), _blank_block(sekcje_przegladu, "obca_sekcja"), wejscie, _blank_block(sekcje_przegladu, "wymagania", rows=[["a", "b", "c"]]), instalacja, sprawdzenie],
        )
        model = _model([zle_id], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(przeglad, mapa, plan, notatki, diagram, kontekst)
        identyfikatory = []
        for blok in zakladka_wynik.blocks:
            identyfikatory.append(blok.section_id)
        wyniki.append(("blok powtórzony i obcy: usunięte, kolejność szablonu, uwagi na liście problemów", identyfikatory == ["opis_robota", "metryczka", "wejscie_wyjscie", "wymagania", "instalacja", "jak_sprawdzic"] and len(problemy) == 2))

        brak_wymaganej = _answer(przeglad, "przeglad", [poczatek])
        model = _model([brak_wymaganej], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(przeglad, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("brak wymaganych sekcji: w problemach, pisarz nie przerywa", len(problemy) == 5 and "metryczka" in problemy[0]))

        gorsza = _answer(przeglad, "przeglad", [poczatek, _blank_block(sekcje_przegladu, "metryczka", config_items=[z_znaczeniem])])
        model = _model([_answer(przeglad, "przeglad", [poczatek, _blank_block(sekcje_przegladu, "metryczka", config_items=[z_znaczeniem]), wejscie, wymagania, instalacja, sprawdzenie]), gorsza], [])
        kontekst = _context_for(app_config, szablon, model, [].append, magazyn)
        zakladka_wynik, problemy, wywolania = write_tab(przeglad, mapa, plan, notatki, diagram, kontekst)
        wyniki.append(("druga wersja gorsza (więcej braków): zostaje pierwsza", wywolania == 2 and len(zakladka_wynik.blocks) == 6 and len(problemy) == 1))

        blad = ""
        try:
            write_tab(_find_tab(szablon, "przeplyw"), mapa, plan, notatki, diagram, kontekst)
        except ValueError as wyjatek:
            blad = str(wyjatek)
        wyniki.append(("zakładka bez sekcji pisarza (diagram): ValueError", "nie ma sekcji" in blad))
        blad = ""
        try:
            write_tab(sciezki, mapa, plan, [], diagram, kontekst)
        except ValueError as wyjatek:
            blad = str(wyjatek)
        wyniki.append(("brak notatek: ValueError", "Brak notatek" in blad))

        linie = []
        model = _model([_good_paths(sciezki, "n0")], [])
        kontekst = _context_for(app_config, szablon, model, linie.append, magazyn)
        stan = {"project_map": mapa, "plan": plan, "notes": notatki, "flow": diagram, "tab_id": "sciezki"}
        zmiana = writer_node(stan, types.SimpleNamespace(context=kontekst))
        zapisana = magazyn.load_json("tabs/sciezki.json", _content.GuideTab)
        wyniki.append(("węzeł: zwraca tabs z jedną zakładką i zapisuje tabs/sciezki.json", list(zmiana) == ["tabs"] and len(zmiana["tabs"]) == 1 and zapisana == zmiana["tabs"][0]))
        wyniki.append(("węzeł: linie postępu start i koniec z nazwą zakładki", len(linie) == 2 and linie[0].endswith("] writer sciezki: start") and "bloków: 1, problemów: 0, wywołań modelu: 1" in linie[1]))

        linie = []
        model = _model([_good_paths(sciezki, "n99")], [])
        kontekst = _context_for(app_config, szablon, model, linie.append, magazyn)
        writer_node(stan, types.SimpleNamespace(context=kontekst))
        wyniki.append(("węzeł: problem zakładki jako uwaga, przebieg się nie przerywa", len(linie) == 3 and "] writer sciezki: problem: " in linie[1]))

        blad = ""
        try:
            writer_node({"project_map": mapa, "plan": plan, "notes": notatki, "flow": diagram, "tab_id": "nie_ma"}, types.SimpleNamespace(context=kontekst))
        except ValueError as wyjatek:
            blad = str(wyjatek)
        wyniki.append(("węzeł: nieznana zakładka: ValueError", "nie istnieje w szablonie" in blad))
        return wyniki

    def _real_model_run(
        project_dir: str,
        tab_ids: list[str],
        app_config: _config.AppConfig,
    ) -> None:
        """Czyta notatki, diagram i plan robota z dev_agents_doc, woła prawdziwy model pisarza dla podanych zakładek, wypisuje wynik, zapisuje tabs/<zakładka>.json i podgląd HTML.

        Po co: sprawdzenie pisarza na prawdziwych notatkach i diagramie, bez ponownej analizy kodu. Robota nie zmienia
        poza katalogiem wyników; podgląd idzie do guide_test.html w katalogu głównym repo.
        """
        project_map = _scanner.build_project_map(project_dir, app_config.scan)
        katalog_wynikow = os.path.join(project_dir, _output.OUTPUT_DIR_NAME)
        pliki_notatek = sorted(glob.glob(os.path.join(katalog_wynikow, "notes", "**", "*.json"), recursive=True))
        sciezka_diagramu = os.path.join(katalog_wynikow, "flow.json")
        if not pliki_notatek or not os.path.isfile(sciezka_diagramu):
            sys.exit(f"BŁĄD: brak notatek albo flow.json w {katalog_wynikow} - najpierw pełny przebieg: python main.py --project {project_dir}")
        notatki = []
        for plik_notatki in pliki_notatek:
            with open(plik_notatki, encoding="utf-8") as plik:
                notatki.append(_schemas.ModuleNote.model_validate_json(plik.read()))
        with open(sciezka_diagramu, encoding="utf-8") as plik:
            diagram = _content.FlowGraph.model_validate_json(plik.read())
        sciezka_planu = os.path.join(katalog_wynikow, "plan.json")
        if os.path.isfile(sciezka_planu):
            with open(sciezka_planu, encoding="utf-8") as plik:
                plan = _schemas.Plan.model_validate_json(plik.read())
        else:
            plan = _schemas.Plan(summary=f"Robot {project_map.project_name} (technologia: {project_map.technology}); plan minimalny.", tasks=[], writer_knowledge=["guide_goals.md"])
            print("Plan minimalny (brak plan.json w katalogu wyników robota).")
        magazyn = _output.RunStore(katalog_wynikow)
        try:
            kontekst = _context.build_context(app_config, magazyn, _progress.print_line)
        except (RuntimeError, ValueError, OSError) as blad:
            sys.exit(f"BŁĄD: {blad}")
        print(f"\n=== Prawdziwy model pisarza: {project_map.project_name}, notatek: {len(notatki)}, klocków: {len(diagram.nodes)}, zakładki: {tab_ids} ===")
        napisane = {}
        for tab_id in tab_ids:
            stan = {"project_map": project_map, "plan": plan, "notes": notatki, "flow": diagram, "tab_id": tab_id}
            try:
                zmiana = writer_node(stan, types.SimpleNamespace(context=kontekst))
            except (ValueError, RuntimeError) as blad:
                sys.exit(f"BŁĄD: {blad}")
            napisane[tab_id] = zmiana["tabs"][0]
            print(f"\n--- {tab_id} ---")
            print(zmiana["tabs"][0].model_dump_json(indent=2, exclude_defaults=True))
        szablon = _template.sections_for_technology(kontekst.template, project_map.technology)
        tresc = _placeholders.build_placeholder_content(kontekst.template, project_map).model_copy(update={"flow": diagram})
        for zakladka in tresc.tabs:
            if zakladka.tab_id in napisane:
                nowe_bloki = {}
                for blok in napisane[zakladka.tab_id].blocks:
                    nowe_bloki[blok.section_id] = blok
                polaczone = []
                for blok in zakladka.blocks:
                    if blok.section_id in nowe_bloki:
                        polaczone.append(nowe_bloki.pop(blok.section_id))
                    else:
                        polaczone.append(blok)
                for blok in nowe_bloki.values():
                    polaczone.append(blok)
                zakladka.blocks = polaczone
        html = _render.render_guide(
            tresc,
            szablon,
            project_map,
            os.path.dirname(app_config.paths.guide_template),
            "podgląd pisarza",
            app_config.analysis.long_unit_lines,
            app_config.flow,
        )
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        sciezka_html = os.path.join(katalog_repo, "guide_test.html")
        with open(sciezka_html, "w", encoding="utf-8") as plik:
            plik.write(html)
        print(f"\nZapisano tabs/*.json w {katalog_wynikow} i podgląd {sciezka_html}")

    def manual_test():
        """Uruchamia sprawdzenia offline pisarza i wypisuje werdykt; z argumentem <katalog robota> woła też prawdziwy model.

        Po co: wynik "zgodne z oczekiwaniem: True" mówi, że pisarz składa schemat i prompt, ponawia i sprząta
        odpowiedź poprawnie; część z prawdziwym modelem pokazuje zakładki z prawdziwych notatek.
        """
        katalog_repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        app_config = _config.load_config(os.path.join(katalog_repo, "config.yaml"))
        temp_dir = tempfile.mkdtemp()
        try:
            print("=== Sprawdzenia offline ===")
            wyniki = _offline_checks(app_config, temp_dir)
            wszystkie_zgodne = True
            for opis, zgodne in wyniki:
                print(f"  {opis}: {zgodne}")
                if not zgodne:
                    wszystkie_zgodne = False
            print(f"\nzgodne z oczekiwaniem: {wszystkie_zgodne}")
            if len(sys.argv) > 1:
                zakladki = sys.argv[2:]
                if not zakladki:
                    zakladki = ["przeglad", "sciezki"]
                _real_model_run(sys.argv[1], zakladki, app_config)
        finally:
            import shutil

            shutil.rmtree(temp_dir)

    manual_test()
