"""
estimation_model.py — F2 Fase 2. Modelo de regresión lineal para estimar
``actual_minutes`` a partir de los 6 ``ScoringFactors`` + ``similar_tickets_count``.

Este módulo:
  - Entrena un modelo de mínimos cuadrados (ecuaciones normales) sobre los
    registros cerrados de ``estimations.json``.
  - Persiste los coeficientes en ``data/estimation_model.json``.
  - Provee ``predict(factors, similar_count) -> int | None`` para que
    ``ticket_scoring.compute_scoring`` lo consulte.

Diseño:
  - **Python puro**: no requiere numpy/scipy. Usa ecuaciones normales
    ``(X^T X + λI)^-1 X^T y`` con Gauss-Jordan. Esto es más que suficiente
    para ≤ 10 features × ≤ miles de muestras (tamaño realista del store).
  - Regularización Ridge (λ=1e-3) para estabilizar la inversión cuando
    alguna columna es casi-constante.
  - Umbral mínimo: ``MIN_SAMPLES`` muestras cerradas para activar el modelo.
    Por debajo, ``train_model()`` devuelve ``None`` y ``predict()`` también,
    dejando que ``compute_scoring`` caiga al heurístico.
  - Idempotente y thread-safe por archivo (lock de módulo + escritura atómica
    temp+replace).

Re-entrenamiento:
  - Manual: ``POST /api/estimation_model/retrain`` (dashboard_server).
  - Automático: hook en ``estimation_store.record_actual`` cuando cierra una
    nueva entry y ``n_samples % RETRAIN_EVERY == 0``.
"""

from __future__ import annotations

import json
import logging
import math
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger("stacky.estimation_model")

_BASE_DIR = Path(__file__).resolve().parent
_DATA_DIR = _BASE_DIR / "data"
_MODEL_PATH = _DATA_DIR / "estimation_model.json"
_STORE_PATH = _DATA_DIR / "estimations.json"

_lock = threading.RLock()

# Umbral mínimo de samples cerradas para entrenar/aplicar el modelo.
MIN_SAMPLES = 20
# Cada N cierres nuevos, se re-entrena automáticamente.
RETRAIN_EVERY = 5
# Regularización Ridge — estabiliza cuando alguna columna es casi-constante.
_RIDGE_LAMBDA = 1e-3

# Orden canónico de features. ¡NO CAMBIAR sin migrar el modelo persistido!
FEATURE_ORDER: tuple[str, ...] = (
    "tech_complexity",
    "uncertainty",
    "impact",
    "files_affected",
    "functional_risk",
    "external_dep",
    "similar_tickets_count",
)


@dataclass
class ModelStats:
    coefficients: list[float]   # len == len(FEATURE_ORDER)
    intercept:    float
    trained_at:   str           # ISO timestamp
    n_samples:    int
    rmse:         float
    features:     list[str]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ── Persistencia ──────────────────────────────────────────────────────────────

def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            import os
            os.fsync(f.fileno())
        except OSError:
            pass
    tmp.replace(path)


def load_model() -> dict[str, Any] | None:
    """Retorna el modelo persistido, o None si no hay."""
    with _lock:
        if not _MODEL_PATH.exists():
            return None
        try:
            with _MODEL_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("estimation_model: no se pudo leer %s: %s", _MODEL_PATH, e)
            return None


def save_model(stats: ModelStats) -> None:
    with _lock:
        _atomic_write(_MODEL_PATH, stats.to_dict())
        logger.info("estimation_model: modelo guardado (n=%d, rmse=%.2f)",
                    stats.n_samples, stats.rmse)


# ── Lectura de samples cerradas desde estimations.json ───────────────────────

def _load_closed_samples(store_path: Path | None = None) -> list[dict[str, Any]]:
    """
    Lee ``data/estimations.json`` y devuelve la lista de entries con
    ``actual_minutes not null`` (samples cerradas, aptas para entrenar).
    """
    path = store_path or _STORE_PATH
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("estimation_model: no se pudo leer %s: %s", path, e)
        return []
    entries = data.get("entries") or []
    out = []
    for e in entries:
        if e.get("actual_minutes") is None:
            continue
        f = e.get("factors") or {}
        # Filtramos samples con factores incompletos (compat hacia atrás)
        if not all(k in f for k in FEATURE_ORDER[:-1]):
            continue
        out.append(e)
    return out


def _entry_to_features(entry: dict[str, Any]) -> list[float] | None:
    f = entry.get("factors") or {}
    try:
        row = [
            float(f.get("tech_complexity", 0)),
            float(f.get("uncertainty", 0)),
            float(f.get("impact", 0)),
            float(f.get("files_affected", 0)),
            float(f.get("functional_risk", 0)),
            float(f.get("external_dep", 0)),
            float(entry.get("similar_tickets_count", 0) or 0),
        ]
    except (TypeError, ValueError):
        return None
    return row


# ── Álgebra lineal en Python puro ─────────────────────────────────────────────

def _transpose(mat: list[list[float]]) -> list[list[float]]:
    if not mat:
        return []
    rows = len(mat)
    cols = len(mat[0])
    return [[mat[r][c] for r in range(rows)] for c in range(cols)]


def _matmul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    ar, ac = len(a), len(a[0])
    br, bc = len(b), len(b[0])
    if ac != br:
        raise ValueError(f"matmul mismatch: {ar}x{ac} · {br}x{bc}")
    out = [[0.0] * bc for _ in range(ar)]
    for i in range(ar):
        ai = a[i]
        oi = out[i]
        for k in range(ac):
            aik = ai[k]
            if aik == 0.0:
                continue
            bk = b[k]
            for j in range(bc):
                oi[j] += aik * bk[j]
    return out


def _matvec(a: list[list[float]], v: list[float]) -> list[float]:
    return [sum(a[i][k] * v[k] for k in range(len(v))) for i in range(len(a))]


def _invert(mat: list[list[float]]) -> list[list[float]]:
    """Inversa por Gauss-Jordan con pivoteo parcial. Matriz cuadrada nxn."""
    n = len(mat)
    # [ mat | I ]
    aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(mat)]
    for col in range(n):
        # Pivoteo parcial: buscar fila con mayor |a[r][col]|
        pivot_row = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot_row][col]) < 1e-12:
            raise ValueError("matriz singular — no se puede invertir")
        if pivot_row != col:
            aug[col], aug[pivot_row] = aug[pivot_row], aug[col]
        pivot = aug[col][col]
        # Normalizar fila pivot
        for j in range(2 * n):
            aug[col][j] /= pivot
        # Eliminar en otras filas
        for r in range(n):
            if r == col:
                continue
            factor = aug[r][col]
            if factor == 0.0:
                continue
            for j in range(2 * n):
                aug[r][j] -= factor * aug[col][j]
    # Extraer la parte derecha
    return [row[n:] for row in aug]


def _fit_least_squares(X: list[list[float]], y: list[float],
                        ridge: float = _RIDGE_LAMBDA) -> tuple[list[float], float]:
    """
    Resuelve (X^T X + λI)^-1 X^T y. Devuelve ``(coeffs[len=ncols], intercept)``.

    La columna de intercept se agrega internamente (no se espera en X).
    Ridge aplica sólo a las columnas de features (no al intercept) para no
    sesgarlo.
    """
    n_samples = len(X)
    if n_samples == 0:
        raise ValueError("sin muestras")
    n_feat = len(X[0])

    # Agregar columna de 1's para intercept al final.
    Xb = [row + [1.0] for row in X]
    Xt = _transpose(Xb)
    XtX = _matmul(Xt, Xb)

    # Ridge: λI sobre los features, 0 sobre el intercept.
    for i in range(n_feat):
        XtX[i][i] += ridge

    Xty = _matvec(Xt, y)

    inv = _invert(XtX)
    beta = _matvec(inv, Xty)

    coeffs = beta[:n_feat]
    intercept = beta[n_feat]
    return coeffs, intercept


def _rmse(X: list[list[float]], y: list[float],
          coeffs: list[float], intercept: float) -> float:
    if not y:
        return 0.0
    se = 0.0
    for row, actual in zip(X, y):
        pred = intercept + sum(c * v for c, v in zip(coeffs, row))
        diff = pred - actual
        se += diff * diff
    return math.sqrt(se / len(y))


# ── API pública ──────────────────────────────────────────────────────────────

def train_model(store_path: Path | None = None,
                 *, min_samples: int = MIN_SAMPLES) -> ModelStats | None:
    """
    Entrena el modelo desde ``estimations.json``. Devuelve stats o None si no
    hay suficientes samples.
    """
    with _lock:
        samples = _load_closed_samples(store_path)
        if len(samples) < min_samples:
            logger.info(
                "estimation_model: entrenamiento skip — %d samples < umbral %d",
                len(samples), min_samples,
            )
            return None

        X: list[list[float]] = []
        y: list[float] = []
        for e in samples:
            row = _entry_to_features(e)
            if row is None:
                continue
            try:
                actual = float(e["actual_minutes"])
            except (TypeError, ValueError):
                continue
            if actual <= 0:
                continue
            X.append(row)
            y.append(actual)

        if len(y) < min_samples:
            logger.info("estimation_model: samples válidas (%d) < umbral %d",
                        len(y), min_samples)
            return None

        try:
            coeffs, intercept = _fit_least_squares(X, y)
        except Exception as e:
            logger.warning("estimation_model: fit falló: %s", e)
            return None
        rmse = _rmse(X, y, coeffs, intercept)

        stats = ModelStats(
            coefficients=[round(float(c), 6) for c in coeffs],
            intercept=round(float(intercept), 6),
            trained_at=datetime.now(timezone.utc).isoformat(),
            n_samples=len(y),
            rmse=round(float(rmse), 3),
            features=list(FEATURE_ORDER),
        )
        save_model(stats)
        return stats


def predict(factors: Any, similar_count: int) -> int | None:
    """
    Predice ``actual_minutes`` (int redondeado) a partir de los factores.
    Retorna None si no hay modelo entrenado o si el modelo está desalineado
    con el orden de features actual.

    ``factors`` puede ser un ``ScoringFactors`` o un dict con esas claves.
    """
    model = load_model()
    if not model:
        return None
    coeffs = model.get("coefficients") or []
    intercept = model.get("intercept")
    features = model.get("features") or list(FEATURE_ORDER)
    if (not coeffs or intercept is None
            or len(coeffs) != len(FEATURE_ORDER)
            or tuple(features) != FEATURE_ORDER):
        logger.debug("estimation_model: modelo incompatible con FEATURE_ORDER — ignorando")
        return None

    # Normalizar factors → dict
    if hasattr(factors, "to_dict"):
        fd = factors.to_dict()
    elif isinstance(factors, dict):
        fd = factors
    else:
        return None

    try:
        row = [
            float(fd.get("tech_complexity", 0)),
            float(fd.get("uncertainty", 0)),
            float(fd.get("impact", 0)),
            float(fd.get("files_affected", 0)),
            float(fd.get("functional_risk", 0)),
            float(fd.get("external_dep", 0)),
            float(similar_count or 0),
        ]
    except (TypeError, ValueError):
        return None

    pred = float(intercept) + sum(c * v for c, v in zip(coeffs, row))
    if not math.isfinite(pred) or pred <= 0:
        # El modelo puede devolver valores absurdos con pocos datos —
        # en ese caso mejor fallback a heurística.
        return None
    return int(round(pred))


def maybe_retrain_after_close(n_closed_samples: int) -> bool:
    """
    Dispara re-entrenamiento si ``n_closed_samples`` es múltiplo de
    ``RETRAIN_EVERY`` y está ≥ ``MIN_SAMPLES``. Devuelve True si entrenó.
    """
    if n_closed_samples < MIN_SAMPLES:
        return False
    if n_closed_samples % RETRAIN_EVERY != 0:
        return False
    try:
        stats = train_model()
        return stats is not None
    except Exception as e:
        logger.warning("estimation_model: maybe_retrain falló: %s", e)
        return False
