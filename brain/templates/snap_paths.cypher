// name: snap_paths
// purpose: up to 3 shortest paths of at most 4 hops between two entities in a snapshot graph, either direction (connection_between, item 17)
// params: a, b, types
// indexes: N.id
// golden: tests/test_templates.py::test_goldens[snap_paths]
// Anchored through WITH (F24 family); 4.22.0 returns a path once per parallel edge, so callers de-duplicate by node ids.
MATCH (s:N {id:$a})
WITH s
MATCH (t:N {id:$b})
CALL algo.SPpaths({sourceNode: s, targetNode: t, relTypes: $types, relDirection: 'both', pathCount: 3, maxLen: 4})
YIELD path
RETURN [n IN nodes(path) | n.id] AS ids, [r IN relationships(path) | {type: type(r), aid: r.aid, from: startNode(r).id}] AS rels
