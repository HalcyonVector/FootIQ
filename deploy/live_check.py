"""One-command smoke test of the deployed site (standard library only).

    py -3 deploy/live_check.py                      # https://footiq.onrender.com
    py -3 deploy/live_check.py http://localhost:5000

Waits for the app to wake up and finish loading its data, then checks health and
memory, the home page, search, a player's advanced stats and the link-up list.
Exits 1 if anything fails, so it can also gate a script.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else "https://footiq.onrender.com").rstrip("/")
MEMORY_WARN_MB = 450          # Render free tier restarts the app at 512
failures: list[str] = []


def call(path, body=None, timeout=90):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"} if data else {})
    t = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, raw, time.time() - t
    except urllib.error.HTTPError as e:
        return e.code, e.read(), time.time() - t
    except Exception as e:                 # DNS, timeout, connection reset while restarting
        return 0, str(e).encode(), time.time() - t


def check(name, ok, detail=""):
    print(f"  [{'ok' if ok else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
    if not ok:
        failures.append(name)


def as_json(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None


print(f"Checking {BASE}")

# 1. wake up and wait for the data to load (a sleeping free-tier app takes ~1 minute)
health = None
deadline = time.time() + 240
while time.time() < deadline:
    status, raw, secs = call("/api/health", timeout=30)
    health = as_json(raw) if status == 200 else None
    if health and health.get("warm"):
        break
    print(f"  waiting for the app ({'HTTP %s' % status if status else 'no answer'}"
          f"{', step: ' + str(health.get('step')) if health else ''})...")
    time.sleep(10)
check("app is up and warm", bool(health and health.get("warm")), f"step={health and health.get('step')}")
rss = health and health.get("rss_mb")
if rss is not None:
    check("memory under the limit", rss < MEMORY_WARN_MB, f"{rss} MB of 512")

# 2. pages
status, raw, secs = call("/")
check("home page", status == 200 and b"FootIQ" in raw, f"{status}, {secs:.1f}s")

# 3. search
status, raw, secs = call("/api/search?" + urllib.parse.urlencode({"name": "bruno", "league": "Premier League", "season": "2025-26"}))
hits = as_json(raw)
check("search returns players", status == 200 and isinstance(hits, list) and len(hits) > 0, f"{status}, {secs:.1f}s")
if not (isinstance(hits, list) and hits):
    sys.exit("search failed, cannot go further")
p = hits[0]
body = {"player_id": p["id"], "league": p["league"], "season": p["season"]}
print(f"  using {p['name']} ({p['league']} {p['season']})")

# 4. advanced stats + player page data + link-up
status, raw, secs = call("/api/advanced-stats", body)
data = as_json(raw)
check("advanced stats", status == 200 and bool(data) and "error" not in data, f"{status}, {secs:.1f}s")
status, raw, secs = call("/api/player?" + urllib.parse.urlencode({"id": p["id"], "league": p["league"], "season": p["season"]}))
check("player profile", status == 200, f"{status}, {secs:.1f}s")
status, raw, secs = call("/api/linkup-teammates", body)
data = as_json(raw)
check("link-up teammates", status == 200 and isinstance(data, dict) and "error" not in data, f"{status}, {secs:.1f}s")

# 5. memory again, after real work
status, raw, _ = call("/api/health", timeout=30)
after = as_json(raw) or {}
if after.get("rss_mb") is not None:
    check("memory after the checks", after["rss_mb"] < MEMORY_WARN_MB, f"{after['rss_mb']} MB of 512")

print("\nALL GOOD" if not failures else f"\nFAILED: {', '.join(failures)}")
sys.exit(1 if failures else 0)
