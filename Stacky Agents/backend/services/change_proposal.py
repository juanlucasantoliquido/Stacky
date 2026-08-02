"""Plan 293 F11 — La propuesta de cambio: el UNICO paso que sigue siendo REST.

POR QUE ESTE PASO NO ES GIT LOCAL
---------------------------------
"Abrir una propuesta de cambio" (Pull Request en Azure DevOps, Merge Request en
GitLab) NO TIENE EQUIVALENTE EN GIT: es un objeto del servidor, no del
repositorio. Por eso el tablero es hibrido A PROPOSITO: todo lo demas (estado,
diferencias, guardar, traer, enviar, ramas, historial) es git local, y solo esto
va por la API del proveedor.

LA RESTRICCION QUE ORDENA TODO EL MODULO
----------------------------------------
`create_merge_request` acepta EXACTAMENTE CUATRO parametros y nada mas:
    create_merge_request(source_branch, target_branch, title, description)
Verificado en los dos proveedores (services/gitlab_provider.py:924 y
services/ado_provider.py:265). Grepeado `reviewers|draft|squash|assignee`: cero
hits. El catalogo declarativo lo confirma en services/provider_capabilities.py.

CONSECUENCIA, DICHA DE FRENTE Y NO ESCONDIDA: todo lo que el pliego pide para el
formulario —resumen de los cambios, checklist de pruebas, evidencias— se
RENDERIZA DENTRO DEL STRING `description`, porque es el unico campo libre que los
proveedores aceptan. No hay campo de reviewers, ni de etiquetas, ni de adjuntos.

PROHIBIDO: `link_attachment` de GitLab (services/gitlab_provider.py:521-537).
Lee la descripcion actual del issue y si el GET previo falla asume "", PISANDO la
descripcion entera. Es riesgo de perdida de datos. Este modulo NO lo llama, y hay
un caso negativo que lo vigila.
"""
from __future__ import annotations

import re
from pathlib import Path

from services import git_workbench as gw

# Los seis patrones de ALTA CONFIANZA del auto-PR del Dev Resolutor. Se avisa de
# menos a proposito: un detector agresivo destruye codigo legitimo
# (`password = cfg.get("db_password")` salia como `***REDACTED***`).
_PATRONES_SECRETO: tuple[tuple[str, str], ...] = (
    (r"AKIA[0-9A-Z]{16}", "clave de acceso de Amazon"),
    (r"ghp_[A-Za-z0-9]{36}", "credencial de GitHub"),
    (r"glpat-[A-Za-z0-9_\-]{20}", "credencial de GitLab"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "credencial de Slack"),
    (r"Authorization:\s*Bearer\s+[A-Za-z0-9._\-]{20,}", "encabezado de autorizacion"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "clave privada"),
)

_MAX_ARCHIVOS_LISTADOS = 60


def buscar_sospechas(textos: dict[str, str]) -> list[dict]:
    """[{'archivo','tipo'}] por cada coincidencia de alta confianza. NUNCA
    devuelve el secreto en si: solo que lo hay y de que tipo."""
    hallazgos: list[dict] = []
    for archivo, contenido in (textos or {}).items():
        for patron, etiqueta in _PATRONES_SECRETO:
            if re.search(patron, contenido or ""):
                hallazgos.append({"archivo": archivo, "tipo": etiqueta})
    return hallazgos


def build_description(
    *,
    resumen: str,
    archivos: list[str],
    pruebas: str = "",
    evidencias: list[str] | None = None,
    sospechas: list[dict] | None = None,
) -> str:
    """Arma el UNICO campo libre que aceptan los proveedores.

    El orden de las secciones es fijo y estable: un revisor humano aprende donde
    mirar, y un test puede aserterlo.
    """
    if not archivos:
        raise ValueError("una propuesta de cambio sin archivos no tiene sentido")

    partes: list[str] = []

    partes.append("## Que cambie\n")
    partes.append((resumen or "").strip() or "_Sin descripcion._")

    partes.append("\n\n## Archivos incluidos\n")
    for a in archivos[:_MAX_ARCHIVOS_LISTADOS]:
        partes.append(f"- `{a}`\n")
    if len(archivos) > _MAX_ARCHIVOS_LISTADOS:
        partes.append(f"- _(y {len(archivos) - _MAX_ARCHIVOS_LISTADOS} mas)_\n")

    if (pruebas or "").strip():
        partes.append("\n## Que probe\n")
        partes.append((pruebas or "").strip())
        partes.append("\n")

    if evidencias:
        partes.append("\n## Evidencia adjunta\n")
        for e in evidencias:
            partes.append(f"{e}\n")

    if sospechas:
        partes.append("\n## Revisar antes de integrar\n")
        partes.append(
            "Se detectaron cadenas que **parecen** credenciales. "
            "Miralas antes de aprobar:\n\n"
        )
        for s in sospechas:
            partes.append(f"- `{s['archivo']}`: {s['tipo']}\n")

    partes.append("\n---\n_Propuesta creada desde el tablero de trabajo de Stacky._\n")
    return "".join(partes)


def resolver_rama_destino(raiz: Path) -> str | None:
    """La rama principal del servidor. NO se supone "main".

    Se pregunta por `origin/HEAD` y, si no esta configurado (es lo normal en un
    clon hecho con --single-branch), se prueban "main" y "master" VERIFICANDO que
    existan. Devolver una rama inexistente hace fallar el REST con un error del
    proveedor que no dice nada util.
    """
    raiz = Path(raiz)
    res = gw._run_git(["rev-parse", "--abbrev-ref", "origin/HEAD"], raiz)
    if res is not None and res.returncode == 0:
        valor = (res.stdout or "").strip()
        if valor.startswith("origin/"):
            return valor[len("origin/"):]

    ramas = gw._run_git(
        ["for-each-ref", "--format=%(refname:short)", "refs/remotes/origin"], raiz,
    )
    disponibles = set()
    if ramas is not None and ramas.returncode == 0:
        disponibles = {
            l.strip().removeprefix("origin/")
            for l in (ramas.stdout or "").splitlines() if l.strip()
        }
    for candidata in ("main", "master", "develop"):
        if candidata in disponibles:
            return candidata
    return None


def abrir_propuesta(
    *,
    raiz: Path,
    rama_origen: str,
    titulo: str,
    resumen: str,
    archivos: list[str],
    pruebas: str = "",
    evidencias: list[str] | None = None,
    sospechas: list[dict] | None = None,
    project: str | None = None,
    rama_destino: str | None = None,
) -> dict:
    """Crea la propuesta en el servidor del proyecto. Un solo llamado REST."""
    from config import config

    if not getattr(config, "STACKY_WORKBENCH_PUSH_ENABLED", False):
        return {
            "ok": False, "codigo": "push_apagado",
            "mensaje": "La opcion que permite abrir propuestas esta apagada.",
        }

    if not (titulo or "").strip():
        return {"ok": False, "codigo": "titulo_vacio", "mensaje": "Falta el titulo de la propuesta."}

    destino = rama_destino or resolver_rama_destino(Path(raiz))
    if not destino:
        return {
            "ok": False, "codigo": "sin_rama_destino",
            "mensaje": "No se pudo determinar contra que version principal proponer el cambio.",
        }
    if destino == rama_origen:
        return {
            "ok": False, "codigo": "misma_rama",
            "mensaje": "Estas trabajando directamente sobre la version principal. "
                       "Crea una version de trabajo propia antes de proponer el cambio.",
        }

    try:
        from services.merge_request_provider import get_merge_request_provider

        proveedor = get_merge_request_provider(project=project)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "codigo": "tracker_sin_propuestas",
            "mensaje": "Este proyecto no tiene un servidor donde abrir propuestas de cambio.",
            "detalle": type(exc).__name__,
        }

    descripcion = build_description(
        resumen=resumen, archivos=archivos, pruebas=pruebas,
        evidencias=evidencias, sospechas=sospechas,
    )

    try:
        # UN solo llamado, con la descripcion YA armada. Nunca se crea primero y
        # se "completa" despues: ese camino es el que puede pisar contenido.
        creada = proveedor.create_merge_request(rama_origen, destino, titulo.strip(), descripcion)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False, "codigo": "no_se_pudo_proponer",
            "mensaje": "El servidor no acepto la propuesta de cambio.",
            "detalle": type(exc).__name__,
        }

    return {
        "ok": True, "codigo": None,
        "url": (creada or {}).get("web_url") or (creada or {}).get("url") or "",
        "id": (creada or {}).get("id") or (creada or {}).get("iid") or "",
        "rama_origen": rama_origen, "rama_destino": destino,
    }
