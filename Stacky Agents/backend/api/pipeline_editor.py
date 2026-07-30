"""api/pipeline_editor.py — Blueprint de edicion quirurgica de pipelines. Plan 250 F3/F5.

url_prefix="/pipeline-editor" -> ruta final /api/pipeline-editor/...
Guard de flag PER-REQUEST (abort(404)), nunca gateado en el registro del blueprint.

DOS superficies con DOS flags, a proposito:
  - analisis (/plan, /verbs, /interpret): default ON. NO escribe en ningun lado.
  - escritura (/commit): flag PROPIA default OFF. Es la unica ruta que empuja un
    commit al Azure DevOps REAL del operador (ado_provider.commit_file hace un push
    de verdad por la Git Pushes API desde el plan 95 F1.a). Excepcion dura (2).
"""
from __future__ import annotations

import hashlib
import json

from flask import Blueprint, abort, jsonify, request

from services.pipeline_diff import review_patch
from services.pipeline_patcher import (
    EDIT_VERBS,
    EditIntent,
    apply_ops,
    build_anchor_index,
    plan_edit,
    validate_intent_dict,
)

bp = Blueprint("pipeline_editor", __name__, url_prefix="/pipeline-editor")

PROMPT_TYPE = "pipeline_edit_intent_v1"
MAX_LLM_CALLS_PER_REQUEST = 1   # C6: constante del modulo, NO flag. Sin reintentos, nunca.

# El puerto RepoWriter es SOLO-ESCRITURA (repo_writer.py:27
# REPO_WRITER_METHODS = ("commit_file",)): no hay `get_file`. Por lo tanto Stacky NO
# PUEDE saber si el archivo cambio en el repo desde que mostro el diff. Se declara;
# jamas se reporta como validado.
STALE_CHECK = "no_verificable"
STALE_CHECK_MOTIVO = (
    "el puerto RepoWriter no expone lectura; si el archivo cambio en el repo desde que "
    "viste el diff, Stacky no puede saberlo — el push contra `old_object_id` lo "
    "rechazaria ADO"
)

_DEFAULT_PROFILE = "dotnet_framework"


def _cfg():
    import config as _config  # noqa: PLC0415
    # GOTCHA dura: la INSTANCIA (_config.config), no el modulo. `getattr` del modulo
    # devuelve el default y mata el branch OFF (el test flag-off pasaria en falso).
    return _config.config


def _guard():
    if not getattr(_cfg(), "STACKY_PIPELINE_NL_EDIT_ENABLED", False):
        abort(404)


def _guard_commit():
    # candado 0 — flag propia. `FlagSpec.requires` es INFORMATIVO para la UI y ningun
    # runner lo evalua (harness_flags.py:30-32): hay que chequear las dos por cuenta propia.
    _guard()
    if not getattr(_cfg(), "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED", False):
        abort(404)


def _sha256(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


def _intent_de(body: dict):
    crudo = body.get("intent")
    if not isinstance(crudo, dict):
        return None, ("falta `intent` (objeto)",)
    perfil = str(body.get("profile") or _DEFAULT_PROFILE)
    return validate_intent_dict(crudo, profile=perfil)


def _serializar_finding(f) -> dict:
    return {
        "code": getattr(f, "code", ""),
        "severity": getattr(f, "severity", ""),
        "message": getattr(f, "message", ""),
        "location": getattr(f, "location", None),
        "line": getattr(f, "line", None),
        "node": getattr(f, "node", None),
    }


def _serializar_review(review) -> dict:
    return {
        "ok": review.ok,
        "summary": review.summary,
        "unsupported": list(review.unsupported),
        "preservation": {
            "ok": review.preservation.ok,
            "comments_before": review.preservation.comments_before,
            "comments_after": review.preservation.comments_after,
            "unsupported_lost": list(review.preservation.unsupported_lost),
            "lines_untouched": review.preservation.lines_untouched,
            "lines_total_before": review.preservation.lines_total_before,
            "detail": review.preservation.detail,
        },
        "gates": [{
            "gate": g.gate,
            "passed": g.passed,
            "new_errors": [_serializar_finding(f) for f in g.new_errors],
            "new_warnings": [_serializar_finding(f) for f in g.new_warnings],
            "resolved": [_serializar_finding(f) for f in g.resolved],
            "skipped_reason": g.skipped_reason,
        } for g in review.gates],
    }


def _serializar_hunk(h) -> dict:
    return {"start_line": h.start_line, "end_line": h.end_line,
            "before": list(h.before), "after": list(h.after), "reason": h.reason}


def _compilar(yaml_text: str, intent: EditIntent, perfil: str, repo_root):
    """(after, hunks, review, errores). Se usa IGUAL en /plan y en /commit: el servidor
    recompila siempre desde el intent y NUNCA acepta el YAML final del cliente."""
    ops, errores = plan_edit(yaml_text, intent, profile=perfil)
    if errores:
        return None, (), None, tuple(errores)
    res = apply_ops(yaml_text, ops)
    if not res.ok:
        return None, (), None, tuple(res.errors)
    # Plan 260 (v3, C8) — la flag se lee ACA (el llamador), nunca en
    # pipeline_diff.py (que declara "PURO salvo repo_root" y no importa config).
    review = review_patch(
        yaml_text, res.text, res.hunks, profile=perfil, repo_root=repo_root,
        verb=intent.verb,
        secret_gate=getattr(_cfg(), "STACKY_PIPELINE_SECRET_COMMIT_GATE_ENABLED", False))
    return res.text, res.hunks, review, ()


# ── /verbs ───────────────────────────────────────────────────────────────────

@bp.get("/verbs")
def verbs_route():
    _guard()
    from services.cicd_task_catalog import TASK_CATALOG  # noqa: PLC0415

    perfil = str(request.args.get("profile") or _DEFAULT_PROFILE)
    catalogo = {ref: list(spec.input_names())
                for ref, spec in (TASK_CATALOG.get(perfil) or {}).items()}
    return jsonify({
        "verbs": list(EDIT_VERBS),
        "catalog": catalogo,
        "profile": perfil,
        # El plan 246 (descubrimiento) y el 248 (recomendaciones) son opcionales: si no
        # estan, la UI no muestra esas vias y NO hay error.
        "discovery_available": _modulo_disponible("services.pipeline_inventory"),
        "recommendations_available": _modulo_disponible("services.pipeline_recommendations"),
        "commit_enabled": bool(getattr(_cfg(), "STACKY_PIPELINE_NL_EDIT_COMMIT_ENABLED", False)),
    }), 200


def _modulo_disponible(nombre: str) -> bool:
    import importlib.util  # noqa: PLC0415
    try:
        return importlib.util.find_spec(nombre) is not None
    except (ImportError, ValueError):
        return False


# ── /plan ────────────────────────────────────────────────────────────────────

@bp.post("/plan")
def plan_route():
    _guard()
    body = request.get_json(silent=True) or {}
    yaml_text = body.get("yaml")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_requerido",
                        "detail": "envia `yaml` (string no vacio)"}), 400
    intent, errores = _intent_de(body)
    if intent is None:
        return jsonify({"error": "intent_invalido", "detail": list(errores)}), 400
    perfil = str(body.get("profile") or _DEFAULT_PROFILE)
    after, hunks, review, errores = _compilar(
        yaml_text, intent, perfil, body.get("repo_root"))
    if after is None:
        return jsonify({"error": "no_se_puede_planificar", "detail": list(errores)}), 400
    return jsonify({
        "ops": len(hunks),
        "hunks": [_serializar_hunk(h) for h in hunks],
        "review": _serializar_review(review),
        "yaml": after,               # SOLO para previsualizar: /commit lo recompila
        "before_sha256": _sha256(yaml_text),
        "after_sha256": _sha256(after),
    }), 200


# ── /commit — la UNICA ruta que escribe en un sistema real del operador ──────

@bp.post("/commit")
def commit_route():
    _guard_commit()                                     # candado 0
    body = request.get_json(silent=True) or {}

    # candado 1 — HITL, literal de pipeline_generator.py:59-60
    if body.get("confirm") is not True:
        return jsonify({"error": "confirm=True requerido (HITL)"}), 400

    yaml_text = body.get("yaml")
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_requerido"}), 400
    path = str(body.get("path") or "").strip()
    if not path:
        return jsonify({"error": "path_requerido",
                        "detail": "indica la ruta del archivo en el repo"}), 400
    project = body.get("project")

    # candado 2 — nunca sobre la rama por defecto
    branch = str(body.get("branch") or "").strip()
    if not branch:
        return jsonify({"error": "branch_requerido",
                        "detail": "el commit va SIEMPRE a una rama, nunca a la default"}), 400
    try:
        from services.ado_pipeline_definitions import _default_branch  # noqa: PLC0415
        default = _default_branch(None, project)
    except Exception as e:  # no poder saber cual es la default NO habilita a escribir
        return jsonify({"error": "rama_default_desconocida", "detail": str(e)}), 400
    if default and branch == default:
        return jsonify({"error": "rama_default_prohibida",
                        "detail": "'%s' es la rama por defecto del repo" % branch}), 400

    # candado 3 — auto-consistencia del `before` (el puerto no sabe leer: §2.8)
    before_sha = str(body.get("before_sha256") or "")
    if not before_sha or _sha256(yaml_text) != before_sha:
        return jsonify({
            "error": "before_incoherente",
            "detail": "el YAML original recibido no coincide con `before_sha256`",
            "stale_check": STALE_CHECK, "stale_check_reason": STALE_CHECK_MOTIVO}), 400

    intent, errores = _intent_de(body)
    if intent is None:
        return jsonify({"error": "intent_invalido", "detail": list(errores),
                        "stale_check": STALE_CHECK}), 400

    # candado 4 — el servidor RECOMPILA. Nunca acepta el YAML final del cliente.
    perfil = str(body.get("profile") or _DEFAULT_PROFILE)
    after, hunks, review, errores = _compilar(
        yaml_text, intent, perfil, body.get("repo_root"))
    if after is None:
        return jsonify({"error": "no_se_puede_planificar", "detail": list(errores),
                        "stale_check": STALE_CHECK}), 400
    aprobado = str(body.get("approved_after_sha256") or "")
    if aprobado and _sha256(after) != aprobado:
        return jsonify({
            "error": "diff_cambio",
            "detail": "el resultado recompilado no es el que aprobaste; revisa el diff nuevo",
            "hunks": [_serializar_hunk(h) for h in hunks],
            "yaml": after, "after_sha256": _sha256(after),
            "stale_check": STALE_CHECK}), 409

    # candado 5 — gates
    if not review.ok:
        return jsonify({
            "error": "gates_en_rojo",
            "review": _serializar_review(review),
            "hunks": [_serializar_hunk(h) for h in hunks],
            "stale_check": STALE_CHECK}), 422

    # candado 6 — get_repo_writer lanza RuntimeError si el provider no implementa el
    # puerto (repo_writer.py:37-41). Sin este try es un 500 mudo.
    try:
        from services.repo_writer import get_repo_writer  # noqa: PLC0415
        writer = get_repo_writer(project)
    except Exception as e:
        return jsonify({"error": "provider_sin_escritura", "detail": str(e),
                        "yaml": after, "stale_check": STALE_CHECK}), 400

    # candado 7 — recien aca se escribe de verdad
    message = str(body.get("message") or "").strip() or (
        "pipeline(%s): edicion asistida por Stacky (plan 250)" % path)
    try:
        from services.tracker_provider import TrackerApiError  # noqa: PLC0415
    except Exception:  # pragma: no cover - el modulo existe en este arbol
        TrackerApiError = Exception  # type: ignore
    try:
        resultado = writer.commit_file(path=path, content=after, branch=branch,
                                       message=message)
    except NotImplementedError as e:
        # candado 8 — degradacion honesta: NUNCA se presenta como "commiteado"
        return jsonify({"error": "escritura_no_soportada", "detail": str(e),
                        "yaml": after,
                        "hunks": [_serializar_hunk(h) for h in hunks],
                        "stale_check": STALE_CHECK}), 501
    except TrackerApiError as e:  # type: ignore[misc]
        return jsonify({"error": str(e), "kind": getattr(e, "kind", ""),
                        "stale_check": STALE_CHECK}), getattr(e, "status", 502)

    salida = dict(resultado or {})
    salida["stale_check"] = STALE_CHECK
    salida["stale_check_reason"] = STALE_CHECK_MOTIVO
    salida["review"] = _serializar_review(review)
    return jsonify(salida), 200


# ── /interpret — F5: el UNICO endpoint que gasta tokens ─────────────────────

def _prompt(texto: str, yaml_text: str, perfil: str) -> str:
    from services.cicd_task_catalog import TASK_CATALOG, extract_task_refs  # noqa: PLC0415

    indice, _errs = build_anchor_index(yaml_text)
    catalogo = {ref: list(spec.input_names())
                for ref, spec in (TASK_CATALOG.get(perfil) or {}).items()}
    # NO se manda el YAML completo: es mas chico, mas barato y no expone los
    # comentarios ni los valores del archivo al modelo.
    return (
        "Sos un traductor de pedidos a una estructura CERRADA. Devolve SOLO un JSON.\n"
        "Verbos permitidos (lista cerrada): %s\n"
        "Puntos direccionables de este pipeline: %s\n"
        "Tareas presentes: %s\n"
        "Catalogo cerrado de tareas del perfil '%s': %s\n"
        "Campos del JSON: verb, target_path, anchor_ref, position (before|after|end), "
        "task_ref, inputs (objeto), display_name, values (lista), notes (lista de "
        "supuestos que asumiste).\n"
        "NUNCA escribas YAML. NUNCA inventes una tarea fuera del catalogo. Si el pedido "
        "no alcanza para completar target_path o el verbo, devolve "
        '{\"questions\": [\"...\"]} nombrando el dato que falta.\n'
        "Pedido del operador: %s\n"
        % (", ".join(EDIT_VERBS), ", ".join(sorted(indice)),
           ", ".join(extract_task_refs(yaml_text) or ()), perfil,
           json.dumps(catalogo, ensure_ascii=False), texto)
    )


def _proyecto_activo() -> str:
    try:
        from project_manager import get_active_project  # noqa: PLC0415
        return str(get_active_project() or "default")
    except Exception:
        return "default"


def _modelo_para_intent() -> str:
    """Modelo del seam de LLM. Con LLM_BACKEND=mock (el default de tests) el valor
    no se usa para la red; se declara igual para que el costo quede atribuido."""
    try:
        return str(getattr(_cfg(), "PM_LLM_MODEL", "") or "mock-1.0")
    except Exception:
        return "mock-1.0"


def interpret_edit(text: str, *, yaml_text: str, profile: str, fixture_id=None) -> tuple:
    """(EditIntent|None, preguntas). UNA sola llamada a call_llm. Nunca lanza.

    CERO reintentos automaticos: si el JSON no valida, se le pregunta al operador. Con
    el humano mirando la pantalla, preguntarle cuesta 0 tokens y acierta mas que un
    bucle de auto-reparacion (leccion C10 del plan 243).
    """
    from services.pm import pm_llm_client  # noqa: PLC0415

    # El plan escribia `LLMCallSpec(prompt=...)`. El dataclass REAL
    # (pm_llm_client.py:90) exige project/agent_kind/prompt_type/model/system/user:
    # con `prompt=` es un TypeError. Se arma con los campos que existen.
    spec = pm_llm_client.LLMCallSpec(
        project=_proyecto_activo(),
        agent_kind="pipeline_edit",
        prompt_type=PROMPT_TYPE,
        model=_modelo_para_intent(),
        system=("Traducis pedidos en castellano a una estructura JSON cerrada. "
                "Nunca escribis YAML."),
        user=_prompt(text, yaml_text, profile),
        temperature=0.0,
        fixture_id=fixture_id,
        expect_json=True,
    )
    resultado = pm_llm_client.call_llm(spec)        # nunca lanza (pm_llm_client:281-283)
    if not getattr(resultado, "success", False):
        return None, ("no se pudo consultar al modelo: %s"
                      % (getattr(resultado, "error", "") or "sin detalle"),)
    datos = getattr(resultado, "parsed_json", None)
    if datos is None:
        crudo = getattr(resultado, "text", "") or ""
        try:
            datos = json.loads(crudo)
        except (ValueError, TypeError):
            return None, ("el modelo no devolvio un JSON interpretable",)
    if isinstance(datos, dict) and datos.get("questions"):
        return None, tuple(str(q) for q in datos["questions"])
    intent, errores = validate_intent_dict(datos, profile=profile)
    if intent is None:
        return None, tuple(errores)
    return intent, ()


def recommendation_to_intent(rec_id: str, yaml_text: str, *, profile: str,
                             provider: str = "ado"):
    """Puente con el plan 248: traduce una recomendacion OPT* a un EditIntent.

    Import BLANDO: si el modulo no esta, degrada con mensaje. NUNCA lanza ImportError.

    NOTA: el plan importaba `get_recommendation`, que NO existe. El simbolo real del
    248 es `check_recommendations(yaml_text, *, provider, mode)` (services/
    pipeline_recommendations.py:238), que devuelve `(findings, notes)`. Se cablea a ese.
    """
    try:
        from services.pipeline_recommendations import (  # noqa: PLC0415
            check_recommendations,
        )
    except ImportError:
        return None, ("el modulo de recomendaciones (plan 248) no esta instalado",)
    try:
        findings, _notas = check_recommendations(yaml_text, provider=provider)
    except Exception as e:
        return None, ("no se pudieron leer las recomendaciones: %s" % e,)
    elegida = next((f for f in findings if getattr(f, "code", "") == rec_id), None)
    if elegida is None:
        disponibles = sorted({getattr(f, "code", "") for f in findings})
        return None, ("esta pipeline no tiene la recomendacion '%s'%s"
                      % (rec_id,
                         (". Las que si tiene: %s" % ", ".join(disponibles))
                         if disponibles else ""),)
    # Ninguna de OPT001..OPT004 cae hoy en los 7 verbos cerrados (cachear, no
    # recompilar en tests, poner timeout, acotar el historial del checkout no son
    # add/remove/move de un `- task:`). Se dice, no se inventa un verbo.
    return None, ("'%s' se entiende pero todavia no tiene traduccion automatica a uno "
                  "de los %d verbos de edicion: %s"
                  % (rec_id, len(EDIT_VERBS), getattr(elegida, "message", "")),)


@bp.post("/interpret")
def interpret_route():
    _guard()
    body = request.get_json(silent=True) or {}
    texto = str(body.get("text") or "").strip()
    yaml_text = body.get("yaml")
    if not texto:
        return jsonify({"error": "text_requerido"}), 400
    if not isinstance(yaml_text, str) or not yaml_text.strip():
        return jsonify({"error": "yaml_requerido"}), 400
    perfil = str(body.get("profile") or _DEFAULT_PROFILE)
    intent, preguntas = interpret_edit(texto, yaml_text=yaml_text, profile=perfil,
                                       fixture_id=body.get("fixture_id"))
    if intent is None:
        return jsonify({"intent": None, "questions": list(preguntas)}), 200
    # NO devuelve `yaml` ni `hunks`: el diff exige el paso /plan aparte, que es donde
    # el operador confirma el intent que el modelo interpreto.
    return jsonify({
        "intent": {
            "verb": intent.verb, "target_path": intent.target_path,
            "anchor_ref": intent.anchor_ref, "position": intent.position,
            "task_ref": intent.task_ref, "inputs": dict(intent.inputs),
            "display_name": intent.display_name, "values": list(intent.values),
        },
        "notes": list(intent.notes),
        "questions": [],
    }), 200
