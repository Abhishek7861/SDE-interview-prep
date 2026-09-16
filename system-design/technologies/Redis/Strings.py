import redis
import time

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Basic set/get
r.set("name", "Alice")
print(r.get("name"))  # Alice

# Set with expiry (TTL in seconds) — great for sessions, OTPs, temp tokens
r.set("session:abc123", "user_data", ex=6)
print(r.ttl("session:abc123"))  # ~6
for i in range(7):
    time.sleep(1)
    # After 6 seconds you get None
    print(r.get("session:abc123"))

# Increment a counter — atomic, no race conditions even under concurrency
r.set("page_views", 0)
r.incr("page_views")
r.incr("page_views")
r.incrby("page_views", 5)
print(r.get("page_views"))  # 7

# Check existence and delete
print(r.exists("name"))  # 1
r.delete("name")
print(r.exists("name"))  # 0