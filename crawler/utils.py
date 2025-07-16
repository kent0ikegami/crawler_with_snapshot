"""
ユーティリティ関数モジュール
URL処理、ファイル操作などの共通関数を提供
"""

import os
import hashlib
import csv
from urllib.parse import urldefrag
from datetime import datetime
from collections import defaultdict, deque
from typing import Set, Dict, List, Tuple, Any, Optional

# Constants
SKIP_EXTENSIONS = [
    ".pdf",
    ".jpg",
    ".png",
    ".zip",
    ".exe",
    ".csv",
    ".tsv",
    ".xls",
    ".xlsx",
    ".doc",
    ".docx",
    ".ppt",
    ".pptx",
    ".txt",
    ".mp4",
    ".avi",
    ".mov",
    ".mp3",
    ".wav",
]


def sanitize_url(url: str) -> str:
    """URLからフラグメント部分を削除し正規化する"""
    return urldefrag(url)[0].strip()


def should_skip_extension(url: str) -> bool:
    """URLの拡張子がスキップすべきものかどうかを判定する"""
    return any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS)


def generate_case_id(url: str) -> str:
    """URLからケースIDを生成する（MD5ハッシュ）"""
    return hashlib.md5(url.encode()).hexdigest()


def save_html(path: str, html: str) -> None:
    """HTMLをファイルに保存する"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def load_html(path: str) -> Optional[str]:
    """HTMLファイルを読み込む。ファイルが存在しない場合はNoneを返す"""
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def log_status(depth: int, url: str, queue: defaultdict[int, deque]) -> None:
    """クローリングの状況をログに出力"""
    print(
        f"[depth={depth}] queue={len(queue[depth])} "
        f"total_queue={sum(len(q) for q in queue.values())} "
        f"visited={len(visited)} → {url}"
    )


def read_csv(path: str) -> List[Dict[str, str]]:
    """CSVファイルを読み込んで辞書のリストとして返す"""
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    """辞書のリストをCSVファイルに書き込む"""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def append_csv_row(path: str, row: Dict[str, str], fieldnames: List[str]) -> None:
    """1行だけCSVファイルに追記する

    Args:
        path: CSVファイルのパス
        row: 書き込む1行のデータ（辞書形式）
        fieldnames: CSVのフィールド名リスト
    """
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def create_output_directories(base_dir: str) -> None:
    """出力ディレクトリを作成"""
    os.makedirs(os.path.join(base_dir, "html"), exist_ok=True)
    os.makedirs(os.path.join(base_dir, "screenshots"), exist_ok=True)


def get_timestamp() -> str:
    """現在のタイムスタンプを取得（ディレクトリ名用）"""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def get_datetime() -> str:
    """現在の日時を文字列で取得（CSV用）"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# グローバル変数
visited: Set[str] = set()
queued: Set[str] = set()


def restore_state_from_csv(path: str) -> Tuple[Set[str], Set[str], int]:
    """CSVから状態を復元する"""
    visited_urls, queued_urls = set(), set()
    max_depth = -1
    if not os.path.exists(path):
        return visited_urls, queued_urls, max_depth

    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("url")
            if url:
                visited_urls.add(url)
            depth = row.get("depth")
            if depth and depth.isdigit():
                max_depth = max(max_depth, int(depth))

    return visited_urls, queued_urls, max_depth
