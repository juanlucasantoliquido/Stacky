"""
mantis_updater.py — E-02: Auto-actualización de Mantis Post-Completado.

Cuando un ticket pasa QA con APROBADO, usa Playwright para:
  1. Navegar al ticket en Mantis
  2. Agregar una nota con el resumen de la solución y el commit message
  3. Cambiar el estado a "Resuelta" (si está configurado)

Sin credenciales en código: reutiliza la sesión SSO de session_manager
(auth.json con cookies Playwright).

Uso:
    from mantis_updater import update_ticket_on_mantis
    success = update_ticket_on_mantis(ticket_id, ticket_folder, mantis_url, auth_path)
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("mantis.updater")

# Ruta al OracleQueryRunner (relativa a este archivo → trunk/tools/OracleQueryRunner)
_ORACLE_RUNNER_DIR = Path(__file__).resolve().parent.parent.parent / "tools" / "OracleQueryRunner"


def _run_oracle_query(sql: str, timeout: int = 45) -> list[dict]:
    """
    Ejecuta una query SELECT contra Oracle via OracleQueryRunner.
    Lee el resultado desde el archivo JSON que genera el runner.
    Retorna lista de dicts (una por fila). Vacía si falla o no está disponible.
    """
    import json as _json
    import glob as _glob

    runner = _ORACLE_RUNNER_DIR
    if not (runner / "OracleQueryRunner.csproj").exists():
        return []

    # Buscar el directorio de salida del runner (bin/Debug/netX.0/)
    output_dirs = list(runner.glob("bin/Debug/net*/"))
    if not output_dirs:
        output_dirs = list(runner.glob("bin/Release/net*/"))
    json_path = (output_dirs[0] / "oracle-output.json") if output_dirs else (runner / "oracle-output.json")

    try:
        result = subprocess.run(
            ["dotnet", "run", "--", sql],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(runner), encoding="utf-8", errors="replace",
        )
        # Leer el JSON desde el archivo de salida (más confiable que stdout)
        if json_path.exists():
            raw = json_path.read_text(encoding="utf-8", errors="replace").strip()
            if raw.startswith('['):
                return _json.loads(raw)
        # Fallback: intentar parsear stdout
        stdout = result.stdout.strip()
        json_start = stdout.find('[')
        if json_start != -1:
            return _json.loads(stdout[json_start:])
        return []
    except Exception:
        return []


def _mantis_base_url(mantis_url: str) -> str:
    """Extrae la base de la URL de Mantis (sin el script final)."""
    import re
    # 'https://host/mantis/view_all_bug_page.php' → 'https://host/mantis'
    return re.sub(r'/[^/]+\.php$', '', mantis_url.rstrip('/'))


def _extract_ticket_titulo(ticket_folder: str, ticket_id: str) -> str:
    """Extrae el título del ticket desde INC-{id}.md o INCIDENTE.md."""
    import re as _re

    inc_path = os.path.join(ticket_folder, f"INC-{ticket_id}.md")
    if os.path.exists(inc_path):
        try:
            text = Path(inc_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        m = _re.search(r'^titulo\s*:\s*["\']?(.+?)["\']?\s*$', text, _re.MULTILINE)
        if m:
            v = m.group(1).strip().strip('"\'')
            if len(v) > 10:
                return v[:200].rstrip()
        body = _re.sub(r'^---.*?---\s*', '', text, flags=_re.DOTALL)
        m = _re.search(r'^#\s+(.+)', body, _re.MULTILINE)
        if m:
            v = m.group(1).strip()
            if len(v) > 10:
                return v[:200].rstrip()

    incidente_path = os.path.join(ticket_folder, "INCIDENTE.md")
    if os.path.exists(incidente_path):
        try:
            text = Path(incidente_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            text = ""
        m = _re.search(
            r'#+\s*descripci[oó]n.*?\n(.*?)(?=\n#+|\Z)',
            text, _re.IGNORECASE | _re.DOTALL,
        )
        if m:
            for line in m.group(1).splitlines():
                s = line.strip()
                if s and not s.startswith('_A completar') and len(s) > 15:
                    return s[:200].rstrip()

    return f"Ticket #{ticket_id}"


def _is_convenios_ticket(ticket_folder: str) -> bool:
    """Heurística rápida: ¿el ticket toca lógica de convenios/RCONVP?"""
    import re as _re
    keywords = ("rconvp", "convenio", "coconv", "cierre de convenio",
                 "actualizacionconv", "rconvpoblg", "rdeuda")
    for fname in ("INCIDENTE.md", "TAREAS_DESARROLLO.md", "DEV_COMPLETADO.md"):
        path = os.path.join(ticket_folder, fname)
        if not os.path.exists(path):
            continue
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")[:3000].lower()
            if any(kw in text for kw in keywords):
                return True
        except Exception:
            pass
    return False


def _fetch_test_lotes(ticket_folder: str) -> list[str]:
    """
    Consulta la BD DEV para obtener IDs reales de convenios/clientes para las pruebas manuales.
    Retorna lista de strings listos para incluir en la nota Mantis.
    """
    output_lines: list[str] = []

    def _fmt_row(row: dict) -> str:
        """Formatea un dict de fila como tabla compacta: COL=val, COL=val"""
        return "  | " + "  |  ".join(f"{k}: {v}" for k, v in row.items())

    # ── Lote A: convenios activos con TODAS las obligaciones deuda=0 (candidatos prontos a cerrar)
    # Query liviana: usa subconsulta acotada con ROWNUM en el WHERE interno
    q_candidatos = (
        "SELECT r.coconv AS CONVENIO, r.colote AS CLIENTE, r.coestado AS ESTADO "
        "FROM rconvp r "
        "WHERE r.coestado IN (1,4,5) AND NVL(r.coentcob,'-')<>'BANCO' "
        "AND EXISTS (SELECT 1 FROM rconvpoblg ro WHERE ro.coconv=r.coconv) "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM rdeuda rde2 JOIN rconvpoblg ro2 ON ro2.cooblg=rde2.deoblig "
        "  WHERE ro2.coconv=r.coconv AND nvl(rde2.demoratot,0)+nvl(rde2.deintpun,0)+nvl(rde2.degscob,0)>0"
        ") AND ROWNUM<=5"
    )
    rows_a = _run_oracle_query(q_candidatos, timeout=35)

    # ── Lote B: convenios activos con deuda > 0 (para CE-1 — el fix NO debe tocarlos)
    # Query liviana: solo RCONVP filtrado por estado, sin JOIN a RDEUDA
    q_con_deuda = (
        "SELECT r.coconv AS CONVENIO, r.colote AS CLIENTE, r.coestado AS ESTADO, "
        "r.codeudatot AS DEUDA_TOTAL "
        "FROM rconvp r "
        "WHERE r.coestado IN (1,4,5) AND NVL(r.coentcob,'-')<>'BANCO' "
        "AND r.codeudatot > 0 AND ROWNUM<=5"
    )
    rows_b = _run_oracle_query(q_con_deuda, timeout=25)

    # ── Lote C: convenios BANCO (CE-2 — siempre excluidos)
    q_banco = (
        "SELECT r.coconv AS CONVENIO, r.colote AS CLIENTE, r.coentcob AS ENTIDAD "
        "FROM rconvp r "
        "WHERE r.coestado IN (1,4,5) AND r.coentcob='BANCO' AND ROWNUM<=3"
    )
    rows_c = _run_oracle_query(q_banco, timeout=25)

    # ── Formatear salida ──────────────────────────────────────────────────
    if rows_a:
        output_lines.append("  [HP-1] Convenios listos para cerrar — usar como lote principal:")
        for row in rows_a:
            output_lines.append(_fmt_row(row))
    else:
        output_lines.append("  [HP-1] Sin convenios candidatos en BD DEV — preparar lote con estos pasos:")
        output_lines.append("    a) Elegir CONVENIO del Lote CE-1 abajo")
        output_lines.append("    b) UPDATE RDEUDA SET DEMORATOT=0,DEINTPUN=0,DEGSCOB=0")
        output_lines.append("       WHERE DEOBLIG IN (SELECT COOBLG FROM RCONVPOBLG WHERE COCONV=<N>); COMMIT;")
        output_lines.append("    c) Correr ACTUALIZACIONCONV — esperado COESTADO=3 y SALDO_CUOTAS=0")

    if rows_b:
        output_lines.append("  [CE-1] Convenios con deuda activa (NO deben cerrarse):")
        for row in rows_b:
            output_lines.append(_fmt_row(row))

    if rows_c:
        output_lines.append("  [CE-2] Convenios BANCO (siempre excluidos por el fix):")
        for row in rows_c:
            output_lines.append(_fmt_row(row))

    return output_lines


def _build_short_summary(ticket_folder: str, ticket_id: str) -> str:
    """
    Construye la nota para Mantis con:
      - Título del ticket (de INC-{id}.md)
      - Resumen de cambios del desarrollador (de DEV_COMPLETADO.md)
      - Archivos modificados
      - Resultado de build
      - Validaciones del checklist
    """
    import re as _re

    titulo = _extract_ticket_titulo(ticket_folder, ticket_id)

    # ── Leer DEV_COMPLETADO.md ─────────────────────────────────────────────
    dev_path = os.path.join(ticket_folder, "DEV_COMPLETADO.md")
    if not os.path.exists(dev_path):
        return titulo

    try:
        text = Path(dev_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return titulo

    parts = [titulo, ""]

    # ── a) Resumen de cambios ──────────────────────────────────────────────
    # Intento 1: sección "## Resumen de cambios" con bullets (- item)
    bullets = []
    cambios_m = _re.search(
        r'##\s+Resumen de cambios?[^\n]*\n((?:.*\n)*?)(?=\n##|\Z)',
        text, _re.IGNORECASE,
    )
    if cambios_m:
        for line in cambios_m.group(1).splitlines():
            s = line.strip()
            if s and (s.startswith('-') or s.startswith('*')):
                clean = _re.sub(r'^[-*]\s*', '', s).strip()
                if len(clean) > 15:
                    bullets.append(f"- {clean[:200]}")
                if len(bullets) >= 4:
                    break

    if bullets:
        parts.append("Cambios realizados:")
        parts.extend(bullets)
        parts.append("")
    else:
        # Intento 2: **CAMBIO MÍNIMO:**  (colon puede estar dentro o fuera del **)
        m = _re.search(
            r'\*\*CAMBIO M[IÍ]NIMO:?\*\*:?\s*\n((?:.+\n?)+?)(?=\n\n---|\n##|\Z)',
            text, _re.IGNORECASE,
        )
        if m:
            cambio = m.group(1).strip().split('\n')[0].strip()
            if len(cambio) > 20:
                parts.append(f"Cambio: {cambio[:300]}")
                parts.append("")
        else:
            # Intento 3: primera descripción de tarea (### T001 ... + primer párrafo)
            task_m = _re.search(
                r'###\s+T\d+[^\n]*\n(?:\*\*[^\n]*\n)?((?:.+\n?)+?)(?=\n###|\n##|\Z)',
                text, _re.IGNORECASE,
            )
            if task_m:
                desc = task_m.group(1).strip().split('\n')[0].strip()
                if len(desc) > 20:
                    parts.append(f"Cambio: {desc[:300]}")
                    parts.append("")

    # ── b) Archivos modificados ────────────────────────────────────────────
    archivos = []
    # Desde tabla markdown: | `ruta/file.cs` |
    for row_m in _re.finditer(r'\|\s*`([^`]+)`\s*\|', text):
        fname = row_m.group(1)
        # solo archivos de código
        if _re.search(r'\.(cs|aspx|xml|sql|js|ts)$', fname, _re.IGNORECASE):
            label = fname.split('/')[-1]
            if label not in archivos:
                archivos.append(label)
    # Desde lista de bullets con archivos
    if not archivos:
        for m in _re.finditer(r'[-*]\s+`?([^\s`]+\.(?:cs|aspx|xml|sql))`?', text):
            label = m.group(1).split('/')[-1]
            if label not in archivos:
                archivos.append(label)
    if archivos:
        parts.append(f"Archivos: {', '.join(archivos[:5])}" + (" ..." if len(archivos) > 5 else ""))

    # ── c) Resultado de build ──────────────────────────────────────────────
    build_m = _re.search(
        r'\*\*Resultado\*\*\s*:?\s*(Build\s+\w+[^\n]*)',
        text, _re.IGNORECASE,
    )
    if build_m:
        parts.append(f"Build: {build_m.group(1).strip()[:120]}")

    # ── d) Validaciones técnicas (checklist DEV_COMPLETADO.md) ───────────
    checklist_items = _re.findall(r'- \[([xX ])\]\s+(.+)', text)
    if checklist_items:
        parts.append("")
        parts.append("Validaciones técnicas:")
        for state, label in checklist_items:
            icon = "✔" if state.lower() == "x" else "✘"
            parts.append(f"  {icon} {label.strip()[:150]}")

    # ── e) Validaciones de negocio (casos de TESTER_COMPLETADO.md) ────────
    tester_path = os.path.join(ticket_folder, "TESTER_COMPLETADO.md")
    if os.path.exists(tester_path):
        try:
            ttext = Path(tester_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            ttext = ""

        # Veredicto global
        veredicto_m = _re.search(r'\*\*Veredicto\*\*\s*:?\s*(.+)', ttext)
        veredicto   = veredicto_m.group(1).strip() if veredicto_m else ""

        # Parser de filas de tabla markdown: split por | para evitar problemas con regex greedy
        casos = []
        _STATUS_ICONS = ('✅', '⚠', '❌', '✔', '✘')

        for line in ttext.splitlines():
            line = line.strip()
            if not (line.startswith('|') and line.endswith('|')):
                continue
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) < 3:
                continue
            # Saltar separadores (---) y encabezados
            if any(set(c) <= set('-: ') for c in cells):
                continue
            caso = cells[0]
            desc = cells[1] if len(cells) > 1 else ""
            if caso.lower() in ('caso', 'id', '#', 'tarea', 'condición', 'condicion', '') or '---' in caso:
                continue
            if desc.lower() in ('entrada', 'descripción', 'descripcion', 'condición', 'condicion') or '---' in desc:
                continue
            # Buscar celda con ícono de estado (de atrás hacia adelante)
            status_cell = next(
                (c for c in reversed(cells) if any(ic in c for ic in _STATUS_ICONS)),
                None,
            )
            if status_cell is None:
                continue
            icon = "⚠" if "⚠" in status_cell else ("✔" if ("✅" in status_cell or "✔" in status_cell) else "✘")

            # Construir etiqueta: Caso [Entrada] → Resultado obtenido
            # Columnas típicas: | Caso | Entrada | Resultado esperado | Resultado obtenido | Estado |
            entrada   = desc[:80].rstrip('.')  if desc  else ""
            resultado = cells[3].strip()[:100] if len(cells) > 3 else (cells[2].strip()[:100] if len(cells) > 2 else "")
            # Si el resultado es el mismo que "esperado" o contiene refs a código, usar descripción del caso
            if resultado.lower() in ('resultado obtenido', 'resultado_obtenido', ''):
                resultado = ""
            label_parts = []
            if caso and caso not in ('1','2','3','4','5','6','7','8','9'):
                label_parts.append(caso)
            if entrada:
                label_parts.append(entrada)
            label = ": ".join(label_parts) if label_parts else desc[:100]
            if resultado and resultado != entrada:
                label += f" → {resultado}"
            casos.append(f"  {icon} {label[:220]}")
            if len(casos) >= 8:
                break

        if casos:
            parts.append("")
            header = "Validaciones de negocio"
            if veredicto:
                header += f" — Veredicto: {veredicto}"
            parts.append(header + ":")
            parts.extend(casos)

        # ── f) Pruebas manuales ───────────────────────────────────────────
        pasos_m = _re.search(
            r'##\s+Pasos para Verificar Manualmente\s*\n((?:.*\n)*?)(?=\n##|\Z)',
            ttext, _re.IGNORECASE,
        )
        if pasos_m:
            pasos_raw = pasos_m.group(1)
            pasos = []
            in_sql = False
            sql_block: list[str] = []

            for line in pasos_raw.splitlines():
                stripped = line.strip()

                # Detectar bloques ```sql ... ```
                if stripped.startswith('```'):
                    if in_sql:
                        # Cierre del bloque — formatear la query compacta
                        sql_one = ' '.join(l.strip() for l in sql_block if l.strip() and not l.strip().startswith('--'))
                        comment_lines = [l.strip()[2:].strip() for l in sql_block if l.strip().startswith('--')]
                        if sql_one:
                            pasos.append(f"    SQL: {sql_one[:300]}")
                        for c in comment_lines:
                            if c:
                                pasos.append(f"    → {c[:150]}")
                        sql_block = []
                        in_sql = False
                    else:
                        in_sql = True
                    continue

                if in_sql:
                    sql_block.append(stripped)
                    continue

                # Pasos numerados: "1. texto" o "**Texto**"
                step_m = _re.match(r'^(\d+)\.\s+\*?\*?(.+)', stripped)
                if step_m:
                    num  = step_m.group(1)
                    text = _re.sub(r'\*+', '', step_m.group(2)).strip()
                    pasos.append(f"  {num}. {text[:200]}")
                    continue

            if pasos:
                parts.append("")
                parts.append("Cómo probar manualmente:")
                parts.extend(pasos)

        # ── g) Lotes de prueba — IDs reales de la BD (solo si aplica al ticket) ──
        lotes_lines = _fetch_test_lotes(ticket_folder) if _is_convenios_ticket(ticket_folder) else []
        if lotes_lines:
            parts.append("")
            parts.append("Lotes para prueba manual (BD DEV):")
            parts.extend(lotes_lines)

    # Limpiar líneas vacías consecutivas
    result_lines = []
    prev_blank = False
    for line in parts:
        if line == "":
            if not prev_blank:
                result_lines.append(line)
            prev_blank = True
        else:
            result_lines.append(line)
            prev_blank = False

    return "\n".join(result_lines).strip()


def _build_pm_note(ticket_folder: str, ticket_id: str) -> str:
    """
    Construye la nota post-PM para Mantis.

    Lee INCIDENTE.md y TAREAS_DESARROLLO.md (salidas del agente PM) y genera
    una nota específica al ticket que incluye:
      - Descripción del problema confirmado
      - Pasos para reproducir (extraídos de INCIDENTE.md)
      - Criterios de aceptación / cómo verificar el fix (de TAREAS_DESARROLLO.md)
      - Archivos/capas que el PM identificó como impactados
    """
    import re as _re

    titulo = _extract_ticket_titulo(ticket_folder, ticket_id)
    lines  = [f"🔍 **Análisis PM — Stacky** | Ticket #{ticket_id}: {titulo}", ""]

    # ── Leer INCIDENTE.md ────────────────────────────────────────────────────
    inc_path = os.path.join(ticket_folder, "INCIDENTE.md")
    inc_text = ""
    if os.path.exists(inc_path):
        try:
            inc_text = Path(inc_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # ── Leer TAREAS_DESARROLLO.md ────────────────────────────────────────────
    tar_path = os.path.join(ticket_folder, "TAREAS_DESARROLLO.md")
    tar_text = ""
    if os.path.exists(tar_path):
        try:
            tar_text = Path(tar_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            pass

    if not inc_text and not tar_text:
        return f"🔍 Stacky analizó ticket #{ticket_id}: {titulo}"

    # ── a) Causa raíz / descripción confirmada ────────────────────────────
    causa_m = _re.search(
        r'#+\s*(?:causa[- ]ra[íi]z|diagn[oó]stico|problema identificado)[^\n]*\n((?:(?!#+).)+)',
        inc_text, _re.IGNORECASE | _re.DOTALL,
    )
    if causa_m:
        causa = causa_m.group(1).strip().split('\n')[0].strip()
        if len(causa) > 20:
            lines += ["**Causa raíz identificada:**", causa[:400], ""]

    # ── b) Pasos para reproducir ─────────────────────────────────────────
    repro_m = _re.search(
        r'#+\s*(?:pasos para reproducir|c[oó]mo reproducir|reproducci[oó]n)[^\n]*\n'
        r'((?:(?!#+).)+)',
        inc_text, _re.IGNORECASE | _re.DOTALL,
    )
    if repro_m:
        pasos = []
        for line in repro_m.group(1).splitlines():
            s = line.strip()
            step = _re.match(r'^(\d+[\.\)]|[-*])\s+(.+)', s)
            if step and len(step.group(2)) > 5:
                pasos.append(f"  {step.group(1)} {step.group(2).strip()[:200]}")
                if len(pasos) >= 6:
                    break
        if pasos:
            lines += ["**Pasos para reproducir:**"]
            lines += pasos
            lines.append("")

    # ── c) Archivos / capas impactadas ────────────────────────────────────
    # Buscar en INCIDENTE.md o TAREAS_DESARROLLO.md menciones de archivos .cs/.aspx/.sql
    archivos = []
    file_pat = _re.compile(r'`([^`]+\.(?:cs|aspx\.cs|aspx|sql|vb|config|js))`', _re.IGNORECASE)
    for source in [inc_text, tar_text]:
        for m in file_pat.finditer(source):
            fname = m.group(1).split('/')[-1].split('\\')[-1]
            if fname not in archivos:
                archivos.append(fname)
        if len(archivos) >= 6:
            break
    if archivos:
        lines.append(f"**Archivos identificados:** {', '.join(archivos[:6])}")
        lines.append("")

    # ── d) Criterios de aceptación / cómo probar ─────────────────────────
    # Desde TAREAS_DESARROLLO.md — sección criterios o validación
    crit_m = _re.search(
        r'#+\s*(?:criterios? de aceptaci[oó]n|c[oó]mo probar|validaci[oó]n|'
        r'resultado esperado|expected result)[^\n]*\n((?:(?!#+).)+)',
        tar_text or inc_text, _re.IGNORECASE | _re.DOTALL,
    )
    if crit_m:
        criterios = []
        for line in crit_m.group(1).splitlines():
            s = line.strip()
            item = _re.match(r'^(\d+[\.\)]|[-*✓✔])\s+(.+)', s)
            if item and len(item.group(2)) > 10:
                criterios.append(f"  {item.group(1)} {item.group(2).strip()[:200]}")
                if len(criterios) >= 5:
                    break
        if criterios:
            lines += ["**Cómo verificar el fix:**"]
            lines += criterios
            lines.append("")

    # ── e) Número de tareas y estimación ──────────────────────────────────
    tareas = _re.findall(r'^###?\s+T\d+', tar_text, _re.MULTILINE)
    if tareas:
        lines.append(f"**Tareas de desarrollo:** {len(tareas)} tarea(s) identificada(s)")
        lines.append("")

    lines.append("_Análisis generado automáticamente por Stacky Pipeline._")
    return "\n".join(lines).strip()


def confirm_ticket_on_mantis(ticket_id: str, ticket_folder: str,
                             mantis_url: str, auth_path: str) -> bool:
    """
    Post-PM: agrega nota con el análisis del PM y cambia el estado a "confirmada".
    Retorna True si la operación fue exitosa.
    """
    if not mantis_url:
        logger.warning("[CONFIRMER] mantis_url no configurado — omitiendo")
        return False

    note = _build_pm_note(ticket_folder, ticket_id)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[CONFIRMER] playwright no disponible")
        return False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx     = _load_session(pw, browser, auth_path)
            if not ctx:
                browser.close()
                return False
            page = ctx.new_page()

            base       = _mantis_base_url(mantis_url)
            ticket_url = f"{base}/view.php?id={int(ticket_id)}"
            page.goto(ticket_url, wait_until="domcontentloaded", timeout=20000)

            ok = _post_note(page, note, ticket_id)
            if ok:
                _change_status(page, ticket_id, target_status="confirmada")

            browser.close()

        if ok:
            _write_update_log(ticket_folder, ticket_id, note)
            logger.info("[CONFIRMER] Ticket #%s → confirmada + nota Stacky enviada", ticket_id)
        return ok

    except Exception as e:
        logger.error("[CONFIRMER] Error en ticket #%s: %s", ticket_id, e)
        return False


def update_ticket_on_mantis(ticket_id: str, ticket_folder: str,
                             mantis_url: str, auth_path: str,
                             resolve_status: bool = False) -> bool:
    """
    Agrega una nota en Mantis con el resumen QA y opcionalmente cambia el estado.
    Retorna True si la actualización fue exitosa.
    """
    if not mantis_url:
        logger.warning("[UPDATER] mantis_url no configurado — omitiendo actualización")
        return False

    note = _build_note(ticket_folder, ticket_id)
    if not note:
        logger.warning("[UPDATER] No se pudo construir nota para ticket #%s", ticket_id)
        return False

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.warning("[UPDATER] playwright no disponible — omitiendo actualización Mantis")
        return False

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx     = _load_session(pw, browser, auth_path)
            if not ctx:
                browser.close()
                return False
            page = ctx.new_page()

            ticket_url = f"{_mantis_base_url(mantis_url)}/view.php?id={int(ticket_id)}"
            page.goto(ticket_url, wait_until="domcontentloaded", timeout=20000)

            # Verificar que estamos en el ticket correcto
            if str(ticket_id) not in page.url and str(ticket_id) not in page.content():
                logger.warning("[UPDATER] Ticket #%s no encontrado en Mantis", ticket_id)
                browser.close()
                return False

            # Agregar nota
            ok = _post_note(page, note, ticket_id)

            # Cambiar estado a "Resuelta" si se pide y la opción existe
            if ok and resolve_status:
                _change_status(page, ticket_id, target_status="resuelta")

            browser.close()

        if ok:
            _write_update_log(ticket_folder, ticket_id, note)
            logger.info("[UPDATER] Ticket #%s actualizado en Mantis", ticket_id)
        return ok

    except Exception as e:
        logger.error("[UPDATER] Error actualizando ticket #%s: %s", ticket_id, e)
        return False


# ── Internals ─────────────────────────────────────────────────────────────────

def _smart_truncate(text: str, max_len: int) -> str:
    """Corta el texto en el último punto o salto de línea antes de max_len para no truncar a mitad de frase."""
    if len(text) <= max_len:
        return text
    chunk = text[:max_len]
    # Buscar el último fin de oración o párrafo
    for sep in ('\n', '. ', '! ', '? '):
        pos = chunk.rfind(sep)
        if pos > max_len // 2:
            return chunk[:pos + len(sep)].strip()
    return chunk.strip()


def _strip_task_codes(text: str) -> str:
    """Elimina referencias a códigos de tarea internos (T001, T002, etc.) del texto."""
    # Quitar frases como "(T002 marcado como `LISTO_PARA_DBA`)"
    text = re.sub(r'\([^)]*\bT\d{3,4}\b[^)]*\)', '', text)
    # Quitar referencias inline como "de T001, T003 y T004"
    text = re.sub(r'(?:de\s+|de\s+los?)\s*T\d{3,4}(?:\s*[,y]\s*T\d{3,4})*', '', text, flags=re.IGNORECASE)
    # Quitar T001 sueltos restantes
    text = re.sub(r'\bT\d{3,4}\b', '', text)
    # Limpiar espacios dobles y comas/conjunciones sueltas que quedaron
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r',\s*,', ',', text)
    text = re.sub(r'\by\s*\.', '.', text)
    return text.strip()


def _build_note(ticket_folder: str, ticket_id: str) -> str:
    """Construye el texto de la nota a publicar en Mantis con información completa del ticket."""
    tester_path   = os.path.join(ticket_folder, "TESTER_COMPLETADO.md")
    commit_path   = os.path.join(ticket_folder, "COMMIT_MESSAGE.txt")
    arq_path      = os.path.join(ticket_folder, "ARQUITECTURA_SOLUCION.md")
    dev_path      = os.path.join(ticket_folder, "DEV_COMPLETADO.md")
    analisis_path = os.path.join(ticket_folder, "ANALISIS_TECNICO.md")

    # Aceptar nota aunque no haya QA completado — publicar con lo disponible
    tester_content = ""
    if os.path.exists(tester_path):
        tester_content = Path(tester_path).read_text(encoding="utf-8", errors="replace")
        if "APROBADO" not in tester_content.upper():
            return ""  # QA explícitamente rechazó — no publicar

    titulo = _extract_ticket_titulo(ticket_folder, ticket_id)
    lines = [
        f"✅ **Fix implementado — Ticket #{ticket_id}: {titulo}**",
        "",
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    # ── Cargar archivos fuente ─────────────────────────────────────────────
    analisis_text = ""
    if os.path.exists(analisis_path):
        analisis_text = Path(analisis_path).read_text(encoding="utf-8", errors="replace")

    arq_text = ""
    if os.path.exists(arq_path):
        arq_text = Path(arq_path).read_text(encoding="utf-8", errors="replace")

    dev_text = ""
    if os.path.exists(dev_path):
        dev_text = Path(dev_path).read_text(encoding="utf-8", errors="replace")

    # ── Causa raíz / problema ──────────────────────────────────────────────
    causa = _extract_section(analisis_text, [
        "causa raíz", "causa-raiz", "problema técnico",
        "problema identificado", "diagnóstico", "descripción del problema",
    ])
    if not causa and analisis_text:
        # Fallback: primer párrafo no vacío del análisis
        for line in analisis_text.splitlines():
            s = line.strip()
            if len(s) > 40 and not s.startswith("#") and not s.startswith("|"):
                causa = s
                break
    if causa:
        lines += ["**Problema:**", _smart_truncate(causa, 550), ""]

    # ── Solución implementada ─────────────────────────────────────────────
    # 1er intento: ARQUITECTURA_SOLUCION.md — distintos encabezados posibles
    solucion = _extract_section(arq_text, [
        "solución", "descripción de la solución",
        "cambios realizados", "cambios requeridos",
        "estrategia general", "implementación", "enfoque",
        "decisiones de diseño",
    ])
    # 2do intento: DEV_COMPLETADO.md — "Resumen de cambios realizados" es la fuente más directa
    if not solucion and dev_text:
        solucion = _extract_section(dev_text, [
            "resumen de cambios realizados", "resumen",
            "cambios realizados", "cambios",
        ])
        if solucion:
            # Convertir lista Markdown a texto corrido limpio
            solucion = re.sub(r'^[-*]\s+', '', solucion, flags=re.MULTILINE)
            solucion = re.sub(r'\n{2,}', '\n', solucion).strip()
    if solucion:
        lines += ["**Solución:**", _smart_truncate(solucion, 650), ""]

    # ── Archivos modificados (DEV_COMPLETADO.md es la fuente más confiable) ─
    archivos = []
    if dev_text:
        files_section = _extract_section(dev_text, ["archivos modificados", "archivos cambiados",
                                                      "cambios", "files changed"])
        file_pat = re.compile(r'`?([^`\s]+\.(?:cs|vb|aspx\.cs|aspx|ascx|sql|config))`?',
                              re.IGNORECASE)
        source = files_section or dev_text
        for m in file_pat.finditer(source):
            fname = m.group(1).replace("\\", "/")
            short = fname.split("/")[-1]
            if short and short not in archivos:
                archivos.append(short)
            if len(archivos) >= 7:
                break

    # Fallback: ARQUITECTURA_SOLUCION.md
    if not archivos and arq_text:
        file_pat2 = re.compile(r'`([^`]+\.(?:cs|vb|aspx\.cs|aspx|sql))`', re.IGNORECASE)
        for m in file_pat2.finditer(arq_text):
            fname = m.group(1).split("/")[-1].split("\\")[-1]
            if fname and fname not in archivos:
                archivos.append(fname)
            if len(archivos) >= 7:
                break

    if archivos:
        lines += [f"**Archivos modificados ({len(archivos)}):** {', '.join(archivos)}", ""]

    # ── Resultado QA ──────────────────────────────────────────────────────
    if tester_content:
        # Preferir "Resumen Ejecutivo" o "Veredicto Detallado" — no tienen desglose de tareas
        qa_summary = _extract_section(tester_content, [
            "resumen ejecutivo",
            "veredicto detallado",
            "veredicto",
            "resultado final",
            "conclusión",
        ])
        if not qa_summary:
            qa_summary = _extract_section(tester_content, ["aprobado"])
        if qa_summary:
            # Eliminar referencias a códigos de tarea internos (T001, T002, etc.)
            qa_summary = _strip_task_codes(qa_summary)
            lines += ["**Resultado QA:**", _smart_truncate(qa_summary, 550), ""]
    elif dev_text:
        # Sin QA — mostrar resumen del developer
        dev_summary = _extract_section(dev_text, ["resumen", "cambios", "completado", "implementado"])
        if dev_summary:
            lines += ["**Cambios del Developer:**", _smart_truncate(dev_summary, 450), ""]

    # ── Commit message ────────────────────────────────────────────────────
    if os.path.exists(commit_path):
        commit = Path(commit_path).read_text(encoding="utf-8", errors="replace")
        first_line = next((l.strip() for l in commit.splitlines() if l.strip()
                           and not l.startswith("#")), "")
        if first_line:
            lines += [f"**Commit:** `{first_line}`", ""]

    lines.append("_Nota generada automáticamente por Stacky Pipeline._")
    return "\n".join(lines)


def _load_session(pw, browser, auth_path: str):
    """Carga las cookies de sesión SSO desde auth.json."""
    try:
        with open(auth_path, encoding="utf-8") as f:
            auth_data = json.load(f)
        cookies = auth_data.get("cookies", [])
        if not cookies:
            logger.warning("[UPDATER] auth.json sin cookies — sesión no disponible")
            return None
        ctx = browser.new_context()
        ctx.add_cookies(cookies)
        return ctx
    except FileNotFoundError:
        logger.warning("[UPDATER] auth.json no encontrado en %s", auth_path)
        return None
    except Exception as e:
        logger.warning("[UPDATER] Error cargando sesión: %s", e)
        return None


def _post_note(page, note: str, ticket_id: str) -> bool:
    """Publica la nota en el ticket de Mantis."""
    try:
        # Buscar el textarea de nota (Mantis usa 'bugnote_text' o similar)
        textarea_selectors = [
            "textarea[name='bugnote_text']",
            "textarea[name='note']",
            "textarea[id='bugnote_text']",
            "#bugnote_text",
        ]
        textarea = None
        for sel in textarea_selectors:
            el = page.query_selector(sel)
            if el:
                textarea = el
                break

        if not textarea:
            logger.warning("[UPDATER] Textarea de nota no encontrado para #%s", ticket_id)
            return False

        textarea.fill(note)

        # Buscar botón submit de nota
        submit_selectors = [
            "input[type='submit'][value*='nota' i]",
            "input[type='submit'][value*='note' i]",
            "input[type='submit'][value*='agregar' i]",
            "input[type='submit'][value*='add' i]",
            "button[type='submit']",
        ]
        submitted = False
        for sel in submit_selectors:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                submitted = True
                break

        if not submitted:
            logger.warning("[UPDATER] Botón submit no encontrado para #%s", ticket_id)
            return False

        return True

    except Exception as e:
        logger.warning("[UPDATER] Error posteando nota en #%s: %s", ticket_id, e)
        return False


def _change_status(page, ticket_id: str, target_status: str) -> bool:
    """Cambia el estado del ticket en Mantis."""
    try:
        # Mantis usa un select con name='status'
        status_select = page.query_selector("select[name='status']")
        if not status_select:
            return False
        # Buscar option que contenga el texto del estado
        options = status_select.query_selector_all("option")
        for opt in options:
            if target_status.lower() in (opt.text_content() or "").lower():
                opt.click()
                # Buscar botón de actualizar estado
                update_btn = page.query_selector("input[type='submit'][value*='actualizar' i]") \
                          or page.query_selector("input[type='submit'][value*='update' i]")
                if update_btn:
                    update_btn.click()
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    logger.info("[UPDATER] Estado de #%s cambiado a '%s'",
                                ticket_id, target_status)
                    return True
        return False
    except Exception as e:
        logger.debug("[UPDATER] Error cambiando estado: %s", e)
        return False


def _extract_section(content: str, headers: list[str]) -> str:
    """Extrae contenido de una sección Markdown."""
    for header in headers:
        m = re.search(
            rf'#+\s*{re.escape(header)}.*?\n(.*?)(?=\n#+\s|\Z)',
            content, re.IGNORECASE | re.DOTALL
        )
        if m:
            text = m.group(1).strip()
            if len(text) > 20:
                return text
    return ""


def _write_update_log(ticket_folder: str, ticket_id: str, note: str) -> None:
    """Escribe un log de la actualización realizada en Mantis."""
    log_path = os.path.join(ticket_folder, "MANTIS_UPDATE.json")
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({
                "ticket_id":   ticket_id,
                "updated_at":  datetime.now().isoformat(),
                "note_length": len(note),
                "success":     True,
            }, f, indent=2, ensure_ascii=False)
    except Exception:
        pass
