Zrecenzuj przewodnik po robocie „{{ project_name }}”.

<zadanie>
Robot: {{ project_name }}

Podsumowanie projektu od plannera:
{{ plan_summary }}

Adresaci uwag (target) - tylko te:
{{ targets }}
</zadanie>

<kontekst_projektu>
{{ project_context }}
</kontekst_projektu>

<notatki_analitykow>
{{ notes }}
</notatki_analitykow>

<diagram>
{{ flow }}
</diagram>

<zakladki>
{{ tabs }}
</zakladki>

<baza_wiedzy>
{{ knowledge }}
</baza_wiedzy>
{% if problems_text %}
<poprawka>
Poprzednia recenzja (JSON):
{{ previous_review }}

Problemy znalezione w tej recenzji:
{{ problems_text }}

Zwróć poprawioną recenzję w całości.
</poprawka>
{% endif %}
