import os
from dotenv import load_dotenv; load_dotenv()

SEC_API_KEY = os.getenv("SEC_API_KEY")
EMAIL_HOST  = os.getenv("EMAIL_HOST")   # e.g. smtp.gmail.com
EMAIL_PORT  = int(os.getenv("EMAIL_PORT", 587))
EMAIL_USER  = os.getenv("EMAIL_USER")
EMAIL_PASS  = os.getenv("EMAIL_PASS")
EMAIL_TO    = os.getenv("EMAIL_TO")
