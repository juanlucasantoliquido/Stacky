"""
qa_119_direct.py — ADO-119 RF-006 — direct URL nav to FrmDetalleClie.
Uses the approach that worked previously: ?LOT= parameter with PACIFICO.
"""
import asyncio, os, sys, pathlib, datetime, json

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PACIFICO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PACIFICO")
EVDIR = pathlib.Path("evidence/119"); EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')

LOTES = ["1000001118137685", "1000010112929743", "1000079106269907",
         "1000139115588708", "1000147113581996"]


async def check_fields(page):
    fields = {}
    for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
        for sel in [f"#c_{fname}", f"input[id*='{fname}']", f"span[id*='{fname}']", f"*[id*='{fname}']"]:
            try:
                n = await page.locator(sel).count()
                if n > 0:
                    el = page.locator(sel).first
                    vis = await el.is_visible()
                    ro  = await el.get_attribute("readonly") or await el.get_attribute("disabled")
                    try: val = await el.input_value()
                    except: val = (await el.text_content() or "").strip()
                    fields[fname] = {"found": True, "visible": vis, "value": val.strip(), "readonly": ro is not None}
                    print(f"  {fname}: vis={vis} val='{val.strip()}' ro={ro is not None} sel={sel}")
                    break
            except Exception: pass
        if fname not in fields:
            fields[fname] = {"found": False}
            print(f"  {fname}: NOT FOUND in DOM")
    # Related labels
    rel = []
    for i in range(await page.locator("label").count()):
        try:
            t = await page.locator("label").nth(i).text_content()
            if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                rel.append(t.strip())
        except: pass
    print(f"  Labels: {rel}")
    return fields, rel


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx  = await browser.new_context()
        page = await ctx.new_page()

        # Login
        print(f"[1] Login {USER}")
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"   {page.url}")

        # Navigate: try LOT= param for each known lote
        target = None
        print("[2] Direct navigation to FrmDetalleClie")
        for lote in LOTES:
            for param in [f"LOT={lote}", f"LOCOD={lote}", f"lot={lote}"]:
                url = f"{BASE}FrmDetalleClie.aspx?{param}"
                try:
                    await page.goto(url, wait_until="load", timeout=20000)
                    await page.wait_for_load_state("load", timeout=15000)
                    if "FrmDetalleClie" in page.url:
                        if await page.locator("#c_abfApellidoNombre, #c_abfNumCliente, .aisfieldbody").count() > 0:
                            print(f"   REACHED: {page.url} (lote={lote}, param={param})")
                            target = page
                            break
                except Exception as e:
                    print(f"   {lote}/{param}: {type(e).__name__}")
            if target:
                break

        if not target:
            # Try FrmAgenda grid
            print("[2b] FrmAgenda — click first row in any grid")
            await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
            await page.wait_for_load_state("networkidle", timeout=10000)
            for sel in ["#c_GridAgendaUsu tbody tr", "#c_GridAgendaAut tbody tr"]:
                rows = page.locator(sel)
                if await rows.count() > 0:
                    await rows.first.click(no_wait_after=True)
                    try: await page.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=10000)
                    except: pass
                    await page.wait_for_load_state("load", timeout=10000)
                    if "FrmDetalleClie" in page.url:
                        target = page
                        break

        if not target:
            print("BLOCKED: Cannot reach FrmDetalleClie in dev env")
            print("  Reason: No lotes assigned to user, LOT= param redirects to login")
            print("  → QA puede ejecutarse en UAT/QA con datos reales post-batch")
            await browser.close()
            return

        # Screenshot
        await target.screenshot(path=str(EVDIR / "ca_05_08_09.png"))
        print(f"[3] Field check on {target.url}")
        fields, labels = await check_fields(target)

        # Verdicts
        results = {}
        corredor = fields.get("abfCorredorPrincipal", {})
        riesgo   = fields.get("abfRiesgoCliente",   {})

        for ca, fd, nm in [("CA-05", corredor, "abfCorredorPrincipal"),
                            ("CA-08", riesgo,   "abfRiesgoCliente")]:
            if fd.get("found") and fd.get("visible"):
                results[ca] = f"PASS — {nm} visible, valor='{fd['value']}' (vacío ok sin batch)"
            elif fd.get("found") and not fd.get("visible"):
                results[ca] = f"FAIL — {nm} en DOM pero NO visible (check InstanciaPacifico)"
            else:
                results[ca] = f"FAIL — {nm} NO en DOM (DLL no tiene ADO-119)"

        if corredor.get("found") and riesgo.get("found"):
            results["CA-09"] = ("PASS — ambos campos readonly"
                                if corredor.get("readonly") and riesgo.get("readonly")
                                else "FAIL — campos NO readonly")
        else:
            results["CA-09"] = "BLOCKED — campos no encontrados"

        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-06","CA-07","CA-11","CA-12"]:
            results[ca] = "BLOCKED — requiere datos post-batch (OGCORREDOR/CLRIESGOSIS vacíos en dev)"

        # Print summary
        print("\n" + "=" * 55)
        print("RESULTADO QA UAT — ADO-119 RF-006")
        print("=" * 55)
        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-05","CA-06","CA-07","CA-08","CA-09","CA-11","CA-12"]:
            v = results[ca]
            icon = "✅" if v.startswith("PASS") else ("❌" if v.startswith("FAIL") else "⏸")
            print(f"  {icon} {ca}: {v}")

        out = {"ticket": "ADO-119", "ts": datetime.datetime.now().isoformat(),
               "results": results, "fields": fields, "labels": labels}
        (EVDIR / "qa_119_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Evidence: evidence/119/ca_05_08_09.png")
        await browser.close()

asyncio.run(main())
