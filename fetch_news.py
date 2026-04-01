#!/usr/bin/env python3
"""
SMB LLC News Pipeline
Scrapes TradingView News Flow for all macro headlines (includes Mace News,
Reuters, Dow Jones, Benzinga, Bloomberg, CNBC, etc.)
Sends to Claude for macro framework summarization.
Outputs news.json for the dashboard.
"""

import json
import os
from datetime import datetime, timezone, timedelta

TV_SYMBOLS = [
    ("SPY", "AMEX"),
    ("QQQ", "NASDAQ"),
    ("DIA", "AMEX"),
    ("IWM", "AMEX"),
    ("BTCUSD", "COINBASE"),
    ("ETHUSD", "COINBASE"),
    ("XAUUSD", "TVC"),
    ("USOIL", "TVC"),
    ("DXY", "TVC"),
    ("US10Y", "TVC"),
    ("US02Y", "TVC"),
    ("VIX", "TVC"),
]

PROVIDER_COLORS = {
    "Mace News": "#e040fb",
    "Reuters": "#ff6d00",
    "Dow Jones": "#ffab00",
    "Dow Jones Newswires": "#ffab00",
    "MarketWatch": "#ffab00",
    "Benzinga": "#00e676",
    "Bloomberg": "#00e676",
    "CNBC": "#2196f3",
    "Yahoo Finance": "#7c4dff",
    "Nasdaq": "#2196f3",
    "CoinDesk": "#f97316",
    "The Block": "#f97316",
    "Cointelegraph": "#f97316",
    "Barron's": "#ffab00",
    "Investor's Business Daily": "#ffab00",
    "GlobeNewsWire": "#8b9ab5",
    "PRNewsWire": "#8b9ab5",
    "AccessWire": "#8b9ab5",
    "BusinessWire": "#8b9ab5",
}


def fetch_tradingview_news():
    articles = []
    seen_titles = set()
    try:
        from tradingview_scraper.symbols.news import NewsScraper
        scraper = NewsScraper(export_result=False)
        for symbol, exchange in TV_SYMBOLS:
            try:
                print(f"  Fetching {exchange}:{symbol}...")
                result = scraper.scrape_headlines(symbol=symbol, exchange=exchange, sort="latest")
                if not result or "data" not in result:
                    continue
                count = 0
                for item in result["data"][:20]:
                    title = item.get("title", "") or item.get("text", "")
                    if not title or title in seen_titles:
                        continue
                    seen_titles.add(title)
                    pub_time = datetime.now(timezone.utc)
                    created = item.get("published", "") or item.get("created", "")
                    if created:
                        try:
                            pub_time = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                        except Exception:
                            try:
                                pub_time = datetime.fromtimestamp(float(created), tz=timezone.utc)
                            except Exception:
                                pass
                    if (datetime.now(timezone.utc) - pub_time) > timedelta(hours=24):
                        continue
                    provider_raw = item.get("provider", {})
                    if isinstance(provider_raw, dict):
                        provider = provider_raw.get("name", "TradingView")
                    elif isinstance(provider_raw, str):
                        provider = provider_raw
                    else:
                        provider = "TradingView"
                    color = PROVIDER_COLORS.get(provider, "#00e5ff")
                    story_path = item.get("storyPath", "")
                    link = f"https://www.tradingview.com{story_path}" if story_path else item.get("url", "")
                    articles.append({
                        "title": title, "source": provider, "color": color,
                        "link": link, "timestamp": pub_time.isoformat(),
                        "time_display": pub_time.strftime("%-I:%M %p"),
                    })
                    count += 1
                print(f"    Got {count} new articles from {symbol}")
            except Exception as e:
                print(f"    Warning: Failed for {symbol}: {e}")
                continue
        articles.sort(key=lambda x: x["timestamp"], reverse=True)
        articles = articles[:75]
        print(f"\nTotal: {len(articles)} unique articles from TradingView News Flow")
    except ImportError:
        print("ERROR: tradingview-scraper not installed")
    except Exception as e:
        print(f"ERROR: TradingView news fetch failed: {e}")
    return articles


def summarize_with_claude(articles):
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"macroSummary": "AI summary unavailable — no API key.", "regimeImpact": "N/A", "actionItems": [], "keySignals": []}
    headline_text = "\n".join([f"[{a['source']}] {a['title']}" for a in articles[:35]])
    prompt = f"""You are a macro research analyst for SMB LLC, a trading operation that uses:
- Lifecycle-stage analysis (Young Growth > High Growth > Mature Growth > Maturity > Decline)
- Multi-timeframe technical analysis (21 EMA, 50 SMA, 200 SMA, MACD, RSI)
- John Murphy intermarket analysis framework
- A BMNR (ETH-linked trust) cash-secured put ladder strategy

Current regime: Bear Market — Oversold Relief Rally. Key levels:
- SPY 200 SMA at 662 (below = bear), VIX 25 regime line, HYG $80 credit threshold
- BTC $62,300 BMNR structural level, Oil above $100 = stagflation
- MOVE above 100 = bond stress, 10Y above 4.50% = growth stress
- Apr 2 tariff deadline = next binary catalyst

Here are the latest headlines from TradingView News Flow:

{headline_text}

Respond in JSON format ONLY (no markdown, no backticks, no preamble):
{{"macroSummary": "2-3 sentence summary of what these headlines mean for the current macro regime", "regimeImpact": "One sentence: does anything change the bear market relief rally assessment?", "actionItems": ["Up to 3 items for current positions (BMNR ladder, short book, Maturity overweight)"], "keySignals": ["Up to 4 most important signals, each 1 sentence"]}}"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(model="claude-sonnet-4-20250514", max_tokens=600, messages=[{"role": "user", "content": prompt}])
        text = response.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        print(f"Warning: Claude summary failed: {e}")
        return {"macroSummary": f"Summary failed: {str(e)[:100]}", "regimeImpact": "N/A", "actionItems": [], "keySignals": []}


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting news fetch...")
    print(f"Scraping TradingView News Flow for {len(TV_SYMBOLS)} symbols...\n")
    articles = fetch_tradingview_news()
    if not articles:
        print("No articles fetched.")
        with open("news.json", "w") as f:
            json.dump({"lastUpdated": datetime.now(timezone.utc).isoformat(), "lastUpdatedDisplay": datetime.now(timezone.utc).strftime("%b %d, %Y — %-I:%M %p UTC"), "articleCount": 0, "summary": {"macroSummary": "No articles available.", "regimeImpact": "N/A", "actionItems": [], "keySignals": []}, "articles": []}, f, indent=2)
        return
    print("\nGenerating Claude macro summary...")
    summary = summarize_with_claude(articles)
    print(f"Summary: {summary.get('macroSummary', 'N/A')[:100]}...")
    output = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "lastUpdatedDisplay": datetime.now(timezone.utc).strftime("%b %d, %Y — %-I:%M %p UTC"),
        "articleCount": len(articles),
        "summary": summary,
        "articles": [{"title": a["title"], "source": a["source"], "color": a["color"], "timestamp": a["timestamp"], "timeDisplay": a["time_display"], "link": a["link"]} for a in articles],
    }
    with open("news.json", "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nDone. {len(articles)} articles written to news.json")


if __name__ == "__main__":
    main()
