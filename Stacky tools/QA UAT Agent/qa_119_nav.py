"""
qa_119_nav.py — Minimal navigation diagnostic for ADO-119.
Step 1: Login, inspect FrmAgenda, click Avanzar, check FrmDetalleClie.
"""
import asyncio, os, sys, pathlib

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PACIFICO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PACIFICO")

EVDIR = pathlib.Path("evidence/119")
EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')


async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=200)
        page = await browser.new_page()

        # 1. Login
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.screenshot(path=str(EVDIR / "nav_01_login.png"))
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try:
            await page.wait_for_url(lambda url: "FrmLogin" not in url, timeout=25000)
        except Exception as e:
            print(f"[WARN] Login wait: {e}")
        await page.wait_for_load_state("load", timeout=20000)
        print(f"[1] Logged in at: {page.url}")
        await page.screenshot(path=str(EVDIR / "nav_02_agenda.png"))

        # 2. Inspect FrmAgenda - list all buttons and links
        print("[2] FrmAgenda elements:")
        btns = page.locator("a, button, input[type=button], input[type=submit]")
        cnt = await btns.count()
        for i in range(min(cnt, 30)):
            try:
                el = btns.nth(i)
                id_ = await el.get_attribute("id") or ""
                text = (await el.text_content() or "").strip()[:40]
                href = await el.get_attribute("href") or ""
                vis = await el.is_visible()
                print(f"  [{i}] id={id_} text='{text}' href={href[:50]} vis={vis}")
            except Exception:
                pass

        # 3. Try btnAvanzar
        avanzar = page.locator("#c_btnAvanzar")
        avanzar_count = await avanzar.count()
        print(f"\n[3] btnAvanzar count: {avanzar_count}")
        if avanzar_count > 0 and await avanzar.is_visible():
            print("  Clicking btnAvanzar...")
            await avanzar.click(no_wait_after=True)
            try:
                await page.wait_for_url(lambda url: "FrmDetalleClie" in url, timeout=20000)
            except Exception as e:
                print(f"  [WARN] Avanzar: {e}")
            await page.wait_for_load_state("load", timeout=15000)
            print(f"  URL after Avanzar: {page.url}")
            await page.screenshot(path=str(EVDIR / "nav_03_after_avanzar.png"))

            if "FrmDetalleClie" in page.url:
                print("  SUCCESS: Reached FrmDetalleClie")
                await check_fields(page)
            else:
                print(f"  Not on FrmDetalleClie. Checking page title...")
                title = await page.title()
                print(f"  Page title: {title}")
        else:
            print("  btnAvanzar not visible/found")

        # 4. Try FrmBusqueda - search empty
        print(f"\n[4] FrmBusqueda empty search...")
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.screenshot(path=str(EVDIR / "nav_04_busqueda.png"))
        # List form fields
        inputs = page.locator("input[type=text], input[type=search], select")
        icnt = await inputs.count()
        print(f"  Inputs on FrmBusqueda: {icnt}")
        for i in range(min(icnt, 10)):
            try:
                el = inputs.nth(i)
                id_ = await el.get_attribute("id") or ""
                name = await el.get_attribute("name") or ""
                print(f"    [{i}] id={id_} name={name}")
            except Exception:
                pass
        # Try search with just submit
        submit = page.locator("#c_btnOk, input[type=submit], button[type=submit]").first
        if await submit.count() > 0:
            print("  Submitting empty search...")
            await submit.click(no_wait_after=True)
            await page.wait_for_load_state("load", timeout=15000)
            rows = page.locator("tbody tr, .grid-row")
            rcnt = await rows.count()
            print(f"  Result rows: {rcnt}")
            if rcnt > 0:
                await rows.first.click(no_wait_after=True)
                try:
                    await page.wait_for_url(lambda url: "FrmDetalleClie" in url, timeout=15000)
                except Exception as e:
                    print(f"  [WARN] After click: {e}")
                await page.wait_for_load_state("load", timeout=15000)
                print(f"  URL: {page.url}")
                await page.screenshot(path=str(EVDIR / "nav_05_after_search.png"))
                if "FrmDetalleClie" in page.url:
                    await check_fields(page)

        await browser.close()


async def check_fields(page):
    """Check ADO-119 fields in FrmDetalleClie."""
    print(f"\n  [FIELD CHECK] Page: {page.url}")
    for field in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
        for sel in [f"#c_{field}", f"*[id*={field}]"]:
            try:
                cnt = await page.locator(sel).count()
                if cnt > 0:
                    el = page.locator(sel).first
                    vis = await el.is_visible()
                    val = ""
                    try:
                        val = await el.input_value()
                    except Exception:
                        val = await el.text_content() or ""
                    ro = await el.get_attribute("readonly")
                    print(f"  {field}: FOUND via {sel} | visible={vis} | value='{val.strip()}' | readonly={ro is not None}")
                    break
            except Exception:
                pass
        else:
            print(f"  {field}: NOT FOUND in DOM")

    # List all labels
    print("  Labels:")
    labels = page.locator("label")
    for i in range(min(await labels.count(), 50)):
        try:
            t = await labels.nth(i).text_content()
            if t and any(w in t.lower() for w in ["corredor", "riesgo"]):
                print(f"    LABEL: '{t.strip()}'")
        except Exception:
            pass


asyncio.run(main())
