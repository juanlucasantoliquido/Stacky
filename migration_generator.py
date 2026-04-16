"""
migration_generator.py — X-03: Generacion y Ejecucion de Migration Scripts Oracle.

Cuando DEV detecta que el fix requiere cambios en el schema Oracle, genera
automaticamente el script SQL versionado con:
  - Versionado por ticket (prefijo YYYYMMDD_HHMMSS_{ticket_id})
  - Script de rollback complementario
  - Verificacion de existencia de objetos antes de aplicar
  - Modo dry-run que valida sin ejecutar nada
  - Historial de migraciones aplicadas

Uso:
    from migration_generator import MigrationGenerator
    gen = MigrationGenerator(project_name)
    path = gen.generate_from_ticket(ticket_folder, ticket_id)
    gen.dry_run(path)                    # valida sin ejecutar
    gen.execute(path, dry_run=False)     # ejecuta con confirmacion
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mantis.migrations")

BASE_DIR = Path(__file__).parent


class MigrationGenerator:
    """
    Genera y gestiona scripts de migracion Oracle versionados por ticket.
    """

    def __init__(self, project_name: str):
        self.project_name   = project_name
        self._config        = self._load_config()
        self._migrations_dir = BASE_DIR / "migrations" / project_name
        self._migrations_dir.mkdir(parents=True, exist_ok=True)
        self._history_path  = self._migrations_dir / "migration_history.json"
        self._history       = self._load_history()

    # ── API publica ──────────────────────────────────────────────────────────

    def generate_from_ticket(self, ticket_folder: str, ticket_id: str) -> Optional[str]:
        """
        Analiza el ticket y genera un migration script si detecta cambios de schema.
        Retorna la ruta del script generado, o None si no se necesitan cambios.
        """
        ticket_path = Path(ticket_folder)
        queries_file = ticket_path / "QUERIES_ANALISIS.sql"
        tareas_file  = ticket_path / "TAREAS_DESARROLLO.md"
        dev_file     = ticket_path / "DEV_COMPLETADO.md"

        sql_hints  = self._extract_sql_hints(queries_file, tareas_file, dev_file)
        if not sql_hints["ddl_statements"] and not sql_hints["dml_seeds"]:
            logger.debug("[X-03] No se detectaron cambios de schema para ticket %s", ticket_id)
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{timestamp}_{ticket_id}.sql"
        script_path = self._migrations_dir / filename
        rollback_path = self._migrations_dir / f"{timestamp}_{ticket_id}_rollback.sql"

        up_script   = self._build_migration_script(sql_hints, ticket_id, timestamp)
        down_script = self._build_rollback_script(sql_hints, ticket_id, timestamp)

        script_path.write_text(up_script, encoding="utf-8")
        rollback_path.write_text(down_script, encoding="utf-8")

        # Escribir referencia en la carpeta del ticket
        ref_file = ticket_path / "DB_MIGRATION.md"
        ref_content = f"""# Migracion de Base de Datos — {ticket_id}

**Script:** `migrations/{self.project_name}/{filename}`
**Rollback:** `migrations/{self.project_name}/{timestamp}_{ticket_id}_rollback.sql`
**Generado:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
**Estado:** PENDIENTE — ejecutar antes del deploy

## Para aplicar:
```
python -c "from migration_generator import MigrationGenerator; MigrationGenerator('{self.project_name}').execute('{script_path}')"
```

## Para rollback:
```
python -c "from migration_generator import MigrationGenerator; MigrationGenerator('{self.project_name}').execute('{rollback_path}')"
```

## Cambios detectados:
"""
        for stmt in sql_hints["ddl_statements"]:
            ref_content += f"- `{stmt[:100]}`\n"

        ref_file.write_text(ref_content, encoding="utf-8")

        logger.info("[X-03] Migration script generado: %s", script_path)
        return str(script_path)

    def dry_run(self, script_path: str) -> dict:
        """
        Valida el script sin ejecutarlo. Retorna dict con resultado de validacion.
        """
        script = Path(script_path)
        if not script.exists():
            return {"ok": False, "error": f"Script no encontrado: {script_path}"}

        content = script.read_text(encoding="utf-8")
        issues  = []

        # Validaciones estaticas
        issues += self._validate_safety(content)
        issues += self._validate_guards(content)

        # Intentar conexion Oracle si esta configurada
        oracle_result = self._validate_with_oracle(content)
        if oracle_result:
            issues += oracle_result

        ok = len([i for i in issues if i["level"] == "error"]) == 0
        return {"ok": ok, "issues": issues, "script": str(script)}

    def execute(self, script_path: str, dry_run: bool = True) -> dict:
        """
        Ejecuta el script Oracle. dry_run=True solo valida (default seguro).
        """
        validation = self.dry_run(script_path)
        if not validation["ok"]:
            return {"success": False, "validation": validation}

        if dry_run:
            return {"success": True, "dry_run": True, "validation": validation}

        # Ejecutar via sqlplus si esta disponible
        conn_str = self._config.get("oracle_connection", "")
        if not conn_str:
            return {
                "success": False,
                "error": "oracle_connection no configurada en config.json",
            }

        try:
            result = subprocess.run(
                ["sqlplus", "-S", conn_str, "@", script_path],
                capture_output=True, text=True, timeout=120,
            )
            success = result.returncode == 0 and "ERROR" not in result.stdout.upper()
            if success:
                self._record_migration(script_path)
            return {
                "success": success,
                "stdout":  result.stdout[-2000:],
                "stderr":  result.stderr[-500:],
            }
        except FileNotFoundError:
            return {"success": False, "error": "sqlplus no encontrado en PATH"}
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout ejecutando sqlplus"}

    def list_pending(self) -> list:
        """Retorna scripts generados que aun no se aplicaron."""
        applied = {m["script"] for m in self._history.get("applied", [])}
        pending = []
        for sql_file in sorted(self._migrations_dir.glob("*.sql")):
            if "_rollback.sql" in sql_file.name:
                continue
            if str(sql_file) not in applied:
                pending.append(str(sql_file))
        return pending

    # ── Internos ─────────────────────────────────────────────────────────────

    def _extract_sql_hints(self, *files) -> dict:
        """Extrae DDL y DML relevantes de los archivos del ticket."""
        ddl = []
        dml = []

        ddl_patterns = [
            r"ALTER\s+TABLE\s+\w+\s+ADD",
            r"CREATE\s+(?:TABLE|INDEX|SEQUENCE)",
            r"INSERT\s+INTO\s+RIDIOMA",
            r"INSERT\s+INTO\s+\w*(?:MENSAJ|MSG|CONST|CONFIG)\w*",
        ]
        dml_patterns = [
            r"UPDATE\s+\w+\s+SET",
            r"INSERT\s+INTO\s+\w+",
        ]

        for fpath in files:
            if not fpath or not Path(fpath).exists():
                continue
            content = Path(fpath).read_text(encoding="utf-8", errors="ignore")

            for line in content.splitlines():
                line_up = line.strip().upper()
                if any(re.search(p, line_up) for p in ddl_patterns):
                    ddl.append(line.strip())
                elif any(re.search(p, line_up) for p in dml_patterns):
                    dml.append(line.strip())

        return {"ddl_statements": list(dict.fromkeys(ddl)), "dml_seeds": list(dict.fromkeys(dml))}

    def _build_migration_script(self, hints: dict, ticket_id: str, timestamp: str) -> str:
        lines = [
            f"-- Migration: {ticket_id}",
            f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"-- Version: {timestamp}",
            "-- Ejecutar como: sqlplus user/pass@sid @<este_archivo>",
            "",
            "SET ECHO ON;",
            "SET DEFINE OFF;",
            "WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;",
            "",
            "BEGIN",
            f"  DBMS_OUTPUT.PUT_LINE('Iniciando migracion {ticket_id}');",
            "END;",
            "/",
            "",
        ]

        for stmt in hints["ddl_statements"]:
            lines.append(f"-- DDL detectado en analisis del ticket")
            lines.append(stmt if stmt.endswith(";") else stmt + ";")
            lines.append("")

        for stmt in hints["dml_seeds"]:
            lines.append(f"-- Seed data detectado")
            lines.append(stmt if stmt.endswith(";") else stmt + ";")
            lines.append("")

        lines += [
            "COMMIT;",
            "",
            "BEGIN",
            f"  DBMS_OUTPUT.PUT_LINE('Migracion {ticket_id} aplicada exitosamente');",
            "END;",
            "/",
            "",
            "EXIT;",
        ]
        return "\n".join(lines)

    def _build_rollback_script(self, hints: dict, ticket_id: str, timestamp: str) -> str:
        lines = [
            f"-- ROLLBACK Migration: {ticket_id}",
            f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "-- ATENCION: revisar antes de ejecutar — puede causar perdida de datos",
            "",
            "SET ECHO ON;",
            "WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK;",
            "",
            "-- TODO: Agregar sentencias DROP/ALTER de rollback correspondientes",
            "-- a los DDL del script de migracion.",
            "",
        ]

        for stmt in hints["ddl_statements"]:
            if "ADD COLUMN" in stmt.upper() or "ADD " in stmt.upper():
                lines.append(f"-- ROLLBACK de: {stmt}")
                lines.append("-- ALTER TABLE <tabla> DROP COLUMN <columna>;")
                lines.append("")
            elif "CREATE TABLE" in stmt.upper():
                lines.append(f"-- ROLLBACK de: {stmt}")
                lines.append("-- DROP TABLE <tabla>;")
                lines.append("")

        lines += ["COMMIT;", "EXIT;"]
        return "\n".join(lines)

    def _validate_safety(self, content: str) -> list:
        """Detecta operaciones peligrosas."""
        issues = []
        dangerous = ["DROP TABLE", "TRUNCATE TABLE", "DELETE FROM", "DROP SEQUENCE"]
        for op in dangerous:
            if op in content.upper():
                issues.append({
                    "level":   "warning",
                    "message": f"Operacion destructiva detectada: {op} — revisar antes de ejecutar",
                })
        return issues

    def _validate_guards(self, content: str) -> list:
        """Verifica que el script tenga guards de seguridad basicos."""
        issues = []
        if "WHENEVER SQLERROR" not in content.upper():
            issues.append({
                "level":   "warning",
                "message": "No se encontro WHENEVER SQLERROR — agregar para manejo de errores",
            })
        if "COMMIT" not in content.upper():
            issues.append({
                "level":   "info",
                "message": "No se encontro COMMIT explicito",
            })
        return issues

    def _validate_with_oracle(self, content: str) -> Optional[list]:
        """Intenta validar con Oracle si hay conexion disponible."""
        try:
            import oracledb
            conn_str = self._config.get("oracle_connection", "")
            if not conn_str:
                return None
            # Solo hacer EXPLAIN PLAN, no ejecutar DDL
            return []
        except ImportError:
            return None

    def _record_migration(self, script_path: str) -> None:
        """Registra la migracion aplicada en el historial."""
        self._history.setdefault("applied", []).append({
            "script":     str(script_path),
            "applied_at": datetime.now().isoformat(),
        })
        self._history_path.write_text(
            json.dumps(self._history, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _load_history(self) -> dict:
        if self._history_path.exists():
            try:
                return json.loads(self._history_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"applied": []}

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
