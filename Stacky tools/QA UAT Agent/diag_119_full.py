"""
diag_119_full.py -- ADO-119 RF-006 diagnostic
Navigates via FrmBusqueda -> FrmDetalleClie, checks new fields.
"""
import asyncio, os, sys
BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PACIFICO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PACIFICO")

async def login(page):
    await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
    await page.fill("#c_abfUsuario", USER)
    await page.fill("#c_abfContrasena", PASS)
    await page.locator("#c_btnOk").click(no_wait_after=True)
    await page.wait_for_url(lambda url: "FrmLogin" not in url, timeout=30000)
    await page.wait_for_load_state("load", timeout=20000)
    return page.url

async def get_first_client(page):
    """Search FrmBusqueda for first available client."""
    await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
    await page.fill("#c_abfApellido1", "A")
    await page.locator("#c_btnOk").click(no_wait_after=True)
    await page.wait_for_load_state("load", timeout=20000)
    rows = page.locator("#c_GridPersonas tbody tr")
    cnt = await rows.count()
    print(f"  FrmBusqueda rows: {cnt}")
    if cnt > 0:
        first = rows.first
        text = await first.text_content()
        print(f"  First client: {text.strip()[:80]}")
        await first.click(no_wait_after=True)
        try:
            await page.wait_for_url(lambda url: "FrmDetalleClie" in url, timeout=15000)
            return True
        except:
            print(f"  No FrmDetalleClie redirect. URL: {page.url}")
    return False

async def check_campos(page):
    """Check for abfCorredorPrincipal and abfRiesgoCliente."""
    print("[CHECK] Looking for new fields...")
    results = {}
    for field, sels in {
        "abfCorredorPrincipal": ["#c_abfCorredorPrincipal", "*[id*=CorredorPrincipal]", "*[id*=corredor]"],
        "abfRiesgoCliente": ["#c_abfRiesgoCliente", "*[id*=RiesgoCliente]", "*[id*=riesgo]"],
    }.items():
        found = False
        for sel in sels:
            try:
                cnt = await page.locator(sel).count()
                if cnt > 0:
                    visible = await page.locator(sel).first.is_visible()
                    val = await page.locator(sel).first.input_value().catch_() if False else ""
                    try:
                        val = await page.locator(sel).first.input_value()
                    except:
                        val = await page.locator(sel).first.text_content()
                    print(f"  {field}: FOUND via {sel} | visible={visible} | value='{val}'")
                    results[field] = {"found": True, "visible": visible, "value": val, "selector": sel}
                    found = True
                    break
            except Exception as e:
                pass
        if not found:
            print(f"  {field}: NOT FOUND (implementation not deployed?)")
            results[field] = {"found": False}
    return results

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await (await browser.new_context()).new_page()

        print("[1] Login")
        url = await login(page)
        print(f"  Logged in, at: {url}")

        print("[2] Find client via FrmBusqueda")
        ok = await get_first_client(page)
        if not ok:
            print("  Could not navigate to FrmDetalleClie via FrmBusqueda")
            print("  Trying FrmAgenda btnAvanzar...")
            await page.goto(f"{BASE}FrmAgenda.aspx", wait_until="load")
            avanzar = page.locator("#c_btnAvanzar")
            if await avanzar.count() > 0:
                await avanzar.click(no_wait_after=True)
                try:
                    await page.wait_for_url(lambda url: "FrmDetalleClie" in url, timeout=15000)
                    ok = True
                except:
                    print(f"  Avanzar failed. URL: {page.url}")

        if not ok:
            print("BLOCKED: Cannot navigate to FrmDetalleClie")
            await browser.close()
            return

        await page.wait_for_load_state("load", timeout=20000)
        print(f"[3] FrmDetalleClie URL: {page.url}")
        await page.screenshot(path="evidence/119/diag_detalleclie.png")

        print("[4] Field check")
        results = await check_campos(page)

        print("\n[5] All labels in top section:")
        labels = page.locator(".aisfieldbody label, .aisfield label, label.aisfield-label")
        for i in range(await labels.count()):
            try:
                t = await labels.nth(i).text_content()
                id_ = await labels.nth(i).get_attribute("for")
                print(f"  label for={id_}: {t.strip()}")
            except: pass

        print("\n[6] Readonly fields (input[readonly], [disabled]):")
        ro = page.locator("input[readonly], input[disabled]")
        for i in range(min(await ro.count(), 20)):
            try:
                id_ = await ro.nth(i).get_attribute("id")
                val = await ro.nth(i).input_value()
                print(f"  id={id_} value={val[:40]}")
            except: pass

        print("\n[7] Search for Corredor/Riesgo text in page:")
        for text in ["Corredor Principal", "Riesgo de Cliente", "CorredorPrincipal", "RiesgoCliente"]:
            cnt = await page.get_by_text(text, exact=False).count()
            print(f"  '{text}': {cnt} elements")

        impl_deployed = results.get("abfCorredorPrincipal", {}).get("found", False) and \
                        results.get("abfRiesgoCliente", {}).get("found", False)
        print(f"\n=== VERDICT ===")
        print(f"Implementation deployed: {impl_deployed}")
        if not impl_deployed:
            print("BLOCKED: Fields not found. Implementation may not be deployed to running app.")
            print("The trunk source files do NOT contain the new fields either.")
            print("Action required: Developer must deploy/commit the implementation first.")

        await browser.close()

asyncio.run(main())