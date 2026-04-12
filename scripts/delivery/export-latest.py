#!/usr/bin/env python3
"""
Export latest articles from DB as markdown for digest agent.

Queries articles from the last N hours with quality_score >= threshold,
groups by source_type, outputs markdown to stdout or file.

Usage:
    python3 export-latest.py
    python3 export-latest.py --hours 48 --min-score 4 --top-n 80
    python3 export-latest.py --output /tmp/articles.md
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_conn import get_conn

import re

EMOJI_RE = re.compile(
    "[\U00010000-\U0010ffff"   # supplementary planes (most emojis)
    "\U00002600-\U000027BF"   # misc symbols
    "\U0001F300-\U0001F9FF"   # emoticons, symbols
    "\u2700-\u27BF"           # dingbats
    "\uFE00-\uFE0F"           # variation selectors
    "\u200d"                  # zero-width joiner
    "]+",
    flags=re.UNICODE,
)

def strip_emoji(text: str) -> str:
    return EMOJI_RE.sub("", text).strip()


SOURCE_LABELS = {
    "github_trending": "GitHub Trending",
    "github":          "GitHub",
    "rss":             "RSS / Новости",
    "web":             "Web",
    "reddit":          "Reddit",
    "twitter":         "Twitter / X",
}

def fetch_articles(hours: int, min_score: float, top_n: int) -> list[dict]:
    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                title, link, snippet, quality_score,
                source_type, source_name, published_at
            FROM articles
            WHERE published_at > NOW() - INTERVAL '%s hours'
              AND quality_score >= %s
              AND (in_previous_digest IS NULL OR in_previous_digest = false)
            ORDER BY quality_score DESC
            LIMIT %s
        """, (hours, min_score, top_n))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        conn.close()


def render_markdown(articles: list[dict], hours: int) -> str:
    if not articles:
        return f"# Дайджест\n\nСтатей за последние {hours}ч не найдено.\n"

    # Group by source_type
    groups: dict[str, list] = {}
    for a in articles:
        key = a["source_type"] or "other"
        groups.setdefault(key, []).append(a)

    # Sort groups: github_trending first, then by count desc
    order = ["github_trending", "github", "rss", "web", "reddit", "twitter"]
    sorted_keys = sorted(groups.keys(), key=lambda k: (order.index(k) if k in order else 99, -len(groups[k])))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"# Digest — {now}",
        f"> Статьи за последние {hours}ч | Всего: {len(articles)} | Мин. скор: {articles[-1]['quality_score']:.1f}",
        "",
    ]

    for key in sorted_keys:
        label = SOURCE_LABELS.get(key, key.capitalize())
        group = groups[key]
        lines.append(f"## {label} ({len(group)})")
        lines.append("")

        for a in group:
            title = strip_emoji((a["title"] or "").strip())
            link  = (a["link"]  or "").strip()
            score = a["quality_score"]
            name  = strip_emoji(a["source_name"] or "")
            snip  = strip_emoji((a["snippet"] or "").strip())

            lines.append(f"### {title}")
            if link:
                lines.append(f"[{link}]({link})")
            meta_parts = [f"score: {score:.0f}"]
            if name:
                meta_parts.append(name)
            lines.append(f"> {' | '.join(meta_parts)}")
            if snip:
                lines.append("")
                lines.append(snip[:300])
            lines.append("")

    lines.append("---")
    lines.append(f"📊 Экспортировано: {now}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Export latest articles as markdown")
    parser.add_argument("--hours",     type=int,   default=24,  help="Window in hours (default: 24)")
    parser.add_argument("--min-score", type=float, default=6.0, help="Min quality_score (default: 6.0)")
    parser.add_argument("--top-n",     type=int,   default=100, help="Max articles to export (default: 100)")
    parser.add_argument("--output",    type=str,   default=None, help="Output file path (default: stdout)")
    args = parser.parse_args()

    articles = fetch_articles(args.hours, args.min_score, args.top_n)
    md = render_markdown(articles, args.hours)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"Exported {len(articles)} articles → {args.output}", file=sys.stderr)
    else:
        print(md)


if __name__ == "__main__":
    main()
