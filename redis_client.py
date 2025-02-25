import json
import redis.asyncio as aioredis

# Подключение к Redis (при необходимости настройте host, port, db)
redis_client = aioredis.Redis(host='localhost', port=6379, db=0)

async def cache_search_results(query: str, settings: dict, page: int, results: dict, ttl: int = 600):
    key = f"gallery:{query}:{json.dumps(settings, sort_keys=True)}:page:{page}"
    await redis_client.set(key, json.dumps(results), ex=ttl)

async def get_cached_search_results(query: str, settings: dict, page: int):
    key = f"gallery:{query}:{json.dumps(settings, sort_keys=True)}:page:{page}"
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None

async def cache_gallery_state(user_id: int, state: dict, ttl: int = 3600):
    key = f"gallery_state:{user_id}"
    await redis_client.set(key, json.dumps(state), ex=ttl)

async def get_gallery_state(user_id: int):
    key = f"gallery_state:{user_id}"
    cached = await redis_client.get(key)
    if cached:
        return json.loads(cached)
    return None
