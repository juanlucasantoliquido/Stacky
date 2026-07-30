"""services/pipeline_diff.py — Plan 250 F2. Gates por DELTA + sello de preservacion.

Un patch NO se ofrece si INTRODUCE un error. Pero un pipeline de produccion que ya
tiene hallazgos tiene que seguir siendo editable: por eso los gates son por DELTA
(bloquea lo que no estaba antes), nunca por valor absoluto. Un gate que se pone rojo
por una falta ajena enseña al operador a ignorar el semaforo, que es el peor
resultado posible.

PURO salvo la verificacion opcional de rutas contra `repo_root` que hace RS006.
"""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from typing import Optional

import yaml

from services.cicd_semantic_rules import MODE_AUDIT, MODE_NL_STRICT, check_semantics
from services.pipeline_lint import SEV_ERROR, SEV_WARNING, lint_yaml
from services.pipeline_renderers import scan_unsupported

DIFF_VERSION = "250.1"

GATE_LINT = "LINT"
GATE_SEM_AUDIT = "SEM_AUDIT"
GATE_SEM_NL_STRICT = "SEM_NL_STRICT"
GATE_PRESERVACION = "G-PRESERVACION"
GATE_SECRET = "SECRET"          # Plan 260 (v3, C8) — NO existia: publico, cruza el modulo

_INDICE_RE = re.compile(r"\[\d+\]")
_PASO_KEYS = ("task", "script", "checkout", "powershell", "bash", "pwsh",
              "publish", "download", "template")


# ── Identidad de finding: DOS claves, porque son DOS formas distintas ────────

def _sem_key(f) -> tuple:
    """SemanticFinding: la posicion es un PATH.
    `stages[1].jobs[0].steps[4]` -> `stages[].jobs[].steps[]`."""
    return (f.code, f.message, _INDICE_RE.sub("[]", getattr(f, "location", "") or ""))


def _lint_key(f) -> tuple:
    """LintFinding: NO tiene `location`. Tiene `node` ("stage:Build", "var:MY_TOKEN"),
    que es ESTABLE ante una insercion, y `line`, que NO lo es.

    REGLA DURA: `f.line` NUNCA entra en la clave. Insertar 8 lineas convierte el
    finding de la linea 40 en el de la 48 y TODOS los posteriores al hunk se contarian
    como nuevos. Si `node` es None la identidad queda (code, message) y punto: perder
    granularidad es infinitamente preferible a inventar 30 findings que no lo son.
    """
    return (f.code, f.message, getattr(f, "node", None) or "")


# ── Contratos ────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GateDelta:
    gate: str
    passed: bool
    new_errors: tuple
    new_warnings: tuple
    resolved: tuple          # findings que el patch HIZO DESAPARECER (es valor: se muestra)
    skipped_reason: str = ""


@dataclass(frozen=True)
class Preservation:
    ok: bool
    comments_before: int
    comments_after: int
    unsupported_lost: tuple
    lines_untouched: int
    lines_total_before: int
    detail: str = ""


@dataclass(frozen=True)
class EditReview:
    ok: bool
    gates: tuple
    hunks: tuple
    summary: str
    unsupported: tuple
    preservation: Preservation


# ── Helpers ──────────────────────────────────────────────────────────────────

def _comentarios(texto: str) -> int:
    return sum(1 for l in (texto or "").splitlines() if l.lstrip().startswith("#"))


def _delta(antes: list, despues: list, keyfn) -> tuple:
    k_antes = {keyfn(f) for f in antes}
    k_despues = {keyfn(f) for f in despues}
    nuevos = [f for f in despues if keyfn(f) not in k_antes]
    resueltos = [f for f in antes if keyfn(f) not in k_despues]
    # dedup estable por clave
    vistos: set = set()
    unicos = []
    for f in nuevos:
        k = keyfn(f)
        if k in vistos:
            continue
        vistos.add(k)
        unicos.append(f)
    return tuple(unicos), tuple(resueltos)


def _dedentar(lineas: list) -> str:
    utiles = [l for l in lineas if l.strip()]
    if not utiles:
        return ""
    margen = min(len(l) - len(l.lstrip()) for l in utiles)
    return "\n".join(l[margen:] if len(l) >= margen else l for l in lineas)


def doc_sintetico(hunks: tuple) -> Optional[str]:
    """Documento MINIMO con SOLO los bloques que el patch introdujo.

    Sin `pool`: el gate estricto existe para juzgar lo que Stacky ESCRIBE (RS004 script
    inline, RS008 tarea fuera del catalogo), no para inventarle un agente al operador y
    disparar RS001/RS002 contra un pool que no eligio.
    """
    nuevas: list = []
    for h in hunks:
        if tuple(h.after) == tuple(h.before):
            continue
        nuevas.extend(list(h.after))
    if not any(l.strip() for l in nuevas):
        return None
    crudo = _dedentar(nuevas)
    try:
        doc = yaml.safe_load(crudo)
    except yaml.YAMLError:
        return None
    if not isinstance(doc, list):
        return None
    pasos = [p for p in doc if isinstance(p, dict) and any(k in p for k in _PASO_KEYS)]
    if not pasos:
        return None
    cuerpo = "\n".join("    " + l if l.strip() else "" for l in crudo.splitlines())
    return ("stages:\n- stage: EdicionStacky\n  jobs:\n  - job: EdicionStacky\n"
            "    steps:\n%s\n" % cuerpo)


def _preservacion(before: str, after: str, hunks: tuple, verb: str) -> Preservation:
    c_antes, c_despues = _comentarios(before), _comentarios(after)
    perdidos_a_proposito = 0
    if verb == "remove_step":
        # unica excepcion legitima y acotada: los comentarios que vivian DENTRO del
        # rango del paso borrado se van con el, a proposito.
        for h in hunks:
            if tuple(h.after):
                continue
            perdidos_a_proposito += sum(
                1 for l in h.before if l.lstrip().startswith("#"))
    perdidos = max(0, (c_antes - perdidos_a_proposito) - c_despues)

    antes_u, despues_u = set(scan_unsupported(before)), set(scan_unsupported(after))
    unsupported_lost = tuple(sorted(antes_u - despues_u))

    lineas_antes = before.splitlines()
    sm = difflib.SequenceMatcher(a=lineas_antes, b=after.splitlines(), autojunk=False)
    intactas = sum(bloque.size for bloque in sm.get_matching_blocks())

    detalle = ""
    if perdidos:
        detalle = "se perderian %d comentario(s)" % perdidos
    if unsupported_lost:
        detalle = (detalle + "; " if detalle else "") + (
            "desaparece(n) construccion(es) no modelada(s): %s"
            % ", ".join(unsupported_lost))

    return Preservation(
        ok=(perdidos == 0 and not unsupported_lost),
        comments_before=c_antes, comments_after=c_despues,
        unsupported_lost=unsupported_lost,
        lines_untouched=intactas, lines_total_before=len(lineas_antes),
        detail=detalle,
    )


def formato_preservacion(p: Preservation) -> str:
    base = ("Se preservan %d/%d comentarios y %d construcciones no modeladas; "
            "%d de %d lineas quedan byte-identicas."
            % (p.comments_after, p.comments_before, len(p.unsupported_lost),
               p.lines_untouched, p.lines_total_before))
    return base if p.ok else base + " " + p.detail


# ── El review ────────────────────────────────────────────────────────────────

def review_patch(before: str, after: str, hunks: tuple, *, profile: str,
                 repo_root: Optional[str] = None, verb: str = "",
                 secret_gate: bool = True) -> EditReview:
    """Los 5 gates sobre (before, after). Nunca lanza.

    `secret_gate` (Plan 260, v3 C8): la flag se lee AFUERA, en el llamador —
    este módulo se mantiene sin ninguna referencia al ajuste global del arnés."""
    hunks = tuple(hunks or ())
    gates: list = []

    # ── G-LINT (delta) ───────────────────────────────────────────────────────
    r_antes = lint_yaml(before, "ado")
    r_despues = lint_yaml(after, "ado")
    nuevos, resueltos = _delta(list(r_antes.findings), list(r_despues.findings), _lint_key)
    lint_err = tuple(f for f in nuevos if f.severity == SEV_ERROR)
    gates.append(GateDelta(
        gate=GATE_LINT, passed=not lint_err, new_errors=lint_err,
        new_warnings=tuple(f for f in nuevos if f.severity == SEV_WARNING),
        resolved=resueltos))
    # Plan 260 (v4, C4): capturado ACA, antes de que G-SEM reasigne `nuevos` (:220).
    # Insertar el gate de secretos mas abajo -agrupado con el resto de este plan-
    # leeria los findings de G-SEM (codigos SEC*/OPT*), que NUNCA matchean
    # SECRET_BLOCKING_LINT (codigos PL*): el gate quedaria passed=True siempre.
    nuevos_lint = nuevos

    # ── G-SECRET (delta, SOLO lint: PL012/PL014) ─────────────────────────────
    from services.ci_env_gate import SECRET_BLOCKING_LINT  # noqa: PLC0415

    _fuga = tuple(f for f in nuevos_lint if f.code in SECRET_BLOCKING_LINT) if secret_gate else ()
    gates.append(GateDelta(
        gate=GATE_SECRET, passed=not _fuga, new_errors=_fuga,
        new_warnings=(), resolved=()))

    # ── G-SEM (audit, documento completo, delta) ─────────────────────────────
    razon = "" if repo_root else ("sin `repo_root`: RS006 no se evalua y NO se reporta "
                                  "como validado")
    try:
        s_antes = check_semantics(before, profile=profile, repo_root=repo_root,
                                  mode=MODE_AUDIT)
        s_despues = check_semantics(after, profile=profile, repo_root=repo_root,
                                    mode=MODE_AUDIT)
        nuevos, resueltos = _delta(s_antes, s_despues, _sem_key)
        sem_err = tuple(f for f in nuevos if f.severity == SEV_ERROR)
        gates.append(GateDelta(
            gate=GATE_SEM_AUDIT, passed=not sem_err, new_errors=sem_err,
            new_warnings=tuple(f for f in nuevos if f.severity == SEV_WARNING),
            resolved=resueltos, skipped_reason=razon))
    except Exception as e:  # una regla rota no puede tumbar el editor
        gates.append(GateDelta(GATE_SEM_AUDIT, True, (), (), (),
                               "no se pudo evaluar: %s" % e))

    # ── G-SEM (nl_strict, SOLO los bloques introducidos, valor absoluto) ─────
    sintetico = doc_sintetico(hunks)
    if sintetico is None:
        gates.append(GateDelta(
            GATE_SEM_NL_STRICT, True, (), (), (),
            "el patch no introduce pasos nuevos evaluables de forma aislada"))
    else:
        try:
            findings = check_semantics(sintetico, profile=profile, repo_root=repo_root,
                                       mode=MODE_NL_STRICT)
            err = tuple(f for f in findings if f.severity == SEV_ERROR)
            gates.append(GateDelta(
                gate=GATE_SEM_NL_STRICT, passed=not err, new_errors=err,
                new_warnings=tuple(f for f in findings if f.severity == SEV_WARNING),
                resolved=(), skipped_reason=razon))
        except Exception as e:
            gates.append(GateDelta(GATE_SEM_NL_STRICT, True, (), (), (),
                                   "no se pudo evaluar: %s" % e))

    # ── G-PRESERVACION ───────────────────────────────────────────────────────
    preservation = _preservacion(before, after, hunks, verb)
    gates.append(GateDelta(
        gate=GATE_PRESERVACION, passed=preservation.ok, new_errors=(),
        new_warnings=(), resolved=(),
        skipped_reason=("" if preservation.ok else preservation.detail)))

    ok = all(g.passed for g in gates)
    agregados = sum(1 for h in hunks if not h.before and h.after)
    quitados = sum(1 for h in hunks if h.before and not h.after)
    cambiados = sum(1 for h in hunks if h.before and h.after)
    summary = ("%d bloque(s) agregado(s), %d quitado(s), %d modificado(s). %s"
               % (agregados, quitados, cambiados, formato_preservacion(preservation)))

    return EditReview(ok=ok, gates=tuple(gates), hunks=hunks, summary=summary,
                      unsupported=scan_unsupported(after), preservation=preservation)
