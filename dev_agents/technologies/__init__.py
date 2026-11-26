"""Obsługa technologii analizowanych projektów (Python, a później UiPath, Robot Framework, NICE).

Każda technologia to podklasa kontraktu z base.py w osobnym pliku. Cała wiedza o języku i frameworku
siedzi tutaj - rdzeń towaru woła tylko metody kontraktu, a technologię projektu wybiera przez rejestr
(registry.py). Ten plik celowo niczego nie importuje - patrz docstring registry.py.
"""
