#!/usr/bin/env python3
"""
Playwrightのインスペクターツール
これを使用すると、ブラウザ上での操作を確認し、セレクターを特定できます。
"""

import os
import asyncio
import argparse
from playwright.async_api import async_playwright
import config

async def main(url=None, use_login=False):
    # ディレクトリの作成
    os.makedirs("videos", exist_ok=True)
    os.makedirs("logs", exist_ok=True)
    
    print("Playwrightインスペクターを起動中...")
    
    async with async_playwright() as p:
        # Chromeを使用
        browser = await p.chromium.launch(
            headless=False,
            devtools=True,  # DevToolsを自動的に開く
        )
        
        # コンテキストのオプション
        context_options = {
            "viewport": {"width": 1280, "height": 720},
        }
        
        # ログインセッションを使用する場合
        if use_login and os.path.exists("storage_state.json"):
            context_options["storage_state"] = "storage_state.json"
            print("ログイン状態を使用します")
        
        # コンテキストを作成
        context = await browser.new_context(**context_options)
        
        # トレースを開始（デバッグ用）
        await context.tracing.start(
            screenshots=True,
            snapshots=True,
            sources=True
        )
        
        # 新しいページを開く
        page = await context.new_page()
        
        # URLが指定されている場合はそこに移動
        if url:
            print(f"指定されたURL {url} に移動しています...")
            await page.goto(url, timeout=30000)
        else:
            # URLが指定されていない場合は設定ファイルのURLを使用
            start_url = config.LOGIN_URL if use_login else (config.START_URLS[0] if config.START_URLS else "https://example.com")
            print(f"デフォルトURL {start_url} に移動しています...")
            await page.goto(start_url, timeout=30000)
        
        print("\n=== Playwrightインスペクターのヒント ===")
        print("1. Dev Toolsの「Elements」タブでHTML要素を検査できます")
        print("2. 要素を右クリックして「Copy」→「Copy selector」でセレクターをコピー")
        print("3. 「Copy」→「Copy XPath」でXPathをコピー")
        print("4. テストしたいセレクターはDevToolsのConsoleで次のように試せます:")
        print("   document.querySelector('your-selector')")
        print("5. 全ての要素を取得するには:")
        print("   document.querySelectorAll('your-selector')")
        print("6. 終了するには、ブラウザを閉じるかCtrl+Cを押してください")
        
        try:
            # 指定した時間だけ待機（6時間）
            await asyncio.sleep(6 * 60 * 60)
        except KeyboardInterrupt:
            print("\n操作を終了します...")
        
        # トレースを終了して保存
        await context.tracing.stop(path="logs/trace.zip")
        print("トレースを logs/trace.zip に保存しました")
        print("トレースを表示するには: playwright show-trace logs/trace.zip")
        
        # リソースをクリーンアップ
        await context.close()
        await browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Playwrightインスペクターツール")
    parser.add_argument("--url", help="検査するURL", default=None)
    parser.add_argument("--login", help="ログイン状態を使用する", action="store_true")
    
    args = parser.parse_args()
    
    asyncio.run(main(url=args.url, use_login=args.login))
