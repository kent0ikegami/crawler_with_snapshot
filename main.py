import os
import csv
import hashlib
import asyncio
from urllib.parse import urljoin, urldefrag, urlparse
import config
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import playwright_config as pw_config
from datetime import datetime

# タイムスタンプ付き出力ディレクトリ
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_base_dir = os.path.join("results", timestamp)
html_dir = os.path.join(output_base_dir, "html")
screenshot_dir = os.path.join(output_base_dir, "screenshots")
csv_path = os.path.join(output_base_dir, "result.csv")

# 出力ディレクトリ作成
os.makedirs(html_dir, exist_ok=True)
os.makedirs(screenshot_dir, exist_ok=True)

visited = set()
results = []

def sanitize_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.strip()

def generate_filename(url: str, ext: str) -> str:
    h = hashlib.md5(url.encode('utf-8')).hexdigest()
    return f"{h}.{ext}"

def extract_unique_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    link_set = set()
    for a in soup.find_all("a", href=True):
        href = a['href']
        joined_url = urljoin(base_url, href)
        clean_url = sanitize_url(joined_url)

        if not clean_url.startswith("http"):
            continue
        netloc = urlparse(clean_url).netloc
        if not any(netloc.endswith(allowed) for allowed in config.ALLOWED_DOMAINS):
            continue
        if any(clean_url.endswith(ext) for ext in [
            ".pdf", ".jpg", ".png", ".zip", ".exe", ".csv", ".tsv", ".xls", ".xlsx",
            ".doc", ".docx", ".ppt", ".pptx", ".txt", ".mp4", ".avi", ".mov", ".mp3", ".wav"
        ]):
            continue

        link_set.add(clean_url)

    return list(link_set)

def extract_title(html: str):
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""

async def crawl(page, url: str, depth: int):
    if url in visited or depth > config.MAX_DEPTH:
        return
    visited.add(url)
    print(f"[+] Crawling: {url} (depth={depth})")
    case_id = hashlib.md5(url.encode('utf-8')).hexdigest()
    html_filename = os.path.join(html_dir, f"{case_id}.html")
    screenshot_filename = os.path.join(screenshot_dir, f"{case_id}.png")

    try:
        await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        content = await page.content()

        # HTML保存
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(content)

        # スクリーンショット
        screenshot_opts = {**pw_config.screenshot_options, "path": screenshot_filename}
        await page.screenshot(**screenshot_opts)

        # 対象リンク抽出
        unique_links = extract_unique_links(content, url)

        result_row = {
            "url": url,
            "case_id": case_id,
            "depth": depth,
            "title": extract_title(content),
            "status_code": 200,
            "content_length": len(content),
            "link_count": len(unique_links),
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        results.append(result_row)

        # CSV追記（都度書き込み）
        file_exists = os.path.exists(csv_path)
        with open(csv_path, "a", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "url", "case_id", "depth", "title", "status_code",
                "content_length", "link_count", "crawled_at"
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(result_row)

        # 再帰クロール
        for link in unique_links:
            await crawl(page, link, depth + 1)

    except Exception as e:
        print(f"[!] Failed to process {url}: {e}")

async def main(start_urls):
    os.makedirs(pw_config.user_data_dir, exist_ok=True)

    async with async_playwright() as p:
        if config.USE_USER_DATA:
            context = await p.chromium.launch_persistent_context(
                pw_config.user_data_dir,
                **pw_config.launch_options,
                **pw_config.context_options
            )
        else:
            browser = await p.chromium.launch(**pw_config.launch_options)
            context = await browser.new_context(**pw_config.context_options)

        page = context.pages[0] if context.pages else await context.new_page()

        if config.USE_USER_DATA and hasattr(config, 'LOGIN_URL') and hasattr(config, 'LOGIN_WAIT_SELECTOR'):
            await page.goto(config.LOGIN_URL)
            await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)

        for url in start_urls:
            await crawl(page, url, depth=0)

        await context.close()

if __name__ == "__main__":
    asyncio.run(main(config.START_URLS))
