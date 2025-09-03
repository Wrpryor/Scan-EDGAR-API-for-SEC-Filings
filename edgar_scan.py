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
import re
import requests
from email.mime.text import MIMEText

from sec_api import QueryApi
import yfinance as yf
import openai  # pip install openai>=1.0

from config import *

YESTERDAY = (dt.datetime.utcnow() - dt.timedelta(days=1)).strftime("%Y-%m-%d")

FORMS = {
    "8-K":      'formType:"8-K"',
    "13D/13G":  '(formType:"SC 13D" OR formType:"SC 13G")',
    "DEF 14A":  'formType:"DEF 14A"',
}

# ------------------------------------------------------------
# Helpers for company name + filing summary  (Moonshot)
# ------------------------------------------------------------
def _get_filing_text(accession_no: str, cik: str, ticker: str = "") -> str:
    """
    Returns the first ~30 KB of clean text from the actual filing.
    Falls back to ticker→CIK lookup if CIK missing.
    """
    if not cik or not accession_no:
        if ticker:
            try:
                tk = yf.Ticker(ticker)
                cik = str(tk.get_info().get("cik")).zfill(10)
            except Exception as e:
                print("DEBUG ticker→CIK failed:", e)
                return ""
        if not cik or not accession_no:
            print("DEBUG: missing cik or accession_no")
            return ""

    cik_stripped = cik.lstrip("0")
    acc_clean = accession_no.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik_stripped}/{acc_clean}/{accession_no}-index.htm"
    print("DEBUG built URL:", url)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; EDGAR-Scan/1.0)"}
    try:
        idx_resp = requests.get(url, headers=headers, timeout=10)
        idx_resp.raise_for_status()
        links = re.findall(r'href="(/Archives/edgar/data/.*?\.htm)"', idx_resp.text)
        if not links:
            print("DEBUG: no .htm link found on index page")
            return ""
        doc_url = f"https://www.sec.gov{links[0]}"
        print("DEBUG doc URL:", doc_url)
        doc_resp = requests.get(doc_url, headers=headers, timeout=10)
        doc_resp.raise_for_status()
        text = re.sub(r"<[^>]+>", " ", doc_resp.text)
        cleaned = " ".join(text.split())[:1500]
        print("DEBUG cleaned text len:", len(cleaned))
        return cleaned
    except Exception as e:
        print("DEBUG filing-text error:", e)
        return ""

def _summarize(text: str) -> str:
    if not text:
        return "Unable to retrieve filing text."

    prompt = (
        "Summarize the following SEC filing in two plain-English sentences, "
        "highlighting what changed and why it matters to investors:\n\n" + text
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
    except Exception as e:
        return f"Summary unavailable ({e})."

# ------------------------------------------------------------
# unchanged helper functions
# ------------------------------------------------------------
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

# ------------------------------------------------------------
# build_summary with safe extraction + debug prints
# ------------------------------------------------------------
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
            # ------------- DEBUG ------
            print("DEBUG: companyName=", repr(doc.get("companyName")),
                  "cik=", repr(doc.get("cik")),
                  "accessionNo=", repr(doc.get("accessionNo")),
                  "issuers=", repr(doc.get("issuers")))
            # --------------------------

            cik = (
                doc.get("cik") or
                (doc.get("filers") or [{}])[0].get("cik", "")
            )
            accession_no = (
                doc.get("accessionNo") or
                (doc.get("filers") or [{}])[0].get("accessionNo", "")
            )

            company_name = (
                doc.get("companyName") or
                (doc.get("issuers") or [{}])[0].get("name") or
                (doc.get("filers") or [{}])[0].get("name") or
                "n/a"
            )

            tickers = get_tickers_from_filing(doc)
            headline = doc.get("description") or doc.get("items", [""])[0] or "No headline"
            ticker_str = ", ".join(tickers) if tickers else "n/a"
            direction = quick_sentiment(tickers[0]) if tickers else "n/a"
            best_way = (
                "Consider short-dated ATM straddles for volatility, "
                "or directional equity/option plays if thesis is clear"
            )

            filing_summary = _summarize(
                _get_filing_text(accession_no, cik, tickers[0] if tickers else "")
            )

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

if __name__ == "__main__":
    report = build_summary()
    email_report(report)
    print("Report sent.")
