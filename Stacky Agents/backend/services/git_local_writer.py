"""Plan 293 F6 — El ESCRITOR local del tablero de trabajo.

Este modulo es el unico que modifica el arbol de trabajo del operador, y existe
separado de services/git_workbench.py (que solo lee) para que el camino de
lectura no pueda escribir ni por accidente.

EL RIESGO #1 DEL PLAN
---------------------
El tablero corre git sobre el repositorio REAL del operador. Ese arbol tiene
normalmente ~50 archivos sin confirmar de otras series y una sesion paralela viva
que `git worktree list` NO detecta. Un boton que ejecute `add -A` le roba el
trabajo al otro y lo publica.

La barrera NO es la buena intencion: es que `git commit -F <mensaje> -- <rutas>`
toma ESAS rutas del arbol de trabajo sin mirar el indice, asi que lo que la
sesion paralela haya dejado preparado no entra. El catalogo cerrado de
git_workbench._validar hace que un `commit` sin pathspec ni siquiera sea
expresable.

Este modulo NO puede vivir en api/git.py ni en services/console_repo.py:
tests/test_plan265_git_readonly.py:213-238 hace un barrido de TEXTO LITERAL sobre
esos dos archivos y falla si aparece la palabra "commit" aunque sea en un
comentario.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from config import config
from services import git_workbench as gw


def _fallo(codigo: str, mensaje: str, **extra) -> dict:
    return {"ok": False, "codigo": codigo, "mensaje": mensaje, **extra}


def _hay_index_lock(raiz: Path) -> bool:
    """Chequeo por SISTEMA DE ARCHIVOS, sin ejecutar git.

    Tiene que ser antes de cualquier subproceso: si el indice esta tomado por la
    sesion paralela, correr git igual seria competir por el mismo lockfile.
    """
    try:
        punto_git = raiz / ".git"
        if punto_git.is_dir():
            return (punto_git / "index.lock").exists()
        # Worktree enlazado: .git es un archivo que apunta al gitdir real.
        if punto_git.is_file():
            texto = punto_git.read_text(encoding="utf-8", errors="replace").strip()
            if texto.startswith("gitdir:"):
                destino = Path(texto.split(":", 1)[1].strip())
                if not destino.is_absolute():
                    destino = (raiz / destino).resolve()
                return (destino / "index.lock").exists()
    except OSError:
        return False
    return False


def _validar_rutas(raiz: Path, rutas: list[str]) -> tuple[list[str], str | None]:
    """Rutas relativas, dentro del repositorio, y NUNCA una carpeta.

    Una pathspec de carpeta es RECURSIVA: `commit -- backend` se lleva todo lo
    modificado debajo de backend, que es exactamente el robo de trabajo ajeno que
    esta fase existe para impedir. El usuario tilda ARCHIVOS, asi que solo
    archivos entran.
    """
    limpias: list[str] = []
    for cruda in rutas:
        if not cruda or not isinstance(cruda, str):
            return [], "ruta_invalida"
        if cruda.startswith("-") or cruda.startswith(":"):
            return [], "ruta_invalida"
        p = Path(cruda)
        if p.is_absolute() or ".." in p.parts:
            return [], "ruta_invalida"
        destino = raiz / p
        try:
            destino.resolve().relative_to(Path(raiz).resolve())
        except (ValueError, OSError):
            return [], "ruta_invalida"
        if destino.is_dir():
            return [], "ruta_es_carpeta"
        limpias.append(str(p).replace("\\", "/"))
    return limpias, None


def _sin_seguimiento(overview: dict, seleccion: list[str]) -> list[str]:
    """Los `??` SI necesitan un `add -- <ruta>` previo: git no los conoce y
    `commit -- <ruta>` falla con 'did not match any file known to git'."""
    nuevos = {
        a["path"] for a in (overview.get("archivos") or [])
        if a.get("grupo") == "sin_seguimiento"
    }
    return [r for r in seleccion if r in nuevos]


def confirmar_cambios(*, raiz: Path, rutas: list[str], mensaje: str) -> dict:
    """Guarda EXACTAMENTE los archivos indicados. Nunca toca los demas.

    Devuelve {'ok': True, 'sha', 'archivos'} o {'ok': False, 'codigo', 'mensaje'}.
    Los codigos son los mismos que traduce el diccionario llano del frontend.
    """
    raiz = Path(raiz)

    # 1) La opcion, primero de todo: apagada, ni se ejecuta git.
    if not getattr(config, "STACKY_WORKBENCH_WRITE_ENABLED", False):
        return _fallo(
            "escritura_apagada",
            "La opcion que permite guardar cambios desde el tablero esta apagada.",
        )

    # 2) Nada seleccionado: elegir es un acto deliberado.
    if not rutas:
        return _fallo("nada_seleccionado", "No elegiste ningun archivo para guardar.")

    # 3) Rutas, antes de cualquier subproceso.
    limpias, error = _validar_rutas(raiz, list(rutas))
    if error == "ruta_invalida":
        return _fallo("ruta_invalida", "Alguno de los archivos elegidos no es valido.")
    if error == "ruta_es_carpeta":
        return _fallo(
            "ruta_es_carpeta",
            "Elegiste una carpeta. Hay que elegir archivos uno por uno: una carpeta "
            "arrastraria tambien cambios que no son tuyos.",
        )

    # 4) Indice tomado por otra sesion: se detecta por disco, sin correr git.
    if _hay_index_lock(raiz):
        return _fallo(
            "otra_operacion_en_curso",
            "Hay otra operacion en curso sobre esta carpeta. Espera unos segundos "
            "y volve a intentar.",
        )

    # 5) Recien ahora se mira el repositorio.
    overview = gw.repo_overview(raiz)
    if not overview.get("available"):
        return _fallo("repo_no_disponible", overview.get("reason") or "No se pudo leer la carpeta.")
    if overview.get("conflictos"):
        return _fallo(
            "conflictos_presentes",
            "Hay archivos con cambios enfrentados. Resolvelos antes de guardar.",
        )
    if overview.get("operacion_en_curso"):
        return _fallo(
            "operacion_en_curso",
            "Quedo una operacion a medias en esta carpeta. Hay que terminarla o "
            "cancelarla antes de guardar.",
            cual=overview["operacion_en_curso"],
        )

    # 6) Los sin seguimiento necesitan un add previo, y SOLO ellos.
    nuevos = _sin_seguimiento(overview, limpias)
    if nuevos:
        res_add = gw._run_git(["add", "--", *nuevos], raiz, escritura=True)
        if res_add is None or res_add.returncode != 0:
            return _fallo(
                "no_se_pudo_guardar",
                "No se pudieron preparar los archivos nuevos que elegiste.",
            )

    # 7) El mensaje va por ARCHIVO, nunca por argumento: comillas, acentos,
    #    backticks y saltos de linea rompen el armado por argv y en Windows son
    #    un camino de inyeccion. El temporal vive FUERA del repositorio para no
    #    aparecer como archivo sin seguimiento.
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", suffix=".stacky-msg", delete=False, newline="\n",
        ) as fh:
            fh.write(mensaje or "Cambios guardados desde el tablero de Stacky")
            tmp_path = fh.name

        res = gw._run_git(
            ["commit", "-F", tmp_path, "--", *limpias], raiz, escritura=True,
        )
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    if res is None:
        return _fallo("no_se_pudo_guardar", "No se pudo guardar: la operacion no respondio a tiempo.")
    if res.returncode != 0:
        salida = f"{res.stdout or ''}\n{res.stderr or ''}"
        if "nothing to commit" in salida or "no changes added" in salida:
            return _fallo("sin_cambios", "Los archivos que elegiste no tienen cambios para guardar.")
        if "cannot do a partial commit during a merge" in salida:
            return _fallo(
                "operacion_en_curso",
                "Quedo una operacion a medias en esta carpeta y por eso no se puede "
                "guardar solo una parte.",
                cual="fusion",
            )
        return _fallo("no_se_pudo_guardar", "No se pudo guardar lo que elegiste.")

    cabeza = gw._run_git(["rev-parse", "HEAD"], raiz)
    sha = (cabeza.stdout or "").strip() if cabeza and cabeza.returncode == 0 else ""

    return {"ok": True, "codigo": None, "sha": sha, "archivos": limpias}


# ══════════════════════════════════════════════════════════════════════════════
# Plan 293 F8 — Enviar al servidor
# ══════════════════════════════════════════════════════════════════════════════


def _auth_para(project: str | None) -> str | None:
    """Reusa el encabezado no interactivo que ya resuelve el pre-run de git, en
    vez de abrir un camino nuevo para el PAT."""
    if not project:
        return None
    try:
        from services.pre_run_git import _resolve_auth_header_for_project

        return _resolve_auth_header_for_project(project)
    except Exception:  # noqa: BLE001
        return None


def enviar_cambios(*, raiz: Path, rama: str, remoto: str = "origin", project: str | None = None) -> dict:
    """Envia la rama al servidor. NUNCA fuerza.

    Un rechazo por non-fast-forward NO es un error del tablero: es la barrera de
    git funcionando, y se traduce a castellano en vez de reintentarse con fuerza.
    """
    raiz = Path(raiz)

    if not getattr(config, "STACKY_WORKBENCH_PUSH_ENABLED", False):
        return _fallo(
            "push_apagado",
            "La opcion que permite enviar tu trabajo al servidor esta apagada.",
        )

    if _hay_index_lock(raiz):
        return _fallo(
            "otra_operacion_en_curso",
            "Hay otra operacion en curso sobre esta carpeta. Espera unos segundos "
            "y volve a intentar.",
        )

    auth = _auth_para(project)
    try:
        res = gw._run_git(
            ["push", remoto, rama], raiz, escritura=True, auth_header=auth,
        )
    except gw.GitVetado:
        # `+rama`, `origen:destino` o un comodin convierten el envio en una
        # reescritura forzada de la historia del servidor. El catalogo lo veta
        # ANTES de ejecutar nada.
        return _fallo(
            "rama_invalida",
            "El nombre de la version de trabajo no es valido para enviar.",
        )

    if res is None:
        return _fallo(
            "no_se_pudo_enviar",
            "No se pudo enviar: el servidor no respondio a tiempo.",
        )

    if res.returncode != 0:
        salida = f"{res.stdout or ''}\n{res.stderr or ''}"
        bajo = salida.lower()
        if "non-fast-forward" in bajo or "fetch first" in bajo or "rejected" in bajo:
            return _fallo(
                "envio_rechazado",
                "Alguien mas subio cambios antes que vos. Trae los cambios y "
                "volve a intentar.",
            )
        if "authentication" in bajo or "403" in bajo or "denied" in bajo:
            return _fallo(
                "sin_permiso_en_el_servidor",
                "El servidor no acepto tus credenciales para esta carpeta.",
            )
        return _fallo("no_se_pudo_enviar", "No se pudo enviar tu trabajo al servidor.")

    return {"ok": True, "codigo": None, "rama": rama, "remoto": remoto}
