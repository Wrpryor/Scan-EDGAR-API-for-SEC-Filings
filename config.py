import os
from dotenv import load_dotenv
load_dotenv()

SEC_API_KEY      = os.getenv("SEC_API_KEY")
SMTP_SERVER      = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT        = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER        = os.getenv("SMTP_USER")
SMTP_PASS        = os.getenv("SMTP_PASS")
MAIL_TO          = os.getenv("MAIL_TO")
