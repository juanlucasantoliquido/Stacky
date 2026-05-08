"""
screen_error_detector.py — In-flight UI error detection for QA UAT Free-Form.

PROBLEM
    Cuando Playwright interactúa con la Agenda Web (ASP.NET WebForms), un
    error de validación o un mensaje de bloqueo en pantalla NO siempre rompe
    el test. Playwright sigue ejecutando steps sobre un formulario que ya
    no avanza, y el diagnóstico recién aparece minutos después en el
    `uat_failure_analyzer`. El operador percibe el problema como "el agente
    se confundió" cuando en realidad la app le mostró un error y nadie lo
    leyó.

DESIGN
    Esta tool ofrece DOS modos de detección, ambos OPT-IN:

    1. DOM-based (rápido, sin LLM, default cuando el flag está ON)
       Inyectamos en el .spec.ts (vía Jinja2) un helper `__detectScreenErrors`
       que después de cada acción (fill / click / select / check / etc.)
       escanea el DOM buscando patrones conocidos de error de la Agenda Web:
         - ASP.NET validators (`[id*='Error']`, `[id*='Validator']`)
         - Field-level errors (`.field-validation-error`, `.error-message`)
         - Inline alerts (`.alert-danger`, `[role='alert']`)
         - Modal de error (`.modal.show .alert-danger`)
         - Texto-rojo embebido en spans/labels (heurística: `style*='color:red'`)
       Si encuentra texto de error VISIBLE Y NO VACÍO el step falla con un
       mensaje estructurado: "UI error detectado tras step <n>: <texto>".

    2. Vision-LLM (opt-in adicional via flag)
       Levanta un servidor HTTP local en 127.0.0.1:<port> que recibe el
       screenshot post-step, lo manda al LLM (gpt-4o por defecto, vía
       GitHub Models API ya disponible vía gh auth) y responde si detectó
       error visual + el texto. El spec.ts hace POST con la screenshot
       cuando `process.env.QA_UAT_VISION_DETECTOR_URL` está seteada.

    Ambos modos persisten un artefacto `screen_errors_<sid>.json` dentro
    de evidence/<run>/<sid>/ con la lista de errores capturados, que el
    `uat_failure_analyzer.py` consume para enriquecer el diagnóstico.

CONTRACT
    Las funciones públicas son:
      - DOM_ERROR_SELECTORS         — lista de selectores CSS a inyectar en el spec
      - DOM_ERROR_DETECTOR_JS       — función JS lista para incluir en el .spec.ts
      - analyze_screenshot(...)     — vision-LLM detection (opcional)
      - run_server(...)             — HTTP entry point para vision LLM
      - persist_error(evidence_dir, scenario_id, entry) — append errors

CLI
    # Modo servidor (vision LLM):
    python screen_error_detector.py serve --port 5061 [--model gpt-4o]

    # Modo standalone (vision-LLM single-shot, útil para debug):
    python screen_error_detector.py analyze --image path/to/screenshot.png

OPT-IN
    Toda la integración es opt-in. Sin el flag --detect-screen-errors en el
    pipeline, este módulo no se importa y el spec generado es idéntico al
    pre-existente.
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional

logger = logging.getLogger("stacky.qa_uat.screen_error_detector")

_TOOL_VERSION = "1.0.0"

# Default vision model. gpt-4o supports vision via GitHub Models inference
# endpoint y está cubierto por la suscripción Copilot Pro del operador.
_DEFAULT_VISION_MODEL = os.environ.get("STACKY_QA_UAT_VISION_MODEL", "gpt-4o")
_DEFAULT_PORT = int(os.environ.get("STACKY_QA_UAT_VISION_PORT", "5061"))


# ── DOM heuristics catalog ────────────────────────────────────────────────────
#
# Selectores conocidos de Agenda Web (ASP.NET WebForms) que típicamente
# muestran errores de validación o estados de bloqueo. El orden es
# defensivo: van primero los selectores con más señal y baja tasa de falsos
# positivos (aria/role/clase explícita) y al final las heurísticas blandas
# (color rojo, ids con sufijo Error*).
#
# IMPORTANTE: este catálogo se inyecta en TypeScript dentro del .spec.ts, así
# que cualquier cambio acá se refleja automáticamente en cada test generado.
DOM_ERROR_SELECTORS: list[str] = [
    # ASP.NET validators (Required/Range/CompareValidator, etc.)
    "span[id*='Error']:not([style*='display:none']):not([style*='display: none'])",
    "span[id*='Validator']:not([style*='display:none']):not([style*='display: none'])",
    "[id*='ErrorSummary']:not([style*='display:none']):not([style*='display: none'])",
    # Bootstrap/Material alert containers
    ".alert.alert-danger:not(.d-none)",
    ".alert-error:not(.d-none)",
    "[role='alert']:not([hidden])",
    # Field-level errors (Razor / Bootstrap convenciones)
    ".field-validation-error",
    ".error-message",
    ".help-block.error",
    "label.error",
    # Modales que típicamente muestran error de bloqueo
    ".modal.show .alert-danger",
    ".modal.in .alert-danger",
    # Heurística blanda: rojo embebido (último recurso)
    "span[style*='color:red']",
    "span[style*='color: red']",
    "label[style*='color:red']",
    "div[style*='color:red']",
]

# Patrones de texto que delatan estados de bloqueo, aunque el contenedor
# no esté en la lista anterior (ej. apps que renderizan errores en spans
# genéricos sin clase distintiva).
DOM_ERROR_TEXT_PATTERNS: list[str] = [
    "es requerido",
    "campo requerido",
    "obligatorio",
    "no puede estar vacío",
    "no puede ser vacío",
    "no se permite",
    "valor inválido",
    "valor invalido",
    "formato inválido",
    "formato invalido",
    "error al guardar",
    "error de validación",
    "error de validacion",
    "no autorizado",
]

# JS function injectada en el spec.ts vía Jinja2. Se ejecuta dentro del
# contexto de la página con `page.evaluate`, devuelve la lista de errores
# detectados (vacía si todo OK). Ver `playwright_test.spec.ts.j2` (block
# `screen_error_helpers`) para cómo se consume.
#
# NOTA: este string se incrusta tal cual en el .spec.ts. Mantener sintaxis
# JS-válida (single quotes para strings dentro). Cualquier `${...}` debe
# escaparse o evitarse para no chocar con template literals del spec.
DOM_ERROR_DETECTOR_JS: str = """
async function __detectScreenErrors(page) {
  // Ejecuta in-page para minimizar round-trips. Devuelve { errors: string[] }.
  const SELECTORS = __SELECTORS__;
  const TEXT_PATTERNS = __TEXT_PATTERNS__;
  return await page.evaluate(({ SELECTORS, TEXT_PATTERNS }) => {
    const out = [];
    const seen = new Set();
    function record(text, source) {
      const trimmed = (text || '').trim();
      if (!trimmed || trimmed.length < 2) return;
      // Limit each error to 240 chars to keep the artefact small.
      const clipped = trimmed.length > 240 ? trimmed.slice(0, 240) + '...' : trimmed;
      const key = source + '|' + clipped;
      if (seen.has(key)) return;
      seen.add(key);
      out.push({ text: clipped, source });
    }
    function isVisible(el) {
      if (!el) return false;
      const style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      const rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }
    // Pass 1: selector-based
    for (const sel of SELECTORS) {
      let nodes;
      try { nodes = document.querySelectorAll(sel); } catch (_e) { continue; }
      nodes.forEach((el) => {
        if (!isVisible(el)) return;
        const txt = (el.innerText || el.textContent || '').trim();
        if (txt) record(txt, sel);
      });
    }
    // Pass 2: text-pattern scan over body — only runs when selector pass found
    // nothing, to avoid false positives on legitimate Spanish copy.
    if (out.length === 0) {
      const bodyText = (document.body && document.body.innerText) || '';
      const lower = bodyText.toLowerCase();
      for (const pat of TEXT_PATTERNS) {
        const idx = lower.indexOf(pat.toLowerCase());
        if (idx >= 0) {
          // Capturamos los 120 chars alrededor del match para contexto.
          const start = Math.max(0, idx - 40);
          const end = Math.min(bodyText.length, idx + pat.length + 80);
          record(bodyText.slice(start, end), 'text:' + pat);
          break;
        }
      }
    }
    return { errors: out };
  }, { SELECTORS, TEXT_PATTERNS });
}
"""


def render_dom_detector_js() -> str:
    """Materializa DOM_ERROR_DETECTOR_JS sustituyendo las constantes.

    Devolvé un bloque TS auto-contenido que el template Jinja2 puede
    incrustar tal cual en el .spec.ts. El template usa este helper para
    no tener que regenerar lógica JS en cada renderizado.
    """
    return (
        DOM_ERROR_DETECTOR_JS
        .replace("__SELECTORS__", json.dumps(DOM_ERROR_SELECTORS))
        .replace("__TEXT_PATTERNS__", json.dumps(DOM_ERROR_TEXT_PATTERNS))
    )


# ── Vision-LLM analyzer (opt-in) ──────────────────────────────────────────────


class VisionDetectorError(RuntimeError):
    """Raised when the vision-LLM analyzer cannot complete a request."""


_VISION_SYSTEM_PROMPT = (
    "You are a QA UI inspector. You receive a screenshot of an internal "
    "Spanish-language web app (ASP.NET WebForms style). Look ONLY for visible "
    "error messages, validation warnings, blocking modals, or 'campo requerido' "
    "indicators. Ignore decorative red colours that are not error text.\n\n"
    "Reply ONLY with a strict JSON object:\n"
    "{\n"
    '  "has_error": true|false,\n'
    '  "error_text": "<copy the visible error text in Spanish, max 240 chars>",\n'
    '  "category": "validation|blocking_modal|server_error|none",\n'
    '  "confidence": "high|medium|low"\n'
    "}\n"
    "If there is no error, return has_error=false and error_text=\"\"."
)


def analyze_screenshot(
    image_bytes: bytes,
    *,
    model: str = _DEFAULT_VISION_MODEL,
    timeout: int = 30,
) -> dict:
    """Send a screenshot to the vision LLM and return a normalised verdict.

    Returns a dict with the same shape we persist:
      {
        "has_error": bool,
        "error_text": str,
        "category": str,
        "confidence": str,
        "model": str,
        "duration_ms": int,
      }

    Raises VisionDetectorError when the LLM call fails or the response
    cannot be parsed. Callers are expected to swallow this error and
    record `has_error=false, capture_error=...` so the test continues.
    """
    started = time.time()
    try:
        from llm_client import call_llm_vision  # local import — opt-in
    except ImportError as exc:
        raise VisionDetectorError(
            f"llm_client.call_llm_vision is not available: {exc}"
        ) from exc

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:image/png;base64,{b64}"

    try:
        result = call_llm_vision(
            model=model,
            system=_VISION_SYSTEM_PROMPT,
            user="Analiza el screenshot adjunto y devolvé el JSON pedido.",
            images=[data_url],
            max_tokens=200,
            timeout=timeout,
        )
    except Exception as exc:
        raise VisionDetectorError(f"vision LLM call failed: {exc}") from exc

    text = (result.get("text") or "").strip()
    parsed = _safe_parse_json(text) or {}
    has_error = bool(parsed.get("has_error", False))
    error_text = str(parsed.get("error_text", "") or "")[:240]
    category = str(parsed.get("category", "none") or "none")
    confidence = str(parsed.get("confidence", "low") or "low")

    return {
        "has_error": has_error,
        "error_text": error_text,
        "category": category,
        "confidence": confidence,
        "model": result.get("model", model),
        "duration_ms": int((time.time() - started) * 1000),
    }


def _safe_parse_json(text: str) -> Optional[dict]:
    """Best-effort JSON parse — strips markdown fences and recovers braces."""
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove leading ```json / ``` and trailing ```
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except Exception:
        # Try slicing to outermost braces.
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start : end + 1])
            except Exception:
                return None
    return None


# ── Evidence persistence ──────────────────────────────────────────────────────


_SCREEN_ERRORS_FILENAME = "screen_errors_{scenario_id}.json"


def persist_error(
    evidence_dir: Path,
    scenario_id: str,
    entry: dict,
) -> Path:
    """Append `entry` to `evidence_dir/<sid>/screen_errors_<sid>.json`.

    The artefact is a list of objects shaped like:
      {
        "step_index": int,
        "screenshot_path": str|null,
        "source": "dom"|"vision"|"runtime",
        "errors": [{ "text": str, "source": str }],
        "captured_at": "<iso8601>"
      }

    If the file does not exist, it's created. If the file exists but is
    not a list, it's overwritten — defensive against partial writes.
    """
    scenario_dir = evidence_dir / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    out_path = scenario_dir / _SCREEN_ERRORS_FILENAME.format(scenario_id=scenario_id)

    existing: list = []
    if out_path.is_file():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existing = data
        except Exception:
            existing = []

    existing.append(entry)
    out_path.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return out_path


# ── HTTP server (vision LLM bridge) ───────────────────────────────────────────


class _VisionHandler(BaseHTTPRequestHandler):
    """POST /analyze — receives JSON {image_base64, scenario_id, step_index, evidence_dir}.

    Returns 200 with {ok, has_error, error_text, ...}. The handler never
    raises — any internal failure becomes a JSON response with ok=false so
    the caller (the spec.ts) can decide whether to fail the step.
    """

    server_version = f"StackyQAUATScreenErrorDetector/{_TOOL_VERSION}"

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        if self.path == "/health":
            self._json(200, {"ok": True, "tool": "screen_error_detector",
                             "version": _TOOL_VERSION})
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/analyze":
            self._json(404, {"ok": False, "error": "not_found"})
            return
        length = int(self.headers.get("Content-Length", "0") or "0")
        try:
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            self._json(400, {"ok": False, "error": "invalid_json", "message": str(exc)})
            return

        image_b64 = payload.get("image_base64") or ""
        if not image_b64:
            self._json(400, {"ok": False, "error": "missing_image"})
            return
        try:
            image_bytes = base64.b64decode(image_b64)
        except Exception as exc:
            self._json(400, {"ok": False, "error": "invalid_base64", "message": str(exc)})
            return

        model = payload.get("model") or _DEFAULT_VISION_MODEL
        try:
            verdict = analyze_screenshot(image_bytes, model=model)
        except VisionDetectorError as exc:
            self._json(200, {"ok": False, "error": "vision_failed",
                             "message": str(exc)[:300]})
            return

        # Optional: persist into evidence_dir if provided
        evidence_dir = payload.get("evidence_dir")
        scenario_id = payload.get("scenario_id")
        if evidence_dir and scenario_id and verdict.get("has_error"):
            try:
                persist_error(
                    Path(evidence_dir),
                    scenario_id,
                    {
                        "step_index": payload.get("step_index"),
                        "screenshot_path": payload.get("screenshot_path"),
                        "source": "vision",
                        "errors": [{"text": verdict["error_text"], "source": "vision"}],
                        "model": verdict["model"],
                        "confidence": verdict["confidence"],
                        "category": verdict["category"],
                        "captured_at": _now_iso(),
                    },
                )
            except Exception as exc:
                logger.warning("could not persist vision error: %s", exc)

        self._json(200, {"ok": True, **verdict})

    # Silence default access log noise — only log errors via logger above.
    def log_message(self, fmt: str, *args) -> None:  # noqa: D401
        logger.debug("HTTP " + fmt, *args)

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def run_server(host: str = "127.0.0.1", port: int = _DEFAULT_PORT) -> None:
    """Boot the local HTTP detector. Blocks until the process is killed."""
    server = HTTPServer((host, port), _VisionHandler)
    logger.warning("screen_error_detector serving on http://%s:%d (vision LLM=%s)",
                   host, port, _DEFAULT_VISION_MODEL)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── CLI ───────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="screen_error_detector — DOM + vision LLM checks for QA UAT.",
    )
    sub = p.add_subparsers(dest="command")

    s_serve = sub.add_parser("serve", help="Run HTTP server for vision LLM analysis")
    s_serve.add_argument("--host", default="127.0.0.1")
    s_serve.add_argument("--port", type=int, default=_DEFAULT_PORT)

    s_analyze = sub.add_parser("analyze", help="One-shot vision analysis of a PNG file")
    s_analyze.add_argument("--image", required=True, help="Path to PNG screenshot")
    s_analyze.add_argument("--model", default=_DEFAULT_VISION_MODEL)

    s_render = sub.add_parser("render-js", help="Print the DOM detector JS helper")

    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
    )
    if args.command == "serve":
        run_server(host=args.host, port=args.port)
        return
    if args.command == "analyze":
        path = Path(args.image)
        if not path.is_file():
            print(json.dumps({"ok": False, "error": "image_not_found",
                              "message": str(path)}), flush=True)
            sys.exit(1)
        try:
            verdict = analyze_screenshot(path.read_bytes(), model=args.model)
        except VisionDetectorError as exc:
            print(json.dumps({"ok": False, "error": "vision_failed",
                              "message": str(exc)}), flush=True)
            sys.exit(1)
        print(json.dumps({"ok": True, **verdict}, ensure_ascii=False, indent=2))
        return
    if args.command == "render-js":
        sys.stdout.write(render_dom_detector_js())
        return

    # No command → print help.
    sys.stderr.write("Usage: screen_error_detector.py {serve|analyze|render-js}\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
