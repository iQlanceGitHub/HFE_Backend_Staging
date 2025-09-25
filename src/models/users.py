import os
import requests
from dotenv import load_dotenv
load_dotenv()

stripe_api_key = os.environ.get("STRIPE_API_KEY")

url = "https://api.stripe.com/v1/prices"
headers = {
    "Authorization": f"Bearer {stripe_api_key}"
}
response = requests.get(url, headers=headers)
