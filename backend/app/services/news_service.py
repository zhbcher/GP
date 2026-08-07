"""Industry news service: RSS fetch + full-text extraction + AI translation + per-sector daily digest.

Pipeline: RSS → parse → fetch full text → translate (batch) → persist → per-sector daily digest.
Stores 7 days of data in SQLite. Layout: sector (left nav) × date (tabs).
"""
import asyncio
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import trafilatura
from bs4 import BeautifulSoup
from sqlalchemy import select, delete, func

from app.config import get_settings
from app.db import async_session_maker
from app.models.news import NewsItem, NewsDigest

logger = logging.getLogger(__name__)
settings = get_settings()

# Load sources config
_SOURCES_FILE = Path(__file__).parent.parent / "news_sources.json"
_sources_config: dict = {}
if _SOURCES_FILE.exists():
    with open(_SOURCES_FILE) as f:
        _sources_config = json.load(f)

SECTORS = sorted(set(s.get("hint", "other") for s in _sources_config.get("sources", [])))
REDLINE_KEYWORDS = _sources_config.get("redline_keywords", [])

# Beijing timezone
_BJT = timezone(timedelta(hours=8))

# State
_last_fetch_time: float = 0
_fetch_lock = asyncio.Lock()
_refreshing = False

# AI config
AI_PROVIDER = settings.news_ai_provider
_digest_key = getattr(settings, "news_ai_" + "api_key")
AI_BASE_URL = settings.news_ai_base_url
AI_MODEL = settings.news_ai_model

# Concurrency
_content_sem = asyncio.Semaphore(10)
CONTENT_MAX_CHARS = 3000
MIN_CONTENT_LEN = 200  # below this, content is considered missing
_browser_sem = asyncio.Semaphore(2)  # browser extraction is heavy, low concurrency
_browser_instance = None  # lazy singleton playwright browser


# ── Helpers ──────────────────────────────────────────────────────────────

def _is_redlined(title: str) -> bool:
    return any(kw.lower() in title.lower() for kw in REDLINE_KEYWORDS)


def _is_cjk(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for c in text[:500] if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
    return cjk / min(len(text), 500) > 0.3


def _parse_pub_date(date_str: str) -> str:
    if not date_str:
        return datetime.now(_BJT).strftime("%Y-%m-%d")
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo:
                dt = dt.astimezone(_BJT)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    m = re.search(r'(\d{4}-\d{2}-\d{2})', date_str)
    return m.group(1) if m else datetime.now(_BJT).strftime("%Y-%m-%d")


# ── RSS Parsing ──────────────────────────────────────────────────────────

def _parse_rss(xml_text: str, source_name: str, sector: str) -> list[dict]:
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        desc = (item.findtext("description") or "").strip()
        if title and not _is_redlined(title):
            items.append({
                "title": title, "link": link, "date": pub_date,
                "summary": desc[:300] if desc else "",
                "source": source_name, "sector": sector,
                "published_at": _parse_pub_date(pub_date),
            })

    if not items:
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry in root.findall(".//atom:entry", ns):
            title = (entry.findtext("atom:title", namespaces=ns) or "").strip()
            link_el = entry.find("atom:link", ns)
            link = link_el.get("href", "") if link_el is not None else ""
            updated = (entry.findtext("atom:updated", namespaces=ns) or "").strip()
            summary = (entry.findtext("atom:summary", namespaces=ns) or "").strip()
            if title and not _is_redlined(title):
                items.append({
                    "title": title, "link": link, "date": updated,
                    "summary": summary[:300] if summary else "",
                    "source": source_name, "sector": sector,
                    "published_at": _parse_pub_date(updated),
                })

    return items[:10]


# ── Fetch Pipeline ───────────────────────────────────────────────────────

async def _fetch_one_source(client: httpx.AsyncClient, source: dict) -> list[dict]:
    url = source.get("url", "")
    name = source.get("name", "unknown")
    sector = source.get("hint", "other")
    if source.get("type", "rss") != "rss" or not url:
        return []
    try:
        resp = await client.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return []
        return _parse_rss(resp.text, name, sector)
    except Exception:
        return []


async def _fetch_full_text(client: httpx.AsyncClient, item: dict) -> None:
    link = item.get("link", "")
    if not link:
        return
    async with _content_sem:
        try:
            resp = await client.get(link, timeout=15, follow_redirects=True)
            if resp.status_code == 200:
                text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
                if text and len(text) >= MIN_CONTENT_LEN:
                    item["content"] = text[:CONTENT_MAX_CHARS]
        except Exception:
            pass


def _clean_html(html: str) -> str:
    """Strip HTML tags from RSS summary, return plain text."""
    if not html:
        return ""
    try:
        text = BeautifulSoup(html, "lxml").get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text).strip()
    except Exception:
        return re.sub(r"<[^>]+>", "", html).strip()


async def _get_browser():
    """Lazy singleton playwright chromium browser (with anti-detection args)."""
    global _browser_instance
    if _browser_instance is None:
        from playwright.async_api import async_playwright
        pw = await async_playwright().start()
        _browser_instance = (pw, await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        ))
    return _browser_instance[1]


async def _browser_extract(link: str) -> str:
    """Render a JS page with headless chromium and extract article text."""
    async with _browser_sem:
        page = None
        try:
            browser = await _get_browser()
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="zh-CN",
            )
            # Mask webdriver flag
            await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            page = await ctx.new_page()
            await page.goto(link, timeout=25000, wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)  # let JS render
            text = await page.evaluate("""() => {
                const selectors = ['.article__content', '.article-content', '.article__inner',
                    '.post-content', '.entry-content', '.content-detail', '.article-detail',
                    'article', '.content', 'main', '[class*="article"]', '[class*="content"]'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText && el.innerText.length > 200) return el.innerText;
                }
                return document.body.innerText || '';
            }""")
            await ctx.close()
            return (text or "").strip()
        except Exception as e:
            logger.debug(f"browser extract failed for {link}: {e}")
            return ""
        finally:
            if page:
                try:
                    await page.close()
                except Exception:
                    pass


async def browser_backfill_pass(max_items: int = 120):
    """Background pass: use browser to extract content for items still missing it.
    Runs after main refresh, low concurrency to avoid OOM."""
    if not AI_PROVIDER:  # reuse the gate loosely; browser works regardless but keep cheap
        pass
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(NewsItem).where(
                NewsItem.link != "",
                (NewsItem.content == "") | (NewsItem.content.is_(None)) |
                (func.length(NewsItem.content) < MIN_CONTENT_LEN),
            ).order_by(NewsItem.fetched_at.desc()).limit(max_items)
        )).scalars().all()
        targets = [(r.id, r.link) for r in rows]

    if not targets:
        logger.info("[news] Browser backfill: nothing to do")
        return

    logger.info(f"[news] Browser backfill: {len(targets)} items to extract")
    filled = 0
    async with async_session_maker() as session:
        for item_id, link in targets:
            text = await _browser_extract(link)
            if text and len(text) >= MIN_CONTENT_LEN:
                row = (await session.execute(
                    select(NewsItem).where(NewsItem.id == item_id)
                )).scalar_one_or_none()
                if row:
                    row.content = text[:CONTENT_MAX_CHARS]
                    filled += 1
            await asyncio.sleep(0.2)
        await session.commit()
    logger.info(f"[news] Browser backfill done: {filled}/{len(targets)} extracted")


async def _translate_backfill_pass(max_items: int = 120):
    """Translate DB items that have content but no content_zh (non-CJK only)."""
    if not AI_PROVIDER or not _digest_key:
        return
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(NewsItem).where(
                NewsItem.content != "",
                (NewsItem.content_zh == "") | (NewsItem.content_zh.is_(None)),
            ).order_by(NewsItem.fetched_at.desc()).limit(max_items)
        )).scalars().all()
        # Filter non-CJK only
        targets = [r for r in rows if not _is_cjk(r.title)]

    if not targets:
        logger.info("[news] Translate backfill: nothing to do")
        return

    logger.info(f"[news] Translate backfill: {len(targets)} items")
    done = 0
    # Batch by 3 (same as content translation)
    for i in range(0, len(targets), 3):
        batch = targets[i:i + 3]
        parts = []
        for j, row in enumerate(batch):
            body = (row.content or row.summary or "")[:1200]
            parts.append(f"[{j+1}] 标题：{row.title}\n正文：{body}")
        prompt = f"将以下{len(batch)}条英文新闻翻译为中文。每条格式：\n标题翻译：xxx\n正文翻译：xxx（300字内摘要）\n用 --- 分隔每条。\n\n" + "\n\n".join(parts)
        text = await _ai_call(prompt, max_tokens=3000, timeout=120)
        if not text:
            continue
        blocks = re.split(r'\n-{3,}\n', text)
        async with async_session_maker() as session:
            for j, block in enumerate(blocks):
                if j >= len(batch):
                    break
                tm = re.search(r'标题翻译[：:]\s*(.+)', block)
                cm = re.search(r'正文翻译[：:]\s*([\s\S]+)', block)
                row = (await session.execute(
                    select(NewsItem).where(NewsItem.id == batch[j].id)
                )).scalar_one_or_none()
                if row:
                    if tm:
                        row.title_zh = tm.group(1).strip()
                    if cm:
                        row.content_zh = cm.group(1).strip()[:1500]
                        done += 1
            await session.commit()
        await asyncio.sleep(0.5)
    logger.info(f"[news] Translate backfill done: {done}/{len(targets)} translated")


# ── Translation (batch, during refresh) ──────────────────────────────────

async def _ai_call(prompt: str, max_tokens: int = 2000, timeout: int = 90) -> str:
    """Single AI API call, returns response text or empty string."""
    if not AI_PROVIDER or not _digest_key:
        return ""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {_digest_key}", "Content-Type": "application/json"},
                json={"model": AI_MODEL, "messages": [{"role": "user", "content": prompt}],
                      "temperature": 0.2, "max_tokens": max_tokens},
            )
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                return msg.get("content") or msg.get("reasoning") or ""
    except Exception as e:
        logger.warning(f"AI call failed: {e}")
    return ""


async def _translate_titles_batch(items: list[dict]) -> None:
    """Translate up to 20 titles at once."""
    entries = [(i, it) for i, it in enumerate(items) if not _is_cjk(it.get("title", "")) and it.get("title")]
    if not entries:
        return
    numbered = "\n".join(f"{j+1}. {it['title']}" for j, (_, it) in enumerate(entries))
    text = await _ai_call(f"将以下英文新闻标题翻译为中文，保持编号，每行一条：\n\n{numbered}", max_tokens=2000, timeout=60)
    for line in text.strip().split("\n"):
        m = re.match(r'^(\d+)[.、)]\s*(.+)', line.strip())
        if m:
            idx = int(m.group(1)) - 1
            if 0 <= idx < len(entries):
                entries[idx][1]["title_zh"] = m.group(2).strip()


async def _translate_content_batch(items: list[dict]) -> None:
    """Translate title+content for up to 3 non-CJK items with extracted content."""
    entries = [(i, it) for i, it in enumerate(items)
               if not _is_cjk(it.get("title", "")) and (it.get("content") or it.get("summary"))]
    if not entries:
        return

    parts = []
    for j, (_, it) in enumerate(entries):
        title = it.get("title", "")
        body = (it.get("content") or it.get("summary", ""))[:1200]
        parts.append(f"[{j+1}] 标题：{title}\n正文：{body}")

    prompt = f"将以下{len(entries)}条英文新闻翻译为中文。每条格式：\n标题翻译：xxx\n正文翻译：xxx（300字内摘要）\n用 --- 分隔每条。\n\n" + "\n\n".join(parts)

    text = await _ai_call(prompt, max_tokens=3000, timeout=120)
    if not text:
        return

    blocks = re.split(r'\n-{3,}\n', text)
    for j, block in enumerate(blocks):
        if j >= len(entries):
            break
        idx_in_items = entries[j][0]
        tm = re.search(r'标题翻译[：:]\s*(.+)', block)
        cm = re.search(r'正文翻译[：:]\s*([\s\S]+)', block)
        if tm:
            items[idx_in_items]["title_zh"] = tm.group(1).strip()
        if cm:
            items[idx_in_items]["content_zh"] = cm.group(1).strip()[:1500]


# ── Persistence ──────────────────────────────────────────────────────────

async def _persist_news(all_items: list[dict]):
    cutoff = datetime.utcnow() - timedelta(days=7)
    async with async_session_maker() as session:
        await session.execute(delete(NewsItem).where(NewsItem.fetched_at < cutoff))
        for item in all_items:
            stmt = select(NewsItem).where(
                NewsItem.title == item["title"],
                NewsItem.source == item.get("source", ""),
            ).limit(1)
            row = (await session.execute(stmt)).scalar_one_or_none()
            if row:
                # Fill content: prefer extracted, fallback to summary
                if item.get("content") and not row.content:
                    row.content = item["content"]
                elif not row.content and item.get("summary"):
                    row.content = item["summary"]
                if item.get("content_zh") and not row.content_zh:
                    row.content_zh = item["content_zh"]
                if item.get("title_zh") and not row.title_zh:
                    row.title_zh = item["title_zh"]
                if item.get("published_at") and not row.published_at:
                    row.published_at = item["published_at"]
            else:
                session.add(NewsItem(
                    sector=item.get("sector", "other"),
                    title=item["title"],
                    title_zh=item.get("title_zh", ""),
                    link=item.get("link", ""),
                    date=item.get("date", ""),
                    published_at=item.get("published_at", ""),
                    summary=item.get("summary", ""),
                    content=item.get("content", ""),
                    content_zh=item.get("content_zh", ""),
                    source=item.get("source", ""),
                ))
        await session.commit()


# ── Per-Sector Daily Digest ──────────────────────────────────────────────

async def _generate_sector_digest(sector: str, date_str: str, items: list[dict]):
    """Generate AI digest for a sector+date. Today = regenerate; past = idempotent."""
    if not AI_PROVIDER or not _digest_key or not items:
        return

    today = datetime.now(_BJT).strftime("%Y-%m-%d")

    async with async_session_maker() as session:
        if date_str != today:
            existing = (await session.execute(
                select(NewsDigest).where(NewsDigest.sector == sector, NewsDigest.date == date_str)
            )).scalar_one_or_none()
            if existing:
                return

    lines = []
    for item in items[:30]:
        t = item.get("title_zh") or item.get("title", "")
        lines.append(f"- {t}")

    prompt = f"""以下是{date_str}「{sector}」板块的资讯标题（共{len(items)}条）：

{chr(10).join(lines)}

请用中文提炼3-5条要点，每条一句话，突出关键公司和数据。格式：
1. xxx
2. xxx
..."""

    text = await _ai_call(prompt, max_tokens=1000, timeout=120)
    points = re.findall(r'^\d+\.\s*(.+)$', text, re.MULTILINE)[:5]
    if not points:
        return

    async with async_session_maker() as session:
        existing = (await session.execute(
            select(NewsDigest).where(NewsDigest.sector == sector, NewsDigest.date == date_str)
        )).scalar_one_or_none()
        if existing:
            existing.points = json.dumps(points, ensure_ascii=False)
            existing.updated_at = datetime.utcnow()
        else:
            session.add(NewsDigest(sector=sector, date=date_str, points=json.dumps(points, ensure_ascii=False)))
        await session.commit()
    logger.info(f"Digest {sector}/{date_str}: {len(points)} points")


# ── Main Refresh Pipeline ────────────────────────────────────────────────

async def fetch_all_sources() -> list[dict]:
    """Full pipeline: RSS → full text → translate → persist → per-sector digest."""
    global _last_fetch_time, _refreshing

    async with _fetch_lock:
        _refreshing = True
        try:
            sources = _sources_config.get("sources", [])
            if not sources:
                return []

            logger.info(f"[news] Fetching {len(sources)} RSS sources...")
            async with httpx.AsyncClient(
                headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"},
                follow_redirects=True,
            ) as client:
                # 1. Fetch RSS
                all_items: list[dict] = []
                for i in range(0, len(sources), 20):
                    batch = sources[i:i + 20]
                    results = await asyncio.gather(
                        *[_fetch_one_source(client, s) for s in batch],
                        return_exceptions=True,
                    )
                    for r in results:
                        if isinstance(r, list):
                            all_items.extend(r)
                    await asyncio.sleep(0.3)

                logger.info(f"[news] RSS done: {len(all_items)} items. Fetching full text...")

                # 2. Fetch full text (all items with links, semaphore controls concurrency)
                to_fetch = [it for it in all_items if it.get("link")]
                await asyncio.gather(
                    *[_fetch_full_text(client, it) for it in to_fetch],
                    return_exceptions=True,
                )
                has_content = sum(1 for it in all_items if it.get("content"))
                logger.info(f"[news] Full text done: {has_content}/{len(to_fetch)} extracted")

                # 2b. Fallback: use cleaned RSS summary as content when full text extraction failed
                for it in all_items:
                    if not it.get("content") and it.get("summary"):
                        cleaned = _clean_html(it["summary"])
                        if cleaned:
                            it["content"] = cleaned

            # 3. Translate titles (batch of 20)
            non_cjk = [it for it in all_items if not _is_cjk(it.get("title", ""))]
            for i in range(0, len(non_cjk), 20):
                await _translate_titles_batch(non_cjk[i:i + 20])
                await asyncio.sleep(0.3)
            translated_titles = sum(1 for it in all_items if it.get("title_zh"))
            logger.info(f"[news] Title translation done: {translated_titles} items")

            # 4. Translate content (batch of 3, only items with extracted content)
            with_content = [it for it in all_items if it.get("content") and not _is_cjk(it.get("title", ""))]
            for i in range(0, len(with_content), 3):
                await _translate_content_batch(with_content[i:i + 3])
                await asyncio.sleep(0.5)
            translated_content = sum(1 for it in all_items if it.get("content_zh"))
            logger.info(f"[news] Content translation done: {translated_content} items")

            # 5. Persist
            await _persist_news(all_items)
            logger.info(f"[news] Persisted to DB")
            _last_fetch_time = time.time()

            # 6. Per-sector daily digests
            by_sector_date: dict[tuple[str, str], list[dict]] = {}
            for item in all_items:
                d = item.get("published_at", "")
                s = item.get("sector", "other")
                if d:
                    by_sector_date.setdefault((s, d), []).append(item)

            today = datetime.now(_BJT).strftime("%Y-%m-%d")
            for (sector, date_str), day_items in sorted(by_sector_date.items()):
                # Only generate for today + yesterday to limit AI calls
                if date_str >= (datetime.now(_BJT) - timedelta(days=1)).strftime("%Y-%m-%d"):
                    await _generate_sector_digest(sector, date_str, day_items)
                    await asyncio.sleep(0.5)

            # 7. Browser backfill: extract content for items trafilatura missed (JS-rendered pages)
            try:
                await browser_backfill_pass(max_items=120)
                # 7b. Translate newly-extracted non-CJK content that lacks translation
                await _translate_backfill_pass(max_items=120)
            except Exception as e:
                logger.warning(f"[news] Browser backfill pass failed: {e}")

            logger.info(f"[news] Refresh complete: {len(all_items)} items")
            return all_items

        finally:
            _refreshing = False


def trigger_refresh():
    asyncio.create_task(fetch_all_sources())


# ── Query API (sector × date) ────────────────────────────────────────────

async def get_sectors() -> list[dict]:
    """Return all sectors with total item counts (last 7 days)."""
    cutoff = (datetime.now(_BJT) - timedelta(days=7)).strftime("%Y-%m-%d")
    async with async_session_maker() as session:
        rows = (await session.execute(
            select(NewsItem.sector, func.count(NewsItem.id))
            .where(NewsItem.published_at >= cutoff)
            .group_by(NewsItem.sector)
        )).all()
    result = [{"sector": r[0], "count": r[1]} for r in rows]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result


async def get_sector_days(sector: str) -> list[dict]:
    """Return last 7 days with item counts for a specific sector."""
    today = datetime.now(_BJT)
    days = []
    async with async_session_maker() as session:
        for i in range(7):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            count = (await session.execute(
                select(func.count(NewsItem.id)).where(
                    NewsItem.sector == sector, NewsItem.published_at == d
                )
            )).scalar() or 0
            digest_row = (await session.execute(
                select(NewsDigest.points).where(
                    NewsDigest.sector == sector, NewsDigest.date == d
                )
            )).scalar_one_or_none()
            days.append({"date": d, "count": count, "has_digest": bool(digest_row)})
    return days


async def get_sector_day(sector: str, date_str: str) -> dict:
    """Get news items + digest for a specific sector+date."""
    async with async_session_maker() as session:
        digest_row = (await session.execute(
            select(NewsDigest.points).where(
                NewsDigest.sector == sector, NewsDigest.date == date_str
            )
        )).scalar_one_or_none()
        digest = json.loads(digest_row) if digest_row else []

        stmt = select(NewsItem).where(
            NewsItem.sector == sector, NewsItem.published_at == date_str
        ).order_by(NewsItem.fetched_at.desc())
        rows = (await session.execute(stmt)).scalars().all()

        items = [{
            "id": row.id,
            "sector": row.sector,
            "title": row.title,
            "title_zh": row.title_zh or "",
            "link": row.link,
            "date": row.date,
            "summary": row.summary,
            "content": row.content or "",
            "content_zh": row.content_zh or "",
            "source": row.source,
        } for row in rows]

    return {"sector": sector, "date": date_str, "digest": digest, "items": items}


# ── Startup ──────────────────────────────────────────────────────────────

async def load_news_on_startup():
    """Verify DB has data; log stats."""
    try:
        async with async_session_maker() as session:
            total = (await session.execute(select(func.count(NewsItem.id)))).scalar() or 0
            sectors = (await session.execute(
                select(func.count(func.distinct(NewsItem.sector)))
            )).scalar() or 0
        if total:
            logger.info(f"News DB: {total} items across {sectors} sectors")
    except Exception as e:
        logger.warning(f"News DB check failed: {e}")


def is_refreshing() -> bool:
    return _refreshing


def get_all_sectors() -> list[str]:
    return SECTORS
