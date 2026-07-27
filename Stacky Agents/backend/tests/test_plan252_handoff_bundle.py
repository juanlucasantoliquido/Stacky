"""Plan 252 F2 — manifest + README por plantilla + degradacion honesta. 17 tests."""
from __future__ import annotations

import dataclasses
import json
import re
import sys
import types

import pytest

from services import pipeline_capability_frontier as fr
from services import pipeline_handoff_bundle as hb

_MODULOS_HERMANOS = ("pipeline_environments", "pipeline_inventory", "pipeline_profiler")


def _forzar_ausencia(monkeypatch, nombres=_MODULOS_HERMANOS) -> None:
    """Fuerza la ausencia de los modulos hermanos DE VERDAD.

    GOTCHA MEDIDO: poner `sys.modules["services.X"] = None` NO alcanza si otro test ya
    importo el modulo, porque `from services import X` usa primero el ATRIBUTO del
    paquete `services` y solo cae a sys.modules si el atributo no existe. Sin parchear
    las dos cosas, este test pasa aislado y falla en el archivo completo -- o peor, pasa
    en verde probando la rama equivocada.
    """
    import services

    for nombre in nombres:
        monkeypatch.setitem(sys.modules, "services.%s" % nombre, None)
        monkeypatch.delattr(services, nombre, raising=False)


def _frontera(probes=None, deploys=True):
    return fr.resolve_frontier(probes or {}, pipeline_deploys=deploys)


def _inputs(**kw):
    base = dict(
        pipeline_name="AgendaWeb CI",
        provider="ado",
        yaml_files={"pipelines/ci.yml": "stages: []\n"},
        script_files={"scripts/Deploy-Local.ps1": "Write-Host hola\n"},
        variables=(hb.HandoffVariable(
            name="DB_PASSWORD", where="Pipelines → Library",
            format_hint="texto de una línea, sin comillas", secret=True),),
        pipeline_deploys=True,
    )
    base.update(kw)
    return hb.BundleInputs(**base)


# ── 1 ────────────────────────────────────────────────────────────────────────
def test_paso_sin_validacion_es_rechazado():
    """KPI-4 — un paso sin validacion no es un paso, es una promesa."""
    comun = dict(n=1, action="a", expected_result="e", source="s", where="w",
                 command="c", on_failure="f")
    hb.HandoffStep(**comun)                       # el completo no lanza
    for campo in ("action", "expected_result", "source", "where", "command", "on_failure"):
        malo = dict(comun)
        malo[campo] = "   "
        with pytest.raises(hb.HandoffError) as exc:
            hb.HandoffStep(**malo)
        assert campo in str(exc.value)


# ── 2 ────────────────────────────────────────────────────────────────────────
def test_variable_no_modela_valor():
    """No se puede filtrar lo que no se modela."""
    campos = {f.name for f in dataclasses.fields(hb.HandoffVariable)}
    assert campos == {"name", "where", "format_hint", "secret"}
    assert "value" not in campos


# ── 3 ────────────────────────────────────────────────────────────────────────
def test_ninguna_accion_can_es_paso_manual():
    """KPI-3."""
    resuelto = _frontera({p: True for p in fr.PROBE_IDS})
    ids_can = {r.action.id for r in fr.automatic_actions(resuelto)}
    for paso in hb.build_steps(resuelto):
        assert paso.source.split(":", 1)[1] not in ids_can, paso.source


# ── 4 ────────────────────────────────────────────────────────────────────────
def test_todo_id_manual_tiene_plantilla():
    for probes in ({}, {p: True for p in fr.PROBE_IDS}, {p: False for p in fr.PROBE_IDS}):
        for deploys in (True, False):
            hb.build_steps(_frontera(probes, deploys))     # no lanza
    faltantes = [r.action.id for r in fr.manual_actions(_frontera({}, True))
                 if r.action.id not in hb._STEP_TEMPLATES]
    assert faltantes == []


def test_accion_manual_sin_plantilla_rompe_ruidoso():
    fake = fr.CapabilityAction(id="inventada", label="X", verdict=fr.CANNOT, reason="y")
    with pytest.raises(hb.HandoffError) as exc:
        hb.build_steps([fr.ResolvedAction(fake, fr.CANNOT, "")])
    assert "inventada" in str(exc.value)


# ── 5 ────────────────────────────────────────────────────────────────────────
def test_pasos_numerados_sin_huecos():
    pasos = hb.build_steps(_frontera({}, True))
    assert [s.n for s in pasos] == list(range(1, len(pasos) + 1))


# ── 6 ────────────────────────────────────────────────────────────────────────
def test_bundle_sin_246_247_251_igual_se_arma(monkeypatch):
    """KPI-5 — la ausencia se FUERZA, no se asume.

    Los 3 modulos SI existen en este arbol (planes 246/247/251 implementados), asi que
    un test que solo confiara en su ausencia probaria la rama equivocada.
    """
    _forzar_ausencia(monkeypatch)
    inputs = hb.collect_inputs({}, pipeline_name="X", provider="ado",
                               yaml_files={"a.yml": "x: 1\n"})
    assert list(inputs.degraded) == sorted(_MODULOS_HERMANOS)
    files = hb.build_files(inputs, _frontera({}, True))
    assert "README.md" in files and "MANIFEST.json" in files
    manifest = json.loads(files["MANIFEST.json"])
    assert manifest["degraded"] == sorted(_MODULOS_HERMANOS)


# ── 7 ────────────────────────────────────────────────────────────────────────
def test_bundle_con_251_presente_no_degrada():
    """La otra mitad: sin este test, KPI-5 solo prueba una de las dos ramas."""
    inputs = hb.collect_inputs({"yaml_text": "variables:\n  REGION: 'us-east'\n"},
                               pipeline_name="X", provider="ado",
                               yaml_files={"a.yml": "x: 1\n"})
    assert "pipeline_environments" not in inputs.degraded
    assert "pipeline_inventory" not in inputs.degraded
    assert "pipeline_profiler" not in inputs.degraded


# ── 8 ────────────────────────────────────────────────────────────────────────
def test_modulo_que_revienta_al_importar_degrada_no_tumba(monkeypatch):
    """`except Exception`, no `except ImportError`: un modulo que exista pero reviente
    al importarse tiene que DEGRADAR el paquete, no tumbarlo."""
    class _Explota(types.ModuleType):
        def __getattr__(self, item):
            raise RuntimeError("boom al usar el modulo")

    import services

    falso = _Explota("services.pipeline_environments")
    monkeypatch.setitem(sys.modules, "services.pipeline_environments", falso)
    monkeypatch.setattr(services, "pipeline_environments", falso, raising=False)
    inputs = hb.collect_inputs({}, pipeline_name="X", provider="ado",
                               yaml_files={"a.yml": "x: 1\n"})
    assert "pipeline_environments" in inputs.degraded
    files = hb.build_files(inputs, _frontera({}, True))
    assert "README.md" in files


# ── 9 ────────────────────────────────────────────────────────────────────────
def test_format_hint_con_connection_string_falla_temprano_y_preciso():
    with pytest.raises(hb.HandoffSecretError) as exc:
        hb.HandoffVariable(name="DB_CONN", where="w",
                           format_hint="Server=x;Database=y;Password=abcd", secret=False)
    mensaje = str(exc.value)
    assert "format_hint" in mensaje
    assert "DB_CONN" in mensaje


# ── 10 ───────────────────────────────────────────────────────────────────────
def test_degraded_aparece_en_el_readme(monkeypatch):
    _forzar_ausencia(monkeypatch)
    inputs = hb.collect_inputs({}, pipeline_name="X", provider="ado",
                               yaml_files={"a.yml": "x: 1\n"})
    readme = hb.build_files(inputs, _frontera({}, True))["README.md"]
    assert hb.DEGRADED_CONSEQUENCE["pipeline_environments"] in readme
    assert "Nota honesta" in readme


# ── 11 ───────────────────────────────────────────────────────────────────────
def test_readme_tiene_las_8_secciones():
    readme = hb.build_files(_inputs(), _frontera({}, True))["README.md"]
    esperados = [
        "## 1. Qué hizo Stacky por vos",
        "## 2. Qué te toca a vos, y por qué",
        "## 3. Prerequisitos",
        "## 4. Variables a completar",
        "## 5. Pasos",
        "## 6. Validación final",
        "## 7. Si algo sale mal",
        "## 8. Anexo — contenido del paquete",
    ]
    posiciones = [readme.find(e) for e in esperados]
    assert all(p >= 0 for p in posiciones), [e for e, p in zip(esperados, posiciones) if p < 0]
    assert posiciones == sorted(posiciones), "las secciones tienen que ir en orden"


# ── 12 ───────────────────────────────────────────────────────────────────────
def test_readme_no_tiene_placeholders_sin_sustituir():
    """Se asserta sobre los placeholders de ESTA plantilla, no sobre cualquier `{`:
    un format_hint de GitLab como ${CI_COMMIT_SHA} o un bloque @{...} de PowerShell son
    llaves legitimas del operador."""
    readme = hb.build_files(_inputs(), _frontera({}, True))["README.md"]
    assert re.findall(r"\{[a-z_]+\}", readme) == []


# ── 13 ───────────────────────────────────────────────────────────────────────
def test_manifest_no_tiene_timestamp():
    files = hb.build_files(_inputs(), _frontera({}, True))
    manifest = json.loads(files["MANIFEST.json"])
    assert "generated_at" not in manifest
    for clave in manifest:
        assert not re.search(r"(_at|timestamp|date)$", clave), clave


# ── 14 ───────────────────────────────────────────────────────────────────────
def test_bundle_id_estable():
    """KPI-1, mitad pura: el orden de insercion NO afecta."""
    files = {"b.yml": "1", "a.yml": "2", "c.ps1": "3"}
    assert hb.compute_bundle_id(files) == hb.compute_bundle_id(
        dict(reversed(list(files.items()))))
    assert len(hb.compute_bundle_id(files)) == hb.BUNDLE_ID_LEN


# ── 15 ───────────────────────────────────────────────────────────────────────
def test_bundle_id_no_es_circular():
    files = hb.build_files(_inputs(), _frontera({}, True))
    manifest = json.loads(files["MANIFEST.json"])
    assert re.match(r"^[0-9a-f]{16}$", manifest["bundle_id"])
    # el id se calcula sobre el mapa SIN MANIFEST.json ni README.md
    base = {k: v for k, v in files.items() if k not in ("MANIFEST.json", "README.md")}
    assert hb.compute_bundle_id(base) == manifest["bundle_id"]


# ── 16 ───────────────────────────────────────────────────────────────────────
def test_vocabulario_espeja_al_209():
    from services.validation_playbook import ValidationStep

    del_209 = {f.name for f in dataclasses.fields(ValidationStep)}
    del_252 = {f.name for f in dataclasses.fields(hb.HandoffStep)}
    assert del_209 <= del_252, del_209 - del_252


# ── 17 ───────────────────────────────────────────────────────────────────────
def test_ningun_paso_del_readme_queda_sin_como_saber_si_salio_bien():
    """KPI-4 end to end: cada paso del README trae su verificacion."""
    files = hb.build_files(_inputs(), _frontera({}, True))
    manifest = json.loads(files["MANIFEST.json"])
    assert manifest["steps"], "con probes vacias tiene que haber trabajo manual"
    for s in manifest["steps"]:
        assert s["expected_result"].strip()
        assert s["on_failure"].strip()
        assert s["command"].strip()
    readme = files["README.md"]
    assert readme.count("**Cómo sabés que salió bien:**") == len(manifest["steps"])
