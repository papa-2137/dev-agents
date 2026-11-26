"""Diagram przepływu: sprawdzenie spójności grafu i układ klocków - zwykłym kodem, bez modelu.

Co robi:
    - validate_flow() zwraca (problemy, ostrzeżenia). Problem = diagram błędny, agent musi go poprawić: liczba
      startów i końców, zdublowane id, strzałka do nieistniejącego klocka, klocek nieosiągalny ze startu, klocek
      bez wyjścia, decyzja z mniej niż dwoma wyjściami albo wyjściem bez etykiety, step/system bez modułu, cykl
      bez strzałki loop. Ostrzeżenie = diagram poprawny, ale za duży (flow.max_nodes, flow.max_decisions),
    - layout_flow() zwraca {id klocka: [wiersz, kolumna]} w formacie czytanym przez skrypt rysujący z makiety:
      wiersze - porządek od startu w dół liczony bez strzałek pętli (przy remisie kolejność klocków od agenta),
      kolumny - 0 ścieżka główna, 1 krótki objazd z decyzji (klocek, do którego prowadzą tylko gałęzie i który
      wraca do ścieżki głównej); pętle rysuje skrypt jako strzałki powrotne,
    - flow_view_data() zwraca słownik {nodes, edges, layout} w formacie skryptu z makiety (guide.js): rodzaje
      term/step/sys/dec, strzałki from/to, funkcje jako jeden napis, flaga unc dla klocka wywnioskowanego.

Dlaczego istnieje: model zwraca tylko graf (klocki i strzałki). Kod gwarantuje, że graf jest poprawny, a układ
powtarzalny - ten sam diagram wygląda tak samo przy każdym przebiegu.

Rola: moduł rdzenia towaru, używany przez renderer (kroki 36-37) i agenta diagramu (krok 51).

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.flow
        diagram z makiety (problemy, ostrzeżenia, układ porównany z makietą, dane dla skryptu rysującego),
        przykładowy diagram robota 02 z guide_content, zepsute kopie i diagram ponad progiem liczby klocków
"""

import dev_agents.config as _config
import dev_agents.guide_content as _content


# --- Pomocnicze ---


def _node_index(
    flow: _content.FlowGraph,
) -> dict[str, int]:
    """Zwraca {id klocka: pozycja na liście od agenta}; przy zdublowanym id zostaje pierwsza pozycja.

    Po co: rozstrzyganie remisów w kolejności wierszy i szybkie sprawdzanie, czy klocek istnieje.
    """
    indeks = {}
    for pozycja, klocek in enumerate(flow.nodes):
        indeks.setdefault(klocek.id, pozycja)
    return indeks


def _order_without_loops(
    flow: _content.FlowGraph,
) -> list[str]:
    """Zwraca klocki w porządku „od startu w dół” (strzałki pętli pominięte, remis - kolejność od agenta).

    Po co: wiersze układu; klocki, których nie da się ułożyć (cykl bez strzałki loop), w wyniku nie występują.
    """
    indeks = _node_index(flow)
    stopnie = {}
    nastepniki = {}
    for identyfikator in indeks:
        stopnie[identyfikator] = 0
        nastepniki[identyfikator] = []
    for strzalka in flow.edges:
        if strzalka.kind == "loop" or strzalka.source not in indeks or strzalka.target not in indeks:
            continue
        stopnie[strzalka.target] = stopnie[strzalka.target] + 1
        nastepniki[strzalka.source].append(strzalka.target)
    gotowe = []
    for identyfikator, stopien in stopnie.items():
        if stopien == 0:
            gotowe.append(identyfikator)
    kolejnosc = []
    while gotowe:
        gotowe.sort(key=indeks.get)
        obecny = gotowe.pop(0)
        kolejnosc.append(obecny)
        for nastepny in nastepniki[obecny]:
            stopnie[nastepny] = stopnie[nastepny] - 1
            if stopnie[nastepny] == 0:
                gotowe.append(nastepny)
    return kolejnosc


def _reachable_from(
    flow: _content.FlowGraph,
    start_id: str,
) -> list[str]:
    """Zwraca id klocków osiągalnych ze startu po wszystkich strzałkach (także pętlach).

    Po co: klocek nieosiągalny ze startu to błąd diagramu.
    """
    odwiedzone = [start_id]
    do_odwiedzenia = [start_id]
    while do_odwiedzenia:
        obecny = do_odwiedzenia.pop()
        for strzalka in flow.edges:
            if strzalka.source == obecny and strzalka.target not in odwiedzone:
                odwiedzone.append(strzalka.target)
                do_odwiedzenia.append(strzalka.target)
    return odwiedzone


# --- Sprawdzanie ---


def _node_problems(
    flow: _content.FlowGraph,
) -> list[str]:
    """Zwraca problemy klocków: liczba startów i końców, zdublowane id, step/system bez modułu.

    Po co: część validate_flow() dotycząca samych klocków.
    """
    problemy = []
    starty = []
    konce = []
    widziane = []
    for klocek in flow.nodes:
        if klocek.id in widziane:
            problemy.append(f"Zdublowane id klocka: '{klocek.id}'")
        widziane.append(klocek.id)
        if klocek.kind == "start":
            starty.append(klocek.id)
        if klocek.kind == "end":
            konce.append(klocek.id)
        if klocek.kind in ("step", "system") and not klocek.module:
            problemy.append(f"Klocek '{klocek.id}' ({klocek.kind}): brak modułu")
    if len(starty) != 1:
        problemy.append(f"Diagram musi mieć dokładnie jeden start, ma {len(starty)}: {starty}")
    if not konce:
        problemy.append("Diagram nie ma klocka końca (end)")
    return problemy


def _edge_problems(
    flow: _content.FlowGraph,
) -> list[str]:
    """Zwraca problemy strzałek: nieistniejące klocki, klocek bez wyjścia, decyzja bez dwóch opisanych wyjść.

    Po co: część validate_flow() dotycząca strzałek.
    """
    problemy = []
    indeks = _node_index(flow)
    wyjscia = {}
    for strzalka in flow.edges:
        for koniec in (strzalka.source, strzalka.target):
            if koniec not in indeks:
                problemy.append(f"Strzałka {strzalka.source} -> {strzalka.target}: nie ma klocka '{koniec}'")
        wyjscia.setdefault(strzalka.source, []).append(strzalka)
    for klocek in flow.nodes:
        strzalki = wyjscia.get(klocek.id, [])
        if klocek.kind != "end" and not strzalki:
            problemy.append(f"Klocek '{klocek.id}' nie ma wyjścia")
        if klocek.kind == "decision" and len(strzalki) < 2:
            problemy.append(f"Decyzja '{klocek.id}' ma {len(strzalki)} wyjście - wymagane co najmniej dwa")
        for strzalka in strzalki:
            if klocek.kind == "decision" and not strzalka.label:
                problemy.append(f"Decyzja '{klocek.id}': wyjście do '{strzalka.target}' bez etykiety")
    return problemy


def validate_flow(
    flow: _content.FlowGraph,
    flow_config: _config.FlowConfig,
) -> tuple[list[str], list[str]]:
    """Zwraca (problemy, ostrzeżenia) diagramu; puste listy = diagram poprawny i w progach z configu.

    Po co: błędny diagram wraca do agenta z czytelną listą, zamiast po cichu zepsuć przewodnik.
    """
    problemy = _node_problems(flow) + _edge_problems(flow)
    starty = []
    decyzje = 0
    for klocek in flow.nodes:
        if klocek.kind == "start":
            starty.append(klocek.id)
        if klocek.kind == "decision":
            decyzje = decyzje + 1
    if len(starty) == 1:
        osiagalne = _reachable_from(flow, starty[0])
        for klocek in flow.nodes:
            if klocek.id not in osiagalne:
                problemy.append(f"Klocek '{klocek.id}' jest nieosiągalny ze startu")
    ulozone = _order_without_loops(flow)
    nieulozone = []
    for identyfikator in _node_index(flow):
        if identyfikator not in ulozone:
            nieulozone.append(identyfikator)
    if nieulozone:
        problemy.append(f"Cykl bez strzałki oznaczonej loop - nie da się ułożyć klocków (cykl i wszystko za nim): {nieulozone}")
    ostrzezenia = []
    if len(flow.nodes) > flow_config.max_nodes:
        ostrzezenia.append(f"Diagram ma {len(flow.nodes)} klocków (próg flow.max_nodes: {flow_config.max_nodes})")
    if decyzje > flow_config.max_decisions:
        ostrzezenia.append(f"Diagram ma {decyzje} decyzji (próg flow.max_decisions: {flow_config.max_decisions})")
    wynik = (problemy, ostrzezenia)
    return wynik


# --- Układ ---


def _side_nodes(
    flow: _content.FlowGraph,
) -> list[str]:
    """Zwraca id klocków-objazdów: wchodzą do nich tylko gałęzie decyzji, wychodzi jedna strzałka do klocka, do którego prowadzi też inna strzałka.

    Po co: objazd (np. obsługa błędu wiersza) rysujemy z boku, a nie na ścieżce głównej.
    """
    wejscia = {}
    wyjscia = {}
    for strzalka in flow.edges:
        if strzalka.kind == "loop":
            continue
        wejscia.setdefault(strzalka.target, []).append(strzalka)
        wyjscia.setdefault(strzalka.source, []).append(strzalka)
    objazdy = []
    for klocek in flow.nodes:
        przychodzace = wejscia.get(klocek.id, [])
        wychodzace = wyjscia.get(klocek.id, [])
        tylko_galezie = len(przychodzace) > 0
        for strzalka in przychodzace:
            if strzalka.kind != "branch":
                tylko_galezie = False
        if not tylko_galezie or len(wychodzace) != 1:
            continue
        if len(wejscia.get(wychodzace[0].target, [])) > 1:
            objazdy.append(klocek.id)
    return objazdy


def layout_flow(
    flow: _content.FlowGraph,
) -> dict[str, list[int]]:
    """Zwraca {id klocka: [wiersz, kolumna]}: wiersze od startu w dół, kolumna 1 dla objazdów, 0 dla reszty.

    Po co: układ liczy kod, więc diagram jest powtarzalny; format zgodny ze skryptem rysującym z makiety.

    Uwaga: klocki w cyklu bez strzałki loop (problem w validate_flow) dostają ostatnie wiersze w kolejności od agenta.
    """
    kolejnosc = _order_without_loops(flow)
    for identyfikator in _node_index(flow):
        if identyfikator not in kolejnosc:
            kolejnosc.append(identyfikator)
    objazdy = _side_nodes(flow)
    uklad = {}
    for wiersz, identyfikator in enumerate(kolejnosc):
        kolumna = 0
        if identyfikator in objazdy:
            kolumna = 1
        uklad[identyfikator] = [wiersz, kolumna]
    return uklad


# --- Dane dla skryptu rysującego ---

_VIEW_KINDS = {"start": "term", "end": "term", "step": "step", "system": "sys", "decision": "dec"}
_VIEW_REF_KINDS = {"file": "f", "env": "env", "system": "sys", "memory": "mem"}


def _view_ref(
    ref: _content.DataRef,
) -> dict:
    """Zwraca dane klocka jako {name, kind}, gdzie kind to klasa kafelka w skrypcie: f, env, sys albo mem.

    Po co: skrypt rysujący nadaje kafelkowi klasę wprost z tego pola, bez zgadywania rodzaju po nazwie.
    """
    wpis = {"name": ref.name, "kind": _VIEW_REF_KINDS[ref.kind]}
    return wpis


def _view_refs(
    refs: list[_content.DataRef],
) -> list[dict]:
    """Zwraca listę danych klocka w formacie skryptu, w kolejności od agenta.

    Po co: jedna pętla dla wejść i wyjść klocka.
    """
    wynik = []
    for ref in refs:
        wynik.append(_view_ref(ref))
    return wynik


def _view_node(
    node: _content.FlowNode,
) -> dict:
    """Zwraca klocek w formacie skryptu z makiety: rodzaj term/step/sys/dec, funcs jako lista, dane z rodzajem, flaga unc.

    Po co: skrypt rysujący czyta te pola wprost; funkcje w kolejności wywołania (podpowiedź łączy je przecinkiem,
    wiersz „Krok po kroku” pokazuje listę numerowaną).
    """
    wezel = {
        "id": node.id,
        "kind": _VIEW_KINDS[node.kind],
        "label": node.label,
        "desc": node.description,
        "module": node.module,
        "funcs": list(node.functions),
        "reads": _view_refs(node.reads),
        "writes": _view_refs(node.writes),
        "unc": not node.certain,
    }
    return wezel


def flow_view_data(
    flow: _content.FlowGraph,
) -> dict:
    """Zwraca {nodes, edges, layout} dla skryptu rysującego diagram (guide.js): klocki, strzałki from/to i układ.

    Po co: renderer wstawia ten słownik do strony jako JSON; skrypt rysuje z niego diagram i wiersze „Krok po kroku”,
    więc oba powstają z tych samych danych.

    Uwaga: wołać dla diagramu bez problemów z validate_flow - przy problemach układ może być niepełny.
    """
    klocki = []
    for klocek in flow.nodes:
        klocki.append(_view_node(klocek))
    strzalki = []
    for strzalka in flow.edges:
        strzalki.append({"from": strzalka.source, "to": strzalka.target, "label": strzalka.label, "kind": strzalka.kind})
    dane = {"nodes": klocki, "edges": strzalki, "layout": layout_flow(flow)}
    return dane


# --- Test ręczny ---

if __name__ == "__main__":
    import os

    def _mockup_flow() -> tuple[_content.FlowGraph, dict[str, list[int]]]:
        """Zwraca diagram z makiety (12 klocków, dwie decyzje, objazd i pętla) i układ zapisany w makiecie.

        Po co: wzorzec - układ liczony przez kod ma być identyczny z makietą.
        """
        dane = [
            ("n1", "start", "Start", ""),
            ("n2", "step", "Wczytanie konfiguracji", "main.py"),
            ("n3", "system", "Otwarcie RPA Challenge", "src/challange_page.py"),
            ("n4", "step", "Pobranie wierszy z Excela", "src/excel_tools.py"),
            ("n5", "decision", "Jest kolejny wiersz?", "main.py"),
            ("n6", "system", "Wypełnienie formularza", "src/challange_page.py"),
            ("n7", "decision", "Wysłanie się udało?", "main.py"),
            ("n8", "step", "Obsługa błędu wiersza", "main.py"),
            ("n9", "system", "Wysyłka wiersza do bazy raportowej", "src/report.py"),
            ("n10", "system", "Odczyt wyniku i zamknięcie strony", "src/challange_page.py"),
            ("n11", "system", "Zapis salda z ParaBank", "src/parabank_page.py"),
            ("n12", "end", "Koniec", ""),
        ]
        klocki = []
        for identyfikator, rodzaj, napis, modul in dane:
            klocki.append(_content.FlowNode(id=identyfikator, kind=rodzaj, label=napis, module=modul))
        strzalki = [
            _content.FlowEdge(source="n1", target="n2"),
            _content.FlowEdge(source="n2", target="n3"),
            _content.FlowEdge(source="n3", target="n4"),
            _content.FlowEdge(source="n4", target="n5"),
            _content.FlowEdge(source="n5", target="n6", label="tak"),
            _content.FlowEdge(source="n5", target="n10", label="nie", kind="branch"),
            _content.FlowEdge(source="n6", target="n7"),
            _content.FlowEdge(source="n7", target="n9", label="tak"),
            _content.FlowEdge(source="n7", target="n8", label="nie", kind="branch"),
            _content.FlowEdge(source="n8", target="n9"),
            _content.FlowEdge(source="n9", target="n5", label="następny wiersz", kind="loop"),
            _content.FlowEdge(source="n10", target="n11"),
            _content.FlowEdge(source="n11", target="n12"),
        ]
        uklad_makiety = {
            "n1": [0, 0], "n2": [1, 0], "n3": [2, 0], "n4": [3, 0], "n5": [4, 0], "n6": [5, 0],
            "n7": [6, 0], "n8": [7, 1], "n9": [8, 0], "n10": [9, 0], "n11": [10, 0], "n12": [11, 0],
        }
        wynik = (_content.FlowGraph(nodes=klocki, edges=strzalki), uklad_makiety)
        return wynik

    def _broken_flows(
        flow: _content.FlowGraph,
    ) -> list[tuple[str, _content.FlowGraph]]:
        """Zwraca zepsute kopie diagramu: klocek bez wyjścia, strzałka donikąd, decyzja z jednym wyjściem, dwa starty, cykl bez loop.

        Po co: każdy rodzaj problemu ma dać czytelny komunikat z id klocka.
        """
        bez_wyjscia = flow.model_copy(deep=True)
        bez_wyjscia.edges = bez_wyjscia.edges[:-1]
        donikad = flow.model_copy(deep=True)
        donikad.edges.append(_content.FlowEdge(source="n2", target="n99"))
        jedno_wyjscie = flow.model_copy(deep=True)
        jedno_wyjscie.edges.pop(5)
        dwa_starty = flow.model_copy(deep=True)
        dwa_starty.nodes[1].kind = "start"
        bez_loop = flow.model_copy(deep=True)
        bez_loop.edges[10].kind = "normal"
        przypadki = [
            ("Klocek bez wyjścia (usunięta strzałka n11 -> n12)", bez_wyjscia),
            ("Strzałka do nieistniejącego klocka n99", donikad),
            ("Decyzja z jednym wyjściem (usunięta gałąź n5 -> n10)", jedno_wyjscie),
            ("Dwa starty (n2 jako start)", dwa_starty),
            ("Cykl bez strzałki loop (n9 -> n5 jako normal)", bez_loop),
        ]
        return przypadki

    def _big_flow() -> _content.FlowGraph:
        """Zwraca poprawny diagram liniowy z 31 klocków (start, 29 kroków, koniec).

        Po co: sprawdzenie ostrzeżenia o rozmiarze przy progu flow.max_nodes = 30.
        """
        klocki = [_content.FlowNode(id="k0", kind="start", label="Start")]
        strzalki = []
        for numer in range(1, 30):
            klocki.append(_content.FlowNode(id=f"k{numer}", kind="step", label=f"Krok {numer}", module="main.py"))
            strzalki.append(_content.FlowEdge(source=f"k{numer - 1}", target=f"k{numer}"))
        klocki.append(_content.FlowNode(id="k30", kind="end", label="Koniec"))
        strzalki.append(_content.FlowEdge(source="k29", target="k30"))
        diagram = _content.FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    def _print_check(
        title: str,
        problems: list[str],
        warnings: list[str],
    ) -> None:
        """Wypisuje problemy i ostrzeżenia diagramu.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"--- {title} ---")
        if not problems:
            print("  Problemy: brak")
        for problem in problems:
            print(f"  PROBLEM: {problem}")
        if not warnings:
            print("  Ostrzeżenia: brak")
        for ostrzezenie in warnings:
            print(f"  OSTRZEŻENIE: {ostrzezenie}")

    def _print_layout(
        flow: _content.FlowGraph,
        layout: dict[str, list[int]],
    ) -> None:
        """Wypisuje tabelę klocek | wiersz | kolumna | napis.

        Po co: układ widoczny bez renderera.
        """
        for klocek in flow.nodes:
            wiersz, kolumna = layout[klocek.id]
            print(f"    {klocek.id:<4} wiersz {wiersz:>2}  kolumna {kolumna}  {klocek.label}")

    def _print_view_data(
        flow: _content.FlowGraph,
    ) -> None:
        """Wypisuje liczby i rodzaje z danych dla skryptu rysującego oraz id klocków z flagą unc.

        Po co: sprawdzenie formatu (term/step/sys/dec, from/to) bez uruchamiania przeglądarki.
        """
        dane = flow_view_data(flow)
        rodzaje = []
        for klocek in dane["nodes"]:
            rodzaje.append(klocek["kind"])
        wywnioskowane = []
        for klocek in dane["nodes"]:
            if klocek["unc"]:
                wywnioskowane.append(klocek["id"])
        kafelki = 0
        funkcje = 0
        for klocek in dane["nodes"]:
            kafelki = kafelki + len(klocek["reads"]) + len(klocek["writes"])
            funkcje = funkcje + len(klocek["funcs"])
        pierwsza = dane["edges"][0]
        print(f"  Dane dla skryptu: klocków {len(dane['nodes'])}, strzałek {len(dane['edges'])}, układ {len(dane['layout'])} wpisów")
        print(f"    kafelków wejść i wyjść: {kafelki}, funkcji: {funkcje}")
        print(f"    rodzaje: {' '.join(rodzaje)}")
        print(f"    pierwsza strzałka: {pierwsza['from']} -> {pierwsza['to']}, wywnioskowane klocki: {wywnioskowane}")

    def _print_ref_kinds() -> None:
        """Wypisuje klasy kafelków dla czterech rodzajów danych klocka i dla klocka bez danych.

        Po co: dowód, że rodzaj z schematu (file, env, system, memory) trafia do skryptu jako f, env, sys, mem.
        """
        klocek = _content.FlowNode(
            id="x",
            kind="system",
            label="Klocek z czterema rodzajami danych",
            reads=[
                _content.DataRef(name="config.yml", kind="file"),
                _content.DataRef(name="HASLO_API", kind="env"),
            ],
            writes=[
                _content.DataRef(name="API zamówień", kind="system"),
                _content.DataRef(name="lista transakcji", kind="memory"),
            ],
        )
        widok = _view_node(klocek)
        klasy = []
        for wpis in widok["reads"] + widok["writes"]:
            klasy.append(wpis["kind"])
        print(f"  Klasy kafelków (plik, zmienna, system, pamięć): {klasy}")
        print(f"  Klocek bez danych: wejścia {_view_node(_content.FlowNode(id='y', kind='end', label='Koniec'))['reads']}")

    def manual_test():
        """Sprawdza diagram z makiety, przykład robota 02, zepsute kopie i diagram ponad progiem.

        Po co: wszystkie problemy i ostrzeżenia, układ i dane dla skryptu rysującego w jednym przebiegu.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        flow_config = _config.load_config(os.path.join(repo_dir, "config.yaml")).flow

        diagram, uklad_makiety = _mockup_flow()
        problemy, ostrzezenia = validate_flow(diagram, flow_config)
        _print_check("Diagram z makiety", problemy, ostrzezenia)
        uklad = layout_flow(diagram)
        _print_layout(diagram, uklad)
        print(f"  Układ zgodny z makietą: {uklad == uklad_makiety}")
        _print_view_data(diagram)
        print()

        przyklad = _robot_02_flow()
        problemy, ostrzezenia = validate_flow(przyklad, flow_config)
        _print_check("Przykładowy diagram robota 02 (guide_content)", problemy, ostrzezenia)
        _print_layout(przyklad, layout_flow(przyklad))
        _print_view_data(przyklad)
        _print_ref_kinds()
        print()

        for tytul, zepsuty in _broken_flows(diagram):
            problemy, ostrzezenia = validate_flow(zepsuty, flow_config)
            _print_check(tytul, problemy, ostrzezenia)
        print()
        problemy, ostrzezenia = validate_flow(_big_flow(), flow_config)
        _print_check("Diagram z 31 klocków", problemy, ostrzezenia)

    def _robot_02_flow() -> _content.FlowGraph:
        """Składa diagram robota 02 - ten sam co w przykładzie z testu guide_content (krok 31).

        Po co: test układu na drugim, prostszym diagramie z pętlą i gałęzią.
        """
        klocki = [
            _content.FlowNode(id="n1", kind="start", label="Start z run.bat"),
            _content.FlowNode(
                id="n2",
                kind="step",
                label="Wczytaj listę plików",
                module="przetwarzanie.py",
                functions=["run:45"],
                reads=[_content.DataRef(name="dane/wejscie/*.csv", kind="file")],
            ),
            _content.FlowNode(id="n3", kind="decision", label="Nagłówek poprawny?", module="przetwarzanie.py"),
            _content.FlowNode(
                id="n4",
                kind="step",
                label="Przelicz zamówienia",
                module="przetwarzanie.py",
                functions=["run:120"],
                writes=[_content.DataRef(name="dane/wyjscie/wyniki_*.json", kind="file")],
            ),
            _content.FlowNode(id="n5", kind="system", label="Wyślij do API", module="przetwarzanie.py", certain=False),
            _content.FlowNode(id="n6", kind="end", label="Raport Excel", module="raport.py"),
        ]
        strzalki = [
            _content.FlowEdge(source="n1", target="n2"),
            _content.FlowEdge(source="n2", target="n3"),
            _content.FlowEdge(source="n3", target="n4", label="tak", kind="branch"),
            _content.FlowEdge(source="n3", target="n2", label="nie - plik do odrzuconych", kind="loop"),
            _content.FlowEdge(source="n4", target="n5"),
            _content.FlowEdge(source="n5", target="n6"),
        ]
        diagram = _content.FlowGraph(nodes=klocki, edges=strzalki)
        return diagram

    manual_test()
