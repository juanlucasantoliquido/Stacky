"""
qa_119_fast.py — ADO-119 RF-006 — quick field check via FrmBusqueda.
Logs in as PACIFICO, searches for 'A', clicks first result, checks new fields.
"""
import asyncio, os, sys, pathlib, datetime, json

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PACIFICO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PACIFICO")

EVDIR = pathlib.Path("evidence/119")
EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')


async def main():
    from playwright.async_api import async_playwright
    results = {}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 1. Login
        print(f"[1] Login {USER}")
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try:
            await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except Exception: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"   URL: {page.url}")

        # 2. FrmBusqueda -> first result
        print("[2] FrmBusqueda search 'A'")
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.fill("#c_abfApellido1", "A")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        rows = page.locator("#c_GridPersonas tbody tr")
        cnt = await rows.count()
        print(f"   Rows found: {cnt}")

        if cnt == 0:
            print("   No rows — trying empty search")
            await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
            await page.locator("#c_btnOk").click(no_wait_after=True)
            await page.wait_for_load_state("load", timeout=20000)
            rows = page.locator("#c_GridPersonas tbody tr")
            cnt = await rows.count()
            print(f"   Rows (empty search): {cnt}")

        if cnt > 0:
            await rows.first.click(no_wait_after=True)
            try:
                await page.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=15000)
            except Exception as e:
                print(f"   [WARN] {e}")
            await page.wait_for_load_state("load", timeout=15000)
            print(f"   URL: {page.url}")
        else:
            print("   BLOCKED: no results in FrmBusqueda")
            results["nav"] = "BLOCKED"
            await browser.close()
            return results

        # 3. Check fields
        print("[3] Field check")
        await page.screenshot(path=str(EVDIR / "P09_full_page.png"), full_page=False)

        fields = {}
        for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
            found = False
            for sel in [f"#c_{fname}", f"input[id*='{fname}']", f"*[id*='{fname}']"]:
                try:
                    n = await page.locator(sel).count()
                    if n > 0:
                        el = page.locator(sel).first
                        vis = await el.is_visible()
                        ro = await el.get_attribute("readonly")
                        dis = await el.get_attribute("disabled")
                        try: val = await el.input_value()
                        except: val = (await el.text_content() or "").strip()
                        fields[fname] = {"found": True, "visible": vis, "value": val.strip(),
                                          "readonly": ro is not None or dis is not None, "selector": sel}
                        print(f"   {fname}: found={True} vis={vis} val='{val.strip()}' ro={ro is not None} sel={sel}")
                        found = True
                        break
                except Exception: pass
            if not found:
                fields[fname] = {"found": False}
                print(f"   {fname}: NOT FOUND in DOM")

        # 4. Scan labels for corredor/riesgo
        labels = page.locator("label")
        rel = []
        for i in range(await labels.count()):
            try:
                t = await labels.nth(i).text_content()
                if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                    rel.append(t.strip())
            except: pass
        print(f"   Related labels: {rel}")

        # 5. CA verdicts
        corredor = fields.get("abfCorredorPrincipal", {})
        riesgo   = fields.get("abfRiesgoCliente", {})

        # CA-05: campo visible y vacío (sin datos batch) → PASS
        if corredor.get("found") and corredor.get("visible") and corredor.get("value") == "":
            results["CA-05"] = "PASS — campo visible y vacío (sin OGCORREDOR en dev, CA-05 ok)"
        elif corredor.get("found") and not corredor.get("visible"):
            results["CA-05"] = "FAIL — campo encontrado pero NO visible"
        elif corredor.get("found") and corredor.get("value"):
            results["CA-05"] = f"PASS — campo visible con valor '{corredor['value']}'"
        else:
            results["CA-05"] = "FAIL — abfCorredorPrincipal NO encontrado en DOM"

        # CA-08: similar para riesgo
        if riesgo.get("found") and riesgo.get("visible") and riesgo.get("value") == "":
            results["CA-08"] = "PASS — campo visible y vacío (sin CLRIESGOSIS en dev, CA-08 ok)"
        elif riesgo.get("found") and not riesgo.get("visible"):
            results["CA-08"] = "FAIL — campo encontrado pero NO visible"
        elif riesgo.get("found") and riesgo.get("value"):
            results["CA-08"] = f"PASS — campo visible con valor '{riesgo['value']}'"
        else:
            results["CA-08"] = "FAIL — abfRiesgoCliente NO encontrado en DOM"

        # CA-09: readonly
        if corredor.get("found") and riesgo.get("found"):
            if corredor.get("readonly") and riesgo.get("readonly"):
                results["CA-09"] = "PASS — ambos campos tienen atributo readonly"
            else:
                issues = []
                if not corredor.get("readonly"): issues.append("abfCorredorPrincipal NO readonly")
                if not riesgo.get("readonly"):   issues.append("abfRiesgoCliente NO readonly")
                results["CA-09"] = "FAIL — " + "; ".join(issues)
        else:
            results["CA-09"] = "BLOCKED — campos no encontrados en DOM"

        # BLOCKED CAs (requieren batch data)
        blocked = ["CA-01","CA-02","CA-03","CA-04","CA-06","CA-07","CA-11","CA-12"]
        for ca in blocked:
            results[ca] = "BLOCKED — requiere datos post-batch (OGCORREDOR/CLRIESGOSIS vacíos en dev)"

        # Print summary
        print("\n" + "=" * 60)
        print("RESULTADO QA UAT — ADO-119 RF-006")
        print("=" * 60)
        icons = {"PASS": "✅", "FAIL": "❌", "BLOCK": "⏸"}
        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-05","CA-06","CA-07","CA-08","CA-09","CA-11","CA-12"]:
            r = results.get(ca, "N/A")
            icon = "✅" if r.startswith("PASS") else ("❌" if r.startswith("FAIL") else "⏸")
            print(f"  {icon} {ca}: {r}")

        # Save JSON
        out = {"ticket": "ADO-119", "timestamp": datetime.datetime.now().isoformat(),
               "ca_results": results, "fields": fields, "labels": rel}
        (EVDIR / "qa_119_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"\nGuardado: evidence/119/qa_119_results.json")
        await browser.close()
    return results


asyncio.run(main())
