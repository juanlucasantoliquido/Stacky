"""environment_init.py — Plan 89. Inicialización de ambientes.
build_environment_layout / layout_fingerprint: PUROS (sin I/O).
plan_environment: solo LECTURA de FS.
apply_environment: SOLO os.makedirs (nunca borra; ver test centinela F2)."""
import hashlib
import os
import re

_LAYOUT_KINDS = ("entry", "processing", "output", "default")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
_INVALID_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')


def _slug(name: str) -> str:
    """Slug endurecido (C9). Base: regex de api/pipeline_generator.py:27-31 (copiado,
    no importado) + colapso de puntos (sin '..') + guard de reservados Windows."""
    s = re.sub(r"[^a-zA-Z0-9._-]+", "-", (name or "").strip().lower())
    s = re.sub(r"\.\.+", ".", s).strip("-.")      # '../../evil' -> 'evil'
    if s.split(".")[0] in _WINDOWS_RESERVED:      # 'con' -> 'p-con'
        s = "p-" + s
    return s or "proceso"


def is_safe_segment(seg: str) -> bool:
    """Segmento relativo seguro (C6, público — lo importa api/client_profile.py F3).
    Reglas por COMPONENTE (split en / y \\): no vacío, != '..', sin '..' como
    substring, sin caracteres inválidos Windows (<>:"|?* y controles), no reservado
    (CON..LPT9, con o sin extensión), no termina en '.' ni espacio. Además el
    segmento completo: no absoluto, no arranca con separador."""
    seg = (seg or "").strip()
    if not seg or os.path.isabs(seg) or seg.startswith(("/", "\\")):
        return False
    for comp in re.split(r"[\\/]+", seg):
        if (not comp or ".." in comp or _INVALID_CHARS.search(comp)
                or comp.split(".")[0].lower() in _WINDOWS_RESERVED
                or comp.endswith((".", " "))):
            return False
    return True


def build_environment_layout(catalog: list, settings: dict | None) -> list[str]:
    """Rutas RELATIVAS únicas y ordenadas según §4. Nunca lanza; omite lo inválido
    (entradas no-dict del catálogo incluidas, C10). settings None o sin
    folder_layout -> []. Separador interno SIEMPRE '/'. Dedup case-insensitive por
    casefold() preservando la primera en orden sorted (C6)."""
    if not isinstance(settings, dict):
        return []
    folder_layout = settings.get("folder_layout")
    if not isinstance(folder_layout, dict):
        return []
    per_process_subfolder = bool(settings.get("per_process_subfolder"))

    default_segs_raw = folder_layout.get("default", [])
    default_segs = default_segs_raw if isinstance(default_segs_raw, list) else []

    acc: list[str] = []
    for entry in catalog or []:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        segs_raw = folder_layout.get(kind, default_segs) if kind in folder_layout else default_segs
        segs = segs_raw if isinstance(segs_raw, list) else []
        safe_segs = [s for s in segs if isinstance(s, str) and is_safe_segment(s)]
        for seg in safe_segs:
            acc.append(seg)
            if per_process_subfolder:
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    acc.append(f"{seg}/{_slug(name)}")

    out = sorted(set(acc))
    seen: set[str] = set()
    deduped = []
    for p in out:
        key = p.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(p)
    return deduped


def layout_fingerprint(root: str, rel_paths: list[str]) -> str:
    """ADICIÓN — sha256 hex de abspath(root) + '\\n' + '\\n'.join(rel_paths).
    PURO (sin I/O). Identifica un plan concreto para el handshake plan->apply."""
    normalized_root = os.path.abspath(root or "")
    payload = normalized_root + "\n" + "\n".join(rel_paths)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_root(root: str) -> str | None:
    """None si OK; mensaje de error si no. Reglas: string no vacío, os.path.isabs,
    y NO raíz de disco: normpath(root) != normpath(splitdrive(root)[0] + os.sep)
    (cubre 'C:\\' en Windows y '/' en POSIX)."""
    if not root or not isinstance(root, str):
        return "environment_root debe ser una ruta no vacia."
    if not os.path.isabs(root):
        return "environment_root debe ser una ruta absoluta."
    drive = os.path.splitdrive(root)[0]
    disk_root = drive + os.sep if drive else os.sep
    if os.path.normpath(root) == os.path.normpath(disk_root):
        return "environment_root no puede ser la raiz del disco."
    return None


def validate_sandbox_override(override: str, production_root: str) -> str | None:
    """Plan 107 — None si el override es un sandbox seguro; string de error si no.
    PURO salvo os.path.realpath (resuelve symlinks del tramo existente, igual
    criterio que plan_environment). NUNCA lanza.

    Normalización (C1/C8/G9): AMBOS lados pasan por
        _norm(x) = os.path.normcase(os.path.realpath(os.path.abspath(x)))
    - normcase => case-insensitive en Windows (FS case-insensitive), no-op en POSIX.
    - abspath colapsa separadores finales/redundantes ('C:\\prod\\' == 'C:\\prod').
    - realpath resuelve symlinks del tramo existente (mismo criterio que plan_environment).

    Reglas, en orden:
      1) validate_root(override) debe pasar (absoluta, no raíz de disco).
      2) Si production_root es válido (validate_root(production_root) is None),
         override NO puede solaparse con producción:
           a = _norm(override); b = _norm(production_root)
           - a == b                      -> 'sandbox_igual_a_produccion'
           - commonpath([a, b]) == b     -> 'sandbox_dentro_de_produccion'
           - commonpath([a, b]) == a     -> 'produccion_dentro_de_sandbox'
           - ValueError (drives distintos) -> OK (no hay solapamiento posible)
      Si production_root NO es válido/está vacío, se omite el chequeo de
      solapamiento (no hay producción real que proteger) y se acepta si (1) pasó.
    """
    err = validate_root(override)
    if err:
        return err
    if validate_root(production_root or "") is not None:
        return None  # sin producción válida no hay nada que pisar
    a = os.path.normcase(os.path.realpath(os.path.abspath(override)))
    b = os.path.normcase(os.path.realpath(os.path.abspath(production_root)))
    if a == b:
        return "sandbox_igual_a_produccion"
    try:
        common = os.path.commonpath([a, b])
    except ValueError:
        return None  # drives distintos: imposible solapar
    if common == b:
        return "sandbox_dentro_de_produccion"
    if common == a:
        return "produccion_dentro_de_sandbox"
    return None


def plan_environment(root: str, rel_paths: list[str]) -> dict:
    """SOLO LECTURA. Retorna el contrato §4:
    {'root', 'root_exists': os.path.isdir(root),                  # C15
     'layout_fingerprint': layout_fingerprint(root, rel_paths),   # ADICIÓN
     'entries': [{'path', 'status', 'reason'}], 'summary': {...}}
    Por cada rel: final = os.path.abspath(os.path.join(root, rel)).
    'unsafe' reason='fuera_de_root' si
      os.path.commonpath([os.path.realpath(os.path.abspath(root)),
                          os.path.realpath(final)]) != os.path.realpath(os.path.abspath(root))
      (realpath resuelve symlinks del tramo EXISTENTE — C6; ValueError de commonpath
      — drives distintos — también es unsafe).
    'unsafe' reason='path_demasiado_largo' si len(final) > 240 (C6, margen MAX_PATH).
    'to_create' si not os.path.exists(final); 'exists_ok' si os.path.isdir(final);
    'conflict' en el resto (existe y no es dir); reason=None salvo unsafe."""
    abs_root = os.path.abspath(root)
    real_root = os.path.realpath(abs_root)
    entries = []
    summary = {"to_create": 0, "exists_ok": 0, "conflict": 0, "unsafe": 0}
    for rel in rel_paths:
        final = os.path.abspath(os.path.join(root, rel))
        status = None
        reason = None
        if len(final) > 240:
            status = "unsafe"
            reason = "path_demasiado_largo"
        else:
            real_final = os.path.realpath(final)
            try:
                contained = os.path.commonpath([real_root, real_final]) == real_root
            except ValueError:
                contained = False
            if not contained:
                status = "unsafe"
                reason = "fuera_de_root"
        if status is None:
            if not os.path.exists(final):
                status = "to_create"
            elif os.path.isdir(final):
                status = "exists_ok"
            else:
                status = "conflict"
        summary[status] += 1
        entries.append({"path": rel, "status": status, "reason": reason})
    return {
        "root": root,
        "root_exists": os.path.isdir(root),
        "layout_fingerprint": layout_fingerprint(root, rel_paths),
        "entries": entries,
        "summary": summary,
    }


def apply_environment(root: str, rel_paths: list[str]) -> dict:
    """CREA SOLO to_create. Re-planifica server-side (plan_environment) y aplica
    os.makedirs(final, exist_ok=True) ÚNICAMENTE a los to_create (nunca confía en la
    lista del cliente). Cada makedirs va en try/except OSError: el fallo se acumula en
    'failed' y se CONTINÚA con el resto (C7 — jamás excepción hacia arriba).
    Retorna {'created': [rel...], 'skipped_existing': [...], 'conflicts': [...],
    'unsafe': [...], 'failed': [{'path': rel, 'error': str(e)}]}.
    Los conflict/unsafe JAMÁS se tocan. NUNCA borra nada."""
    plan = plan_environment(root, rel_paths)
    created: list[str] = []
    skipped_existing: list[str] = []
    conflicts: list[str] = []
    unsafe: list[str] = []
    failed: list[dict] = []
    for entry in plan["entries"]:
        rel = entry["path"]
        status = entry["status"]
        if status == "exists_ok":
            skipped_existing.append(rel)
        elif status == "conflict":
            conflicts.append(rel)
        elif status == "unsafe":
            unsafe.append(rel)
        elif status == "to_create":
            final = os.path.abspath(os.path.join(root, rel))
            try:
                os.makedirs(final, exist_ok=True)
                created.append(rel)
            except OSError as e:
                failed.append({"path": rel, "error": str(e)})
    return {
        "created": created,
        "skipped_existing": skipped_existing,
        "conflicts": conflicts,
        "unsafe": unsafe,
        "failed": failed,
    }
