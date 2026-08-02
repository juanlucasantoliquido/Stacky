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
