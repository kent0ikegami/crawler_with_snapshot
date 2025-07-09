"""
Crawler with Snapshot
クローリングと同時に画面キャプチャも取るWebクローラー

コマンドライン引数:
--resume DIR: 指定ディレクトリのクロールを再開する
--retry DIR: 指定ディレクトリのエラー行を再試行する
"""

import os
import asyncio
import argparse
from datetime import datetime
from playwright.async_api import async_playwright

import config
import playwright_config as pw_config
from crawler.utils import (
    visited,
    queued,
    restore_state_from_csv,
    load_html,
    create_output_directories,
    get_timestamp,
)
from crawler.parser import extract_unique_links
from crawler.crawler import crawl_bfs, retry_errors

# === コマンドライン引数のセットアップ ===
parser = argparse.ArgumentParser()
parser.add_argument("--resume", type=str, metavar="DIR", help="Resume crawl")
parser.add_argument("--retry", type=str, metavar="DIR", help="Retry ERROR rows")
args = parser.parse_args()


async def main():
    # Playwrightのユーザーデータディレクトリを作成
    os.makedirs(pw_config.user_data_dir, exist_ok=True)

    async with async_playwright() as p:
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

        # ログイン処理（必要な場合）
        if config.USE_USER_DATA and config.USE_USER_DATA_AND_LOGIN:
            if hasattr(config, "LOGIN_URL"):
                await page.goto(config.LOGIN_URL)
                await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR, timeout=600000)
            if hasattr(config, "LOGIN_URL2"):
                await page.goto(config.LOGIN_URL2)
                await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)

        # エラー行の再試行モード
        if args.retry:
            await retry_errors(page, args.retry)
        else:
            # 通常のクロールまたは再開モード
            output_dir = args.resume or os.path.join("results", get_timestamp())
            create_output_directories(output_dir)
            csv_path = os.path.join(output_dir, "result.csv")

            # クロール再開モード
            if args.resume:
                visited_set, _, max_depth = restore_state_from_csv(csv_path)
                start_depth = max_depth + 1
                start_urls = []

                # 最大深さのページからリンクを抽出
                import csv

                with open(csv_path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if int(row.get("depth", -1)) == max_depth:
                            html_path = os.path.join(
                                output_dir, "html", f"{row['case_id']}.html"
                            )
                            html = load_html(html_path)
                            if html:
                                for next_url, a_html in extract_unique_links(
                                    html, row["url"]
                                ).items():
                                    start_urls.append((next_url, row["url"], a_html))

                # グローバル状態を復元
                global visited, queued
                visited = visited_set
                queued = set()
            else:
                # 新規クロール
                start_depth = 0
                start_urls = [(url, "", "") for url in config.START_URLS]

            # クローリングを実行
            await crawl_bfs(page, start_urls, output_dir, start_depth)

        # ブラウザを閉じる
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
