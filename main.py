import os
import csv
import hashlib
import asyncio
import argparse
from urllib.parse import urljoin, urldefrag, urlparse
from datetime import datetime
from collections import defaultdict, deque
import config
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import playwright_config as pw_config

parser = argparse.ArgumentParser()
parser.add_argument(
    "--resume",
    type=str,
    metavar="DIR",
    help="Resume from existing directory (e.g., results/20250708_093000)",
)
args = parser.parse_args()

# 出力先ディレクトリ
if args.resume:
    output_base_dir = args.resume
else:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_base_dir = os.path.join("results", timestamp)

html_dir = os.path.join(output_base_dir, "html")
screenshot_dir = os.path.join(output_base_dir, "screenshots")
csv_path = os.path.join(output_base_dir, "result.csv")
os.makedirs(html_dir, exist_ok=True)
os.makedirs(screenshot_dir, exist_ok=True)

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

visited = set()
queued = set()


def sanitize_url(url: str) -> str:
    url, _ = urldefrag(url)
    return url.strip()


def generate_filename(url: str, ext: str) -> str:
    h = hashlib.md5(url.encode("utf-8")).hexdigest()
    return f"{h}.{ext}"


def extract_unique_links(html: str, base_url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    actual_base = base_tag["href"] if base_tag else base_url
    link_map = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        html_snippet = str(a)
        text = a.get_text(strip=True) or ""
        if hasattr(config, "SKIP_LINK_KEYWORDS") and any(
            k in text for k in config.SKIP_LINK_KEYWORDS
        ):
            continue
        parsed = urlparse(href)
        if parsed.scheme in ["mailto", "tel", "javascript"]:
            continue
        joined_url = urljoin(actual_base, href)
        clean_url = sanitize_url(joined_url)
        if hasattr(config, "SKIP_URL_PATTERNS") and any(
            p in clean_url for p in config.SKIP_URL_PATTERNS
        ):
            continue
        netloc = urlparse(clean_url).netloc
        if not any(netloc.endswith(allowed) for allowed in config.ALLOWED_DOMAINS):
            continue
        if any(
            clean_url.endswith(ext)
            for ext in [
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
        ):
            continue
        if clean_url not in link_map:
            link_map[clean_url] = html_snippet
    return link_map


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


def log_status(depth: int, current_url: str, queue: defaultdict[int, deque]):
    total_queue = sum(len(q) for q in queue.values())
    print(
        f"[depth={depth}] queue={len(queue[depth])} total_queue={total_queue} visited={len(visited)} → {current_url}"
    )


def restore_state_from_csv(csv_path: str):
    visited_urls = set()
    queued_urls = set()
    max_depth = -1
    if not os.path.exists(csv_path):
        return visited_urls, queued_urls, max_depth
    with open(csv_path, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            url = row.get("url")
            depth = row.get("depth")
            if url:
                visited_urls.add(url)
            if depth and depth.isdigit():
                max_depth = max(max_depth, int(depth))
    return visited_urls, queued_urls, max_depth


def get_urls_to_resume(depth: int) -> list[tuple[str, str, str]]:
    urls = []
    if not os.path.exists(csv_path):
        return urls
    with open(csv_path, "r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                if int(row.get("depth", -1)) == depth - 1:
                    url = row.get("url")
                    case_id = row.get("case_id")
                    if url and case_id:
                        html_path = os.path.join(html_dir, f"{case_id}.html")
                        if os.path.exists(html_path):
                            with open(html_path, "r", encoding="utf-8") as f:
                                html = f.read()
                            link_map = extract_unique_links(html, url)
                            for next_url, anchor_html in link_map.items():
                                urls.append((next_url, url, anchor_html))
            except ValueError:
                continue
    return urls


async def crawl_single_page(
    page, url: str, depth: int, from_url: str = "", from_anchor_html: str = ""
) -> dict:
    if url in visited:
        return {}
    visited.add(url)
    case_id = hashlib.md5(url.encode("utf-8")).hexdigest()
    html_filename = os.path.join(html_dir, f"{case_id}.html")
    screenshot_filename = os.path.join(screenshot_dir, f"{case_id}.png")
    response = None
    status_code = "ERROR"

    try:
        try:
            response = await page.goto(
                url,
                timeout=pw_config.timeouts["navigation_timeout"],
            )
            status_code = response.status
        except Exception as nav_err:
            err_msg = str(nav_err)
            if "ERR_HTTP_RESPONSE_CODE_FAILURE" in err_msg:
                status_code = 500
            else:
                raise nav_err
        if (
            hasattr(config, "WAIT_FOR_TEXT_TO_DISAPPEAR")
            and config.WAIT_FOR_TEXT_TO_DISAPPEAR
        ):
            wait_text = config.WAIT_FOR_TEXT_TO_DISAPPEAR
            await page.wait_for_function(
                f"""() => !document.body.innerText.includes('{wait_text}')""",
                timeout=10000,
            )
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
        link_map = extract_unique_links(content, response.url)
        row = {
            "url": url,
            "redirect_chain": redirect_chain_str,
            "from_url": from_url,
            "case_id": case_id,
            "depth": depth,
            "title": extract_title(content),
            "status_code": status_code,
            "content_length": len(content),
            "link_count": len(link_map),
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": "",
            "anchor_html": from_anchor_html or "",
        }
        write_csv_row(row)
        return link_map
    except Exception as e:
        row = {
            "url": url,
            "redirect_chain": "",
            "from_url": from_url,
            "case_id": case_id,
            "depth": depth,
            "title": "",
            "status_code": status_code,
            "content_length": 0,
            "link_count": 0,
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": str(e),
            "anchor_html": from_anchor_html or "",
        }
        write_csv_row(row)
        return {}


async def crawl_bfs(page, start_urls: list[str], start_depth: int = 0):
    queue = defaultdict(deque)
    max_depth = config.MAX_DEPTH
    for url, from_url, anchor_html in start_urls:
        if url not in visited and url not in queued:
            queue[start_depth].append((url, from_url, anchor_html))
            queued.add(url)
    for depth in range(start_depth, max_depth + 1):
        while queue[depth]:
            url, from_url, anchor_html = queue[depth].popleft()
            log_status(depth, url, queue)
            link_map = await crawl_single_page(page, url, depth, from_url, anchor_html)
            for next_url, next_anchor_html in link_map.items():
                if next_url not in visited and next_url not in queued:
                    queue[depth + 1].append((next_url, url, next_anchor_html))
                    queued.add(next_url)


async def main(start_urls, start_depth, visited_input, queued_input):
    global visited, queued
    visited = visited_input
    queued = queued_input
    os.makedirs(pw_config.user_data_dir, exist_ok=True)
    async with async_playwright() as p:
        if config.USE_USER_DATA:
            context = await p.chromium.launch_persistent_context(
                pw_config.user_data_dir,
                **pw_config.launch_options,
                **pw_config.context_options,
            )
        else:
            browser = await p.chromium.launch(**pw_config.launch_options)
            context = await browser.new_context(**pw_config.context_options)
        page = context.pages[0] if context.pages else await context.new_page()
        if (
            config.USE_USER_DATA
            and config.USE_USER_DATA_AND_LOGIN
            and hasattr(config, "LOGIN_URL")
            and hasattr(config, "LOGIN_WAIT_SELECTOR")
        ):
            await page.goto(config.LOGIN_URL)
            await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR, timeout=600000)
        if (
            config.USE_USER_DATA
            and config.USE_USER_DATA_AND_LOGIN
            and hasattr(config, "LOGIN_URL2")
            and hasattr(config, "LOGIN_WAIT_SELECTOR")
        ):
            await page.goto(config.LOGIN_URL2)
            await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)
        await crawl_bfs(page, start_urls, start_depth=start_depth)
        await context.close()


if __name__ == "__main__":
    if args.resume:
        visited, queued, max_depth = restore_state_from_csv(csv_path)
        start_depth = max_depth + 1
        start_urls = get_urls_to_resume(start_depth)
    else:
        visited = set()
        queued = set()
        start_depth = 0
        start_urls = [(url, "", "") for url in config.START_URLS]

    async def start():
        await main(start_urls, start_depth, visited, queued)

    asyncio.run(start())
