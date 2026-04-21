"""
knowledge_base.py — E-01: Knowledge Base de Tickets Resueltos (RAG lite).

Construye un índice TF-IDF sobre tickets ya procesados (con QA aprobado)
y permite buscar los más similares a un ticket nuevo. Los resultados se
inyectan en el prompt del PM para darle contexto de soluciones anteriores.

Sin dependencias externas: solo stdlib (math, re, json).

Uso:
    from knowledge_base import KnowledgeBase
    kb = KnowledgeBase(tickets_base, project_name)
    kb.rebuild_index()                     # reconstruir desde cero
    results = kb.search(inc_content, k=3)  # buscar similares
    section = kb.format_kb_section(results) # Markdown para prompt PM
"""

import json
import logging
import math
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.knowledge_base")

# Directorio del índice dentro de Stacky/knowledge/{project}/
_INDEX_FILENAME = "kb_index.json"


# ── Tokenización ──────────────────────────────────────────────────────────────

_STOP_ES = frozenset([
    "el", "la", "los", "las", "un", "una", "de", "en", "y", "a", "que",
    "es", "se", "no", "con", "por", "para", "al", "del", "lo", "le", "su",
    "si", "hay", "pero", "como", "más", "este", "esta", "estos", "estas",
    "también", "su", "sus", "son", "fue", "era", "ser", "estar", "tiene",
    "han", "ha", "he", "al", "cuando", "donde", "quien", "cual", "cuales",
])


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"\b[a-záéíóúüñA-ZÁÉÍÓÚÜÑ\w]{3,}\b", text.lower())
    return [t for t in tokens if t not in _STOP_ES]


def _tf(tokens: list[str]) -> dict[str, float]:
    freq: dict[str, int] = {}
    for t in tokens:
        freq[t] = freq.get(t, 0) + 1
    n = len(tokens) or 1
    return {t: c / n for t, c in freq.items()}


def _cosine(vec_a: dict, vec_b: dict, idf: dict) -> float:
    """Cosine similarity entre dos TF dicts, ponderado por IDF."""
    keys = set(vec_a) & set(vec_b)
    if not keys:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] * idf.get(k, 1.0) ** 2 for k in keys)
    norm_a = math.sqrt(sum((vec_a[k] * idf.get(k, 1.0)) ** 2 for k in vec_a))
    norm_b = math.sqrt(sum((vec_b[k] * idf.get(k, 1.0)) ** 2 for k in vec_b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0


# ── Clase principal ───────────────────────────────────────────────────────────

class KnowledgeBase:
    """
    Índice TF-IDF liviano sobre tickets resueltos con QA aprobado.
    El índice se persiste en knowledge/{project}/kb_index.json.
    """

    def __init__(self, tickets_base: str, project_name: str):
        self._tickets_base  = tickets_base
        self._project_name  = project_name
        self._index_path    = self._get_index_path()
        self._index: dict   = {}   # {ticket_id: {tf, title, types, solution_hint}}
        self._idf:   dict   = {}   # {term: idf_score}
        self._loaded        = False

    # ── API pública ───────────────────────────────────────────────────────

    def ensure_loaded(self) -> None:
        """Carga el índice desde disco si no está en memoria."""
        if not self._loaded:
            self._load_index()
            self._loaded = True

    def rebuild_index(self) -> int:
        """
        Reconstruye el índice desde cero leyendo todos los tickets con
        TESTER_COMPLETADO.md que contenga APROBADO. Retorna cantidad indexada.
        """
        logger.info("[KB] Reconstruyendo índice de knowledge base...")
        docs: dict[str, dict] = {}

        search_dirs = []
        for estado in ["archivado", "resuelta", "asignada", "aceptada"]:
            d = os.path.join(self._tickets_base, estado)
            if os.path.isdir(d):
                search_dirs.append(d)

        for base_dir in search_dirs:
            try:
                for tid in os.listdir(base_dir):
                    ticket_folder = os.path.join(base_dir, tid)
                    tester_path   = os.path.join(ticket_folder, "TESTER_COMPLETADO.md")
                    if not os.path.exists(tester_path):
                        continue
                    try:
                        tester = Path(tester_path).read_text(encoding="utf-8", errors="replace")
                        if "APROBADO" not in tester.upper():
                            continue
                    except Exception:
                        continue

                    doc = self._build_doc(tid, ticket_folder)
                    if doc:
                        docs[tid] = doc
            except Exception as e:
                logger.debug("[KB] Error en %s: %s", base_dir, e)

        # Calcular IDF
        self._idf   = self._compute_idf(docs)
        self._index = docs
        self._loaded = True
        self._save_index()
        logger.info("[KB] Índice reconstruido: %d documentos", len(docs))
        return len(docs)

    def add_ticket(self, ticket_id: str, ticket_folder: str) -> bool:
        """
        Agrega o actualiza un ticket individual al índice.
        Retorna True si fue indexado.
        """
        self.ensure_loaded()
        doc = self._build_doc(ticket_id, ticket_folder)
        if not doc:
            return False
        self._index[ticket_id] = doc
        # Recalcular IDF incrementalmente (aprox: añadir doc al corpus)
        self._idf = self._compute_idf(self._index)
        self._save_index()
        return True

    def search(self, query: str, k: int = 3) -> list[dict]:
        """
        Busca los k tickets más similares a la query (texto del INC).
        Retorna lista de dicts con: ticket_id, score, title, solution_hint, types.
        """
        self.ensure_loaded()
        if not self._index:
            return []

        q_tokens = _tokenize(query)
        q_tf     = _tf(q_tokens)

        scored = []
        for tid, doc in self._index.items():
            sim = _cosine(q_tf, doc["tf"], self._idf)
            if sim > 0.05:
                scored.append((sim, tid, doc))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for sim, tid, doc in scored[:k]:
            results.append({
                "ticket_id":     tid,
                "score":         round(sim, 3),
                "title":         doc.get("title", ""),
                "solution_hint": doc.get("solution_hint", ""),
                "types":         doc.get("types", []),
                "files":         doc.get("files", []),
            })
        return results

    def format_kb_section(self, results: list[dict]) -> str:
        """Formatea resultados como sección Markdown para inyectar en prompt PM."""
        if not results:
            return ""
        lines = [
            "",
            "---",
            "",
            "## Knowledge Base — Tickets similares resueltos anteriormente",
            "",
            "_Tickets con QA aprobado que pueden orientar el análisis. Usar como referencia._",
            "",
        ]
        for i, r in enumerate(results, 1):
            tid   = r["ticket_id"]
            score = r["score"]
            title = r.get("title", "")
            hint  = r.get("solution_hint", "")
            files = r.get("files", [])
            types = ", ".join(r.get("types", ["general"]))

            lines.append(f"### #{i} — Ticket #{tid} ({types}) — similitud {score:.0%}")
            lines.append("")
            if title:
                lines.append(f"**Título:** {title}")
                lines.append("")
            if hint:
                lines.append(f"**Solución aplicada:** {hint[:300]}")
                lines.append("")
            if files:
                lines.append(f"**Archivos involucrados:** {', '.join(files[:4])}")
                lines.append("")

        return "\n".join(lines)

    # ── Internals ─────────────────────────────────────────────────────────

    def _build_doc(self, ticket_id: str, ticket_folder: str) -> dict | None:
        """Construye la representación de un ticket para el índice."""
        inc_path  = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
        arq_path  = os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md")
        anal_path = os.path.join(ticket_folder, "ANALISIS_TECNICO.md")
        dev_path  = os.path.join(ticket_folder, "DEV_COMPLETADO.md")

        if not os.path.exists(inc_path):
            return None

        try:
            inc  = Path(inc_path ).read_text(encoding="utf-8", errors="replace")[:4000]
            arq  = Path(arq_path ).read_text(encoding="utf-8", errors="replace")[:2000] \
                   if os.path.exists(arq_path)  else ""
            anal = Path(anal_path).read_text(encoding="utf-8", errors="replace")[:2000] \
                   if os.path.exists(anal_path) else ""
            dev  = Path(dev_path ).read_text(encoding="utf-8", errors="replace")[:1000] \
                   if os.path.exists(dev_path)  else ""
        except Exception:
            return None

        combined = inc + " " + arq + " " + anal
        tokens   = _tokenize(combined)
        if len(tokens) < 10:
            return None

        # Extraer título del INC (primera línea no vacía o encabezado)
        title = ""
        for line in inc.splitlines():
            stripped = line.strip("# ").strip()
            if len(stripped) > 10:
                title = stripped[:120]
                break

        # Hint de solución: primera línea de ARQUITECTURA o ANALISIS con contenido
        solution_hint = ""
        for src in [arq, anal]:
            for line in src.splitlines():
                stripped = line.strip()
                if len(stripped) > 30 and not stripped.startswith("#"):
                    solution_hint = stripped[:300]
                    break
            if solution_hint:
                break

        # Archivos modificados
        files = re.findall(r'[\w/\\]+\.(?:cs|aspx\.cs|aspx|sql|vb)', dev + arq,
                           re.IGNORECASE)
        files = list(dict.fromkeys(f.replace("\\", "/") for f in files))[:6]

        # Tipos de patrón (reutilizar lógica del pattern_extractor si disponible)
        types = []
        combined_lower = combined.lower()
        type_keywords = {
            "null_reference": ["nullreferenceexception", "object reference"],
            "validation":     ["validación", "campo requerido", "error.agregar"],
            "dal_query":      ["dal_", "oraclecommand", "query"],
            "performance":    ["rendimiento", "lentitud", "timeout"],
            "ui_webforms":    ["aspx", "postback", "gridview"],
            "batch_process":  ["batch", "scheduler"],
            "integration":    ["webservice", "soap", "rest api"],
        }
        for ptype, kws in type_keywords.items():
            if sum(1 for kw in kws if kw in combined_lower) >= 1:
                types.append(ptype)
        if not types:
            types = ["general"]

        return {
            "tf":            _tf(tokens),
            "title":         title,
            "solution_hint": solution_hint,
            "types":         types,
            "files":         files,
            "indexed_at":    datetime.now().isoformat(),
        }

    @staticmethod
    def _compute_idf(docs: dict) -> dict:
        """Calcula IDF para todos los términos en el corpus."""
        n = len(docs)
        if n == 0:
            return {}
        df: dict[str, int] = {}
        for doc in docs.values():
            for term in doc["tf"]:
                df[term] = df.get(term, 0) + 1
        return {term: math.log((n + 1) / (freq + 1)) + 1
                for term, freq in df.items()}

    def _get_index_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project_name)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, _INDEX_FILENAME)

    def _load_index(self) -> None:
        try:
            with open(self._index_path, encoding="utf-8") as f:
                data = json.load(f)
            self._index = data.get("docs", {})
            self._idf   = data.get("idf", {})
            logger.debug("[KB] Índice cargado: %d documentos", len(self._index))
        except FileNotFoundError:
            self._index = {}
            self._idf   = {}
        except Exception as e:
            logger.warning("[KB] Error cargando índice: %s", e)
            self._index = {}
            self._idf   = {}

    def _save_index(self) -> None:
        try:
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump({"docs": self._index, "idf": self._idf,
                           "saved_at": datetime.now().isoformat()},
                          f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error("[KB] Error guardando índice: %s", e)


# ── Singleton por proyecto ────────────────────────────────────────────────────

_kb_instances: dict[str, KnowledgeBase] = {}


def get_kb(tickets_base: str, project_name: str) -> KnowledgeBase:
    """Retorna (y cachea) una instancia de KnowledgeBase por proyecto."""
    if project_name not in _kb_instances:
        _kb_instances[project_name] = KnowledgeBase(tickets_base, project_name)
    return _kb_instances[project_name]
