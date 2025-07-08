import os
import asyncio
from playwright.async_api import async_playwright
import config
import playwright_config as pw_config


async def main():
    os.makedirs(pw_config.user_data_dir, exist_ok=True)

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            pw_config.user_data_dir,
            **pw_config.launch_options,
            **pw_config.context_options,
        )

        # 最初のページを取得
        page = context.pages[0] if context.pages else await context.new_page()

        await page.goto(config.LOGIN_URL)

        await page.wait_for_selector(config.USERNAME_SELECTOR)

        await page.fill(config.USERNAME_SELECTOR, config.USERNAME)
        await page.fill(config.PASSWORD_SELECTOR, config.PASSWORD)

        # パスワードセレクタからフォーカスを外す
        await page.focus(config.USERNAME_SELECTOR)

        await page.click(config.SUBMIT_SELECTOR)

        await page.wait_for_url(config.LOGIN_SUCCESS_URL_PATTERN, timeout=500000)

        # ログイン状態はuser_data_dirに自動保存される
        print(
            f"ログイン状態がユーザーデータディレクトリに保存されました: {pw_config.user_data_dir}"
        )

        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
