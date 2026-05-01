"""
multi_agent_deliberator.py — G-08: Deliberación Multi-Agente para Tickets Complejos.

Para tickets clasificados como 'complejo' (score M-07 > 12), lanza 3 perspectivas
PM en paralelo y las sintetiza antes de generar la documentación final:

  Perspectiva A: Análisis técnico profundo (causa raíz, DB, código)
  Perspectiva B: Impacto en el negocio y usuario (QA, validaciones, UX)
  Perspectiva C: Riesgos y dependencias (blast radius, compatibilidad)

El sintetizador combina las 3 perspectivas en un ANALISIS_TECNICO.md enriquecido.

Uso:
    from multi_agent_deliberator import MultiAgentDeliberator
    mad = MultiAgentDeliberator(project_name)
    prompts = mad.build_deliberation_prompts(ticket_folder, ticket_id, base_prompt)
    # Invocar 3 agentes PM con los prompts, luego:
    synthesis = mad.synthesize(ticket_folder, ticket_id)
"""

import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.deliberator")


class MultiAgentDeliberator:
    """
    Orquesta la deliberación multi-perspectiva para tickets complejos.
    """

    def __init__(self, project_name: str):
        self._project = project_name

    # ── API pública ───────────────────────────────────────────────────────

    def should_deliberate(self, ticket_folder: str, ticket_id: str) -> bool:
        """Retorna True si el ticket amerita deliberación multi-agente."""
        try:
            from ticket_classifier import classify_ticket
            score = classify_ticket(ticket_folder, ticket_id)
            return score.should_use_multi_agent
        except ImportError:
            return False

    def build_deliberation_prompts(self, ticket_folder: str, ticket_id: str,
                                    base_prompt: str) -> list[dict]:
        """
        Genera las 3 variantes del prompt PM para deliberación.
        Retorna lista de dicts: [{'perspective': str, 'prompt': str}]
        """
        perspectives = [
            {
                "perspective": "A_TECNICA",
                "focus":       self._FOCUS_A,
                "output_file": "PERSPECTIVA_A.md",
            },
            {
                "perspective": "B_NEGOCIO",
                "focus":       self._FOCUS_B,
                "output_file": "PERSPECTIVA_B.md",
            },
            {
                "perspective": "C_RIESGOS",
                "focus":       self._FOCUS_C,
                "output_file": "PERSPECTIVA_C.md",
            },
        ]

        result = []
        for p in perspectives:
            prompt = self._wrap_with_perspective(base_prompt, p["focus"],
                                                  p["output_file"], ticket_id)
            result.append({"perspective": p["perspective"], "prompt": prompt,
                           "output_file": p["output_file"]})

        # Marcar ticket como en deliberación
        flag_path = os.path.join(ticket_folder, "DELIBERACION_EN_PROCESO.flag")
        try:
            Path(flag_path).write_text(
                f"Iniciado: {datetime.now().isoformat()}",
                encoding="utf-8"
            )
        except Exception:
            pass

        return result

    def synthesize(self, ticket_folder: str, ticket_id: str) -> str:
        """
        Sintetiza las 3 perspectivas en un análisis unificado.
        Retorna la síntesis como texto Markdown.
        """
        perspectives = {}
        for fname, key in [("PERSPECTIVA_A.md", "tecnica"),
                            ("PERSPECTIVA_B.md", "negocio"),
                            ("PERSPECTIVA_C.md", "riesgos")]:
            fpath = os.path.join(ticket_folder, fname)
            if os.path.exists(fpath):
                try:
                    perspectives[key] = Path(fpath).read_text(
                        encoding="utf-8", errors="replace")[:3000]
                except Exception:
                    pass

        if not perspectives:
            return ""

        synthesis = self._build_synthesis_prompt(perspectives, ticket_id)

        # Escribir prompt de síntesis para que el agente sintetizador lo procese
        synth_path = os.path.join(ticket_folder, "SYNTHESIS_PROMPT.md")
        try:
            Path(synth_path).write_text(synthesis, encoding="utf-8")
        except Exception:
            pass

        # Limpiar flag
        flag_path = os.path.join(ticket_folder, "DELIBERACION_EN_PROCESO.flag")
        try:
            os.remove(flag_path)
        except Exception:
            pass

        return synthesis

    def all_perspectives_ready(self, ticket_folder: str) -> bool:
        """Verifica si las 3 perspectivas ya fueron generadas."""
        return all(
            os.path.exists(os.path.join(ticket_folder, f))
            for f in ["PERSPECTIVA_A.md", "PERSPECTIVA_B.md", "PERSPECTIVA_C.md"]
        )

    # ── Internals ─────────────────────────────────────────────────────────

    _FOCUS_A = """
> **PERSPECTIVA A — Análisis Técnico Profundo**
>
> Enfócate EXCLUSIVAMENTE en:
> - La causa raíz técnica exacta (línea de código, query, configuración)
> - Qué tablas Oracle están involucradas y sus constraints
> - Qué métodos DAL/BLL deben modificarse y por qué
> - Condiciones de reproducción exactas
> - Impacto en el schema de datos
>
> Produce el resultado en `PERSPECTIVA_A.md`.
"""

    _FOCUS_B = """
> **PERSPECTIVA B — Impacto en Negocio y Usuario**
>
> Enfócate EXCLUSIVAMENTE en:
> - Qué ve el usuario final y cuál es el comportamiento esperado
> - Validaciones de negocio que deben cumplirse
> - Casos edge (nulls, strings vacíos, permisos)
> - Criterios de aceptación para QA
> - Impacto en otros usuarios o módulos de negocio
>
> Produce el resultado en `PERSPECTIVA_B.md`.
"""

    _FOCUS_C = """
> **PERSPECTIVA C — Riesgos y Dependencias**
>
> Enfócate EXCLUSIVAMENTE en:
> - Qué otros módulos podrían verse afectados por el fix
> - Riesgo de regresión: qué puede romper esta solución
> - Dependencias con otros tickets activos
> - Plan de rollback si la solución falla
> - Complejidad y estimación de esfuerzo
>
> Produce el resultado en `PERSPECTIVA_C.md`.
"""

    def _wrap_with_perspective(self, base_prompt: str, focus: str,
                                output_file: str, ticket_id: str) -> str:
        return f"""{focus}

---

{base_prompt}

---

> **Nota:** Este es un análisis de perspectiva única como parte de una deliberación multi-agente.
> Solo produce `{output_file}` — NO generes ANALISIS_TECNICO.md ni PM_COMPLETADO.flag todavía.
> El sintetizador combinará todas las perspectivas al final.
"""

    def _build_synthesis_prompt(self, perspectives: dict, ticket_id: str) -> str:
        lines = [
            f"# Síntesis de Deliberación Multi-Agente — Ticket #{ticket_id}",
            "",
            "Tienes 3 perspectivas de análisis del mismo ticket. Sintetízalas en:",
            "- `ANALISIS_TECNICO.md` — combina causa raíz técnica + criterios de negocio",
            "- `ARQUITECTURA_SOLUCION.md` — solución que considera riesgos identificados",
            "- `TAREAS_DESARROLLO.md` — tareas ordenadas por la complejidad detectada",
            "",
            "Luego crea `PM_COMPLETADO.flag`.",
            "",
            "---",
            "",
        ]

        if "tecnica" in perspectives:
            lines += ["## Perspectiva A — Técnica", "", perspectives["tecnica"], "", "---", ""]
        if "negocio" in perspectives:
            lines += ["## Perspectiva B — Negocio", "", perspectives["negocio"], "", "---", ""]
        if "riesgos" in perspectives:
            lines += ["## Perspectiva C — Riesgos", "", perspectives["riesgos"], "", "---", ""]

        lines += [
            "## Tu tarea: Síntesis",
            "",
            "Integra las 3 perspectivas. Si hay contradicciones, elige la solución más segura.",
            "Menciona explícitamente los riesgos detectados en la Perspectiva C en el análisis.",
        ]
        return "\n".join(lines)
