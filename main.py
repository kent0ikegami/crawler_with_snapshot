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
import argparse
import csv
import sys
from datetime import datetime
from urllib.parse import urlparse, urlunparse
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
    generate_case_id,
    save_html,
    read_csv,
    get_datetime,
)
from crawler.parser import extract_unique_links
from crawler.crawler import crawl_bfs, retry_errors, crawl_single_page

# === コマンドライン引数のセットアップ ===
parser = argparse.ArgumentParser()
parser.add_argument("--resume", type=str, metavar="DIR", help="Resume crawl")
parser.add_argument("--retry", type=str, metavar="DIR", help="Retry ERROR rows")
parser.add_argument(
    "--domain-replace",
    type=str,
    metavar="CSV",
    help="Run domain replacement crawl on existing CSV",
)
args = parser.parse_args()


def replace_domain(url: str) -> str:
    """
    設定に基づいてURLのドメインを置換する

    Args:
        url: 元のURL

    Returns:
        ドメインが置換されたURL。置換ルールがなければ元のURLを返す
    """
    parsed = urlparse(url)
    domain = parsed.netloc

    if not hasattr(config, "DOMAIN_REPLACEMENT_RULES"):
        return url

    for original_domain, replacement_domain in config.DOMAIN_REPLACEMENT_RULES.items():
        if original_domain in domain:
            new_domain = domain.replace(original_domain, replacement_domain)
            new_parsed = parsed._replace(netloc=new_domain)
            return urlunparse(new_parsed)

    return url


async def crawl_with_domain_replacement(
    page,
    csv_path: str,
    output_dir: str,
) -> None:
    """
    既存のCSVファイルに記載されたURLに対して、ドメインを変更して追加クロールを行う

    Args:
        page: Playwrightのページオブジェクト
        csv_path: 入力CSVファイルのパス
        output_dir: 出力ディレクトリ
    """
    # R1用のディレクトリを作成
    r1_html_dir = os.path.join(output_dir, "html_r1")
    r1_screenshots_dir = os.path.join(output_dir, "screenshots_r1")
    os.makedirs(r1_html_dir, exist_ok=True)
    os.makedirs(r1_screenshots_dir, exist_ok=True)

    # CSVファイルを読み込む
    rows = read_csv(csv_path)
    if not rows:
        print(f"No rows found in {csv_path}")
        return

    # 追加フィールドの存在を確認し、必要に応じてヘッダーを追加
    if not all(field in rows[0] for field in config.R1_CSV_FIELDS):
        # 新しいヘッダーを追加したCSVを作成
        temp_path = csv_path + ".temp"
        with open(csv_path, "r", encoding="utf-8") as infile, open(
            temp_path, "w", newline="", encoding="utf-8"
        ) as outfile:
            writer = csv.writer(outfile)
            # 既存のヘッダーを取得
            header = next(csv.reader(infile))
            # 新しいヘッダーを追加
            writer.writerow(header + config.R1_CSV_FIELDS)
            # 残りの行をそのままコピー
            for line in infile:
                outfile.write(line)

        # 元のファイルを置き換え
        os.replace(temp_path, csv_path)

        # 更新されたCSVを再読み込み
        rows = read_csv(csv_path)

    # 全行を処理
    rows_to_process = rows
    total_rows = len(rows_to_process)

    print(f"Processing {total_rows} URLs for domain replacement...")

    # 各URLをクロール
    for i, row in enumerate(rows_to_process):
        url = row.get("url")
        if not url:
            continue

        print(f"[{i+1}/{total_rows}] Processing {url}")

        # ドメインを変更
        new_url = replace_domain(url)
        if new_url == url:
            print(f"No domain replacement rule matched for {url}, skipping...")
            continue

        # クロールを実行
        case_id = generate_case_id(new_url)
        html_path = os.path.join(r1_html_dir, f"{case_id}.html")
        screenshot_path = os.path.join(r1_screenshots_dir, f"{case_id}.png")

        try:
            # クロール実行
            depth = int(row.get("depth", "0"))
            r1_row, r1_link_map = await crawl_single_page(
                page, new_url, depth, url, "", output_dir
            )

            # R1用の結果行を作成
            r1_data = {
                "url_r1": new_url,
                "redirect_chain_r1": r1_row.get("redirect_chain", ""),
                "title_r1": r1_row.get("title", ""),
                "status_code_r1": r1_row.get("status_code", "ERROR"),
                "content_length_r1": str(r1_row.get("content_length", 0)),
                "link_count_r1": str(r1_row.get("link_count", 0)),
                "crawled_at_r1": r1_row.get("crawled_at", get_datetime()),
                "error_message_r1": r1_row.get("error_message", ""),
            }

            # CSVに行を追記
            update_csv_row(csv_path, url, r1_data)
            print(f"  → R1 crawl completed: {new_url}")

        except Exception as e:
            error_message = str(e)
            r1_data = {
                "url_r1": new_url,
                "redirect_chain_r1": "",
                "title_r1": "",
                "status_code_r1": "ERROR",
                "content_length_r1": "0",
                "link_count_r1": "0",
                "crawled_at_r1": get_datetime(),
                "error_message_r1": error_message,
            }

            # エラーがあっても行を追記
            update_csv_row(csv_path, url, r1_data)
            print(f"  → Error crawling {new_url}: {error_message}")


def update_csv_row(csv_path: str, url: str, r1_data: dict) -> None:
    """
    CSVの特定のURLの行にR1データを追記する

    Args:
        csv_path: CSVファイルのパス
        url: 対象のURL
        r1_data: 追記するR1のデータ
    """
    # CSVを読み込む
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)

    # URLに一致する行を更新
    for row in rows:
        if row.get("url") == url:
            row.update(r1_data)
            break

    # CSVに書き戻す
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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

        # ドメイン置換クロールモード
        if args.domain_replace:
            if not os.path.exists(args.domain_replace):
                print(f"Error: CSVファイルが見つかりません: {args.domain_replace}")
                sys.exit(1)

            # 出力ディレクトリはCSVファイルと同じディレクトリ
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
