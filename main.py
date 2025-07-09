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

# === Argument Setup ===
parser = argparse.ArgumentParser()
parser.add_argument("--resume", type=str, metavar="DIR", help="Resume crawl")
parser.add_argument("--retry", type=str, metavar="DIR", help="Retry ERROR rows")
args = parser.parse_args()

# === Global State ===
visited, queued = set(), set()


# === Utility Functions ===
def sanitize_url(url: str) -> str:
    return urldefrag(url)[0].strip()


def should_skip_extension(url: str) -> bool:
    return any(url.lower().endswith(ext) for ext in SKIP_EXTENSIONS)


def generate_case_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()


def save_html(path: str, html: str):
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


def load_html(path: str) -> str | None:
    return open(path, encoding="utf-8").read() if os.path.exists(path) else None


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
        if hasattr(config, "SKIP_LINK_KEYWORDS") and any(
            k in a.get_text(strip=True) for k in config.SKIP_LINK_KEYWORDS
        ):
            continue
        if urlparse(href).scheme in ["mailto", "tel", "javascript"]:
            continue
        joined_url = urljoin(actual_base, href)
        clean_url = sanitize_url(joined_url)
        if hasattr(config, "SKIP_URL_PATTERNS") and any(
            p in clean_url for p in config.SKIP_URL_PATTERNS
        ):
            continue
        if not any(
            urlparse(clean_url).netloc.endswith(d) for d in config.ALLOWED_DOMAINS
        ):
            continue
        if should_skip_extension(clean_url):
            continue
        if clean_url not in link_map:
            link_map[clean_url] = str(a)
    return link_map


def log_status(depth: int, url: str, queue: defaultdict[int, deque]):
    print(
        f"[depth={depth}] queue={len(queue[depth])} total_queue={sum(len(q) for q in queue.values())} visited={len(visited)} → {url}"
    )


def read_csv(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: str, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


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


# === Crawl Functions ===
async def crawl_single_page(
    page, url: str, depth: int, from_url="", from_anchor_html="", output_dir=""
) -> dict:
    case_id = generate_case_id(url)
    html_path = os.path.join(output_dir, "html", f"{case_id}.html")
    screenshot_path = os.path.join(output_dir, "screenshots", f"{case_id}.png")
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
        save_html(html_path, content)
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
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
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
            "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error_message": str(e),
            "anchor_html": from_anchor_html,
        }, {}


async def crawl_bfs(
    page, start_urls: list[tuple[str, str, str]], output_dir: str, start_depth=0
):
    queue = defaultdict(deque)
    for url, from_url, a_html in start_urls:
        if url not in visited and url not in queued:
            queue[start_depth].append((url, from_url, a_html))
            queued.add(url)

    all_rows = (
        read_csv(os.path.join(output_dir, "result.csv"))
        if os.path.exists(os.path.join(output_dir, "result.csv"))
        else []
    )
    for depth in range(start_depth, config.MAX_DEPTH + 1):
        while queue[depth]:
            url, from_url, a_html = queue[depth].popleft()
            log_status(depth, url, queue)
            row, link_map = await crawl_single_page(
                page, url, depth, from_url, a_html, output_dir
            )
            all_rows = [r for r in all_rows if r.get("url") != url]
            all_rows.append(row)
            for next_url, next_anchor in link_map.items():
                if next_url not in visited and next_url not in queued:
                    queue[depth + 1].append((next_url, url, next_anchor))
                    queued.add(next_url)
    write_csv(os.path.join(output_dir, "result.csv"), all_rows)


async def retry_errors(page, output_dir: str):
    rows = read_csv(os.path.join(output_dir, "result.csv"))
    error_rows = [r for r in rows if r.get("status_code") == "ERROR"]
    print(f"Retrying {len(error_rows)} error rows...")
    for row in error_rows:
        url = row["url"]
        new_row, _ = await crawl_single_page(
            page,
            url,
            int(row["depth"]),
            row["from_url"],
            row["anchor_html"],
            output_dir,
        )
        rows = [r for r in rows if r.get("url") != url]
        rows.append(new_row)
    write_csv(os.path.join(output_dir, "result.csv"), rows)


async def main():
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

        if args.retry:
            await retry_errors(page, args.retry)
        else:
            output_dir = args.resume or os.path.join(
                "results", datetime.now().strftime("%Y%m%d_%H%M%S")
            )
            os.makedirs(os.path.join(output_dir, "html"), exist_ok=True)
            os.makedirs(os.path.join(output_dir, "screenshots"), exist_ok=True)
            csv_path = os.path.join(output_dir, "result.csv")

            if args.resume:
                visited_set, _, max_depth = restore_state_from_csv(csv_path)
                start_depth = max_depth + 1
                start_urls = []
                with open(csv_path, "r", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        if int(row.get("depth", -1)) == max_depth:
                            html_path = os.path.join(
                                output_dir, "html", f"{row['case_id']}.html"
                            )
                            html = load_html(html_path)
                            if html:
                                for next_url, a_html in extract_unique_links(
                                    html, row["url"]
                                ).items():
                                    start_urls.append((next_url, row["url"], a_html))
                global visited, queued
                visited = visited_set
                queued = set()
            else:
                start_depth = 0
                start_urls = [(url, "", "") for url in config.START_URLS]

            await crawl_bfs(page, start_urls, output_dir, start_depth)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())
