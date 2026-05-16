import json
import os
import time
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, render_template, url_for

from serpapi import GoogleSearch

load_dotenv()

app = Flask(__name__)

CACHE_FILE = Path(__file__).parent / "news_cache.json"
CACHE_TTL_SECONDS = 86400  # 24 hours
SEARCH_QUERY = "FIRST Robotics OR FIRST ROBOTICS COMPETITION OR FIRST LEGO LEAGUE OR FIRST TECH CHALLENGE"


# ── Cache helpers ──────────────────────────────────────────────────────────────


def _load_cache() -> dict:
    """Return cached data or an empty structure if the cache file is missing."""
    if CACHE_FILE.exists():
        try:
            with CACHE_FILE.open() as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"timestamp": 0, "articles": []}


def _save_cache(articles: list[dict]) -> None:
    with CACHE_FILE.open("w") as f:
        json.dump({"timestamp": time.time(), "articles": articles}, f, indent=2)


def _cache_is_fresh(cache: dict) -> bool:
    return (time.time() - cache.get("timestamp", 0)) < CACHE_TTL_SECONDS


# ── SerpAPI fetch ──────────────────────────────────────────────────────────────


def _normalize_article(raw: dict) -> dict:
    """Extract and normalize fields from a SerpAPI news result entry."""
    source = raw.get("source", {})
    source_name = source.get("name", "") if isinstance(source, dict) else str(source)

    thumbnail = raw.get("thumbnail", "")
    # Some results nest the thumbnail under a stories sub-key
    if not thumbnail and raw.get("stories"):
        thumbnail = raw["stories"][0].get("thumbnail", "")

    return {
        "title": raw.get("title", "Untitled"),
        "link": raw.get("link", "#"),
        "source": source_name or "Unknown",
        "date": raw.get("date", ""),
        "snippet": raw.get("snippet", ""),
        "thumbnail": thumbnail,
    }


def fetch_news() -> tuple[list[dict], str | None]:
    """
    Fetch news articles from SerpAPI Google News.
    Returns (articles, error_message).  error_message is None on success.
    """
    api_key = os.environ.get("SERPAPI_KEY", "")
    if not api_key or api_key == "your_key_here":
        return [], "SERPAPI_KEY is not set. Add your key to serpapi/.env."

    try:
        search = GoogleSearch(
            {
                "engine": "google_news",
                "q": SEARCH_QUERY,
                "hl": "en",
                "gl": "us",
                "api_key": api_key,
            }
        )
        results = search.get_dict()
    except Exception as exc:
        return [], f"SerpAPI request failed: {exc}"

    raw_articles = results.get("news_results", [])
    articles = [_normalize_article(a) for a in raw_articles]
    return articles, None


# ── Routes ─────────────────────────────────────────────────────────────────────


@app.route("/")
def index():
    cache = _load_cache()
    error = None

    if _cache_is_fresh(cache) and cache["articles"]:
        articles = cache["articles"]
    else:
        articles, error = fetch_news()
        if articles:
            _save_cache(articles)

    last_updated = ""
    if cache.get("timestamp"):
        import datetime

        last_updated = datetime.datetime.fromtimestamp(cache["timestamp"]).strftime(
            "%b %d, %Y at %I:%M %p"
        )

    return render_template(
        "index.html",
        articles=articles,
        last_updated=last_updated,
        error=error,
    )


@app.route("/refresh")
def refresh():
    """Force-expire the cache, then redirect to the main feed."""
    if CACHE_FILE.exists():
        # Zero out the timestamp so the next request triggers a fresh fetch
        try:
            with CACHE_FILE.open() as f:
                data = json.load(f)
            data["timestamp"] = 0
            with CACHE_FILE.open("w") as f:
                json.dump(data, f)
        except (json.JSONDecodeError, OSError):
            CACHE_FILE.unlink(missing_ok=True)
    return redirect(url_for("index"))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
