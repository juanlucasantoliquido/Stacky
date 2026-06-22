#!/usr/bin/env python3
"""Dashboard HTML del loop de automejora de Kaizen. stdlib pura, offline-first (sin CDN).

Sirve una página que se auto-refresca y muestra, en vivo:
  - qué está haciendo el loop AHORA (fase del ciclo, mapeada a PLAN->DO->CHECK->ACT),
  - métricas (implementadas / planificadas / rechazadas / iterando / escaladas),
  - cada plan con su ESTADO: si quedó IMPLEMENTADO o sólo está el plan sin implementar, etc.
  - el detalle de cada sesión (propuesta, evaluación, decisión, cambios, medición).

No usa red saliente ni recursos externos (CSP-safe): HTML+CSS+JS embebidos. El front consume
dos endpoints JSON locales. Botón STOP = parada cooperativa (flag que el loop respeta).

Uso:
    python scripts/dashboard.py                 # http://127.0.0.1:8765
    python scripts/dashboard.py --port 9000 --host 0.0.0.0
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _console import enable_utf8  # noqa: E402
import aotl_state as st  # noqa: E402

enable_utf8()

SESSIONS = ROOT / "sessions"
INDEX = SESSIONS / "_index.json"


# --- estado agregado (rápido: solo el índice + el estado del loop) --------------------------
def build_state() -> dict:
    sessions = st.load_json(INDEX).get("sessions", []) if INDEX.exists() else []
    loop = st.read_loop_status() or {"state": "idle"}
    counts: dict[str, int] = {}
    verdicts: dict[str, int] = {}
    for e in sessions:
        counts[e.get("impl_status", "—")] = counts.get(e.get("impl_status", "—"), 0) + 1
        if e.get("verdict"):
            verdicts[e["verdict"]] = verdicts.get(e["verdict"], 0) + 1
    view = [{
        "id": e.get("id"), "objective": e.get("objective", ""),
        "created_utc": e.get("created_utc", ""), "status": e.get("status", ""),
        "verdict": e.get("verdict"), "impl_status": e.get("impl_status"),
        "auto": e.get("auto", False), "tags": e.get("tags", []), "commit": e.get("commit"),
        "child": e.get("child"),
    } for e in reversed(sessions)]
    return {
        "loop": loop,
        "metrics": {"total": len(sessions), "by_impl": counts, "by_verdict": verdicts,
                    "stop_requested": st.stop_requested()},
        "sessions": view,
    }


def session_detail(sid: str) -> dict:
    sdir = SESSIONS / sid
    if not sdir.is_dir():
        return {"error": "no existe la sesión %s" % sid}
    out: dict = {"id": sid}
    for name in ("proposal", "evaluation", "decision", "change_set"):
        p = sdir / ("%s.json" % name)
        if p.exists():
            try:
                out[name] = st.load_json(p)
            except (json.JSONDecodeError, OSError):
                out[name] = None
    applied = sdir / "_apply" / "applied.json"
    if applied.exists():
        try:
            out["applied"] = st.load_json(applied)
        except (json.JSONDecodeError, OSError):
            pass
    return out


PAGE = r"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kaizen — Automejora AI-driven</title>
<style>
:root{--bg:#0d1117;--panel:#161b22;--panel2:#1c2230;--bd:#30363d;--fg:#e6edf3;--mut:#8b949e;
--green:#3fb950;--red:#f85149;--amber:#d29922;--purple:#a371f7;--orange:#db8c3a;--blue:#58a6ff;--slate:#6e7681;}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial}
header{padding:14px 20px;border-bottom:1px solid var(--bd);display:flex;gap:16px;align-items:center;flex-wrap:wrap;background:var(--panel)}
h1{font-size:17px;margin:0;font-weight:650}.sub{color:var(--mut);font-size:12px}
.wrap{padding:18px 20px;max-width:1180px;margin:0 auto}
.pill{padding:3px 10px;border-radius:999px;font-size:12px;font-weight:650;border:1px solid var(--bd)}
.run{background:rgba(63,185,80,.15);color:var(--green);border-color:var(--green)}
.stopped{background:rgba(110,118,129,.15);color:var(--slate)}
.paused-escalated{background:rgba(219,140,58,.18);color:var(--orange);border-color:var(--orange)}
.error{background:rgba(248,81,73,.15);color:var(--red);border-color:var(--red)}
button{background:var(--panel2);color:var(--fg);border:1px solid var(--bd);border-radius:7px;padding:6px 12px;cursor:pointer;font-weight:600}
button:hover{border-color:var(--blue)}button.stop{border-color:var(--red);color:var(--red)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin:14px 0}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:10px;padding:12px 14px}
.card .n{font-size:24px;font-weight:700}.card .l{color:var(--mut);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.pipe{display:flex;gap:6px;flex-wrap:wrap;margin:6px 0 0}
.step{padding:4px 9px;border-radius:7px;border:1px solid var(--bd);background:var(--panel2);color:var(--mut);font-size:12px}
.step.on{background:rgba(88,166,255,.2);color:var(--blue);border-color:var(--blue);font-weight:700}
.phgrp{color:var(--mut);font-size:11px;margin-right:4px;align-self:center}
table{width:100%;border-collapse:collapse;margin-top:8px}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--bd);vertical-align:top}
th{color:var(--mut);font-size:11px;text-transform:uppercase;letter-spacing:.04em}
tr.s{cursor:pointer}tr.s:hover{background:var(--panel2)}
.badge{padding:2px 9px;border-radius:999px;font-size:11px;font-weight:700;white-space:nowrap}
.implemented{background:rgba(63,185,80,.18);color:var(--green)}
.planned{background:rgba(88,166,255,.16);color:var(--blue)}
.applied{background:rgba(210,153,34,.18);color:var(--amber)}
.rejected{background:rgba(248,81,73,.16);color:var(--red)}
.iterating{background:rgba(163,113,247,.18);color:var(--purple)}
.escalated{background:rgba(219,140,58,.2);color:var(--orange)}
.reverted{background:rgba(110,118,129,.18);color:var(--slate)}
.detail{background:var(--panel2);padding:14px;border-radius:8px;margin:2px 0 8px}
.detail h4{margin:10px 0 4px;font-size:12px;color:var(--mut);text-transform:uppercase}
pre{background:#0a0d12;border:1px solid var(--bd);border-radius:6px;padding:10px;overflow:auto;max-height:280px;font-size:12px}
code{color:var(--blue)}.muted{color:var(--mut)}.right{margin-left:auto}
a{color:var(--blue)}
</style></head><body>
<header>
  <h1>🔁 Kaizen <span class="sub">Automejora AI-driven</span></h1>
  <span id="loopPill" class="pill stopped">—</span>
  <span id="loopInfo" class="sub"></span>
  <span class="right"></span>
  <button id="stopBtn" class="stop">■ STOP</button>
  <button id="refreshBtn">↻</button>
</header>
<div class="wrap">
  <div><span class="phgrp">PLAN</span><span class="phgrp">·</span><span class="phgrp">DO</span>
  <span class="phgrp">·</span><span class="phgrp">CHECK</span><span class="phgrp">·</span><span class="phgrp">ACT</span></div>
  <div id="pipe" class="pipe"></div>
  <div id="metrics" class="grid"></div>
  <h3 style="margin:18px 0 0">Planes y su estado</h3>
  <div class="sub">verde = implementado · azul = sólo plan (sin implementar) · rojo = rechazado · violeta = iterando · naranja = escalado a vos</div>
  <table><thead><tr><th>Cuándo (UTC)</th><th>Plan (objetivo)</th><th>Estado</th><th>Veredicto</th><th>Motor</th></tr></thead>
  <tbody id="rows"></tbody></table>
</div>
<script>
const PHASES=[["observe","PLAN"],["propose","PLAN"],["apply","DO"],["measure","CHECK"],
["evaluate","CHECK"],["gate","ACT"],["resolve","ACT"]];
const ST=["implemented","planned","applied","rejected","iterating","escalated","reverted"];
function esc(s){return (s==null?"":(""+s)).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}
function badge(s){s=s||"—";const c=ST.includes(s)?s:"reverted";return '<span class="badge '+c+'">'+esc(s)+'</span>';}
async function load(){
  let d; try{d=await (await fetch("/api/state")).json();}catch(e){return;}
  const lp=d.loop||{}, st=lp.state||"idle";
  const pill=document.getElementById("loopPill");
  pill.className="pill "+(["running","stopped","paused-escalated","error"].includes(st)?st:"stopped");
  pill.textContent=st.toUpperCase();
  document.getElementById("loopInfo").textContent=
    (lp.engine?("motor="+lp.engine+" · "):"")+(lp.adapter?("adapter="+lp.adapter+" · "):"")+
    "vuelta "+(lp.iteration||0)+(lp.max_iterations?("/"+lp.max_iterations):"")+
    (lp.current_session?(" · "+lp.current_session):"");
  document.getElementById("pipe").innerHTML=PHASES.map(([p,g])=>
    '<span class="step'+(lp.phase===p?" on":"")+'">'+p+'</span>').join("");
  const m=d.metrics||{by_impl:{}};
  const cells=[["total",m.total||0]].concat(ST.map(k=>[k,(m.by_impl||{})[k]||0]));
  document.getElementById("metrics").innerHTML=cells.map(([k,v])=>
    '<div class="card"><div class="n">'+v+'</div><div class="l">'+k+'</div></div>').join("");
  document.getElementById("rows").innerHTML=(d.sessions||[]).map(s=>{
    const when=esc((s.created_utc||"").replace("T"," ").replace("+00:00",""));
    const motor=esc((s.tags||[]).filter(t=>t.startsWith("engine:")).map(t=>t.slice(7))[0]||(s.auto?"auto":"—"));
    return '<tr class="s" data-id="'+esc(s.id)+'"><td class="muted">'+when+'</td><td>'+esc(s.objective)+
      (s.commit?' <code>#'+esc(s.commit)+'</code>':'')+'</td><td>'+badge(s.impl_status)+'</td><td class="muted">'+
      esc(s.verdict||"—")+'</td><td class="muted">'+motor+'</td></tr><tr class="d" data-for="'+esc(s.id)+'"></tr>';
  }).join("");
  document.querySelectorAll("tr.s").forEach(tr=>tr.onclick=()=>toggle(tr.dataset.id));
}
async function toggle(id){
  const row=document.querySelector('tr.d[data-for="'+CSS.escape(id)+'"]');
  if(row.dataset.open){row.innerHTML="";row.dataset.open="";return;}
  let d; try{d=await (await fetch("/api/session/"+encodeURIComponent(id))).json();}catch(e){return;}
  const p=d.proposal||{},ev=d.evaluation||{},dec=d.decision||{},cs=d.change_set||{};
  let h='<td colspan="5"><div class="detail">';
  if(p.title)h+='<b>'+esc(p.title)+'</b><div class="muted">'+esc(p.summary||"")+'</div>';
  if(p.success_metric)h+='<h4>Métrica de éxito</h4>'+esc(p.success_metric);
  if(p.reversibility)h+='<h4>Rollback</h4>'+esc(p.reversibility.rollback||"");
  if(ev.scores)h+='<h4>Evaluación (total '+esc(ev.total)+'/15, confianza '+esc(ev.confidence)+')</h4><pre>'+esc(JSON.stringify(ev.scores))+'</pre>';
  if(dec.verdict)h+='<h4>Decisión: veredicto='+esc(dec.verdict)+(dec.escalated_to_human?' · ESCALADO A HUMANO':'')+'</h4>'+esc(dec.rationale||"");
  if(cs.changes)h+='<h4>Cambios ('+cs.changes.length+')</h4><pre>'+esc(cs.changes.map(c=>c.action+"  "+c.path).join("\n"))+'</pre>';
  h+='</div></td>';row.innerHTML=h;row.dataset.open="1";
}
document.getElementById("stopBtn").onclick=async()=>{await fetch("/api/stop",{method:"POST"});load();};
document.getElementById("refreshBtn").onclick=load;
load();setInterval(load,2000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: dict, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/" or path == "/index.html":
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif path == "/api/state":
            try:
                self._json(build_state())
            except Exception as exc:  # noqa: BLE001
                self._json({"error": str(exc)}, 500)
        elif path.startswith("/api/session/"):
            self._json(session_detail(path[len("/api/session/"):]))
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        if path == "/api/stop":
            st.request_stop(reason="dashboard")
            self._json({"ok": True, "stop_requested": True})
        elif path == "/api/resume":
            st.clear_stop()
            self._json({"ok": True, "stop_requested": False})
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args) -> None:  # silencia el log por request
        pass


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Dashboard del loop de automejora de Kaizen.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = "http://%s:%d" % ("127.0.0.1" if args.host == "0.0.0.0" else args.host, args.port)
    print("Kaizen dashboard en %s  (Ctrl+C para salir)" % url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\ncerrando dashboard.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
