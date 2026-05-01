"""
shadow_mode.py — N-07: Modo Shadow (Dry Run del Pipeline).

Cuando shadow_mode está activo, los agentes DEV no modifican archivos reales:
en cambio describen qué cambiarían (en formato structured Markdown).
Permite validar el razonamiento del pipeline sin riesgo de tocar el codebase.

El PM y QA funcionan normalmente. Solo DEV opera en modo descripción.

Uso:
    from shadow_mode import ShadowMode
    sm = ShadowMode(project_name)
    sm.enable() / sm.disable() / sm.is_enabled()
    prompt = sm.wrap_dev_prompt(original_dev_prompt)
    sm.record_shadow_result(ticket_id, ticket_folder)
"""

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.shadow_mode")

_SHADOW_FLAG_FILENAME = "shadow_mode.flag"
_SHADOW_CONFIG_KEY    = "shadow_mode"


class ShadowMode:
    """
    Gestiona el modo shadow del pipeline Stacky.
    El flag persiste en el directorio base de Stacky.
    """

    def __init__(self, project_name: str = ""):
        self._project  = project_name
        self._base_dir = os.path.dirname(os.path.abspath(__file__))
        self._flag     = os.path.join(self._base_dir, _SHADOW_FLAG_FILENAME)

    # ── API pública ───────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        """Retorna True si shadow mode está activo."""
        return os.path.exists(self._flag)

    def enable(self) -> None:
        """Activa shadow mode."""
        try:
            Path(self._flag).write_text(
                json.dumps({"enabled_at": datetime.now().isoformat(),
                            "project": self._project}),
                encoding="utf-8"
            )
            logger.info("[SHADOW] Modo shadow activado — DEV solo describirá cambios")
        except Exception as e:
            logger.error("[SHADOW] Error activando: %s", e)

    def disable(self) -> None:
        """Desactiva shadow mode."""
        try:
            os.remove(self._flag)
            logger.info("[SHADOW] Modo shadow desactivado — DEV operará normalmente")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error("[SHADOW] Error desactivando: %s", e)

    def wrap_dev_prompt(self, original_prompt: str) -> str:
        """
        Envuelve el prompt DEV con instrucciones de shadow mode.
        El agente describirá los cambios en lugar de ejecutarlos.
        """
        shadow_preamble = """
> ⚠️ **MODO SHADOW ACTIVO** — No modifiques ningún archivo real.
> En lugar de aplicar cambios, produce un documento `DEV_COMPLETADO.md` que describa:
>
> 1. **Archivos que se modificarían** (path completo relativo al workspace)
> 2. **Cambios propuestos** por archivo (diff conceptual o descripción detallada)
> 3. **Razón de cada cambio** (vinculada al análisis técnico)
> 4. **Riesgos identificados** (efectos secundarios, breaking changes posibles)
> 5. **Orden de implementación recomendado**
>
> El formato de DEV_COMPLETADO.md debe ser:
> ```
> # DEV SHADOW COMPLETADO — Ticket #[ID]
> ## Archivos a modificar
> ### [ruta/archivo.cs]
> **Cambio:** [descripción]
> **Razón:** [vinculada al análisis]
> **Riesgo:** [bajo/medio/alto — explicación]
> ```
> NO uses herramientas de escritura de archivos. Solo produce el documento de descripción.

---

"""
        return shadow_preamble + original_prompt

    def record_shadow_result(self, ticket_id: str, ticket_folder: str) -> dict | None:
        """
        Lee DEV_COMPLETADO.md de un ticket shadow y genera un reporte comparativo.
        Retorna dict con análisis del shadow result.
        """
        dev_path = os.path.join(ticket_folder, "DEV_COMPLETADO.md")
        if not os.path.exists(dev_path):
            return None

        try:
            content = Path(dev_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        if "SHADOW" not in content.upper():
            return None  # No es un resultado shadow

        # Extraer archivos mencionados
        files = re.findall(r'###\s+([\w/\\.\-]+\.(?:cs|aspx\.cs|aspx|sql|vb))',
                           content, re.IGNORECASE)
        files = [f.replace("\\", "/") for f in files]

        # Contar riesgos
        high_risk   = len(re.findall(r'riesgo[:\s]+alto', content, re.IGNORECASE))
        medium_risk = len(re.findall(r'riesgo[:\s]+medio', content, re.IGNORECASE))

        result = {
            "ticket_id":      ticket_id,
            "mode":           "shadow",
            "files_proposed": files,
            "file_count":     len(files),
            "risk_high":      high_risk,
            "risk_medium":    medium_risk,
            "recorded_at":    datetime.now().isoformat(),
        }

        # Escribir reporte shadow
        report_path = os.path.join(ticket_folder, "SHADOW_REPORT.json")
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        logger.info("[SHADOW] Resultado shadow registrado para #%s: %d archivos, "
                    "%d riesgo alto", ticket_id, len(files), high_risk)
        return result

    def get_shadow_summary(self) -> str:
        """Texto de estado del shadow mode para el dashboard."""
        if self.is_enabled():
            try:
                data = json.loads(Path(self._flag).read_text(encoding="utf-8"))
                since = data.get("enabled_at", "")[:16].replace("T", " ")
                return f"🔮 Shadow mode ACTIVO desde {since} — DEV solo describe cambios"
            except Exception:
                return "🔮 Shadow mode ACTIVO"
        return "▶️ Shadow mode INACTIVO — pipeline operando normalmente"


# ── Singleton global ──────────────────────────────────────────────────────────

_shadow_instance: ShadowMode | None = None


def get_shadow_mode(project_name: str = "") -> ShadowMode:
    """Retorna la instancia singleton de ShadowMode."""
    global _shadow_instance
    if _shadow_instance is None:
        _shadow_instance = ShadowMode(project_name)
    return _shadow_instance
