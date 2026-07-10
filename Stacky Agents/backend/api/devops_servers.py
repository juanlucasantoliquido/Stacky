"""api/devops_servers.py — Plan 91: registro de servidores DevOps.

url_prefix="/devops/servers" → rutas finales /api/devops/servers/... (namespacing
§3.12 del plan 87). Guard per-request 404 si STACKY_DEVOPS_SERVERS_ENABLED=OFF
(mismo patrón api/devops.py:28-29). El password entra SOLO por POST/PUT (write-only),
JAMÁS sale en respuestas ni logs (§3.1).
"""
import io
import subprocess
import sys
import zipfile
from pathlib import Path

from flask import Blueprint, jsonify, request, abort, send_file

import config as _config
from services import server_registry

bp = Blueprint("devops_servers", __name__, url_prefix="/devops/servers")


def _guard():
    if not getattr(_config.config, "STACKY_DEVOPS_SERVERS_ENABLED", False):
        abort(404)
    # §3.12 local (C5): métodos mutantes exigen JSON — bloquea form POST cross-origin
    # (un content-type application/json cross-origin fuerza preflight CORS).
    if request.method in ("POST", "PUT", "DELETE") and not request.is_json:
        abort(400, description="Content-Type application/json requerido")


def _apply_password(alias: str, password) -> tuple[bool, tuple]:
    """Devuelve (ok, error_response). error_response es (json, code) si 503."""
    if not password:
        return True, ()
    if not server_registry.keyring_available():
        return False, (jsonify({
            "error": (
                "keyring no disponible: instale keyring==25.6.0; el password NO se "
                "guardó (nunca se persiste en texto plano)."
            )
        }), 503)
    server_registry.set_password(alias, password)
    return True, ()


@bp.get("")
def list_route():
    _guard()
    return jsonify({
        "servers": server_registry.list_servers(),
        "keyring_available": server_registry.keyring_available(),
    })


@bp.post("")
def create_route():
    _guard()
    body = request.get_json(silent=True) or {}
    try:
        server = server_registry.upsert_server(
            alias=(body.get("alias") or "").strip(),
            host=(body.get("host") or "").strip(),
            domain=body.get("domain") or "",
            username=(body.get("username") or "").strip(),
            notes=body.get("notes") or "",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    ok, err = _apply_password(server["alias"], body.get("password"))
    if not ok:
        # el servidor SÍ quedó guardado sin password (§3.1)
        server = server_registry.get_server(server["alias"])
        return err
    server = server_registry.get_server(server["alias"])
    server["has_password"] = server_registry.has_password(server["alias"])
    return jsonify(server), 201


@bp.put("/<alias>")
def update_route(alias):
    _guard()
    body = request.get_json(silent=True) or {}
    if body.get("alias") and body["alias"] != alias:
        return jsonify({"error": "el alias de la URL y el del body no coinciden"}), 400
    if server_registry.get_server(alias) is None:
        return jsonify({"error": f"Servidor '{alias}' no existe."}), 404
    try:
        server_registry.upsert_server(
            alias=alias,
            host=(body.get("host") or "").strip(),
            domain=body.get("domain") or "",
            username=(body.get("username") or "").strip(),
            notes=body.get("notes") or "",
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    # Semántica del campo password (C6): AUSENTE/"" = conservar; null explícito = borrar;
    # string no vacío = reemplazar.
    if "password" in body and body["password"] is None:
        server_registry.clear_password(alias)
    elif body.get("password"):
        ok, err = _apply_password(alias, body["password"])
        if not ok:
            return err
    server = server_registry.get_server(alias)
    server["has_password"] = server_registry.has_password(alias)
    return jsonify(server), 200


@bp.delete("/<alias>")
def delete_route(alias):
    _guard()
    if not server_registry.delete_server(alias):
        return jsonify({"error": f"Servidor '{alias}' no existe."}), 404
    return jsonify({"ok": True}), 200


@bp.post("/<alias>/test")
def test_route(alias):
    _guard()
    server = server_registry.get_server(alias)
    if server is None:
        return jsonify({"error": f"Servidor '{alias}' no existe."}), 404
    ok, detail = server_registry.test_connectivity(server["host"])
    return jsonify({"ok": ok, "detail": detail}), 200


@bp.post("/<alias>/rdp")
def rdp_route(alias):
    """HITL §3.2: SIEMPRE un click explícito del operador; nada se conecta solo.
    §3.9: cmdkey/mstsc corren en el HOST del backend — si el backend corriera en otra
    máquina, el mstsc se abre allá. Aceptado: Stacky es mono-operador y corre local.
    """
    _guard()
    if sys.platform != "win32":
        return jsonify({"error": "RDP solo disponible en Windows (host del backend)."}), 501
    srv = server_registry.get_server(alias)
    if srv is None:
        return jsonify({"error": f"Servidor '{alias}' no existe."}), 404
    cred = server_registry.get_credential(alias)
    if cred is None:
        return jsonify({
            "error": (
                f"'{alias}' no tiene password guardada (o keyring no disponible). "
                "Editá el servidor y cargala."
            )
        }), 409
    username, domain, password = cred
    user_arg = f"{domain}\\{username}" if domain else username
    # lista de args, SIN shell, SIN log del comando (contiene el password) — §3.1
    # C1: TimeoutExpired/OSError incluyen el COMANDO (con /pass:) en su mensaje —
    # JAMÁS dejar propagar la excepción (terminaría en logs/traceback de Flask).
    try:
        rc = subprocess.run(
            ["cmdkey", f"/generic:TERMSRV/{srv['host']}", f"/user:{user_arg}", f"/pass:{password}"],
            capture_output=True, timeout=15,
        )
    except Exception:  # noqa: BLE001 — genérico A PROPÓSITO (C1): la excepción contiene el password
        return jsonify({"error": "cmdkey falló (timeout o error de ejecución) al registrar la credencial TERMSRV."}), 502
    if rc.returncode != 0:
        return jsonify({"error": "cmdkey falló al registrar la credencial TERMSRV."}), 502
    subprocess.Popen(  # detached: NO bloquea el request
        ["mstsc", f"/v:{srv['host']}"],
        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    server_registry.touch_last_connected(alias)  # [ADICIÓN ARQUITECTO] trazabilidad HITL
    return jsonify({"ok": True, "detail": f"mstsc lanzado hacia {srv['host']}."})


@bp.get("/download-setup")
def download_setup_route():
    """Descarga un ZIP con los scripts Enable-WinRM.ps1 y Enable-WinRM.bat para
    configurar WinRM en un servidor (habilitar listener 5985 + firewall). Uso:
    1. Descargar desde el botón del panel DevOps.
    2. Extraer el ZIP.
    3. Ejecutar Enable-WinRM.bat en el servidor (como admin).
    """
    _guard()

    from runtime_paths import app_root

    # Ubicar los scripts en app_root (root del deploy: donde está backend/, frontend/, etc.)
    # En deploy congelado: C:\...\DeployStackyAgents\
    # En desarrollo: N:\...\Stacky Agents\backend\...\
    app_dir = app_root()
    ps_script = app_dir / "Enable-WinRM.ps1"
    bat_script = app_dir / "Enable-WinRM.bat"

    # Si no están en app_root (desarrollo), probar en deployment/release_assets
    if not ps_script.exists():
        ps_script = Path(__file__).parents[2] / "deployment" / "release_assets" / "Enable-WinRM.ps1"
    if not bat_script.exists():
        bat_script = Path(__file__).parents[2] / "deployment" / "release_assets" / "Enable-WinRM.bat"

    if not ps_script.exists() or not bat_script.exists():
        return jsonify({
            "error": "Scripts no encontrados. Verifica que Enable-WinRM.ps1 y Enable-WinRM.bat existan en el deploy."
        }), 404

    # Crear ZIP en memoria
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(ps_script, arcname="Enable-WinRM.ps1")
        zf.write(bat_script, arcname="Enable-WinRM.bat")
    zip_buffer.seek(0)

    return send_file(
        zip_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="Enable-WinRM.zip"
    ))
