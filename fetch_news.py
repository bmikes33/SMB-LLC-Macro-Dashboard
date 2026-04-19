#!/usr/bin/env python3
"""
SMB LLC News Pipeline
Hits TradingView's news API directly for headlines (includes Mace News,
Reuters, Dow Jones, Benzinga, etc). No third-party scraper library needed.
Sends to Claude for NEUTRAL macro framework summarization — regime is context,
not conclusion. Claude is explicitly instructed to surface contradictions.
Outputs news.json for the dashboard.
"""

import json
import os
import requests
from datetime import datetime, timezone, timedelta

# TradingView's internal news API endpoint
TV_NEWS_API = "https://news-headlines.tradingview.com/v2/view/headlines/symbol"

# Symbols to fetch news for
TV_SYMBOLS = [
    "AMEX:SPY", "NASDAQ:QQQ", "AMEX:DIA", "AMEX:IWM",
    "COINBASE:BTCUSD", "COINBASE:ETHUSD",
    "TVC:GOLD", "TVC:USOIL", "TVC:DXY",
    "TVC:US10Y", "TVC:US02Y", "TVC:VIX",
]

PROVIDER_COLORS = {
    "Mace News": "#e040fb",
    "Reuters": "#ff6d00", "reuters": "#ff6d00",
    "Dow Jones": "#ffab00", "Dow Jones Newswires": "#ffab00", "DowJones": "#ffab00",
    "MarketWatch": "#ffab00",
    "Benzinga": "#00e676", "benzinga": "#00e676",
    "Bloomberg": "#00e676",
    "CNBC": "#2196f3", "cnbc": "#2196f3",
    "Yahoo Finance": "#7c4dff",
    "Nasdaq": "#2196f3",
    "CoinDesk": "#f97316", "coindesk": "#f97316",
    "The Block": "#f97316", "Cointelegraph": "#f97316",
    "Barron's": "#ffab00", "barrons": "#ffab00",
    "Investor's Business Daily": "#ffab00",
    "GlobeNewsWire": "#8b9ab5", "PRNewsWire": "#8b9ab5",
    "AccessWire": "#8b9ab5", "BusinessWire": "#8b9ab5",
    "TradingView": "#00e5ff",
}


def load_latest_regime():
    """
    Read reports/index.json and return the latest macro report context.
    Returns None if no macro reports exist or file is missing/malformed.
    """
    try:
        with open("reports/index.json", "r") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"  No regime context available: {e}")
        return None

    reports = data.get("reports", [])
    macro_reports = [r for r in reports if r.get("type") == "macro"]
    if not macro_reports:
        print("  No macro reports in index.")
        return None

    macro_reports.sort(key=lambda r: r.get("date", ""), reverse=True)
    latest = macro_reports[0]
    print(f"  Latest regime: {latest.get('regime')} ({latest.get('regimeConfidence')}) as of {latest.get('date')}")
    return latest


def fetch_tradingview_news():
    """Fetch news from TradingView's headline API for multiple symbols."""
    articles = []
    seen_titles = set()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://www.tradingview.com",
        "Referer": "https://www.tradingview.com/",
    }

    for symbol in TV_SYMBOLS:
        try:
            print(f"  Fetching {symbol}...")
            params = {
                "client": "web",
                "lang": "en",
                "symbol": symbol,
                "count": 20,
            }

            resp = requests.get(TV_NEWS_API, params=params, headers=headers, timeout=15)

            if resp.status_code != 200:
                print(f"    HTTP {resp.status_code} for {symbol}")
                alt_url = f"https://news-headlines.tradingview.com/v2/view/headlines"
                params_alt = {
                    "client": "web",
                    "lang": "en",
                    "category": "base",
                    "symbol": symbol,
                    "count": 20,
                }
                resp = requests.get(alt_url, params=params_alt, headers=headers, timeout=15)
                if resp.status_code != 200:
                    print(f"    Alt endpoint also failed: HTTP {resp.status_code}")
                    continue

            data = resp.json()

            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("items", data.get("stories", data.get("data", data.get("astDescription", {}).get("items", []))))
                if not items and "storyPath" in str(data):
                    items = [data]

            count = 0
            for item in items[:20]:
                title = item.get("title", "") or item.get("headline", "") or item.get("text", "")
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                pub_time = datetime.now(timezone.utc)
                for time_field in ["published", "published_at", "publishedAt", "created", "timestamp"]:
                    ts = item.get(time_field)
                    if ts:
                        try:
                            if isinstance(ts, (int, float)):
                                pub_time = datetime.fromtimestamp(ts, tz=timezone.utc)
                            else:
                                pub_time = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                            break
                        except Exception:
                            continue

                if (datetime.now(timezone.utc) - pub_time) > timedelta(hours=24):
                    continue

                provider_raw = item.get("provider", item.get("source", {}))
                if isinstance(provider_raw, dict):
                    provider = provider_raw.get("name", provider_raw.get("title", "TradingView"))
                elif isinstance(provider_raw, str):
                    provider = provider_raw
                else:
                    provider = "TradingView"

                color = PROVIDER_COLORS.get(provider, "#00e5ff")

                story_path = item.get("storyPath", item.get("link", item.get("url", "")))
                if story_path and not story_path.startswith("http"):
                    link = f"https://www.tradingview.com{story_path}"
                else:
                    link = story_path or ""

                articles.append({
                    "title": title,
                    "source": provider,
                    "color": color,
                    "link": link,
                    "timestamp": pub_time.isoformat(),
                    "time_display": pub_time.strftime("%-I:%M %p") if os.name != "nt" else pub_time.strftime("%I:%M %p"),
                })
                count += 1

            print(f"    Got {count} articles")

        except Exception as e:
            print(f"    Error for {symbol}: {e}")
            continue

    articles.sort(key=lambda x: x["timestamp"], reverse=True)
    articles = articles[:75]
    print(f"\nTotal: {len(articles)} unique articles")
    return articles


def fetch_tradingview_news_fallback():
    """Fallback: scrape TradingView news page directly if API fails."""
    articles = []
    try:
        print("  Trying fallback: TradingView news page scrape...")
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        urls_to_try = [
            "https://news-headlines.tradingview.com/v2/view/headlines?client=web&lang=en&category=market&count=50",
            "https://news-headlines.tradingview.com/v2/view/headlines?client=web&lang=en&category=base&count=50",
            "https://www.tradingview.com/news-flow/",
        ]
        for url in urls_to_try:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/json"):
                    data = resp.json()
                    items = data if isinstance(data, list) else data.get("items", data.get("stories", []))
                    for item in items[:30]:
                        title = item.get("title", "") or item.get("headline", "")
                        if not title:
                            continue
                        provider_raw = item.get("provider", item.get("source", {}))
                        provider = provider_raw.get("name", "TradingView") if isinstance(provider_raw, dict) else str(provider_raw)
                        color = PROVIDER_COLORS.get(provider, "#00e5ff")
                        pub_time = datetime.now(timezone.utc)
                        articles.append({
                            "title": title,
                            "source": provider,
                            "color": color,
                            "link": "",
                            "timestamp": pub_time.isoformat(),
                            "time_display": pub_time.strftime("%-I:%M %p") if os.name != "nt" else pub_time.strftime("%I:%M %p"),
                        })
                    if articles:
                        print(f"    Fallback got {len(articles)} articles from {url}")
                        break
            except Exception as e:
                print(f"    Fallback failed for {url}: {e}")
                continue
    except Exception as e:
        print(f"  Fallback completely failed: {e}")
    return articles


def fetch_rss_fallback():
    """Last resort: RSS feeds if TradingView is completely blocked."""
    articles = []
    try:
        import feedparser
    except ImportError:
        print("  feedparser not installed, skipping RSS fallback")
        return articles

    feeds = [
        ("https://feeds.content.dowjones.io/public/rss/mw_topstories", "MarketWatch", "#ffab00"),
        ("https://feeds.reuters.com/reuters/businessNews", "Reuters", "#ff6d00"),
        ("https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114", "CNBC", "#2196f3"),
        ("https://www.federalreserve.gov/feeds/press_all.xml", "Fed", "#ff3d57"),
    ]
    for url, source, color in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:10]:
                title = entry.get("title", "").strip()
                if not title:
                    continue
                pub_time = datetime.now(timezone.utc)
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                if (datetime.now(timezone.utc) - pub_time) > timedelta(hours=24):
                    continue
                articles.append({
                    "title": title, "source": source, "color": color,
                    "link": entry.get("link", ""), "timestamp": pub_time.isoformat(),
                    "time_display": pub_time.strftime("%-I:%M %p") if os.name != "nt" else pub_time.strftime("%I:%M %p"),
                })
        except Exception as e:
            print(f"  RSS fallback failed for {source}: {e}")
    print(f"  RSS fallback got {len(articles)} articles")
    return articles


def build_prompt(articles, regime_context):
    """
    Construct the Claude prompt.
    regime_context: dict from latest macro report, or None if unavailable.

    Key design: regime is provided as CONTEXT only. Claude is explicitly instructed
    to evaluate news neutrally and actively surface contradictions — not confirm
    the regime call.
    """
    headline_text = "\n".join([f"[{a['source']}] {a['title']}" for a in articles[:35]])

    if regime_context:
        thresholds = regime_context.get("thresholds", [])
        # Show up to 8 most relevant thresholds
        threshold_lines = "\n".join([
            f"  - {t.get('indicator', '?')} {t.get('level', '?')}: {t.get('signal', '')}"
            for t in thresholds[:8]
        ])

        regime_block = f"""CURRENT REGIME CONTEXT (from last macro analysis):
- Regime: {regime_context.get('regime', 'Unknown')} ({regime_context.get('regimeConfidence', 'UNKNOWN')} confidence)
- As of: {regime_context.get('date', 'unknown')}
- Equity bias: {regime_context.get('equityBias', 'N/A')}
- Primary tension: {regime_context.get('primaryTension', 'N/A')}
- Invalidation thresholds to watch:
{threshold_lines}

CRITICAL INSTRUCTION: The regime above is the most recent Claude-generated classification. It may be stale or wrong. Your job is NOT to confirm this regime. Evaluate each headline on its own merits. Actively surface evidence that contradicts the regime or approaches an invalidation threshold. If the news in aggregate challenges the regime call, say so directly and plainly. Do not soften contradictory news to preserve the thesis."""
    else:
        regime_block = """NO RECENT REGIME CONTEXT AVAILABLE. Summarize the news in neutral terms without a regime lens."""

    prompt = f"""You are a macro research analyst for SMB LLC, a trading operation using:
- Lifecycle-stage equity analysis (Young Growth → High Growth → Mature Growth → Maturity → Decline)
- Multi-timeframe TA (21 EMA, 50 SMA, 200 SMA, MACD, RSI)
- John Murphy intermarket analysis framework
- A BMNR (ETH-linked trust) cash-secured put ladder strategy

{regime_block}

HEADLINES (last 24 hours):

{headline_text}

Respond in JSON format ONLY — no markdown, no backticks, no preamble:
{{
  "macroSummary": "2-3 neutral sentences describing what the headlines collectively say. Do not frame through the regime lens; just summarize what's happening.",
  "regimePressure": "REINFORCING | MIXED | PRESSURING | CHALLENGING",
  "regimePressureReason": "One sentence explaining the pressure call. Be direct — if news challenges the regime, say so.",
  "thresholdWatches": [
    {{"indicator": "VIX", "level": "> 22", "signal": "One-line article-derived observation"}}
  ],
  "keySignals": [
    {{"signal": "One-sentence signal summary", "tag": "SUPPORTS | CONTRADICTS | NEUTRAL | THRESHOLD_WATCH"}}
  ],
  "actionItems": ["Up to 3 items for current positions (BMNR ladder, short book, Maturity overweight, etc.)"]
}}

Rules:
- regimePressure: REINFORCING = broadly confirms regime, MIXED = split evidence, PRESSURING = noticeable contradictions emerging, CHALLENGING = regime call likely stale or wrong.
- thresholdWatches: empty array if no article approaches a threshold. Do not fabricate.
- keySignals: 3-5 entries, prioritize CONTRADICTS and THRESHOLD_WATCH over SUPPORTS.
- Tag each keySignal honestly. Do not tag CONTRADICTS as NEUTRAL to protect the regime call.
- actionItems: can be empty array if no clear actions."""
    return prompt


def summarize_with_claude(articles, regime_context):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "macroSummary": "AI summary unavailable — no API key.",
            "regimePressure": "N/A",
            "regimePressureReason": "",
            "thresholdWatches": [],
            "keySignals": [],
            "actionItems": [],
        }

    prompt = build_prompt(articles, regime_context)

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(text)

        # Normalize — ensure all expected fields exist even if Claude omits them
        return {
            "macroSummary": parsed.get("macroSummary", ""),
            "regimePressure": parsed.get("regimePressure", "N/A"),
            "regimePressureReason": parsed.get("regimePressureReason", ""),
            "thresholdWatches": parsed.get("thresholdWatches", []),
            "keySignals": parsed.get("keySignals", []),
            "actionItems": parsed.get("actionItems", []),
        }
    except Exception as e:
        print(f"Warning: Claude summary failed: {e}")
        return {
            "macroSummary": f"Summary failed: {str(e)[:100]}",
            "regimePressure": "N/A",
            "regimePressureReason": "",
            "thresholdWatches": [],
            "keySignals": [],
            "actionItems": [],
        }


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting news fetch...\n")

    # Load current regime for context
    print("Loading regime context...")
    regime_context = load_latest_regime()
    print()

    # Fetch news
    articles = fetch_tradingview_news()

    if not articles:
        print("\nPrimary API returned no results. Trying fallback...")
        articles = fetch_tradingview_news_fallback()

    if not articles:
        print("\nFallback also empty. Trying RSS as last resort...")
        articles = fetch_rss_fallback()

    if not articles:
        print("\nAll methods failed. Writing empty news.json.")
        with open("news.json", "w") as f:
            json.dump({
                "lastUpdated": datetime.now(timezone.utc).isoformat(),
                "lastUpdatedDisplay": datetime.now(timezone.utc).strftime("%b %d, %Y — %I:%M %p UTC"),
                "articleCount": 0,
                "currentRegime": regime_context.get("regime") if regime_context else None,
                "currentRegimeColor": regime_context.get("regimeColor") if regime_context else None,
                "regimeConfidence": regime_context.get("regimeConfidence") if regime_context else None,
                "regimeAsOf": regime_context.get("date") if regime_context else None,
                "summary": {
                    "macroSummary": "All news sources failed. Check GitHub Action logs.",
                    "regimePressure": "N/A",
                    "regimePressureReason": "",
                    "thresholdWatches": [],
                    "keySignals": [],
                    "actionItems": [],
                },
                "articles": [],
            }, f, indent=2)
        return

    # Summarize with Claude
    print("\nGenerating Claude macro summary...")
    summary = summarize_with_claude(articles, regime_context)
    print(f"Summary: {summary.get('macroSummary', 'N/A')[:120]}...")
    print(f"Regime pressure: {summary.get('regimePressure', 'N/A')}")

    # Write output
    output = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "lastUpdatedDisplay": datetime.now(timezone.utc).strftime("%b %d, %Y — %I:%M %p UTC"),
        "articleCount": len(articles),
        # Dashboard-visible regime context: which regime was in Claude's context when this summary ran
        "currentRegime": regime_context.get("regime") if regime_context else None,
        "currentRegimeColor": regime_context.get("regimeColor") if regime_context else None,
        "regimeConfidence": regime_context.get("regimeConfidence") if regime_context else None,
        "regimeAsOf": regime_context.get("date") if regime_context else None,
        "summary": summary,
        "articles": [
            {
                "title": a["title"],
                "source": a["source"],
                "color": a["color"],
                "timestamp": a["timestamp"],
                "timeDisplay": a["time_display"],
                "link": a["link"],
            }
            for a in articles
        ],
    }
    with open("news.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nDone. {len(articles)} articles written to news.json")


if __name__ == "__main__":
    main()
