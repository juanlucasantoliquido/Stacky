"""
pick_project.py — Abre Mantis en Chromium, detecta el proyecto seleccionado
y escribe el resultado en <result_file> como JSON atomico.

    python pick_project.py <auth_path> <mantis_url> <result_file> [timeout_sec]
"""

import json
import os
import sys
import time
from urllib.parse import urlparse, parse_qs
from playwright.sync_api import sync_playwright


def write_result(result_file, data):
    tmp = result_file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, result_file)


def extract_pid(url="", body=""):
    keys = ("project_id", "f_project_id", "filter[project_id][]", "f[project_id][]")
    for source in (parse_qs(urlparse(url).query), parse_qs(body)):
        for k in keys:
            v = source.get(k, [None])[0]
            if v and str(v).isdigit() and int(v) > 0:
                return int(v)
    return None


BANNER = """() => {
    if (document.getElementById('__pb')) return;
    const b = document.createElement('div');
    b.id = '__pb';
    b.style = 'position:fixed;bottom:0;left:0;right:0;z-index:99999;' +
              'background:#1a1d2e;color:#7ee8a2;padding:12px 20px;' +
              'font:bold 14px monospace;text-align:center;' +
              'border-top:2px solid #7ee8a2;';
    b.textContent = '\ud83c\udfaf  Selecciona el proyecto en el menu de Mantis  ->  la ventana se cerrara sola';
    document.body.appendChild(b);
}"""


def main():
    if len(sys.argv) < 4:
        sys.exit(1)

    auth_path   = sys.argv[1]
    mantis_url  = sys.argv[2]
    result_file = sys.argv[3]
    timeout_sec = int(sys.argv[4]) if len(sys.argv) > 4 else 120

    result   = {"project_id": None, "project_name": None}
    detected = {"pid": None}

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=False,
                args=["--window-size=1280,860", "--window-position=80,50"],
            )
            ctx  = browser.new_context(storage_state=auth_path)
            page = ctx.new_page()

            def on_request(req):
                if detected["pid"] is not None:
                    return
                try:
                    body = req.post_data or ""
                except Exception:
                    body = ""
                pid = extract_pid(req.url, body)
                if pid:
                    detected["pid"] = pid

            page.on("request", on_request)

            page.goto(mantis_url, timeout=30000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=10000)
                page.evaluate(BANNER)
            except Exception:
                pass

            deadline = time.time() + timeout_sec
            while detected["pid"] is None and time.time() < deadline:
                page.wait_for_timeout(500)

                # Fallback DOM: leer el select de proyectos
                for sel in ("select[name='project_id']", "select#project_id"):
                    try:
                        v = page.eval_on_selector(f"{sel} option:checked", "e=>e.value")
                        if v and str(v).isdigit() and int(v) > 0:
                            detected["pid"] = int(v)
                            break
                    except Exception:
                        pass

            if detected["pid"]:
                result["project_id"] = detected["pid"]
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                    page.evaluate(BANNER)
                except Exception:
                    pass
                for sel in ("select[name='project_id']", "select#project_id"):
                    try:
                        name = page.eval_on_selector(
                            f"{sel} option:checked", "e=>e.textContent.trim()")
                        if name and name not in ("0", "All Projects", "Todos los Proyectos", ""):
                            result["project_name"] = name
                            break
                    except Exception:
                        pass
                if not result["project_name"]:
                    try:
                        parts = [p.strip() for p in page.title().split(" - ")]
                        result["project_name"] = parts[1] if len(parts) >= 3 else parts[0]
                    except Exception:
                        pass
                page.wait_for_timeout(800)

            browser.close()

    except Exception as ex:
        import traceback
        result["error"] = traceback.format_exc()

    write_result(result_file, result)


if __name__ == "__main__":
    main()
