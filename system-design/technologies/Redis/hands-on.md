# Redis with Python — A Hands-On Tutorial

This tutorial walks through Redis fundamentals using `redis-py`, the official Python client. Every example below has been run and verified against a live Redis instance — the output shown is real, not simulated.

---

## 0. Setup

**Install Redis server** Docker

```bash
docker run -d --name my-redis -p 6379:6379 redis:latest
docker exec -it my-redis redis-cli
docker stop my-redis
docker start my-redis
```

**Install the Python client:**

```bash
pip install redis
```

**Connect from Python:**

```python
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
```

`decode_responses=True` makes Redis return normal Python strings instead of bytes (`b'...'`) — makes the examples much easier to read.

---

## 1. Strings — the simplest data type

Strings are the "hello world" of Redis: a key mapped to a value, with optional expiry.

```python
import redis

r = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Basic set/get
r.set("name", "Alice")
print(r.get("name"))  # Alice

# Set with expiry (TTL in seconds) — great for sessions, OTPs, temp tokens
r.set("session:abc123", "user_data", ex=10)
print(r.ttl("session:abc123"))  # ~10

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
```

**Verified output:**

```
Alice
10
7
1
0
```

**Why this matters:** `INCR` is atomic at the Redis level — this is why Redis strings are the go-to choice for counters, rate limiters, and view counts, even under heavy concurrent traffic.

---

## 2. Lists — ordered collections

Backed by a doubly linked list — cheap to push/pop from either end, useful for queues and recent-activity feeds.

```python
r.delete("recent_orders")

r.rpush("recent_orders", "order_101")   # push to the tail (right)
r.rpush("recent_orders", "order_102")
r.lpush("recent_orders", "order_100")   # push to the head (left)

print(r.lrange("recent_orders", 0, -1))  # get the whole list

print(r.lpop("recent_orders"))   # remove and return from the head
print(r.llen("recent_orders"))   # remaining length
```

**Verified output:**

```
['order_100', 'order_101', 'order_102']
order_100
2
```

**Use case:** a simple task queue — workers `LPOP` (or better, `BLPOP` for blocking pop) while producers `RPUSH` new jobs.

---

## 3. Sets & Hashes

**Sets** — unordered, unique members. Great for tags, memberships, and relationship queries.

```python
r.delete("post:1:tags", "post:2:tags")

r.sadd("post:1:tags", "python", "redis", "tutorial")
r.sadd("post:2:tags", "python", "django")

print(r.smembers("post:1:tags"))
print(r.sismember("post:1:tags", "redis"))         # membership check, O(1)
print(r.sinter("post:1:tags", "post:2:tags"))       # tags common to both posts
```

**Hashes** — field-value pairs under one key. This is how you naturally model an object (like a row/document) in Redis.

```python
r.delete("user:1")

r.hset("user:1", mapping={"name": "Bob", "age": "30", "city": "Delhi"})
print(r.hget("user:1", "name"))
print(r.hgetall("user:1"))
r.hincrby("user:1", "age", 1)   # atomically increment just one field
print(r.hget("user:1", "age"))
```

**Verified output:**

```
{'python', 'tutorial', 'redis'}
True
{'python'}
Bob
{'name': 'Bob', 'age': '30', 'city': 'Delhi'}
31
```

**Why Hashes over separate keys?** Storing a user as `user:1:name`, `user:1:age`, `user:1:city` (three separate string keys) wastes memory on key overhead. A single Hash groups related fields under one key far more efficiently.

---

## 4. Sorted Sets — the leaderboard structure

Every member has a score, and Redis keeps the set sorted by score automatically — O(log N) insert, O(log N + M) range queries.

```python
r.delete("leaderboard")

r.zadd("leaderboard", {"alice": 1500, "bob": 2200, "carol": 1800})

# Top 3 players, highest score first
print(r.zrevrange("leaderboard", 0, 2, withscores=True))

# Atomically increase a player's score (e.g., after they win a match)
r.zincrby("leaderboard", 500, "alice")
print(r.zscore("leaderboard", "alice"))

print(r.zrank("leaderboard", "bob"))       # rank ascending (0 = lowest score)
print(r.zrevrank("leaderboard", "bob"))    # rank descending (0 = top of leaderboard)
```

**Verified output:**

```
[('bob', 2200.0), ('carol', 1800.0), ('alice', 1500.0)]
2000.0
2
0
```

**Beyond leaderboards:** Sorted Sets are also used for priority queues (score = priority) and time-based sliding-window rate limiters (score = timestamp).

---

## 5. Pipelining — batching commands for speed

Every Redis command normally costs one network round trip. Pipelining bundles many commands into a single round trip.

```python
import time

# Without pipeline: 1000 separate round trips
r.delete("counter")
start = time.time()
for _ in range(1000):
    r.incr("counter")
no_pipeline_time = time.time() - start

# With pipeline: batched into far fewer round trips
r.delete("counter")
start = time.time()
pipe = r.pipeline()
for _ in range(1000):
    pipe.incr("counter")
pipe.execute()
pipeline_time = time.time() - start

print(f"Without pipeline: {no_pipeline_time:.4f}s")
print(f"With pipeline:    {pipeline_time:.4f}s")
print(f"Final counter value: {r.get('counter')}")
```

**Verified output (actual measured run):**

```
Without pipeline: 0.0374s
With pipeline:    0.0067s
Final counter value: 1000
```

That's roughly a **5.5x speedup** on this machine for 1000 commands — and the gap widens further over a real network (this test ran on localhost, where round trips are already cheap).

---

## 6. The Cache-Aside Pattern — Redis's most common real-world use

This is the pattern almost every production Redis deployment implements: check cache first, fall back to the slow source (a database) on a miss, then populate the cache for next time.

```python
import json
import time

def fetch_from_db(product_id):
    time.sleep(0.5)  # simulate a slow SQL query
    return {"id": product_id, "name": "Wireless Mouse", "price": 799}

def get_product(product_id):
    cache_key = f"product:{product_id}"
    cached = r.get(cache_key)
    if cached:
        print("Cache HIT")
        return json.loads(cached)

    print("Cache MISS -> querying DB")
    data = fetch_from_db(product_id)
    r.set(cache_key, json.dumps(data), ex=60)  # cache for 60 seconds
    return data

start = time.time()
get_product(42)
print(f"Took {time.time()-start:.2f}s\n")

start = time.time()
get_product(42)
print(f"Took {time.time()-start:.2f}s")
```

**Verified output:**

```
Cache MISS -> querying DB
Took 0.50s

Cache HIT
Took 0.00s
```

The second call is effectively instant — this is the entire value proposition of caching in one demo. In production, you'd also handle **cache invalidation** (delete/update the key when the underlying DB row changes) and consider **cache stampede** protection (a lock or "stale-while-revalidate" strategy) for very hot keys.

---

## 7. Distributed Locking — a classic Redis interview + real-world pattern

Using `SET ... NX EX` to acquire a lock, and a Lua script to release it safely (only if you're still the lock's owner).

```python
import uuid

def acquire_lock(lock_key, ttl_seconds=10):
    token = str(uuid.uuid4())
    acquired = r.set(lock_key, token, nx=True, ex=ttl_seconds)
    return token if acquired else None

def release_lock(lock_key, token):
    # Only delete if the value still matches our token —
    # prevents releasing a lock that another process now owns
    script = """
    if redis.call("GET", KEYS[1]) == ARGV[1] then
        return redis.call("DEL", KEYS[1])
    else
        return 0
    end
    """
    return r.eval(script, 1, lock_key, token)

lock_key = "lock:inventory:item42"

token_a = acquire_lock(lock_key)
print("Process A acquired lock:", bool(token_a))

token_b = acquire_lock(lock_key)          # fails — A still holds it
print("Process B acquired lock:", bool(token_b))

print("Process A release result:", release_lock(lock_key, token_a))

token_b = acquire_lock(lock_key)          # now succeeds
print("Process B acquired lock after A released:", bool(token_b))
```

**Verified output:**

```
Process A acquired lock: True
Process B acquired lock: False
Process A release result: 1
Process B acquired lock after A released: True
```

**Why the Lua script matters:** without it, you'd do a `GET` then `DEL` as two separate commands — but another process could acquire the lock in between those two calls. The Lua script runs atomically inside Redis, closing that race window entirely.

---

## 8. Pub/Sub — real-time messaging

Publishers broadcast messages to a channel; subscribers listening on that channel receive them instantly. Note: messages are fire-and-forget — if nobody's subscribed when you publish, the message is lost.

```python
import threading
import time

def subscriber():
    pubsub = r.pubsub()
    pubsub.subscribe("notifications")
    for message in pubsub.listen():
        if message["type"] == "message":
            print(f"Subscriber received: {message['data']}")
            break

t = threading.Thread(target=subscriber)
t.start()
time.sleep(0.5)  # give the subscriber time to connect

r.publish("notifications", "New order placed: #1042")
t.join(timeout=2)
```

**Verified output:**

```
Subscriber received: New order placed: #1042
```

**When to reach for something else:** if you need guaranteed delivery, message replay, or consumer groups, look at Redis **Streams** (`XADD`/`XREADGROUP`) instead — Pub/Sub has no persistence or replay.

---

## Where to Go Next

- **Redis Streams** — append-only log with consumer groups, closer to Kafka semantics
- **HyperLogLog** — approximate unique counts in constant memory (`PFADD`/`PFCOUNT`)
- **Redis Cluster** — sharding across nodes via hash slots, for scaling beyond one machine
- **`redis-py`'s async client** (`redis.asyncio`) — for use inside `asyncio`based Python apps (FastAPI, etc.)

## Full Runnable Scripts

All 8 examples above are also included as standalone, tested `.py` files (`01_strings.py` through `08_pubsub.py`) — run any of them directly once you have `redis-server` running locally:

```bash
python3 01_strings.py
```