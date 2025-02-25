import os
import time
import uuid
import httpx
import aiofiles
import asyncio

BUFFER_DIR = "buffer_images"

if not os.path.exists(BUFFER_DIR):
    os.makedirs(BUFFER_DIR)

# Простой in‑memory кэш: URL -> {path, time}
CACHE = {}
CACHE_TTL = 3600  # время жизни в секундах

async def download_image(url: str) -> str:
    filename = f"{uuid.uuid4()}.jpg"
    filepath = os.path.join(BUFFER_DIR, filename)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
    if response.status_code == 200:
        async with aiofiles.open(filepath, "wb") as f:
            await f.write(response.content)
        CACHE[url] = {"path": filepath, "time": time.time()}
        return filepath
    return None

async def get_buffered_image(url: str) -> str:
    entry = CACHE.get(url)
    if entry and (time.time() - entry["time"]) < CACHE_TTL and os.path.exists(entry["path"]):
        return entry["path"]
    return await download_image(url)

async def cleanup_buffer():
    now = time.time()
    to_delete = []
    for url, entry in CACHE.items():
        if now - entry["time"] > CACHE_TTL:
            to_delete.append(url)
            try:
                os.remove(entry["path"])
            except Exception:
                pass
    for url in to_delete:
        del CACHE[url]
