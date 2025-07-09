"""
ドメイン置換関連の機能を提供するモジュール
"""

import os
import csv
from urllib.parse import urlparse, urlunparse
from typing import Dict, Any, List

import config
from crawler.utils import get_datetime, generate_case_id, read_csv
from crawler.crawler import crawl_single_page

# 追加クロールのCSV項目（ハードコーディング）
R1_CSV_FIELDS = [
    "url_r1",
    "redirect_chain_r1",
    "title_r1",
    "status_code_r1",
    "content_length_r1",
    "link_count_r1",
    "crawled_at_r1",
    "error_message_r1",
]


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
    if not all(field in rows[0] for field in R1_CSV_FIELDS):
        # 新しいヘッダーを追加したCSVを作成
        temp_path = csv_path + ".temp"
        with open(csv_path, "r", encoding="utf-8") as infile, open(
            temp_path, "w", newline="", encoding="utf-8"
        ) as outfile:
            writer = csv.writer(outfile)
            # 既存のヘッダーを取得
            header = next(csv.reader(infile))
            # 新しいヘッダーを追加
            writer.writerow(header + R1_CSV_FIELDS)
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
