import os

# Wikipedia player-photo cache (core/cache.py, used by core/media.py)
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data", "cache")
CACHE_TTL_DAYS = 7
