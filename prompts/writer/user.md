Napisz zakładkę „{{ tab_title }}” przewodnika po robocie „{{ project_name }}”.

<zadanie>
Robot: {{ project_name }}
tab_id: {{ tab_id }}
Tytuł zakładki: {{ tab_title }}
Wstęp zakładki (stałe zdanie pod tytułem, nie piszesz go): {{ tab_lead }}

Podsumowanie projektu od plannera:
{{ plan_summary }}
</zadanie>

<sekcje>
{{ sections }}
</sekcje>

<kontekst_projektu>
{{ project_context }}
</kontekst_projektu>

<notatki_analitykow>
{{ notes }}
</notatki_analitykow>

<diagram>
{{ flow }}
</diagram>
{% if text_files %}
<pliki_robota>
{{ text_files }}
</pliki_robota>
{% endif %}{% if risky_facts %}
<fakty_kodu>
{{ risky_facts }}
</fakty_kodu>
{% endif %}
<baza_wiedzy>
{{ knowledge }}
</baza_wiedzy>
{% if problems_text %}
<poprawka>
Poprzednia wersja zakładki (JSON):
{{ previous_tab }}

Problemy i uwagi do poprawienia w tej wersji (od kodu albo od recenzenta):
{{ problems_text }}

Zwróć poprawioną zakładkę w całości.
</poprawka>
{% endif %}
