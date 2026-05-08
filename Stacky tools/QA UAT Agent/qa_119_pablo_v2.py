"""
qa_119_pablo_v2.py — Login PABLO, click FrmAgenda row (same-page nav), check ADO-119 fields.
"""
import asyncio, os, sys, pathlib, json, datetime

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = "PABLO"; PASS = "PABLO"
EVDIR = pathlib.Path("evidence/119"); EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # Login
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"[1] {page.url}")

        # FrmAgenda
        await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
        await page.wait_for_load_state("networkidle", timeout=15000)
        rows = page.locator("table tbody tr")
        cnt  = await rows.count()
        print(f"[2] Rows: {cnt}")
        for i in range(min(cnt, 3)):
            text = (await rows.nth(i).text_content() or "").strip()[:80]
            print(f"  [{i}] {text}")

        if cnt == 0:
            print("No rows — BLOCKED"); await browser.close(); return

        # Click first row — same page nav
        print("[3] Clicking row[0]")
        await rows.first.click()
        try:
            await page.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=15000)
        except Exception as e:
            print(f"  wait_for_url: {e}")
        await page.wait_for_load_state("load", timeout=15000)
        print(f"  URL after click: {page.url}")

        if "FrmDetalleClie" not in page.url:
            print("  Not on FrmDetalleClie — trying Avanzar or JS click")
            # Try JS navigation from onclick
            onclick = await rows.first.get_attribute("onclick") or ""
            print(f"  onclick: {onclick[:200]}")
            if onclick:
                await page.evaluate(f"eval(arguments[0])", onclick)
                await page.wait_for_load_state("load", timeout=10000)
                print(f"  URL after eval: {page.url}")

        if "FrmDetalleClie" not in page.url:
            print("BLOCKED"); await browser.close(); return

        # Screenshot + check
        await page.screenshot(path=str(EVDIR / "ca_05_08_09.png"))
        print(f"[4] FrmDetalleClie loaded. Checking ADO-119 fields...")

        results = {}
        for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
            found = False
            for sel in [f"#c_{fname}", f"input[id*='{fname}']", f"*[id*='{fname}']"]:
                try:
                    n = await page.locator(sel).count()
                    if n > 0:
                        el = page.locator(sel).first
                        vis = await el.is_visible()
                        ro  = await el.get_attribute("readonly") or await el.get_attribute("disabled")
                        try: val = await el.input_value()
                        except: val = (await el.text_content() or "").strip()
                        results[fname] = {"found": True, "visible": vis, "value": val.strip(), "readonly": ro is not None}
                        print(f"  {fname}: vis={vis} val='{val.strip()}' ro={ro is not None}")
                        found = True; break
                except: pass
            if not found:
                results[fname] = {"found": False}
                print(f"  {fname}: NOT FOUND")

        # Labels
        rel = []
        for i in range(await page.locator("label").count()):
            try:
                t = await page.locator("label").nth(i).text_content()
                if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                    rel.append(t.strip())
            except: pass
        print(f"  Labels match: {rel}")

        # Verdicts
        ca = {}
        corredor = results.get("abfCorredorPrincipal", {})
        riesgo   = results.get("abfRiesgoCliente",   {})
        for caId, fd in [("CA-05", corredor), ("CA-08", riesgo)]:
            if fd.get("found") and fd.get("visible"):
                ca[caId] = f"PASS — visible, valor='{fd['value']}'"
            elif fd.get("found"):
                ca[caId] = "FAIL — en DOM pero NO visible"
            else:
                ca[caId] = "FAIL — NO encontrado en DOM"
        if corredor.get("found") and riesgo.get("found"):
            ca["CA-09"] = "PASS — readonly" if (corredor.get("readonly") and riesgo.get("readonly")) else "FAIL — NO readonly"
        else:
            ca["CA-09"] = "BLOCKED — campos no encontrados"
        for x in ["CA-01","CA-02","CA-03","CA-04","CA-06","CA-07","CA-11","CA-12"]:
            ca[x] = "BLOCKED — requiere datos post-batch"

        print("\n" + "="*55)
        print("RESULTADO QA UAT — ADO-119 RF-006")
        print("="*55)
        for c in ["CA-01","CA-02","CA-03","CA-04","CA-05","CA-06","CA-07","CA-08","CA-09","CA-11","CA-12"]:
            v = ca[c]; icon = "✅" if v.startswith("PASS") else ("❌" if v.startswith("FAIL") else "⏸")
            print(f"  {icon} {c}: {v}")

        (EVDIR / "qa_119_results.json").write_text(
            json.dumps({"ticket":"ADO-119","ts":datetime.datetime.now().isoformat(),"results":ca,"fields":results,"labels":rel},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Evidence: evidence/119/ca_05_08_09.png")
        await browser.close()

asyncio.run(main())
