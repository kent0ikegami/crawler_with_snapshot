import os
import csv
import hashlib
import asyncio
from urllib.parse import urljoin, urldefrag, urlparse
from datetime import datetime
import config
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import playwright_config as pw_config

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

CSV_FIELDS = [
    "url", "redirect_chain", "from_url", "case_id", "depth",
    "title", "status_code", "content_length", "link_count", "crawled_at", "error_message"
]

def sanitize_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.strip()

def generate_filename(url: str, ext: str) -> str:
    h = hashlib.md5(url.encode('utf-8')).hexdigest()
    return f"{h}.{ext}"

def extract_unique_links(html: str, base_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    actual_base = base_tag["href"] if base_tag else base_url

    link_set = set()
    for a in soup.find_all("a", href=True):
        href = a['href']
        parsed = urlparse(href)
        if parsed.scheme in ["mailto", "tel", "javascript"]:
            continue

        joined_url = urljoin(actual_base, href)
        clean_url = sanitize_url(joined_url)

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

def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""

def write_csv_row(row: dict):
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

async def crawl(page, url: str, depth: int, from_url: str = ""):
    if url in visited or depth > config.MAX_DEPTH:
        return
    visited.add(url)
    print(f"[+] Crawling: {url} (depth={depth})")
    case_id = hashlib.md5(url.encode('utf-8')).hexdigest()
    html_filename = os.path.join(html_dir, f"{case_id}.html")
    screenshot_filename = os.path.join(screenshot_dir, f"{case_id}.png")

    try:
        response = await page.goto(url, timeout=pw_config.timeouts['navigation_timeout'])
        if not response:
            raise Exception("No response received")

        req = response.request
        redirect_chain = []
        while req:
            redirect_chain.append(req.url)
            req = req.redirected_from
        redirect_chain_str = " → ".join(reversed(redirect_chain))

        content = await page.content()

        with open(html_filename, "w", encoding="utf-8") as f:
            f.write(content)

        screenshot_opts = {**pw_config.screenshot_options, "path": screenshot_filename}
        await page.screenshot(**screenshot_opts)

        unique_links = extract_unique_links(content, response.url)

        row = {
            "url": url,
            "redirect_chain": redirect_chain_str,
            "from_url": from_url,
            "case_id": case_id,
            "depth": depth,
            "title": extract_title(content),
            "status_code": response.status,
            "content_length": len(content),
            "link_count": len(unique_links),
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": ""
        }
        results.append(row)
        write_csv_row(row)

        for link in unique_links:
            await crawl(page, link, depth + 1, from_url=url)

    except Exception as e:
        print(f"[!] Failed to process {url}: {e}")
        row = {
            "url": url,
            "redirect_chain": "",
            "from_url": from_url,
            "case_id": case_id,
            "depth": depth,
            "title": "",
            "status_code": "ERROR",
            "content_length": 0,
            "link_count": 0,
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": str(e)
        }
        write_csv_row(row)

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
            await crawl(page, url, depth=0, from_url="")

        await context.close()

if __name__ == "__main__":
    asyncio.run(main(config.START_URLS))
