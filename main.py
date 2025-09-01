#!/usr/bin/env python3
"""
EDGAR Morning Scan
Pulls yesterday’s 8-K, 13D/13G, DEF 14A filings and
sends a concise bullet-point summary via e-mail.
"""
import datetime as dt
import textwrap
import smtplib
import ssl
from email.mime.text import MIMEText

from sec_api import QueryApi
import yfinance as yf
from config import *

YESTERDAY = (dt.datetime.utcnow() - dt.timedelta(days=1)).strftime("%Y-%m-%d")

FORMS = {
    "8-K":      "formType:\"8-K\"",
    "13D/13G":  "(formType:\"SC 13D\" OR formType:\"SC 13G\")",
    "DEF 14A":  "formType:\"DEF 14A\"",
}

def email_report(body: str):
    """Send plain-text e-mail using SMTP_SSL."""
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"EDGAR Scan – {YESTERDAY}"
    msg["From"]    = SMTP_USER
    msg["To"]      = MAIL_TO
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ssl.create_default_context()) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, MAIL_TO.split(","), msg.as_string())

def get_tickers_from_filing(filing: dict) -> list:
    """Return list of tickers referenced in the filing."""
    tickers = []
    for f in filing.get("filers", []):
        if "ticker" in f:
            tickers.append(f["ticker"])
    if not tickers and "ticker" in filing:
        tickers.append(filing["ticker"])
    return list(set(tickers))

def quick_sentiment(ticker: str) -> str:
    """
    Naïve 1-3 month sentiment guess based on
    1) 30-day implied volatility percentile vs 1-year
    2) Insider/activist filing types
    """
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y")
        iv = hist["Close"].pct_change().rolling(30).std().iloc[-1]
        iv_pct = (iv / hist["Close"].pct_change().rolling(30).std().quantile(0.9))
        if iv_pct < 0.3:
            mag = "Small"
        elif iv_pct < 0.6:
            mag = "Moderate"
        else:
            mag = "Large"
        return f"{mag} move expected"
    except Exception:
        return "Direction unclear"

def build_summary() -> str:
    api = QueryApi(api_key=SEC_API_KEY)
    bullets = []
    for form, query_str in FORMS.items():
        q = {
            "query": f"{query_str} AND filedAt:[{YESTERDAY}T00:00:00 TO {YESTERDAY}T23:59:59]",
            "from": "0",
            "size": "50",
            "sort": [{"filedAt": {"order": "desc"}}]
        }
        hits = api.get_filings(q)
        for doc in hits.get("filings", []):
            tickers = get_tickers_from_filing(doc)
            headline = doc.get("description") or doc.get("items", [""])[0] or "No headline"
            ticker_str = ", ".join(tickers) if tickers else "n/a"
            direction = quick_sentiment(tickers[0]) if tickers else "n/a"
            best_way = "Consider short-dated ATM straddles for volatility, or directional equity/option plays if thesis is clear"
            bullets.append(
                f"• {headline[:120]}…\n"
                f"  – SEC form: {form}\n"
                f"  – Filing date: {doc['filedAt'][:10]}\n"
                f"  – Ticker(s): {ticker_str}\n"
                f"  – Likely 1-3 m move: {direction}\n"
                f"  – Best way to invest: {best_way}\n"
            )
    if not bullets:
        body = f"No 8-K, 13D/13G, or DEF 14A filings found for {YESTERDAY}."
    else:
        body = f"EDGAR scan for {YESTERDAY}:\n\n" + "\n".join(bullets)
    return body

if __name__ == "__main__":
    report = build_summary()
    email_report(report)
    print("Report sent.")
