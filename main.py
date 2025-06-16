import os
import csv
import hashlib
import asyncio
from urllib.parse import urljoin, urldefrag
import config
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import playwright_config as pw_config
from datetime import datetime


# 出力ディレクトリ作成
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_base_dir = os.path.join("results", timestamp)
html_dir = os.path.join(output_base_dir, "html")
screenshot_dir = os.path.join(output_base_dir, "screenshots")
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

def extract_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a['href']
        joined_url = urljoin(base_url, href)
        clean_url = sanitize_url(joined_url)

        # スキップ対象
        if not clean_url.startswith("http"):
            continue
        if any(clean_url.endswith(ext) for ext in [".pdf", ".jpg", ".png", ".zip", ".exe", ".csv", ".tsv", ".xls", ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".txt", ".mp4", ".avi", ".mov", ".mp3", ".wav"]):
            continue    

        yield clean_url

def extract_title(html: str):
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""

async def crawl(page, url: str, depth: int):
    if url in visited or depth > config.MAX_DEPTH:
        return
    visited.add(url)
    print(f"[+] Crawling: {url} (depth={depth})")

    html_filename = os.path.join(html_dir, generate_filename(url, "html"))
    screenshot_filename = os.path.join(screenshot_dir, generate_filename(url, "png"))

    try:
        await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        content = await page.content()

        # HTML保存
        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(content)

        # スクリーンショット
        screenshot_opts = {**pw_config.screenshot_options, "path": screenshot_filename}
        await page.screenshot(**screenshot_opts)

        # 結果保存
        results.append({
            "url": url,
            "depth": depth,
            "title": extract_title(content),
            "html_file": os.path.basename(html_filename),
            "screenshot_file": os.path.basename(screenshot_filename),
            "status_code": 200,
            "content_length": len(content),
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

        # 再帰クロール
        for link in extract_links(content, url):
            await crawl(page, link, depth + 1)

    except Exception as e:
        print(f"[!] Failed to process {url}: {e}")

async def main(start_urls):
    os.makedirs(pw_config.user_data_dir, exist_ok=True)
    
    async with async_playwright() as p:
        options = dict(pw_config.browser_context_options)
        context = await p.chromium.launch_persistent_context(
            pw_config.user_data_dir, 
            **options
        )

        # 初期ページ取得 or 新規作成
        if context.pages:
            page = context.pages[0]
        else:
            page = await context.new_page()
        await page.goto(config.LOGIN_URL)
        await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)

        # 各URLクロール開始
        for url in start_urls:
            await crawl(page, url, depth=0)

        await context.close()

    # CSV出力
    with open(os.path.join(output_base_dir, "result.csv"), "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["url", "depth", "title", "html_file", "screenshot_file", "status_code", "content_length", "crawled_at"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

if __name__ == "__main__":
    asyncio.run(main(config.START_URLS))
