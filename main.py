import os
import csv
import hashlib
import asyncio
from urllib.parse import urljoin, urldefrag
import config
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import playwright_config as pw_config

# 保存ディレクトリ
os.makedirs("html", exist_ok=True)
os.makedirs("screenshots", exist_ok=True)

visited = set()
results = []

def sanitize_url(url: str) -> str:
    url, _ = urldefrag(url)  # #以降を除去
    return url.strip()

def generate_filename(url: str, ext: str) -> str:
    h = hashlib.md5(url.encode('utf-8')).hexdigest()
    return f"{h}.{ext}"

async def take_screenshot(page, url: str, filename: str):
    try:
        await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        # filenameを直接指定し、設定オプションとマージ
        screenshot_opts = {**pw_config.screenshot_options, "path": filename}
        await page.screenshot(**screenshot_opts)
    except Exception as e:
        print(f"[!] Screenshot failed for {url}: {e}")

async def save_html(context, url: str, filename: str):
    try:
        page = await context.new_page()
        await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        content = await page.content()
        status = 200  # Playwrightは正常にページを取得できた場合は暗黙的に成功
        
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
            
        await page.close()
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

async def crawl(context, url: str, depth: int):
    if url in visited or depth > config.MAX_DEPTH:
        return
    visited.add(url)
    print(f"[+] Crawling: {url} (depth={depth})")

    html_filename = os.path.join("html", generate_filename(url, "html"))
    screenshot_filename = os.path.join("screenshots", generate_filename(url, "png"))

    html, status_code, content_length = await save_html(context, url, html_filename)
    if not html:
        return

    page = await context.new_page()
    await take_screenshot(page, url, screenshot_filename)
    await page.close()

    title = extract_title(html)

    results.append({
        "url": url,
        "depth": depth,
        "title": title,
        "html_file": os.path.basename(html_filename),
        "screenshot_file": os.path.basename(screenshot_filename),
        "status_code": status_code,
        "content_length": content_length
    })

    for link in extract_links(html, url):
        await crawl(context, link, depth + 1)

async def main(start_urls):
    # ディレクトリが存在することを確認
    os.makedirs(pw_config.user_data_dir, exist_ok=True)
    
    async with async_playwright() as p:
        # 設定を準備
        options = dict(pw_config.browser_context_options)
        
        # ログイン状態を使用する場合
        # if config.USE_LOGIN and os.path.exists("storage_state.json"):
        #     options["storage_state"] = "storage_state.json"
            
        # 永続的コンテキストを作成
        context = await p.chromium.launch_persistent_context(
            pw_config.user_data_dir, 
            **options
        )

        for url in start_urls:
            await crawl(context, url, depth=0)

        # launch_persistent_contextを使用した場合はcontextのみを閉じる
        await context.close()

    with open("result.csv", "w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["url", "depth", "title", "html_file", "screenshot_file", "status_code", "content_length"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

if __name__ == "__main__":
    asyncio.run(main(config.START_URLS))
