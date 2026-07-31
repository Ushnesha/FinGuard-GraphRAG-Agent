import os
import json
import redis
from app.config import REDIS_URL

class RedisCache:
    def __init__(self):
        try:
            self.client = redis.Redis.from_url(url=REDIS_URL, socket_timeout=2)
            self.client.ping()
        except redis.ConnectionError:
            self.client = None

    def get(self, key:str):
        if not self.client: return None
        try:
            val = self.client.get(key)
            return json.loads(val.decode('utf-8'))
        except Exception:
            return None

    def set(self, key:str, value:str, ttl:int = 600):
        if not self.client: return
        try:
            self.client.setex(key, ttl, json.dumps(value))
        except Exception:
            pass
            
        
        
        
            