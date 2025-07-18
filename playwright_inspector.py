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
import playwright_config

async def main(url=None):
    
    print("Playwrightインスペクターを起動中...")
    
    async with async_playwright() as p:
        # 設定を準備
        options = dict(playwright_config.browser_context_options)
        

        # ブラウザタイプを選択
        browser_type = p.chrome if options.get("channel") == "chrome" else p.chromium
        
        # 永続的コンテキストを作成
        context = await browser_type.launch_persistent_context(
            playwright_config.user_data_dir,
            **options
        )
        
        # トレースを開始
        await context.tracing.start(**playwright_config.trace_options)
        
        # 新しいページを開く
        page = await context.new_page()
        
        # タイムアウト設定を適用
        page.set_default_timeout(playwright_config.timeouts["timeout"])
        page.set_default_navigation_timeout(playwright_config.timeouts["navigation_timeout"])
        
        # URLが指定されている場合はそこに移動
        if url:
            print(f"指定されたURL {url} に移動しています...")
            await page.goto(url, timeout=playwright_config.timeouts["page_load_timeout"])
        else:
            # URLが指定されていない場合は設定ファイルのURLを使用
            start_url = config.START_URLS[0] if config.START_URLS else "https://example.com"
            print(f"デフォルトURL {start_url} に移動しています...")
            await page.goto(start_url, timeout=playwright_config.timeouts["page_load_timeout"])
        
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
                
        # リソースをクリーンアップ
        await context.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Playwrightインスペクターツール")
    parser.add_argument("--url", help="検査するURL", default=None)
    
    args = parser.parse_args()
    
    asyncio.run(main(url=args.url))
