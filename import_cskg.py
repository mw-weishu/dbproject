"""
CSKG → ArangoDB importer (Windows / python-arango)
===================================================
Handles the most common pitfalls:
  1. Embedded quotes in TSV fields  (e.g.  5.7" screen)
  2. Header row accidentally inserted as data
  3. Batch-size tuning to avoid OOM / timeout on large uploads
  4. ArangoDB _key character restrictions
  5. Duplicate nodes / edges (upsert semantics)
  6. Multi-value pipe-separated labels
  7. Network retries on transient failures
  8. Progress reporting with ETA

Usage:
    pip install python-arango tqdm
    python import_cskg.py                           # defaults
    python import_cskg.py --file cskg.tsv --batch 500
    python import_cskg.py --dry-run                 # parse only, no DB writes
"""

import argparse
import gzip
import hashlib
import os
import random
import re
import sys
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

try:
    from arango import ArangoClient
except ImportError:
    sys.exit(
        "ERROR: python-arango is not installed.\n"
        "Run:  pip install python-arango"
    )

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None  # graceful fallback

# ──────────────────────────────────────────────
# Configuration defaults  (override via CLI args)
# ──────────────────────────────────────────────
DEFAULTS = dict(
    file="cskg.tsv",
    url="https://d1b0a8055389.arangodb.cloud:8529",
    user="root",
    password="mkD0PXhHS1GRzAlBe6R8",
    db="DB_Project",
    node_coll="nodes",
    edge_coll="relation",
    batch=2000,          # lower default keeps throughput steady on cloud tiers
    max_retries=5,       # retries on transient errors
    threads=4,           # fixed parallel upload threads
    timeout=60,           # HTTP request timeout in seconds
    dry_run=False,
)

# CSKG column names (KGTK format, order matters for positional fallback)
EXPECTED_HEADERS = [
    "id", "node1", "relation", "node2",
    "node1;label", "node2;label", "relation;label",
    "relation;dimension", "source", "sentence",
]

# ──────────────────────────────────────────────
# Key sanitisation
# ──────────────────────────────────────────────
# ArangoDB _key allows:  a-z A-Z 0-9  _ - : . @ ( ) + , = ; ! * ' %
# Max length: 254 bytes.  We hash if longer or if chars are outside the set.
_SAFE_KEY_RE = re.compile(r"^[A-Za-z0-9_\-:.@()+,=;!*'%]+$")


def _percent_encode_char(m: re.Match) -> str:
    """Percent-encode a single character (may be multi-byte UTF-8)."""
    char = m.group(0)
    return "".join(f"%{b:02X}" for b in char.encode("utf-8"))


def to_key(raw: str) -> str:
    """Return an ArangoDB-safe _key from an arbitrary string.

    Uses percent-encoding for unsafe characters so that distinct IDs
    never collide.  E.g. '/' → '%2F', ' ' → '%20', '"' → '%22'.
    """
    raw = raw.strip()
    if not raw:
        return "_empty_"
    # Fast path: already safe
    if _SAFE_KEY_RE.match(raw) and len(raw) <= 254:
        return raw
    # Percent-encode every character NOT in ArangoDB's allowed _key set
    safe = re.sub(r"[^A-Za-z0-9_\-:.@()+,=;!*'%]", _percent_encode_char, raw)
    if len(safe) <= 254:
        return safe
    # Too long → use full SHA-256 hash to guarantee uniqueness
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return h


# ──────────────────────────────────────────────
# TSV reader that survives embedded quotes
# ──────────────────────────────────────────────
def robust_tsv_reader(filepath: str):
    """
    Yields dicts keyed by column name.
    Handles:
      - bare double-quotes inside fields  (e.g. 5.7" screen)
      - fields that START with a quote but aren't properly closed
      - BOM on first line
    Strategy: read raw lines → split on TAB (never let csv interpret quotes).
    """
    with open(filepath, "r", encoding="utf-8-sig", newline="") as fh:
        # ── Read header ──
        header_line = fh.readline()
        if not header_line:
            raise ValueError("File is empty")
        headers = header_line.rstrip("\n\r").split("\t")
        headers = [h.strip() for h in headers]
        num_cols = len(headers)

        # ── Validate header looks like CSKG ──
        lower_headers = [h.lower() for h in headers]
        required = {"node1", "relation", "node2"}
        if not required.issubset(set(lower_headers)):
            # Try common aliases
            alias_map = {"from": "node1", "subject": "node1",
                         "to": "node2", "object": "node2",
                         "label": "relation", "predicate": "relation",
                         "relationship": "relation"}
            mapped = [alias_map.get(h, h) for h in lower_headers]
            if not required.issubset(set(mapped)):
                raise ValueError(
                    f"Header row doesn't look like CSKG.\n"
                    f"  Expected at least: {required}\n"
                    f"  Got: {headers}"
                )
            headers = [alias_map.get(h.lower(), h) for h in headers]

        line_no = 1
        for raw_line in fh:
            line_no += 1
            line = raw_line.rstrip("\n\r")
            if not line or line.startswith("#"):
                continue

            fields = line.split("\t")

            # Pad or truncate to match header count
            if len(fields) < num_cols:
                fields.extend([""] * (num_cols - len(fields)))
            elif len(fields) > num_cols:
                # Merge excess into last column (common with embedded tabs)
                fields = fields[:num_cols - 1] + [
                    "\t".join(fields[num_cols - 1:])
                ]

            row = dict(zip(headers, fields))

            # ── GUARD: skip if this row IS the header again ──
            # (happens when files are concatenated or have repeated headers)
            if row.get("node1", "").lower() == "node1" and \
               row.get("relation", "").lower() == "relation":
                continue

            row["__line__"] = line_no
            yield row


# ──────────────────────────────────────────────
# Count lines for progress bar
# ──────────────────────────────────────────────
def count_lines(filepath: str) -> int:
    """Fast line count (binary read)."""
    count = 0
    with open(filepath, "rb") as f:
        buf = f.raw.read(1024 * 1024)
        while buf:
            count += buf.count(b"\n")
            buf = f.raw.read(1024 * 1024)
    return count


class SimpleProgress:
    """Plain-text progress fallback that prints to stdout with rate + ETA."""

    def __init__(self, total: int, unit: str, desc: str, report_every: float = 1.0):
        self.total = max(0, int(total))
        self.unit = unit.strip() or "items"
        self.desc = desc.strip() or "Progress"
        self.report_every = max(0.2, float(report_every))
        self.current = 0
        self.start = time.monotonic()
        self.last_report = 0.0
        self.postfix = ""
        self._render(force=True)

    def update(self, n: int = 1):
        self.current += int(n)
        self._render(force=False)

    def set_postfix_str(self, text: str):
        self.postfix = text.strip()
        self._render(force=False)

    def refresh(self):
        self._render(force=False)

    def close(self):
        self._render(force=True)
        print()

    def _render(self, force: bool):
        now = time.monotonic()
        if not force and (now - self.last_report) < self.report_every:
            return
        self.last_report = now
        elapsed = max(now - self.start, 1e-9)
        rate = self.current / elapsed
        if self.total > 0:
            pct = min(100.0, (self.current / self.total) * 100.0)
            remaining = max(0, self.total - self.current)
            eta = remaining / rate if rate > 0 else float("inf")
            eta_text = f"ETA {eta:,.1f}s" if eta != float("inf") else "ETA --"
            body = (f"{self.current:,}/{self.total:,} {self.unit} "
                    f"({pct:5.1f}%) {rate:,.1f} {self.unit}/s {eta_text}")
        else:
            body = f"{self.current:,} {self.unit} {rate:,.1f} {self.unit}/s"
        if self.postfix:
            body = f"{body} | {self.postfix}"
        print(f"\r{self.desc} {body}", end="", flush=True)


def make_progress(total: int, unit: str, desc: str):
    """Create a progress reporter that is visible in regular console output."""
    if tqdm:
        return tqdm(
            total=total,
            unit=unit,
            desc=desc,
            file=sys.stdout,
            dynamic_ncols=True,
            mininterval=1.0,
            leave=True,
            disable=False,
        )
    return SimpleProgress(total=total, unit=unit, desc=desc)


# ──────────────────────────────────────────────
# Batch insert with retry
# ──────────────────────────────────────────────
def batch_insert(collection, docs: list, on_dup: str = "ignore",
                 max_retries: int = 5, label: str = "docs"):
    """
    Bulk-import a batch via /_api/import (much faster than insert_many).
    Returns (inserted_count, skipped_count, error_count, elapsed_secs).
    """
    inserted = 0
    skipped = 0
    errors = 0
    t0 = time.monotonic()

    for attempt in range(1, max_retries + 1):
        try:
            result = collection.import_bulk(
                docs,
                on_duplicate=on_dup,
            )
            # import_bulk returns: {created, errors, empty, updated, ignored, details}
            inserted += result.get("created", 0) + result.get("updated", 0)
            skipped += result.get("ignored", 0)
            errors += result.get("errors", 0)
            return inserted, skipped, errors, time.monotonic() - t0

        except Exception as e:
            if attempt < max_retries:
                base = min(2 ** attempt, 30)
                wait_time = base + random.uniform(0, base * 0.5)
                print(f"  ⚠ Transient error ({e}), retry {attempt}/{max_retries} "
                      f"(wait {wait_time:.1f}s) …")
                time.sleep(wait_time)
                continue
            print(f"  ✗ Batch of {len(docs)} {label} failed: {e}")
            errors += len(docs)
            return inserted, skipped, errors, time.monotonic() - t0

    return inserted, skipped, errors, time.monotonic() - t0


def fixed_upload(collection, batches, threads, max_retries, label,
                 progress=None, on_dup="ignore"):
    """Upload batches with constant in-flight concurrency."""
    threads = max(1, int(threads))
    total_ins = 0
    total_skip = 0
    total_err = 0

    with ThreadPoolExecutor(max_workers=threads) as pool:
        inflight = {}  # future -> batch_len
        batch_iter = iter(batches)
        exhausted = False
        submitted_batches = 0
        completed_batches = 0

        def _submit_next():
            """Submit one batch if available and under in-flight limit."""
            nonlocal exhausted, submitted_batches
            if exhausted or len(inflight) >= threads:
                return False
            batch = next(batch_iter, None)
            if batch is None:
                exhausted = True
                return False
            fut = pool.submit(
                batch_insert, collection, batch,
                on_dup=on_dup, max_retries=max_retries, label=label)
            inflight[fut] = len(batch)
            submitted_batches += 1
            return True

        while inflight or not exhausted:
            # Fill available worker slots.
            while _submit_next():
                pass

            if not inflight:
                break

            done, _ = wait(
                inflight.keys(),
                timeout=1.0,
                return_when=FIRST_COMPLETED,
            )
            if not done:
                if progress:
                    progress.set_postfix_str(
                        f"batches {completed_batches}/{submitted_batches}, "
                        f"inflight={len(inflight)}"
                    )
                    if hasattr(progress, "refresh"):
                        progress.refresh()
                continue

            for fut in done:
                batch_len = inflight.pop(fut)
                ins, skp, err, _elapsed = fut.result()
                completed_batches += 1
                total_ins += ins
                total_skip += skp
                total_err += err
                if progress:
                    progress.update(batch_len)
                    progress.set_postfix_str(
                        f"batches {completed_batches}/{submitted_batches}, "
                        f"inflight={len(inflight)}"
                    )

    return total_ins, total_skip, total_err


# ──────────────────────────────────────────────
# Main import logic
# ──────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Import CSKG tsv into ArangoDB (nodes + edges)")
    parser.add_argument("--file",     default=DEFAULTS["file"])
    parser.add_argument("--url",      default=DEFAULTS["url"])
    parser.add_argument("--user",     default=DEFAULTS["user"])
    parser.add_argument("--password", default=DEFAULTS["password"])
    parser.add_argument("--db",       default=DEFAULTS["db"])
    parser.add_argument("--node-coll", default=DEFAULTS["node_coll"])
    parser.add_argument("--edge-coll", default=DEFAULTS["edge_coll"])
    parser.add_argument("--batch",    type=int, default=DEFAULTS["batch"])
    parser.add_argument("--max-retries", type=int, default=DEFAULTS["max_retries"])
    parser.add_argument("--threads",  type=int, default=DEFAULTS["threads"],
                        help="Parallel upload threads (default 4)")
    parser.add_argument("--timeout",  type=int, default=DEFAULTS["timeout"],
                        help="HTTP request timeout in seconds (default 300)")
    parser.add_argument("--dry-run",  action="store_true")
    parser.add_argument("--skip-nodes", action="store_true",
                        help="Skip node import (if already loaded)")
    parser.add_argument("--skip-edges", action="store_true",
                        help="Skip edge import (if already loaded)")
    parser.add_argument("--fresh", action="store_true",
                        help="Truncate collections first (fastest: avoids "
                             "on_duplicate=replace read-before-write overhead)")
    args = parser.parse_args()

    if args.batch < 1:
        sys.exit("ERROR: --batch must be >= 1")
    if args.threads < 1:
        sys.exit("ERROR: --threads must be >= 1")

    # ── Validate file ──
    if not os.path.isfile(args.file):
        sys.exit(f"ERROR: File not found: {args.file}")

    print(f"╔══════════════════════════════════════════════╗")
    print(f"║   CSKG → ArangoDB Importer                  ║")
    print(f"╠══════════════════════════════════════════════╣")
    print(f"║ File : {args.file:<37s} ║")
    print(f"║ URL  : {args.url:<37s} ║")
    print(f"║ DB   : {args.db:<37s} ║")
    print(f"║ Nodes: {args.node_coll:<37s} ║")
    print(f"║ Edges: {args.edge_coll:<37s} ║")
    print(f"║ Batch: {str(args.batch):<37s} ║")
    print(f"╚══════════════════════════════════════════════╝")

    if args.dry_run:
        print("\n*** DRY RUN — no data will be written ***\n")

    # ── Phase 0: Connect ──
    if not args.dry_run:
        print("\n[0/4] Connecting to ArangoDB …")
        import requests
        from arango.http import DefaultHTTPClient
        from arango.response import Response

        class TunedHTTPClient(DefaultHTTPClient):
            """HTTP client with larger pool, guaranteed timeout, gzip."""

            def __init__(self, timeout, pool_size):
                self._custom_timeout = timeout
                self._pool_size = pool_size
                try:
                    super().__init__(request_timeout=timeout)
                except TypeError:
                    super().__init__()
                self.REQUEST_TIMEOUT = timeout
                self._request_timeout = timeout

            def create_session(self, host):
                session = requests.Session()
                adapter = requests.adapters.HTTPAdapter(
                    pool_connections=self._pool_size,
                    pool_maxsize=self._pool_size,
                    max_retries=0,
                )
                session.mount("https://", adapter)
                session.mount("http://", adapter)
                return session

            def send_request(self, session, method, url,
                             headers=None, params=None, data=None,
                             auth=None):
                """Override to guarantee timeout and send gzip'd bodies."""
                if headers is None:
                    headers = {}
                # Gzip compress request bodies > 1 KB
                if data and len(data) > 1024:
                    compressed = gzip.compress(
                        data.encode("utf-8") if isinstance(data, str) else data,
                        compresslevel=1)  # fast compression
                    if len(compressed) < len(data if isinstance(data, bytes) else data.encode("utf-8")):
                        data = compressed
                        headers["Content-Encoding"] = "gzip"
                headers["Accept-Encoding"] = "gzip, deflate"
                resp = session.request(
                    method, url,
                    params=params, data=data, headers=headers, auth=auth,
                    timeout=self._custom_timeout,
                )
                return Response(
                    method=method,
                    url=str(resp.url),
                    headers=resp.headers,
                    status_code=resp.status_code,
                    status_text=resp.reason,
                    raw_body=resp.text,
                )

        pool_size = args.threads + 2
        http_client = TunedHTTPClient(
            timeout=args.timeout, pool_size=pool_size)
        client = ArangoClient(hosts=args.url, http_client=http_client)
        print(f"  ✓ HTTP timeout={args.timeout}s, pool={pool_size}")

        # Connect to _system first to ensure DB exists
        try:
            sys_db = client.db("_system", username=args.user,
                               password=args.password, verify=True)
            if not sys_db.has_database(args.db):
                print(f"  Creating database '{args.db}' …")
                sys_db.create_database(args.db)
        except Exception as e:
            # Cloud instances may not allow _system access;
            # try connecting directly to the target DB
            print(f"  (Could not access _system: {e})")
            print(f"  Trying direct connection to '{args.db}' …")

        db = client.db(args.db, username=args.user,
                       password=args.password, verify=True)
        print(f"  ✓ Connected to '{args.db}'")

        # Ensure collections exist
        if not db.has_collection(args.node_coll):
            db.create_collection(args.node_coll)
            print(f"  ✓ Created node collection '{args.node_coll}'")
        else:
            print(f"  ✓ Node collection '{args.node_coll}' exists")

        if not db.has_collection(args.edge_coll):
            db.create_collection(args.edge_coll, edge=True)
            print(f"  ✓ Created edge collection '{args.edge_coll}'")
        else:
            print(f"  ✓ Edge collection '{args.edge_coll}' exists")

        nodes_coll = db.collection(args.node_coll)
        edges_coll = db.collection(args.edge_coll)

        # Disable waitForSync for bulk import
        try:
            nodes_coll.configure(sync=False)
            edges_coll.configure(sync=False)
            print(f"  ✓ waitForSync disabled (bulk import mode)")
        except Exception:
            pass

        # --fresh: truncate collections for fastest possible insert
        if args.fresh:
            print("  ⚠ --fresh: truncating collections …")
            if not args.skip_nodes:
                nodes_coll.truncate()
                print(f"    ✓ '{args.node_coll}' truncated")
            if not args.skip_edges:
                edges_coll.truncate()
                print(f"    ✓ '{args.edge_coll}' truncated")

    else:
        nodes_coll = None
        edges_coll = None

    # ── Phase 1: Scan file — collect unique nodes ──
    print("\n[1/4] Scanning TSV for unique nodes …")
    total_lines = count_lines(args.file)

    # OrderedDict preserves insertion order; value = node metadata dict
    node_map = OrderedDict()   # key → {_key, label, …}
    edge_count = 0

    progress = make_progress(total=total_lines, unit="lines", desc="  Scan")
    row_count = 0
    skipped_rows = 0

    for row in robust_tsv_reader(args.file):
        row_count += 1
        if progress:
            progress.update(1)

        n1_raw = row.get("node1", "").strip()
        n2_raw = row.get("node2", "").strip()
        # Skip blank rows
        if not n1_raw or not n2_raw:
            skipped_rows += 1
            continue

        n1_key = to_key(n1_raw)
        n2_key = to_key(n2_raw)

        # Collect node1
        if n1_key not in node_map:
            labels = row.get("node1;label", "").strip()
            doc = {"_key": n1_key, "id_original": n1_raw}
            doc["label"] = labels.split("|")[0] if labels else n1_raw
            if labels:
                doc["labels"] = labels
            node_map[n1_key] = doc

        # Collect node2
        if n2_key not in node_map:
            labels = row.get("node2;label", "").strip()
            doc = {"_key": n2_key, "id_original": n2_raw}
            doc["label"] = labels.split("|")[0] if labels else n2_raw
            if labels:
                doc["labels"] = labels
            node_map[n2_key] = doc

        edge_count += 1

    if progress:
        progress.close()

    print(f"  ✓ {row_count:,} data rows scanned  "
          f"({skipped_rows:,} blank/skipped)")
    print(f"  ✓ {len(node_map):,} unique nodes found")
    print(f"  ✓ {edge_count:,} edges found")

    # ── Phase 2: Upload nodes ──
    if args.skip_nodes:
        print("\n[2/4] Skipping node upload (--skip-nodes)")
    else:
        print(f"\n[2/4] Uploading {len(node_map):,} nodes "
              f"(batch={args.batch}, threads={args.threads}) …")
        if not args.dry_run:
            # With --fresh: truncated → plain insert (no duplicates expected)
            # Without --fresh: replace to upsert existing nodes
            node_on_dup = "ignore" if args.fresh else "replace"
            node_list = list(node_map.values())
            batches = (node_list[i:i + args.batch]
                       for i in range(0, len(node_list), args.batch))

            progress = make_progress(total=len(node_list), unit="nodes", desc="  Nodes")

            total_ins, total_skip, total_err = fixed_upload(
                nodes_coll, batches, args.threads,
                args.max_retries, "nodes", progress,
                on_dup=node_on_dup)

            if progress:
                progress.close()

            print(f"  ✓ Nodes — inserted: {total_ins:,}  "
                  f"replaced: {total_skip:,}  errors: {total_err:,}")
        else:
            print("  (dry run — skipped)")

    # ── Phase 3: Upload edges ──
    if args.skip_edges:
        print("\n[3/4] Skipping edge upload (--skip-edges)")
    else:
        print(f"\n[3/4] Uploading {edge_count:,} edges "
              f"(batch={args.batch}, threads={args.threads}) …")
        if not args.dry_run:
            def edge_batches():
                batch = []
                for row in robust_tsv_reader(args.file):
                    n1_raw = row.get("node1", "").strip()
                    n2_raw = row.get("node2", "").strip()
                    if not n1_raw or not n2_raw:
                        continue

                    n1_key = to_key(n1_raw)
                    n2_key = to_key(n2_raw)
                    relation = row.get("relation", "").strip()
                    edge_doc = {
                        "_from": f"{args.node_coll}/{n1_key}",
                        "_to":   f"{args.node_coll}/{n2_key}",
                        "relation": relation,
                    }
                    # Only include non-empty optional fields (saves ~20-30% payload)
                    relation_label = row.get("relation;label", "").strip()
                    relation_dimension = row.get("relation;dimension", "").strip()
                    source = row.get("source", "").strip()
                    sentence = row.get("sentence", "").strip()
                    edge_id = row.get("id", "").strip()

                    if relation_label:
                        edge_doc["relation_label"] = relation_label
                    if relation_dimension:
                        edge_doc["relation_dimension"] = relation_dimension
                    if source:
                        edge_doc["source"] = source
                    if sentence:
                        edge_doc["sentence"] = sentence
                    if edge_id:
                        edge_doc["_key"] = to_key(edge_id)
                    else:
                        raw = f"{n1_key}|{relation}|{n2_key}"
                        edge_doc["_key"] = to_key(raw)

                    batch.append(edge_doc)
                    if len(batch) >= args.batch:
                        yield batch
                        batch = []

                if batch:
                    yield batch

            progress = make_progress(total=edge_count, unit="edges", desc="  Edges")

            # Edges have deterministic _keys; "ignore" avoids write-write conflicts
            total_ins, total_skip, total_err = fixed_upload(
                edges_coll, edge_batches(), args.threads,
                args.max_retries, "edges", progress,
                on_dup="ignore")

            if progress:
                progress.close()

            print(f"  ✓ Edges — inserted: {total_ins:,}  "
                  f"replaced: {total_skip:,}  errors: {total_err:,}")
        else:
            print("  (dry run — skipped)")

    print("\n[4/5] Verification …")
    if not args.dry_run:
        n_count = nodes_coll.count()
        e_count = edges_coll.count()
        print(f"  ✓ Collection '{args.node_coll}': {n_count:,} documents")
        print(f"  ✓ Collection '{args.edge_coll}': {e_count:,} documents")
    else:
        print(f"  (dry run) Would have uploaded "
              f"{len(node_map):,} nodes + {edge_count:,} edges")

    # ── Phase 5: Create indexes ──
    # Indexes are idempotent — safe to re-run on an already-indexed collection.
    print("\n[5/5] Creating indexes …")
    if not args.dry_run:
        # nodes.id_original — every resolve_handle() lookup filters on this field
        nodes_coll.add_persistent_index(
            fields=["id_original"], unique=False, sparse=False)
        print(f"  ✓ Persistent index on '{args.node_coll}.id_original'")

        # relation.relation — BFS synonym/antonym filtering uses this field
        edges_coll.add_persistent_index(
            fields=["relation"], unique=False, sparse=False)
        print(f"  ✓ Persistent index on '{args.edge_coll}.relation'")

        # _from / _to on edge collections are indexed automatically by ArangoDB
        print(f"  ✓ Edge indexes on _from / _to are managed automatically")
    else:
        print("  (dry run — skipped)")

    print("\n✓ Done.")


if __name__ == "__main__":
    main()
