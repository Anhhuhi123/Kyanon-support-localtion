# ...existing code...
import sys
import json
import redis
from collections import defaultdict

REDIS_HOST="localhost"
REDIS_PORT=6379
REDIS_DB=0
REDIS_CACHE_TTL=3600

def list_cache(pattern: str = "*", max_preview: int = 200, scan_count: int = 1000):
    r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=False)
    total = 0
    type_counts = defaultdict(int)

    print(f"Scanning Redis for pattern: {pattern}")
    for key in r.scan_iter(match=pattern, count=scan_count):
        total += 1
        try:
            ktype = r.type(key)
            if isinstance(ktype, bytes):
                ktype = ktype.decode()
            ttl = r.ttl(key)
            try:
                mem = r.memory_usage(key) or 0
            except Exception:
                mem = None

            type_counts[ktype] += 1
            k_display = key.decode() if isinstance(key, bytes) else str(key)
            line = f"- {k_display} | type={ktype} | ttl={ttl}s | mem={mem} bytes"
            print(line)

            # preview for common types
            if ktype == "string":
                val = r.get(key) or b""
                try:
                    parsed = json.loads(val)
                    preview = f"JSON keys={list(parsed.keys())[:10]}"
                except Exception:
                    preview = (val.decode(errors="replace")[:max_preview] + ("..." if len(val) > max_preview else ""))
                print(f"    preview: {preview}")
            elif ktype == "hash":
                cnt = r.hlen(key)
                sample = r.hgetall(key)
                # show up to 10 fields
                sample_decoded = {k.decode(): (v.decode(errors="replace")[:max_preview] if isinstance(v, bytes) else v) for k, v in list(sample.items())[:10]}
                print(f"    hash_len={cnt}, sample={sample_decoded}")
            elif ktype in ("list", "set", "zset"):
                if ktype == "list":
                    cnt = r.llen(key)
                    sample = r.lrange(key, 0, 9)
                elif ktype == "set":
                    cnt = r.scard(key)
                    sample = list(r.sscan_iter(key, count=10))[:10]
                else:
                    cnt = r.zcard(key)
                    sample = r.zrange(key, 0, 9, withscores=True)
                print(f"    {ktype}_count={cnt}, sample={sample}")
        except Exception as e:
            print(f"  Error inspecting key {key}: {e}")

    print("\nSummary:")
    print(f"  Total matched keys: {total}")
    print(f"  By type: {dict(type_counts)}")

if __name__ == "__main__":
    pattern = sys.argv[1] if len(sys.argv) > 1 else "*"
    list_cache(pattern)
# ...existing code...