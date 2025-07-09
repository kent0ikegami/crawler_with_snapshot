"""
Crawler with Snapshot
クローリングと同時に画面キャプチャも取るWebクローラー

コマンドライン引数:
--resume DIR: 指定ディレクトリのクロールを再開する
--retry DIR: 指定ディレクトリのエラー行を再試行する
--domain-replace CSV: 既存のCSVに対してドメインを変更してクロールする
"""

import os
import asyncio
import sys
import csv
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
from crawler.cli import parse_args, validate_args
from crawler.browser import setup_browser, perform_login
from crawler.domain.replacer import crawl_with_domain_replacement

# コマンドライン引数の解析
args = parse_args()


async def main():
    # 引数の検証
    if not validate_args(args):
        sys.exit(1)

    async with async_playwright() as p:
        # ブラウザと初期ページのセットアップ
        context, page = await setup_browser(p, pw_config, config)

        # ログイン処理
        await perform_login(page, config)

        # ドメイン置換クロールモード
        if args.domain_replace:
            output_dir = os.path.dirname(args.domain_replace)
            print(f"Domain replacement crawling on: {args.domain_replace}")
            await crawl_with_domain_replacement(page, args.domain_replace, output_dir)

        # エラー行の再試行モード
        elif args.retry:
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
                        if int(row.get("depth", "-1")) == max_depth:
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

            # 自動ドメイン置換クロール (設定でオプトイン)
            if (
                hasattr(config, "DOMAIN_REPLACEMENT")
                and isinstance(config.DOMAIN_REPLACEMENT, dict)
                and config.DOMAIN_REPLACEMENT.get("ENABLE", False)
            ):
                csv_path = config.DOMAIN_REPLACEMENT.get("CSV_PATH") or csv_path
                if os.path.exists(csv_path):
                    print(f"Auto domain replacement crawling on: {csv_path}")
                    await crawl_with_domain_replacement(page, csv_path, output_dir)
                else:
                    print("Domain replacement is enabled but CSV_PATH is not valid.")

        # ブラウザを閉じる
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
