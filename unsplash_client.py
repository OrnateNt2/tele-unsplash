import httpx
import logging
from config import UNSPLASH_ACCESS_KEY

BASE_URL = "https://api.unsplash.com"

async def get_random_photo(query: str = None, **extra_params):
    url = f"{BASE_URL}/photos/random"
    params = {}
    if query:
        params["query"] = query
    params.update(extra_params)
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Unsplash API error: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logging.error(f"Exception in get_random_photo: {e}")
        return None

async def search_photos(query: str, page: int = 1, per_page: int = 10, **extra_params):
    url = f"{BASE_URL}/search/photos"
    params = {
        "query": query,
        "page": page,
        "per_page": per_page,
    }
    params.update(extra_params)
    headers = {"Authorization": f"Client-ID {UNSPLASH_ACCESS_KEY}"}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, headers=headers)
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Unsplash API error: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logging.error(f"Exception in search_photos: {e}")
        return None
