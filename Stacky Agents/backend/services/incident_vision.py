"""services/incident_vision.py — Plan 166 F2.

Extrae texto de las capturas adjuntas de un incidente con un modelo de
visión OpenAI-compatible (Ollama llava/llama3.2-vision, LM Studio, OpenAI)
ANTES del análisis, y lo mete inline en el manifiesto de adjuntos — así los
3 runtimes (Codex/Claude/Copilot) reciben el mismo texto sin depender de
capacidades de visión del runtime de análisis.

Best-effort en todo momento: cualquier fallo (sin endpoint, sin modelo, red
caída, respuesta no-200) degrada a `None`/incidente sin cambios — el
manifiesto queda como hoy (ruta + [PENDIENTE]).
"""
from __future__ import annotations

import base64
import logging
import time as _time
from pathlib import Path

import requests

logger = logging.getLogger("stacky.services.incident_vision")

# C5 — presupuesto: máx N imágenes y M segundos totales por incidente.
_MAX_IMAGES_PER_INCIDENT = 6
_TOTAL_OCR_BUDGET_SEC = 240

_VISION_INSTRUCTION = (
    "Transcribí TODO el texto visible en esta captura de una incidencia de software "
    "(mensajes de error, stack traces, valores de pantalla, nombres de campos). Después, "
    "en una línea, describí brevemente qué muestra. NO inventes: si algo no se lee, "
    "escribí [ilegible]. Respondé sólo la transcripción + la descripción, sin preámbulo."
)

_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}


def _mime_for_ext(ext: str) -> str:
    return _MIME_BY_EXT.get((ext or "").lower(), "image/png")


def extract_text_from_image(
    image_path,
    mime: str,
    *,
    endpoint: str,
    model: str,
    timeout_sec: int = 120,
    on_log=None,
) -> str | None:
    """Postea la imagen (base64 data URL) al endpoint de visión OpenAI-compatible.
    Devuelve el texto transcripto, o None ante cualquier fallo (degradación)."""
    try:
        raw = Path(image_path).read_bytes()
    except OSError:
        return None
    b64 = base64.b64encode(raw).decode("ascii")
    data_url = f"data:{mime or 'image/png'};base64,{b64}"
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": _VISION_INSTRUCTION},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]},
        ],
        "stream": False,
    }
    try:
        resp = requests.post(
            endpoint, headers={"Content-Type": "application/json"},
            json=payload, timeout=timeout_sec,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        text = text.strip()
        return text or None
    except Exception:  # noqa: BLE001 — cualquier fallo → None (degradación declarada)
        return None


def enrich_incident_with_ocr(incident_id: str) -> dict:
    """Enriquece cada archivo `kind == "image"` del incidente con `ocr_text`.
    Best-effort; respeta el presupuesto C5 (máx _MAX_IMAGES_PER_INCIDENT
    imágenes, _TOTAL_OCR_BUDGET_SEC segundos totales). Devuelve el incidente
    (actualizado si hubo cambios, o el original si no)."""
    from config import config as _cfg
    from services import incident_store

    incident = incident_store.get_incident(incident_id)
    if incident is None:
        return {}
    if not getattr(_cfg, "STACKY_INCIDENT_VISION_OCR_ENABLED", True):
        return incident
    endpoint = (_cfg.STACKY_INCIDENT_VISION_ENDPOINT or _cfg.LOCAL_LLM_ENDPOINT or "").strip()
    model = (_cfg.STACKY_INCIDENT_VISION_MODEL or _cfg.LOCAL_LLM_MODEL or "").strip()
    if not endpoint or not model:
        return incident  # sin modelo de visión → degradación exacta a hoy

    files = incident.get("files") or []
    incident_dir = incident_store.incidents_root() / incident_id
    timeout_sec = int(getattr(_cfg, "LOCAL_LLM_TIMEOUT_SEC", 120))  # C4
    changed = False
    processed = 0
    started = _time.monotonic()
    for f in files:
        if f.get("kind") != "image" or f.get("ocr_text"):
            continue
        if processed >= _MAX_IMAGES_PER_INCIDENT:
            break
        if _time.monotonic() - started > _TOTAL_OCR_BUDGET_SEC:
            break
        mime = _mime_for_ext(f.get("ext", ""))
        text = extract_text_from_image(
            incident_dir / f["stored_name"], mime,
            endpoint=endpoint, model=model, timeout_sec=timeout_sec,
        )
        processed += 1
        if text:
            f["ocr_text"] = text
            changed = True
    if changed:
        incident_store.update_incident(incident_id, files=files)
    return incident_store.get_incident(incident_id) or incident
