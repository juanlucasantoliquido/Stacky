"""Plan 209 F2 — Gate determinista: detectar la sección + evaluar grounding.

Advisory: emite warnings, nunca bloquea. Nunca lanza.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("LLM_BACKEND", "mock")

from services.validation_playbook import (  # noqa: E402
    DEGRADED_MESSAGE,
    SECTION_TITLE,
    ValidationPlaybook,
    ValidationStep,
    assess_grounding,
    detect,
)

_HTML_OK = f"""<html><body>
<h1>Analisis</h1>
<ol><li>ruido que NO es del playbook</li></ol>
<section data-stacky="validation-playbook" data-confidence="0.8">
  <h2>{SECTION_TITLE}</h2>
  <ol>
    <li data-source="func-docs:alta-cliente">Entrar a Clientes &gt; Detalle.
        <em>Resultado esperado:</em> se abre la ficha [func-docs: Alta de cliente]</li>
    <li data-source="catalog:IncHost">Asignar una obligacion.
        <em>Resultado esperado:</em> aparece en el inicio [catalog: IncHost]</li>
  </ol>
  <p data-sources>Fuentes: func-docs:alta-cliente, catalog:IncHost</p>
</section>
</body></html>"""


def test_detect_sin_marcador_devuelve_none():
    assert detect("<html><body><p>sin seccion</p></body></html>") is None


def test_detect_parsea_pasos_y_fuentes():
    pb = detect(_HTML_OK)

    assert pb is not None
    assert pb.status == "agent_provided"
    assert pb.confidence == 0.8
    assert len(pb.steps) == 2, "solo los <li> DE LA SECCION, no el ruido de afuera"
    assert pb.steps[0].source == "func-docs:alta-cliente"
    assert "Entrar a Clientes > Detalle" in pb.steps[0].action
    assert "Resultado esperado" not in pb.steps[0].action
    assert "se abre la ficha" in pb.steps[0].expected_result
    assert pb.steps[1].n == 2
    assert pb.sources == ["func-docs:alta-cliente", "catalog:IncHost"]


def test_detect_degradado():
    html = f'<section data-stacky="validation-playbook"><h2>{SECTION_TITLE}</h2>' \
           f'<p>{DEGRADED_MESSAGE}</p></section>'
    pb = detect(html)

    assert pb.status == "degraded"
    assert pb.steps == []
    assert pb.degraded_reason == "agent_declared"


def test_detect_degradado_sin_acentos():
    """El modelo puede comerse las tildes: la detección es tolerante."""
    sin_acentos = ("Estos pasos no pudieron verificarse contra la documentacion del "
                   "producto. Confirma con un referente de RS antes de usarlos.")
    pb = detect(f'<section data-stacky="validation-playbook"><p>{sin_acentos}</p></section>')

    assert pb.status == "degraded"


def test_detect_confidence_invalida_cae_a_default():
    html = '<section data-stacky="validation-playbook" data-confidence="zzz">' \
           '<ol><li data-source="x">a</li></ol></section>'
    assert detect(html).confidence == 0.5

    html2 = '<section data-stacky="validation-playbook" data-confidence="7">' \
            '<ol><li data-source="x">a</li></ol></section>'
    assert detect(html2).confidence == 1.0, "se capea a [0,1]"


def test_detect_seccion_sin_pasos():
    html = f'<section data-stacky="validation-playbook"><h2>{SECTION_TITLE}</h2></section>'
    pb = detect(html)

    assert pb.status == "agent_provided"
    assert pb.steps == []


def test_detect_nunca_lanza():
    for entrada in (None, "", "<b>roto", "<section data-stacky=\"validation-playbook\">",
                    "<section data-stacky='validation-playbook'><li>x</li>"):
        detect(entrada)  # no debe lanzar


def _pb(steps, status="agent_provided"):
    return ValidationPlaybook(status=status, steps=steps, sources=[], confidence=0.5,
                              degraded_reason=None)


def test_assess_paso_sin_fuente_warning():
    pb, warnings = assess_grounding(
        _pb([ValidationStep(1, "con fuente", "r", "func-docs:x"),
             ValidationStep(2, "huerfano", "r", "")]),
        None,
    )

    assert any("ungrounded_step" in w and "2" in w for w in warnings), warnings
    assert [s.n for s in pb.steps] == [1], "el paso sin fuente se elimina"
    assert pb.status == "agent_provided"


def test_assess_todos_sin_fuente_degrada():
    pb, warnings = assess_grounding(
        _pb([ValidationStep(1, "a", "r", ""), ValidationStep(2, "b", "r", "  ")]), None
    )

    assert pb.status == "degraded"
    assert pb.steps == []
    assert pb.degraded_reason == "ungrounded_steps"
    assert len(warnings) == 2


def test_assess_proceso_fuera_de_catalogo():
    catalogo = [{"name": "IncHost", "purpose": "hosting", "kind": "batch"}]
    steps = [ValidationStep(1, "Corré el proceso Zeta desde el menu", "r", "func-docs:x")]

    pb, warnings = assess_grounding(_pb(list(steps)), catalogo)
    assert any("process_not_in_catalog" in w for w in warnings), warnings
    assert pb.steps == [], "un paso que cita un proceso inexistente no se publica como grounded"

    pb_sin_cat, warnings_sin_cat = assess_grounding(_pb(list(steps)), None)
    assert not any("process_not_in_catalog" in w for w in warnings_sin_cat), (
        "sin catálogo no se opina (degradación honesta)"
    )
    assert len(pb_sin_cat.steps) == 1


def test_assess_proceso_en_catalogo_no_avisa():
    catalogo = [{"name": "IncHost", "purpose": "hosting", "kind": "batch"}]
    pb, warnings = assess_grounding(
        _pb([ValidationStep(1, "Corré el proceso IncHost", "r", "catalog:IncHost")]), catalogo
    )

    assert warnings == []
    assert len(pb.steps) == 1


def test_assess_source_text_se_usa_para_el_catalogo():
    """C4 — el HTML original puede pasarse como source_text para máxima fidelidad."""
    catalogo = [{"name": "IncHost", "purpose": "hosting", "kind": "batch"}]
    pb, warnings = assess_grounding(
        _pb([ValidationStep(1, "paso neutro", "r", "func-docs:x")]),
        catalogo,
        source_text="<p>ejecutá el proceso Omega</p>",
    )

    assert any("process_not_in_catalog" in w and "Omega" in w for w in warnings), warnings
    assert len(pb.steps) == 1, "el warning global no borra un paso que no cita el proceso"


def test_assess_nunca_lanza():
    assess_grounding(_pb([]), None)
    assess_grounding(_pb([]), [{"sin_name": 1}])
    assess_grounding(ValidationPlaybook(status="disabled", steps=[], sources=[],
                                        confidence=0.0, degraded_reason=None), None)
