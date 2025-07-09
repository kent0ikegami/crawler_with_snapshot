"""
ドメイン置換関連の機能を提供するモジュール
"""

import os
import csv
from urllib.parse import urlparse, urlunparse
from typing import Dict, Any, List, Tuple

import config
import playwright_config as pw_config
from crawler.utils import get_datetime, generate_case_id, read_csv, save_html
from crawler.parser import extract_title, extract_unique_links

# 特殊処理用の矢印
NORMAL_ARROW = "→"
REPLACEMENT_ARROW = "⇒"

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


def is_domain_match(domain1: str, domain2: str) -> bool:
    """
    2つのドメインが完全に一致するかを判定する

    Args:
        domain1: 比較するドメイン1
        domain2: 比較するドメイン2

    Returns:
        完全に一致するかどうかのブール値
    """
    # 完全一致のみを判定
    return domain1 == domain2


def replace_domain(url: str) -> str:
    """
    設定に基づいてURLのドメインを置換する
    完全一致の場合のみ置換を行う

    Args:
        url: 元のURL

    Returns:
        ドメインが置換されたURL。置換ルールがなければ元のURLを返す
    """
    parsed = urlparse(url)
    netloc = parsed.netloc

    if not hasattr(config, "DOMAIN_REPLACEMENT_RULES"):
        return url

    for original_domain, replacement_domain in config.DOMAIN_REPLACEMENT_RULES.items():
        # 完全一致の場合のみ置換
        if netloc == original_domain:
            new_parsed = parsed._replace(netloc=replacement_domain)
            return urlunparse(new_parsed)

    return url


def check_redirect_chain_domain(
    redirect_chain: List[str], original_url: str
) -> Tuple[str, bool]:
    """
    リダイレクトチェーンを検査し、元のドメインに戻っている場合は再度置換する

    Args:
        redirect_chain: リダイレクトチェーン（URLのリスト）
        original_url: 元のURL

    Returns:
        (再度置換したURL, 特殊処理を行ったかどうか)のタプル
    """
    if not redirect_chain:
        return None, False

    # 最後のURLを取得
    final_url = redirect_chain[-1]

    # 元のURLから置換前のドメインを取得
    original_netloc = urlparse(original_url).netloc
    original_domain = None

    # 元のURLに一致する置換ルールを探す
    for domain, _ in config.DOMAIN_REPLACEMENT_RULES.items():
        if is_domain_match(domain, original_netloc):
            original_domain = domain
            break

    if not original_domain:
        return None, False

    # 最終URLのドメインをチェック
    final_netloc = urlparse(final_url).netloc

    # 最終的なURLが元のドメインかをチェック
    is_original_domain = is_domain_match(final_netloc, original_domain)

    if is_original_domain:
        # 元のドメインに戻っていた場合、再度置換
        new_url = replace_domain(final_url)
        if new_url != final_url:
            return new_url, True

    return None, False


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


def ensure_r1_csv_fields(csv_path: str) -> List[Dict]:
    """
    CSVファイルにR1用のフィールドが存在することを確認し、必要に応じて追加する

    Args:
        csv_path: 入力CSVファイルのパス

    Returns:
        更新後のCSVの行リスト
    """
    # CSVファイルを読み込む
    rows = read_csv(csv_path)
    if not rows:
        print(f"No rows found in {csv_path}")
        return []

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

    return rows


async def handle_redirects(
    page, redirect_chain: List[str], url: str, html_path: str, screenshot_path: str
) -> Tuple[str, str, int]:
    """
    リダイレクトを処理し、必要に応じて追加のURLにアクセスする

    Args:
        page: Playwrightのページオブジェクト
        redirect_chain: リダイレクトチェーン
        url: 元のURL
        html_path: 保存先HTMLパス
        screenshot_path: 保存先スクリーンショットパス

    Returns:
        (リダイレクト文字列, コンテンツ, ステータスコード)のタプル
    """
    redirect_chain_str = ""
    content = await page.content()
    status_code = 200  # デフォルト値

    # リダイレクトチェーンを逆順に（実際の流れ順に）
    if redirect_chain:
        redirect_chain = list(reversed(redirect_chain))

        # 元のドメインに戻っていないかチェック
        additional_url, special_redirect = check_redirect_chain_domain(
            redirect_chain, url
        )

        # リダイレクトチェーン文字列の作成（特殊処理がある場合は別の矢印を使用）
        redirect_chain_str = " ".join(
            [f"{NORMAL_ARROW} {url}" for url in redirect_chain]
        )

        # 特殊処理が必要な場合
        if special_redirect and additional_url:
            redirect_chain_str += f" {REPLACEMENT_ARROW} {additional_url}"

            # 追加のURLにアクセス
            try:
                print(
                    f"  → Detected redirect to original domain. Accessing replaced URL: {additional_url}"
                )
                additional_response = await page.goto(
                    additional_url,
                    timeout=pw_config.timeouts["navigation_timeout"],
                    wait_until="domcontentloaded",
                )

                if additional_response and additional_response.status < 400:
                    # 追加アクセスが成功した場合、新しいコンテンツを使用
                    content = await page.content()
                    save_html(html_path, content)
                    print(f"  → Updated R1 HTML with additional redirect content")

                    # 追加のスクリーンショット
                    await page.wait_for_timeout(500)
                    await page.screenshot(
                        **{
                            **pw_config.screenshot_options,
                            "path": screenshot_path,
                        }
                    )
                    print(f"  → Updated R1 screenshot with additional redirect content")

                    # 追加アクセスのステータスに更新
                    status_code = additional_response.status
            except Exception as add_err:
                print(f"  → Failed to access additional redirect URL: {str(add_err)}")

    return redirect_chain_str, content, status_code


async def crawl_single_url(
    page, url: str, new_url: str, depth: int, r1_html_dir: str, r1_screenshots_dir: str
) -> Dict:
    """
    単一のURLをクロールする

    Args:
        page: Playwrightのページオブジェクト
        url: 元のURL
        new_url: ドメイン置換後のURL
        depth: クロール深度
        r1_html_dir: R1用HTML保存ディレクトリ
        r1_screenshots_dir: R1用スクリーンショット保存ディレクトリ

    Returns:
        R1データの辞書
    """
    # 元のURLと同じcase_idを使用する（比較できるようにするため）
    original_case_id = generate_case_id(url)

    html_path = os.path.join(r1_html_dir, f"{original_case_id}.html")
    screenshot_path = os.path.join(r1_screenshots_dir, f"{original_case_id}.png")

    # ページクロールとHTMLの保存
    status_code = "ERROR"
    redirect_chain_str = ""
    title = ""
    content_length = 0
    link_count = 0
    error_message = ""
    content = ""

    try:
        response = None
        try:
            response = await page.goto(
                new_url,
                timeout=pw_config.timeouts["navigation_timeout"],
                wait_until="domcontentloaded",
            )

            if not response:
                raise Exception("No response received")

            if response.status >= 400:
                raise Exception(f"HTTP error: status={response.status}")

            status_code = response.status

        except Exception as nav_err:
            err_msg = str(nav_err)
            if "ERR_HTTP_RESPONSE_CODE_FAILURE" in err_msg or "HTTP error" in err_msg:
                status_code = 500
            else:
                raise nav_err

        # 特定のテキストが消えるのを待機
        if (
            hasattr(config, "WAIT_FOR_TEXT_TO_DISAPPEAR")
            and config.WAIT_FOR_TEXT_TO_DISAPPEAR
        ):
            try:
                await page.wait_for_function(
                    f"""() => !document.body.innerText.includes('{config.WAIT_FOR_TEXT_TO_DISAPPEAR}')""",
                    timeout=10000,
                )
            except Exception:
                pass

        # ページコンテンツの取得
        content = await page.content()
        save_html(html_path, content)
        print(f"  → R1 HTML saved to: {html_path}")

        # スクリーンショット取得
        try:
            await page.wait_for_timeout(500)
            await page.screenshot(
                **{**pw_config.screenshot_options, "path": screenshot_path}
            )
            print(f"  → R1 screenshot saved to: {screenshot_path}")
        except Exception as ss_err:
            print(f"  → Failed to save R1 screenshot: {str(ss_err)}")

        # リダイレクトチェーンの処理
        redirect_chain = []
        try:
            req = response.request if response else None
            while req:
                redirect_chain.append(req.url)
                req = req.redirected_from
        except Exception:
            pass

        # リダイレクト処理
        redirect_chain_str, content, status_code = await handle_redirects(
            page, redirect_chain, url, html_path, screenshot_path
        )

        # コンテンツ分析
        title = extract_title(content)
        link_map = extract_unique_links(content, new_url)
        link_count = len(link_map)
        content_length = len(content)

    except Exception as e:
        error_message = str(e)

    # 結果行の作成
    r1_row = {
        "url": new_url,
        "redirect_chain": redirect_chain_str,
        "from_url": url,
        "case_id": original_case_id,  # 元のURLと同じcase_idを使用
        "depth": depth,
        "title": title,
        "status_code": status_code,
        "content_length": content_length,
        "link_count": link_count,
        "crawled_at": get_datetime(),
        "error_message": error_message,
        "anchor_html": "",
    }

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

    return r1_data


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

    # CSVファイルを準備して読み込む
    rows = ensure_r1_csv_fields(csv_path)
    if not rows:
        return

    # 全行を処理
    total_rows = len(rows)
    print(f"Processing {total_rows} URLs for domain replacement...")

    # 各URLをクロール
    for i, row in enumerate(rows):
        url = row.get("url")
        if not url:
            continue

        print(f"[{i+1}/{total_rows}] Processing {url}")

        # ドメインを変更
        new_url = replace_domain(url)
        if new_url == url:
            print(f"No domain replacement rule matched for {url}, skipping...")
            continue

        print(f"  → Domain replaced: {url} → {new_url}")

        try:
            # クロール実行
            depth = int(row.get("depth", "0"))
            r1_data = await crawl_single_url(
                page, url, new_url, depth, r1_html_dir, r1_screenshots_dir
            )

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
