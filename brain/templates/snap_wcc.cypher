// name: snap_wcc
// purpose: connected components of people, teams, systems and projects over ownership, leads, membership and part-of in a snapshot graph (knowledge_gaps, item 17)
// params: none
// indexes: none (an algorithm over the whole snapshot graph)
// golden: tests/test_templates.py::test_goldens[snap_wcc]
CALL algo.WCC({nodeLabels: ['Person', 'Team', 'System', 'Project'],
               relationshipTypes: ['OWNS', 'LEADS', 'MEMBER_OF', 'PART_OF']}) YIELD node, componentId
RETURN node.id AS id, node.name AS name, labels(node) AS labels, componentId AS c
