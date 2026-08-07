#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fulltext.py —— 全文提取层。读 ../data.js，对每条新闻抓取原文全文（trafilatura），
失败时用 RSS summary 兜底。写回 data.js 的 content 字段。
需要 trafilatura + bs4（用 GP venv 运行）。
"""
import json, os, re, sys, time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA_FILE = os.path.join(ROOT, "data.js")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
CONTENT_MAX = 3000
MIN_CONTENT_LEN = 200
WORKERS = 8
TIMEOUT = 20

try:
    import trafilatura
    HAS_TRAFILATURA = True
except ImportError:
    HAS_TRAFILATURA = False
    print("⚠️ trafilatura 未安装，将只用 RSS 摘要兜底")

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


def strip_html(s):
    if not s:
        return ""
    if HAS_BS4:
        try:
            return BeautifulSoup(s, "html.parser").get_text(separator=" ", strip=True)
        except Exception:
            pass
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def fetch_url(url):
    """Fetch a URL and return HTML text."""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*",
        })
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception:
        return ""


def extract_content(url, summary=""):
    """Extract full text from a URL. Returns (content, method)."""
    if not url:
        return strip_html(summary)[:CONTENT_MAX] if summary else "", "summary"

    html = fetch_url(url)
    if not html:
        return strip_html(summary)[:CONTENT_MAX] if summary else "", "summary"

    # Try trafilatura first
    if HAS_TRAFILATURA:
        try:
            text = trafilatura.extract(html, include_comments=False, include_tables=False)
            if text and len(text) >= MIN_CONTENT_LEN:
                return text[:CONTENT_MAX], "trafilatura"
        except Exception:
            pass

    # Fallback: try common article selectors with bs4
    if HAS_BS4:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for sel in ["article", ".article__content", ".article-content",
                        ".post-content", ".entry-content", ".content-detail",
                        ".article-detail", "main", ".content"]:
                el = soup.select_one(sel)
                if el:
                    text = el.get_text(separator="\n", strip=True)
                    if len(text) >= MIN_CONTENT_LEN:
                        return text[:CONTENT_MAX], "bs4"
        except Exception:
            pass

    # Last resort: RSS summary
    cleaned = strip_html(summary)
    if cleaned:
        return cleaned[:CONTENT_MAX], "summary"
    return "", "none"


def is_cjk(text):
    """Check if text is predominantly CJK."""
    if not text:
        return False
    sample = text[:500]
    cjk = sum(1 for c in sample if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
    return cjk / max(len(sample), 1) > 0.3


def process_item(item):
    """Extract content for a single item. Mutates item dict."""
    url = item.get("url", "")
    summary = item.get("summary", "")

    # Skip if already has good content
    existing = item.get("content", "")
    if existing and len(existing) >= MIN_CONTENT_LEN:
        return "skip"

    content, method = extract_content(url, summary)
    if content:
        item["content"] = content
        item["_extract_method"] = method
        return method
    return "none"


def main():
    # Read data.js
    txt = open(DATA_FILE, encoding="utf-8").read()
    data = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])

    # Collect all items
    all_items = []
    for ind in data.get("industries", []):
        for item in ind.get("items", []):
            all_items.append(item)

    total = len(all_items)
    need_extract = [it for it in all_items
                    if not it.get("content") or len(it.get("content", "")) < MIN_CONTENT_LEN]
    print(f"全文提取：共 {total} 条，需提取 {len(need_extract)} 条")

    if not need_extract:
        print("无需提取，跳过")
        return

    # Parallel extraction
    stats = {"trafilatura": 0, "bs4": 0, "summary": 0, "none": 0, "skip": 0}
    done = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futures = {ex.submit(process_item, it): it for it in need_extract}
        for future in as_completed(futures):
            try:
                method = future.result()
                stats[method] = stats.get(method, 0) + 1
            except Exception as e:
                stats["none"] += 1
            done += 1
            if done % 50 == 0:
                print(f"  进度: {done}/{len(need_extract)}")

    # Write back
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        f.write("// data.js —— 含全文提取。\n")
        f.write("window.DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")

    has_content = sum(1 for it in all_items if it.get("content") and len(it["content"]) >= MIN_CONTENT_LEN)
    print(f"全文提取完成：{has_content}/{total} 条有内容")
    print(f"  trafilatura: {stats.get('trafilatura', 0)}, bs4: {stats.get('bs4', 0)}, "
          f"summary兜底: {stats.get('summary', 0)}, 失败: {stats.get('none', 0)}")


if __name__ == "__main__":
    main()
