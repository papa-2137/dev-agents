"""Graf zależności między plikami źródłowymi robota i kolejność czytania kodu - liczone zwykłym kodem, bez modelu.

Co robi: build_dependencies() bierze z mapy projektu odwołania plików (SourceFile.references.files) i zwraca:
    - krawędzie grafu: pary [plik, plik, z którego korzysta] - tylko między plikami źródłowymi robota
      (odwołania do plików frameworku i plików spoza mapy odpadają),
    - kolejność czytania: od każdego punktu wejścia w głąb (najpierw plik, potem pliki, z których korzysta,
      alfabetycznie na każdym poziomie), każdy plik raz - cykl nie zawiesza obliczeń; pliki nieosiągalne
      z punktów wejścia na końcu, alfabetycznie.

Dlaczego istnieje: z krawędzi powstaje graf zależności modułów w zakładce Struktura projektu, a kolejność
czytania trafia do zakładki Dla dewelopera i do planisty - nikt nie zgaduje, od czego zacząć. Moduł nie wie
nic o technologii: dostaje ścieżki, więc działa tak samo dla każdej technologii, która zwraca odwołania.

Uwaga: kolejność uruchamiania (np. z run.bat) to co innego - ustalają ją agenci z plików uruchamiających.

Rola: moduł rdzenia towaru, wołany przez scanner.build_project_map() na końcu budowy mapy.

Test ręczny (z katalogu głównego repo):
    python -m dev_agents.dependencies
        krawędzie i kolejność czytania robotów testowych 01 i 02 oraz projektu tymczasowego z cyklem
        a.py <-> b.py, plikiem bez odwołań i odwołaniem do skopiowanego frameworku
"""

import dev_agents.schemas as _schemas


def _robot_edges(
    project_map: _schemas.ProjectMap,
) -> list[list[str]]:
    """Zwraca krawędzie [plik, plik, z którego korzysta] tylko między plikami źródłowymi robota, w kolejności z mapy.

    Po co: graf ma pokazywać kod robota - odwołania do plików frameworku albo spoza mapy są pomijane.
    """
    pliki_robota = []
    for plik_zrodlowy in project_map.source_files:
        pliki_robota.append(plik_zrodlowy.path)
    krawedzie = []
    for plik_zrodlowy in project_map.source_files:
        for cel in plik_zrodlowy.references.files:
            if cel in pliki_robota:
                krawedzie.append([plik_zrodlowy.path, cel])
    return krawedzie


def _visit(
    path: str,
    neighbours: dict[str, list[str]],
    order: list[str],
) -> None:
    """Dopisuje plik do kolejności, a potem - alfabetycznie i w głąb - pliki, z których korzysta; plik już obecny pomija.

    Po co: czytanie od ogółu do szczegółu; sprawdzenie "już obecny" przerywa cykle.
    """
    if path in order:
        return
    order.append(path)
    for cel in sorted(neighbours.get(path, [])):
        _visit(cel, neighbours, order)


def build_dependencies(
    project_map: _schemas.ProjectMap,
) -> tuple[list[list[str]], list[str]]:
    """Zwraca (krawędzie grafu zależności, kolejność czytania plików źródłowych robota).

    Po co: dane do grafu zależności i do kolejności czytania liczone raz, przy budowie mapy projektu.
    """
    krawedzie = _robot_edges(project_map)
    sasiedzi = {}
    for zrodlo, cel in krawedzie:
        sasiedzi.setdefault(zrodlo, []).append(cel)
    kolejnosc = []
    for punkt_wejscia in project_map.entrypoints:
        _visit(punkt_wejscia, sasiedzi, kolejnosc)
    pozostale = []
    for plik_zrodlowy in project_map.source_files:
        if plik_zrodlowy.path not in kolejnosc:
            pozostale.append(plik_zrodlowy.path)
    for sciezka in sorted(pozostale):
        _visit(sciezka, sasiedzi, kolejnosc)
    wynik = (krawedzie, kolejnosc)
    return wynik


# --- Test ręczny ---

if __name__ == "__main__":
    import os
    import shutil
    import tempfile

    import dev_agents.config as _config
    import dev_agents.scanner as _scanner

    def _make_cycle_project(
        directory: str,
    ) -> None:
        """Tworzy projekt tymczasowy: main.py -> a.py <-> b.py (cykl), samotny.py bez odwołań, main.py -> skopiowany framework.

        Po co: sprawdzenie, że cykl nie zawiesza obliczeń, plik nieosiągalny trafia na koniec, a krawędź do
        frameworku odpada.
        """
        tresci = {
            "main.py": "import a\nimport roboforge_framework.launcher\n",
            "a.py": "import b\n",
            "b.py": "import a\n",
            "samotny.py": "x = 1\n",
            "roboforge_framework/launcher.py": "y = 2\n",
        }
        for sciezka, tresc in tresci.items():
            pelna = os.path.join(directory, sciezka)
            os.makedirs(os.path.dirname(pelna), exist_ok=True)
            with open(pelna, "w", encoding="utf-8") as plik:
                plik.write(tresc)

    def _print_dependencies(
        title: str,
        project_map: _schemas.ProjectMap,
    ) -> None:
        """Wypisuje punkty wejścia, krawędzie grafu i ponumerowaną kolejność czytania z mapy projektu.

        Po co: czytelny wynik testu; tylko formatuje gotowe dane.
        """
        print(f"=== {title}: {project_map.root} ===")
        print(f"  Punkty wejścia: {project_map.entrypoints}")
        print(f"  Krawędzie ({len(project_map.dependency_edges)}):")
        for zrodlo, cel in project_map.dependency_edges:
            print(f"      {zrodlo} -> {cel}")
        print("  Kolejność czytania:")
        numer = 1
        for sciezka in project_map.reading_order:
            print(f"      {numer}. {sciezka}")
            numer = numer + 1
        print()

    def manual_test():
        """Buduje mapy robotów testowych i projektu tymczasowego (graf liczy build_project_map) i wypisuje wynik.

        Po co: sprawdzenie grafu i kolejności na prawdziwych robotach i na cyklu.
        """
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        app_config = _config.load_config(os.path.join(repo_dir, "config.yaml"))
        katalog_testow = os.path.normpath(os.path.join(repo_dir, "..", "..", "tests"))
        for tytul, nazwa in [("robot 01", "01_rpa_challange_roboforge"), ("robot 02", "02_robot_bez_frameworku")]:
            root = os.path.join(katalog_testow, nazwa)
            if not os.path.isdir(root):
                print(f"=== {tytul}: brak katalogu {root} - pomijam ===\n")
                continue
            _print_dependencies(tytul, _scanner.build_project_map(root, app_config.scan))

        temp_dir = tempfile.mkdtemp()
        try:
            _make_cycle_project(temp_dir)
            _print_dependencies("projekt z cyklem", _scanner.build_project_map(temp_dir, app_config.scan))
        finally:
            shutil.rmtree(temp_dir)

    manual_test()
