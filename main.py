import os
import csv
import hashlib
import asyncio
import argparse
from urllib.parse import urljoin, urldefrag, urlparse
from datetime import datetime
from collections import defaultdict, deque
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import config
import playwright_config as pw_config

# === Constants ===
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

# === Argument & Output Setup ===
parser = argparse.ArgumentParser()
parser.add_argument(
    "--resume", type=str, metavar="DIR", help="Resume from existing directory"
)
args = parser.parse_args()
output_base_dir = args.resume or os.path.join(
    "results", datetime.now().strftime("%Y%m%d_%H%M%S")
)
html_dir = os.path.join(output_base_dir, "html")
screenshot_dir = os.path.join(output_base_dir, "screenshots")
csv_path = os.path.join(output_base_dir, "result.csv")
os.makedirs(html_dir, exist_ok=True)
os.makedirs(screenshot_dir, exist_ok=True)

visited, queued = set(), set()


# === Utility Functions ===
def sanitize_url(url: str) -> str:
    return urldefrag(url)[0].strip()


def should_skip_extension(url: str) -> bool:
    return any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS)


def generate_filename(url: str, ext: str) -> str:
    return f"{hashlib.md5(url.encode()).hexdigest()}.{ext}"


def save_html(case_id: str, html: str):
    with open(os.path.join(html_dir, f"{case_id}.html"), "w", encoding="utf-8") as f:
        f.write(html)


def load_html(case_id: str) -> str | None:
    path = os.path.join(html_dir, f"{case_id}.html")
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


def log_status(depth: int, url: str, queue: defaultdict[int, deque]):
    total = sum(len(q) for q in queue.values())
    print(
        f"[depth={depth}] queue={len(queue[depth])} total_queue={total} visited={len(visited)} → {url}"
    )


# === HTML Processing ===
def extract_title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.string.strip() if soup.title and soup.title.string else ""


def extract_unique_links(html: str, base_url: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    base_tag = soup.find("base", href=True)
    actual_base = base_tag["href"] if base_tag else base_url
    link_map = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
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
        if not any(
            urlparse(clean_url).netloc.endswith(allowed)
            for allowed in config.ALLOWED_DOMAINS
        ):
            continue
        if should_skip_extension(clean_url):
            continue
        if clean_url not in link_map:
            link_map[clean_url] = str(a)
    return link_map


# === CSV Handling ===
def write_csv_row(row: dict):
    file_exists = os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def restore_state_from_csv(path: str):
    visited_urls, max_depth = set(), -1
    if not os.path.exists(path):
        return visited_urls, set(), max_depth
    with open(path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("url")
            if url:
                visited_urls.add(url)
            depth = row.get("depth")
            if depth and depth.isdigit():
                max_depth = max(max_depth, int(depth))
    return visited_urls, set(), max_depth


def get_urls_to_resume(depth: int) -> list[tuple[str, str, str]]:
    urls = []
    if not os.path.exists(csv_path):
        return urls
    with open(csv_path, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if int(row.get("depth", -1)) == depth - 1:
                url = row.get("url")
                case_id = row.get("case_id")
                if url and case_id:
                    html = load_html(case_id)
                    if html:
                        for next_url, a_html in extract_unique_links(html, url).items():
                            urls.append((next_url, url, a_html))
    return urls


# === Core Crawl Logic ===
async def crawl_single_page(
    page, url: str, depth: int, from_url="", from_anchor_html=""
) -> dict:
    if url in visited:
        return {}
    visited.add(url)
    case_id = hashlib.md5(url.encode()).hexdigest()
    html_path = os.path.join(html_dir, f"{case_id}.html")
    screenshot_path = os.path.join(screenshot_dir, f"{case_id}.png")
    status_code = "ERROR"

    try:
        try:
            response = await page.goto(
                url, timeout=pw_config.timeouts["navigation_timeout"]
            )
            if not response or response.status >= 400:
                raise Exception(
                    f"HTTP error or no response: status={response.status if response else 'N/A'}"
                )
            status_code = response.status
        except Exception as nav_err:
            err_msg = str(nav_err)
            if "ERR_HTTP_RESPONSE_CODE_FAILURE" in err_msg or "HTTP error" in err_msg:
                status_code = 500
            else:
                raise nav_err

        content = await page.content()
        save_html(case_id, content)
        await page.screenshot(
            **{**pw_config.screenshot_options, "path": screenshot_path}
        )

        redirect_chain = []
        req = response.request if response else None
        while req:
            redirect_chain.append(req.url)
            req = req.redirected_from
        redirect_chain_str = " → ".join(reversed(redirect_chain))

        link_map = extract_unique_links(content, url)
        write_csv_row(
            {
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
                "anchor_html": from_anchor_html,
            }
        )
        return link_map

    except Exception as e:
        write_csv_row(
            {
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
                "anchor_html": from_anchor_html,
            }
        )
        return {}


async def crawl_bfs(page, start_urls: list[tuple[str, str, str]], start_depth=0):
    queue = defaultdict(deque)
    for url, from_url, a_html in start_urls:
        if url not in visited and url not in queued:
            queue[start_depth].append((url, from_url, a_html))
            queued.add(url)
    for depth in range(start_depth, config.MAX_DEPTH + 1):
        while queue[depth]:
            url, from_url, a_html = queue[depth].popleft()
            log_status(depth, url, queue)
            link_map = await crawl_single_page(page, url, depth, from_url, a_html)
            for next_url, next_anchor in link_map.items():
                if next_url not in visited and next_url not in queued:
                    queue[depth + 1].append((next_url, url, next_anchor))
                    queued.add(next_url)


# === Main Entrypoint ===
async def main(start_urls, start_depth, visited_input, queued_input):
    global visited, queued
    visited = visited_input
    queued = queued_input
    os.makedirs(pw_config.user_data_dir, exist_ok=True)
    async with async_playwright() as p:
        context = await (
            p.chromium.launch_persistent_context(
                pw_config.user_data_dir,
                **pw_config.launch_options,
                **pw_config.context_options,
            )
            if config.USE_USER_DATA
            else (await p.chromium.launch(**pw_config.launch_options)).new_context(
                **pw_config.context_options
            )
        )
        page = context.pages[0] if context.pages else await context.new_page()

        if config.USE_USER_DATA and config.USE_USER_DATA_AND_LOGIN:
            if hasattr(config, "LOGIN_URL"):
                await page.goto(config.LOGIN_URL)
                await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR, timeout=600000)
            if hasattr(config, "LOGIN_URL2"):
                await page.goto(config.LOGIN_URL2)
                await page.wait_for_selector(config.LOGIN_WAIT_SELECTOR)

        await crawl_bfs(page, start_urls, start_depth)
        await context.close()


if __name__ == "__main__":
    if args.resume:
        visited, queued, max_depth = restore_state_from_csv(csv_path)
        start_depth = max_depth + 1
        start_urls = get_urls_to_resume(start_depth)
    else:
        visited, queued, start_depth = set(), set(), 0
        start_urls = [(url, "", "") for url in config.START_URLS]

    asyncio.run(main(start_urls, start_depth, visited, queued))
