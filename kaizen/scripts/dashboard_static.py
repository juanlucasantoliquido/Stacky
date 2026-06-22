#!/usr/bin/env python3
"""Generador de dashboard estático HTML para Kaizen. stdlib pura, offline-first (sin CDN).

Genera kaizen/dashboard/index.html autocontenido (CSS/JS inline) que se puede abrir
con file:// sin necesidad de un servidor HTTP. Muestra:
  - Pipeline de 7 etapas (observar→proponer→aplicar→medir→evaluar→decidir→registrar)
    con la etapa actual resaltada (leída del _loop.status.json si existe).
  - Historial de sesiones (de sessions/_index.json) con veredicto, impl_status, motor.
  - Métricas forenses (total sesiones, accept/reject/iterate, tasa de aceptación).
  - Contador de sesiones AOTL de la corrida en curso.

Uso directo:
    python scripts/dashboard_static.py           # genera dashboard/index.html
    python scripts/dashboard_static.py --out /ruta/custom.html
Uso desde el CLI unificado:
    python kaizen.py dashboard                   # genera el estatico (sin --port)
    python kaizen.py dashboard --port 8765       # sigue siendo el servidor HTTP en vivo
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"
LOOP_STATUS = SESSIONS / "_loop.status.json"
OUT_DIR = ROOT / "dashboard"

PHASES = [
    ("observar", "PLAN"),
    ("proponer", "PLAN"),
    ("aplicar", "DO"),
    ("medir", "CHECK"),
    ("evaluar", "CHECK"),
    ("decidir", "ACT"),
    ("registrar", "ACT"),
]

VERDICT_LABELS = {
    "accept": "aceptado",
    "reject": "rechazado",
    "iterate": "iterando",
    None: "—",
}

IMPL_BADGE = {
    "implemented": ("verde", "#3fb950"),
    "planned":     ("azul",  "#58a6ff"),
    "applied":     ("ambar", "#d29922"),
    "rejected":    ("rojo",  "#f85149"),
    "iterating":   ("violeta", "#a371f7"),
    "escalated":   ("naranja", "#db8c3a"),
    "reverted":    ("gris",  "#6e7681"),
}


def _load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _esc(s: object) -> str:
    """Escapado HTML mínimo."""
    return str(s if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_data(out_path: "Path | None" = None) -> dict:
    index = _load_json(INDEX)
    sessions = index.get("sessions", [])
    loop = _load_json(LOOP_STATUS) if LOOP_STATUS.exists() else {}

    total = len(sessions)
    verdicts: dict[str, int] = {}
    aotl_count = 0
    for s in sessions:
        v = s.get("verdict")
        verdicts[v or "(sin correr)"] = verdicts.get(v or "(sin correr)", 0) + 1
        if s.get("auto") or s.get("mode") == "aotl":
            aotl_count += 1

    accept = verdicts.get("accept", 0)
    closed = sum(v for k, v in verdicts.items() if k != "(sin correr)")
    rate = (accept / closed * 100) if closed else 0

    target = out_path or (OUT_DIR / "index.html")
    file_url = target.resolve().as_uri()

    return {
        "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "total": total,
        "verdicts": verdicts,
        "accept_rate": rate,
        "aotl_count": aotl_count,
        "loop": loop,
        "sessions": list(reversed(sessions)),
        "file_url": file_url,
    }


def _pill(verdict: str | None) -> str:
    colors = {
        "accept": "#3fb950",
        "reject": "#f85149",
        "iterate": "#a371f7",
    }
    c = colors.get(verdict or "", "#6e7681")
    label = VERDICT_LABELS.get(verdict, verdict or "—")
    return f'<span style="background:{c}22;color:{c};border:1px solid {c};padding:2px 8px;border-radius:99px;font-size:11px;font-weight:700">{_esc(label)}</span>'


def _impl_badge(impl: str | None) -> str:
    if not impl:
        return '<span style="color:#6e7681">—</span>'
    color = IMPL_BADGE.get(impl, ("gris", "#6e7681"))[1]
    return f'<span style="background:{color}22;color:{color};border:1px solid {color}22;padding:2px 8px;border-radius:99px;font-size:11px">{_esc(impl)}</span>'


def _phase_pills(current_phase: str | None) -> str:
    parts = []
    for phase, group in PHASES:
        active = current_phase and (phase == current_phase or phase.startswith(current_phase[:4]))
        style = (
            'background:rgba(88,166,255,.2);color:#58a6ff;border:1px solid #58a6ff;font-weight:700'
            if active else
            'background:#1c2230;color:#8b949e;border:1px solid #30363d'
        )
        parts.append(
            f'<span style="padding:4px 10px;border-radius:7px;font-size:12px;{style}">'
            f'<span style="color:#6e7681;font-size:10px">{_esc(group)} </span>{_esc(phase)}</span>'
        )
    return "  ".join(parts)


def _pending_review_section(sessions: list[dict]) -> str:
    """Devuelve HTML de la seccion 'Pendiente de revision humana' o '' si no hay nada."""
    pending = [
        s for s in sessions
        if s.get("verdict") == "iterate" or s.get("escalated_to_human")
    ]
    if not pending:
        return ""

    rows = []
    for s in pending:
        sid = s.get("id", "")
        obj = _esc(s.get("objective", ""))
        when = _esc((s.get("created_utc") or "").replace("T", " ").replace("+00:00", ""))
        is_escalated = s.get("escalated_to_human") or s.get("verdict") == "iterate"
        # Naranja para escalado al humano, ambar para iterate sin escalacion explicita
        color = "#db8c3a" if is_escalated else "#d29922"
        rows.append(
            f'<tr style="background:{color}11;border-left:3px solid {color}">'
            f'<td style="color:#8b949e;font-size:12px;white-space:nowrap;padding-left:10px">{when}</td>'
            f'<td style="color:{color};font-weight:600">{obj}</td>'
            f'<td>{_pill(s.get("verdict"))}</td>'
            f'<td style="color:#8b949e;font-size:12px">{_esc(s.get("status", ""))}</td>'
            f"</tr>"
        )

    rows_html = "\n".join(rows)
    count = len(pending)
    return f"""
  <h3 style="color:#db8c3a">Pendiente de revision humana ({count})</h3>
  <div style="background:#db8c3a11;border:1px solid #db8c3a44;border-radius:8px;padding:10px 14px;margin-bottom:10px">
    <span style="color:#db8c3a;font-size:12px">
      Estas sesiones tienen verdict=iterate o fueron escaladas al operador y requieren decision manual.
    </span>
  </div>
  <table>
    <thead>
      <tr>
        <th>Cuando (UTC)</th>
        <th>Objetivo</th>
        <th>Veredicto</th>
        <th>Estado</th>
      </tr>
    </thead>
    <tbody>{rows_html}</tbody>
  </table>
"""


def _session_rows(sessions: list[dict]) -> str:
    rows = []
    for s in sessions:
        sid = s.get("id", "")
        obj = _esc(s.get("objective", ""))
        when = _esc((s.get("created_utc") or "").replace("T", " ").replace("+00:00", ""))
        engine = next((t[7:] for t in (s.get("tags") or []) if t.startswith("engine:")), "")
        if not engine and s.get("auto"):
            engine = "auto"
        commit = s.get("commit")
        commit_html = f' <code style="color:#58a6ff;font-size:11px">#{_esc(commit)}</code>' if commit else ""
        mode = _esc(s.get("mode", ""))
        rows.append(
            f"<tr>"
            f'<td style="color:#8b949e;font-size:12px;white-space:nowrap">{when}</td>'
            f'<td>{obj}{commit_html}</td>'
            f'<td>{_impl_badge(s.get("impl_status"))}</td>'
            f'<td>{_pill(s.get("verdict"))}</td>'
            f'<td style="color:#8b949e;font-size:12px">{_esc(engine) or _esc(mode)}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


def generate_html(data: dict) -> str:
    loop = data["loop"]
    loop_state = loop.get("state", "idle")
    loop_engine = loop.get("engine", "")
    loop_phase = loop.get("phase")
    loop_iter = loop.get("iteration", 0)
    loop_session = loop.get("current_session", "")

    loop_color = "#3fb950" if loop_state == "running" else "#6e7681"
    loop_label = loop_state.upper()

    verdicts = data["verdicts"]
    verdicts_html = "  ".join(
        f'<div style="background:#161b22;border:1px solid #30363d;border-radius:10px;padding:12px 16px;min-width:90px">'
        f'<div style="font-size:22px;font-weight:700">{v}</div>'
        f'<div style="color:#8b949e;font-size:11px;text-transform:uppercase;letter-spacing:.04em">{_esc(k)}</div>'
        f'</div>'
        for k, v in [
            ("total", data["total"]),
            ("aceptadas", verdicts.get("accept", 0)),
            ("rechazadas", verdicts.get("reject", 0) + verdicts.get("(sin correr)", 0)),
            ("iterando", verdicts.get("iterate", 0)),
            ("AOTL", data["aotl_count"]),
            ("tasa %", f"{data['accept_rate']:.0f}"),
        ]
    )

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kaizen — Dashboard</title>
<style>
:root{{--bg:#0d1117;--panel:#161b22;--bd:#30363d;--fg:#e6edf3;--mut:#8b949e}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial}}
header{{padding:14px 20px;border-bottom:1px solid var(--bd);display:flex;gap:12px;align-items:center;flex-wrap:wrap;background:var(--panel)}}
h1{{font-size:17px;margin:0;font-weight:650}}
.wrap{{padding:18px 20px;max-width:1180px;margin:0 auto}}
h3{{margin:20px 0 8px;font-size:14px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}}
.grid{{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}}
table{{width:100%;border-collapse:collapse;margin-top:8px}}
th,td{{text-align:left;padding:9px 8px;border-bottom:1px solid var(--bd);vertical-align:top}}
th{{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}}
tr:hover td{{background:#161b22}}
.note{{color:var(--mut);font-size:11px;margin-top:6px}}
</style>
</head>
<body>
<header>
  <h1>Kaizen <span style="color:#8b949e;font-size:13px;font-weight:400">Automejora AI-driven</span></h1>
  <span style="background:{loop_color}22;color:{loop_color};border:1px solid {loop_color};padding:3px 10px;border-radius:99px;font-size:12px;font-weight:700">{loop_label}</span>
  <span style="color:#8b949e;font-size:12px">
    {"motor=" + _esc(loop_engine) + " · " if loop_engine else ""}
    vuelta {loop_iter}{(" · " + _esc(loop_session)) if loop_session else ""}
  </span>
  <span style="margin-left:auto;display:flex;flex-direction:column;align-items:flex-end;gap:2px">
    <span style="color:#8b949e;font-size:11px">generado {_esc(data["generated_utc"])}</span>
    <a href="{_esc(data["file_url"])}" style="color:#58a6ff;font-size:10px;text-decoration:none;font-family:ui-monospace,monospace;white-space:nowrap;overflow:hidden;max-width:420px;text-overflow:ellipsis" title="{_esc(data["file_url"])}">{_esc(data["file_url"])}</a>
  </span>
</header>

<div class="wrap">
  <h3>Pipeline actual</h3>
  <div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">
    {_phase_pills(loop_phase)}
  </div>

  <h3>Metricas</h3>
  <div class="grid">{verdicts_html}</div>

  {_pending_review_section(data["sessions"])}
  <h3>Historial de sesiones ({data["total"]} total)</h3>
  <div class="note">verde = implementado · azul = planificado · rojo = rechazado · violeta = iterando · naranja = escalado</div>
  <table>
    <thead>
      <tr>
        <th>Cuando (UTC)</th>
        <th>Objetivo</th>
        <th>Impl status</th>
        <th>Veredicto</th>
        <th>Motor</th>
      </tr>
    </thead>
    <tbody>
      {_session_rows(data["sessions"])}
    </tbody>
  </table>
</div>
</body>
</html>
"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Genera kaizen/dashboard/index.html estatico.")
    parser.add_argument("--out", default=None, help="Ruta de salida (default: dashboard/index.html)")
    args = parser.parse_args(argv)

    out_path = Path(args.out) if args.out else OUT_DIR / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = build_data(out_path)
    html = generate_html(data)
    out_path.write_text(html, encoding="utf-8")

    file_url = out_path.resolve().as_uri()
    print("Dashboard estatico generado: %s" % out_path)
    print("Abrilo con: %s" % file_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
