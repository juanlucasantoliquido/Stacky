"""services/pipeline_lint.py — Plan 186. Lint determinista de pipelines ADO/GitLab.

PURO: sin red, sin disco, sin config. Recibe texto y devuelve LintReport.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict, replace

import yaml  # PyYAML — ya es dependencia (services/pipeline_renderers.py la importa)

# Plan 195 §6/C1 — masking CANÓNICO común (prefijo + >=8). NO redefinir TOKEN_VALUE_PREFIXES.
from services.secret_masking import mask_token_values  # módulo PURO (sin red/disco/config)

ENGINE_VERSION = "186.1"

SEV_ERROR = "error"
SEV_WARNING = "warning"
SEV_INFO = "info"

# C9 — por encima de este tamaño de YAML no se adjuntan new_yaml de fixes (payload acotado)
MAX_YAML_BYTES_FOR_FIXES = 200_000


@dataclass(frozen=True)
class LintFix:
    description: str        # es-AR, 1 línea, imperativo ("Renombrar el stage duplicado a ...")
    new_yaml: str           # YAML COMPLETO corregido (cirugía de líneas, nunca re-dump)


@dataclass(frozen=True)
class LintFinding:
    code: str               # "PL001".."PL014"
    severity: str           # SEV_ERROR | SEV_WARNING | SEV_INFO
    message: str            # es-AR llano, sin jerga
    line: int | None = None  # 1-based sobre el YAML fuente; None = global
    node: str | None = None  # "stage:Build" | "job:test" | "var:MY_TOKEN" | None
    fix: LintFix | None = None


@dataclass(frozen=True)
class LintReport:
    ok: bool                        # True ⇔ counts["error"] == 0
    findings: tuple  # tuple[LintFinding, ...]
    counts: dict                    # {"error": n, "warning": n, "info": n}
    engine_version: str
    duration_ms: float
    fixes_omitted: bool = False     # C9 — True si el YAML superó MAX_YAML_BYTES_FOR_FIXES

    def to_dict(self) -> dict:
        return asdict(self)


# ── Motor de reglas ────────────────────────────────────────────────────────────

@dataclass
class LintContext:
    provider: str                     # "ado" | "gitlab"
    text: str                         # YAML original
    lines: list                       # text.splitlines()
    data: object                      # yaml.safe_load(text) — dict | list | None
    known_variables: list | None      # nombres caja fuerte (F2); None = no disponible


# [(code, severity, providers, fn, repro)]
_RULES: list = []


def _rule(code: str, severity: str, providers: tuple = ("ado", "gitlab"),
          repro: tuple | None = None):
    """repro: (provider, yaml_minimo_que_dispara_la_regla) — OBLIGATORIO para toda regla
    (ADICIÓN ARQUITECTO 2: el selftest del catálogo lo verifica)."""
    def deco(fn):
        _RULES.append((code, severity, providers, fn, repro))
        return fn
    return deco


def _find_line(ctx: LintContext, needle) -> int | None:
    """Primera línea (1-based) cuyo contenido contiene needle. Best-effort; None si no está."""
    if not needle:
        return None
    for i, ln in enumerate(ctx.lines, start=1):
        if needle in ln:
            return i
    return None


def _find_line_nth(ctx: LintContext, needle: str, nth: int) -> int | None:
    """C3 — n-ésima línea (1-based, nth>=1) que contiene needle. None si hay menos de nth."""
    count = 0
    for i, ln in enumerate(ctx.lines, start=1):
        if needle in ln:
            count += 1
            if count == nth:
                return i
    return None


# ── Modelo de nodos por provider (C1/C2) ────────────────────────────────────────

_ADO_ALLOWED_ROOT = {
    "trigger", "pr", "pool", "variables", "stages", "jobs", "steps", "resources",
    "parameters", "name", "schedules", "extends", "pipelines",
}
_GITLAB_RESERVED = {
    "stages", "variables", "include", "workflow", "default", "image", "services",
    "before_script", "after_script", "cache", "pages",
}
_GL_TOPKEY_RE = re.compile(r"^([A-Za-z_][\w .-]*):")


def _as_name_list(x) -> list:
    if isinstance(x, str):
        return [x]
    if isinstance(x, list):
        return [str(i) for i in x if isinstance(i, (str, int, float))]
    return []


def _ado_has_structure(data) -> bool:
    return isinstance(data, dict) and any(k in data for k in ("stages", "jobs", "steps"))


def _ado_stage_items(data) -> list:
    if not isinstance(data, dict):
        return []
    stages = data.get("stages")
    if not isinstance(stages, list):
        return []
    return [s for s in stages if isinstance(s, dict) and "stage" in s]


def _ado_job_items(container) -> list:
    jobs = container.get("jobs") if isinstance(container, dict) else None
    if not isinstance(jobs, list):
        return []
    return [j for j in jobs if isinstance(j, dict) and ("job" in j or "deployment" in j)]


def _ado_job_name(j):
    return j.get("job") if "job" in j else j.get("deployment")


def _ado_job_groups(data) -> list:
    """Lista de grupos de jobs; cada stage es su propio namespace (o jobs top-level)."""
    stages = _ado_stage_items(data)
    if stages:
        return [_ado_job_items(s) for s in stages]
    return [_ado_job_items(data)]


def _gitlab_jobs(data) -> dict:
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        ks = str(k)
        if isinstance(v, dict) and not ks.startswith(".") and ks not in _GITLAB_RESERVED:
            out[ks] = v
    return out


def _gitlab_needs_refs(needs) -> list:
    refs = []
    if isinstance(needs, str):
        refs.append(needs)
    elif isinstance(needs, list):
        for n in needs:
            if isinstance(n, str):
                refs.append(n)
            elif isinstance(n, dict) and "job" in n:
                refs.append(str(n["job"]))
    return refs


def _duplicates(names) -> list:
    seen = {}
    for n in names:
        if n is None:
            continue
        seen[n] = seen.get(n, 0) + 1
    return [n for n, c in seen.items() if c > 1]


def _find_cycle(edges: dict):
    """DFS con pila de recursión. Devuelve el ciclo como lista [A, B, A] o None."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in edges}
    stack = []
    found = []

    def dfs(n):
        color[n] = GRAY
        stack.append(n)
        for m in sorted(edges.get(n, ())):
            if m not in color:
                continue
            if color[m] == GRAY:
                idx = stack.index(m)
                found.extend(stack[idx:] + [m])
                return True
            if color[m] == WHITE and dfs(m):
                return True
        stack.pop()
        color[n] = BLACK
        return False

    for n in sorted(edges):
        if color[n] == WHITE and dfs(n):
            return found
    return None


# ── Reglas estructurales PL002..PL006 (PL001 se maneja en lint_yaml) ────────────

@_rule("PL002", SEV_ERROR, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n- stage: A\n"))
def _rule_pl002(ctx: LintContext):
    if ctx.provider == "ado":
        return _pl002_ado(ctx)
    return _pl002_gitlab(ctx)


def _pl002_ado(ctx: LintContext):
    findings = []
    if not _ado_has_structure(ctx.data):
        return findings
    stages = _ado_stage_items(ctx.data)
    for name in _duplicates([s.get("stage") for s in stages]):
        line = _find_line_nth(ctx, f"stage: {name}", 2) or _find_line(ctx, f"stage: {name}")
        findings.append(LintFinding(
            "PL002", SEV_ERROR,
            f"El stage '{name}' está definido más de una vez. Los nombres de stage deben ser únicos.",
            line=line, node=f"stage:{name}"))
    for grp in _ado_job_groups(ctx.data):
        for name in _duplicates([_ado_job_name(j) for j in grp]):
            line = (_find_line_nth(ctx, f"job: {name}", 2)
                    or _find_line_nth(ctx, f"deployment: {name}", 2)
                    or _find_line(ctx, f"job: {name}"))
            findings.append(LintFinding(
                "PL002", SEV_ERROR,
                f"El job '{name}' está definido más de una vez dentro de su stage. "
                f"Los nombres de job deben ser únicos.",
                line=line, node=f"job:{name}"))
    return findings


def _pl002_gitlab(ctx: LintContext):
    findings = []
    top = {}
    for i, ln in enumerate(ctx.lines, start=1):
        m = _GL_TOPKEY_RE.match(ln)
        if m:
            top.setdefault(m.group(1), []).append(i)
    for name, lns in top.items():
        if name in _GITLAB_RESERVED:
            continue
        if len(lns) >= 2:
            findings.append(LintFinding(
                "PL002", SEV_ERROR,
                f"La clave top-level '{name}' está definida más de una vez (job duplicado).",
                line=lns[1], node=f"job:{name}"))
    return findings


@_rule("PL003", SEV_ERROR, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n  dependsOn: Z\n"))
def _rule_pl003(ctx: LintContext):
    if ctx.provider == "ado":
        return _pl003_ado(ctx)
    return _pl003_gitlab(ctx)


def _pl003_ado(ctx: LintContext):
    findings = []
    if not _ado_has_structure(ctx.data):
        return findings
    stages = _ado_stage_items(ctx.data)
    stage_names = {s.get("stage") for s in stages}
    for s in stages:
        sname = s.get("stage")
        for dep in _as_name_list(s.get("dependsOn")):
            if dep not in stage_names:
                line = _find_line(ctx, f"dependsOn: {dep}") or _find_line(ctx, f"stage: {sname}")
                findings.append(LintFinding(
                    "PL003", SEV_ERROR,
                    f"El stage '{sname}' depende de '{dep}', que no existe.",
                    line=line, node=f"stage:{sname}"))
    for grp in _ado_job_groups(ctx.data):
        jnames = {_ado_job_name(j) for j in grp}
        for j in grp:
            nm = _ado_job_name(j)
            for dep in _as_name_list(j.get("dependsOn")):
                if dep not in jnames:
                    line = (_find_line(ctx, f"dependsOn: {dep}")
                            or _find_line(ctx, f"job: {nm}")
                            or _find_line(ctx, f"deployment: {nm}"))
                    findings.append(LintFinding(
                        "PL003", SEV_ERROR,
                        f"El job '{nm}' depende de '{dep}', que no existe en su stage.",
                        line=line, node=f"job:{nm}"))
    return findings


def _pl003_gitlab(ctx: LintContext):
    findings = []
    jobs = _gitlab_jobs(ctx.data)
    jobset = set(jobs.keys())
    for name, jd in jobs.items():
        for ref in _gitlab_needs_refs(jd.get("needs")):
            if ref not in jobset:
                line = _find_line(ctx, f"- {ref}") or _find_line(ctx, f"{name}:")
                findings.append(LintFinding(
                    "PL003", SEV_ERROR,
                    f"El job '{name}' necesita '{ref}' (needs), que no existe.",
                    line=line, node=f"job:{name}"))
    return findings


@_rule("PL004", SEV_ERROR, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n  dependsOn: B\n- stage: B\n  dependsOn: A\n"))
def _rule_pl004(ctx: LintContext):
    findings = []
    if ctx.provider == "ado":
        if not _ado_has_structure(ctx.data):
            return findings
        stages = _ado_stage_items(ctx.data)
        stage_names = {s.get("stage") for s in stages}
        edges = {}
        for s in stages:
            n = s.get("stage")
            edges.setdefault(n, set())
            for dep in _as_name_list(s.get("dependsOn")):
                if dep in stage_names:
                    edges[n].add(dep)
        cyc = _find_cycle(edges)
        if cyc:
            findings.append(_cycle_finding(ctx, cyc, "stage"))
        for grp in _ado_job_groups(ctx.data):
            jnames = {_ado_job_name(j) for j in grp}
            jedges = {}
            for j in grp:
                n = _ado_job_name(j)
                jedges.setdefault(n, set())
                for dep in _as_name_list(j.get("dependsOn")):
                    if dep in jnames:
                        jedges[n].add(dep)
            cyc = _find_cycle(jedges)
            if cyc:
                findings.append(_cycle_finding(ctx, cyc, "job"))
    else:
        jobs = _gitlab_jobs(ctx.data)
        jobset = set(jobs.keys())
        edges = {}
        for name, jd in jobs.items():
            edges.setdefault(name, set())
            for ref in _gitlab_needs_refs(jd.get("needs")):
                if ref in jobset:
                    edges[name].add(ref)
        cyc = _find_cycle(edges)
        if cyc:
            findings.append(_cycle_finding(ctx, cyc, "job"))
    return findings


def _cycle_finding(ctx: LintContext, cyc: list, kind: str):
    chain = " → ".join(cyc)
    label = "stages" if kind == "stage" else "jobs"
    node0 = cyc[0]
    needle = f"stage: {node0}" if kind == "stage" else f"{node0}:"
    return LintFinding(
        "PL004", SEV_ERROR,
        f"Hay un ciclo de dependencias entre {label}: {chain}.",
        line=_find_line(ctx, needle), node=f"{kind}:{node0}")


@_rule("PL005", SEV_ERROR, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n  jobs:\n  - job: J\n"))
def _rule_pl005(ctx: LintContext):
    findings = []
    if ctx.provider == "ado":
        if not _ado_has_structure(ctx.data):
            return findings
        for grp in _ado_job_groups(ctx.data):
            for j in grp:
                if "job" not in j:  # deployment ⇒ ejecuta vía strategy (C1)
                    continue
                if not _ado_job_has_steps(j):
                    nm = j.get("job")
                    findings.append(LintFinding(
                        "PL005", SEV_ERROR,
                        f"El job '{nm}' no tiene pasos ejecutables (ni 'steps' ni 'template').",
                        line=_find_line(ctx, f"job: {nm}"), node=f"job:{nm}"))
    else:
        jobs = _gitlab_jobs(ctx.data)
        for name, jd in jobs.items():
            if not any(k in jd for k in ("script", "run", "trigger", "extends")):
                findings.append(LintFinding(
                    "PL005", SEV_ERROR,
                    f"El job '{name}' no tiene pasos ejecutables "
                    f"('script', 'run', 'trigger' o 'extends').",
                    line=_find_line(ctx, f"{name}:"), node=f"job:{name}"))
    return findings


def _ado_job_has_steps(j) -> bool:
    steps = j.get("steps")
    if isinstance(steps, list) and len(steps) > 0:
        return True
    if "template" in j:
        return True
    return False


@_rule("PL006", SEV_INFO, ("ado", "gitlab"),
       repro=("ado", "stages: []\nfoobar: 1\n"))
def _rule_pl006(ctx: LintContext):
    findings = []
    data = ctx.data
    if ctx.provider == "ado":
        if not _ado_has_structure(data):
            findings.append(LintFinding(
                "PL006", SEV_INFO,
                "Estructura mínima no reconocida: se esperaba 'stages', 'jobs' o 'steps' en la raíz.",
                line=None, node=None))
            return findings
        for k in list(data.keys()):
            if k not in _ADO_ALLOWED_ROOT:
                findings.append(LintFinding(
                    "PL006", SEV_INFO,
                    f"Clave '{k}' no reconocida en la raíz del pipeline ADO.",
                    line=_find_line(ctx, f"{k}:"), node=None))
    else:
        if not isinstance(data, dict):
            findings.append(LintFinding(
                "PL006", SEV_INFO,
                "Estructura mínima no reconocida en el pipeline GitLab.",
                line=None, node=None))
            return findings
        for k, v in data.items():
            ks = str(k)
            if ks in _GITLAB_RESERVED:
                continue
            if not isinstance(v, dict):
                findings.append(LintFinding(
                    "PL006", SEV_INFO,
                    f"Clave '{ks}' no reconocida en la raíz (su valor no es un job).",
                    line=_find_line(ctx, f"{ks}:"), node=None))
    return findings


# ── Reglas de variables y secretos PL010..PL014 (walk C4) ───────────────────────

_ADO_REF_RE = re.compile(r"\$\(([A-Za-z_][A-Za-z0-9_.]*)\)")
_GITLAB_REF_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")
_ADO_EXEC_KEYS = ("script", "bash", "powershell", "pwsh")
_GITLAB_SCRIPT_KEYS = ("script", "before_script", "after_script")

_ADO_WL_PREFIXES = ("Build.", "System.", "Agent.", "Pipeline.", "Resources.",
                    "BUILD_", "SYSTEM_", "AGENT_", "PIPELINE_", "TF_")
_GITLAB_WL_PREFIXES = ("CI_", "GITLAB_")
_GITLAB_WL_EXACT = {"HOME", "PATH", "USER", "PWD"}

_SECRET_SUFFIXES = ("_TOKEN", "_PAT", "_PASSWORD", "_SECRET", "_KEY", "_APIKEY")


def _looks_secret(name: str) -> bool:
    return str(name).upper().endswith(_SECRET_SUFFIXES)


def _is_whitelisted(ref: str, provider: str) -> bool:
    if provider == "ado":
        return any(ref.startswith(p) for p in _ADO_WL_PREFIXES)
    return ref in _GITLAB_WL_EXACT or any(ref.startswith(p) for p in _GITLAB_WL_PREFIXES)


def _find_ref_line(ctx: LintContext, ref: str) -> int | None:
    if ctx.provider == "ado":
        return _find_line(ctx, f"$({ref})")
    return _find_line(ctx, f"${{{ref}}}") or _find_line(ctx, f"${ref}")


def _collect_refs(ctx: LintContext):
    """Walk C4 sobre el árbol parseado. Devuelve (refs:set, exec_strings:list[str]).
    NUNCA regex sobre el YAML crudo (los comentarios no generan refs)."""
    refs: set = set()
    exec_strings: list = []
    if ctx.provider == "ado":
        _walk_ado(ctx.data, refs, exec_strings)
    else:
        _walk_gitlab(ctx.data, refs, exec_strings)
    return refs, exec_strings


def _walk_ado(node, refs: set, exec_strings: list):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _ADO_EXEC_KEYS and isinstance(v, str):
                refs.update(_ADO_REF_RE.findall(v))
                exec_strings.append(v)
            elif k == "env" and isinstance(v, dict):
                for ev in v.values():
                    if isinstance(ev, str):
                        refs.update(_ADO_REF_RE.findall(ev))
            _walk_ado(v, refs, exec_strings)
    elif isinstance(node, list):
        for item in node:
            _walk_ado(item, refs, exec_strings)


def _walk_gitlab(node, refs: set, exec_strings: list):
    if isinstance(node, dict):
        for k, v in node.items():
            if k in _GITLAB_SCRIPT_KEYS:
                items = v if isinstance(v, list) else ([v] if isinstance(v, str) else [])
                for it in items:
                    if isinstance(it, str):
                        refs.update(_GITLAB_REF_RE.findall(it))
                        exec_strings.append(it)
            elif k == "variables" and isinstance(v, dict):
                for vv in v.values():
                    if isinstance(vv, str):
                        refs.update(_GITLAB_REF_RE.findall(vv))
            _walk_gitlab(v, refs, exec_strings)
    elif isinstance(node, list):
        for item in node:
            _walk_gitlab(item, refs, exec_strings)


def _declared(ctx: LintContext):
    """Devuelve (declared:set, root_names:set, entries:list[(name, value)])."""
    if ctx.provider == "ado":
        return _ado_declared(ctx.data)
    return _gitlab_declared(ctx.data)


def _collect_var_block(varblock, entries: list, root_names: set, is_root: bool):
    if isinstance(varblock, dict):
        for n, val in varblock.items():
            entries.append((str(n), val))
            if is_root:
                root_names.add(str(n))
    elif isinstance(varblock, list):
        for it in varblock:
            if isinstance(it, dict) and "name" in it:
                entries.append((str(it["name"]), it.get("value")))
                if is_root:
                    root_names.add(str(it["name"]))


def _ado_declared(data):
    entries: list = []
    root_names: set = set()
    if isinstance(data, dict):
        _collect_var_block(data.get("variables"), entries, root_names, True)
        for s in _ado_stage_items(data):
            _collect_var_block(s.get("variables"), entries, root_names, False)
            for j in _ado_job_items(s):
                _collect_var_block(j.get("variables"), entries, root_names, False)
        for j in _ado_job_items(data):  # jobs top-level (sin stages)
            _collect_var_block(j.get("variables"), entries, root_names, False)
    return {n for n, _ in entries}, root_names, entries


def _gitlab_declared(data):
    entries: list = []
    root_names: set = set()
    if isinstance(data, dict):
        rv = data.get("variables")
        if isinstance(rv, dict):
            for n, val in rv.items():
                entries.append((str(n), val))
                root_names.add(str(n))
        for _name, jd in _gitlab_jobs(data).items():
            jv = jd.get("variables")
            if isinstance(jv, dict):
                for n, val in jv.items():
                    entries.append((str(n), val))
    return {n for n, _ in entries}, root_names, entries


@_rule("PL010", SEV_WARNING, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n  jobs:\n  - job: J\n"
                     "    steps:\n    - script: echo $(FANTASMA)\n"))
def _rule_pl010(ctx: LintContext):
    findings = []
    refs, _ = _collect_refs(ctx)
    declared, _root, _entries = _declared(ctx)
    known = set(ctx.known_variables or [])
    for ref in sorted(refs):
        if _is_whitelisted(ref, ctx.provider) or ref in declared or ref in known:
            continue
        findings.append(LintFinding(
            "PL010", SEV_WARNING,
            f"La variable '{ref}' se usa pero no está declarada (ni en la caja fuerte).",
            line=_find_ref_line(ctx, ref), node=f"var:{ref}"))
    return findings


@_rule("PL011", SEV_INFO, ("ado", "gitlab"),
       repro=("ado", "variables:\n  UNUSED: hola\n"
                     "stages:\n- stage: A\n  jobs:\n  - job: J\n"
                     "    steps:\n    - script: echo hi\n"))
def _rule_pl011(ctx: LintContext):
    findings = []
    refs, _ = _collect_refs(ctx)
    _declared_set, root_names, _entries = _declared(ctx)
    for name in sorted(root_names):
        if name not in refs:
            findings.append(LintFinding(
                "PL011", SEV_INFO,
                f"La variable '{name}' se declara en la raíz pero nunca se usa.",
                line=_find_line(ctx, f"{name}:"), node=f"var:{name}"))
    return findings


@_rule("PL012", SEV_WARNING, ("ado", "gitlab"),
       repro=("ado", "variables:\n  DEPLOY_TOKEN: " + ("x" * 16) + "\n"
                     "stages:\n- stage: A\n  jobs:\n  - job: J\n"
                     "    steps:\n    - script: echo hi\n"))
def _rule_pl012(ctx: LintContext):
    findings = []
    _declared_set, _root, entries = _declared(ctx)
    for name, val in entries:
        if not isinstance(val, str):
            continue
        # (b) ADICIÓN 1 — prefijo de token conocido, criterio CANÓNICO secret_masking (prefijo + >=8)
        if mask_token_values(val) != val:
            findings.append(LintFinding(
                "PL012", SEV_WARNING,
                f"La variable '{name}' parece contener un token/secreto hardcodeado "
                f"(prefijo conocido). Movelo a la caja fuerte de variables.",
                line=_find_line(ctx, f"{name}:"), node=f"var:{name}"))
            continue
        # (a) nombre parece secreto + valor con >=12 chars alfanuméricos
        if _looks_secret(name) and sum(1 for c in val if c.isalnum()) >= 12:
            findings.append(LintFinding(
                "PL012", SEV_WARNING,
                f"La variable '{name}' parece contener un secreto en texto plano. "
                f"Movelo a la caja fuerte de variables.",
                line=_find_line(ctx, f"{name}:"), node=f"var:{name}"))
    return findings


@_rule("PL013", SEV_WARNING, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n  jobs:\n  - job: J\n"
                     "    steps:\n    - script: deploy --key $(DEPLOY_TOKEN)\n"))
def _rule_pl013(ctx: LintContext):
    findings = []
    if ctx.known_variables is None:
        return findings  # degradación explícita: la UI no mandó la caja fuerte
    known = set(ctx.known_variables)
    refs, _ = _collect_refs(ctx)
    for ref in sorted(refs):
        if _looks_secret(ref) and ref not in known:
            findings.append(LintFinding(
                "PL013", SEV_WARNING,
                f"El secreto '{ref}' se usa pero no está en la caja fuerte de variables (Plan 94).",
                line=_find_ref_line(ctx, ref), node=f"var:{ref}"))
    return findings


@_rule("PL014", SEV_WARNING, ("ado", "gitlab"),
       repro=("ado", "stages:\n- stage: A\n  jobs:\n  - job: J\n"
                     "    steps:\n    - script: echo $(API_KEY)\n"))
def _rule_pl014(ctx: LintContext):
    findings = []
    _refs, exec_strings = _collect_refs(ctx)
    ref_re = _ADO_REF_RE if ctx.provider == "ado" else _GITLAB_REF_RE
    seen: set = set()
    for s in exec_strings:
        if "echo" not in s:
            continue
        for ref in ref_re.findall(s):
            if _looks_secret(ref) and ref not in seen:
                seen.add(ref)
                findings.append(LintFinding(
                    "PL014", SEV_WARNING,
                    f"Se hace 'echo' de la variable secreta '{ref}': puede filtrarse en los logs.",
                    line=_find_ref_line(ctx, ref), node=f"var:{ref}"))
    return findings


# ── Motor principal ─────────────────────────────────────────────────────────────

def _build_report(findings: list, t0: float, yaml_text: str) -> LintReport:
    fixes_omitted = False
    if len(yaml_text.encode("utf-8", "replace")) > MAX_YAML_BYTES_FOR_FIXES:
        findings = [replace(f, fix=None) if f.fix is not None else f for f in findings]
        fixes_omitted = True
    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        if f.severity in counts:
            counts[f.severity] += 1
    return LintReport(
        ok=counts["error"] == 0,
        findings=tuple(findings),
        counts=counts,
        engine_version=ENGINE_VERSION,
        duration_ms=(time.perf_counter() - t0) * 1000.0,
        fixes_omitted=fixes_omitted,
    )


def lint_yaml(yaml_text: str, provider: str,
              known_variables: list | None = None) -> LintReport:
    """provider: "ado" | "gitlab". known_variables: nombres de la caja fuerte 94
    (los inyecta el ENDPOINT si la UI los mandó; el servicio NO llama a la red)."""
    t0 = time.perf_counter()
    findings: list = []
    # (1) PL001 — parseo
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as e:
        line = None
        mark = getattr(e, "problem_mark", None)
        if mark is not None:
            line = mark.line + 1
        findings.append(LintFinding(
            "PL001", SEV_ERROR,
            "El YAML no se pudo interpretar (error de sintaxis). Revisá indentación y símbolos.",
            line=line, node=None))
        return _build_report(findings, t0, yaml_text)
    # (2) contexto
    ctx = LintContext(
        provider=provider, text=yaml_text, lines=yaml_text.splitlines(),
        data=data, known_variables=known_variables)
    # (3) reglas
    for code, severity, providers, fn, _repro in _RULES:
        if provider not in providers:
            continue
        try:
            findings.extend(fn(ctx) or [])
        except Exception as exc:  # robustez: una regla no puede romper el editor
            findings.append(LintFinding(
                "PL000", SEV_INFO, f"La regla {code} falló internamente: {exc}", line=None))
    findings.sort(key=lambda f: (f.line if f.line is not None else 10 ** 9, f.code))
    # (4) report (+ C9 fix-omission)
    return _build_report(findings, t0, yaml_text)
