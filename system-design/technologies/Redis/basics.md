# Redis Basics for SDE Interviews

A condensed, interview-ready reference covering the Redis concepts that come up most in SDE screens and system design rounds.

---

## 1. What Redis Actually Is

Redis = **RE**mote **DI**ctionary **S**erver — an in-memory, key-value data store that can also act as a cache, message broker, and (optionally) durable database.

**Key characteristics to lead with:**

- **In-memory** → extremely fast (sub-millisecond reads/writes), since it avoids disk I/O on the hot path.
- **Single-threaded core** (for command execution) → no locking overhead, but means one slow command blocks everything else.
- **Rich data structures**, not just strings — this is what separates it from plain key-value stores like Memcached.
- **Persistence options** despite being in-memory (**RDB snapshots**, **AOF logs**).
- **Supports replication, clustering, and pub/sub** out of the box.

**Common opener question:** *"Redis vs Memcached?"*

|  | Redis | Memcached |
| --- | --- | --- |
| Data structures | Strings, Lists, Sets, Hashes, Sorted Sets, Streams, etc. | Only strings (key-value) |
| Persistence | RDB / AOF | None — pure in-memory |
| Threading | Single-threaded core (I/O threading added in 6+) | Multi-threaded |
| Replication | Built-in master-replica | Not built-in |
| Use case | Cache + broker + lightweight DB | Pure caching layer |

---

## 2. Core Data Structures

Interviewers love asking "how would you model X in Redis" — know the structures and their Big-O.

| Structure | Description | Common Commands | Typical Use Case |
| --- | --- | --- | --- |
| **String** | Binary-safe byte sequence, up to 512MB | `SET`, `GET`, `INCR`, `EXPIRE` | Caching, counters, session tokens |
| **List** | Doubly linked list of strings | `LPUSH`, `RPUSH`, `LPOP`, `LRANGE` | Queues, activity feeds, recent items |
| **Set** | Unordered collection, unique members | `SADD`, `SREM`, `SISMEMBER`, `SINTER` | Tags, unique visitor tracking, relationships |
| **Sorted Set (ZSet)** | Set with a score per member, kept sorted | `ZADD`, `ZRANGE`, `ZRANK`, `ZINCRBY` | Leaderboards, priority queues, rate limiting |
| **Hash** | Field-value pairs under one key | `HSET`, `HGET`, `HGETALL` | Representing objects (e.g., a user record) |
| **Bitmap** | String treated as a bit array | `SETBIT`, `GETBIT`, `BITCOUNT` | Feature flags, presence tracking (e.g., daily active users) |
| **HyperLogLog** | Probabilistic structure for cardinality estimation | `PFADD`, `PFCOUNT` | Approximate unique counts (millions of items, ~0.81% error, tiny memory footprint) |
| **Stream** | Append-only log, similar to Kafka topics | `XADD`, `XREAD`, `XRANGE` | Event sourcing, message queues with consumer groups |

**Follow-up they'll ask:** *"**How would you build a leaderboard?**"* → Sorted Set. `ZADD leaderboard 1500 "user123"`, then `ZREVRANGE leaderboard 0 9 WITHSCORES` for top 10. O(log N) insert, O(log N + M) range fetch.

**Follow-up on rate limiting:** *"**How would you implement a rate limiter?**"* → Two common patterns:

1. **Fixed window counter**: `INCR` on a key like `rate:user123:2026-09-16-14`, set `EXPIRE` on first increment.
2. **Sliding window log**: use a Sorted Set with timestamps as scores, `ZREMRANGEBYSCORE` to evict old entries, `ZCARD` to count requests in the window.

---

## 3. Expiration & Eviction

**TTL basics:**

```
SET session:abc123 "userdata" EX 3600   # expires in 1 hour
TTL session:abc123                       # check remaining time
PERSIST session:abc123                   # remove expiration
```

**How expiration actually works internally** (a good depth-signal answer):

- **Passive**: checked when a key is accessed — if expired, it's deleted then.
- **Active**: a background cycle periodically samples random keys with TTLs and deletes expired ones, to avoid memory bloat from keys that are never accessed again.

**Eviction policies** — asked when discussing Redis as a cache under memory pressure (`maxmemory-policy`):

- `noeviction` — returns errors on writes once memory is full (default).
- `allkeys-lru` — evicts least recently used key, regardless of TTL.
- `volatile-lru` — evicts LRU among keys **with a TTL set**.
- `allkeys-lfu` / `volatile-lfu` — evicts least frequently used (better for skewed access patterns).
- `volatile-ttl` — evicts the key with the shortest remaining TTL first.

**Interview tip:** if asked "how would you design a cache with Redis," always mention picking an eviction policy deliberately — `allkeys-lru` is the most common default for pure caching workloads.

---

## 4. Persistence

Since Redis is in-memory, interviewers often probe: *"What happens if the server restarts?"*

**RDB (Redis Database snapshot):**

- Point-in-time binary snapshot of the dataset, written to disk at configured intervals (e.g., every 60s if 1000+ keys changed).
- Fast to restart from, compact file size.
- Risk: can lose data since the last snapshot if the process crashes.

**AOF (Append Only File):**

- Logs every write operation as it happens.
- More durable — configurable fsync policy (`always`, `everysec`, `no`).
- Larger file size, slower to replay on restart (though Redis rewrites/compacts the AOF periodically).

**Hybrid approach:** Redis supports using both simultaneously — RDB for fast restarts, AOF for durability. Mention this shows you understand it's not an either/or in production.

---

## 5. Replication & High Availability

**Master-Replica replication:**

- Writes go to the master; replicas asynchronously copy data from it.
- Replicas can serve reads, offloading read traffic from the master.
- Asynchronous by default → possible for a replica to lag behind (eventual consistency, not strong consistency).

!image.png

**Redis Sentinel:**

- Monitors master/replica health.
- Handles automatic failover — promotes a replica to master if the master goes down.
- Provides service discovery for clients to find the current master.

!image.png

**Redis Cluster:**

- Horizontal scaling — data is sharded across multiple nodes using **16384 hash slots**.
- Each key is mapped to a slot via `CRC16(key) % 16384`.
- Each node owns a subset of slots; supports resharding without downtime.
- Provides both sharding and replication (each shard can have its own replicas).

!image.png

**Common question:** *"How does Redis Cluster decide which node holds a key?"* → Hash slot formula above. Also mention **hash tags** (`{user1000}.profile`, `{user1000}.orders`) to force related keys into the same slot when you need multi-key operations.

---

## 6. Redis as a Cache — The Classic System Design Angle

This is where Redis interview questions most often land in a broader system design context.

**Cache-aside (lazy loading) — most common pattern:**

1. App checks Redis for the key.
2. Cache miss → fetch from DB → write result into Redis → return to caller.
3. Cache hit → return directly from Redis.

**Write-through:** every write goes to the cache and the DB together (simpler consistency, slightly higher write latency).

**Write-behind (write-back):** writes go to cache first, asynchronously flushed to DB later (faster writes, risk of data loss if cache fails before flush).

**Cache invalidation strategies (mention this — it's a classic "hardest problem in CS" callback):**

- TTL-based expiry (simplest, slight staleness window).
- Explicit invalidation on write (`DEL` the key when the underlying DB row changes).
- Versioned/namespaced keys to invalidate large groups at once.

**Cache stampede ("thundering herd") — a strong differentiator to bring up:**

- Problem: a hot key expires, and many concurrent requests all miss the cache simultaneously and hammer the DB at once.
- Mitigations: **mutex/lock on cache miss** (only one request repopulates, others wait), **probabilistic early expiration**, or **stale-while-revalidate** (serve stale data while one request refreshes it in the background).

---

## 7. Atomicity, Transactions & Scripting

**Single commands are atomic** — Redis's single-threaded execution model guarantees this without extra locking.

**MULTI/EXEC (transactions):**

```
MULTI
SET key1 "a"
INCR counter
EXEC
```

- Commands are queued, then executed sequentially and atomically as a batch.
- Not full ACID — no rollback on a runtime error inside a queued command; it's "all commands execute" not "all-or-nothing on failure."
- `WATCH` enables optimistic locking — if a watched key changes before `EXEC`, the transaction aborts.

**Lua scripting (`EVAL`):**

- Runs atomically since Redis executes the whole script without interruption from other clients.
- Common use case: implementing "check-then-act" logic atomically (e.g., a distributed lock's check-and-delete).

**Distributed locking (`SETNX` / Redlock) — a favorite whiteboard question:**

```
SET lock:resource "unique_token" NX EX 30
```

- `NX` = only set if not exists (acquire lock), `EX 30` = auto-expire after 30s to avoid deadlock if the holder crashes.
- Release safely with a Lua script that checks the token matches before deleting (prevents accidentally releasing someone else's lock).
- **Redlock algorithm**: acquiring the lock across a majority of independent Redis instances for stronger guarantees in distributed setups — mention it exists, note it's debated for correctness under certain failure/clock-drift scenarios (worth knowing this nuance if the interviewer pushes).

---

## 8. Pub/Sub and Streams

**Pub/Sub:**

```
SUBSCRIBE channel1
PUBLISH channel1 "hello"
```

- Fire-and-forget — if no subscriber is listening, the message is lost. No persistence, no replay.

**Streams (`XADD`/`XREAD`) — the more robust alternative:**

- Append-only log, similar conceptually to Kafka.
- Supports **consumer groups** (`XREADGROUP`) — multiple consumers can split load and each message is processed once per group.
- Messages persist and can be replayed, unlike Pub/Sub.

**Interview framing:** if asked "would you use Redis as a message queue," the honest answer is: Streams work well for lightweight, low-latency queuing needs; for heavy-duty, high-throughput, guaranteed-delivery messaging at scale, dedicated systems like Kafka or RabbitMQ are usually a better fit. Showing this judgment (not just "yes Redis can do it") signals seniority.

---

## 9. Common "Explain the Behavior" Trick Questions

```
# 1. INCR on a non-existent key
INCR counter          # returns 1 — treats missing key as 0

# 2. EXPIRE on a non-existent key
EXPIRE missingkey 10  # returns 0 (integer), does nothing — key doesn't exist

# 3. Overwriting TTL
SET key "value" EX 100
SET key "newvalue"     # TTL is removed! Plain SET without EX clears any prior expiration

# 4. Type mismatch
SET mykey "hello"
LPUSH mykey "world"   # (error) WRONGTYPE Operation against a key holding the wrong kind of value
```

---

## 10. Design/Behavioral Angles Interviewers Layer On Top

- **"Design a session store"** → Hash or String per session ID, TTL matching session expiry, replicate for HA.
- **"Design an online leaderboard for millions of users"** → Sorted Set, discuss sharding via Redis Cluster if it exceeds single-node capacity.
- **"How do you keep Redis and your DB in sync?"** → cache-aside + TTL, or invalidate-on-write; acknowledge eventual staleness is usually acceptable for caching use cases.
- **"What happens on a Redis outage?"** → depends on architecture: with Sentinel/Cluster, automatic failover; without it, discuss graceful degradation (fall back to DB reads directly, accept higher latency temporarily).

---

## Quick-Fire Prep Checklist

- [ ]  Can explain Redis vs Memcached in under 30 seconds
- [ ]  Know all core data structures and can map a use case to each
- [ ]  Can explain RDB vs AOF trade-offs
- [ ]  Understand eviction policies and when you'd pick `allkeys-lru` vs `volatile-ttl`
- [ ]  Can explain hash slots in Redis Cluster and why hash tags matter
- [ ]  Can design a cache-aside flow and explain cache stampede mitigation
- [ ]  Know how `SETNX` + TTL implements a basic distributed lock, and its failure edge cases
- [ ]  Can distinguish Pub/Sub from Streams and justify which fits a given scenario

---

*Tip: Redis interview questions are rarely about memorizing commands — they're testing whether you can reason about trade-offs (consistency vs speed, memory vs durability, simplicity vs correctness under failure). Frame every answer around the trade-off, not just the mechanism.*