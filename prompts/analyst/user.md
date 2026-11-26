Opisz jednostkę kodu „{{ unit_name }}” robota „{{ project_name }}”.

<zadanie>
Jednostka: {{ unit_name }}
Pliki jednostki: {{ unit_files }}

Podsumowanie projektu od plannera:
{{ plan_summary }}

Wskazówka plannera dla tej jednostki:
{{ hint }}
</zadanie>

<kontekst_projektu>
{{ project_context }}
</kontekst_projektu>

<kod_jednostki>
{{ unit_code }}
</kod_jednostki>
{% if chunk_total > 1 %}
<kawalek>
Ta jednostka jest długa, więc czytasz ją po kawałkach. Teraz analizujesz kawałek {{ chunk_index }} z {{ chunk_total }}: {{ chunk_range }}. W <kod_jednostki> jest tylko ten kawałek, a numery linii są bezwzględne (z całego pliku) - przepisuj je bez zmian. Funkcje i klasy całego pliku z zakresami linii są w <kontekst_projektu> (source_files).
Opisz wyłącznie to, co jest w tym kawałku: w polu purpose jedno-dwa zdania o tym, co robi ten kawałek (nie cała jednostka). Funkcja przerwana na granicy kawałka (początek albo koniec) - opisz to, co widać, nie zgaduj reszty. Poniższe podsumowanie poprzednich kawałków służy tylko jako kontekst - nie powtarzaj w tej odpowiedzi czynności z poprzednich kawałków. Z czasem wszystkie kawałki zostaną złożone w jedną notatkę.

Podsumowanie poprzednich kawałków:
{{ previous_summary }}
</kawalek>
{% endif %}

<pliki_tekstowe>
{{ text_files }}
</pliki_tekstowe>

<baza_wiedzy>
{{ knowledge }}
</baza_wiedzy>

<czesc_notatki>
{{ note_part }}
</czesc_notatki>
