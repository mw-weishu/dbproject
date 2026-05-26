#!/usr/bin/env python3
"""
CSKG Command Line Tool
Usage: python cskg_cli.py --host <host> --port <port> --db <db>
                          --user <user> --password <pass>
                          <command> [args...]

Commands:
  successors <node_id>
  count-successors <node_id>
  predecessors <node_id>
  count-predecessors <node_id>
  neighbors <node_id>
  count-neighbors <node_id>
  grandchildren <node_id>
  grandparents <node_id>
  count-nodes
  count-no-successors
  count-no-predecessors
  most-neighbors
  count-single-neighbor
  rename <old_node_id> <new_node_id> <new_label>
  similar <node_id>
  shortest-path <node1_id> <node2_id>
  distant-synonyms <node_id> <distance>
  distant-antonyms <node_id> <distance>

  delete <node_id>
"""

import argparse
import sys
from urllib.parse import quote, unquote
from arango import ArangoClient
from arango.http import DefaultHTTPClient

# ---------------------------------------------------------------------------
# Schema constants — update here if collection/field names ever change
# ---------------------------------------------------------------------------
NODE_COLLECTION = "nodes"
EDGE_COLLECTION = "relation"
ID_FIELD        = "id_original"   # human-readable original node ID
LABEL_FIELD     = "label"


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------

def connect(host: str, port: int, db: str, user: str, password: str):
    # Strip any scheme the caller may have included to avoid double-scheme URLs
    for scheme in ("https://", "http://"):
        if host.startswith(scheme):
            host = host[len(scheme):]
            break
    http_client = DefaultHTTPClient(request_timeout=600)  # 10-minute timeout
    client = ArangoClient(hosts=f"https://{host}:{port}", http_client=http_client)
    return client.db(db, username=user, password=password, verify=True)


# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------

def encode_key(node_id: str) -> str:
    """URL-encode a node_id to match the _key stored in ArangoDB."""
    return quote(node_id, safe="")


def node_handle(node_id: str) -> str:
    """Return the full document handle: nodes/<url-encoded-key>"""
    return f"{NODE_COLLECTION}/{encode_key(node_id)}"


def resolve_handle(database, node_id: str) -> str:
    """
    Verify the node exists and return its handle.
    Accepts either a raw id_original (e.g. /c/en/©) or a
    handle-style input (e.g. nodes/%2Fc%2Fen%2F%C2%A9).
    """
    # Strip collection prefix + URL-decode if caller passed a handle
    prefix = NODE_COLLECTION + "/"
    if node_id.startswith(prefix):
        node_id = unquote(node_id[len(prefix):])
    else:
        node_id = unquote(node_id)
    aql = f"""
    FOR n IN {NODE_COLLECTION}
        FILTER n.{ID_FIELD} == @id
        LIMIT 1
        RETURN n._id
    """
    cursor = database.aql.execute(aql, bind_vars={"id": node_id})
    results = list(cursor)
    if not results:
        print(f"Error: node '{node_id}' not found.", file=sys.stderr)
        sys.exit(1)
    return results[0]


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_nodes(rows):
    if not rows:
        print("(no results)")
        return
    for r in rows:
        print(f"{r.get(LABEL_FIELD, '')} {r.get(ID_FIELD, r.get('_id', '?'))}")


def print_count(n: int):
    print(n)


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

def successors(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"FOR v IN 1..1 OUTBOUND @start {EDGE_COLLECTION} RETURN DISTINCT v"
    print_nodes(list(db.aql.execute(aql, bind_vars={"start": handle})))


def count_successors(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"RETURN COUNT(FOR v IN 1..1 OUTBOUND @start {EDGE_COLLECTION} RETURN DISTINCT v._key)"
    print_count(list(db.aql.execute(aql, bind_vars={"start": handle}))[0])


def predecessors(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"FOR v IN 1..1 INBOUND @start {EDGE_COLLECTION} RETURN DISTINCT v"
    print_nodes(list(db.aql.execute(aql, bind_vars={"start": handle})))


def count_predecessors(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"RETURN COUNT(FOR v IN 1..1 INBOUND @start {EDGE_COLLECTION} RETURN DISTINCT v._key)"
    print_count(list(db.aql.execute(aql, bind_vars={"start": handle}))[0])


def neighbors(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"FOR v IN 1..1 ANY @start {EDGE_COLLECTION} RETURN DISTINCT v"
    print_nodes(list(db.aql.execute(aql, bind_vars={"start": handle})))


def count_neighbors(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"RETURN COUNT(FOR v IN 1..1 ANY @start {EDGE_COLLECTION} RETURN DISTINCT v._key)"
    print_count(list(db.aql.execute(aql, bind_vars={"start": handle}))[0])


def grandchildren(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"FOR v IN 2..2 OUTBOUND @start {EDGE_COLLECTION} RETURN DISTINCT v"
    print_nodes(list(db.aql.execute(aql, bind_vars={"start": handle})))


def grandparents(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"FOR v IN 2..2 INBOUND @start {EDGE_COLLECTION} RETURN DISTINCT v"
    print_nodes(list(db.aql.execute(aql, bind_vars={"start": handle})))


def count_nodes(db):
    aql = f"RETURN COUNT(FOR n IN {NODE_COLLECTION} RETURN 1)"
    print_count(list(db.aql.execute(aql))[0])


def count_no_successors(db):
    # Use COLLECT (sort-based) instead of DISTINCT to count unique _from values
    aql = f"""
    LET total = LENGTH({NODE_COLLECTION})
    LET with_successors = LENGTH(
        FOR e IN {EDGE_COLLECTION}
            COLLECT _from = e._from
            RETURN 1
    )
    RETURN total - with_successors
    """
    print_count(list(db.aql.execute(aql))[0])


def count_no_predecessors(db):
    # Use COLLECT (sort-based) instead of DISTINCT to count unique _to values
    aql = f"""
    LET total = LENGTH({NODE_COLLECTION})
    LET with_predecessors = LENGTH(
        FOR e IN {EDGE_COLLECTION}
            COLLECT _to = e._to
            RETURN 1
    )
    RETURN total - with_predecessors
    """
    print_count(list(db.aql.execute(aql))[0])


def _compute_degrees(db):
    """Stream all edges and return a dict: node _id -> unique neighbor count (any direction)."""
    neighbor_sets = {}
    aql = f"FOR e IN {EDGE_COLLECTION} RETURN [e._from, e._to]"
    for row in db.aql.execute(aql, batch_size=50000):
        f, t = row[0], row[1]
        if f not in neighbor_sets:
            neighbor_sets[f] = set()
        if t not in neighbor_sets:
            neighbor_sets[t] = set()
        neighbor_sets[f].add(t)
        neighbor_sets[t].add(f)
    return {k: len(v) for k, v in neighbor_sets.items()}


def most_neighbors(db):
    deg = _compute_degrees(db)

    if not deg:
        print("(no results)")
        return

    max_deg = max(deg.values())
    for node_id, d in deg.items():
        if d == max_deg:
            node = list(db.aql.execute("RETURN DOCUMENT(@h)", bind_vars={"h": node_id}))[0]
            if node:
                print(f"{node.get(LABEL_FIELD, '')} {node.get(ID_FIELD, '?')}  neighbors: {d}")


def count_single_neighbor(db):
    deg = _compute_degrees(db)
    print_count(sum(1 for d in deg.values() if d == 1))


def rename(db, old_node_id: str, new_node_id: str, new_label: str):
    handle = resolve_handle(db, old_node_id)
    key = handle.split("/")[1]

    # Abort if another node already carries new_node_id as its id_original,
    # which would create ambiguous duplicates and corrupt future lookups.
    aql_check = f"""
    FOR n IN {NODE_COLLECTION}
        FILTER n.{ID_FIELD} == @new_id
        FILTER n._id != @current
        LIMIT 1
        RETURN n._id
    """
    if list(db.aql.execute(aql_check, bind_vars={"new_id": new_node_id, "current": handle})):
        print(f"Error: a node with id '{new_node_id}' already exists.", file=sys.stderr)
        sys.exit(1)

    aql = f"""
    UPDATE @key WITH {{ {ID_FIELD}: @new_id, {LABEL_FIELD}: @new_label, labels: @new_label }}
    IN {NODE_COLLECTION}
    RETURN NEW
    """
    cursor = db.aql.execute(aql, bind_vars={
        "key": key,
        "new_id": new_node_id,
        "new_label": new_label,
    })
    result = list(cursor)
    if result:
        print(f"Renamed: {old_node_id} -> {new_node_id} [{new_label}]")
        print(f"  (internal _key '{key}' unchanged)")
    else:
        print("Rename failed.", file=sys.stderr)


def delete_node(db, node_id: str):
    handle = resolve_handle(db, node_id)
    key = handle.split("/")[1]

    # Count edges so the user knows what will be removed
    aql_count = f"""
    RETURN COUNT(
        FOR e IN {EDGE_COLLECTION}
            FILTER e._from == @handle OR e._to == @handle
            RETURN 1
    )
    """
    edge_count = list(db.aql.execute(aql_count, bind_vars={"handle": handle}))[0]

    confirm = input(
        f"Delete '{node_id}' and its {edge_count} edge(s)? [y/N] "
    ).strip().lower()
    if confirm != "y":
        print("Aborted.")
        return

    # Remove all connected edges first, then the node
    aql_edges = f"""
    FOR e IN {EDGE_COLLECTION}
        FILTER e._from == @handle OR e._to == @handle
        REMOVE e IN {EDGE_COLLECTION}
    """
    db.aql.execute(aql_edges, bind_vars={"handle": handle})

    aql_node = f"""
    REMOVE @key IN {NODE_COLLECTION}
    RETURN OLD.{ID_FIELD}
    """
    result = list(db.aql.execute(aql_node, bind_vars={"key": key}))
    if result:
        print(f"Deleted: {result[0]}  (edges removed: {edge_count})")
    else:
        print("Delete failed.", file=sys.stderr)


def similar(db, node_id):
    handle = resolve_handle(db, node_id)
    aql = f"""
    LET start = @start
    LET via_out = (
        FOR v, e IN 1..1 OUTBOUND start {EDGE_COLLECTION}
            FOR v2, e2 IN 1..1 INBOUND v {EDGE_COLLECTION}
                FILTER e2._from != start
                FILTER e2.relation == e.relation
                RETURN DISTINCT DOCUMENT(e2._from)
    )
    LET via_in = (
        FOR v, e IN 1..1 INBOUND start {EDGE_COLLECTION}
            FOR v2, e2 IN 1..1 OUTBOUND v {EDGE_COLLECTION}
                FILTER e2._to != start
                FILTER e2.relation == e.relation
                RETURN DISTINCT DOCUMENT(e2._to)
    )
    FOR n IN UNION_DISTINCT(via_out, via_in)
        FILTER n != null
        RETURN DISTINCT n
    """
    print_nodes(list(db.aql.execute(aql, bind_vars={"start": handle})))


def shortest_path(db, node1_id: str, node2_id: str):
    handle1 = resolve_handle(db, node1_id)
    handle2 = resolve_handle(db, node2_id)
    aql = f"""
    FOR v IN ANY SHORTEST_PATH @start TO @end {EDGE_COLLECTION}
        RETURN v
    """
    path = list(db.aql.execute(aql, bind_vars={"start": handle1, "end": handle2}))
    if not path:
        print(f"No path found between '{node1_id}' and '{node2_id}'.")
        return
    print(f"Shortest path ({len(path) - 1} hops):")
    for node in path:
        print(f"{node.get(LABEL_FIELD, '')} {node.get(ID_FIELD, '?')}")


def distant_synonyms_antonyms(db, node_id: str, distance: int, find: str):
    """
    BFS over synonym/antonym edges tracking parity:
      synonym-of-synonym = synonym
      antonym-of-antonym = synonym
      synonym-of-antonym = antonym
      antonym-of-synonym = antonym
    Returns nodes at exactly `distance` hops with the requested parity.
    """
    handle = resolve_handle(db, node_id)
    syn_rel = "/r/Synonym"
    ant_rel = "/r/Antonym"

    # {handle: (is_synonym_parity, min_distance)}
    visited = {handle: (True, 0)}
    frontier = [(handle, True, 0)]

    while frontier:
        next_frontier = []
        for h, is_syn, dist in frontier:
            if dist >= distance:
                continue
            aql = f"""
            FOR v, e IN 1..1 ANY @start {EDGE_COLLECTION}
                FILTER e.relation IN [@syn, @ant]
                RETURN {{ v: v, relation: e.relation }}
            """
            for row in db.aql.execute(aql, bind_vars={"start": h, "syn": syn_rel, "ant": ant_rel}):
                v_handle = row["v"]["_id"]
                new_is_syn = is_syn if row["relation"] == syn_rel else not is_syn
                new_dist = dist + 1
                if v_handle not in visited or visited[v_handle][1] > new_dist:
                    visited[v_handle] = (new_is_syn, new_dist)
                    next_frontier.append((v_handle, new_is_syn, new_dist))
        frontier = next_frontier

    want_syn = (find == "synonym")
    results = [
        h for h, (parity, d) in visited.items()
        if h != handle and parity == want_syn and d == distance
    ]

    if not results:
        print("(no results)")
        return

    for h in results:
        cursor = db.aql.execute("RETURN DOCUMENT(@h)", bind_vars={"h": h})
        node = list(cursor)[0]
        if node:
            print(f"{node.get(LABEL_FIELD, '')} {node.get(ID_FIELD, '?')}")


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        description="CSKG graph query CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--host",     default="localhost")
    p.add_argument("--port",     type=int, default=8529)
    p.add_argument("--db",       default="new_database")
    p.add_argument("--user",     default="root")
    p.add_argument("--password", default="")

    sub = p.add_subparsers(dest="command", required=True)

    def node_cmd(name):
        s = sub.add_parser(name)
        s.add_argument("node_id")
        return s

    node_cmd("successors")
    node_cmd("count-successors")
    node_cmd("predecessors")
    node_cmd("count-predecessors")
    node_cmd("neighbors")
    node_cmd("count-neighbors")
    node_cmd("grandchildren")
    node_cmd("grandparents")
    node_cmd("similar")
    node_cmd("delete")

    sub.add_parser("count-nodes")
    sub.add_parser("count-no-successors")
    sub.add_parser("count-no-predecessors")
    sub.add_parser("most-neighbors")
    sub.add_parser("count-single-neighbor")

    r = sub.add_parser("rename")
    r.add_argument("old_node_id")
    r.add_argument("new_node_id")
    r.add_argument("new_label")

    sp = sub.add_parser("shortest-path")
    sp.add_argument("node1_id")
    sp.add_argument("node2_id")

    ds = sub.add_parser("distant-synonyms")
    ds.add_argument("node_id")
    ds.add_argument("distance", type=int)

    da = sub.add_parser("distant-antonyms")
    da.add_argument("node_id")
    da.add_argument("distance", type=int)

    return p


DISPATCH = {
    "successors":            lambda db, a: successors(db, a.node_id),
    "count-successors":      lambda db, a: count_successors(db, a.node_id),
    "predecessors":          lambda db, a: predecessors(db, a.node_id),
    "count-predecessors":    lambda db, a: count_predecessors(db, a.node_id),
    "neighbors":             lambda db, a: neighbors(db, a.node_id),
    "count-neighbors":       lambda db, a: count_neighbors(db, a.node_id),
    "grandchildren":         lambda db, a: grandchildren(db, a.node_id),
    "grandparents":          lambda db, a: grandparents(db, a.node_id),
    "count-nodes":           lambda db, a: count_nodes(db),
    "count-no-successors":   lambda db, a: count_no_successors(db),
    "count-no-predecessors": lambda db, a: count_no_predecessors(db),
    "most-neighbors":        lambda db, a: most_neighbors(db),
    "count-single-neighbor": lambda db, a: count_single_neighbor(db),
    "rename":                lambda db, a: rename(db, a.old_node_id, a.new_node_id, a.new_label),
    "delete":                lambda db, a: delete_node(db, a.node_id),
    "similar":               lambda db, a: similar(db, a.node_id),
    "shortest-path":         lambda db, a: shortest_path(db, a.node1_id, a.node2_id),
    "distant-synonyms":      lambda db, a: distant_synonyms_antonyms(db, a.node_id, a.distance, "synonym"),
    "distant-antonyms":      lambda db, a: distant_synonyms_antonyms(db, a.node_id, a.distance, "antonym"),
}


def main():
    parser = build_parser()
    args = parser.parse_args()
    db = connect(args.host, args.port, args.db, args.user, args.password)
    DISPATCH[args.command](db, args)


if __name__ == "__main__":
    main()