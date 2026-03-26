#!/usr/bin/env python3
"""
Store merged/scored articles from JSON into Postgres.

Reads the output of merge-sources.py and inserts articles into the
'articles' table, updating 'seen_urls' for cross-run deduplication.

Usage:
    python3 store-merged.py --input /tmp/td-merged.json --pipeline-run-id 1
"""

import json
import sys
import argparse
import logging
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

# Allow importing db_conn from same directory
sys.path.insert(0, str(Path(__file__).parent))
from db_conn import get_conn

try:
    import psycopg2.extras
except ImportError:
    print("Error: psycopg2 is required. Install with: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)


def normalize_url(url: str) -> str:
    """Normalize URL for dedup (same logic as merge-sources.py)."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")
        path = parsed.path.rstrip("/")
        return f"{domain}{path}"
    except Exception:
        return url


def store_articles(conn, pipeline_run_id: int, merged_data: dict) -> int:
    """Insert merged articles into Postgres. Returns count of inserted rows."""
    topics = merged_data.get("topics", {})
    rows = []

    for topic_id, topic_data in topics.items():
        for article in topic_data.get("articles", []):
            link = article.get("link", "")
            normalized = normalize_url(link)
            published_at = article.get("date")

            rows.append((
                pipeline_run_id,
                article.get("title", ""),
                link,
                normalized,
                published_at,
                article.get("source_type", ""),
                article.get("source_id"),
                article.get("source_name"),
                article.get("primary_topic") or topic_id,
                article.get("all_topics") or article.get("topics") or [topic_id],
                article.get("quality_score", 0),
                article.get("snippet"),
                json.dumps(article.get("metrics")) if article.get("metrics") else None,
                article.get("multi_source", False),
                article.get("source_count", 1),
                article.get("all_sources"),
                article.get("full_text"),
                article.get("full_text_method"),
                article.get("in_previous_digest", False),
                json.dumps(article),
            ))

    if not rows:
        return 0

    insert_sql = """
        INSERT INTO articles (
            pipeline_run_id, title, link, normalized_url, published_at,
            source_type, source_id, source_name, primary_topic, all_topics,
            quality_score, snippet, metrics, multi_source, source_count,
            all_sources, full_text, full_text_method, in_previous_digest, raw_json
        ) VALUES %s
        ON CONFLICT (pipeline_run_id, normalized_url) DO NOTHING
    """

    template = (
        "(%(pipeline_run_id)s, %(title)s, %(link)s, %(normalized_url)s, %(published_at)s, "
        "%(source_type)s, %(source_id)s, %(source_name)s, %(primary_topic)s, %(all_topics)s, "
        "%(quality_score)s, %(snippet)s, %(metrics)s::jsonb, %(multi_source)s, %(source_count)s, "
        "%(all_sources)s, %(full_text)s, %(full_text_method)s, %(in_previous_digest)s, %(raw_json)s::jsonb)"
    )

    # Convert tuples to dicts for execute_values with template
    dict_rows = []
    for r in rows:
        dict_rows.append({
            "pipeline_run_id": r[0], "title": r[1], "link": r[2],
            "normalized_url": r[3], "published_at": r[4], "source_type": r[5],
            "source_id": r[6], "source_name": r[7], "primary_topic": r[8],
            "all_topics": r[9], "quality_score": r[10], "snippet": r[11],
            "metrics": r[12], "multi_source": r[13], "source_count": r[14],
            "all_sources": r[15], "full_text": r[16], "full_text_method": r[17],
            "in_previous_digest": r[18], "raw_json": r[19],
        })

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur, insert_sql, dict_rows, template=template, page_size=100
        )

    conn.commit()
    return len(rows)


def update_seen_urls(conn, merged_data: dict):
    """Upsert normalized URLs into seen_urls for cross-run dedup."""
    urls = []
    for topic_data in merged_data.get("topics", {}).values():
        for article in topic_data.get("articles", []):
            link = article.get("link", "")
            normalized = normalize_url(link)
            title = article.get("title", "")
            urls.append((normalized, title))

    if not urls:
        return

    with conn.cursor() as cur:
        for normalized, title in urls:
            cur.execute("""
                INSERT INTO seen_urls (normalized_url, best_title)
                VALUES (%s, %s)
                ON CONFLICT (normalized_url) DO UPDATE SET
                    last_seen_at = NOW(),
                    times_seen = seen_urls.times_seen + 1
            """, (normalized, title))

    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Store merged articles in Postgres")
    parser.add_argument("--input", type=Path, required=True, help="Path to merged JSON")
    parser.add_argument("--pipeline-run-id", type=int, required=True, help="Pipeline run ID")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not args.input.exists():
        logging.error(f"Input file not found: {args.input}")
        sys.exit(1)

    with open(args.input, "r", encoding="utf-8") as f:
        merged_data = json.load(f)

    conn = get_conn()
    try:
        count = store_articles(conn, args.pipeline_run_id, merged_data)
        logging.info(f"Stored {count} articles for pipeline run {args.pipeline_run_id}")

        update_seen_urls(conn, merged_data)
        logging.info("Updated seen_urls for cross-run dedup")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
