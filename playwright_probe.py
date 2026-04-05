import asyncio
from playwright.async_api import async_playwright

async def main():
    print('before playwright', flush=True)
    async with async_playwright() as p:
        print('before launch', flush=True)
        browser = await p.chromium.launch(headless=True)
        print('after launch', flush=True)
        page = await browser.new_page()
        print('before goto', flush=True)
        await page.goto('https://example.com', wait_until='domcontentloaded', timeout=10000)
        print('after goto', flush=True)
        print(await page.title(), flush=True)
        await browser.close()
        print('done', flush=True)

asyncio.run(main())
