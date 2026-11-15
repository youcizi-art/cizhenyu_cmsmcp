"""Public site tech probes (no CMS cookie required)."""

from __future__ import annotations

import urllib.error
import urllib.request
from typing import Any


def _fetch_text(url: str) -> tuple[int, str]:
    req = urllib.request.Request(
        url,
        headers={"Accept": "text/html,application/xml,text/plain,*/*", "User-Agent": "cizhenyu-cmsmcp/0.6"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            return res.status, res.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"请求失败 {url}: {e}") from None


def crawl_fetch(args: dict[str, Any]) -> dict[str, Any]:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        raise ValueError("crawl_fetch 需要 url")
    status, body = _fetch_text(url.strip())
    return {
        "status": status,
        "url": url.strip(),
        "length": len(body),
        "sample": body[:4000],
    }


def tech_robots(origin: str) -> dict[str, Any]:
    url = f"{origin.rstrip('/')}/robots.txt"
    status, body = _fetch_text(url)
    ok = status == 200 and bool(body.strip())
    return {"ok": ok, "status": status, "sample": body[:400]}


def tech_sitemap(origin: str) -> dict[str, Any]:
    origin = origin.rstrip("/")
    robots = ""
    try:
        _, robots = _fetch_text(f"{origin}/robots.txt")
    except Exception:
        robots = ""
    urls: list[str] = []
    for line in robots.splitlines():
        t = line.strip()
        if t.lower().startswith("sitemap:"):
            u = t[8:].strip()
            if u:
                urls.append(u)
    if not urls:
        urls.append(f"{origin}/sitemap.xml")

    count = 0
    ok = False
    issues: list[str] = []
    for sm in urls[:3]:
        try:
            status, body = _fetch_text(sm)
            if status == 200 and ("<urlset" in body or "<sitemapindex" in body):
                ok = True
                count += min(body.count("<loc>"), 200)
            else:
                issues.append(f"{sm} HTTP {status}")
        except Exception as e:  # noqa: BLE001
            issues.append(str(e))
    return {"ok": ok, "urlCount": count, "issues": issues}


def tech_home(origin: str) -> dict[str, Any]:
    url = f"{origin.rstrip('/')}/"
    status, body = _fetch_text(url)
    ok = 200 <= status < 400 and bool(body)
    title = ""
    lower = body.lower()
    start = lower.find("<title>")
    if start >= 0:
        after = body[start + 7 :]
        end = after.lower().find("</title>")
        if end >= 0:
            title = after[:end].strip()[:120]
    return {"ok": ok, "status": status, "titleHint": title}
