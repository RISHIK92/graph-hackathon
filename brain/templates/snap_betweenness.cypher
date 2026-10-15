// name: snap_betweenness
// purpose: betweenness of people over the snapshot's undirected LINK edges (ownership, leads, membership, dependencies, work, authored mentions) (key_people, item 17)
// params: n, seed
// indexes: none (an algorithm over the whole snapshot graph)
// golden: tests/test_templates.py::test_goldens[snap_betweenness]
// samplingSize >= the node count makes the result exact; the fixed seed keeps it repeatable.
CALL algo.betweenness({nodeLabels: ['Person', 'Team', 'System'],
                       relationshipTypes: ['LINK'],
                       samplingSize: $n, samplingSeed: $seed}) YIELD node, score
WITH node, score
WHERE 'Person' IN labels(node)
RETURN node.id AS id, node.name AS name, score
