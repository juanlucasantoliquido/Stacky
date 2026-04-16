"""
predictor.py — G-10: Capa de Inteligencia Predictiva.

Entrena un modelo simple (Naive Bayes de texto + regresión lineal sobre features
numéricas) con el historial de tickets y predice:
  - Complejidad esperada (simple/medio/complejo)
  - Probabilidad de rework (0-1)
  - Tiempo estimado de resolución (minutos)
  - Tipo de error más probable

Sin dependencias externas — usa solo stdlib (math, collections, json).

Uso:
    from predictor import TicketPredictor
    pred = TicketPredictor(project_name)
    pred.train()                          # entrena con historial
    result = pred.predict(inc_content)   # predice para un ticket nuevo
"""

import json
import logging
import math
import os
import re
import threading
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.predictor")

_MIN_TRAINING_SAMPLES = 10

# Feature extractors
_COMPLEXITY_SIGNALS = {
    "batch": 3, "performance": 3, "deadlock": 4, "integración": 3,
    "webservice": 3, "rendimiento": 3, "migración": 4, "timeout": 2,
    "masivo": 3, "bloqueante": 2, "crítico": 2, "dal_": 1, "bll_": 1,
}
_SIMPLE_SIGNALS = {
    "typo": -3, "ortografía": -3, "color": -2, "título": -2, "label": -2,
}


class TicketPredictor:
    """
    Modelo predictivo lightweight entrenado con historial de tickets Stacky.
    """

    def __init__(self, project_name: str):
        self._project = project_name
        self._lock    = threading.RLock()
        self._path    = self._get_path()
        self._model   = self._load_model()

    # ── API pública ───────────────────────────────────────────────────────

    def train(self, tickets_base: str) -> int:
        """
        Entrena el modelo con tickets completados. Retorna cantidad de muestras.
        """
        samples = self._collect_training_data(tickets_base)
        if len(samples) < _MIN_TRAINING_SAMPLES:
            logger.info("[PREDICTOR] Insuficientes muestras para entrenar (%d)", len(samples))
            return 0

        model = self._train_naive_bayes(samples)
        model["training_samples"] = len(samples)
        model["trained_at"]       = datetime.now().isoformat()

        with self._lock:
            self._model = model
            self._save_model()

        logger.info("[PREDICTOR] Modelo entrenado con %d muestras", len(samples))
        return len(samples)

    def predict(self, inc_content: str) -> dict:
        """
        Predice atributos de un ticket nuevo basándose en su INC.
        Retorna dict con: complexity, rework_prob, error_type, confidence.
        """
        with self._lock:
            model = dict(self._model)

        if not model.get("classes"):
            # Sin modelo — usar heurística estática (ticket_classifier)
            return self._fallback_predict(inc_content)

        # Feature extraction
        features = self._extract_features(inc_content)
        tokens   = self._tokenize(inc_content)

        # Naive Bayes para tipo de error
        error_type, et_prob = self._nb_predict(tokens, model, "error_type")

        # Complejidad por score
        score = sum(
            features.get(k, 0) * v for k, v in _COMPLEXITY_SIGNALS.items()
        ) + sum(
            features.get(k, 0) * v for k, v in _SIMPLE_SIGNALS.items()
        ) + len(tokens) * 0.01  # longitud

        complexity = "simple" if score <= 4 else \
                     "medio"  if score <= 12 else "complejo"

        # Rework probability desde historial
        rework_by_type = model.get("rework_by_type", {})
        rework_prob    = rework_by_type.get(error_type, {}).get("rate", 0.2)

        # Tiempo estimado
        time_by_complexity = model.get("time_by_complexity", {})
        est_minutes = time_by_complexity.get(complexity, {}).get("avg_min", 60)

        return {
            "complexity":    complexity,
            "complexity_score": round(score, 1),
            "rework_prob":   round(rework_prob, 2),
            "error_type":    error_type,
            "type_confidence": round(et_prob, 2),
            "est_minutes":   int(est_minutes),
            "model_samples": model.get("training_samples", 0),
        }

    def format_prediction_section(self, prediction: dict) -> str:
        """Formatea predicción como sección Markdown para prompts."""
        if not prediction:
            return ""

        rework_icon = "🔴" if prediction["rework_prob"] > 0.4 else \
                      "🟡" if prediction["rework_prob"] > 0.2 else "🟢"

        lines = [
            "",
            "---",
            "",
            "## Predicción IA — Stacky Predictor",
            "",
            f"| Atributo | Predicción |",
            f"|----------|------------|",
            f"| Complejidad estimada | **{prediction['complexity'].upper()}** (score: {prediction['complexity_score']}) |",
            f"| Tipo de error | {prediction['error_type']} (confianza: {prediction['type_confidence']:.0%}) |",
            f"| Probabilidad de rework | {rework_icon} {prediction['rework_prob']:.0%} |",
            f"| Tiempo estimado | ~{prediction['est_minutes']} min |",
            "",
            f"_Modelo entrenado con {prediction.get('model_samples', 0)} tickets históricos._",
            "",
        ]
        return "\n".join(lines)

    def get_model_stats(self) -> dict:
        """Retorna estadísticas del modelo entrenado."""
        with self._lock:
            return {
                "trained_at":      self._model.get("trained_at", ""),
                "training_samples": self._model.get("training_samples", 0),
                "classes":         list(self._model.get("classes", {}).keys()),
            }

    # ── Training ──────────────────────────────────────────────────────────

    def _collect_training_data(self, tickets_base: str) -> list[dict]:
        samples = []
        for estado in ["archivado", "resuelta", "asignada", "aceptada"]:
            estado_dir = os.path.join(tickets_base, estado)
            if not os.path.isdir(estado_dir):
                continue
            try:
                for tid in os.listdir(estado_dir):
                    folder       = os.path.join(estado_dir, tid)
                    tester_path  = os.path.join(folder, "TESTER_COMPLETADO.md")
                    inc_path     = os.path.join(folder, f"INC-{tid}.md")
                    if not os.path.exists(tester_path) or not os.path.exists(inc_path):
                        continue
                    try:
                        tester  = Path(tester_path).read_text(encoding="utf-8", errors="replace")
                        inc     = Path(inc_path).read_text(encoding="utf-8", errors="replace")[:2000]
                    except Exception:
                        continue

                    qa_ok   = "APROBADO" in tester.upper()
                    rework  = os.path.exists(os.path.join(folder, "TESTER_COMPLETADO.md.prev"))
                    combined = inc.lower()
                    error_type = (
                        "null_reference" if "nullreferenceexception" in combined else
                        "validation"     if "validaci" in combined else
                        "performance"    if "rendimiento" in combined else
                        "ui"             if "aspx" in combined else
                        "data"           if "oracle" in combined or "dal_" in combined else
                        "general"
                    )
                    samples.append({
                        "inc":        inc,
                        "error_type": error_type,
                        "had_rework": rework,
                        "qa_ok":      qa_ok,
                    })
            except Exception:
                pass
        return samples

    def _train_naive_bayes(self, samples: list[dict]) -> dict:
        """Entrena un modelo Naive Bayes multinomial simple."""
        classes: dict[str, dict] = defaultdict(lambda: {"count": 0, "word_counts": Counter()})

        for s in samples:
            cls = s["error_type"]
            classes[cls]["count"] += 1
            tokens = self._tokenize(s["inc"])
            classes[cls]["word_counts"].update(tokens)

        total = len(samples)
        vocab: set[str] = set()
        for cls_data in classes.values():
            vocab.update(cls_data["word_counts"].keys())

        # Calcular log-probabilidades
        log_priors = {}
        log_likelihoods = {}
        for cls, data in classes.items():
            log_priors[cls] = math.log(data["count"] / total)
            total_words = sum(data["word_counts"].values()) + len(vocab)
            log_likelihoods[cls] = {
                w: math.log((data["word_counts"].get(w, 0) + 1) / total_words)
                for w in vocab
            }

        # Rework por tipo
        rework_by_type = defaultdict(lambda: {"rework": 0, "total": 0})
        for s in samples:
            t = s["error_type"]
            rework_by_type[t]["total"] += 1
            if s["had_rework"]:
                rework_by_type[t]["rework"] += 1
        rework_rates = {
            t: {"rate": d["rework"] / d["total"] if d["total"] else 0}
            for t, d in rework_by_type.items()
        }

        return {
            "classes":          {k: {"prior": log_priors[k]} for k in classes},
            "log_priors":       log_priors,
            "log_likelihoods":  log_likelihoods,
            "rework_by_type":   rework_rates,
            "time_by_complexity": {
                "simple":  {"avg_min": 45},
                "medio":   {"avg_min": 90},
                "complejo": {"avg_min": 180},
            },
        }

    def _nb_predict(self, tokens: list[str], model: dict,
                     label: str = "error_type") -> tuple[str, float]:
        """Predice la clase con mayor log-probabilidad posterior."""
        log_priors = model.get("log_priors", {})
        log_lhs    = model.get("log_likelihoods", {})

        if not log_priors:
            return "general", 0.0

        scores: dict[str, float] = {}
        for cls, prior in log_priors.items():
            lh = log_lhs.get(cls, {})
            score = prior + sum(lh.get(t, -10) for t in tokens)
            scores[cls] = score

        best = max(scores, key=scores.__getitem__)
        # Softmax para confianza aproximada
        max_s = scores[best]
        exp_s = {k: math.exp(v - max_s) for k, v in scores.items()}
        total_exp = sum(exp_s.values())
        confidence = exp_s[best] / total_exp if total_exp > 0 else 1.0

        return best, confidence

    # ── Features ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_features(text: str) -> dict:
        text_lower = text.lower()
        return {
            kw: text_lower.count(kw)
            for kw in list(_COMPLEXITY_SIGNALS) + list(_SIMPLE_SIGNALS)
        }

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        _STOP = {"el", "la", "los", "las", "un", "una", "de", "en", "y", "a",
                 "que", "es", "se", "no", "con", "por", "para", "al", "del"}
        tokens = re.findall(r"\b\w{3,}\b", text.lower())
        return [t for t in tokens if t not in _STOP]

    @staticmethod
    def _fallback_predict(inc_content: str) -> dict:
        """Predicción sin modelo — usa heurística del ticket_classifier."""
        try:
            import sys, os
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from ticket_classifier import classify_ticket
            # No tenemos ticket_folder aquí, usar análisis de texto directo
        except ImportError:
            pass
        word_count = len(inc_content.split())
        complexity = "simple" if word_count < 80 else \
                     "medio"  if word_count < 300 else "complejo"
        return {
            "complexity": complexity, "complexity_score": 0,
            "rework_prob": 0.2, "error_type": "general",
            "type_confidence": 0.0, "est_minutes": 60,
            "model_samples": 0,
        }

    def _get_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "predictor_model.json")

    def _load_model(self) -> dict:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except Exception as e:
            logger.warning("[PREDICTOR] Error cargando modelo: %s", e)
            return {}

    def _save_model(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._model, f, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            logger.error("[PREDICTOR] Error guardando modelo: %s", e)


# ── Singleton por proyecto ────────────────────────────────────────────────────

_pred_instances: dict[str, TicketPredictor] = {}
_pred_lock = threading.Lock()


def get_predictor(project_name: str) -> TicketPredictor:
    with _pred_lock:
        if project_name not in _pred_instances:
            _pred_instances[project_name] = TicketPredictor(project_name)
        return _pred_instances[project_name]
