"""
deploy_packager.py — Generador de paquetes de despliegue por ticket.

Para cada ticket, analiza:
  - DEV_COMPLETADO.md   → lista de archivos fuente modificados
  - SVN_CHANGES.md      → svn status + diff de los cambios
  - INC-{id}.md         → comentarios/notas con SQL embebido
  - QUERIES_ANALISIS.sql → consultas SQL del PM

Genera un ZIP en la carpeta del ticket con:
  - Solo las DLLs que se compilaron a partir de archivos .cs/.vb modificados
  - Archivos web modificados (.aspx, .ascx, .asmx, .js, .css, .html, etc.)
  - Scripts SQL encontrados (como archivos .sql separados)
  - Un README_DEPLOY.md con instrucciones

Uso:
    from deploy_packager import DeployPackager
    pkg = DeployPackager(ticket_folder, ticket_id, workspace_root)
    result = pkg.build()
    # result = { "ok": True, "zip_path": "...", "files": [...], "sql_scripts": [...] }
"""

import os
import re
import sys
import zipfile
import logging
import tempfile
import shutil
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("stacky.deploy")

# Extensiones de archivos web que se despliegan tal cual (sin compilar)
WEB_EXTENSIONS = {
    ".aspx", ".ascx", ".asmx", ".master", ".ashx",
    ".html", ".htm", ".js", ".css", ".xml", ".config",
    ".json", ".resx",
}

# Extensiones de código fuente compilable → generan DLL
SOURCE_EXTENSIONS = {".cs", ".vb"}


class DeployPackager:
    """
    Construye un paquete ZIP con los binarios y scripts SQL necesarios
    para desplegar un ticket en otro entorno.
    """

    def __init__(self, ticket_folder: str, ticket_id: str, workspace_root: str):
        self.ticket_folder  = Path(ticket_folder)
        self.ticket_id      = ticket_id
        self.workspace_root = Path(workspace_root)

    # ── API principal ────────────────────────────────────────────────────────

    def build(self, generate_rollback: bool = True) -> dict:
        """
        Construye el paquete de despliegue. Retorna un dict con:
          ok, zip_path, zip_name, files, sql_scripts, warnings,
          rollback_zip_path (si generate_rollback=True)
        """
        warnings = []

        # 1. Obtener archivos modificados — svn diff como fuente primaria
        modified = self._get_modified_files(warnings)
        if not modified:
            return {
                "ok":         False,
                "error":      "No se encontraron archivos modificados. Verificar que SVN tenga cambios locales.",
                "warnings":   warnings,
            }

        # 2. Separar fuentes compilables de archivos web
        source_files = [f for f in modified if Path(f).suffix.lower() in SOURCE_EXTENSIONS]
        web_files    = [f for f in modified if Path(f).suffix.lower() in WEB_EXTENSIONS]
        # Archivos desconocidos → igual los incluimos si existen
        other_files  = [f for f in modified
                        if Path(f).suffix.lower() not in SOURCE_EXTENSIONS
                        and Path(f).suffix.lower() not in WEB_EXTENSIONS]

        # 3. Resolver DLLs para los archivos fuente
        dlls      = self._resolve_dlls(source_files, warnings)

        # 4. Extraer SQL de comentarios y archivos
        sql_blocks = self._extract_sql(warnings)

        # 5. Construir ZIP
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name   = f"DEPLOY_{self.ticket_id}_{timestamp}.zip"
        zip_path   = self.ticket_folder / zip_name

        included  = []
        excluded  = []

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            # Binarios compilados (DLL o EXE)
            for dll_info in dlls:
                src = Path(dll_info["path"])
                if src.exists():
                    ext = src.suffix.lower()
                    folder_arc = "exe" if ext == ".exe" else "bin"
                    arc = f"{folder_arc}/{src.name}"
                    zf.write(src, arc)
                    bin_type = "exe" if ext == ".exe" else "dll"
                    included.append({"type": bin_type, "source": str(src), "arc": arc})
                else:
                    excluded.append({"type": "dll", "source": str(src),
                                     "reason": "Binario no encontrado (¿sin compilar?)"})
                    warnings.append(f"Binario no encontrado: {src}")

            # Archivos web (aspx, ascx, js, css, etc.)
            for rel_path in web_files:
                abs_path = self._resolve_abs(rel_path)
                if abs_path and abs_path.exists():
                    arc = f"web/{rel_path.lstrip('/').replace(chr(92), '/')}"
                    zf.write(abs_path, arc)
                    included.append({"type": "web", "source": str(abs_path), "arc": arc})
                else:
                    excluded.append({"type": "web", "source": rel_path,
                                     "reason": "Archivo no encontrado en workspace"})
                    warnings.append(f"Archivo web no encontrado: {rel_path}")

            # Otros archivos modificados (que no sean .cs/.vb ni web conocido)
            for rel_path in other_files:
                abs_path = self._resolve_abs(rel_path)
                if abs_path and abs_path.exists():
                    arc = f"otros/{Path(rel_path).name}"
                    zf.write(abs_path, arc)
                    included.append({"type": "other", "source": str(abs_path), "arc": arc})

            # Scripts SQL
            sql_files_added = []
            for i, (label, sql_content) in enumerate(sql_blocks, 1):
                safe_label = re.sub(r"[^\w\-]", "_", label)[:60]
                sql_arc    = f"sql/{i:02d}_{safe_label}.sql"
                zf.writestr(sql_arc, sql_content)
                included.append({"type": "sql", "label": label, "arc": sql_arc})
                sql_files_added.append(sql_arc)

            # README de despliegue
            readme = self._build_readme(included, excluded, sql_files_added, warnings)
            zf.writestr("README_DEPLOY.md", readme)

        # Generar paquete de rollback (binarios de la revisión anterior)
        rollback_zip_path = None
        rollback_zip_name = None
        if generate_rollback and dlls:
            rollback_zip_path, rollback_zip_name = self._build_rollback_zip(
                dlls, web_files, timestamp, warnings
            )

        # Registrar en historial
        try:
            from deploy_history import DeployHistory
            DeployHistory(self.ticket_folder).record(
                zip_name=zip_name,
                files=included,
                excluded=excluded,
                warnings=warnings,
                rollback_zip=rollback_zip_name,
            )
        except Exception:
            pass

        return {
            "ok":               True,
            "zip_path":         str(zip_path),
            "zip_name":         zip_name,
            "files":            included,
            "excluded":         excluded,
            "sql_scripts":      sql_files_added,
            "warnings":         warnings,
            "rollback_zip_path": rollback_zip_path,
            "rollback_zip_name": rollback_zip_name,
        }

    def _build_rollback_zip(self, dlls: list, web_files: list,
                             timestamp: str, warnings: list):
        """
        Genera un ZIP de rollback con los binarios en su estado PREVIO al cambio
        (usando svn export -r BASE para obtener la versión commiteada anterior).
        """
        try:
            from svn_ops import export_prev_revision
        except ImportError:
            warnings.append("svn_ops no disponible — rollback no generado")
            return None, None

        rollback_name = f"ROLLBACK_{self.ticket_id}_{timestamp}.zip"
        rollback_path = self.ticket_folder / rollback_name

        # Recopilar rutas de los binarios actuales para exportar su versión previa
        binary_paths = [d["path"] for d in dlls if Path(d["path"]).exists()]

        if not binary_paths:
            warnings.append("Sin binarios para rollback")
            return None, None

        tmp_dir = Path(tempfile.mkdtemp(prefix="stacky_rollback_"))
        try:
            exported = export_prev_revision(binary_paths, str(tmp_dir))
            ok_exports = [e for e in exported if e["ok"]]

            if not ok_exports:
                warnings.append("No se pudo exportar ningún binario previo para rollback")
                shutil.rmtree(tmp_dir, ignore_errors=True)
                return None, None

            with zipfile.ZipFile(rollback_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for exp in ok_exports:
                    src = Path(exp["exported"])
                    ext = src.suffix.lower()
                    folder_arc = "exe" if ext == ".exe" else "bin"
                    zf.write(src, f"{folder_arc}/{src.name}")

                # README de rollback
                readme_lines = [
                    f"# Paquete de ROLLBACK — Ticket #{self.ticket_id}",
                    f"",
                    f"**Generado:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    f"",
                    f"Este paquete contiene los binarios en su estado **PREVIO** al deploy del ticket.",
                    f"",
                    f"## Instrucciones",
                    f"1. Detener el pool de aplicación",
                    f"2. Reemplazar los binarios actuales con los de este ZIP",
                    f"3. Reiniciar el pool de aplicación",
                    f"",
                    f"## Binarios incluidos",
                ]
                for exp in ok_exports:
                    readme_lines.append(f"- `{Path(exp['exported']).name}` (revisión BASE/PREV)")
                zf.writestr("README_ROLLBACK.md", "\n".join(readme_lines))

            return str(rollback_path), rollback_name
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # ── Extracción de archivos modificados ───────────────────────────────────

    def _get_modified_files(self, warnings: list) -> list:
        """
        Obtiene la lista de archivos modificados. Orden de prioridad:
        1. svn diff --summarize en tiempo real (fuente de verdad exacta)
        2. SVN_CHANGES.md snapshot (si hay, capturado por el agente)
        3. DEV_COMPLETADO.md (parse de texto — menos preciso)
        """
        files = set()

        # 1. svn diff --summarize — fuente de verdad
        try:
            from svn_ops import diff_summarize, status as svn_status
            svn_files = diff_summarize(str(self.workspace_root))
            if not svn_files:
                # Fallback: svn status (incluye no versionados)
                svn_files = svn_status(str(self.workspace_root))
            for entry in svn_files:
                if entry["status"] != "D":  # no incluir archivos borrados
                    files.add(entry["path"])
        except Exception as e:
            warnings.append(f"svn diff --summarize no disponible: {e}")

        # 2. SVN_CHANGES.md — snapshot capturado post-dev
        if not files:
            svn_md = self.ticket_folder / "SVN_CHANGES.md"
            if svn_md.exists():
                files.update(self._parse_svn_changes(
                    svn_md.read_text(encoding="utf-8", errors="ignore")))

        # 3. DEV_COMPLETADO.md — parse de texto como último recurso
        if not files:
            dev_md = self.ticket_folder / "DEV_COMPLETADO.md"
            if dev_md.exists():
                files.update(self._parse_dev_completado(
                    dev_md.read_text(encoding="utf-8", errors="ignore")))

        return list(files)

    def _parse_dev_completado(self, content: str) -> list:
        """
        Extrae rutas de archivos mencionadas en DEV_COMPLETADO.md.
        Busca líneas con extensiones de código o web conocidas.
        """
        found = []
        # Patrón: cualquier ruta con extensión conocida (absoluta o relativa)
        pattern = re.compile(
            r"(?:^|[\s\`\*\-\|])([A-Za-z]:[\\\/][^\s\`\*\|\]]+|[\\\/\w][^\s\`\*\|\]]*)"
            r"(?:\.(?:cs|vb|aspx|ascx|asmx|master|ashx|js|css|config|xml|html|htm|resx|json))"
            r"\b",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in pattern.finditer(content):
            raw = m.group(0).strip().strip("`*-| ")
            # Normalizar: quitar workspace_root si está absoluto
            raw = raw.replace("\\", "/")
            if raw:
                found.append(raw)
        return found

    def _parse_svn_changes(self, content: str) -> list:
        """
        Extrae rutas del svn status en SVN_CHANGES.md.
        Formato: 'M      path/to/file.cs'  o  '?      path/to/file.cs'
        """
        found = []
        # Líneas de svn status: letra de estado + espacios + ruta
        pattern = re.compile(r"^[MADC?!]+\s+(.+)$", re.MULTILINE)
        for m in pattern.finditer(content):
            raw = m.group(1).strip().replace("\\", "/")
            if raw and not raw.endswith("/"):
                found.append(raw)
        return found

    def _svn_status_live(self, warnings: list) -> list:
        """Ejecuta svn status en workspace_root y retorna archivos modificados."""
        try:
            import subprocess
            result = subprocess.run(
                ["svn", "status", str(self.workspace_root)],
                capture_output=True, text=True, timeout=30,
                encoding="utf-8", errors="replace",
            )
            found = []
            for line in result.stdout.splitlines():
                if line and line[0] in "MADC" and len(line) > 8:
                    path = line[8:].strip().replace("\\", "/")
                    if path:
                        found.append(path)
            return found
        except Exception as e:
            warnings.append(f"No se pudo ejecutar svn status: {e}")
            return []

    # ── Resolución de DLLs ───────────────────────────────────────────────────

    def _resolve_dlls(self, source_files: list, warnings: list) -> list:
        """
        Para cada archivo .cs/.vb modificado, encuentra el binario compilado.
        Puede ser una DLL (librería) o un EXE (aplicación de consola/Windows).
        Estrategia:
          1. Buscar .csproj/.vbproj en el mismo directorio o padres
          2. Extraer <AssemblyName> y <OutputType> del proyecto
          3. Buscar el binario (.dll o .exe) en bin/, bin/Release/, bin/Debug/
        """
        binaries = {}  # assembly_name → { path, project, ext }

        for rel in source_files:
            abs_path = self._resolve_abs(rel)
            if not abs_path:
                continue

            proj = self._find_project_file(abs_path)
            if not proj:
                # Sin .csproj: buscar cualquier binario en bin/ cercano
                binary = self._find_binary_near(abs_path, warnings)
                if binary and binary["name"] not in binaries:
                    binaries[binary["name"]] = binary
                continue

            assembly = self._get_assembly_name(proj)
            if not assembly:
                assembly = proj.stem

            if assembly in binaries:
                continue  # ya resuelto

            output_type = self._get_output_type(proj)  # "Exe" | "WinExe" | "Library"
            binary_path = self._find_binary_in_bin(proj.parent, assembly, output_type, warnings)
            if binary_path:
                binaries[assembly] = {
                    "name":    assembly,
                    "path":    str(binary_path),
                    "project": str(proj),
                    "ext":     binary_path.suffix,
                }
            else:
                ext_hint = ".exe" if output_type in ("Exe", "WinExe") else ".dll"
                warnings.append(
                    f"Binario '{assembly}{ext_hint}' no encontrado para {rel} "
                    f"(OutputType={output_type or '?'}) — ¿sin compilar?"
                )

        return list(binaries.values())

    def _find_project_file(self, source_path: Path) -> Path | None:
        """Busca el .csproj/.vbproj más cercano subiendo la jerarquía."""
        current = source_path.parent
        # Subir máximo 6 niveles
        for _ in range(6):
            for ext in ("*.csproj", "*.vbproj"):
                candidates = list(current.glob(ext))
                if candidates:
                    return candidates[0]
            if current == current.parent:
                break
            current = current.parent
        return None

    def _get_assembly_name(self, proj_file: Path) -> str | None:
        """Lee <AssemblyName> del archivo .csproj/.vbproj."""
        try:
            content = proj_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"<AssemblyName>([^<]+)</AssemblyName>", content)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return None

    def _get_output_type(self, proj_file: Path) -> str:
        """
        Lee <OutputType> del .csproj/.vbproj.
        Valores típicos: 'Library' (→ .dll), 'Exe' / 'WinExe' (→ .exe).
        """
        try:
            content = proj_file.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"<OutputType>([^<]+)</OutputType>", content, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        except Exception:
            pass
        return "Library"  # default conservador

    def _find_binary_in_bin(self, proj_dir: Path, assembly: str,
                             output_type: str, warnings: list) -> Path | None:
        """
        Busca el binario compilado (.dll o .exe) en las carpetas bin/ conocidas.
        Si OutputType es Exe/WinExe busca .exe primero, luego .dll como fallback
        (y viceversa para Library).
        """
        is_exe = output_type in ("Exe", "WinExe")
        primary_ext   = ".exe" if is_exe else ".dll"
        secondary_ext = ".dll" if is_exe else ".exe"

        bin_subdirs = [
            proj_dir / "bin",
            proj_dir / "bin" / "Release",
            proj_dir / "bin" / "Debug",
            proj_dir / "bin" / "Release" / "net48",
            proj_dir / "bin" / "Release" / "net472",
            proj_dir / "bin" / "Release" / "net461",
            proj_dir / "bin" / "Release" / "net6.0",
            proj_dir / "bin" / "Release" / "net8.0",
        ]

        for ext in (primary_ext, secondary_ext):
            for d in bin_subdirs:
                candidate = d / f"{assembly}{ext}"
                if candidate.exists():
                    return candidate

        # Glob recursivo: buscar cualquier binario con ese nombre
        bin_dir = proj_dir / "bin"
        if bin_dir.exists():
            for ext in (primary_ext, secondary_ext):
                hits = list(bin_dir.rglob(f"{assembly}{ext}"))
                if hits:
                    return hits[0]

        return None

    def _find_binary_near(self, source_path: Path, warnings: list) -> dict | None:
        """
        Sin .csproj: busca cualquier .dll o .exe en el bin/ más cercano.
        Heurística para proyectos legacy sin archivo de proyecto explícito.
        """
        current = source_path.parent
        for _ in range(5):
            bin_dir = current / "bin"
            if bin_dir.exists():
                binaries = (
                    [p for p in bin_dir.glob("*.exe") if not _is_third_party_dll(p.name)] +
                    [p for p in bin_dir.glob("*.dll") if not _is_third_party_dll(p.name)]
                )
                if binaries:
                    dirname = current.name
                    match = next(
                        (b for b in binaries if b.stem.lower() == dirname.lower()), None
                    )
                    chosen = match or binaries[0]
                    return {"name": chosen.stem, "path": str(chosen),
                            "project": None, "ext": chosen.suffix}
            if current == current.parent:
                break
            current = current.parent
        return None

    # ── Extracción de SQL ────────────────────────────────────────────────────

    def _extract_sql(self, warnings: list) -> list:
        """
        Extrae scripts SQL de:
        1. INC-{id}.md — busca bloques ```sql o sentencias SQL en notas/comentarios
        2. QUERIES_ANALISIS.sql — SQL generado por el PM
        3. DEV_COMPLETADO.md — SQL mencionado por el dev

        Retorna lista de (label, contenido_sql).
        """
        blocks = []

        # QUERIES_ANALISIS.sql — incluir completo si tiene contenido útil
        qa_sql = self.ticket_folder / "QUERIES_ANALISIS.sql"
        if qa_sql.exists():
            content = qa_sql.read_text(encoding="utf-8", errors="ignore").strip()
            if content and not _only_comments(content):
                blocks.append((f"QUERIES_ANALISIS_{self.ticket_id}", content))

        # INC-{id}.md — buscar bloques SQL en comentarios del ticket (Mantis notes)
        inc_md = self.ticket_folder / f"INC-{self.ticket_id}.md"
        if inc_md.exists():
            content = inc_md.read_text(encoding="utf-8", errors="ignore")
            extracted = _extract_sql_blocks(content)
            for i, sql in enumerate(extracted, 1):
                blocks.append((f"SQL_comentario_{self.ticket_id}_{i:02d}", sql))

        # DEV_COMPLETADO.md — SQL que el dev dice haber ejecutado
        dev_md = self.ticket_folder / "DEV_COMPLETADO.md"
        if dev_md.exists():
            content = dev_md.read_text(encoding="utf-8", errors="ignore")
            extracted = _extract_sql_blocks(content)
            for i, sql in enumerate(extracted, 1):
                blocks.append((f"SQL_dev_{self.ticket_id}_{i:02d}", sql))

        return blocks

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _resolve_abs(self, rel_path: str) -> Path | None:
        """Resuelve una ruta relativa o absoluta al workspace."""
        p = Path(rel_path)
        if p.is_absolute() and p.exists():
            return p
        # Intentar combinar con workspace_root
        candidate = self.workspace_root / rel_path.lstrip("/\\")
        if candidate.exists():
            return candidate
        # Buscar el nombre de archivo dentro del workspace (búsqueda heurística)
        fname = p.name
        if fname:
            hits = list(self.workspace_root.rglob(fname))
            if hits:
                return hits[0]
        return None

    def _build_readme(self, included: list, excluded: list, sql_files: list, warnings: list) -> str:
        now  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"# Paquete de Despliegue — Ticket #{self.ticket_id}",
            f"",
            f"**Generado:** {now}  ",
            f"**Ticket:** {self.ticket_id}  ",
            f"",
            f"---",
            f"",
            f"## Archivos incluidos",
            f"",
        ]
        by_type = {}
        for f in included:
            t = f.get("type", "otro")
            by_type.setdefault(t, []).append(f)

        if by_type.get("dll"):
            lines.append("### DLLs compiladas")
            for f in by_type["dll"]:
                lines.append(f"- `{f['arc']}`  ← fuente: `{f['source']}`")
            lines.append("")

        if by_type.get("web"):
            lines.append("### Archivos web")
            for f in by_type["web"]:
                lines.append(f"- `{f['arc']}`")
            lines.append("")

        if by_type.get("sql"):
            lines.append("### Scripts SQL")
            for f in by_type["sql"]:
                lines.append(f"- `{f['arc']}` — {f.get('label','')}")
            lines.append("")
            lines.append("> ⚠️ **Revisar los scripts SQL antes de ejecutar en producción.**")
            lines.append("> Ejecutar en el orden numerado.")
            lines.append("")

        if by_type.get("other"):
            lines.append("### Otros archivos")
            for f in by_type["other"]:
                lines.append(f"- `{f['arc']}`")
            lines.append("")

        if excluded:
            lines += [
                "## Archivos excluidos (no encontrados)",
                "",
            ]
            for f in excluded:
                lines.append(f"- `{f['source']}` — {f['reason']}")
            lines.append("")

        if warnings:
            lines += ["## Advertencias", ""]
            for w in warnings:
                lines.append(f"- {w}")
            lines.append("")

        lines += [
            "---",
            "",
            "## Instrucciones de despliegue",
            "",
            "1. **DLLs** → copiar a la carpeta `bin/` del sitio en el servidor destino.",
            "2. **Archivos web** → copiar manteniendo la estructura de carpetas relativa al sitio.",
            "3. **Scripts SQL** → ejecutar en Oracle con sqlplus en el orden numerado.",
            "4. Reiniciar el pool de aplicación si se reemplazaron DLLs.",
            "",
            "_Generado por Stacky — Pipeline de tickets Mantis_",
        ]
        return "\n".join(lines)


# ── Utilidades ────────────────────────────────────────────────────────────────

# DLLs de terceros frecuentes que no deben incluirse en el paquete
_THIRD_PARTY_PREFIXES = (
    "System.", "Microsoft.", "Newtonsoft.", "log4net", "NLog",
    "Oracle.", "EntityFramework", "AutoMapper", "Dapper",
    "mscorlib", "netstandard", "WindowsBase",
)


def _is_third_party_dll(dll_name: str) -> bool:
    lower = dll_name.lower()
    return any(lower.startswith(p.lower()) for p in _THIRD_PARTY_PREFIXES)


def _extract_sql_blocks(text: str) -> list:
    """
    Extrae bloques SQL de markdown.
    Busca:
      - bloques ```sql ... ```
      - bloques ``` ... ``` con contenido que parece SQL
      - Sentencias SELECT/INSERT/UPDATE/DELETE/ALTER/CREATE sueltas en el texto
    """
    blocks = []
    seen   = set()

    # Bloques ```sql ... ``` o ```SQL ... ```
    for m in re.finditer(r"```(?:sql|SQL|Sql)\s*\n(.*?)```", text, re.DOTALL):
        sql = m.group(1).strip()
        if sql and _looks_like_sql(sql) and sql not in seen:
            blocks.append(sql)
            seen.add(sql)

    # Bloques ``` ... ``` genéricos con contenido SQL
    for m in re.finditer(r"```\s*\n(.*?)```", text, re.DOTALL):
        sql = m.group(1).strip()
        if sql and _looks_like_sql(sql) and sql not in seen:
            blocks.append(sql)
            seen.add(sql)

    return blocks


def _looks_like_sql(text: str) -> bool:
    """Heurística: ¿el texto parece SQL?"""
    keywords = ["SELECT", "INSERT", "UPDATE", "DELETE", "ALTER", "CREATE", "DROP",
                "COMMIT", "BEGIN", "EXEC", "EXECUTE", "MERGE", "TRUNCATE"]
    upper = text.upper()
    return any(kw in upper for kw in keywords)


def _only_comments(text: str) -> bool:
    """¿El texto solo tiene comentarios SQL (-- ...) sin sentencias reales?"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    real  = [l for l in lines if not l.startswith("--")]
    return len(real) == 0
