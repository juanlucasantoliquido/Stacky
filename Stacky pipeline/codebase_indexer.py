"""
codebase_indexer.py — G-02: Índice del Codebase para Búsqueda Semántica.

Construye un índice TF-IDF invertido de todo el codebase (archivos .cs, .aspx, .sql)
para encontrar rápidamente los archivos más relevantes dado un INC o símbolo.

A diferencia de blast_radius_analyzer (que busca impacto), este módulo
ayuda al PM/DEV a encontrar los archivos correctos para implementar el fix.

Sin dependencias externas. El índice se reconstruye en background
cuando se detectan cambios en el workspace.

Uso:
    from codebase_indexer import CodebaseIndexer
    idx = CodebaseIndexer(workspace_root, project_name)
    idx.build_index()                        # construir o reconstruir
    results = idx.search("OracleCommand RST_PAGOS", top_k=5)
    section  = idx.format_context_section(results)
"""

import json
import logging
import math
import os
import re
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.codebase_indexer")

_SKIP_DIRS  = {"bin", "obj", ".vs", ".git", "packages", "node_modules"}
_CODE_EXTS  = {".cs", ".aspx.cs", ".aspx", ".sql", ".vb"}
_MAX_FILES  = 5000
_MAX_CONTENT_PER_FILE = 6000
_STOP_WORDS = frozenset([
    "using", "namespace", "class", "public", "private", "protected", "static",
    "void", "return", "new", "this", "base", "true", "false", "null", "var",
    "string", "int", "bool", "object", "list", "dictionary", "if", "else",
    "for", "foreach", "while", "try", "catch", "finally", "throw",
    "el", "la", "de", "en", "y", "a", "que", "es", "se", "no", "con",
])


def _tokenize_code(text: str) -> list[str]:
    """Tokeniza código fuente: split por CamelCase + símbolos."""
    # Split CamelCase: FrmPagos → frm pagos
    text = re.sub(r'([A-Z][a-z]+)', r' \1', text)
    text = re.sub(r'([A-Z]+)(?=[A-Z][a-z])', r' \1', text)
    tokens = re.findall(r'\b[a-zA-Z][a-zA-Z0-9_]{2,}\b', text.lower())
    return [t for t in tokens if t not in _STOP_WORDS]


class CodebaseIndexer:
    """
    Índice TF-IDF invertido del codebase para búsqueda de archivos relevantes.
    """

    def __init__(self, workspace_root: str, project_name: str):
        self._workspace = workspace_root
        self._project   = project_name
        self._lock      = threading.RLock()
        self._path      = self._get_index_path()
        self._index: dict     = {}   # {rel_path: {tf, snippet}}
        self._idf:   dict     = {}   # {term: idf_score}
        self._loaded          = False

    # ── API pública ───────────────────────────────────────────────────────

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self._load()
            self._loaded = True

    def build_index(self, progress_cb=None) -> int:
        """
        Construye el índice desde cero. Retorna cantidad de archivos indexados.
        progress_cb: callback(current, total) para progreso.
        """
        logger.info("[CODEBASE] Construyendo índice de %s...", self._workspace)
        docs: dict[str, dict] = {}
        files_to_index        = list(self._enumerate_files())
        total = len(files_to_index)

        for i, (rel_path, full_path) in enumerate(files_to_index):
            if progress_cb:
                progress_cb(i + 1, total)
            try:
                content  = Path(full_path).read_text(
                    encoding="utf-8", errors="replace")[:_MAX_CONTENT_PER_FILE]
                tokens   = _tokenize_code(content)
                if len(tokens) < 3:
                    continue
                snippet  = content[:200].replace("\n", " ").strip()
                docs[rel_path] = {"tf": self._compute_tf(tokens), "snippet": snippet}
            except Exception:
                pass

        with self._lock:
            self._index  = docs
            self._idf    = self._compute_idf(docs)
            self._loaded = True
            self._save()

        logger.info("[CODEBASE] Índice construido: %d archivos", len(docs))
        return len(docs)

    def build_index_async(self) -> threading.Thread:
        """Construye el índice en un thread background."""
        t = threading.Thread(target=self.build_index, daemon=True,
                             name="codebase-indexer")
        t.start()
        return t

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Busca los archivos más relevantes para la query.
        Retorna lista de dicts con path, score, snippet.
        """
        self.ensure_loaded()
        if not self._index:
            return []

        q_tokens = _tokenize_code(query)
        q_tf     = self._compute_tf(q_tokens)

        scored = []
        for rel_path, doc in self._index.items():
            sim = self._cosine(q_tf, doc["tf"])
            if sim > 0.01:
                scored.append((sim, rel_path, doc))

        scored.sort(key=lambda x: -x[0])
        return [
            {"path": rp, "score": round(sim, 3), "snippet": doc["snippet"]}
            for sim, rp, doc in scored[:top_k]
        ]

    def search_by_symbol(self, symbol: str, top_k: int = 10) -> list[str]:
        """
        Búsqueda exacta de símbolo (clase, método) en el índice.
        Más preciso que search() para símbolos conocidos.
        """
        self.ensure_loaded()
        sym_lower = symbol.lower()
        results   = []
        for rel_path, doc in self._index.items():
            if sym_lower in doc["tf"]:
                results.append((doc["tf"][sym_lower], rel_path))
        results.sort(reverse=True)
        return [rp for _, rp in results[:top_k]]

    def format_context_section(self, results: list[dict]) -> str:
        """Formatea resultados como sección Markdown para prompts."""
        if not results:
            return ""
        lines = [
            "",
            "---",
            "",
            "## Codebase — Archivos más relevantes al ticket",
            "",
            "_Encontrados por búsqueda semántica en el workspace._",
            "",
            "| Archivo | Relevancia | Preview |",
            "|---------|------------|---------|",
        ]
        for r in results:
            snippet = r["snippet"][:80].replace("|", "\\|")
            lines.append(f"| `{r['path']}` | {r['score']:.0%} | {snippet} |")
        lines.append("")
        return "\n".join(lines)

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "indexed_files": len(self._index),
                "workspace":     self._workspace,
                "project":       self._project,
            }

    # ── Internals ─────────────────────────────────────────────────────────

    def _enumerate_files(self):
        """Enumera (rel_path, full_path) de archivos a indexar."""
        count = 0
        for root, dirs, files in os.walk(self._workspace):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            if count >= _MAX_FILES:
                break
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                full_ext = fname.lower()  # para .aspx.cs
                if ext not in _CODE_EXTS and not full_ext.endswith(".aspx.cs"):
                    continue
                full_path = os.path.join(root, fname)
                rel_path  = os.path.relpath(full_path, self._workspace).replace("\\", "/")
                yield rel_path, full_path
                count += 1
                if count >= _MAX_FILES:
                    return

    @staticmethod
    def _compute_tf(tokens: list[str]) -> dict[str, float]:
        freq: dict[str, int] = {}
        for t in tokens:
            freq[t] = freq.get(t, 0) + 1
        n = len(tokens) or 1
        return {t: c / n for t, c in freq.items()}

    @staticmethod
    def _compute_idf(docs: dict) -> dict:
        n = len(docs)
        if n == 0:
            return {}
        df: dict[str, int] = {}
        for doc in docs.values():
            for term in doc["tf"]:
                df[term] = df.get(term, 0) + 1
        return {t: math.log((n + 1) / (f + 1)) + 1 for t, f in df.items()}

    def _cosine(self, vec_a: dict, vec_b: dict) -> float:
        keys = set(vec_a) & set(vec_b)
        if not keys:
            return 0.0
        idf = self._idf
        dot   = sum(vec_a[k] * vec_b[k] * idf.get(k, 1.0) ** 2 for k in keys)
        norm_a = math.sqrt(sum((vec_a[k] * idf.get(k, 1.0)) ** 2 for k in vec_a))
        norm_b = math.sqrt(sum((vec_b[k] * idf.get(k, 1.0)) ** 2 for k in vec_b))
        return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    def _get_index_path(self) -> str:
        base = os.path.dirname(os.path.abspath(__file__))
        kb   = os.path.join(base, "knowledge", self._project)
        os.makedirs(kb, exist_ok=True)
        return os.path.join(kb, "codebase_index.json")

    def _load(self) -> None:
        try:
            with open(self._path, encoding="utf-8") as f:
                data = json.load(f)
            self._index = data.get("docs", {})
            self._idf   = data.get("idf", {})
            logger.debug("[CODEBASE] Índice cargado: %d archivos", len(self._index))
        except FileNotFoundError:
            self._index = {}
            self._idf   = {}
        except Exception as e:
            logger.warning("[CODEBASE] Error cargando índice: %s", e)
            self._index = {}
            self._idf   = {}

    def _save(self) -> None:
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump({"docs": self._index, "idf": self._idf,
                           "saved_at": datetime.now().isoformat()},
                          f, separators=(",", ":"), ensure_ascii=False)
        except Exception as e:
            logger.error("[CODEBASE] Error guardando índice: %s", e)


# ── Singleton ─────────────────────────────────────────────────────────────────

_idx_instances: dict[str, CodebaseIndexer] = {}
_idx_lock = threading.Lock()


def get_codebase_indexer(workspace_root: str, project_name: str) -> CodebaseIndexer:
    with _idx_lock:
        if project_name not in _idx_instances:
            _idx_instances[project_name] = CodebaseIndexer(workspace_root, project_name)
        return _idx_instances[project_name]
