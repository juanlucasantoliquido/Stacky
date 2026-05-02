"""
safety — Módulo de seguridad para operaciones de BD.

Provee un wrapper físico que rechaza sentencias DML antes de llegar a la BD,
reemplazando la disciplina del LLM con un control determinístico.

Uso:
    from safety.db_safety import is_safe_sql, SqlSafetyDecision
"""
from .db_safety import is_safe_sql, SqlSafetyDecision

__all__ = ["is_safe_sql", "SqlSafetyDecision"]
