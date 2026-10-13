from __future__ import annotations

import hashlib
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import frontmatter
import markdown

from app.config import settings

MD = markdown.Markdown(extensions=["extra", "sane_lists", "tables", "nl2br"])


def _news_dir() -> Path:
    return Path(settings.news_dir)


def _slug(path: Path, meta: dict[str, Any]) -> str:
    if meta.get("id"):
        return str(meta["id"])
    return path.stem


def _parse_one(path: Path) -> dict[str, Any]:
    post = frontmatter.load(path)
    meta = dict(post.metadata)
    MD.reset()
    html = MD.convert(post.content or "")
    published = meta.get("published") or meta.get("date")
    if isinstance(published, datetime):
        published_s = published.date().isoformat()
        published_dt = published
    elif published:
        published_s = str(published)
        try:
            published_dt = datetime.fromisoformat(published_s)
        except ValueError:
            published_dt = datetime.fromtimestamp(path.stat().st_mtime)
    else:
        published_dt = datetime.fromtimestamp(path.stat().st_mtime)
        published_s = published_dt.date().isoformat()

    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    digest = hashlib.sha1(path.read_bytes()).hexdigest()[:10]
    return {
        "id": _slug(path, meta),
        "title": meta.get("title") or path.stem,
        "title_en": meta.get("title_en"),
        "summary": meta.get("summary") or "",
        "category": meta.get("category") or "资讯",
        "tags": tags,
        "author": meta.get("author") or "AetherWatch Desk",
        "source": meta.get("source"),
        "source_url": meta.get("source_url"),
        "published": published_s,
        "published_at": published_dt.isoformat(),
        "lang": meta.get("lang") or "zh",
        "html": html,
        "hash": digest,
        "word_count": len(post.content or ""),
    }


@lru_cache(maxsize=8)
def _load_all(stamp: int) -> list[dict[str, Any]]:
    directory = _news_dir()
    if not directory.exists():
        return []
    items = []
    for path in sorted(directory.glob("*.md")):
        try:
            items.append(_parse_one(path))
        except Exception:
            continue
    items.sort(key=lambda x: x.get("published") or "", reverse=True)
    return items


def list_articles() -> list[dict[str, Any]]:
    directory = _news_dir()
    stamp = int(directory.stat().st_mtime) if directory.exists() else 0
    articles = _load_all(stamp)
    return [{k: v for k, v in a.items() if k != "html"} for a in articles]


def get_article(article_id: str) -> dict[str, Any] | None:
    directory = _news_dir()
    stamp = int(directory.stat().st_mtime) if directory.exists() else 0
    for article in _load_all(stamp):
        if article["id"] == article_id:
            return article
    return None
