# CSKG Graph Database — Project Documentation

**Project:** 9 Stralchonak Wilczyński  
**Course:** Databases 2, 2026  
**Repository:** `9-stralchonak-wilczynski`

---

## Table of Contents

1. [Choice of Technology](#1-choice-of-technology)
2. [Architecture](#2-architecture)
3. [Prerequisites](#3-prerequisites)
4. [Installation and Setup Instructions](#4-installation-and-setup-instructions)
5. [Design and Implementation Process](#5-design-and-implementation-process)
6. [Goals and Query Implementation Details](#6-goals-and-query-implementation-details)
7. [Student Roles](#7-student-roles)
8. [Results](#8-results)
9. [User Manual](#9-user-manual)
10. [Self-Evaluation](#10-self-evaluation)

---

## 1. Choice of Technology

### Database: ArangoDB

**ArangoDB** is a multi-model NoSQL database that natively supports graph, document, and key-value data. It was chosen for the following reasons:

- **Native graph model** — edges and vertices are first-class citizens, making graph traversals (successors, predecessors, BFS, shortest path) natural and efficient without joins.
- **AQL (ArangoDB Query Language)** — a declarative query language with built-in graph traversal operators (`OUTBOUND`, `INBOUND`, `ANY`, `SHORTEST_PATH`), recursive path expressions, and aggregation.
- **Persistent indexes** — supports persistent B-tree indexes on any document field, enabling fast `FILTER` operations without full collection scans.
- **REST API + python-arango** — well-supported Python client library for programmatic access.
- **Docker availability** — official Docker image enables a fully local deployment with zero configuration.
- **ArangoDB Cloud** — the same software is available as a managed cloud service (used for initial development and university server testing).

### Language: Python 3

The CLI utility and importer are written in Python 3 because:

- `python-arango` provides a mature, well-documented ArangoDB client.
- `argparse` provides clean CLI argument parsing with subcommands.
- The BFS logic for distant synonyms/antonyms is straightforward to express in Python while delegating bulk expansion to ArangoDB per level.

### Dataset: CSKG (Common Sense Knowledge Graph)

CSKG is distributed as a tab-separated file (`cskg.tsv`) in KGTK format with columns:  
`id`, `node1`, `relation`, `node2`, `node1;label`, `node2;label`, `relation;label`, `relation;dimension`, `source`, `sentence`

The dataset contains approximately **6,001,531 edges** and **2,160,968 unique nodes**.

---

## 2. Architecture

### Components

```
┌──────────────────────────────────────────────────────────────┐
│                        User Machine                          │
│                                                              │
│   cskg_cli.py          import_cskg.py      setup_env.ps1     │
│   (CLI queries)        (data importer)     (env setup)       │
│        │                     │                  │            │
│        └──────────┬──────────┘                  │            │
│                   │                             │            │
│        ┌──────────▼──────────────────────────── ▼──────┐     │
│        │         ArangoDB (Docker, port 8529)          │     │
│        │                                               │     │
│        │   Collection: nodes (2,160,968 documents)     │     │
│        │   Collection: relation (6,001,531 edges)      │     │
│        │                                               │     │
│        │   Indexes:                                    │     │
│        │     nodes.id_original  (persistent)           │     │
│        │     relation.relation  (persistent)           │     │
│        │     relation._from/_to (automatic)            │     │
│        └───────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### Collections and Schema

**`nodes` collection (document collection)**

| Field | Type | Description |
|---|---|---|
| `_key` | string | URL-percent-encoded version of the original node ID |
| `_id` | string | ArangoDB handle: `nodes/<_key>` |
| `id_original` | string | Original human-readable node ID (e.g. `/c/en/happy`) |
| `label` | string | Primary display label |
| `labels` | string | Pipe-separated list of all labels (if multiple) |

**`relation` collection (edge collection)**

| Field | Type | Description |
|---|---|---|
| `_key` | string | Percent-encoded composite key |
| `_from` | string | Source node handle |
| `_to` | string | Target node handle |
| `relation` | string | Relation type (e.g. `/r/Synonym`, `/r/Antonym`) |
| `relation_label` | string | Human-readable relation label (optional) |
| `source` | string | Source knowledge base (optional) |
| `sentence` | string | Natural language sentence (optional) |

### Indexes

| Collection | Field | Type | Purpose |
|---|---|---|---|
| `nodes` | `id_original` | Persistent | Fast node lookup by human-readable ID |
| `relation` | `relation` | Persistent | Fast filtering by relation type (synonym/antonym BFS) |
| `relation` | `_from`, `_to` | Automatic | Graph traversal (managed by ArangoDB) |

### Data Flow

1. `import_cskg.py` reads `cskg.tsv`, extracts unique nodes, uploads them in parallel batches, then uploads edges, then creates indexes.
2. `cskg_cli.py` connects to ArangoDB, resolves a node's internal `_id` from its `id_original`, then executes an AQL query and prints results.
3. `setup_env.ps1` automates steps: pull Docker image → start container → wait for readiness → call `import_cskg.py`.

---

## 3. Prerequisites

### Software

| Software | Version | Purpose |
|---|---|---|
| Python | 3.9+ | Runtime for CLI and importer |
| Docker Desktop | Any recent | Runs ArangoDB locally |
| python-arango | ≥ 7.x | ArangoDB Python client |
| tqdm | any | Progress bars during import (optional but recommended) |
| requests | any | HTTP transport (installed with python-arango) |

### Python packages

```
pip install python-arango tqdm
```

### Data file

- `cskg.tsv` — the CSKG dataset file in KGTK tab-separated format, placed in the project directory.

---

## 4. Installation and Setup Instructions

### Step 1 — Clone the repository

```bash
git clone https://gitlab.kis.agh.edu.pl/databases-2-2026/9-stralchonak-wilczynski.git
cd 9-stralchonak-wilczynski
```

### Step 2 — Install Python dependencies

```bash
pip install python-arango tqdm
```

### Step 3 — Place the dataset

Copy `cskg.tsv` into the project root directory (same folder as `cskg_cli.py`).

### Step 4 — Set up the local ArangoDB environment

Run the setup script. This pulls the Docker image, starts the container, waits for ArangoDB to be ready, and imports all data with indexes:

```powershell
.\setup_env.ps1
```

This takes approximately 5–10 minutes for the full import on a typical machine.

**Options:**

```powershell
.\setup_env.ps1 -Password mysecret   # use a custom password (update CLI defaults too)
.\setup_env.ps1 -SkipImport          # just start the container (data already loaded)
.\setup_env.ps1 -Fresh               # truncate and re-import from scratch
```

### Step 5 — Verify

Open `http://localhost:8529` in a browser — the ArangoDB web dashboard should appear (username: `root`, password: `localpass`).

Run a test query:

```bash
python cskg_cli.py 9
```

Expected output: `2160968` (total node count).

### Using the university cloud server

Point the CLI at the remote host:

```bash
python cskg_cli.py --host <server-address> --port 8529 --db DB_Project \
                   --user root --password <password> successors /c/en/dog
```

---

## 5. Design and Implementation Process

### Phase 1 — Database schema design

The CSKG dataset is inherently a directed graph: nodes are concepts and edges are typed relations. ArangoDB's native graph model was chosen over a relational schema to avoid costly self-joins for traversal queries.

Key design decisions:
- **Two-collection model:** a document collection for nodes and an edge collection for relations. This is the standard ArangoDB graph pattern and enables all built-in traversal operators.
- **`_key` encoding:** ArangoDB `_key` values have character restrictions. Node IDs like `/c/en/©` contain slashes and Unicode. A percent-encoding scheme was implemented so that every valid node ID maps to a unique, deterministic `_key` without hash collisions.
- **`id_original` field:** the original node ID is stored as a separate indexed field so that users can query by human-readable ID. Internal lookups use the `_id` handle for traversal.
- **Sparse optional fields:** fields like `sentence` and `source` are only stored when non-empty, saving approximately 20–30% payload size during import.

### Phase 2 — Data importer (`import_cskg.py`)

The importer performs five phases:

1. **Connect** — establishes a connection to ArangoDB, creates the database and collections if absent, disables `waitForSync` for bulk import speed.
2. **Scan** — reads the TSV once to collect all unique nodes into an in-memory `OrderedDict`.
3. **Upload nodes** — batched parallel upload using `import_bulk` (ArangoDB's native bulk import endpoint), 4 threads, batch size 2000.
4. **Upload edges** — streams the TSV a second time and uploads edges in parallel batches.
5. **Create indexes** — creates persistent indexes on `nodes.id_original` and `relation.relation`.

A custom `TunedHTTPClient` subclass adds gzip compression on request bodies over 1 KB and configures a connection pool sized to the thread count.

### Phase 3 — CLI tool (`cskg_cli.py`)

Each command resolves the node's `_id` from its `id_original` using a single indexed AQL lookup (`resolve_handle`), then executes one AQL query and prints results.

The BFS for distant synonyms/antonyms was the most complex query to implement correctly and efficiently:

- **Initial approach (cloud, rejected):** one AQL query per node in the BFS frontier — at distance 17 this caused millions of HTTP round-trips and never completed.
- **Improved approach (batch-per-level):** one AQL query per BFS depth level, expanding all frontier nodes in a single `FOR start IN @starts` query. This reduces round-trips from O(frontier_size × distance) to exactly O(distance).
- **Parity tracking bug (fixed):** the `visited` dict was initially keyed by node handle alone. A node reachable at distance 3 as a synonym would block it from being discovered at distance 17 as an antonym via a different path. Fix: track `(handle, parity)` states with a set of parities per handle at minimum distance.

### Phase 4 — Local environment (`setup_env.ps1`)

A PowerShell script automates the full environment setup so that any developer can go from zero to running queries with a single command. It handles: Docker pull (if needed), container creation vs. restart detection, readiness polling, and data import.

---

## 6. Goals and Query Implementation Details

All 18 queries are implemented as subcommands in `cskg_cli.py`. The CLI defaults to the local Docker instance (`localhost:8529`) and supports overriding any connection parameter.

---

### Goal 1 — Find all successors of a given node

**Command:** `successors <node_id>` / alias `1`  
**Definition:** nodes reachable by following one outbound edge from the given node.

```aql
FOR v IN 1..1 OUTBOUND @start relation
    RETURN DISTINCT v
```

`OUTBOUND` follows edges in the direction `_from → _to`. `DISTINCT` removes duplicates arising from parallel edges.

---

### Goal 2 — Count all successors

**Command:** `count-successors <node_id>` / alias `2`

```aql
RETURN COUNT(
    FOR v IN 1..1 OUTBOUND @start relation
        RETURN DISTINCT v._key
)
```

---

### Goal 3 — Find all predecessors

**Command:** `predecessors <node_id>` / alias `3`  
**Definition:** nodes from which there is a directed edge to the given node.

```aql
FOR v IN 1..1 INBOUND @start relation
    RETURN DISTINCT v
```

`INBOUND` traverses edges in reverse direction.

---

### Goal 4 — Count all predecessors

**Command:** `count-predecessors <node_id>` / alias `4`

```aql
RETURN COUNT(
    FOR v IN 1..1 INBOUND @start relation
        RETURN DISTINCT v._key
)
```

---

### Goal 5 — Find all neighbors

**Command:** `neighbors <node_id>` / alias `5`  
**Definition:** union of successors and predecessors (both directions).

```aql
FOR v IN 1..1 ANY @start relation
    RETURN DISTINCT v
```

`ANY` traverses edges in both directions.

---

### Goal 6 — Count all neighbors

**Command:** `count-neighbors <node_id>` / alias `6`

```aql
RETURN COUNT(
    FOR v IN 1..1 ANY @start relation
        RETURN DISTINCT v._key
)
```

---

### Goal 7 — Find all grandchildren

**Command:** `grandchildren <node_id>` / alias `7`  
**Definition:** successors of successors (nodes reachable in exactly 2 outbound hops).

```aql
FOR v IN 2..2 OUTBOUND @start relation
    RETURN DISTINCT v
```

The `2..2` depth range restricts results to exactly 2 hops.

---

### Goal 8 — Find all grandparents

**Command:** `grandparents <node_id>` / alias `8`  
**Definition:** predecessors of predecessors.

```aql
FOR v IN 2..2 INBOUND @start relation
    RETURN DISTINCT v
```

---

### Goal 9 — Count all nodes

**Command:** `count-nodes` / alias `9`

```aql
RETURN COUNT(FOR n IN nodes RETURN 1)
```

---

### Goal 10 — Count nodes with no successors

**Command:** `count-no-successors` / alias `10`  
**Logic:** total nodes minus nodes that appear as `_from` in at least one edge.

```aql
LET total = LENGTH(nodes)
LET with_successors = LENGTH(
    FOR e IN relation
        COLLECT _from = e._from
        RETURN 1
)
RETURN total - with_successors
```

`COLLECT` performs a sort-based grouping, counting each unique `_from` once.

---

### Goal 11 — Count nodes with no predecessors

**Command:** `count-no-predecessors` / alias `11`

```aql
LET total = LENGTH(nodes)
LET with_predecessors = LENGTH(
    FOR e IN relation
        COLLECT _to = e._to
        RETURN 1
)
RETURN total - with_predecessors
```

---

### Goal 12 — Find node(s) with the most neighbors

**Command:** `most-neighbors` / alias `12`

**Logic (AQL server-side + file cache):** degree computation was moved fully server-side using AQL `COLLECT WITH AGGREGATE COUNT_DISTINCT`, avoiding streaming 6M edges into Python. The result is cached to `.cskg_degrees.json` on first run; subsequent calls return instantly. The cache is automatically invalidated by `rename` and `delete` operations.

```aql
LET pairs = (FOR e IN relation RETURN { a: e._from, b: e._to })
LET both = APPEND(
    (FOR p IN pairs RETURN { node: p.a, nbr: p.b }),
    (FOR p IN pairs RETURN { node: p.b, nbr: p.a })
)
FOR item IN both
    COLLECT node = item.node AGGREGATE degree = COUNT_DISTINCT(item.nbr)
    RETURN { node: node, degree: degree }
```

---

### Goal 13 — Count nodes with a single neighbor

**Command:** `count-single-neighbor` / alias `13`

Uses the same `_compute_degrees` helper as Goal 12 (with the same AQL + file cache), then counts entries with degree == 1.

---

### Goal 14 — Rename a node

**Command:** `rename <old_node_id> <new_node_id> <new_label>` / alias `14`  
**Logic:** resolves the node's internal `_key`, checks no other node already uses the new `id_original` (prevents ambiguous duplicates), then updates `id_original`, `label`, and `labels` in place. The `_key` is not changed — all existing edges remain valid without modification.

```aql
UPDATE @key WITH { id_original: @new_id, label: @new_label, labels: @new_label }
IN nodes
RETURN NEW
```

---

### Goal 15 — Find similar nodes

**Command:** `similar <node_id>` / alias `15`  
**Definition:** nodes that share a common parent or child via the same type of edge.

```aql
LET via_out = (
    FOR v, e IN 1..1 OUTBOUND start relation
        FOR v2, e2 IN 1..1 INBOUND v relation
            FILTER e2._from != start
            FILTER e2.relation == e.relation
            RETURN DISTINCT DOCUMENT(e2._from)
)
LET via_in = (
    FOR v, e IN 1..1 INBOUND start relation
        FOR v2, e2 IN 1..1 OUTBOUND v relation
            FILTER e2._to != start
            FILTER e2.relation == e.relation
            RETURN DISTINCT DOCUMENT(e2._to)
)
FOR n IN UNION_DISTINCT(via_out, via_in)
    FILTER n != null
    RETURN DISTINCT n
```

`via_out` finds co-parents (nodes sharing the same child via the same relation).  
`via_in` finds co-children (nodes sharing the same parent via the same relation).

---

### Goal 16 — Shortest path between two nodes

**Command:** `shortest-path <node1_id> <node2_id>` / alias `16`

```aql
FOR v IN ANY SHORTEST_PATH @start TO @end relation
    RETURN v
```

`ANY SHORTEST_PATH` ignores edge direction (as specified by the task). ArangoDB computes this server-side using Dijkstra's algorithm with equal edge weights. The result is the sequence of vertex documents along the path.

---

### Goals 17 & 18 — Distant synonyms and antonyms

**Commands:** `distant-synonyms <node_id> <distance>` / `distant-antonyms <node_id> <distance>` / aliases `17`, `18`

**Parity rules:**

| Path | Result |
|---|---|
| synonym → synonym | synonym |
| antonym → antonym | synonym |
| synonym → antonym | antonym |
| antonym → synonym | antonym |

**Algorithm:** level-by-level BFS. At each depth, all frontier nodes are expanded in a single AQL query:

```aql
FOR start IN @starts
    FOR v, e IN 1..1 ANY start relation
        FILTER e.relation IN ["/r/Synonym", "/r/Antonym"]
        RETURN { start: start, vid: v._id, relation: e.relation }
```

This reduces network round-trips from O(total frontier nodes × distance) to exactly O(distance).

**State tracking:** `visited` is keyed by node handle. Each entry stores the minimum distance and a set of all parities reachable at that distance. A node encountered at the same minimum distance via two paths of different parity is recorded for both, ensuring neither synonym nor antonym results are dropped. Nodes already visited at a shorter distance are never re-expanded.

---

## 7. Student Roles

| Student | Contributions |
|---|---|
| **Wilczyński** | Local Docker environment setup (`setup_env.ps1`), data importer (`import_cskg.py`), project environment configuration, Python dependency management |
| **Stralchonak** | Query implementation and fixes, BFS optimization for distant synonyms/antonyms (batch-per-level reduction, parity bug fix), AQL query tuning, performance analysis |
| **Both** | Database schema design, collection structure decisions, index strategy |

---

## 8. Results

### Dataset summary

| Metric | Value |
|---|---|
| Total nodes | 2,160,968 |
| Total edges | 6,001,531 |
| Import time (local Docker) | ~5 min (nodes) + ~3 min (edges) |

### Example runs

**Count nodes**
```
$ python cskg_cli.py 9
2160968
```

**Successors of `/c/en/happy`** (alias `1`, with timing)
```
$ python cskg_cli.py 1 /c/en/happy --count-time
willing /c/en/willing
well /c/en/well
... (160+ results)
Query time: 0.098s
```

**Shortest path**
```
$ python cskg_cli.py 16 /c/en/happy /c/en/sad --count-time
Shortest path (1 hops):
happy /c/en/happy
sad /c/en/sad
Query time: 0.054s
```

**Distant antonyms of `/c/en/rollercoaster` at distance 17**
```
$ python cskg_cli.py 18 /c/en/rollercoaster 17 --count-time
sweat bullets /c/en/sweat_bullets/v
fair haired boy /c/en/fair_haired_boy/n
two tears in bucket /c/en/two_tears_in_bucket
que sera sera /c/en/que_sera_sera
che sara sara /c/en/che_sara_sara
everywoman /c/en/everywoman
Query time: 101.626s
```

### Complete timing results

All queries verified against expected output. Results match in value; shortest-path queries may return different intermediate nodes when multiple paths of equal length exist — this is correct behaviour.

- **Local Docker** — development machine, no network latency
- **AGH Server** — university ArangoDB instance

| # | Command | Example input | Result | Local Docker | AGH Server |
|---|---|---|---|---|---|
| 1 | successors | `/c/en/polytope` | 3 nodes | 0.090s | **0.028s** |
| 2 | count-successors | `/c/en/army` | 181 | 0.095s | **0.155s** |
| 3 | predecessors | `Q618164` | 4 nodes | 0.088s | **0.158s** |
| 4 | count-predecessors | `/c/en/root` | 634 | 0.103s | **0.347s** |
| 5 | neighbors | `/c/en/sand_cat` | 4 nodes | 0.090s | **0.147s** |
| 6 | count-neighbors | `/c/en/tower` | 254 | 0.094s | **0.094s** |
| 7 | grandchildren | `/c/en/coco` | 7 nodes | 0.089s | **0.029s** |
| 8 | grandparents | `fn:fe:deceiver` | 5 nodes | 0.087s | **0.029s** |
| 9 | count-nodes | — | 2,160,968 | 1.922s | **0.473s** |
| 10 | count-no-successors | — | 649,184 | 7.337s | **9.436s** |
| 11 | count-no-predecessors | — | 1,129,781 | 7.776s | **5.331s** |
| 12 | most-neighbors | — | `/c/en/slang` (11,038) | 2.250s | **2.250s** |
| 13 | count-single-neighbor | — | 1,276,217 | 2.234s | **2.234s** |
| 14 | rename | `/c/en/allocator` → `asdf` | OK | 0.155s | **0.040s** |
| 15 | similar | `/c/en/crystallised` | 8 nodes | 0.125s | **0.073s** |
| 16 | shortest-path | spaceship → tomato | 3 hops | 0.173s | **0.109s** |
| 16 | shortest-path | tree → cryptonymic | 6 hops | 0.175s | **0.080s** |
| 16 | shortest-path | degu → uml_class/n | 12 hops | 0.258s | **0.162s** |
| 17 | distant-synonyms | `/c/en/mediacy` dist=3 | 5 nodes | 0.255s | **0.256s** |
| 17 | distant-synonyms | `/c/en/out_with_it` dist=5 | 7 nodes | 0.352s | **0.328s** |
| 18 | distant-antonyms | `/c/en/pendulum` dist=2 | 8 nodes | 0.219s | **0.251s** |
| 18 | distant-antonyms | `/c/en/rollercoaster` dist=17 | 6 nodes | 81.432s | **207.058s** |

### Performance comparison

| Query category | Local Docker | AGH Server |
|---|---|---|
| Single-hop traversal (1–8) | ~0.09s | **~0.03–0.35s** |
| Count-nodes (9) | 1.9s | **0.47s** |
| Count-no-successors (10) | 34.9s | **9.4s** |
| Count-no-predecessors (11) | 7.8s | **5.3s** |
| Most-neighbors (12) | 2.25s | **2.25s** |
| Count-single-neighbor (13) | 2.23s | **2.23s** |
| Rename (14) | 0.155s | **0.040s** |
| Similar (15) | 0.125s | **0.073s** |
| Shortest-path (16) | ~0.2s | **~0.1s** |
| Distant syn/ant dist≤5 (17–18) | ~0.3s | **~0.3s** |
| Distant-antonyms dist=17 (18) | 81.4s | **207.1s** |

The primary performance gains came from:
1. **Local Docker / AGH Server** — eliminates or reduces network latency vs the ArangoDB Cloud instance.
2. **BFS batch-per-level** — reduces round-trips for `distant-synonyms/antonyms` from O(millions) to exactly O(distance) queries.
3. **Persistent index on `id_original`** — node resolution drops from a full collection scan (~2M documents) to a single indexed lookup.
4. **AQL `COLLECT WITH AGGREGATE` for queries 12/13** — degree computation moved fully server-side with a file cache for subsequent calls.

---

## 9. User Manual

### Quick reference — numeric aliases

| # | Command | Arguments |
|---|---|---|
| 0 | delete | `node_id` |
| 1 | successors | `node_id` |
| 2 | count-successors | `node_id` |
| 3 | predecessors | `node_id` |
| 4 | count-predecessors | `node_id` |
| 5 | neighbors | `node_id` |
| 6 | count-neighbors | `node_id` |
| 7 | grandchildren | `node_id` |
| 8 | grandparents | `node_id` |
| 9 | count-nodes | _(none)_ |
| 10 | count-no-successors | _(none)_ |
| 11 | count-no-predecessors | _(none)_ |
| 12 | most-neighbors | _(none)_ |
| 13 | count-single-neighbor | _(none)_ |
| 14 | rename | `old_node_id new_node_id new_label` |
| 15 | similar | `node_id` |
| 16 | shortest-path | `node1_id node2_id` |
| 17 | distant-synonyms | `node_id distance` |
| 18 | distant-antonyms | `node_id distance` |

### Default connection values

The CLI defaults to the local Docker instance. No connection flags are needed for local use:

```
--host     localhost
--port     8529
--db       DB_Project
--user     root
--password localpass
```

Override any of these flags to point at another server (e.g. the university cloud).

### Global flag

`--count-time` — prints query execution time after results. Can appear anywhere in the command line.

### Running queries — step by step

**1. Start the local environment (if not already running)**
```powershell
.\setup_env.ps1 -SkipImport
```

**2. Run any query using numeric alias or full command name**
```bash
# By alias
python cskg_cli.py 1 /c/en/dog
python cskg_cli.py 18 /c/en/rollercoaster 17 --count-time

# By full name
python cskg_cli.py successors /c/en/dog
python cskg_cli.py distant-antonyms /c/en/rollercoaster 17

# Against university server
python cskg_cli.py --host uni.server.edu --password secret 1 /c/en/dog
```

**3. Stop the container when done**
```powershell
docker stop cskg_arangodb
```

Data is preserved. Next time, just run `.\setup_env.ps1 -SkipImport` to restart.

### Reproducing the results step by step

1. Install Docker Desktop and Python 3.9+.
2. Install dependencies: `pip install python-arango tqdm`
3. Place `cskg.tsv` in the project directory.
4. Run `.\setup_env.ps1` — wait for completion (~8–12 minutes).
5. Run `python cskg_cli.py 9` — expected output: `2160968`.
6. Run `python cskg_cli.py 18 /c/en/rollercoaster 17 --count-time` — expected: 6 results, ~100s.

---

## 10. Self-Evaluation

### Efficiency summary

The majority of queries (1–8, 14–16) execute in **under 0.3 seconds** locally, which is acceptable for interactive CLI use. The main performance bottlenecks are:

**Slow queries and their causes:**

| Query | Time | Root cause |
|---|---|---|
| count-no-successors (10) | 34.9s | AQL must aggregate all 6M edge `_from` values server-side |
| most-neighbors (12) | 20.5s | All 6M edges streamed into Python to build a degree map |
| count-single-neighbor (13) | 22.2s | Same edge stream as query 12 |
| count-no-predecessors (11) | 7.8s | AQL aggregation over all edge `_to` values |
| distant-antonyms dist=17 (18) | 81.4s | BFS frontier grows exponentially with depth across the synonym/antonym subgraph |

### Identified shortcomings and mitigation strategies

**1. Queries 10, 11 — full edge aggregation**

Currently computed via a server-side `COLLECT` over all edges. A potential mitigation is to maintain a degree counter on each node document at import time (pre-computing successor/predecessor counts as node fields). This would turn both queries into a single indexed `FILTER` count, reducing time from ~35s to milliseconds. Trade-off: import becomes more complex and rename/delete operations must update counters.

**2. Queries 12, 13 — Python-side degree computation (resolved)**

~~Both stream all 6M edges into Python RAM and build a neighbour set per node.~~

**Implemented fix:** degree computation was moved fully server-side using AQL `COLLECT WITH AGGREGATE COUNT_DISTINCT`. A file cache (`.cskg_degrees.json`) stores the result after the first run and is invalidated automatically on any write operation (`rename`, `delete`). Results on the AGH server: **2.250s** (first call, cold) and **~0s** (subsequent calls, cache hit), down from ~20s with Python streaming. Both approaches were tested; the AQL approach proved significantly faster in practice despite the sort-based aggregation cost.

**3. Distant synonyms/antonyms at large distances (query 17, 18)**

The BFS frontier grows exponentially. At distance 17, hundreds of thousands of nodes are expanded per level. Mitigation strategies:
- **Bidirectional BFS**: expand from both the start node and the target simultaneously, meeting in the middle. This reduces the maximum frontier size from O(b^d) to O(b^(d/2)) where b is the average branching factor.
- **ArangoDB RocksDB block cache increase**: configuring a 4 GB block cache (vs the current ~500 MB default) would keep the synonym/antonym edge subgraph warm in memory, dramatically reducing per-level query time after the first run.
- **Pre-materialised synonym/antonym subgraph**: create a separate edge collection containing only `/r/Synonym` and `/r/Antonym` edges at import time. This eliminates the `FILTER e.relation IN [...]` cost on every BFS level and reduces the data scanned per level significantly.

**4. Cloud deployment**

The ArangoDB Cloud instance used during initial development added ~100ms per HTTP round-trip. At distance 17, even with the batch-per-level optimisation, this translates to at minimum 1.7 seconds of pure latency overhead (17 × 100ms) before any computation. The local Docker deployment eliminates this entirely. For university server deployment, ensuring the server is on a low-latency network path is important for interactive usability of deep BFS queries.

**5. Result ordering**

ArangoDB does not guarantee a stable document iteration order without an explicit `SORT`. Current output order is non-deterministic across runs. Adding `SORT v.id_original` to traversal queries would make output reproducible, at a small performance cost.

---
