"""Plan 293 F1 — Tablero de trabajo: el catalogo CERRADO de verbos git.

Este modulo es la UNICA puerta por la que el tablero ejecuta git. Su razon de ser
es el riesgo #1 del plan 293: el tablero corre git sobre el repositorio REAL del
operador, que normalmente tiene trabajo sin confirmar de otras series y una sesion
paralela viva escribiendo al mismo tiempo.

POR QUE ALLOWLIST Y NO DENYLIST
-------------------------------
El contraejemplo esta medido dentro de este mismo repositorio:
services/doc_documenter.py:651 usa una denylist {"push","merge","stash"} y se
olvido de "branch", de modo que `git branch -D` alcanza el repositorio del
operador. Con denylist, olvidarse ABRE un agujero; con allowlist, olvidarse
CIERRA una funcion y se nota en el acto. El molde correcto es
services/night_foundry_workers.py:44-51, que usa allowlist y lanza ValueError.

DONDE VIVE ESTE ARCHIVO (y por que no en otro lado)
---------------------------------------------------
tests/test_plan265_git_readonly.py:213-238 hace un barrido de TEXTO LITERAL sobre
backend/api/git.py y backend/services/console_repo.py y falla si aparece alguno de
once subcomandos entre comillas. Por eso el tablero vive en modulos NUEVOS y no
extiende aquellos dos. Importarlos desde aca si esta permitido: el barrido mira el
texto de esos archivos, no el de quien los usa.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

# Verbos que solo LEEN. Nunca modifican el arbol de trabajo ni la historia.
_VERBOS_LECTURA = frozenset({
    "status", "rev-parse", "diff", "for-each-ref", "log", "config", "ls-files",
})

# Verbos que ESCRIBEN. Solo alcanzables con escritura=True, que a su vez solo se
# activa detras de una opcion apagada de fabrica.
_VERBOS_ESCRITURA = frozenset({
    "add", "commit", "switch", "push", "fetch", "merge",
})

# Formas prohibidas en CUALQUIER posicion. La comparacion es por token EXACTO,
# no por subcadena: "-F" (archivo de mensaje) no colisiona con "-f" (force), y
# "--format=x" no colisiona con "-f".
_FORMAS_PROHIBIDAS = frozenset({
    "--force", "-f", "--force-with-lease", "--hard", "--soft", "--mixed",
    "--amend", "-A", "--all", "-D", "--delete", "--allow-empty",
    "--discard-changes", "--global", "--system", "--no-verify", "-i",
    "--interactive", "--exec", "--upload-pack", "--receive-pack",
})

_TIMEOUT_LOCAL_SEG = 15
_TIMEOUT_RED_SEG = 30  # igual criterio que STACKY_PRE_RUN_GIT_TIMEOUT_SECONDS


class GitVetado(ValueError):
    """Un comando git que el catalogo cerrado NO admite. Nunca se ejecuta."""


def _validar(args: list[str], *, escritura: bool = False) -> None:
    """Lanza GitVetado si `args` no es un comando admitido. No ejecuta nada.

    `args` NO incluye el ejecutable: es ["status", "--porcelain=v2"], no
    ["git", "status", ...].
    """
    if not args:
        raise GitVetado("comando git vacio: <vacio>")

    verbo = args[0]

    if verbo not in _VERBOS_LECTURA and verbo not in _VERBOS_ESCRITURA:
        raise GitVetado(
            f"verbo git no permitido en el tablero: {verbo!r}. "
            f"El catalogo es cerrado a proposito (plan 293 F1)."
        )

    if verbo in _VERBOS_ESCRITURA and not escritura:
        raise GitVetado(
            f"el verbo {verbo!r} escribe y se pidio por el camino de lectura. "
            f"El camino de lectura no puede modificar el repositorio."
        )

    prohibidos = _FORMAS_PROHIBIDAS.intersection(args)
    if prohibidos:
        raise GitVetado(
            f"forma prohibida en el comando git: {sorted(prohibidos)}. "
            f"Estas formas destruyen o sobrescriben trabajo y no son expresables."
        )

    if verbo == "add":
        _validar_pathspec(args, "add")
    elif verbo == "commit":
        _validar_pathspec(args, "commit")
    elif verbo == "config":
        # `git config <clave> <valor>` ESCRIBE. Solo se admite la forma exacta
        # de lectura de una clave.
        if len(args) != 3 or args[1] != "--get":
            raise GitVetado(
                "config solo se admite como ['config','--get',<clave>]: "
                "cualquier otra forma puede escribir en el .git/config del operador."
            )
    elif verbo == "push":
        if len(args) != 3:
            raise GitVetado(
                "push solo se admite como ['push',<remoto>,<rama>]: "
                "cualquier argumento extra puede cambiar la semantica."
            )
    elif verbo == "merge":
        if len(args) < 2 or args[1] != "--ff-only":
            raise GitVetado(
                "merge solo se admite con --ff-only: es el unico modo que no "
                "puede fusionar a la fuerza ni perder trabajo."
            )


def _validar_pathspec(args: list[str], verbo: str) -> None:
    """Exige `-- <ruta> [<ruta>...]` con al menos una ruta concreta.

    Esta es LA barrera del riesgo #1. Con pathspec explicita, git toma esas rutas
    del arbol de trabajo sin importar que haya en el indice, asi que lo que la
    sesion paralela haya dejado preparado NO entra.
    """
    if "--" not in args:
        raise GitVetado(
            f"{verbo} exige pathspec explicita tras '--': sin ella se toma el "
            f"indice completo, que puede contener trabajo ajeno."
        )
    rutas = args[args.index("--") + 1:]
    if not rutas:
        raise GitVetado(f"{verbo} exige al menos una ruta despues de '--' (pathspec vacia).")
    for ruta in rutas:
        if ruta in (".", "..", "*", ":/") or ruta.startswith(":"):
            raise GitVetado(
                f"{verbo}: la ruta {ruta!r} es un comodin y barreria trabajo ajeno."
            )


def _entorno_no_interactivo() -> dict:
    """Mismo criterio que services/pre_run_git.py:264-272: git nunca puede quedar
    esperando un prompt dentro de un backend sin terminal."""
    env = os.environ.copy()
    env.update({
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "Never",
        "GIT_ASKPASS": "",
        "SSH_ASKPASS": "",
    })
    return env


def redactar(cmd: list[str]) -> list[str]:
    """Enmascara el PAT del http.extraheader. Ningun comando sin redactar puede
    salir del backend (ni a un log, ni a una respuesta HTTP)."""
    out: list[str] = []
    for parte in cmd:
        if parte.startswith("http.extraheader=Authorization:"):
            out.append("http.extraheader=Authorization: <redactado>")
        else:
            out.append(parte)
    return out


def _run_git(
    args: list[str],
    cwd: Path,
    *,
    escritura: bool = False,
    auth_header: str | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess | None:
    """Ejecuta git como LISTA de argumentos tras pasar por el catalogo cerrado.

    Devuelve None ante timeout, git ausente o error del sistema operativo: el
    tablero degrada, nunca revienta. La UNICA excepcion que sale de aca es
    GitVetado, y significa un error de programacion, no una condicion del entorno.
    """
    _validar(args, escritura=escritura)

    config_args = ["-c", "credential.helper=", "-c", "core.longpaths=true"]
    if auth_header:
        config_args += ["-c", f"http.extraheader=Authorization: {auth_header}"]
    cmd = ["git", *config_args, *args]

    if timeout is None:
        timeout = _TIMEOUT_RED_SEG if args[0] in ("push", "fetch", "merge") else _TIMEOUT_LOCAL_SEG

    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            env=_entorno_no_interactivo(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Plan 293 F3 — Estado enriquecido del repositorio
# ══════════════════════════════════════════════════════════════════════════════
#
# Se usa `--porcelain=v2 --branch` y NO `v1` (lo que usa console_repo.py:97)
# porque v1 no trae rama, ni upstream, ni adelante/atras, ni distingue los
# conflictos: los mezcla con los agregados y los borrados. Medido.

_GRUPOS = ("modificados", "nuevos", "borrados", "conflictos", "renombrados", "sin_seguimiento", "otros")


def _degradado(motivo: str) -> dict:
    return {
        "ok": True, "available": False, "reason": motivo,
        "repo": {}, "archivos": [], "conflictos": [], "identidad_ok": False,
    }


def _grupo_de(xy: str) -> str:
    """Clasifica el par XY de git status. Los conflictos van PRIMERO: `AA` y `DD`
    contienen 'A' y 'D', y clasificarlos por `in` los disfraza de nuevos y
    borrados — el defecto que este plan viene a cerrar."""
    if xy in ("DD", "AU", "UD", "UA", "DU", "AA", "UU"):
        return "conflictos"
    if xy.startswith("R") or xy[1:2] == "R":
        return "renombrados"
    if "D" in xy:
        return "borrados"
    if "A" in xy:
        return "nuevos"
    if "M" in xy or "T" in xy:
        return "modificados"
    return "otros"


def _parsear_status_v2(salida: str) -> tuple[list[dict], list[str]]:
    """Devuelve (archivos, conflictos). Formato en `git help status`, seccion
    "Porcelain Format Version 2". El path va SIEMPRE al final y puede tener
    espacios, asi que se corta por cantidad de campos, nunca por split() suelto.
    """
    archivos: list[dict] = []
    conflictos: list[str] = []
    for linea in salida.splitlines():
        if not linea or linea.startswith("#"):
            continue
        tipo = linea[0]
        if tipo == "1":                      # entrada ordinaria
            partes = linea.split(" ", 8)
            if len(partes) < 9:
                continue
            xy, ruta = partes[1], partes[8]
            archivos.append({"path": ruta, "xy": xy, "grupo": _grupo_de(xy)})
        elif tipo == "2":                    # renombrada o copiada
            partes = linea.split(" ", 9)
            if len(partes) < 10:
                continue
            xy = partes[1]
            ruta = partes[9].split("\t", 1)[0]
            archivos.append({"path": ruta, "xy": xy, "grupo": "renombrados"})
        elif tipo == "u":                    # sin fusionar = CONFLICTO
            partes = linea.split(" ", 10)
            if len(partes) < 11:
                continue
            xy, ruta = partes[1], partes[10]
            archivos.append({"path": ruta, "xy": xy, "grupo": "conflictos"})
            conflictos.append(ruta)
        elif tipo == "?":                    # sin seguimiento
            ruta = linea[2:]
            archivos.append({"path": ruta, "xy": "??", "grupo": "sin_seguimiento"})
        # '!' (ignorado) se descarta a proposito: no es trabajo del usuario.
    return archivos, conflictos


def _parsear_cabecera(salida: str) -> dict:
    cab = {"branch": None, "upstream": None, "ahead": 0, "behind": 0, "detached": False}
    for linea in salida.splitlines():
        if not linea.startswith("# branch."):
            continue
        if linea.startswith("# branch.head "):
            valor = linea[len("# branch.head "):].strip()
            cab["detached"] = valor == "(detached)"
            cab["branch"] = None if cab["detached"] else valor
        elif linea.startswith("# branch.upstream "):
            cab["upstream"] = linea[len("# branch.upstream "):].strip()
        elif linea.startswith("# branch.ab "):
            for token in linea[len("# branch.ab "):].split():
                if token.startswith("+"):
                    cab["ahead"] = int(token[1:] or 0)
                elif token.startswith("-"):
                    cab["behind"] = int(token[1:] or 0)
    return cab


def resolver_raiz(workspace: Path) -> Path | None:
    """La raiz real del repositorio. El workspace_root del proyecto puede ser un
    SUBDIRECTORIO: incident_dev_pr.py:77 ya usa este mismo criterio."""
    if not workspace or not Path(workspace).exists():
        return None
    res = _run_git(["rev-parse", "--show-toplevel"], Path(workspace))
    if res is None or res.returncode != 0:
        return None
    raiz = (res.stdout or "").strip()
    return Path(raiz) if raiz else None


def repo_overview(workspace: Path) -> dict:
    """Estado completo del repositorio para el tablero. NUNCA lanza."""
    workspace = Path(workspace)
    if not workspace.exists():
        return _degradado("esta carpeta no existe")

    raiz = resolver_raiz(workspace)
    if raiz is None:
        return _degradado("esta carpeta no esta preparada para guardar historial de cambios")

    if (raiz / ".git" / "index.lock").exists():
        return _degradado("hay otra operacion en curso sobre esta carpeta")

    res = _run_git(["status", "--porcelain=v2", "--branch"], raiz)
    if res is None:
        return _degradado("no se pudo consultar el estado de la carpeta")
    if res.returncode != 0:
        return _degradado("no se pudo consultar el estado de la carpeta")

    salida = res.stdout or ""
    archivos, conflictos = _parsear_status_v2(salida)
    cabecera = _parsear_cabecera(salida)

    ident = _run_git(["config", "--get", "user.email"], raiz)
    identidad_ok = bool(ident and ident.returncode == 0 and (ident.stdout or "").strip())

    return {
        "ok": True,
        "available": True,
        "reason": None,
        "raiz": str(raiz),
        "repo": cabecera,
        "archivos": archivos,
        "conflictos": conflictos,
        "identidad_ok": identidad_ok,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Plan 293 F4 — El semaforo: una sola funcion decide si se puede operar
# ══════════════════════════════════════════════════════════════════════════════
#
# Existe para que la respuesta a "por que no puedo publicar" se calcule en UN
# lugar. Repartida en cinco pantallas, produce el defecto que
# PipelineCopilotSection.tsx:246-256 ya documento: dejar apretar el boton y
# fallar al final. Ademas la re-evalua el servidor antes de escribir, asi que la
# interfaz nunca es la autoridad.

CODIGOS_BLOQUEO = frozenset({
    "repo_no_disponible", "conflictos_presentes", "sin_cambios", "nada_seleccionado",
    "escritura_apagada", "push_apagado", "sin_identidad_git", "sin_upstream",
})

CODIGOS_AVISO = frozenset({
    "hay_cambios_no_seleccionados", "rama_sin_upstream", "carrera_working_tree",
})

_ACCIONES_QUE_ESCRIBEN = ("confirmar", "traer", "cambiar_rama", "crear_rama")
_ACCIONES_QUE_ENVIAN = ("enviar", "proponer")


def evaluar_operacion(*, repo: dict, accion: str, flags: dict, seleccion: list[str]) -> dict:
    """PURA. Devuelve {'puede', 'bloqueos', 'avisos'} con CODIGOS, nunca textos:
    el castellano lo pone el diccionario del frontend.

    Los bloqueos se ACUMULAN: devolver el primero esconde los otros y obliga al
    usuario a descubrirlos de a uno.
    """
    bloqueos: list[dict] = []
    avisos: list[dict] = []

    def bloquear(codigo: str, severidad: str = "error") -> None:
        bloqueos.append({"codigo": codigo, "severidad": severidad})

    disponible = bool(repo.get("available"))
    if not disponible:
        bloquear("repo_no_disponible")

    archivos = repo.get("archivos") or []
    conflictos = repo.get("conflictos") or []
    seleccion = list(seleccion or [])

    if conflictos:
        bloquear("conflictos_presentes")

    if disponible and not archivos and accion == "confirmar":
        bloquear("sin_cambios")

    if accion == "confirmar" and not seleccion:
        bloquear("nada_seleccionado")

    if accion in _ACCIONES_QUE_ESCRIBEN and not flags.get("escritura"):
        bloquear("escritura_apagada")

    if accion in _ACCIONES_QUE_ENVIAN and not flags.get("envio"):
        bloquear("push_apagado")

    if accion == "confirmar" and disponible and not repo.get("identidad_ok", True):
        bloquear("sin_identidad_git")

    upstream = (repo.get("repo") or {}).get("upstream")
    if accion == "traer" and not upstream:
        bloquear("sin_upstream")

    # ── Avisos: NO bloquean, pero se muestran en el paso 1 ────────────────────
    if accion == "confirmar" and seleccion and len(seleccion) < len(archivos):
        avisos.append({
            "codigo": "hay_cambios_no_seleccionados",
            "severidad": "info",
            "cantidad": len(archivos) - len(seleccion),
        })

    if not upstream and accion != "traer":
        avisos.append({"codigo": "rama_sin_upstream", "severidad": "info"})

    if accion == "confirmar" and seleccion:
        avisos.append({"codigo": "carrera_working_tree", "severidad": "info"})

    return {"puede": not bloqueos, "bloqueos": bloqueos, "avisos": avisos}
