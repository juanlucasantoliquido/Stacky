"""failure_doctor.py — Plan 96. PURO: sin I/O, sin config, sin LLM.
Clasifica el texto de un log de CI en clases de fallo conocidas."""
import re

_MAX_LOG_CHARS = 200_000       # se analiza el TAIL (los fallos viven al final)
_SNIPPET_CONTEXT = 15          # líneas antes/después del primer match
_FALLBACK_TAIL_LINES = 40

# Catálogo v1 — 12 clases. Cada entrada: id, regex (compilada, IGNORECASE),
# title en llano, hint accionable. ORDEN = prioridad (gana el primero que matchea
# por línea; un log puede acumular varias clases distintas).
FAILURE_PATTERNS: list[dict] = [
    {"id": "cmd_not_found",
     "regex": re.compile(r"(command not found|no se reconoce como un comando|not recognized as an internal or external command|'[^']+' is not recognized)", re.I),
     "title": "Un comando del script no existe en el runner",
     "hint": "Instala la herramienta en el runner/agent o usa un tag/pool que la tenga; revisa el nombre del comando."},
    {"id": "file_not_found",
     "regex": re.compile(r"(No such file or directory|no se puede encontrar (el archivo|la ruta)|The system cannot find the (file|path)|FileNotFoundError|DirectoryNotFoundException)", re.I),
     "title": "El script busca un archivo o carpeta que no existe",
     "hint": "Verifica la ruta (¿corre en el working_directory correcto?) y que el paso anterior haya generado el archivo. Si es una carpeta de ambiente, inicializala (seccion Ambientes)."},
    {"id": "permission_denied",
     "regex": re.compile(r"(Permission denied|Acceso denegado|Access (is )?denied|EACCES)", re.I),
     "title": "Permisos insuficientes",
     "hint": "El usuario del runner no puede acceder a esa ruta/recurso; ajusta permisos o usa otro runner."},
    {"id": "var_undefined",
     "regex": re.compile(r"(unbound variable|variable .{1,60} (no esta definida|is not defined)|The term '\$\w+' is not recognized|##\[error\].{0,80}variable)", re.I),
     "title": "Una variable no esta definida",
     "hint": "Definila en el spec o como variable segura del proyecto (seccion Variables, plan 94)."},
    {"id": "auth_failed",
     "regex": re.compile(r"(authentication failed|401 Unauthorized|403 Forbidden|invalid credentials|TF401019|HTTP Basic: Access denied)", re.I),
     "title": "Fallo de autenticacion contra un servicio",
     "hint": "Revisa el token/credencial que usa el paso (¿expiro?, ¿scope?); guardalo como variable segura."},
    {"id": "network",
     "regex": re.compile(r"(Connection (refused|timed out)|Could not resolve host|getaddrinfo|Name or service not known|ETIMEDOUT|ECONNREFUSED)", re.I),
     "title": "Problema de red desde el runner",
     "hint": "El runner no llega al host destino: verifica DNS/firewall/VPN del runner."},
    {"id": "timeout",
     "regex": re.compile(r"(job exceeded (the )?timeout|timeout exceeded|ha superado el tiempo|##\[error\].{0,40}timed? ?out)", re.I),
     "title": "El job se quedo sin tiempo",
     "hint": "Sube el timeout del job o parti el trabajo en pasos mas chicos."},
    {"id": "disk_space",
     "regex": re.compile(r"(No space left on device|not enough space|disco lleno|ENOSPC)", re.I),
     "title": "Sin espacio en disco en el runner",
     "hint": "Limpia workspaces/caches del runner o usa otro con mas disco."},
    {"id": "yaml_config",
     "regex": re.compile(r"(yaml invalid|syntax error.{0,40}yaml|mapping values are not allowed|##\[error\].{0,60}template)", re.I),
     "title": "Error de configuracion del pipeline (YAML)",
     "hint": "Corre el preflight '¿Va a funcionar?' (plan 93) para ver el error de lint exacto."},
    {"id": "test_failures",
     "regex": re.compile(r"(\d+ (test(s)?|pruebas?) failed|FAILED \(|AssertionError|Tests? run: .* Failures: [1-9])", re.I),
     "title": "Tests del proyecto fallaron",
     "hint": "No es un problema del pipeline: abri el detalle de tests y arregla el codigo."},
    {"id": "package_manager",
     "regex": re.compile(r"(npm ERR!|pip(3)? .{0,30}error|ERROR: Could not find a version|Unable to resolve dependency|MSB\d{4})", re.I),
     "title": "Fallo instalando dependencias / build",
     "hint": "Revisa versiones/locks del gestor de paquetes; suele ser dependencia inexistente o registry inaccesible."},
    {"id": "exit_code",
     "regex": re.compile(r"(exited with( exit)? code [1-9]\d*|##\[error\]Process completed with exit code [1-9]|ERROR: Job failed: exit code [1-9]\d*)", re.I),
     "title": "Un paso termino con codigo de error",
     "hint": "Mira el fragmento del log: el error real esta unas lineas antes del exit code."},
]


def classify_failure(log_text: str) -> dict:
    """Retorna {'matches': [{'id','title','hint','line_no'}...]  (dedup por id,
    orden de aparicion), 'snippet': str}.
    - Analiza solo el TAIL de _MAX_LOG_CHARS.
    - snippet: ±_SNIPPET_CONTEXT lineas alrededor del PRIMER match; sin matches ⇒
      ultimas _FALLBACK_TAIL_LINES lineas y matches=[] (el caller muestra el
      fallback honesto).
    - PURA, nunca lanza (log vacio ⇒ {'matches': [], 'snippet': ''})."""
    if not log_text:
        return {"matches": [], "snippet": ""}

    text = log_text[-_MAX_LOG_CHARS:] if len(log_text) > _MAX_LOG_CHARS else log_text
    lines = text.splitlines()

    matches: list[dict] = []
    seen_ids: set[str] = set()
    first_match_line: int | None = None

    for line_no, line in enumerate(lines):
        for pattern in FAILURE_PATTERNS:
            if pattern["regex"].search(line):
                if pattern["id"] not in seen_ids:
                    seen_ids.add(pattern["id"])
                    matches.append({
                        "id": pattern["id"],
                        "title": pattern["title"],
                        "hint": pattern["hint"],
                        "line_no": line_no,
                    })
                    if first_match_line is None:
                        first_match_line = line_no
                # una vez que esta clase matcheo en esta linea, no evaluamos
                # las demas clases sobre la MISMA linea (gana la de mayor
                # prioridad definida por el orden del catalogo).
                break

    if first_match_line is not None:
        start = max(0, first_match_line - _SNIPPET_CONTEXT)
        end = min(len(lines), first_match_line + _SNIPPET_CONTEXT + 1)
        snippet = "\n".join(lines[start:end])
    else:
        snippet = "\n".join(lines[-_FALLBACK_TAIL_LINES:])

    return {"matches": matches, "snippet": snippet}
