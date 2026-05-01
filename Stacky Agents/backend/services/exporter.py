"""
FA-23 — Multi-format export.

Convierte el output markdown en distintos formatos:
- "md"     → markdown puro (default)
- "html"   → HTML standalone con CSS embebido
- "slack"  → markdown adaptado al estilo Slack (mrkdwn)
- "email"  → draft de email con asunto + body HTML

Sin dependencias externas pesadas: HTML es markdown-to-html básico vía
remarkable-style. Para export más fiel se puede sumar `markdown` o `mistune`
en el requirements.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass


SUPPORTED_FORMATS = {"md", "html", "slack", "email"}


@dataclass
class ExportResult:
    format: str
    content: str
    filename: str
    mime: str

    def to_dict(self) -> dict:
        return {
            "format": self.format,
            "content": self.content,
            "filename": self.filename,
            "mime": self.mime,
        }


def _md_to_html_basic(md: str) -> str:
    """Conversión mínima MD → HTML (h1-h3, **bold**, *italic*, ```code```, `inline`,
    listas, párrafos). No es full-featured pero alcanza para preview/email."""
    lines = md.split("\n")
    out: list[str] = []
    in_code = False
    code_buffer: list[str] = []
    in_list = False
    for line in lines:
        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_buffer)) + "</code></pre>")
                code_buffer = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_buffer.append(line)
            continue
        m1 = re.match(r"^#\s+(.*)", line)
        m2 = re.match(r"^##\s+(.*)", line)
        m3 = re.match(r"^###\s+(.*)", line)
        if m1:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h1>{html.escape(m1.group(1))}</h1>")
            continue
        if m2:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h2>{html.escape(m2.group(1))}</h2>")
            continue
        if m3:
            if in_list:
                out.append("</ul>"); in_list = False
            out.append(f"<h3>{html.escape(m3.group(1))}</h3>")
            continue
        if line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if not line.strip():
            if in_list:
                out.append("</ul>"); in_list = False
            out.append("<p></p>")
            continue
        out.append(f"<p>{_inline(line)}</p>")
    if in_list:
        out.append("</ul>")
    if in_code and code_buffer:
        out.append("<pre><code>" + html.escape("\n".join(code_buffer)) + "</code></pre>")
    return "\n".join(out)


def _inline(text: str) -> str:
    text = html.escape(text)
    # **bold**
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # *italic*
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<em>\1</em>", text)
    # `inline code`
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _md_to_slack(md: str) -> str:
    """Slack mrkdwn: # heading se convierte a *Heading* en negrita."""
    lines = md.split("\n")
    out: list[str] = []
    for line in lines:
        m = re.match(r"^(#{1,3})\s+(.*)", line)
        if m:
            out.append(f"*{m.group(2)}*")
            continue
        # **bold** queda **bold** → mrkdwn usa *bold*
        line = re.sub(r"\*\*(.+?)\*\*", r"*\1*", line)
        out.append(line)
    return "\n".join(out)


def export(*, output: str, fmt: str, agent_type: str = "agent", exec_id: int | None = None) -> ExportResult:
    fmt = fmt.lower().strip()
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"unsupported format: {fmt} (supported: {sorted(SUPPORTED_FORMATS)})")

    base_name = f"stacky-agents-{agent_type}-{exec_id or 'export'}"

    if fmt == "md":
        return ExportResult(
            format="md", content=output, filename=f"{base_name}.md", mime="text/markdown"
        )
    if fmt == "html":
        body = _md_to_html_basic(output)
        page = (
            "<!doctype html><html><head><meta charset=\"utf-8\"><title>Stacky Agents export</title>"
            "<style>body{font-family:system-ui,sans-serif;max-width:760px;margin:32px auto;"
            "line-height:1.55;color:#222}h1,h2,h3{margin-top:1.2em}code{background:#f3f3f3;"
            "padding:2px 4px;border-radius:3px}pre{background:#0f0f0f;color:#e6e9f0;padding:12px;"
            "border-radius:6px;overflow:auto}</style></head><body>"
            + body
            + "</body></html>"
        )
        return ExportResult(
            format="html", content=page, filename=f"{base_name}.html", mime="text/html"
        )
    if fmt == "slack":
        return ExportResult(
            format="slack",
            content=_md_to_slack(output),
            filename=f"{base_name}.txt",
            mime="text/plain",
        )
    if fmt == "email":
        # subject derivado del primer h1 o h2
        m = re.search(r"^#{1,2}\s+(.+?)$", output, re.MULTILINE)
        subject = m.group(1).strip() if m else f"Stacky Agents — {agent_type} #{exec_id}"
        body_html = _md_to_html_basic(output)
        eml = (
            f"To: \r\nSubject: {subject}\r\nMIME-Version: 1.0\r\n"
            f"Content-Type: text/html; charset=utf-8\r\n\r\n{body_html}"
        )
        return ExportResult(
            format="email", content=eml, filename=f"{base_name}.eml", mime="message/rfc822"
        )
    raise AssertionError("unreachable")
