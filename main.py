"""
Morning SEC Digest
Pull yesterday’s 8-K, 13D/13G and DEF 14A filings,
summarize, and e-mail bullet list.
"""
import datetime, smtplib, ssl, yfinance as yf
from sec_api import QueryApi, Form13D13GApi
from email.mime.text import MIMEText
from config import *

YESTERDAY = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")

def fetch_filings(form_type: str):
    q = QueryApi(api_key=SEC_API_KEY)
    query = {
        "query": f"formType:\"{form_type}\" AND filedAt:[{YESTERDAY} TO {YESTERDAY}]",
        "from": "0", "size": "200", "sort": [{"filedAt": {"order": "desc"}}]
    }
    return q.get_filings()['filings']

def enrich(ticker: str) -> dict:
    """Return a tiny sentiment & magnitude estimate using yfinance."""
    tk = yf.Ticker(ticker)
    info = tk.info
    fwd = {"direction": "NEUTRAL", "magnitude": "±0–5%", "ticker": ticker.upper()}
    if not info: return fwd
    if info.get("recommendationMean", 3) < 2.5:
        fwd["direction"] = "BULLISH"
        fwd["magnitude"] = "+5–15%"
    elif info.get("recommendationMean", 3) > 3.5:
        fwd["direction"] = "BEARISH"
        fwd["magnitude"] = "–5–15%"
    return fwd

def build_summary():
    bullets = [f"SEC Morning Digest – {YESTERDAY}\n"]
    # 1. 8-K
    for f in fetch_filings("8-K"):
        ticker = f.get("ticker", f['entities'][0]['ticker'])
        headline = f.get("items", [""])[0] if f.get("items") else "Material event"
        meta = enrich(ticker)
        bullets.append(
            f"• {headline} | Form 8-K | {YESTERDAY} | {ticker} | "
            f"{meta['direction']} {meta['magnitude']} | "
            f"Trade: Buy-write on elevated vol or sell ATM puts if bullish."
        )
    # 2. 13D/13G
    g = Form13D13GApi(api_key=SEC_API_KEY)
    for f in g.get_filings({"filedAt": YESTERDAY})['filings']:
        ticker = f.get("tickers", [""])[0]
        if not ticker: continue
        meta = enrich(ticker)
        bullets.append(
            f"• {f['formType']} filing by {f['owners'][0]['name']} | "
            f"{YESTERDAY} | {ticker} | "
            f"{meta['direction']} {meta['magnitude']} | "
            f"Trade: Watch for follow-through; synthetic long via ATM call or short put spread."
        )
    # 3. DEF 14A
    for f in fetch_filings("DEF 14A"):
        ticker = f.get("ticker", f['entities'][0]['ticker'])
        meta = enrich(ticker)
        bullets.append(
            f"• Proxy statement / annual meeting | DEF 14A | {YESTERDAY} | {ticker} | "
            f"{meta['direction']} {meta['magnitude']} | "
            f"Trade: Read proxy for M&A risk; buy straddles if binary events likely."
        )
    return "\n".join(bullets)

def send_email(body: str):
    msg = MIMEText(body)
    msg["Subject"] = f"SEC Morning Digest – {YESTERDAY}"
    msg["From"] = EMAIL_USER
    msg["To"] = EMAIL_TO
    with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, EMAIL_TO, msg.as_string())

if __name__ == "__main__":
    digest = build_summary()
    if EMAIL_TO:
        send_email(digest)
    else:
        print(digest)  # fallback
