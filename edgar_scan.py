#!/usr/bin/env python3
"""
EDGAR Morning Scan – 2025-09-03
Pulls yesterday’s 8-K / 13D / 13G / DEF 14A filings
and e-mails a concise bullet summary with company name + filing summary.
"""
import datetime as dt
import re
import requests
import smtplib
import ssl
from email.mime.text import MIMEText

from sec_api import QueryApi      # pip install sec-api
import yfinance as yf            # pip install yfinance
import openai                   # pip install openai>=1.0

from config import *             # SEC_API_KEY, MOONSHOT_API_KEY, SMTP_*, MAIL_TO

YESTERDAY = (dt.datetime.utcnow() - dt.timedelta(days=1)).strftime("%Y-%m-%d")

FORMS = {
    "8-K":      'formType:"8-K"',
    "13D/13G":  '(formType:"SC 13D" OR formType:"SC 13G")',
    "DEF 14A":  'formType:"DEF 14A"',
}

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; EDGAR-Scan/1.0)"}

# ------------------------------------------------------------------
# Helper – fetch filing text via SEC-API’s documentUrl
# ------------------------------------------------------------------
def _get_filing_text(url: str) -> str:
    """Return the first 2 KB of clean text from SEC-API documentUrl."""
    if not url:
        return ""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", r.text)
        return " ".join(text.split())[:2000]
    except Exception:
        return ""

# ------------------------------------------------------------------
# Helper – two-sentence summary via Moonshot
# ------------------------------------------------------------------
def _summarize(text: str) -> str:
    """Two-sentence plain-English summary via Moonshot."""
    if not text:
        return "Unable to retrieve filing text."

    prompt = (
        "Summarize the following SEC filing in two plain-English sentences. "
        "Highlight the key event and why it matters to investors:\n\n" + text
    )
    try:
        client = openai.OpenAI(
            api_key=MOONSHOT_API_KEY,
            base_url="https://api.moonshot.cn/v1"
        )
        resp = client.chat.completions.create(
            model="moonshot-v1-8k",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=80,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return "Summary unavailable."

# ------------------------------------------------------------------
# Helpers – SMTP + ticker extraction
# ------------------------------------------------------------------
def email_report(body: str):
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"EDGAR Scan – {YESTERDAY}"
    msg["From"] = SMTP_USER
    msg["To"] = MAIL_TO
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ssl.create_default_context()) as server:
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, MAIL_TO.split(","), msg.as_string())

def get_tickers_from_filing(filing: dict) -> list:
    tickers = []
    for f in filing.get("filers", []):
        if "ticker" in f:
            tickers.append(f["ticker"])
    if not tickers and "ticker" in filing:
        tickers.append(filing["ticker"])
    return list(set(tickers))

def quick_sentiment(ticker: str) -> str:
    try:
        tk = yf.Ticker(ticker)
        hist = tk.history(period="1y")
        iv = hist["Close"].pct_change().rolling(30).std().iloc[-1]
        iv_pct = iv / hist["Close"].pct_change().rolling(30).std().quantile(0.9)
        if iv_pct < 0.3:
            return "Small move expected"
        elif iv_pct < 0.6:
            return "Moderate move expected"
        else:
            return "Large move expected"
    except Exception:
        return "Direction unclear"

# ------------------------------------------------------------------
# Main build routine
# ------------------------------------------------------------------
def build_summary() -> str:
    api = QueryApi(api_key=SEC_API_KEY)
    bullets = []

    for form, query_str in FORMS.items():
        q = {
            "query": f"{query_str} AND filedAt:[{YESTERDAY}T00:00:00 TO {YESTERDAY}T23:59:59]",
            "from": "0",
            "size": "50",
            "sort": [{"filedAt": {"order": "desc"}}],
            "includeFields": ["companyName", "ticker", "formType", "filedAt", "documentUrl", "description", "items"]
        }
        hits = api.get_filings(q)

        for doc in hits.get("filings", []):
            # company name – fallback chain
            company_name = (
                doc.get("companyName")
                or (doc.get("issuers") or [{}])[0].get("name")
                or (doc.get("filers") or [{}])[0].get("name")
                or "n/a"
            )

            tickers = get_tickers_from_filing(doc)
            headline = doc.get("description") or doc.get("items", [""])[0] or "No headline"
            ticker_str = ", ".join(tickers) if tickers else "n/a"
            direction = quick_sentiment(tickers[0]) if tickers else "n/a"
            best_way = (
                "Consider short-dated ATM straddles for volatility, "
                "or directional equity/option plays if thesis is clear"
            )

            # SEC-API gives the raw document link in "documentUrl"
            filing_summary = _summarize(_get_filing_text(doc.get("documentUrl", "")))

            bullets.append(
                f"• {headline[:120]}…\n"
                f"  – Company: {company_name}\n"
                f"  – SEC form: {form}\n"
                f"  – Filing date: {doc['filedAt'][:10]}\n"
                f"  – Ticker(s): {ticker_str}\n"
                f"  – Filing summary: {filing_summary}\n"
                f"  – Likely 1-3 m move: {direction}\n"
                f"  – Best way to invest: {best_way}\n"
            )

    if not bullets:
        body = f"No 8-K, 13D/13G, or DEF 14A filings found for {YESTERDAY}."
    else:
        body = f"EDGAR scan for {YESTERDAY}:\n\n" + "\n".join(bullets)
    return body

# ------------------------------------------------------------------
if __name__ == "__main__":
    report = build_summary()
    email_report(report)
    print("Report sent.")
