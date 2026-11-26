Ułóż diagram przepływu robota „{{ project_name }}”.

<zadanie>
Robot: {{ project_name }}

Podsumowanie projektu od plannera:
{{ plan_summary }}

Limity rozmiaru diagramu: najwyżej {{ max_nodes }} klocków i najwyżej {{ max_decisions }} decyzji.
</zadanie>

<kontekst_projektu>
{{ project_context }}
</kontekst_projektu>

<notatki_analitykow>
{{ notes }}
</notatki_analitykow>

<baza_wiedzy>
{{ knowledge }}
</baza_wiedzy>
{% if problems_text %}
<poprawka>
Poprzednia wersja diagramu (JSON):
{{ previous_flow }}

Problemy i uwagi do poprawienia w tej wersji (od kodu albo od recenzenta):
{{ problems_text }}

Zwróć poprawiony diagram w całości.
</poprawka>
{% endif %}
