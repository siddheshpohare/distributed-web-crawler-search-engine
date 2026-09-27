# Distributed Web Crawler + Search Engine

## 1. Project Overview

**Distributed Web Crawler + Search Engine** is a production-style backend and distributed-systems project that crawls web pages, discovers new URLs, processes and indexes page content, and provides a search API through which users can search the crawled data.

The project is intentionally designed to evolve from a simple crawler into a distributed system. As the workload grows, the architecture introduces queues, multiple crawler workers, deduplication, rate limiting, retries, fault tolerance, search indexing, caching, observability, containerization, CI/CD, and cloud deployment.

The goal is **not** to recreate Google. The goal is to understand and implement the engineering principles that make large-scale crawling and search systems work.

---

## 2. Motivation

I wanted to build a project that goes beyond a standard CRUD backend and gives practical exposure to **backend engineering, distributed systems, search systems, and DevOps**.

A search engine is interesting because it naturally creates real engineering problems:

- How do we discover and crawl a large number of pages?
- How do we distribute crawling across multiple workers?
- How do we prevent multiple workers from processing the same URL?
- What happens when a website is slow or unavailable?
- How do we control request rates for each domain?
- How do we store and process large amounts of crawled content?
- How can users search millions of documents efficiently?
- How do we rank search results?
- How do we scale the API when search traffic increases?
- How do we monitor failures and system performance?

Each problem motivates a new architectural component. This makes the project useful for learning **why** technologies are needed rather than simply adding technologies to a project.

---

## 3. High-Level Architecture

```text
                              INTERNET
                                  |
                                  v
                         +----------------+
                         |  Seed URLs     |
                         +-------+--------+
                                 |
                                 v
                         +----------------+
                         | URL Frontier   |
                         | Redis / Queue  |
                         +-------+--------+
                                 |
                    +------------+------------+
                    |            |            |
                    v            v            v
               +---------+  +---------+  +---------+
               |Crawler 1|  |Crawler 2|  |Crawler N|
               +----+----+  +----+----+  +----+----+
                    |            |            |
                    +------------+------------+
                                 |
                                 v
                         +----------------+
                         | HTML Processor |
                         +-------+--------+
                                 |
                    +------------+------------+
                    |                         |
                    v                         v
             +-------------+          +-------------+
             | PostgreSQL  |          | Search Index|
             | Metadata    |          | Inverted   |
             |             |          | Index      |
             +-------------+          +------+------+
                                           |
                                           v
                                    +--------------+
                                    | Search API   |
                                    | FastAPI      |
                                    +------+-------+
                                           |
                                           v
                                        USER
```

Supporting infrastructure:

```text
Docker
GitHub Actions
AWS
Prometheus
Grafana
Structured Logging
```

---

# 4. Core Components

## 4.1 Search API

The API is the entry point for users.

Responsibilities:

- Accept search queries
- Return ranked results
- Provide pagination
- Provide autocomplete
- Expose crawler/system statistics
- Provide health-check endpoints
- Handle authentication if required

Example endpoints:

```text
POST /api/v1/crawl
GET  /api/v1/search?q=distributed+systems
GET  /api/v1/search/suggest?q=dist
GET  /api/v1/pages/{id}
GET  /api/v1/crawl/status
GET  /health
GET  /metrics
```

---

## 4.2 URL Frontier

The URL Frontier manages URLs waiting to be crawled.

It is responsible for:

- Queueing URLs
- Prioritizing URLs
- Preventing uncontrolled crawling
- Tracking crawl state
- Supporting retries
- Supporting distributed workers

Example states:

```text
DISCOVERED
    |
    v
QUEUED
    |
    v
CRAWLING
    |
    +----> SUCCESS
    |
    +----> RETRY
    |
    +----> FAILED / DEAD LETTER
```

Redis will initially be used for queueing and fast shared state.

---

## 4.3 Distributed Crawlers

Multiple crawler workers fetch pages concurrently.

Each crawler:

1. Gets a URL from the queue.
2. Checks whether it is allowed to crawl the domain.
3. Sends an HTTP request.
4. Handles timeout/errors.
5. Extracts HTML.
6. Extracts links.
7. Normalizes URLs.
8. Deduplicates URLs.
9. Stores page metadata/content.
10. Sends content to the indexing pipeline.

Example:

```text
Crawler Worker
     |
     +--> Fetch URL
     |
     +--> Parse HTML
     |
     +--> Extract text
     |
     +--> Extract links
     |
     +--> Normalize URLs
     |
     +--> Deduplicate
     |
     +--> Store page
     |
     +--> Enqueue new URLs
```

---

# 5. URL Deduplication

Duplicate work is a major problem in distributed crawling.

Example:

```text
https://example.com
https://example.com/
https://example.com/index.html
```

may refer to the same resource.

The system will normalize URLs before inserting them into the queue.

Possible approach:

```text
Raw URL
   |
   v
URL Normalization
   |
   v
Canonical URL
   |
   v
Hash
   |
   v
Already Seen?
   |
   +---- YES ---> Ignore
   |
   +---- NO ----> Add to Queue
```

Redis can be used for fast membership checks.

Important concepts:

- URL normalization
- hashing
- deduplication
- atomic operations
- race conditions
- idempotency

---

# 6. Domain Rate Limiting

The crawler must avoid overwhelming websites.

Instead of allowing unlimited requests:

```text
example.com -> max 2 requests/sec
```

The system will maintain per-domain crawl limits.

This introduces:

- rate limiting
- token bucket / leaky bucket concepts
- distributed shared state
- fairness between domains

The crawler should also respect crawling policies such as `robots.txt` where applicable.

---

# 7. Failure Handling

Web crawling is unreliable by nature.

Possible failures:

```text
DNS failure
Connection timeout
Connection reset
HTTP 404
HTTP 429
HTTP 500
HTTP 502
HTTP 503
```

The system will classify errors and decide whether to retry.

Example:

```text
Request
   |
   v
Failure
   |
   v
Retryable?
  / \
YES  NO
 |    |
 v    v
Retry  Failed
 |
 v
Exponential Backoff
 |
 v
Retry Limit Reached?
 |
 +---- YES ---> Dead Letter / Failed
```

Concepts:

- timeouts
- retries
- exponential backoff
- retry limits
- dead-letter queues
- fault tolerance

---

# 8. Worker Failure Recovery

A crawler worker may crash while processing a URL.

Example:

```text
Worker 3
   |
   +--> takes URL A
   |
   +--> crashes
```

The system should not permanently lose URL A.

Possible mechanism:

```text
Queue
  |
  v
Worker claims URL
  |
  v
Lease / visibility timeout
  |
  +--> Worker succeeds -> ACK
  |
  +--> Worker crashes -> lease expires
                         |
                         v
                    URL requeued
```

This introduces:

- acknowledgements
- leases
- visibility timeouts
- heartbeats
- recovery
- at-least-once processing

---

# 9. Content Processing

After crawling a page, the system extracts useful information.

From HTML:

```text
HTML
 |
 +--> Title
 +--> Headings
 +--> Main text
 +--> Links
 +--> Metadata
 +--> Canonical URL
```

The processor should remove unnecessary content such as:

- scripts
- styles
- navigation noise
- irrelevant HTML elements

The resulting document becomes an input to the indexing pipeline.

---

# 10. Search Index

Searching raw HTML with database queries does not scale well.

Instead, the project will implement an **inverted index**.

Example documents:

```text
D1 = "distributed systems are interesting"
D2 = "distributed databases are scalable"
D3 = "systems design is important"
```

Inverted index:

```text
distributed -> D1, D2
systems     -> D1, D3
databases   -> D2
scalable    -> D2
design      -> D3
important   -> D3
```

For:

```text
distributed systems
```

the system can quickly identify candidate documents.

The first version should implement a simple custom inverted index to understand the underlying mechanism.

Later, OpenSearch can be introduced and compared with the custom implementation.

---

# 11. Search Ranking

Finding matching documents is not enough. Results need to be ranked.

Initial ranking can consider:

- term frequency
- inverse document frequency
- title matches
- body matches
- document length

Later, implement or experiment with **BM25**.

Possible future signals:

- page freshness
- link-based importance
- anchor-text relevance

The project should explain why a particular ranking approach was selected.

---

# 12. Search Caching

Popular search queries can be cached.

Example:

```text
User
 |
 v
Search API
 |
 v
Redis
 |
 +---- Cache Hit ----> Return result
 |
 +---- Cache Miss
          |
          v
      Search Index
          |
          v
      Store in Redis
```

Concepts:

- cache-aside
- TTL
- cache invalidation
- hot keys
- cache hit ratio

---

# 13. Backend Database

PostgreSQL will store metadata and durable application state.

Potential tables:

```text
pages
------
id
url
canonical_url
domain
title
content_hash
http_status
crawl_status
last_crawled_at
created_at
updated_at

crawl_tasks
-----------
id
url
status
priority
attempt_count
worker_id
leased_until
last_error
created_at

domains
-------
id
hostname
crawl_delay
last_request_at
status
created_at
```

The exact schema will evolve as the system is implemented.

Important database concepts:

- primary keys
- foreign keys
- indexes
- unique constraints
- transactions
- query optimization
- connection pooling

---

# 14. Scalability Design

The API layer should be stateless.

```text
                 Load Balancer
                       |
          +------------+------------+
          |            |            |
          v            v            v
       API 1         API 2         API 3
          |            |            |
          +------------+------------+
                       |
                     Redis
                       |
                  Search Index
```

This allows horizontal scaling.

Crawler workers can also be scaled independently:

```text
                URL Queue
              /     |     \
             v      v      v
          Worker  Worker  Worker
             \      |      /
              \     |     /
               Crawl Data
```

This demonstrates separation of concerns and independent scaling.

---

# 15. DevOps

## Docker

Each major component will be containerized.

Potential services:

```text
api
crawler
indexer
postgres
redis
opensearch
prometheus
grafana
```

Docker Compose will be used for local development.

---

## CI/CD

GitHub Actions pipeline:

```text
git push
   |
   v
Run linting
   |
   v
Run unit tests
   |
   v
Run integration tests
   |
   v
Build Docker image
   |
   v
Push image
   |
   v
Deploy
```

---

# 16. Cloud Deployment

Target platform: **AWS**

A possible production architecture:

```text
                    Internet
                       |
                       v
                Load Balancer
                       |
              +--------+--------+
              |                 |
              v                 v
           API EC2          API EC2
              |
              v
            Redis
              |
              v
        Crawler Workers
              |
              v
        Search / Index
              |
       +------+------+
       |             |
       v             v
    PostgreSQL    Object Storage
```

The exact AWS architecture can be simplified or expanded based on cost and project scope.

Potential AWS services:

- EC2 / ECS
- RDS PostgreSQL
- ElastiCache Redis
- S3
- CloudWatch
- IAM
- Application Load Balancer

---

# 17. Observability

The system should expose metrics instead of relying only on logs.

Important metrics:

```text
pages_crawled_total
pages_failed_total
crawl_latency
crawl_requests_per_second
queue_depth
queue_wait_time
search_requests_total
search_latency
search_error_rate
cache_hit_ratio
worker_count
```

Prometheus will collect metrics.

Grafana will provide dashboards.

Example dashboard:

```text
+-----------------------------------------+
|         CRAWLER DASHBOARD               |
+-----------------------------------------+
| Pages/sec       | Queue Depth           |
|     42          |      8,421             |
+-----------------------------------------+
| Success Rate    | Error Rate             |
|     96.8%       |       3.2%             |
+-----------------------------------------+
| Average Latency| Active Workers         |
|     480 ms      |       12               |
+-----------------------------------------+
```

---

# 18. Logging

Use structured logs.

Example:

```json
{
  "level": "ERROR",
  "service": "crawler",
  "worker_id": "worker-03",
  "url": "https://example.com/page",
  "status": 503,
  "attempt": 3,
  "message": "request failed"
}
```

Useful fields:

- timestamp
- service
- worker ID
- request ID
- URL
- job/task ID
- error type
- latency

---

# 19. Testing

Testing should cover more than API endpoints.

## Unit tests

- URL normalization
- URL validation
- HTML extraction
- tokenization
- ranking
- retry logic

## Integration tests

- API + PostgreSQL
- API + Redis
- crawler + queue
- indexer + search index

## Load testing

Test:

```text
100 requests/sec
500 requests/sec
1000 requests/sec
```

Measure:

- latency
- throughput
- error rate
- CPU
- memory
- queue growth

Tools can include:

- pytest
- Locust / k6

---

# 20. Security

Potential security measures:

- API authentication
- authorization
- input validation
- rate limiting
- secrets through environment variables / secret manager
- HTTPS
- SQL injection protection through parameterized queries
- SSRF protection for crawler-controlled URLs
- container isolation
- restricted IAM permissions

Crawler-specific security is especially important because the system makes outbound requests based on URLs.

---

# 21. Project Phases

## Phase 1 — Basic Crawler

Build:

```text
Seed URL
   ↓
HTTP Request
   ↓
HTML Parser
   ↓
Extract Links
   ↓
Store Pages
```

Learn:

- HTTP
- HTML
- URL parsing
- PostgreSQL

---

## Phase 2 — REST API

Build:

```text
POST /crawl
GET /pages
GET /pages/{id}
GET /crawl/status
```

Learn:

- FastAPI
- API design
- validation
- database access

---

## Phase 3 — Redis Queue

Change:

```text
Crawler → Database
```

into:

```text
Crawler → Redis Queue → Worker → Database
```

Learn:

- asynchronous processing
- producer/consumer
- queues
- Redis

---

## Phase 4 — Distributed Crawling

Run:

```text
Worker 1
Worker 2
Worker 3
...
Worker N
```

Learn:

- concurrency
- horizontal scaling
- distributed coordination
- deduplication
- race conditions

---

## Phase 5 — Reliability

Implement:

- retries
- exponential backoff
- timeouts
- worker heartbeats
- leases
- dead-letter queue
- domain rate limiting

---

## Phase 6 — Search Engine

Implement:

```text
HTML
 ↓
Text Extraction
 ↓
Tokenization
 ↓
Inverted Index
 ↓
Ranking
 ↓
Search API
```

Implement basic ranking and then BM25.

---

## Phase 7 — Performance

Add:

- Redis caching
- database indexes
- connection pooling
- pagination
- query optimization
- load testing

---

## Phase 8 — DevOps

Add:

- Docker
- Docker Compose
- GitHub Actions
- automated testing
- CI/CD

---

## Phase 9 — Observability

Add:

- structured logging
- Prometheus
- Grafana
- health checks
- application metrics

---

## Phase 10 — Cloud

Deploy the system to AWS.

Document:

- architecture
- infrastructure
- deployment process
- costs
- scaling strategy

---

# 22. Failure Scenarios to Demonstrate

The project should deliberately test failure.

### Scenario 1: Worker crashes

```text
Worker claims URL
       ↓
Worker crashes
       ↓
Lease expires
       ↓
URL requeued
       ↓
Another worker processes it
```

### Scenario 2: Website is slow

```text
Request
  ↓
Timeout
  ↓
Retry with backoff
  ↓
Retry limit
  ↓
Dead Letter Queue
```

### Scenario 3: Duplicate URL

```text
Worker 1 ──┐
           ├──> Same URL
Worker 2 ──┘
             ↓
       Atomic deduplication
             ↓
       Only one crawl
```

### Scenario 4: Search traffic increases

```text
More users
    ↓
Load balancer
    ↓
More API instances
    ↓
Redis cache
    ↓
Search index
```

These experiments should be documented with measurements.

---

# 23. System Design Questions This Project Helps Answer

After completing the project, I should be able to discuss:

### Distributed systems

- How would you distribute crawling across 100 workers?
- How do you prevent duplicate work?
- What happens if a worker crashes?
- At-most-once vs at-least-once processing?
- How do retries create duplicate work?
- How would you implement backpressure?
- How would you partition the workload?

### Backend

- Why PostgreSQL?
- Where should Redis be used?
- How should APIs be designed?
- How do you handle concurrent requests?
- How do you optimize database queries?
- How do you implement rate limiting?

### Search

- What is an inverted index?
- Why not search raw HTML in PostgreSQL?
- How does BM25 work?
- How do you rank results?
- How would you scale search?

### DevOps

- Why Docker?
- How does CI/CD work?
- How do you monitor the system?
- What metrics matter?
- How do you deploy multiple workers?
- How would you roll back a bad deployment?

---

# 24. Complete Tech Stack

| Layer | Technology |
|---|---|
| Programming Language | **Python** |
| Backend Framework | **FastAPI** |
| API | **REST + OpenAPI** |
| Database | **PostgreSQL** |
| Cache | **Redis** |
| Message Queue | **Redis Streams initially** |
| Web Crawling | **httpx / aiohttp** |
| HTML Parsing | **BeautifulSoup / lxml** |
| Search | **Custom Inverted Index → OpenSearch** |
| Ranking | **TF-IDF → BM25** |
| Containerization | **Docker** |
| Local Orchestration | **Docker Compose** |
| CI/CD | **GitHub Actions** |
| Cloud | **AWS** |
| Database Hosting | **Amazon RDS** |
| Cache Hosting | **Amazon ElastiCache** |
| Object Storage | **Amazon S3** |
| Compute | **EC2 / ECS** |
| Load Balancing | **Application Load Balancer** |
| Monitoring | **Prometheus** |
| Dashboards | **Grafana** |
| Logging | **Structured JSON Logging** |
| Testing | **Pytest** |
| Load Testing | **Locust / k6** |
| Version Control | **Git + GitHub** |

> Note: the queue technology can later be replaced with Kafka or RabbitMQ if there is a genuine reason to study those systems. Do not add Kafka just to increase the number of technologies.

---

# 25. Resume-Level Project Description

**Distributed Web Crawler & Search Engine**

> Built a distributed web crawling and search platform using Python, FastAPI, PostgreSQL and Redis, with concurrent crawler workers, URL deduplication, domain-aware rate limiting, retries and failure recovery. Implemented an inverted search index with relevance ranking and Redis-based query caching. Containerized services with Docker, automated testing and deployment using GitHub Actions, and added Prometheus/Grafana observability for crawl throughput, queue depth, latency and error rates.

Only claim features that are actually implemented.

---

# 26. Interview Explanation

If asked **"Why did you choose this project?"**, the core answer is:

> I wanted to understand what happens behind a search engine rather than simply using an existing search API. When I broke the problem down, I found that it naturally involves distributed crawling, concurrency, URL deduplication, fault tolerance, indexing, ranking, caching and scalability. I also wanted one project where I could combine backend, distributed systems and DevOps instead of building another CRUD application. The interesting part for me was that each technology was introduced to solve an actual engineering problem in the system.

---

# 27. Final Project Goal

The final system should demonstrate:

```text
                 DISTRIBUTED SEARCH ENGINE

        ┌──────────────────────────────────────┐
        │              SEARCH API              │
        │          FastAPI + Redis Cache       │
        └──────────────────┬───────────────────┘
                           │
                           v
                     Search Index
                           ^
                           |
                    Indexing Pipeline
                           ^
                           |
                    Crawled Content
                           ^
                           |
                Distributed Crawlers
                 /       |       \
                /        |        \
          Worker 1   Worker 2   Worker N
                \        |        /
                 \       |       /
                    URL Frontier
                         |
                         v
                      Redis
                         |
                         v
                     PostgreSQL

        Docker + CI/CD + AWS + Prometheus + Grafana
```

## Success Criteria

By the end, the project should be able to:

- Crawl a controlled set of public websites.
- Discover and normalize new URLs.
- Avoid duplicate crawling.
- Run multiple crawler workers concurrently.
- Respect per-domain crawling limits.
- Recover from worker/network failures.
- Retry transient failures with backoff.
- Store crawl metadata reliably.
- Build an inverted search index.
- Rank search results.
- Serve search requests through an API.
- Cache popular searches.
- Run the full stack locally with Docker.
- Run automated tests through CI.
- Deploy the system to the cloud.
- Expose useful metrics and dashboards.
- Perform load/failure experiments and document the results.

**Primary learning outcome:** understand how a backend system evolves from a single-process application into a distributed, observable, scalable system as workload and reliability requirements increase.
