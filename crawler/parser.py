"""
HTMLパーサーモジュール
HTMLの解析とリンク抽出などの機能を提供
"""

from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from typing import Dict, List
import config
from crawler.utils import sanitize_url, should_skip_extension


def extract_title(html: str) -> str:
    """HTMLからタイトルを抽出する"""
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""


def extract_unique_links(html: str, base_url: str) -> Dict[str, str]:
    """HTMLから一意なリンクを抽出する

    Args:
        html: HTMLの内容
        base_url: リンクの基準URL

    Returns:
        key=URL、value=アンカータグのHTMLの辞書
    """
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    actual_base = base_tag["href"] if base_tag else base_url
    link_map = {}

    for a in soup.find_all("a", href=True):
        href = a["href"]

        # リンクテキストによるフィルタリング
        if hasattr(config, "SKIP_LINK_KEYWORDS") and any(
            k in a.get_text(strip=True) for k in config.SKIP_LINK_KEYWORDS
        ):
            continue

        # スキーム（mailto:など）によるフィルタリング
        if urlparse(href).scheme in ["mailto", "tel", "javascript"]:
            continue

        # URLの正規化
        joined_url = urljoin(actual_base, href)
        clean_url = sanitize_url(joined_url)

        # URLパターンによるフィルタリング
        if hasattr(config, "SKIP_URL_PATTERNS") and any(
            p in clean_url for p in config.SKIP_URL_PATTERNS
        ):
            continue

        # ドメインによるフィルタリング
        if not any(
            urlparse(clean_url).netloc.endswith(d) for d in config.ALLOWED_DOMAINS
        ):
            continue

        # 拡張子によるフィルタリング
        if should_skip_extension(clean_url):
            continue

        # 重複を防ぐ
        if clean_url not in link_map:
            link_map[clean_url] = str(a)

    return link_map
