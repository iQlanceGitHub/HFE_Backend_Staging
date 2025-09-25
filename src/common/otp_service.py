import random

from pydantic import EmailStr

from src.common.email_service import send_email


def generate_otp(length=6):
    return str(random.randint(10 ** (length - 1), 10**length - 1))


async def send_otp(recipient: EmailStr, otp: str):
    subject = "Your OTP"
    body = f"Your OTP is: {otp}"
    await send_email(recipient, subject, body)
