"""Aísla el logging de pytest (Plan 145 / V7): setea STACKY_TEST_MODE antes de
que cualquier módulo de app importe/instale el FileHandler, para que los tests
no escriban en backend/data/logs/. También asegura backend/ en sys.path."""
import os
import sys

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

os.environ.setdefault("STACKY_TEST_MODE", "1")
