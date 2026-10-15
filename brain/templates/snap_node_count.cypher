// name: snap_node_count
// purpose: how many nodes a snapshot graph has, so betweenness samples every node (key_people, item 17)
// params: none
// indexes: none (counts the snapshot graph's nodes)
// golden: tests/test_templates.py::test_goldens[snap_node_count]
MATCH (n:N)
RETURN count(n) AS n
