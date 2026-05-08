"""
allocators — Módulo de asignación transaccional de IDs RIDIOMA.

Garantiza que no se reutilice ni duplique ningún IDTEXTO, eliminando la
dependencia del LLM para calcular MAX(IDTEXTO)+1.

Uso:
    from allocators.ridioma_allocator import allocate, RidiomaEntry
"""
from .ridioma_allocator import allocate, RidiomaEntry

__all__ = ["allocate", "RidiomaEntry"]
