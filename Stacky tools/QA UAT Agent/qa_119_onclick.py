"""
qa_119_onclick.py — Extract grid row onclick and navigate to FrmDetalleClie directly.
"""
import asyncio, os, sys, pathlib, re

BASE = os.environ.get("AGENDA_WEB_BASE_URL", "http://localhost:35017/AgendaWeb/")
USER = os.environ.get("AGENDA_WEB_USER", "PABLO")
PASS = os.environ.get("AGENDA_WEB_PASS", "PABLO")
EVDIR = pathlib.Path("evidence/119"); EVDIR.mkdir(parents=True, exist_ok=True)
sys.stdout.reconfigure(encoding='utf-8')

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        ctx  = await browser.new_context()
        page = await ctx.new_page()

        # Login
        await page.goto(f"{BASE}FrmLogin.aspx", wait_until="load")
        await page.fill("#c_abfUsuario", USER)
        await page.fill("#c_abfContrasena", PASS)
        await page.locator("#c_btnOk").click(no_wait_after=True)
        try: await page.wait_for_url(lambda u: "FrmLogin" not in u, timeout=25000)
        except: pass
        await page.wait_for_load_state("load", timeout=20000)

        # FrmBusqueda - fresh load, click OK (empty search)
        await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
        await page.locator("#c_btnOk").click(no_wait_after=True)
        await page.wait_for_load_state("load", timeout=20000)
        rows = page.locator("#c_GridPersonas tbody tr")
        cnt = await rows.count()
        print(f"Rows: {cnt}")

        if cnt == 0:
            print("No rows. Trying FrmBusqueda with apellido search 'A'...")
            await page.goto(f"{BASE}FrmBusqueda.aspx", wait_until="load")
            await page.fill("#c_abfApellido1", "A")
            await page.locator("#c_btnOk").click(no_wait_after=True)
            await page.wait_for_load_state("load", timeout=20000)
            rows = page.locator("#c_GridPersonas tbody tr")
            cnt = await rows.count()
            print(f"Rows with 'A': {cnt}")

        if cnt > 0:
            first_row = rows.first
            onclick = await first_row.get_attribute("onclick") or ""
            href    = await first_row.get_attribute("href") or ""
            # Also try first cell link
            cell_link = first_row.locator("a, td[onclick]").first
            cell_onclick = ""
            cell_href = ""
            if await cell_link.count() > 0:
                cell_onclick = await cell_link.get_attribute("onclick") or ""
                cell_href    = await cell_link.get_attribute("href") or ""
            row_html = await first_row.inner_html()
            print(f"Row onclick: {onclick[:200]}")
            print(f"Row href:    {href[:200]}")
            print(f"Cell onclick:{cell_onclick[:200]}")
            print(f"Cell href:   {cell_href[:200]}")
            print(f"Row HTML:    {row_html[:400]}")

            # Try to extract LOT or client code from onclick/href
            for text in [onclick, cell_onclick, cell_href, href, row_html]:
                m = re.search(r"FrmDetalleClie[^'\"]*[?&](LOT|lot|LOCOD)[=]([^'\"&]+)", text)
                if m:
                    param, val = m.group(1), m.group(2)
                    url = f"{BASE}FrmDetalleClie.aspx?{param}={val}"
                    print(f"\n→ Found URL: {url}")
                    await page.goto(url, wait_until="load")
                    await page.wait_for_load_state("load", timeout=15000)
                    print(f"  Final URL: {page.url}")
                    await page.screenshot(path=str(EVDIR / "onclick_nav.png"))
                    break

            # Alternative: just execute the onclick JS
            if "FrmDetalleClie" not in page.url:
                print("\n→ Executing row onclick JS...")
                try:
                    await page.evaluate("arguments[0].click()", await first_row.element_handle())
                    await page.wait_for_timeout(3000)
                    print(f"  After js click URL: {page.url}")
                    all_pages = ctx.pages
                    print(f"  Total pages in context: {len(all_pages)}")
                    for pg in all_pages:
                        print(f"    Page: {pg.url}")
                        if "FrmDetalleClie" in pg.url:
                            await pg.screenshot(path=str(EVDIR / "onclick_nav.png"))
                            # Check fields
                            await check_fields(pg)
                            break
                except Exception as e:
                    print(f"  JS click error: {e}")

        await browser.close()

async def check_fields(page):
    print("\n--- FIELD CHECK ---")
    for fname in ["abfCorredorPrincipal", "abfRiesgoCliente"]:
        for sel in [f"#c_{fname}", f"*[id*='{fname}']"]:
            try:
                n = await page.locator(sel).count()
                if n > 0:
                    el = page.locator(sel).first
                    vis = await el.is_visible()
                    ro  = await el.get_attribute("readonly")
                    try: val = await el.input_value()
                    except: val = (await el.text_content() or "").strip()
                    print(f"  {fname}: vis={vis} val='{val}' ro={ro is not None}")
                    break
            except: pass
        else:
            print(f"  {fname}: NOT FOUND")

asyncio.run(main())
