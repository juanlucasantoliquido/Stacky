"""
lm_enricher.py — Enriquece tests auto-generados con assertions reales via Copilot.

Usa el VS Code Bridge (http://127.0.0.1:5052) que ya existe en Stacky Agents.
Es completamente opcional — si el bridge no está disponible, el tool funciona igual.

Qué hace:
  - Lee un archivo .cs de test auto-generado
  - Lee el código fuente de la clase de negocio y DALC
  - Llama al LLM para completar las secciones TODO con assertions reales y mocks Moq
  - Reemplaza el contenido entre los marcadores [BTG-AUTO] y el [TestFixture]
  - Marca los tests enriquecidos con [BTG-ENRICHED] para no re-procesarlos
"""
from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_BRIDGE_URL = "http://127.0.0.1:5052"
_BTG_ENRICHED_MARKER = "// [BTG-ENRICHED]"

# ─── HEALTH CHECK ────────────────────────────────────────────────────────────


def bridge_available() -> bool:
    """Verifica si el VS Code Bridge (Stacky Agents extension) está corriendo."""
    try:
        import urllib.request
        with urllib.request.urlopen(f"{_BRIDGE_URL}/health", timeout=3) as r:
            import json
            data = json.loads(r.read())
            return data.get("ok") is True
    except Exception:
        return False


# ─── EXTRACCIÓN DE CONTEXTO ──────────────────────────────────────────────────

def _read_source_context(
    biz_namespace: str,
    biz_class: str,
    dalc_class: Optional[str],
    negocio_root: Path,
    max_chars: int = 4000,
) -> str:
    """
    Lee el código fuente de la clase de negocio y DALC.
    Limita a max_chars para no saturar el contexto del LLM.
    """
    parts = []

    biz_folder = negocio_root / biz_namespace
    if biz_folder.is_dir():
        biz_file = biz_folder / f"{biz_class}.cs"
        if biz_file.is_file():
            content = biz_file.read_text(encoding="utf-8", errors="replace")
            parts.append(f"// === {biz_class}.cs ===\n{content[:max_chars // 2]}")

        if dalc_class:
            dalc_file = biz_folder / f"{dalc_class}.cs"
            if dalc_file.is_file():
                content = dalc_file.read_text(encoding="utf-8", errors="replace")
                parts.append(f"// === {dalc_class}.cs ===\n{content[:max_chars // 2]}")

    return "\n\n".join(parts)[:max_chars]


# ─── LLAMADA AL BRIDGE ───────────────────────────────────────────────────────


def _invoke_bridge(system: str, user: str, model: str = "claude-sonnet-4.5") -> Optional[str]:
    """Llama al VS Code Bridge y retorna el texto de respuesta."""
    try:
        import json
        import urllib.request

        payload = json.dumps({
            "system": system,
            "user": user,
            "agent": "batch_test_gen",
            "model": model,
            "timeout_sec": 120,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{_BRIDGE_URL}/invoke",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=150) as r:
            data = json.loads(r.read())
            if data.get("ok"):
                return data.get("text", "")
            logger.warning("Bridge respondio ok=false: %s", data.get("error"))
            return None
    except Exception as exc:
        logger.warning("Bridge no disponible: %s", exc)
        return None


# ─── PROMPT DE ENRIQUECIMIENTO ────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
Eres un experto en testing de aplicaciones .NET con NUnit.
Tu tarea es mejorar tests de integración para procesos Batch de un sistema de cobranza (RSPacifico).

REGLAS ESTRICTAS:
1. SOLO modifica los tests marcados con "// [BTG-AUTO]". 
2. NO elimines ningún test existente.
3. Reemplaza los comentarios "// TODO:" con código real cuando sea posible.
4. Agrega el comentario "// [BTG-ENRICHED]" al inicio de cada test que modifiques.
5. Si no puedes generar una assertion específica por falta de contexto, deja el TODO pero mejora lo que puedas.
6. Retorna el archivo .cs COMPLETO, sin truncar.
7. No uses Moq — cConexion es clase concreta. Usa conexión real con RollbackTransaccion().
8. Mantén el namespace, usings y nombre de clase exactamente igual.
"""


def _build_enrichment_prompt(
    test_file_content: str,
    source_context: str,
    process_name: str,
    subproc_name: str,
) -> str:
    return f"""\
Proceso: {process_name} | Sub-proceso: {subproc_name}

CÓDIGO FUENTE DE LA CLASE DE NEGOCIO:
```csharp
{source_context}
```

ARCHIVO DE TEST A MEJORAR:
```csharp
{test_file_content}
```

Devuelve el archivo .cs completo con los tests mejorados. 
Comienza directamente con los comentarios de cabecera del archivo, sin preámbulos.
"""


# ─── EXTRACCIÓN DE C# DEL RESPONSE ───────────────────────────────────────────

_RE_CSHARP_BLOCK = re.compile(r"```(?:csharp|cs)?\s*\n(.*?)```", re.DOTALL)


def _extract_cs_from_response(response: str) -> Optional[str]:
    """Extrae el bloque de código C# del response del LLM."""
    m = _RE_CSHARP_BLOCK.search(response)
    if m:
        return m.group(1).strip()
    # Si no hay bloque markdown, verificar si es C# directo
    if "namespace" in response and "[TestFixture]" in response:
        return response.strip()
    return None


# ─── ENRIQUECIMIENTO DE UN ARCHIVO ───────────────────────────────────────────


def enrich_test_file(
    test_file: Path,
    biz_namespace: str,
    biz_class: str,
    dalc_class: Optional[str],
    negocio_root: Path,
    process_name: str,
    subproc_name: str,
    model: str = "claude-sonnet-4.5",
    dry_run: bool = False,
) -> dict:
    """
    Enriquece un archivo de test con assertions reales via Copilot.

    Returns:
        dict con "ok", "status", "message"
    """
    if not test_file.is_file():
        return {"ok": False, "status": "skipped", "message": f"Archivo no encontrado: {test_file}"}

    existing_content = test_file.read_text(encoding="utf-8", errors="replace")

    # Si ya fue enriquecido y no tiene TODOs, omitir
    todo_count = existing_content.count("// TODO:")
    enriched_count = existing_content.count(_BTG_ENRICHED_MARKER)
    auto_count = existing_content.count("// [BTG-AUTO]")

    if todo_count == 0 and enriched_count >= auto_count:
        return {"ok": True, "status": "skipped", "message": "Ya enriquecido, sin TODOs pendientes."}

    if not bridge_available():
        return {
            "ok": False,
            "status": "no_bridge",
            "message": "VS Code Bridge no disponible. Abri VS Code con la extension Stacky Agents.",
        }

    # Dry-run: solo contar TODOs y auto-marks sin llamar al LLM
    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "message": (
                f"Dry-run: {todo_count} TODOs a resolver, "
                f"{auto_count - enriched_count} tests pendientes de enriquecimiento."
            ),
        }

    logger.info("Enriqueciendo %s...", test_file.name)

    source_ctx = _read_source_context(biz_namespace, biz_class, dalc_class, negocio_root)
    if not source_ctx:
        return {
            "ok": False,
            "status": "no_source",
            "message": f"No se encontro codigo fuente para {biz_namespace}.{biz_class}",
        }

    prompt = _build_enrichment_prompt(existing_content, source_ctx, process_name, subproc_name)
    response = _invoke_bridge(_SYSTEM_PROMPT, prompt, model=model)

    if response is None:
        return {"ok": False, "status": "llm_error", "message": "LLM no retorno respuesta."}

    enriched_cs = _extract_cs_from_response(response)
    if enriched_cs is None:
        return {
            "ok": False,
            "status": "parse_error",
            "message": "No se pudo extraer C# del response. Guardando response crudo en .enrich_log.",
            "raw": response[:500],
        }

    # Validaciones básicas de integridad
    if "namespace" not in enriched_cs or "[TestFixture]" not in enriched_cs:
        return {
            "ok": False,
            "status": "invalid_output",
            "message": "El output del LLM no parece C# valido.",
        }

    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "message": f"Dry-run: {len(enriched_cs)} chars generados, {enriched_cs.count(_BTG_ENRICHED_MARKER)} tests enriquecidos.",
        }

    # Guardar backup antes de sobreescribir
    backup = test_file.with_suffix(".cs.bak")
    backup.write_text(existing_content, encoding="utf-8")

    test_file.write_text(enriched_cs, encoding="utf-8")

    enriched = enriched_cs.count(_BTG_ENRICHED_MARKER)
    todos_remaining = enriched_cs.count("// TODO:")

    return {
        "ok": True,
        "status": "enriched",
        "message": f"{enriched} tests enriquecidos, {todos_remaining} TODOs restantes. Backup: {backup.name}",
    }
