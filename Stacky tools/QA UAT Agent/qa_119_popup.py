"""
qa_119_popup.py — ADO-119: handle popup when clicking busqueda row.
"""
import asyncio, os, sys, pathlib, datetime, json

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PABLO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PABLO")
EVDIR = pathlib.Path("evidence/119")
EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')

async def check_fields(page, label):
    fields = {}
    for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
        for sel in [f"#c_{fname}", f"input[id*='{fname}']", f"*[id*='{fname}']"]:
            try:
                n = await page.locator(sel).count()
                if n > 0:
                    el = page.locator(sel).first
                    vis = await el.is_visible()
                    ro  = await el.get_attribute("readonly")
                    dis = await el.get_attribute("disabled")
                    try: val = await el.input_value()
                    except: val = (await el.text_content() or "").strip()
                    fields[fname] = {"found": True, "visible": vis, "value": val.strip(),
                                     "readonly": ro is not None or dis is not None, "sel": sel}
                    print(f"  [{label}] {fname}: vis={vis} val='{val.strip()}' ro={ro is not None}")
                    break
            except Exception: pass
        if fname not in fields:
            fields[fname] = {"found": False}
            print(f"  [{label}] {fname}: NOT FOUND")
    return fields


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx    = await browser.new_context()
        page   = await ctx.new_page()

        # 1. Login
        print(f"[1] Login {USER}")
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except Exception: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"   {page.url}")

        # 2. FrmBusqueda empty search
        print("[2] FrmBusqueda empty search")
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        rows = page.locator("#c_GridPersonas tbody tr")
        cnt  = await rows.count()
        print(f"   Rows: {cnt}")

        target_page = None

        if cnt > 0:
            # Try: detect popup/new tab
            print("[3] Clicking first row (watching for new page / same-page nav)")
            async with ctx.expect_page(timeout=10000) as popup_info:
                await rows.first.click()
            try:
                target_page = await popup_info.value
                await target_page.wait_for_load_state("load", timeout=20000)
                print(f"   Popup: {target_page.url}")
            except Exception as e:
                print(f"   No popup ({e}) — checking same page")
                await page.wait_for_load_state("load", timeout=10000)
                if "FrmDetalleClie" in page.url:
                    target_page = page
                    print(f"   Same page nav: {page.url}")

        if target_page is None:
            print("   Nav BLOCKED — trying PACIFICO user avanzar approach")
            # Try PACIFICO agenda
            await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
            await page.wait_for_load_state("networkidle", timeout=15000)
            avanzar = page.locator("#c_btnAvanzar")
            if await avanzar.count() > 0 and await avanzar.is_visible():
                await avanzar.click(no_wait_after=True)
                try: await page.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=15000)
                except Exception: pass
                await page.wait_for_load_state("load", timeout=15000)
                if "FrmDetalleClie" in page.url:
                    target_page = page
                    print(f"   Avanzar nav: {page.url}")

        if target_page is None:
            print("BLOCKED: Cannot reach FrmDetalleClie")
            await browser.close()
            return

        # 4. Screenshot + field check
        await target_page.screenshot(path=str(EVDIR / "ca05_08_09_detalleclie.png"))
        print(f"[4] On: {target_page.url}")
        fields = await check_fields(target_page, "FrmDetalleClie")

        # Scan labels
        labels = target_page.locator("label")
        rel = []
        for i in range(await labels.count()):
            try:
                t = await labels.nth(i).text_content()
                if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                    rel.append(t.strip())
            except: pass
        print(f"   Labels match: {rel}")

        # 5. Verdicts
        r = {}
        corredor = fields.get("abfCorredorPrincipal", {})
        riesgo   = fields.get("abfRiesgoCliente", {})

        def verdict_field(fdata, ca_id, field_name):
            if fdata.get("found"):
                if fdata.get("visible"):
                    return f"PASS — {field_name} visible, valor='{fdata['value']}' (vacío=ok sin batch)"
                else:
                    return f"FAIL — {field_name} en DOM pero NO visible (InstanciaPacifico check)"
            return f"FAIL — {field_name} NO encontrado en DOM (DLL no actualizado o no en Pacifico)"

        r["CA-05"] = verdict_field(corredor, "CA-05", "abfCorredorPrincipal")
        r["CA-08"] = verdict_field(riesgo,   "CA-08", "abfRiesgoCliente")

        if corredor.get("found") and riesgo.get("found"):
            if corredor.get("readonly") and riesgo.get("readonly"):
                r["CA-09"] = "PASS — ambos campos tienen atributo readonly"
            else:
                issues = []
                if not corredor.get("readonly"): issues.append("abfCorredorPrincipal no readonly")
                if not riesgo.get("readonly"):   issues.append("abfRiesgoCliente no readonly")
                r["CA-09"] = "FAIL — " + "; ".join(issues)
        else:
            r["CA-09"] = "BLOCKED — campos no encontrados"

        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-06","CA-07","CA-11","CA-12"]:
            r[ca] = "BLOCKED — requiere datos post-batch"

        # Print
        print("\n" + "=" * 55)
        print("RESULTADO QA UAT — ADO-119 RF-006")
        print("=" * 55)
        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-05","CA-06","CA-07","CA-08","CA-09","CA-11","CA-12"]:
            v = r[ca]
            icon = "✅" if v.startswith("PASS") else ("❌" if v.startswith("FAIL") else "⏸")
            print(f"  {icon} {ca}: {v}")

        # Save
        out = {"ticket": "ADO-119", "ts": datetime.datetime.now().isoformat(),
               "results": r, "fields": fields, "labels": rel}
        (EVDIR / "qa_119_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Evidencia: evidence/119/ca05_08_09_detalleclie.png")
        await browser.close()


asyncio.run(main())
