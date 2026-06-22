#!/usr/bin/env python3
"""Motor (engine) de los roles improver/evaluator del ciclo Kaizen. stdlib pura.

El engine es el "cerebro": produce la PROPUESTA (+ su change_set declarativo) y la EVALUACIÓN,
ambas conforme a los contratos. NUNCA toca el filesystem ni decide: eso es de apply.py y del
gate (run_session.py). Hay dos drivers:

  - mock:   determinista, sin red. Para tests y para correr el loop offline (anota un latido
            en el sandbox playground/). Útil como control y como demo reproducible.
  - claude: invoca el CLI `claude -p` (modo print, read-only). El modelo devuelve JSON que se
            parsea y valida. La config del adapter fija modelo, comando y timeout.

El acoplamiento a un runtime de IA vive SOLO acá (y en el adapter), respetando el diseño
"engine: adapter" de los agentes (agents/improver.agent.md, agents/evaluator.agent.md).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts" / "system"

_SCORE_KEYS = ("value", "correctness", "scope", "reversibility", "measurability")


class EngineError(RuntimeError):
    """Falla del motor (CLI ausente, timeout, salida no parseable, contrato incumplido)."""


# --- utilidades de parsing -----------------------------------------------------------------
def extract_json(text: str) -> dict:
    """Extrae el primer objeto JSON de una salida de modelo (tolera fences y prosa alrededor)."""
    if not text or not text.strip():
        raise EngineError("salida vacía del modelo")
    fence = "```json"
    if fence in text:
        chunk = text.split(fence, 1)[1].split("```", 1)[0]
    elif "```" in text:
        chunk = text.split("```", 1)[1].split("```", 1)[0]
    else:
        chunk = text
    start, end = chunk.find("{"), chunk.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise EngineError("no se encontró objeto JSON en la salida")
    try:
        return json.loads(chunk[start:end + 1])
    except json.JSONDecodeError as exc:
        raise EngineError("JSON inválido en la salida del modelo: %s" % exc)


# Bloques de contenido fuera del JSON: evitan tener que escapar archivos completos como
# strings JSON (la causa típica de "JSON inválido" del modelo).
_FILE_BLOCK = re.compile(
    r"===KAIZEN-FILE:\s*(?P<path>.+?)\s*===\r?\n(?P<body>.*?)\r?\n===KAIZEN-END===", re.DOTALL)


def parse_file_blocks(text: str) -> dict:
    """Extrae {ruta: contenido} de los bloques ===KAIZEN-FILE: ...=== / ===KAIZEN-END===."""
    return {m.group("path").strip(): m.group("body") for m in _FILE_BLOCK.finditer(text)}


def normalize_proposal(proposal: dict, session_id: str, author: str) -> dict:
    """Completa defaults y fuerza session_id/author. No inventa campos faltantes obligatorios."""
    proposal = dict(proposal)
    proposal["session_id"] = session_id
    proposal.setdefault("author", author)
    proposal.setdefault("risks", [])
    proposal.setdefault("artifacts", [])
    return proposal


def normalize_evaluation(evaluation: dict, session_id: str, evaluator: str) -> dict:
    evaluation = dict(evaluation)
    evaluation["session_id"] = session_id
    evaluation.setdefault("evaluator", evaluator)
    evaluation.setdefault("findings", [])
    evaluation.setdefault("blocking", [])
    scores = evaluation.get("scores", {})
    # total derivado para garantizar coherencia con el gate (que recomputa igual).
    if scores:
        evaluation["total"] = sum(int(scores.get(k, 0)) for k in _SCORE_KEYS)
    return evaluation


# --- driver mock ----------------------------------------------------------------------------
class MockEngine:
    """Motor determinista: anota un latido en playground/JOURNAL.md. Sin red, reproducible."""

    name = "mock"

    def propose(self, context: dict) -> tuple[dict, dict]:
        sid = context["session_id"]
        it = context.get("iteration", 0)
        rel = "playground/JOURNAL.md"
        current = context.get("files", {}).get(rel, "# Kaizen Playground — Journal\n")
        line = "- [%s] latido de automejora #%d (sesión %s)\n" % (st_now(), it, sid)
        new_content = current if current.endswith("\n") else current + "\n"
        new_content += line
        proposal = normalize_proposal({
            "title": "Anotar latido de automejora #%d" % it,
            "summary": "Agrega una línea trazable al journal del sandbox playground/.",
            "motivation": "Ejercitar el ciclo AOTL de punta a punta de forma segura y reproducible.",
            "scope": {"in": [rel], "out": ["cualquier archivo fuera de playground/"]},
            "reversibility": {"reversible": True, "rollback": "borrar la línea agregada a %s" % rel},
            "success_metric": "el gate de regresión (selfcheck) sigue en verde tras el cambio",
        }, sid, "agent:improver:mock")
        change_set = {
            "session_id": sid,
            "note": "latido mock",
            "changes": [{"path": rel, "action": "modify", "content": new_content}],
        }
        return proposal, change_set

    def evaluate(self, proposal: dict, measurement: dict, context: dict) -> dict:
        sid = context["session_id"]
        passed = bool(measurement.get("passed"))
        if passed:
            scores = {"value": 2, "correctness": 3, "scope": 3, "reversibility": 3, "measurability": 3}
            verdict, conf = "accept", 0.95
            findings = ["la métrica de regresión pasó tras aplicar el cambio"]
        else:
            scores = {"value": 1, "correctness": 0, "scope": 2, "reversibility": 3, "measurability": 2}
            verdict, conf = "reject", 0.9
            findings = ["la métrica de regresión FALLÓ: %s" % measurement.get("summary", "")]
        return normalize_evaluation({
            "findings": findings,
            "scores": scores,
            "blocking": [] if passed else ["B2"],
            "preliminary_verdict": verdict,
            "confidence": conf,
        }, sid, "agent:evaluator:mock")


def st_now() -> str:
    import datetime as _dt
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


# --- driver claude --------------------------------------------------------------------------
_PROPOSAL_SKELETON = """{
  "title": "...", "summary": "...", "motivation": "...",
  "scope": {"in": ["..."], "out": ["..."]},
  "risks": ["..."],
  "reversibility": {"reversible": true, "rollback": "OBLIGATORIO: cómo se deshace"},
  "success_metric": "cómo se mide objetivamente que mejoró"
}"""

_EVAL_SKELETON = """{
  "findings": ["hallazgo con evidencia de la medición"],
  "scores": {"value": 0, "correctness": 0, "scope": 0, "reversibility": 0, "measurability": 0},
  "blocking": [],
  "preliminary_verdict": "accept|iterate|reject",
  "confidence": 0.0
}"""


class ClaudeCliEngine:
    """Motor que delega improver/evaluator en el CLI `claude -p` (print, read-only)."""

    name = "claude"

    def __init__(self, command: str = "claude", model: str = "claude-sonnet-4-6",
                 timeout_seconds: int = 180):
        self.command = command
        self.model = model
        self.timeout = int(timeout_seconds)

    def _system(self, role: str) -> str:
        path = PROMPTS / ("%s.system.md" % role)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _run(self, system: str, user: str) -> str:
        # En Windows, `claude` suele ser un shim .CMD: hay que resolver la ruta real con
        # shutil.which (CreateProcess no aplica PATHEXT). El system prompt va plegado en el
        # stdin (no como arg multilínea) para no romper el shim .cmd.
        exe = shutil.which(self.command)
        if not exe:
            raise EngineError("CLI %r no encontrado en PATH" % self.command)
        cmd = [exe, "-p", "--model", self.model, "--output-format", "text"]
        prompt = ("%s\n\n---\n\n%s" % (system, user)) if system else user
        try:
            res = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                 timeout=self.timeout, encoding="utf-8")
        except FileNotFoundError:
            raise EngineError("CLI %r no ejecutable" % self.command)
        except subprocess.TimeoutExpired:
            raise EngineError("timeout de %ds esperando al modelo" % self.timeout)
        if res.returncode != 0:
            raise EngineError("claude salió con código %d: %s" %
                              (res.returncode, (res.stderr or "").strip()[:500]))
        return res.stdout

    @staticmethod
    def _context_block(context: dict) -> str:
        lines = ["## Contexto observado de kaizen/", "objetivo: %s" % context.get("objective", "")]
        if context.get("tree"):
            lines.append("\n### Archivos editables (foco):")
            lines += ["- %s" % p for p in context["tree"]]
        if context.get("recent_decisions"):
            lines.append("\n### Decisiones recientes:")
            lines += ["- %s" % d for d in context["recent_decisions"]]
        for rel, content in (context.get("files") or {}).items():
            lines.append("\n### Contenido actual de %s:\n```\n%s\n```" % (rel, content))
        lines.append("\n### Rutas PROHIBIDAS (no las toques): %s" %
                     ", ".join(context.get("protected", [])))
        return "\n".join(lines)

    def propose(self, context: dict) -> tuple[dict, dict]:
        sid = context["session_id"]
        ctx = self._context_block(context)
        user = (
            ctx + "\n\n## Tarea\n"
            "Proponé UNA mejora pequeña, valiosa y reversible DENTRO del foco.\n\n"
            "Respondé en DOS partes:\n"
            "PARTE 1 — un bloque ```json con la propuesta y el plan de cambios "
            "(SIN el contenido de los archivos):\n"
            '{"proposal": ' + _PROPOSAL_SKELETON + ', "change_set": {"changes": '
            '[{"path": "ruta/relativa", "action": "create|modify|delete"}]}}\n\n'
            "PARTE 2 — para CADA archivo con action create o modify, el contenido COMPLETO "
            "resultante, delimitado EXACTAMENTE así (texto crudo, SIN fences ni JSON adentro):\n"
            "===KAIZEN-FILE: ruta/relativa===\n"
            "<contenido completo del archivo>\n"
            "===KAIZEN-END===\n\n"
            "Reglas duras: toda ruta dentro del foco; rollback y success_metric obligatorios; "
            "NO pongas el contenido de archivos dentro del JSON (va SOLO en los bloques de la PARTE 2)."
        )
        out = self._run(self._system("improver"), user)
        data = extract_json(out)
        if "proposal" not in data or "change_set" not in data:
            raise EngineError("la respuesta del improver no trae 'proposal' + 'change_set'")
        proposal = normalize_proposal(data["proposal"], sid, "agent:improver:claude")
        change_set = data["change_set"]
        change_set["session_id"] = sid
        blocks = parse_file_blocks(out)
        for ch in change_set.get("changes", []):
            if ch.get("action") in ("create", "modify") and not ch.get("content"):
                if ch.get("path") in blocks:
                    ch["content"] = blocks[ch["path"]]
                else:
                    raise EngineError("falta el bloque de contenido (PARTE 2) para %s" % ch.get("path"))
        return proposal, change_set

    def evaluate(self, proposal: dict, measurement: dict, context: dict) -> dict:
        sid = context["session_id"]
        user = (
            "## Propuesta\n```json\n%s\n```\n\n## Medición real (success_metric)\n"
            "passed=%s\nsalida:\n```\n%s\n```\n\n## Tarea\nEvaluá con la rúbrica C1..C5 (0-3 c/u). "
            "Sé severo y honesto; si dudás, bajá confidence (eso escala a humano). "
            "Devolvé SOLO un bloque ```json con: {\"evaluation\": %s}\n" %
            (json.dumps(proposal, ensure_ascii=False, indent=2),
             measurement.get("passed"), (measurement.get("summary") or "")[:1500], _EVAL_SKELETON)
        )
        data = extract_json(self._run(self._system("evaluator"), user))
        ev = data.get("evaluation", data)
        return normalize_evaluation(ev, sid, "agent:evaluator:claude")


# --- factory --------------------------------------------------------------------------------
def make_engine(adapter_cfg: dict, override_driver: str | None = None):
    eng = (adapter_cfg or {}).get("engine", {}) or {}
    driver = override_driver or eng.get("driver", "mock")
    if driver == "mock":
        return MockEngine()
    if driver == "claude":
        return ClaudeCliEngine(
            command=eng.get("command", "claude"),
            model=eng.get("model", "claude-sonnet-4-6"),
            timeout_seconds=eng.get("timeout_seconds", 180),
        )
    raise EngineError("driver de engine desconocido: %r" % driver)
