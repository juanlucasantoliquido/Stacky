"""
ado_html_postprocessor — Conversor Markdown → HTML compatible con Azure DevOps.

Azure DevOps no renderiza Markdown en comentarios de work items: usa HTML.
Este módulo recibe el Markdown que produce el agente y devuelve HTML con las
tags que ADO soporta (h2/h3/h4, strong, em, hr, p, ul, ol, li, table con styles
inline, code, pre, blockquote, br, span con color rojo/verde).

Implementación intencionalmente acotada — sólo cubre los elementos que generan
los agentes (TechnicalAnalyst, DevPacifico). Si aparece un elemento Markdown
no soportado, se preserva como texto plano en lugar de romper el output.

Uso:

    from ado_html_postprocessor import md_to_ado_html
    html = md_to_ado_html(markdown_text)

    # En el flow de publicación:
    body = md_to_ado_html(comentario)
    ado_manager.add_work_item_comment(workItemId=id, comment=body)

Cubierto por tests/test_ado_html_postprocessor.py (Fase 1, P1.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ── Estilos inline obligatorios para tablas (ADO ignora CSS externo) ─────────

TABLE_STYLE = 'border-collapse:collapse;width:100%'
TH_STYLE = 'border:1px solid #ccc;padding:6px;background:#f0f0f0'
TD_STYLE = 'border:1px solid #ccc;padding:6px'


# ── Regex compilados ─────────────────────────────────────────────────────────

RE_HEADING = re.compile(r'^(#{1,6})\s+(.+?)\s*$')
RE_HR = re.compile(r'^\s*---+\s*$')
RE_FENCE = re.compile(r'^```(\w+)?\s*$')
RE_BLOCKQUOTE = re.compile(r'^>\s?(.*)$')
RE_OL = re.compile(r'^(\s*)(\d+)\.\s+(.*)$')
RE_UL = re.compile(r'^(\s*)[-*+]\s+(.*)$')
RE_TABLE_ROW = re.compile(r'^\s*\|(.+)\|\s*$')
RE_TABLE_SEP = re.compile(r'^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$')

# Inline
RE_INLINE_CODE = re.compile(r'`([^`\n]+?)`')
RE_BOLD = re.compile(r'\*\*([^*\n]+?)\*\*')
RE_ITALIC = re.compile(r'(?<!\*)\*([^*\n]+?)\*(?!\*)')
RE_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')


# ── Modelo de bloques ────────────────────────────────────────────────────────

@dataclass
class _Block:
    """Bloque parseado del Markdown. type controla cómo se renderiza."""
    type: str
    content: str = ''
    level: int = 0
    lang: str = ''
    items: list = None
    rows: list = None


# ── API pública ──────────────────────────────────────────────────────────────

def md_to_ado_html(markdown_text: str) -> str:
    """
    Convierte Markdown a HTML compatible con Azure DevOps.

    Args:
        markdown_text: contenido en Markdown.

    Returns:
        HTML string listo para enviar a `comment` del work item.

    El conversor preserva HTML que ya venga inline (útil cuando un agente legacy
    sigue devolviendo HTML — backward-compatible con prompts no migrados).
    """
    if not markdown_text or not markdown_text.strip():
        return ''

    blocks = _parse_blocks(markdown_text)
    return _render_blocks(blocks)


# ── Parser de bloques ────────────────────────────────────────────────────────

def _parse_blocks(text: str) -> list[_Block]:
    lines = text.split('\n')
    blocks: list[_Block] = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Bloque de código fenced
        m = RE_FENCE.match(line)
        if m:
            lang = m.group(1) or ''
            content_lines = []
            i += 1
            while i < len(lines) and not RE_FENCE.match(lines[i]):
                content_lines.append(lines[i])
                i += 1
            i += 1  # consumir cierre
            blocks.append(_Block(type='code', content='\n'.join(content_lines), lang=lang))
            continue

        # Heading
        m = RE_HEADING.match(line)
        if m:
            level = len(m.group(1))
            blocks.append(_Block(type='heading', level=level, content=m.group(2)))
            i += 1
            continue

        # HR
        if RE_HR.match(line):
            blocks.append(_Block(type='hr'))
            i += 1
            continue

        # Blockquote (continúa mientras la línea siga con >)
        if RE_BLOCKQUOTE.match(line):
            quote_lines = []
            while i < len(lines) and RE_BLOCKQUOTE.match(lines[i]):
                quote_lines.append(RE_BLOCKQUOTE.match(lines[i]).group(1))
                i += 1
            blocks.append(_Block(type='blockquote', content='\n'.join(quote_lines)))
            continue

        # Tabla — detectar header + separator
        if RE_TABLE_ROW.match(line) and i + 1 < len(lines) and RE_TABLE_SEP.match(lines[i+1]):
            rows = [_split_table_row(line)]
            i += 2  # saltear separator
            while i < len(lines) and RE_TABLE_ROW.match(lines[i]):
                rows.append(_split_table_row(lines[i]))
                i += 1
            blocks.append(_Block(type='table', rows=rows))
            continue

        # Listas
        if RE_UL.match(line) or RE_OL.match(line):
            list_block, consumed = _parse_list(lines, i)
            blocks.append(list_block)
            i += consumed
            continue

        # Línea en blanco — separador de párrafos
        if not line.strip():
            i += 1
            continue

        # Párrafo (acumula líneas no vacías hasta encontrar uno de los blocks de arriba)
        para_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _is_block_start(lines[i], lines, i):
            para_lines.append(lines[i])
            i += 1
        blocks.append(_Block(type='paragraph', content=' '.join(s.strip() for s in para_lines)))

    return blocks


def _is_block_start(line: str, lines: list[str], i: int) -> bool:
    """¿La línea inicia un bloque que cierra el párrafo actual?"""
    if RE_HEADING.match(line) or RE_HR.match(line) or RE_FENCE.match(line):
        return True
    if RE_BLOCKQUOTE.match(line) or RE_UL.match(line) or RE_OL.match(line):
        return True
    if RE_TABLE_ROW.match(line) and i + 1 < len(lines) and RE_TABLE_SEP.match(lines[i+1]):
        return True
    return False


def _split_table_row(line: str) -> list[str]:
    inner = line.strip().strip('|')
    return [c.strip() for c in inner.split('|')]


def _parse_list(lines: list[str], start: int) -> tuple[_Block, int]:
    """
    Parsea una lista (ul u ol). Retorna el bloque y cuántas líneas consumió.
    Lista anidada simple soportada por nivel de indentación (2 espacios).
    """
    items = []
    i = start
    is_ordered = bool(RE_OL.match(lines[i]))
    base_indent = None

    while i < len(lines):
        line = lines[i]
        m_ol = RE_OL.match(line)
        m_ul = RE_UL.match(line)
        if not (m_ol or m_ul):
            # Línea continuación del item previo (indentada, no nueva lista)
            if line.strip() and items and (line.startswith('  ') or line.startswith('\t')):
                items[-1] = items[-1] + ' ' + line.strip()
                i += 1
                continue
            break
        m = m_ol if m_ol else m_ul
        indent = len(m.group(1))
        if base_indent is None:
            base_indent = indent
        if indent < base_indent:
            break
        items.append(m.group(3) if m_ol else m.group(2))
        i += 1

    return _Block(type='ol' if is_ordered else 'ul', items=items), i - start


# ── Render ───────────────────────────────────────────────────────────────────

def _render_blocks(blocks: list[_Block]) -> str:
    parts = []
    for b in blocks:
        if b.type == 'heading':
            level = min(max(b.level, 1), 6)
            parts.append(f'<h{level}>{_render_inline(b.content)}</h{level}>')
        elif b.type == 'hr':
            parts.append('<hr>')
        elif b.type == 'code':
            content = _escape_html(b.content)
            parts.append(f'<pre><code>{content}</code></pre>')
        elif b.type == 'blockquote':
            inner = _render_inline(b.content).replace('\n', '<br>')
            parts.append(f'<blockquote>{inner}</blockquote>')
        elif b.type == 'table':
            parts.append(_render_table(b.rows))
        elif b.type == 'ul':
            items = ''.join(f'<li>{_render_inline(it)}</li>' for it in b.items)
            parts.append(f'<ul>{items}</ul>')
        elif b.type == 'ol':
            items = ''.join(f'<li>{_render_inline(it)}</li>' for it in b.items)
            parts.append(f'<ol>{items}</ol>')
        elif b.type == 'paragraph':
            parts.append(f'<p>{_render_inline(b.content)}</p>')
    return '\n'.join(parts)


def _render_table(rows: list[list[str]]) -> str:
    if not rows:
        return ''
    out = [f'<table style="{TABLE_STYLE}">']
    # Primera fila → th
    header = rows[0]
    out.append('<tr>' + ''.join(
        f'<th style="{TH_STYLE}">{_render_inline(c)}</th>' for c in header
    ) + '</tr>')
    for row in rows[1:]:
        out.append('<tr>' + ''.join(
            f'<td style="{TD_STYLE}">{_render_inline(c)}</td>' for c in row
        ) + '</tr>')
    out.append('</table>')
    return ''.join(out)


def _render_inline(text: str) -> str:
    """
    Aplica conversiones inline. El orden importa: code primero (protege contenido),
    después bold, italic, link.
    """
    # Si ya hay HTML inline, preservarlo (backward-compat con prompts legacy)
    if _looks_like_html(text):
        return text

    # 1. Code inline — protege su contenido del resto de regex
    placeholders: dict[str, str] = {}
    def _stash_code(m: re.Match) -> str:
        token = f'\x00CODE{len(placeholders)}\x00'
        placeholders[token] = f'<code>{_escape_html(m.group(1))}</code>'
        return token
    text = RE_INLINE_CODE.sub(_stash_code, text)

    # 2. Escape HTML del resto
    text = _escape_html(text)

    # 3. Bold, italic, link sobre texto escapado
    text = RE_BOLD.sub(r'<strong>\1</strong>', text)
    text = RE_ITALIC.sub(r'<em>\1</em>', text)
    text = RE_LINK.sub(r'<a href="\2">\1</a>', text)

    # 4. Restaurar code inline
    for token, replacement in placeholders.items():
        text = text.replace(token, replacement)

    return text


def _escape_html(text: str) -> str:
    return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;'))


def _looks_like_html(text: str) -> bool:
    """
    Detecta si un fragmento ya viene en HTML — heurística simple.
    Si el agente legacy devuelve HTML (TechnicalAnalyst pre-Fase 1), preservarlo.
    """
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith('<') and stripped.endswith('>'):
        # Y tiene al menos un tag conocido
        return bool(re.search(r'<(h[1-6]|p|table|tr|td|ul|ol|li|strong|em|code|pre|blockquote|hr|br|span)\b', stripped))
    return False
