import asyncio
from playwright.async_api import async_playwright
import config

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto(config.LOGIN_URL)

        await page.wait_for_selector(config.USERNAME_SELECTOR)

        await page.fill(config.USERNAME_SELECTOR, config.USERNAME)
        await page.fill(config.PASSWORD_SELECTOR, config.PASSWORD)
        
        # パスワードセレクタからフォーカスを外す
        await page.focus(config.USERNAME_SELECTOR)

        await page.click(config.SUBMIT_SELECTOR)

        await page.wait_for_url(config.LOGIN_SUCCESS_URL_PATTERN)

        await context.storage_state(path="storage_state.json")
        print("ログイン状態を保存: storage_state.json")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
