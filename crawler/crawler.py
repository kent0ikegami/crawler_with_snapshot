"""
クローラーの中核ロジック
ページのクロール、スクリーンショット取得、BFS探索などの機能を提供
"""

import os
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Set, Any, Optional
from playwright.async_api import Page
from datetime import datetime
import config
import playwright_config as pw_config
from crawler.utils import (
    visited,
    queued,
    generate_case_id,
    save_html,
    log_status,
    read_csv,
    write_csv,
    get_datetime,
    load_html,
)
from crawler.parser import extract_unique_links, extract_title

# CSV出力項目の定義
CSV_FIELDS = [
    "url",
    "redirect_chain",
    "from_url",
    "case_id",
    "depth",
    "title",
    "status_code",
    "content_length",
    "link_count",
    "crawled_at",
    "error_message",
    "anchor_html",
]


async def crawl_single_page(
    page: Page,
    url: str,
    depth: int,
    from_url: str = "",
    from_anchor_html: str = "",
    output_dir: str = "",
) -> Tuple[Dict[str, Any], Dict[str, str]]:
    """単一のページをクロールする

    Args:
        page: Playwrightのページオブジェクト
        url: クロール対象のURL
        depth: クロールの深さ
        from_url: リンク元のURL
        from_anchor_html: リンク元のアンカータグHTML
        output_dir: 出力先ディレクトリ

    Returns:
        結果行の辞書とリンクマップのタプル
    """
    case_id = generate_case_id(url)
    html_path = os.path.join(output_dir, "html", f"{case_id}.html")
    screenshot_path = os.path.join(output_dir, "screenshots", f"{case_id}.png")
    status_code = "ERROR"

    try:
        response = None
        try:
            # waitUntil: 'networkidle'を追加してリダイレクトを含むページの読み込み完了を待機
            response = await page.goto(
                url,
                timeout=pw_config.timeouts["navigation_timeout"],
                wait_until="networkidle",  # リダイレクト完了＆ネットワーク通信完了まで待機
            )

            # ページの準備ができているか確認
            if not response:
                raise Exception("No response received")

            if response.status >= 400:
                raise Exception(f"HTTP error: status={response.status}")

            status_code = response.status

            # まずDOMContentLoadedイベントを待つ
            await page.wait_for_load_state("domcontentloaded")

            # 次に、可能であればnetworkidleを待つ（より安定したページ状態）
            try:
                await page.wait_for_load_state(
                    "networkidle", timeout=pw_config.timeouts["network_idle_timeout"]
                )
            except Exception as idle_err:
                print(f"Network idle timeout for {url}: {str(idle_err)}")
                # networkidle待機のエラーは無視して続行

        except Exception as nav_err:
            err_msg = str(nav_err)
            if "ERR_HTTP_RESPONSE_CODE_FAILURE" in err_msg or "HTTP error" in err_msg:
                status_code = 500
                # エラーページでもできるだけコンテンツを取得
                try:
                    await page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass  # エラーは無視して続行
            else:
                print(f"Navigation error for {url}: {err_msg}")
                raise nav_err

        # WAIT_FOR_TEXT_TO_DISAPPEARの処理（configに設定がある場合）
        if (
            hasattr(config, "WAIT_FOR_TEXT_TO_DISAPPEAR")
            and config.WAIT_FOR_TEXT_TO_DISAPPEAR
        ):
            try:
                wait_text = config.WAIT_FOR_TEXT_TO_DISAPPEAR
                await page.wait_for_function(
                    f"""() => !document.body.innerText.includes('{wait_text}')""",
                    timeout=10000,
                )
            except Exception as wait_err:
                print(f"Wait error for {url}: {str(wait_err)}")
                # エラーをスローせずに続行

        # ページコンテンツの取得
        content = await page.content()
        save_html(html_path, content)

        # スクリーンショットを取得（リダイレクト完了後）
        try:
            # スクリーンショット取得前に短い待機を追加（ページレンダリング完了を確保）
            await page.wait_for_timeout(500)

            # スクリーンショットの取得
            await page.screenshot(
                **{**pw_config.screenshot_options, "path": screenshot_path}
            )
        except Exception as ss_err:
            print(f"Screenshot error for {url}: {str(ss_err)}")
            # スクリーンショットが失敗しても処理を続行

        # リダイレクトチェーンの処理
        redirect_chain = []
        try:
            # responseがNoneの場合でも安全に処理
            req = response.request if response else None
            while req:
                redirect_chain.append(req.url)
                req = req.redirected_from
        except Exception as redirect_err:
            print(f"Redirect chain error for {url}: {str(redirect_err)}")
            # リダイレクト情報の取得に失敗しても処理を続行

        # リダイレクトチェーンが空でない場合のみ結合
        redirect_chain_str = (
            " → ".join(reversed(redirect_chain)) if redirect_chain else ""
        )

        link_map = extract_unique_links(content, url)
        return {
            "url": url,
            "redirect_chain": redirect_chain_str,
            "from_url": from_url,
            "case_id": case_id,
            "depth": depth,
            "title": extract_title(content),
            "status_code": status_code,
            "content_length": len(content),
            "link_count": len(link_map),
            "crawled_at": get_datetime(),
            "error_message": "",
            "anchor_html": from_anchor_html,
        }, link_map

    except Exception as e:
        return {
            "url": url,
            "redirect_chain": "",
            "from_url": from_url,
            "case_id": case_id,
            "depth": depth,
            "title": "",
            "status_code": status_code,
            "content_length": 0,
            "link_count": 0,
            "crawled_at": get_datetime(),
            "error_message": str(e),
            "anchor_html": from_anchor_html,
        }, {}


async def crawl_bfs(
    page: Page,
    start_urls: List[Tuple[str, str, str]],
    output_dir: str,
    start_depth: int = 0,
) -> None:
    """幅優先探索でクロールを実行する

    Args:
        page: Playwrightのページオブジェクト
        start_urls: 開始URLのリスト (url, from_url, anchor_html)のタプル
        output_dir: 出力先ディレクトリ
        start_depth: 開始深さ
    """
    global visited, queued

    queue = defaultdict(deque)
    for url, from_url, a_html in start_urls:
        if url not in visited and url not in queued:
            queue[start_depth].append((url, from_url, a_html))
            queued.add(url)

    csv_path = os.path.join(output_dir, "result.csv")

    # 既存の結果を読み込み、URLをキーにした辞書に変換
    rows_by_url = {}
    if os.path.exists(csv_path):
        for row in read_csv(csv_path):
            if row.get("url"):
                rows_by_url[row.get("url")] = row

    for depth in range(start_depth, config.MAX_DEPTH + 1):
        while queue[depth]:
            url, from_url, a_html = queue[depth].popleft()
            log_status(depth, url, queue)

            visited.add(url)
            row, link_map = await crawl_single_page(
                page, url, depth, from_url, a_html, output_dir
            )

            # URLをキーにして行を辞書に格納（同じURLは上書き）
            rows_by_url[url] = row

            for next_url, next_anchor in link_map.items():
                if next_url not in visited and next_url not in queued:
                    queue[depth + 1].append((next_url, url, next_anchor))
                    queued.add(next_url)

    # 辞書から値のリストに戻してCSVに書き出し
    write_csv(csv_path, list(rows_by_url.values()), CSV_FIELDS)


async def retry_errors(page: Page, output_dir: str) -> None:
    """エラーになったページを再試行する

    Args:
        page: Playwrightのページオブジェクト
        output_dir: 出力先ディレクトリ
    """
    csv_path = os.path.join(output_dir, "result.csv")
    rows = read_csv(csv_path)

    # URLをキーにして行を辞書化（同じURLの行はこれで上書きされる）
    rows_by_url = {row.get("url"): row for row in rows if row.get("url")}

    error_rows = [r for r in rows if r.get("status_code") == "ERROR"]
    print(f"Retrying {len(error_rows)} error rows...")

    for i, row in enumerate(error_rows):
        url = row["url"]
        print(f"[{i+1}/{len(error_rows)}] Retrying {url}")

        new_row, _ = await crawl_single_page(
            page,
            url,
            int(row["depth"]),
            row["from_url"],
            row["anchor_html"],
            output_dir,
        )

        # 元の行のインデックスを維持しつつ、新しい行で上書き
        rows_by_url[url] = new_row

    # 辞書から値のリストに戻す
    updated_rows = list(rows_by_url.values())

    # CSVに書き出し
    write_csv(csv_path, updated_rows, CSV_FIELDS)
    print(f"Updated {len(error_rows)} rows in {csv_path}")
