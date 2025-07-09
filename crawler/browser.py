"""
Playwrightの初期化と管理を行うモジュール
"""

import os
from playwright.async_api import Page, BrowserContext


async def setup_browser(p, pw_config, config):
    """
    ブラウザとコンテキストを初期化する

    Args:
        p: Playwrightのインスタンス
        pw_config: Playwrightの設定
        config: アプリケーションの設定

    Returns:
        (context, page): ブラウザコンテキストとページのタプル
    """
    # ユーザーデータディレクトリを作成
    os.makedirs(pw_config.user_data_dir, exist_ok=True)

    # ブラウザコンテキストの設定
    context = await (
        p.chromium.launch_persistent_context(
            pw_config.user_data_dir,
            **pw_config.launch_options,
            **pw_config.context_options,
        )
        if config.USE_USER_DATA
        else (await p.chromium.launch(**pw_config.launch_options)).new_context(
            **pw_config.context_options
        )
    )
    page = context.pages[0] if context.pages else await context.new_page()
    return context, page


async def perform_login(page: Page, config) -> None:
    """
    ログイン処理を実行する

    Args:
        page: Playwrightのページオブジェクト
        config: アプリケーションの設定
    """
    if not (config.USE_USER_DATA and config.USE_USER_DATA_AND_LOGIN):
        return

    if hasattr(config, "LOGIN_URL"):
        await page.goto(config.LOGIN_URL)
        await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR, timeout=600000)
    if hasattr(config, "LOGIN_URL2"):
        await page.goto(config.LOGIN_URL2)
        await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)
