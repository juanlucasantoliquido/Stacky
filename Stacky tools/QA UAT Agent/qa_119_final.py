"""
qa_119_final.py — ADO-119 RF-006 — final targeted test.
Replicates the exact flow that returned 20 rows + handles popup.
"""
import asyncio, os, sys, pathlib, datetime, json

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PABLO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PABLO")
EVDIR = pathlib.Path("evidence/119")
EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')


async def check_fields(page):
    fields = {}
    for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
        for sel in [f"#c_{fname}", f"input[id*='{fname}']", f"span[id*='{fname}']", f"*[id*='{fname}']"]:
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
                    print(f"  {fname}: found=True vis={vis} val='{val.strip()}' ro={ro is not None}")
                    break
            except Exception: pass
        if fname not in fields:
            fields[fname] = {"found": False}
            print(f"  {fname}: NOT FOUND")
    return fields


async def navigate_to_detalle(ctx, page) -> "page":
    """Returns the page on FrmDetalleClie, handling popups."""
    # Strategy A: busqueda "A" first (0 rows) → then empty search (20 rows) → popup
    print("[NAV-A] FrmBusqueda search 'A' then empty")
    await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
    await page.fill("#c_abfApellido1", "A")
    await page.locator("#c_btnOk").click(no_wait_after=True)
    await page.wait_for_load_state("load", timeout=15000)
    rows_a = await page.locator("#c_GridPersonas tbody tr").count()
    print(f"  Search 'A': {rows_a} rows")

    # Empty search
    inputs = page.locator("input[type=text], input[type=search]")
    for i in range(await inputs.count()):
        try: await inputs.nth(i).fill("")
        except: pass
    await page.locator("#c_btnOk").click(no_wait_after=True)
    await page.wait_for_load_state("load", timeout=15000)
    rows = page.locator("#c_GridPersonas tbody tr")
    cnt  = await rows.count()
    print(f"  Empty search: {cnt} rows")

    if cnt > 0:
        # Try same-page nav first
        async with ctx.expect_page(timeout=8000) as popup_catcher:
            await rows.first.click()
        try:
            popup = await popup_catcher.value
            await popup.wait_for_load_state("load", timeout=20000)
            if "FrmDetalleClie" in popup.url:
                print(f"  Popup nav: {popup.url}")
                return popup
            print(f"  Popup URL (not DetalleClie): {popup.url}")
        except Exception as e:
            print(f"  No popup ({type(e).__name__}) — checking same page")
            await page.wait_for_load_state("load", timeout=10000)
            if "FrmDetalleClie" in page.url:
                print(f"  Same-page nav: {page.url}")
                return page

    # Strategy B: FrmAgenda avanzar (for users with a lote assigned)
    print("[NAV-B] FrmAgenda btnAvanzar")
    await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
    await page.wait_for_load_state("networkidle", timeout=10000)
    avanzar = page.locator("#c_btnAvanzar")
    if await avanzar.count() > 0 and await avanzar.is_visible():
        await avanzar.click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmDetalleClie" in u, timeout=15000)
        except: pass
        await page.wait_for_load_state("load", timeout=15000)
        if "FrmDetalleClie" in page.url:
            print(f"  Avanzar nav: {page.url}")
            return page

    # Strategy C: Grid rows on FrmAgenda (both grids)
    print("[NAV-C] FrmAgenda grid rows")
    for grid in ["#c_GridAgendaUsu", "#c_GridAgendaAut", "table.grid tbody"]:
        rows2 = page.locator(f"{grid} tr")
        c2 = await rows2.count()
        if c2 > 0:
            async with ctx.expect_page(timeout=8000) as pop2:
                await rows2.first.click()
            try:
                pg2 = await pop2.value
                await pg2.wait_for_load_state("load", timeout=15000)
                if "FrmDetalleClie" in pg2.url:
                    print(f"  Grid popup: {pg2.url}")
                    return pg2
            except:
                await page.wait_for_load_state("load", timeout=8000)
                if "FrmDetalleClie" in page.url:
                    return page

    return None


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx    = await browser.new_context()
        page   = await ctx.new_page()

        # Login
        print(f"[1] Login {USER} @ {BASE}")
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)
        print(f"   Landed: {page.url}")

        # Navigate
        target = await navigate_to_detalle(ctx, page)

        if target is None:
            print("\nBLOCKED: No se pudo navegar a FrmDetalleClie")
            print("  → El entorno de dev no tiene lotes asignados al usuario.")
            print("  → Los campos solo pueden verificarse en UA/QA con datos reales post-batch.")
            await browser.close()
            return

        # Screenshot + check
        print(f"\n[FIELDS] On: {target.url}")
        await target.screenshot(path=str(EVDIR / "ca_05_08_09.png"))
        fields = await check_fields(target)

        # Labels
        rel_labels = []
        for i in range(await target.locator("label").count()):
            try:
                t = await target.locator("label").nth(i).text_content()
                if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                    rel_labels.append(t.strip())
            except: pass
        print(f"  Labels: {rel_labels}")

        # Verdicts
        results = {}
        corredor = fields.get("abfCorredorPrincipal", {})
        riesgo   = fields.get("abfRiesgoCliente",   {})

        for ca, fdata, name in [
            ("CA-05", corredor, "abfCorredorPrincipal"),
            ("CA-08", riesgo,   "abfRiesgoCliente"),
        ]:
            if fdata.get("found"):
                if fdata.get("visible"):
                    v = fdata.get("value", "")
                    results[ca] = f"PASS — visible, valor='{v}' (vacío ok sin batch)"
                else:
                    results[ca] = f"FAIL — {name} en DOM pero NO visible"
            else:
                results[ca] = f"FAIL — {name} NO en DOM (DLL sin ADO-119 o InstanciaPacifico=0)"

        if corredor.get("found") and riesgo.get("found"):
            if corredor.get("readonly") and riesgo.get("readonly"):
                results["CA-09"] = "PASS — ambos campos readonly"
            else:
                results["CA-09"] = "FAIL — campos NO readonly"
        else:
            results["CA-09"] = "BLOCKED — campos no encontrados"

        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-06","CA-07","CA-11","CA-12"]:
            results[ca] = "BLOCKED — requiere datos post-batch (OGCORREDOR/CLRIESGOSIS vacíos en dev)"

        # Print
        print("\n" + "=" * 55)
        print("RESULTADO QA UAT — ADO-119 RF-006")
        print("=" * 55)
        for ca in ["CA-01","CA-02","CA-03","CA-04","CA-05","CA-06","CA-07","CA-08","CA-09","CA-11","CA-12"]:
            v = results[ca]
            icon = "✅" if v.startswith("PASS") else ("❌" if v.startswith("FAIL") else "⏸")
            print(f"  {icon} {ca}: {v}")

        out = {"ticket": "ADO-119", "ts": datetime.datetime.now().isoformat(),
               "results": results, "fields": fields, "labels": rel_labels}
        (EVDIR / "qa_119_results.json").write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Screenshot: evidence/119/ca_05_08_09.png")
        await browser.close()


asyncio.run(main())
