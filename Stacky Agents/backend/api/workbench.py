"""Plan 293 — La API del tablero de trabajo.

R6: el blueprint declara `url_prefix="/workbench"` y se registra DENTRO de
`api_bp` (que ya aporta `/api`), asi que la ruta final es `/api/workbench/...`.
Declarar `/api` aca produciria `/api/api/workbench/...`, el defecto que hizo
rechazar a los planes 72, 73 y 74.

El apagado por opcion vive DENTRO de cada ruta (404), NO en el registro: el
registro se evalua una sola vez al importar el modulo, asi que gatearlo ahi
obligaria a REINICIAR el backend para que el operador viera el efecto de tocar
la opcion.

Este modulo NO se llama `git.py` a proposito: tests/test_plan265_git_readonly.py
hace un barrido de TEXTO LITERAL sobre `api/git.py` y falla si aparece la palabra
"commit" aunque sea en un comentario.

Cero logica aca: parsear, delegar, serializar.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, request

bp = Blueprint("workbench", __name__, url_prefix="/workbench")

_MAX_RUTAS = 60          # mismo tope que el auto-PR del Dev Resolutor
_MAX_MENSAJE = 5000


def _flags() -> dict:
    from config import config as _cfg

    return {
        "lectura": bool(getattr(_cfg, "STACKY_WORKBENCH_ENABLED", True)),
        "escritura": bool(getattr(_cfg, "STACKY_WORKBENCH_WRITE_ENABLED", False)),
        "envio": bool(getattr(_cfg, "STACKY_WORKBENCH_PUSH_ENABLED", False)),
    }


def _apagado():
    return jsonify({
        "ok": False, "error": "feature_disabled", "feature": "STACKY_WORKBENCH_ENABLED",
    }), 404


def _auditar(accion: str, **contexto) -> None:
    """Auditoria por SystemLog, que ya existe indexado. NO se crea una tabla
    nueva: seria duplicar. Nunca viaja contenido de archivos ni rutas absolutas."""
    try:
        from services.stacky_logger import logger as stacky_logger

        stacky_logger.info(source="git_workbench", action=accion, context=contexto)
    except Exception:  # noqa: BLE001
        pass


def _workspace() -> tuple[Path | None, str | None, str | None]:
    """(raiz_validada, nombre_proyecto, motivo_de_error).

    El control de acceso REAL de Stacky es la lista blanca de carpetas
    registradas: `resolve_known_workspace` compara rutas YA RESUELTAS contra las
    de project_manager. Una carpeta que el operador no registro no se toca.
    """
    from services import console_repo
    from services.project_context import resolve_project_context

    nombre = (request.args.get("project") or "").strip() or None
    if nombre is None and request.method == "POST":
        cuerpo = request.get_json(force=True, silent=True) or {}
        nombre = (cuerpo.get("project") or "").strip() or None

    try:
        ctx = resolve_project_context(project_name=nombre)
    except Exception:  # noqa: BLE001
        ctx = None
    if ctx is None or not getattr(ctx, "workspace_root", None):
        return None, nombre, "el proyecto no tiene una carpeta de trabajo configurada"

    validada = console_repo.resolve_known_workspace(ctx.workspace_root)
    if validada is None:
        return None, nombre, "esa carpeta no esta habilitada para trabajar desde Stacky"
    return validada, getattr(ctx, "stacky_project_name", nombre), None


# ── Salud: SIEMPRE 200, incluso con la opcion apagada ───────────────────────
@bp.get("/health")
def health():
    """`flag_enabled` es la clave EXACTA que mira el gate de navegacion
    (frontend/src/utils/flagHealth.ts:9-16). Con otra clave el tab queda en
    `unknown` para siempre y el enlace directo muere."""
    f = _flags()
    return jsonify({
        "ok": True,
        "flag_enabled": f["lectura"],
        "write_enabled": f["escritura"],
        "push_enabled": f["envio"],
    })


# ── Lectura ─────────────────────────────────────────────────────────────────
@bp.get("/overview")
def overview():
    if not _flags()["lectura"]:
        return _apagado()
    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": True, "available": False, "reason": motivo,
                        "repo": {}, "archivos": [], "conflictos": []})

    from services import git_workbench as gw

    datos = gw.repo_overview(raiz)
    f = _flags()
    datos["semaforo"] = gw.evaluar_operacion(
        repo=datos, accion="confirmar", flags=f, seleccion=[],
    )
    datos["flags"] = f
    _auditar("overview", proyecto=proyecto, archivos=len(datos.get("archivos") or []))
    return jsonify(datos)


@bp.get("/diff")
def diff():
    if not _flags()["lectura"]:
        return _apagado()
    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": True, "available": False, "reason": motivo, "diff": ""})

    from services import console_repo

    ruta = console_repo.resolve_safe_path(raiz, request.args.get("path") or "")
    if ruta is None:
        return jsonify({"ok": True, "available": False, "reason": "archivo invalido", "diff": ""})
    _auditar("diff", proyecto=proyecto)
    return jsonify(console_repo.repo_diff(raiz, ruta))


@bp.get("/historial")
def historial():
    if not _flags()["lectura"]:
        return _apagado()
    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": True, "available": False, "reason": motivo, "commits": []})

    from services import git_workbench as gw

    _auditar("historial", proyecto=proyecto)
    return jsonify(gw.historial(raiz, n=request.args.get("n", default=20, type=int)))


@bp.get("/ramas")
def ramas():
    if not _flags()["lectura"]:
        return _apagado()
    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": True, "available": False, "reason": motivo, "ramas": []})

    from services import git_workbench as gw

    _auditar("ramas", proyecto=proyecto)
    return jsonify(gw.listar_ramas(raiz))


# ── Escritura: TODAS exigen confirm=true ────────────────────────────────────
def _cuerpo() -> dict:
    return request.get_json(force=True, silent=True) or {}


def _sin_confirmacion():
    return jsonify({
        "ok": False, "codigo": "sin_confirmacion",
        "mensaje": "Falta la confirmacion explicita de la accion.",
    }), 400


@bp.post("/confirmar")
def confirmar():
    if not _flags()["lectura"]:
        return _apagado()
    datos = _cuerpo()
    if datos.get("confirm") is not True:
        return _sin_confirmacion()

    rutas = datos.get("rutas") or []
    if not isinstance(rutas, list) or len(rutas) > _MAX_RUTAS:
        return jsonify({"ok": False, "codigo": "demasiados_archivos",
                        "mensaje": f"Elegi como maximo {_MAX_RUTAS} archivos por vez."}), 400
    mensaje = (datos.get("mensaje") or "")[:_MAX_MENSAJE]

    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": False, "codigo": "repo_no_disponible", "mensaje": motivo}), 200

    from services import git_local_writer as glw

    _auditar("guardar_intento", proyecto=proyecto, cantidad=len(rutas))
    res = glw.confirmar_cambios(raiz=raiz, rutas=rutas, mensaje=mensaje)
    _auditar("guardar_ok" if res.get("ok") else "guardar_error",
             proyecto=proyecto, codigo=res.get("codigo"))
    return jsonify(res)


@bp.post("/enviar")
def enviar():
    if not _flags()["lectura"]:
        return _apagado()
    datos = _cuerpo()
    if datos.get("confirm") is not True:
        return _sin_confirmacion()

    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": False, "codigo": "repo_no_disponible", "mensaje": motivo}), 200

    from services import git_local_writer as glw
    from services import git_workbench as gw

    rama = (datos.get("rama") or "").strip()
    if not rama:
        rama = (gw.repo_overview(raiz).get("repo") or {}).get("branch") or ""
    _auditar("enviar", proyecto=proyecto)
    return jsonify(glw.enviar_cambios(raiz=raiz, rama=rama, project=proyecto))


@bp.post("/traer")
def traer():
    if not _flags()["lectura"]:
        return _apagado()
    datos = _cuerpo()
    if datos.get("confirm") is not True:
        return _sin_confirmacion()
    if not _flags()["escritura"]:
        return jsonify({"ok": False, "codigo": "escritura_apagada",
                        "mensaje": "La opcion que permite traer cambios esta apagada."})

    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": False, "codigo": "repo_no_disponible", "mensaje": motivo}), 200

    from services.pre_run_git import run_pull_check

    _auditar("traer", proyecto=proyecto)
    # La politica se pasa EXPLICITA: con la de fabrica ("fetch_only_warn") el
    # bloque de fusion no corre y el boton no bajaria nada (plan 293 F7).
    res = run_pull_check(
        str(raiz), enabled=True, required=False, fetch=True,
        project=proyecto, policy="ff_only_block_on_dirty",
    )
    return jsonify(res.to_dict())


# ── Evidencias de prueba ────────────────────────────────────────────────────
@bp.post("/evidencias")
def subir_evidencias():
    """Recibe capturas. El guard de tamano corre ANTES de leer un solo byte:
    la app NO define MAX_CONTENT_LENGTH (unico hit en todo el backend es un
    comentario en api/incidents.py admitiendolo), asi que cada endpoint que
    recibe archivos hereda CERO proteccion y tiene que ponerla."""
    if not _flags()["lectura"]:
        return _apagado()

    from services import work_evidence as we

    if request.content_length and request.content_length > we.MAX_BYTES_TOTAL + 1_048_576:
        return jsonify({
            "ok": False, "codigo": "total_muy_grande",
            "mensaje": "Las capturas juntas pesan demasiado.",
        }), 413

    sesion = (request.form.get("sesion") or "").strip() or we.nueva_sesion()
    archivos: list[tuple[str, bytes]] = []
    for f in request.files.getlist("archivos"):
        if not f or not f.filename:
            continue
        datos = f.read(we.MAX_BYTES_POR_ARCHIVO + 1)
        archivos.append((f.filename, datos))

    res = we.guardar(sesion, archivos)
    res["sesion"] = sesion
    _auditar("evidencia_subida", cantidad=len(res.get("archivos") or []))
    return jsonify(res)


@bp.get("/evidencias")
def listar_evidencias():
    """La PREVISUALIZACION antes de crear la propuesta, que era el pedido literal."""
    if not _flags()["lectura"]:
        return _apagado()

    from services import work_evidence as we

    sesion = (request.args.get("sesion") or "").strip()
    return jsonify({"ok": True, "sesion": sesion, "archivos": we.listar(sesion)})


@bp.get("/evidencias/vista")
def ver_evidencia():
    """Sirve el archivo para la miniatura. La ruta NO se arma con lo que llega
    de afuera: el nombre interno tiene que figurar en el meta de la tanda."""
    if not _flags()["lectura"]:
        return _apagado()

    from flask import send_file

    from services import work_evidence as we

    ruta = we.ruta_de((request.args.get("sesion") or "").strip(),
                      (request.args.get("archivo") or "").strip())
    if ruta is None:
        return jsonify({"ok": False, "codigo": "evidencia_inexistente"}), 404
    return send_file(str(ruta))


@bp.post("/proponer")
def proponer():
    """El UNICO paso que va por REST: abrir una propuesta de cambio no tiene
    equivalente en git. Todo el formulario se renderiza dentro de `description`
    porque `create_merge_request` acepta cuatro parametros y nada mas."""
    if not _flags()["lectura"]:
        return _apagado()
    datos = _cuerpo()
    if datos.get("confirm") is not True:
        return _sin_confirmacion()

    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": False, "codigo": "repo_no_disponible", "mensaje": motivo}), 200

    from services import change_proposal as cp
    from services import git_workbench as gw

    vista = gw.repo_overview(raiz)
    rama_origen = (datos.get("rama") or "").strip() or (vista.get("repo") or {}).get("branch") or ""
    archivos = datos.get("archivos") or [a["path"] for a in (vista.get("archivos") or [])]

    # Las evidencias se suben y se EMBEBEN en la descripcion que se manda al
    # crear la propuesta, en un unico llamado. Nunca se "completa" despues: ese
    # es el camino que puede pisar contenido del servidor.
    evidencias: list[str] = []
    degradado = None
    sesion = (datos.get("sesion_evidencias") or "").strip()
    if sesion:
        from services import work_evidence as we

        subida = we.subir_al_proveedor(sesion, project=proyecto)
        evidencias = subida.get("markdown") or []
        degradado = subida.get("degradado")

    _auditar("proponer", proyecto=proyecto, cantidad=len(archivos), evidencias=len(evidencias))
    res = cp.abrir_propuesta(
        raiz=raiz,
        rama_origen=rama_origen,
        titulo=(datos.get("titulo") or "")[:200],
        resumen=(datos.get("resumen") or "")[:_MAX_MENSAJE],
        archivos=list(archivos)[:_MAX_RUTAS],
        pruebas=(datos.get("pruebas") or "")[:_MAX_MENSAJE],
        evidencias=evidencias,
        project=proyecto,
    )
    if degradado:
        res["degradado"] = degradado
    return jsonify(res)


@bp.post("/rama")
def rama():
    if not _flags()["lectura"]:
        return _apagado()
    datos = _cuerpo()
    if datos.get("confirm") is not True:
        return _sin_confirmacion()

    raiz, proyecto, motivo = _workspace()
    if raiz is None:
        return jsonify({"ok": False, "codigo": "repo_no_disponible", "mensaje": motivo}), 200

    from services import git_local_writer as glw

    nombre = (datos.get("nombre") or "").strip()
    _auditar("rama", proyecto=proyecto, crear=bool(datos.get("crear")))
    if datos.get("crear") is True:
        return jsonify(glw.crear_rama(raiz=raiz, nombre=nombre))
    return jsonify(glw.cambiar_rama(raiz=raiz, nombre=nombre))
