"""services/pipeline_handoff_bundle.py — Plan 252 F2/F3. Paquete de entrega.

PURO salvo `persist_bundle`/`prune_bundles`/`append_ledger` (F3). El README sale de
PLANTILLA, jamas de un LLM: por eso la paridad de los 3 runtimes es trivial y el texto
es identico bit a bit en Codex, Claude Code y Copilot.

Este modulo no cruza la frontera: no importa nada de ejecucion remota ni de red, y no
usa imports dinamicos. La lista negra y su verificacion por AST viven en
tests/test_plan252_capability_frontier.py::test_modulos_sin_ejecucion_remota.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.pipeline_capability_frontier import CATALOG_VERSION, manual_actions

MANIFEST_VERSION = 1
BUNDLE_ID_LEN = 16
_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
MAX_BUNDLE_BYTES = 20 * 1024 * 1024
_BUNDLES_DIRNAME = "pipeline_handoff/bundles"
_BUNDLE_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_SECRET_CLASS = "secrets"
_PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


class HandoffError(RuntimeError):
    """Falla del paquete de entrega."""


class HandoffSecretError(HandoffError):
    """Se detecto material sensible: el paquete NO se genera."""


class HandoffTooLargeError(HandoffError):
    """El paquete supera el tope."""


# ── Contratos ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class HandoffStep:
    """Espeja campo por campo a validation_playbook.ValidationStep (n / action /
    expected_result / source) y AGREGA lo que un paso de servidor necesita: donde, con
    que comando, y que hacer si falla."""

    n: int
    action: str
    expected_result: str
    source: str
    where: str
    command: str
    on_failure: str
    lang: str = "powershell"
    repeatable: bool = True

    def __post_init__(self):
        for campo in ("action", "expected_result", "source", "where", "command",
                      "on_failure"):
            if not str(getattr(self, campo)).strip():
                raise HandoffError(
                    "HandoffStep.%s no puede estar vacio: un paso sin validacion no es "
                    "un paso, es una promesa (KPI-4)" % campo)

    def to_dict(self) -> dict:
        return {"n": int(self.n), "action": self.action, "where": self.where,
                "command": self.command, "expected_result": self.expected_result,
                "on_failure": self.on_failure, "source": self.source,
                "lang": self.lang, "repeatable": self.repeatable}


def _assert_campo_limpio(obj, campo: str) -> None:
    """El campo se valida en SU constructor y el error NOMBRA el campo y la variable.

    Fallar temprano y preciso, no tarde y generico: sin esto, un `format_hint` con forma
    de cadena de conexion dispara el gate de F3 y aborta el paquete entero con un 409
    que dice "hay material sensible en README.md", sin decir cual de las N variables lo
    causo. Sigue siendo falla cerrado; solo se mueve el punto de deteccion.
    """
    from services.egress_policies import detect_classes

    texto = str(getattr(obj, campo) or "")
    if _SECRET_CLASS in detect_classes(texto):
        raise HandoffSecretError(
            "%s.%s parece contener un valor sensible (o una plantilla con forma de "
            "credencial): %r. Describi el FORMATO sin escribir un valor de ejemplo con "
            "forma de clave." % (type(obj).__name__, campo, getattr(obj, "name", "?")))


@dataclass(frozen=True)
class HandoffVariable:
    name: str
    where: str
    format_hint: str
    secret: bool
    # INVARIANTE: NO existe un campo `value`. No se puede filtrar lo que no se modela.

    def __post_init__(self):
        _assert_campo_limpio(self, "format_hint")

    def to_dict(self) -> dict:
        return {"name": self.name, "where": self.where,
                "format_hint": self.format_hint, "secret": bool(self.secret)}


@dataclass(frozen=True)
class BundleInputs:
    pipeline_name: str
    provider: str                      # "ado" | "gitlab"
    yaml_files: dict                   # {"pipelines/ci.yml": "<texto>"}
    script_files: dict = field(default_factory=dict)
    variables: tuple = ()
    pipeline_deploys: bool = False
    degraded: tuple = ()


DEGRADED_CONSEQUENCE = {
    "pipeline_inventory": (
        "no se pudo cruzar con las pipelines ya existentes: revisá a mano que el nombre "
        "no choque con una definición registrada"),
    "pipeline_profiler": (
        "el propósito y la tecnología del pipeline no están descritos en este README"),
    "pipeline_environments": (
        "las variables por entorno se dedujeron de los marcadores del YAML en vez de la "
        "matriz de entornos, así que la lista puede estar incompleta"),
}


PREREQUISITES: tuple = (
    HandoffStep(
        n=1, action="Tenés acceso de administrador al servidor destino",
        where="servidor destino", lang="powershell",
        command='whoami /groups | findstr /i "S-1-5-32-544"',
        expected_result="Aparece al menos una línea (grupo Administradores).",
        on_failure="Pedí que te agreguen al grupo Administradores del servidor; sin eso "
                   "los pasos de instalación no se pueden hacer.",
        source="prereq:admin"),
    HandoffStep(
        n=2, action="El servidor sale a internet por HTTPS",
        where="servidor destino", lang="powershell",
        command="Test-NetConnection dev.azure.com -Port 443",
        expected_result="TcpTestSucceeded : True",
        on_failure="Pedí a la gente de red que habilite la salida HTTPS del servidor "
                   "hacia el proveedor; el agente no puede registrarse sin eso.",
        source="prereq:egress"),
    HandoffStep(
        n=3, action="Tenés permiso de escritura en la carpeta de destino del deploy",
        where="servidor destino", lang="powershell",
        command=('New-Item -ItemType File -Path "<RUTA_DESTINO>\\stacky.probe" -Force; '
                 'Remove-Item "<RUTA_DESTINO>\\stacky.probe"'),
        expected_result="Ninguno de los dos comandos imprime un error.",
        on_failure="Pedí permiso de escritura sobre esa carpeta para la cuenta con la "
                   "que corre el agente.",
        source="prereq:write"),
)

FINAL_CHECKS: tuple = (
    {"check": "La pipeline aparece listada en el proveedor",
     "command": "# Pipelines -> buscar por nombre: {pipeline_name}"},
    {"check": "La primera corrida terminó en verde",
     "command": "# Pipelines -> {pipeline_name} -> última corrida -> estado 'Succeeded'"},
    {"check": "El artefacto o el deploy llegó al destino",
     "command": 'Get-ChildItem "<RUTA_DESTINO>" | Select-Object -First 5'},
)


_STEP_TEMPLATES: dict = {
    "set_pipeline_secrets": dict(
        where="web del proveedor",
        lang="text",
        command="# Pipelines -> Library / Variables -> por cada secreto del punto 4:\n"
                "#   nombre = el de la tabla, valor = el tuyo, casilla 'secreto' TILDADA",
        expected_result="Cada secreto de la tabla del punto 4 aparece listado con el "
                        "candado, y su valor ya no se puede volver a leer.",
        on_failure="Si el proveedor rechaza el nombre, revisá que empiece con letra o "
                   "guion bajo y que solo tenga letras, dígitos y guiones bajos.",
        repeatable=True),
    "create_service_connection": dict(
        where="web de Azure DevOps",
        lang="text",
        command="# Project settings -> Service connections -> New service connection",
        expected_result="La conexión aparece en la lista con estado verificado y el "
                        "nombre que usa el YAML.",
        on_failure="Si no te deja crearla, pedí rol de administrador del proyecto: la "
                   "creación exige el consentimiento de una identidad.",
        repeatable=True),
    "create_variable_group": dict(
        where="web de Azure DevOps",
        lang="text",
        command="# Pipelines -> Library -> + Variable group",
        expected_result="El grupo aparece en Library y el pipeline lo puede referenciar.",
        on_failure="Si no aparece la opción, te falta permiso sobre Library.",
        repeatable=True),
    "create_environment_and_approvals": dict(
        where="web de Azure DevOps",
        lang="text",
        command="# Pipelines -> Environments -> New environment, y despues\n"
                "#   Approvals and checks -> Approvals -> agregar aprobadores",
        expected_result="El entorno figura en la lista y muestra al menos un aprobador.",
        on_failure="Si no podés agregar aprobadores, pedí permiso de Environments.",
        repeatable=True),
    "create_agent_pool": dict(
        where="web de Azure DevOps",
        lang="text",
        command="# Project settings -> Agent pools -> Add pool",
        expected_result="El pool aparece en la lista, todavía sin agentes.",
        on_failure="Crear un pool exige rol de administrador a nivel organización: "
                   "pedíselo a quien administra la organización.",
        repeatable=True),
    "install_selfhosted_agent": dict(
        where="servidor destino (sesión de administrador)",
        lang="powershell",
        command=(
            "# 1) En el proveedor: Project settings -> Agent pools -> <pool> -> New agent\n"
            "# 2) En el SERVIDOR, en una consola como administrador:\n"
            "mkdir C:\\agent; cd C:\\agent\n"
            "Add-Type -AssemblyName System.IO.Compression.FileSystem\n"
            "[System.IO.Compression.ZipFile]::ExtractToDirectory("
            "\"$HOME\\Downloads\\vsts-agent-win-x64.zip\", \"C:\\agent\")\n"
            ".\\config.cmd --unattended --url <URL_DE_TU_ORGANIZACION> --auth pat "
            "--pool <NOMBRE_DEL_POOL> --runAsService\n"
            "# La credencial te la pide de forma interactiva: NO la escribas en este archivo."),
        expected_result="En el proveedor, el pool muestra el agente con el punto VERDE y "
                        "estado 'Online'. En el servidor, `Get-Service vstsagent*` "
                        "devuelve Status=Running.",
        on_failure="Si el agente queda 'Offline': revisá que el servicio esté corriendo "
                   "y que el servidor salga por HTTPS al proveedor. El registro de "
                   "diagnóstico vive en C:\\agent\\_diag\\.",
        repeatable=False),
    "install_server_prerequisites": dict(
        where="servidor destino (sesión de administrador)",
        lang="powershell",
        command=("Install-WindowsFeature -Name Web-Server -IncludeManagementTools\n"
                 "# y las herramientas de compilación que pida tu stack"),
        expected_result="`Get-WindowsFeature Web-Server` muestra Install State=Installed "
                        "y el sitio responde en el puerto configurado.",
        on_failure="Si falla la instalación del rol, revisá que el servidor tenga la "
                   "fuente de instalación disponible y reintentá.",
        repeatable=True),
    "commit_yaml_to_repo": dict(
        where="tu máquina",
        lang="powershell",
        command="git checkout -b feature/pipeline; git add <ruta-del-yml>; "
                "git commit -m \"pipeline\"; git push -u origin feature/pipeline",
        expected_result="La rama aparece en el repo con el .yml adentro.",
        on_failure="Si el push es rechazado, revisá que tengas permiso de escritura en "
                   "el repositorio.",
        repeatable=True),
    "open_pull_request": dict(
        where="web del proveedor",
        lang="text",
        command="# Repos -> Pull requests -> New pull request, desde tu rama a la default",
        expected_result="El PR queda creado y muestra el .yml entre sus cambios.",
        on_failure="Si no te deja crearlo, revisá que la rama esté pusheada.",
        repeatable=True),
    "register_pipeline_definition": dict(
        where="web del proveedor",
        lang="text",
        command="# Pipelines -> New pipeline -> Existing Azure Pipelines YAML file\n"
                "#   y eleg� la ruta del .yml de este paquete",
        expected_result="La pipeline aparece listada con el nombre esperado y apunta al "
                        "archivo correcto.",
        on_failure="Si no encuentra el archivo, revisá que la rama y la ruta sean las "
                   "que dice el punto 8 de este README.",
        repeatable=True),
    "set_pipeline_variables": dict(
        where="web del proveedor",
        lang="text",
        command="# Pipelines -> Variables (o Settings -> CI/CD -> Variables en GitLab)",
        expected_result="Cada variable NO secreta de la tabla del punto 4 aparece con su "
                        "valor.",
        on_failure="Si el nombre es rechazado, revisá el formato permitido de claves.",
        repeatable=True),
    "run_pipeline_first_time": dict(
        where="web del proveedor",
        lang="text",
        command="# Pipelines -> <tu pipeline> -> Run pipeline",
        expected_result="La corrida arranca, toma un agente y termina en verde.",
        on_failure="Si queda en cola para siempre, es que no hay ningún agente en línea "
                   "en el pool: volvé al paso del agente.",
        repeatable=True),
}


# ── F2 — recoleccion, manifest, README ──────────────────────────────────────

def _variables_from_preflight(spec_dict: dict, provider: str) -> tuple:
    """Fallback determinista: NO inventa nada, usa lo que el preflight ya sabe leer."""
    from services.ci_variables import looks_secret
    from services.pipeline_preflight import referenced_variables

    target = "gitlab" if provider == "gitlab" else "ado"
    donde = ("Settings → CI/CD → Variables" if target == "gitlab"
             else "Pipelines → Library / variables de la pipeline")
    nombres = sorted(referenced_variables(spec_dict or {}, target))
    return tuple(
        HandoffVariable(
            name=n, where=donde,
            format_hint="texto de una línea, sin comillas",
            secret=bool(looks_secret(n)),
        ) for n in nombres
    )


def _variables_from_env_matrix(modulo, spec_dict: dict, provider: str) -> tuple:
    """Plan 251 presente: la lista sale de la matriz de entornos, que ya sabe cuáles
    faltan y cuáles no."""
    from services.ci_variables import looks_secret

    yaml_text = str((spec_dict or {}).get("yaml_text") or "")
    proveedor = "gitlab" if provider == "gitlab" else "azure_devops"
    donde = ("Settings → CI/CD → Variables" if provider == "gitlab"
             else "Pipelines → Library / variables de la pipeline")
    requisitos = modulo.extract_requirements(yaml_text, proveedor)
    salida = []
    for r in requisitos:
        if r.kind not in ("variable", "secret"):
            continue
        salida.append(HandoffVariable(
            name=r.name, where=donde,
            format_hint="texto de una línea, sin comillas",
            secret=bool(r.is_secret or looks_secret(r.name)),
        ))
    return tuple(salida)


def collect_inputs(spec_dict, *, pipeline_name: str, provider: str, yaml_files: dict,
                   script_files: Optional[dict] = None,
                   pipeline_deploys: bool = False) -> BundleInputs:
    """Degradacion HONESTA.

    `except Exception`, no `except ImportError`: un modulo hermano que exista pero
    reviente al importarse tiene que DEGRADAR el paquete, no tumbarlo. Degradar es el
    trabajo de esta funcion.

    `degraded` se devuelve SIEMPRE ordenado: entra al MANIFEST y al README, y por lo
    tanto al bundle_id. Si su orden dependiera del orden de los `try`, dos corridas
    equivalentes darian ids distintos tras cualquier refactor.

    Sin imports dinamicos: tres bloques explicitos, para que el test por AST sea decidible.
    """
    degraded: list = []

    try:
        from services import pipeline_environments
        variables = _variables_from_env_matrix(pipeline_environments, spec_dict, provider)
    except Exception:  # noqa: BLE001
        degraded.append("pipeline_environments")
        variables = _variables_from_preflight(spec_dict, provider)

    try:
        from services import pipeline_inventory
        _ = pipeline_inventory
    except Exception:  # noqa: BLE001
        degraded.append("pipeline_inventory")

    try:
        from services import pipeline_profiler
        _ = pipeline_profiler
    except Exception:  # noqa: BLE001
        degraded.append("pipeline_profiler")

    return BundleInputs(
        pipeline_name=str(pipeline_name),
        provider=str(provider),
        yaml_files=dict(yaml_files or {}),
        script_files=dict(script_files or {}),
        variables=tuple(variables),
        pipeline_deploys=bool(pipeline_deploys),
        degraded=tuple(sorted(set(degraded))),
    )


def build_steps(resolved_frontier: list) -> tuple:
    """Un HandoffStep por accion MANUAL, en orden de catalogo. Ninguna accion CAN
    produce un paso: si Stacky ya lo hizo, no es trabajo del operador (KPI-3)."""
    pasos: list = []
    for n, resuelto in enumerate(manual_actions(resolved_frontier), start=1):
        plantilla = _STEP_TEMPLATES.get(resuelto.action.id)
        if plantilla is None:
            raise HandoffError(
                "no hay plantilla de paso para la accion manual '%s': preferimos romper "
                "en un test a emitir un README con un paso vacio" % resuelto.action.id)
        pasos.append(HandoffStep(n=n, action=resuelto.action.label,
                                 source="frontier:%s" % resuelto.action.id,
                                 **plantilla))
    return tuple(pasos)


def build_manifest(inputs: BundleInputs, resolved_frontier: list) -> dict:
    """Shape exacto, SIN `generated_at`: un timestamp adentro rompe el determinismo."""
    pasos = build_steps(resolved_frontier)
    return {
        "manifest_version": MANIFEST_VERSION,
        "catalog_version": CATALOG_VERSION,
        "bundle_id": "",                       # se inyecta en build_files
        "pipeline_name": inputs.pipeline_name,
        "provider": inputs.provider,
        "degraded": list(inputs.degraded),
        "frontier": [{"id": r.action.id, "label": r.action.label,
                      "effective": r.effective, "reason": r.action.reason,
                      "probe_detail": r.probe_detail} for r in resolved_frontier],
        "steps": [s.to_dict() for s in pasos],
        "prerequisites": [s.to_dict() for s in PREREQUISITES],
        "variables": [v.to_dict() for v in inputs.variables],
        "final_checks": [dict(c) for c in FINAL_CHECKS],
        "files": [],                           # se completa en build_files
    }


def _bloque(titulo: str, cuerpo: str) -> str:
    """Una seccion vacia se omite ENTERA, encabezado incluido."""
    return ("## %s\n\n%s\n\n" % (titulo, cuerpo)) if cuerpo.strip() else ""


def render_readme(manifest: dict) -> str:
    """Por PLANTILLA, jamas por un LLM. Identico bit a bit en los 3 runtimes."""
    nombre = manifest.get("pipeline_name") or "pipeline"
    partes: list = [
        "# Paquete de entrega — %s\n" % nombre,
        "Generado por Stacky Agents · id `%s` · proveedor `%s`\n"
        % (manifest.get("bundle_id") or "", manifest.get("provider") or ""),
        "El `id` es la huella del contenido de este paquete, no una fecha: dos paquetes "
        "con el mismo id son byte a byte el mismo paquete.\n\n---\n\n",
    ]

    hizo = [f for f in manifest.get("frontier") or [] if f["effective"] == "CAN"]
    partes.append(_bloque(
        "1. Qué hizo Stacky por vos",
        "\n".join("- %s. %s" % (f["label"], f["reason"]) for f in hizo)))

    toca = [f for f in manifest.get("frontier") or []
            if f["effective"] in ("CANNOT", "CANNOT_NOW", "UNKNOWN")]
    if toca:
        lineas = ["Estas son las únicas tareas que Stacky no puede ejecutar por sí "
                  "mismo. No hay ninguna otra.\n"]
        for f in toca:
            extra = ""
            if f["effective"] == "CANNOT_NOW":
                extra = (" (hoy no se pudo: %s; si lo configurás en Stacky, la próxima "
                         "vez esto lo hace solo)" % f["probe_detail"])
            elif f["effective"] == "UNKNOWN":
                extra = (" (Stacky no pudo verificarlo: %s; queda como trabajo tuyo por "
                         "las dudas)" % f["probe_detail"])
            lineas.append("- **%s** — %s%s" % (f["label"], f["reason"], extra))
        degradado = manifest.get("degraded") or []
        if degradado:
            consecuencias = "; ".join(
                DEGRADED_CONSEQUENCE.get(d, "faltó el módulo %s" % d) for d in degradado)
            lineas.append("\n> Nota honesta: este paquete se armó sin %s. Eso significa "
                          "que %s." % (", ".join(degradado), consecuencias))
        partes.append(_bloque("2. Qué te toca a vos, y por qué", "\n".join(lineas)))

    prereqs = manifest.get("prerequisites") or []
    if prereqs:
        filas = ["Verificá los tres antes de empezar. Si alguno falla, frená: los pasos "
                 "siguientes no van a andar.\n",
                 "| # | Prerequisito | Cómo verificarlo | Qué tenés que ver |",
                 "|---|--------------|------------------|-------------------|"]
        for p in prereqs:
            filas.append("| %s | %s | `%s` | %s |"
                         % (p["n"], p["action"], p["command"].replace("\n", " "),
                            p["expected_result"]))
        partes.append(_bloque("3. Prerequisitos", "\n".join(filas)))

    variables = manifest.get("variables") or []
    if variables:
        filas = ["Stacky **no incluye ni un solo valor secreto en este paquete**, a "
                 "propósito. Acá está la lista de qué completar y dónde; los valores "
                 "los ponés vos.\n",
                 "| Variable | Dónde se carga | Formato / ejemplo | ¿Es secreta? |",
                 "|----------|----------------|-------------------|--------------|"]
        for v in variables:
            filas.append("| `%s` | %s | %s | %s |"
                         % (v["name"], v["where"], v["format_hint"],
                            "SÍ — cargala marcada como secreta" if v["secret"] else "no"))
        partes.append(_bloque("4. Variables a completar", "\n".join(filas)))

    pasos = manifest.get("steps") or []
    if pasos:
        bloques = []
        for s in pasos:
            bloques.append(
                "### Paso %s — %s\n\n- **Dónde:** %s\n- **Comando:**\n  ```%s\n%s\n  ```\n"
                "- **Cómo sabés que salió bien:** %s\n- **Si falla:** %s\n- **Fuente:** %s"
                "%s"
                % (s["n"], s["action"], s["where"], s["lang"],
                   "\n".join("  " + l for l in s["command"].splitlines()),
                   s["expected_result"], s["on_failure"], s["source"],
                   "" if s.get("repeatable", True) else "\n- **No repetible.**"))
        partes.append(_bloque("5. Pasos", "\n\n".join(bloques)))

    checks = manifest.get("final_checks") or []
    cuerpo = ["Cuando termines todos los pasos, esto tiene que ser cierto:\n"]
    for c in checks:
        cuerpo.append("- [ ] %s — verificalo con: `%s`"
                      % (c["check"], str(c["command"]).replace("{pipeline_name}", nombre)))
    cuerpo.append("\nSi algún ítem no se cumple, **no des el pipeline por operativo**.")
    partes.append(_bloque("6. Validación final", "\n".join(cuerpo)))

    partes.append(_bloque(
        "7. Si algo sale mal",
        "Nada de lo que hiciste con este paquete borra datos: si un paso falló a la "
        "mitad, se puede repetir. Los pasos marcados como no repetibles en la sección 5 "
        "son la excepción y lo dicen ahí mismo."))

    archivos = manifest.get("files") or []
    if archivos:
        partes.append(_bloque(
            "8. Anexo — contenido del paquete",
            "\n".join("- `%s` — %s · %s bytes" % (f["path"], f["kind"], f["bytes"])
                      for f in archivos)))

    return "".join(partes)


def compute_bundle_id(files: dict) -> str:
    """sha256 del mapa de archivos, insensible al orden de insercion."""
    h = hashlib.sha256()
    for path in sorted(files):
        h.update(path.encode("utf-8"))
        h.update(b"\x00")
        h.update(files[path].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:BUNDLE_ID_LEN]


def _kind_de(path: str) -> str:
    bajo = path.lower()
    if bajo.endswith((".yml", ".yaml")):
        return "yaml"
    if bajo.endswith((".ps1", ".sh", ".cmd", ".bat")):
        return "script"
    if bajo.endswith(".json"):
        return "manifest"
    if bajo.endswith(".md"):
        return "doc"
    return "otro"


def build_files(inputs: BundleInputs, resolved_frontier: list) -> dict:
    """{ruta: texto} completo. El bundle_id se calcula sobre el mapa SIN MANIFEST.json
    ni README.md (que lo contienen) y recien despues se inyecta: si no, es una
    referencia circular."""
    base = {**dict(inputs.yaml_files or {}), **dict(inputs.script_files or {})}
    if not base:
        raise HandoffError("un paquete sin archivos no es un paquete")

    bundle_id = compute_bundle_id(base)
    manifest = build_manifest(inputs, resolved_frontier)
    manifest["bundle_id"] = bundle_id
    manifest["files"] = [
        {"path": p, "kind": _kind_de(p), "bytes": len(base[p].encode("utf-8"))}
        for p in sorted(base)
    ]
    readme = render_readme(manifest)
    manifest_json = json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True)
    return {**base, "MANIFEST.json": manifest_json, "README.md": readme}


# ── F3 — gate anti-secreto, zip determinista, persistencia ──────────────────

def assert_no_secrets(files: dict) -> None:
    """Capa 1 (GATE): corre sobre el texto CRUDO. Si detecta un secreto, LANZA.
    Falla cerrado: no enmascara y sigue.

    Solo mira la clase "secrets". Las clases `pii` (un build number de 8 digitos la
    dispara) y `production` (un README de deploy dice "producción" si o si) volverian el
    paquete INCONSTRUIBLE. Los dos patrones instructivos de la clase secrets
    (password=... y ;password=...) NO se relajan: se atajan en el origen, validando
    HandoffVariable.format_hint en su constructor.
    """
    from services.egress_policies import detect_classes

    ofensores = [p for p, t in sorted(files.items())
                 if _SECRET_CLASS in detect_classes(t)]
    if ofensores:
        from services.secret_masking import MASK_PLACEHOLDER
        raise HandoffSecretError(
            "El paquete NO se generó: se detectó material sensible en %s. Quitá el valor "
            "del origen (el paquete solo debe nombrar variables, nunca sus valores) y "
            "volvé a intentar. Marcador de enmascarado: %s"
            % (", ".join(ofensores), MASK_PLACEHOLDER))


def scrub_files(files: dict) -> dict:
    """Capa 2 (TESTIGO, ya no filtro): masking canonico sobre TODO texto.

    Corre DESPUES del gate, y su unico proposito es delatar lo que el gate no vio. No
    limpia: acusa. Si corriera ANTES, BORRARIA el secreto y el gate no encontraria nada
    -> el paquete saldria. Es decir: fallaria ABIERTO justo para los formatos que el
    enmascarador sabe reconocer.
    """
    from services.secret_masking import mask_token_values

    return {path: mask_token_values(text) for path, text in files.items()}


def zip_bytes(files: dict) -> bytes:
    """Zip REPRODUCIBLE: mismas entradas -> mismos bytes, siempre.

    Regla: una entrada NUNCA se escribe desde una ruta del filesystem (tomaria el mtime
    del disco) ni pasando un nombre desnudo (usaria la hora local). Siempre ZipInfo
    explicito con la epoca fija.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname in sorted(files):
            info = zipfile.ZipInfo(arcname.replace("\\", "/"), date_time=_ZIP_EPOCH)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 0
            zf.writestr(info, files[arcname].encode("utf-8"))
    return buf.getvalue()


def build_bundle(inputs: BundleInputs, resolved_frontier: list) -> tuple:
    """Camino UNICO de generacion. -> (bundle_id, bytes, manifest).

    ORDEN NO NEGOCIABLE:
        build_files -> assert_no_secrets(CRUDO) -> scrub_files -> scrub fue no-op? -> zip
    """
    files = build_files(inputs, resolved_frontier)
    assert_no_secrets(files)                     # gate sobre el texto CRUDO
    scrubbed = scrub_files(files)
    if scrubbed != files:                        # el enmascarado debe ser un NO-OP
        culpables = sorted(p for p in files if scrubbed[p] != files[p])
        raise HandoffSecretError(
            "El paquete NO se generó: el enmascarado canónico encontró material sensible "
            "que el gate no reconoció, en %s. Es un formato de credencial nuevo: quitalo "
            "del origen y reportalo para sumarlo al detector." % ", ".join(culpables))
    data = zip_bytes(files)
    if len(data) > MAX_BUNDLE_BYTES:
        raise HandoffTooLargeError(
            "el paquete pesa %d bytes (tope %d)" % (len(data), MAX_BUNDLE_BYTES))
    manifest = json.loads(files["MANIFEST.json"])
    return manifest["bundle_id"], data, manifest


def _bundles_root() -> Path:
    from runtime_paths import data_dir

    return Path(data_dir()) / "pipeline_handoff" / "bundles"


def bundle_path(bundle_id: str) -> Optional[Path]:
    """`bundle_id` es una CLAVE, jamas parte de una ruta construida a ciegas. Se valida
    contra ^[0-9a-f]{16}$ ANTES de tocar el filesystem; si no matchea -> None."""
    if not isinstance(bundle_id, str) or not _BUNDLE_ID_RE.match(bundle_id):
        return None
    return _bundles_root() / ("%s.zip" % bundle_id)


def persist_bundle(bundle_id: str, data: bytes) -> Path:
    """Escritura ATOMICA: se escribe a .tmp y recien ahi os.replace. Un lector nunca ve
    un zip parcial."""
    destino = bundle_path(bundle_id)
    if destino is None:
        raise HandoffError("bundle_id invalido: %r" % bundle_id)
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(".zip.tmp")
    tmp.write_bytes(data)
    os.replace(str(tmp), str(destino))
    return destino


def prune_bundles(max_age_hours: int = 72, keep_last: int = 20) -> int:
    """Vida util del artefacto. Best-effort: NUNCA lanza."""
    import time

    try:
        raiz = _bundles_root()
        if not raiz.is_dir():
            return 0
        zips = sorted(raiz.glob("*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        corte = time.time() - max_age_hours * 3600
        borrados = 0
        for i, p in enumerate(zips):
            if i < keep_last and p.stat().st_mtime >= corte:
                continue
            try:
                p.unlink()
                borrados += 1
            except OSError:
                continue
        return borrados
    except Exception:  # noqa: BLE001
        return 0


def append_ledger(bundle_id: str, manifest: dict) -> None:
    """JSONL fuera del zip. ACA SI va el timestamp. Best-effort: un fallo de bitacora
    nunca tumba la descarga."""
    import datetime

    try:
        raiz = _bundles_root().parent
        raiz.mkdir(parents=True, exist_ok=True)
        fila = {
            "bundle_id": bundle_id,
            "pipeline_name": manifest.get("pipeline_name"),
            "provider": manifest.get("provider"),
            "steps": len(manifest.get("steps") or []),
            "degraded": manifest.get("degraded") or [],
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        with (raiz / "bundles.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        return
