import os,httpx
from pydantic import EmailStr
from src.common.logger import Logger

logger = Logger()


# Gmail Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
GMAIL_USERNAME = "testemail20012025@gmail.com"
GMAIL_PASSWORD = "pgts meql cmle ahrd"


MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
MAILGUN_SENDER = f"Mailgun Sandbox <postmaster@{MAILGUN_DOMAIN}>"



async def send_email(recipient: EmailStr, subject: str, body: str):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}/messages",
                auth=("api", MAILGUN_API_KEY),
                data={
                    "from": MAILGUN_SENDER,  
                    "to": [recipient],
                    "subject": subject,
                    "html": body,
                },
            )

        if response.status_code == 200:
            logger.log_info("Email sent successfully via Mailgun.")
        else:
            logger.log_error(f"Mailgun send error: {response.status_code} - {response.text}")
        return response.status_code == 200
    
    except httpx.RequestError as e:
        logger.log_error(f"Request error while sending email: {e}")
    except Exception as e:
        logger.log_error(f"Unexpected exception during email sending: {e}")
