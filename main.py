import os
import csv
import hashlib
import asyncio
from urllib.parse import urljoin, urldefrag
import config
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import playwright_config as pw_config

os.makedirs("html", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

visited = set()
results = []

def sanitize_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.strip()

def generate_filename(url: str, ext: str) -> str:
    h = hashlib.md5(url.encode('utf-8')).hexdigest()
    return f"{h}.{ext}"

async def take_screenshot(page, url: str, filename: str):
    try:
        # 既存のページでURLに移動
        await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        # filenameを直接指定し、設定オプションとマージ
        screenshot_opts = {**pw_config.screenshot_options, "path": filename}
        await page.screenshot(**screenshot_opts)
        return True
    except Exception as e:
        print(f"[!] Screenshot failed for {url}: {e}")
        return False

async def save_html(page, url: str, filename: str):
    try:
        # 既存のページでURLに移動
        await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        content = await page.content()
        status = 200  # Playwrightは正常にページを取得できた場合は暗黙的に成功
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
        
        return content, status, len(content)
    except Exception as e:
        print(f"[!] HTML fetch failed for {url}: {e}")
        return "", None, 0

def extract_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a['href']
        joined_url = urljoin(base_url, href)
        clean_url = sanitize_url(joined_url)
        if clean_url.startswith("http"):
            yield clean_url

def extract_title(html: str):
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""

async def crawl(page, url: str, depth: int):
    if url in visited or depth > config.MAX_DEPTH:
        return
    visited.add(url)
    print(f"[+] Crawling: {url} (depth={depth})")

    html_filename = os.path.join("html", generate_filename(url, "html"))
    screenshot_filename = os.path.join("screenshots", generate_filename(url, "png"))

    html, status_code, content_length = await save_html(page, url, html_filename)
    if not html:
        return

    await take_screenshot(page, url, screenshot_filename)
    
    results.append({
        "url": url,
        "depth": depth,
        "title": extract_title(html),
        "html_file": os.path.basename(html_filename),
        "screenshot_file": os.path.basename(screenshot_filename),
        "status_code": status_code,
        "content_length": content_length
    })

    for link in extract_links(html, url):
        await crawl(page, link, depth + 1)

async def main(start_urls):
    os.makedirs(pw_config.user_data_dir, exist_ok=True)
    
    async with async_playwright() as p:
        options = dict(pw_config.browser_context_options)
        context = await p.chromium.launch_persistent_context(
            pw_config.user_data_dir, 
            **options
        )
        page = context.pages[0] if context.pages else await context.new_page()

        # 初期ページをローディング
        await page.goto(config.LOGIN_URL)
        await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)
        
        # 各URLを同じページでクロール
        for url in start_urls:
            await crawl(page, url, depth=0)

        await context.close()

    with open("result.csv", "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["url", "depth", "title", "html_file", "screenshot_file", "status_code", "content_length"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

if __name__ == "__main__":
    asyncio.run(main(config.START_URLS))
