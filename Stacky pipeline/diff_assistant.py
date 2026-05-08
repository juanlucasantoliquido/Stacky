"""
diff_assistant.py — Analizador de diffs para Stacky.

Dado un diff Git, genera:
  - checklist de testing (qué verificar manualmente antes de deployar)
  - puntos de riesgo detectados (capas tocadas, patrones peligrosos)
  - orden sugerido de ejecución de scripts SQL
  - resumen de impacto (qué módulos se modificaron)

No usa LLMs — análisis estático basado en patrones del codebase RS Standard / Pacífico.
"""

import re
from pathlib import Path
from typing import Optional


# ── Patrones de riesgo por tipo de archivo/código ────────────────────────────

RISK_PATTERNS = [
    # Base de datos
    {
        "pattern":     r"\bSqlCommand\b|\bOracleCommand\b|\bDbCommand\b",
        "level":       "high",
        "message":     "Cambios en comandos SQL — verificar parámetros y tipos de datos",
        "test_hint":   "Ejecutar el flujo completo con datos de prueba, verificar que no haya SQL injection",
    },
    {
        "pattern":     r"\.ExecuteNonQuery\(\)|\.ExecuteScalar\(\)|\.ExecuteReader\(\)",
        "level":       "high",
        "message":     "Ejecución directa de queries — verificar transacciones y manejo de errores",
        "test_hint":   "Probar con datos límite (null, strings vacíos, valores máximos)",
    },
    {
        "pattern":     r"BEGIN\s+TRAN|COMMIT\s+TRAN|ROLLBACK",
        "level":       "high",
        "message":     "Cambios en transacciones Oracle/SQL — verificar atomicidad",
        "test_hint":   "Simular error en mitad del proceso y verificar rollback correcto",
    },
    # Autenticación/sesión
    {
        "pattern":     r"Session\[|HttpContext\.Current\.User|FormsAuthentication",
        "level":       "high",
        "message":     "Cambios en sesión o autenticación — riesgo de acceso no autorizado",
        "test_hint":   "Verificar que el login/logout funcione y que los permisos no cambien",
    },
    # Configuración
    {
        "pattern":     r"ConfigurationManager|AppSettings|ConnectionStrings",
        "level":       "medium",
        "message":     "Se leen parámetros de configuración — verificar que el web.config del entorno destino tenga las claves",
        "test_hint":   "Revisar app.config / web.config en el servidor destino antes de deployar",
    },
    # Archivos y paths
    {
        "pattern":     r"File\.|Directory\.|Path\.|StreamReader|StreamWriter",
        "level":       "medium",
        "message":     "Operaciones de archivo — verificar permisos en el servidor destino",
        "test_hint":   "Verificar que las carpetas existan y el usuario IIS tenga permisos de escritura",
    },
    # Servicios web
    {
        "pattern":     r"HttpWebRequest|WebClient|HttpClient|RestClient",
        "level":       "medium",
        "message":     "Llamadas a servicios externos — verificar URLs y credenciales en el entorno destino",
        "test_hint":   "Confirmar que el endpoint de servicio en el entorno destino sea el correcto",
    },
    # Caché
    {
        "pattern":     r"HttpRuntime\.Cache|MemoryCache|Cache\[",
        "level":       "low",
        "message":     "Uso de caché — un restart limpiará el caché automáticamente",
        "test_hint":   "Si el bug era de caché desactualizado, verificar que el comportamiento sea correcto post-restart",
    },
    # Redioma (RS-específico)
    {
        "pattern":     r"RIDIOMA|GetMensaje|GetMensajeById",
        "level":       "medium",
        "message":     "Cambios en mensajes RIDIOMA — verificar que los IDs existan en la BD del entorno destino",
        "test_hint":   "Ejecutar el script SQL de RIDIOMA incluido en el paquete antes del deploy",
    },
    # Stored procedures
    {
        "pattern":     r"CommandType\.StoredProcedure|\.StoredProcedure",
        "level":       "medium",
        "message":     "Llamada a stored procedures — verificar que existan en el entorno destino",
        "test_hint":   "Confirmar que los SPs requeridos estén desplegados en la BD destino",
    },
    # Batch / procesos en background
    {
        "pattern":     r"Thread\.|Task\.|Async|await |BackgroundWorker",
        "level":       "medium",
        "message":     "Cambios en procesos asíncronos o hilos — verificar race conditions",
        "test_hint":   "Ejecutar el proceso varias veces en simultáneo y verificar consistencia",
    },
    # Logging
    {
        "pattern":     r"log\.Error|log\.Fatal|Logger\.Error|EventLog",
        "level":       "low",
        "message":     "Cambios en logging — verificar que los logs sean legibles y no versen datos sensibles",
        "test_hint":   "Revisar logs después del primer deploy para confirmar que no hay excepciones",
    },
]

# ── Capas de la arquitectura RS Standard ─────────────────────────────────────

LAYER_PATTERNS = {
    "UI (ASPX / Frontend)":     r"\.aspx$|\.ascx$|\.master$|\.css$|\.js$",
    "Code-Behind (ASPX.CS)":    r"\.aspx\.cs$|\.ascx\.cs$",
    "Lógica de negocio (BLL)":  r"(?i)(bll|business|logic|service|manager).*\.cs$",
    "Acceso a datos (DAL)":     r"(?i)(dal|data|repo|repositor|access|bd|db).*\.cs$",
    "Entidades / Modelos":      r"(?i)(model|entity|entidad|dto|bean).*\.cs$",
    "Batch / Procesos":         r"(?i)(batch|proceso|scheduler|job|task).*\.cs$",
    "Configuración":            r"\.config$|\.json$|\.xml$",
    "Base de datos (SQL)":      r"\.sql$",
}


class DiffAssistant:
    """Analiza un diff Git y genera recomendaciones de testing y puntos de riesgo."""

    def __init__(self, diff_text: str, modified_files: list[str]):
        self.diff_text      = diff_text or ""
        self.modified_files = modified_files or []

    def analyze(self) -> dict:
        """
        Retorna:
          layers:    capas arquitectónicas afectadas
          risks:     lista de { level, message, test_hint }
          checklist: lista de strings (acciones de verificación)
          sql_order: sugerencia de orden de ejecución de scripts
          summary:   texto breve del impacto
        """
        layers    = self._detect_layers()
        risks     = self._detect_risks()
        checklist = self._build_checklist(layers, risks)
        sql_order = self._suggest_sql_order()
        summary   = self._build_summary(layers, risks)

        return {
            "layers":    layers,
            "risks":     risks,
            "checklist": checklist,
            "sql_order": sql_order,
            "summary":   summary,
        }

    # ── Detección de capas ────────────────────────────────────────────────────

    def _detect_layers(self) -> list[str]:
        touched = []
        for layer_name, pattern in LAYER_PATTERNS.items():
            if any(re.search(pattern, f) for f in self.modified_files):
                touched.append(layer_name)
        return touched

    # ── Detección de riesgos ──────────────────────────────────────────────────

    def _detect_risks(self) -> list[dict]:
        found = []
        seen  = set()
        for rule in RISK_PATTERNS:
            if re.search(rule["pattern"], self.diff_text, re.IGNORECASE):
                msg = rule["message"]
                if msg not in seen:
                    found.append({
                        "level":     rule["level"],
                        "message":   msg,
                        "test_hint": rule["test_hint"],
                    })
                    seen.add(msg)
        # Ordenar: high → medium → low
        order = {"high": 0, "medium": 1, "low": 2}
        found.sort(key=lambda r: order.get(r["level"], 9))
        return found

    # ── Checklist de testing ──────────────────────────────────────────────────

    def _build_checklist(self, layers: list, risks: list) -> list[str]:
        items = []

        # Siempre
        items.append("Hacer backup de los binarios actuales antes de deployar")
        items.append("Verificar que el entorno destino esté accesible y sin usuarios activos")

        # Por capa
        if any("ASPX" in l or "UI" in l for l in layers):
            items.append("Verificar que las páginas web cargan sin errores 500")
            items.append("Probar el flujo desde el navegador en el entorno destino")
        if any("DAL" in l or "datos" in l for l in layers):
            items.append("Ejecutar queries de verificación en la BD del entorno destino")
            items.append("Verificar que no haya timeouts en consultas")
        if any("BLL" in l or "negocio" in l for l in layers):
            items.append("Ejecutar el caso de uso principal del ticket end-to-end")
        if any("Batch" in l for l in layers):
            items.append("Verificar que el batch/proceso no quede colgado ni falle silenciosamente")
        if any("SQL" in l for l in layers):
            items.append("Ejecutar los scripts SQL en orden ANTES de deployar los binarios")

        # Por riesgo
        for risk in risks:
            if risk["level"] == "high" and risk["test_hint"] not in items:
                items.append(risk["test_hint"])

        # Siempre al final
        items.append("Reiniciar el pool de aplicación después del deploy")
        items.append("Verificar los logs de error (Event Viewer / log4net) los primeros 5 minutos")
        items.append("Confirmar que el ticket funciona correctamente con el usuario solicitante")

        return items

    # ── Orden sugerido de SQL ─────────────────────────────────────────────────

    def _suggest_sql_order(self) -> list[str]:
        """
        Detecta bloques SQL en el diff y sugiere un orden de ejecución.
        DDL primero (CREATE/ALTER), luego DML (INSERT/UPDATE), luego verificación (SELECT).
        """
        ddl_hints = []
        dml_hints = []
        ver_hints = []

        for line in self.diff_text.splitlines():
            line_up = line.strip().upper()
            if not line_up or line_up.startswith("--"):
                continue
            if re.match(r"^[+>]?\s*(CREATE|ALTER|DROP|ADD COLUMN)", line_up):
                ddl_hints.append(line.strip().lstrip("+>").strip()[:80])
            elif re.match(r"^[+>]?\s*(INSERT|UPDATE|DELETE|MERGE)", line_up):
                dml_hints.append(line.strip().lstrip("+>").strip()[:80])
            elif re.match(r"^[+>]?\s*SELECT", line_up):
                ver_hints.append(line.strip().lstrip("+>").strip()[:80])

        order = []
        if ddl_hints:
            order.append("1. DDL primero: crear/modificar estructuras")
            for h in ddl_hints[:3]:
                order.append(f"   • {h}")
        if dml_hints:
            order.append("2. DML: insertar/actualizar datos de configuración")
            for h in dml_hints[:3]:
                order.append(f"   • {h}")
        if ver_hints:
            order.append("3. Verificación: ejecutar SELECTs para confirmar los datos")
        if not order:
            order.append("No se detectaron scripts SQL en el diff")
        return order

    # ── Resumen ───────────────────────────────────────────────────────────────

    def _build_summary(self, layers: list, risks: list) -> str:
        high_risks = sum(1 for r in risks if r["level"] == "high")
        med_risks  = sum(1 for r in risks if r["level"] == "medium")

        parts = []
        if layers:
            parts.append(f"Capas afectadas: {', '.join(layers)}")
        if high_risks:
            parts.append(f"⚠️ {high_risks} riesgo(s) alto(s)")
        if med_risks:
            parts.append(f"{med_risks} riesgo(s) medio(s)")
        if not parts:
            parts.append("Cambios de bajo impacto")
        return " · ".join(parts)


def analyze_ticket(ticket_folder: str, workspace_root: str) -> dict:
    """
    Helper de alto nivel: obtiene el diff del workspace y lo analiza.
    """
    diff_text      = ""
    modified_files = []

    try:
        import subprocess
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=workspace_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=30
        )
        diff_text = r.stdout
        r2 = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=workspace_root,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15
        )
        modified_files = [l.strip() for l in r2.stdout.splitlines() if l.strip()]
    except Exception:
        # Fallback: leer GIT_CHANGES.md
        changes_md = Path(ticket_folder) / "GIT_CHANGES.md"
        if changes_md.exists():
            content = changes_md.read_text(encoding="utf-8", errors="ignore")
            diff_text = content
            import re as _re
            for line in content.splitlines():
                m = _re.match(r"^[MADC?!]+\s+(.+)$", line)
                if m:
                    modified_files.append(m.group(1).strip())

    return DiffAssistant(diff_text, modified_files).analyze()
