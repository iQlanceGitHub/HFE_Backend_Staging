import os

import httpx
import requests

from src.configs.config import EnvVar

API_KEY = os.environ.get(EnvVar.GoogleApiKey.value)


async def translate_text(text, source_lang="es", target_lang="en"):
    url = f"https://translation.googleapis.com/language/translate/v2?key={API_KEY}"

    payload = {
        "q": text,
        # 'source': source_lang,  # 'es' -> Spanish
        "target": target_lang,  # 'en' -> English
        # 'format': 'text'
    }

    response = requests.post(url, json=payload)

    if response.status_code == 200:
        translated_text = response.json()["data"]["translations"][0]["translatedText"]
        return translated_text
    else:
        return None


async def translate_fields(data, fields: list):
    if isinstance(data, str):
        return await translate_text(data)

    for field in fields:
        value = getattr(data, field, None)
        if value:
            if isinstance(value, list):
                translated_list = []
                for item in value:
                    translated_item = await translate_text(item)
                    translated_list.append(translated_item)
                setattr(data, field, translated_list)
            else:
                translated_value = await translate_text(value)
                setattr(data, field, translated_value)
    return data


async def translate_text_to_spanish(text, source_lang="en", target_lang="es"):
    url = f"https://translation.googleapis.com/language/translate/v2?key={API_KEY}"
    payload = {
        "q": text,
        "source": source_lang,
        "target": target_lang,
        "format": "text",
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload)

    if response.status_code == 200:
        return response.json()["data"]["translations"][0]["translatedText"]
    else:
        return text


async def translate_fields_to_spanish(data, fields: list):
    # Works with dict or object (like SQLAlchemy or Pydantic)
    def get_field_value(obj, field):
        try:
            return (
                obj.get(field) if isinstance(obj, dict) else getattr(obj, field, None)
            )
        except Exception:
            return None

    def set_field_value(obj, field, value):
        try:
            if isinstance(obj, dict):
                obj[field] = value
            else:
                setattr(obj, field, value)
        except Exception:
            pass

    for field in fields:
        value = get_field_value(data, field)
        if value:
            if isinstance(value, list):
                translated_list = [
                    await translate_text_to_spanish(item) for item in value
                ]
                set_field_value(data, field, translated_list)
            else:
                translated_value = await translate_text_to_spanish(value)
                set_field_value(data, field, translated_value)

    return data
