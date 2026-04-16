"""
ridioma_lookup.py — S-02: Reverse Lookup de Mensajes RIDIOMA → Constante → Método.

Cuando un ticket reporta un mensaje de error (ej: "El pedido no fue encontrado"),
este modulo hace el reverse lookup:
  Mensaje visible → constante coMens.mXXXX → metodo(s) que la usan

Esto da a PM el camino exacto de ejecucion sin necesidad de busqueda manual.

Fuentes de datos:
  1. Tabla RIDIOMA en Oracle (si hay conexion configurada)
  2. Archivos coMens.cs / MensajesConst.cs en el trunk (fallback offline)
  3. Cache JSON para evitar consultas repetidas

Uso:
    from ridioma_lookup import RIDIOMALookup
    lookup = RIDIOMALookup(project_name, workspace_root)
    result = lookup.find_message("El pedido no fue encontrado")
    # result.matches      → lista de MessageMatch
    # result.callers      → metodos que usan esa constante
    # result.markdown     → bloque Markdown para prompt PM
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent


@dataclass
class MessageMatch:
    """Un mensaje encontrado en RIDIOMA."""
    constant_name:  str = ""   # ej: coMens.m2847
    message_text:   str = ""   # texto del mensaje en el idioma buscado
    message_id:     str = ""   # ID en tabla RIDIOMA
    similarity:     float = 0.0


@dataclass
class CallerInfo:
    """Un metodo del codebase que usa una constante de mensaje."""
    file_path:    str = ""
    class_name:   str = ""
    method_name:  str = ""
    line_number:  int = 0
    constant_used: str = ""


@dataclass
class LookupResult:
    """Resultado del reverse lookup."""
    query:      str = ""
    found:      bool = False
    matches:    list = field(default_factory=list)
    callers:    list = field(default_factory=list)
    markdown:   str = ""


class RIDIOMALookup:
    """
    Reverse lookup de mensajes RIDIOMA hacia constantes y callers en el codebase.
    """

    def __init__(self, project_name: str, workspace_root: str = None):
        self.project_name = project_name
        self._workspace   = Path(workspace_root) if workspace_root else BASE_DIR.parent.parent
        self._config      = self._load_config()
        self._cache_path  = BASE_DIR / "projects" / project_name / "ridioma_cache.json"
        self._cache       = self._load_cache()
        self._const_index = None  # lazy loaded

    def find_message(self, query: str, top_k: int = 3) -> LookupResult:
        """
        Busca un mensaje por texto y retorna las constantes y callers correspondientes.
        """
        result = LookupResult(query=query)

        # Buscar en cache primero
        cache_key = query.lower().strip()[:100]
        if cache_key in self._cache:
            cached = self._cache[cache_key]
            result.found   = True
            result.matches = [MessageMatch(**m) for m in cached.get("matches", [])]
            result.callers = [CallerInfo(**c) for c in cached.get("callers", [])]
            result.markdown = self._build_markdown(result)
            return result

        # Buscar en Oracle si esta disponible
        matches = self._search_oracle(query, top_k)

        # Fallback: buscar en archivos de constantes del trunk
        if not matches:
            matches = self._search_const_files(query, top_k)

        if matches:
            result.found   = True
            result.matches = matches
            result.callers = self._find_callers(matches)
            # Guardar en cache
            self._cache[cache_key] = {
                "matches": [m.__dict__ for m in matches],
                "callers": [c.__dict__ for c in result.callers],
            }
            self._save_cache()

        result.markdown = self._build_markdown(result)
        return result

    def rebuild_const_index(self) -> int:
        """
        Reconstruye el indice de constantes desde archivos .cs del trunk.
        Retorna la cantidad de constantes indexadas.
        """
        index = {}
        patterns = [
            re.compile(r'public\s+const\s+string\s+(m\d+)\s*=\s*["\'](\w+)["\']', re.IGNORECASE),
            re.compile(r'(m\d+)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE),
        ]

        const_files = list(self._workspace.rglob("coMens*.cs")) + \
                      list(self._workspace.rglob("Mensajes*.cs")) + \
                      list(self._workspace.rglob("*Const*.cs"))

        for fpath in const_files[:20]:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                for pattern in patterns:
                    for match in pattern.finditer(content):
                        const_name, value = match.group(1), match.group(2)
                        index[const_name] = {
                            "file":       str(fpath.relative_to(self._workspace)),
                            "value":      value,
                            "const_name": const_name,
                        }
            except Exception:
                pass

        # Tambien buscar en RIDIOMA_CACHE.sql o archivos de datos
        for sql_file in list(self._workspace.rglob("*ridioma*.sql"))[:3]:
            try:
                content = sql_file.read_text(encoding="utf-8", errors="ignore")
                # INSERT INTO RIDIOMA (ID_MENS, TEXTO, ...) VALUES ('m2847', 'Mensaje', ...)
                for match in re.finditer(
                    r"INSERT.*?RIDIOMA.*?VALUES\s*\(['\"](\w+)['\"],\s*['\"]([^'\"]+)['\"]",
                    content, re.IGNORECASE | re.DOTALL
                ):
                    index[match.group(1)] = {
                        "file":       str(sql_file.relative_to(self._workspace)),
                        "value":      match.group(2),
                        "const_name": match.group(1),
                    }
            except Exception:
                pass

        self._const_index = index
        # Persistir indice
        index_path = BASE_DIR / "projects" / self.project_name / "ridioma_index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return len(index)

    # ── Privados ─────────────────────────────────────────────────────────────

    def _search_oracle(self, query: str, top_k: int) -> list:
        """Busca en Oracle RIDIOMA si hay conexion configurada."""
        conn_str = self._config.get("oracle_connection", "")
        if not conn_str:
            return []
        try:
            import oracledb
            conn    = oracledb.connect(conn_str)
            cursor  = conn.cursor()
            cursor.execute(
                "SELECT ID_MENS, TEXTO FROM RIDIOMA "
                "WHERE UPPER(TEXTO) LIKE UPPER(:q) "
                "AND ROWNUM <= :n",
                q=f"%{query[:50]}%", n=top_k,
            )
            rows = cursor.fetchall()
            conn.close()
            return [
                MessageMatch(
                    constant_name = f"coMens.{row[0]}",
                    message_text  = row[1],
                    message_id    = row[0],
                    similarity    = 1.0,
                )
                for row in rows
            ]
        except Exception:
            return []

    def _search_const_files(self, query: str, top_k: int) -> list:
        """Busca en el indice de archivos de constantes del trunk."""
        if self._const_index is None:
            self._load_const_index()

        if not self._const_index:
            return []

        query_words = set(query.lower().split())
        results     = []

        for const_name, data in self._const_index.items():
            value_words = set(data.get("value", "").lower().split())
            if query_words & value_words:  # interseccion de palabras
                overlap = len(query_words & value_words) / max(len(query_words), 1)
                results.append(MessageMatch(
                    constant_name = f"coMens.{const_name}",
                    message_text  = data.get("value", ""),
                    message_id    = const_name,
                    similarity    = overlap,
                ))

        results.sort(key=lambda m: m.similarity, reverse=True)
        return results[:top_k]

    def _find_callers(self, matches: list) -> list:
        """Busca en el trunk los metodos que usan las constantes encontradas."""
        callers = []
        for match in matches[:2]:  # Limitar para no saturar
            const = match.message_id  # ej: m2847
            pattern = re.compile(rf"\b{re.escape(const)}\b")

            for fpath in list(self._workspace.rglob("*.cs"))[:500]:
                try:
                    lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
                    for i, line in enumerate(lines):
                        if pattern.search(line):
                            # Buscar el metodo contenedor hacia atras
                            method_name = self._find_enclosing_method(lines, i)
                            class_name  = self._find_enclosing_class(lines, i)
                            try:
                                rel = str(fpath.relative_to(self._workspace))
                            except ValueError:
                                rel = fpath.name
                            callers.append(CallerInfo(
                                file_path     = rel,
                                class_name    = class_name,
                                method_name   = method_name,
                                line_number   = i + 1,
                                constant_used = f"coMens.{const}",
                            ))
                            if len(callers) >= 5:
                                break
                except Exception:
                    pass
                if len(callers) >= 5:
                    break

        return callers

    def _find_enclosing_method(self, lines: list, line_idx: int) -> str:
        """Busca el metodo que contiene la linea dada."""
        method_pattern = re.compile(
            r"(?:public|private|protected|internal|static)\s+[\w<>\[\]]+\s+(\w+)\s*\("
        )
        for i in range(line_idx, max(0, line_idx - 50), -1):
            match = method_pattern.search(lines[i])
            if match:
                return match.group(1)
        return "unknown"

    def _find_enclosing_class(self, lines: list, line_idx: int) -> str:
        """Busca la clase que contiene la linea dada."""
        class_pattern = re.compile(r"(?:public|internal)\s+(?:partial\s+)?class\s+(\w+)")
        for i in range(line_idx, max(0, line_idx - 200), -1):
            match = class_pattern.search(lines[i])
            if match:
                return match.group(1)
        return "unknown"

    def _build_markdown(self, result: LookupResult) -> str:
        if not result.found:
            return f"## RIDIOMA Lookup\n\nNo se encontro constante para: `{result.query}`\n"

        lines = [
            "## RIDIOMA Lookup — Mensaje Identificado",
            "",
            f"**Busqueda:** `{result.query}`",
            "",
        ]

        for m in result.matches[:3]:
            lines.append(f"### {m.constant_name}")
            lines.append(f"- **Texto:** `{m.message_text}`")
            lines.append(f"- **ID:** `{m.message_id}`")
            lines.append("")

        if result.callers:
            lines.append("### Metodos que usan esta constante")
            lines.append("")
            lines.append("| Clase | Metodo | Archivo | Linea |")
            lines.append("|-------|--------|---------|-------|")
            for c in result.callers:
                fname = Path(c.file_path).name if c.file_path else "—"
                lines.append(f"| `{c.class_name}` | `{c.method_name}` | `{fname}` | {c.line_number} |")

        return "\n".join(lines)

    def _load_const_index(self) -> None:
        index_path = BASE_DIR / "projects" / self.project_name / "ridioma_index.json"
        if index_path.exists():
            try:
                self._const_index = json.loads(index_path.read_text(encoding="utf-8"))
                return
            except Exception:
                pass
        self._const_index = {}
        # Intentar construir en segundo plano
        try:
            self.rebuild_const_index()
        except Exception:
            pass

    def _load_cache(self) -> dict:
        if self._cache_path.exists():
            try:
                return json.loads(self._cache_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save_cache(self) -> None:
        self._cache_path.write_text(
            json.dumps(self._cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _load_config(self) -> dict:
        cfg = BASE_DIR / "projects" / self.project_name / "config.json"
        if cfg.exists():
            try:
                return json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}
