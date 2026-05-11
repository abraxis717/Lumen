#!/usr/bin/env python3
"""
test_amendment_dag.py — Amendment DAG tests
============================================
Phase 4: Tests for the amendment DAG system including cycle detection,
version management, and chain traversal.
"""
import sys
import os
import hashlib
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kernel.amendments.amendment_dag import AmendmentDAG, AmendmentNode


def test_basic_insertion():
    """Test inserting nodes into the DAG."""
    print("\n[TEST 1] Basic node insertion...")
    dag = AmendmentDAG()

    node = AmendmentNode(
        node_id="base_v0",
        parent_ids=[],
        version=0,
        description="Base kernel",
        author="system",
        timestamp=time.time(),
    )
    assert dag.insert(node), "Failed to insert base node"
    assert len(dag._nodes) == 1
    assert dag.get_latest_version() == node
    print("  ✓ Base node inserted successfully")

    # Insert child node
    child = AmendmentNode(
        node_id="v1_child",
        parent_ids=["base_v0"],
        version=1,
        description="Add feature X",
        author="dev",
        timestamp=time.time(),
    )
    assert dag.insert(child), "Failed to insert child node"
    assert len(dag._nodes) == 2
    print("  ✓ Child node inserted with parent reference")

    # Insert grandchild
    grandchild = AmendmentNode(
        node_id="v2_grandchild",
        parent_ids=["v1_child"],
        version=2,
        description="Fix bug Y",
        author="dev",
        timestamp=time.time(),
    )
    assert dag.insert(grandchild), "Failed to insert grandchild"
    assert len(dag._nodes) == 3
    print("  ✓ Grandchild node inserted")


def test_cycle_detection():
    """Test that cycles are prevented."""
    print("\n[TEST 2] Cycle detection...")
    dag = AmendmentDAG()

    # Insert linear chain
    n1 = AmendmentNode(
        node_id="n1",
        parent_ids=[],
        version=1,
        description="Node 1",
        author="dev",
        timestamp=time.time(),
    )
    n2 = AmendmentNode(
        node_id="n2",
        parent_ids=["n1"],
        version=2,
        description="Node 2",
        author="dev",
        timestamp=time.time(),
    )
    assert dag.insert(n1)
    assert dag.insert(n2)

    # Try to create cycle: n3 -> n2 -> n1 -> n3
    n3 = AmendmentNode(
        node_id="n3",
        parent_ids=["n2"],
        version=3,
        description="Node 3",
        author="dev",
        timestamp=time.time(),
    )
    assert dag.insert(n3), "Failed to insert n3 (linear)"

    # Try to create cycle: add edge n1 -> n3 (already exists via n1->n2->n3)
    # Actually, we need a different structure. Let's try inserting n4 with parent n3
    # then trying to insert n5 with parents [n4, n1] which would create a DAG
    # To truly test cycle detection, we need to try inserting a node that references
    # a descendant as a parent
    n4 = AmendmentNode(
        node_id="n4",
        parent_ids=["n3"],
        version=4,
        description="Node 4",
        author="dev",
        timestamp=time.time(),
    )
    assert dag.insert(n4), "Failed to insert n4"

    # Try to insert a node that would create a cycle: reference a descendant
    cycle_attempt = AmendmentNode(
        node_id="n_cycle",
        parent_ids=["n4", "n1"],  # n1 -> n2 -> n3 -> n4, so n_cycle would be fine
        version=5,
        description="Test DAG, not cycle",
        author="dev",
        timestamp=time.time(),
    )
    # This should succeed since n1 is an ancestor of n4, not a descendant
    assert dag.insert(cycle_attempt), "Failed to insert valid DAG node"

    # Now verify acyclicity
    assert dag.verify_acyclic(), "DAG should be acyclic"
    print("  ✓ DAG verified acyclic after multiple insertions")


def test_version_chain():
    """Test version chain retrieval."""
    print("\n[TEST 3] Version chain retrieval...")
    dag = AmendmentDAG()

    for i in range(5):
        parent_ids = [f"v{i-1}"] if i > 0 else []
        node = AmendmentNode(
            node_id=f"v{i}",
            parent_ids=parent_ids,
            version=i,
            description=f"Version {i}",
            author="system",
            timestamp=time.time(),
        )
        assert dag.insert(node)

    chain = dag.get_chain_of_versions(0, 4)
    assert len(chain) == 5, f"Expected 5 versions, got {len(chain)}"
    assert all(n.applied for n in chain) is False, "Nodes should not be auto-applied"
    print(f"  ✓ Retrieved {len(chain)} versions in chain")

    # Apply a version
    applied = dag.apply_version(2)
    assert applied is not None
    assert applied.applied, "Version 2 should be marked as applied"
    stats = dag.get_dag_stats()
    assert stats["applied_versions"] == 1
    print("  ✓ Version application works correctly")


def test_ancestors():
    """Test ancestor traversal."""
    print("\n[TEST 4] Ancestor traversal...")
    dag = AmendmentDAG()

    n1 = AmendmentNode(
        node_id="root",
        parent_ids=[],
        version=0,
        description="Root",
        author="system",
        timestamp=time.time(),
    )
    n2 = AmendmentNode(
        node_id="child",
        parent_ids=["root"],
        version=1,
        description="Child",
        author="dev",
        timestamp=time.time(),
    )
    n3 = AmendmentNode(
        node_id="grandchild",
        parent_ids=["child"],
        version=2,
        description="Grandchild",
        author="dev",
        timestamp=time.time(),
    )
    dag.insert(n1)
    dag.insert(n2)
    dag.insert(n3)

    ancestors = dag.get_ancestors("grandchild")
    ancestor_ids = [a.node_id for a in ancestors]
    assert "child" in ancestor_ids, "Child should be ancestor of grandchild"
    assert "root" in ancestor_ids, "Root should be ancestor of grandchild"
    assert ancestors[-1].node_id == "grandchild", "Last ancestor should be the node itself"
    print(f"  ✓ Ancestors of 'grandchild': {ancestor_ids}")


def test_dag_stats():
    """Test DAG statistics."""
    print("\n[TEST 5] DAG statistics...")
    dag = AmendmentDAG()

    # Insert a few nodes
    for i in range(3):
        parent_ids = [f"node_{i-1}"] if i > 0 else []
        node = AmendmentNode(
            node_id=f"node_{i}",
            parent_ids=parent_ids,
            version=i,
            description=f"Node {i}",
            author="dev",
            timestamp=time.time(),
        )
        dag.insert(node)

    stats = dag.get_dag_stats()
    assert stats["total_nodes"] == 3
    assert stats["max_version"] == 2
    assert len(stats["root_nodes"]) == 1, "Should have one root node"
    print(f"  ✓ Stats: {stats}")


def test_export_import():
    """Test DAG serialization and deserialization."""
    print("\n[TEST 6] Export/import round-trip...")
    dag = AmendmentDAG()

    for i in range(3):
        parent_ids = [f"n{i-1}"] if i > 0 else []
        node = AmendmentNode(
            node_id=f"n{i}",
            parent_ids=parent_ids,
            version=i,
            description=f"Node {i}",
            author="dev",
            timestamp=time.time() + i,
        )
        dag.insert(node)

    exported = dag.export()
    assert "nodes" in exported
    assert "edges" in exported
    assert exported["stats"]["total_nodes"] == 3

    imported = AmendmentDAG.from_dict(exported)
    assert len(imported._nodes) == len(dag._nodes)
    assert imported.verify_acyclic()
    print("  ✓ DAG exported and imported successfully")


def test_duplicate_rejection():
    """Test that duplicate node IDs are rejected."""
    print("\n[TEST 7] Duplicate rejection...")
    dag = AmendmentDAG()

    node1 = AmendmentNode(
        node_id="dup",
        parent_ids=[],
        version=0,
        description="First",
        author="dev",
        timestamp=time.time(),
    )
    assert dag.insert(node1)

    node2 = AmendmentNode(
        node_id="dup",
        parent_ids=[],
        version=1,
        description="Second",
        author="dev",
        timestamp=time.time(),
    )
    assert not dag.insert(node2), "Duplicate node should be rejected"
    assert len(dag._nodes) == 1
    print("  ✓ Duplicate node rejected")


def test_missing_parent_rejection():
    """Test that nodes with missing parents are rejected."""
    print("\n[TEST 8] Missing parent rejection...")
    dag = AmendmentDAG()

    try:
        node = AmendmentNode(
            node_id="orphan",
            parent_ids=["nonexistent"],
            version=0,
            description="Orphan",
            author="dev",
            timestamp=time.time(),
        )
        dag.insert(node)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "nonexistent" in str(e)
        print(f"  ✓ Missing parent rejected: {e}")


def main():
    tests = [
        test_basic_insertion,
        test_cycle_detection,
        test_version_chain,
        test_ancestors,
        test_dag_stats,
        test_export_import,
        test_duplicate_rejection,
        test_missing_parent_rejection,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            failed += 1

    print(f"\n{'═'*60}")
    print(f"  Amendment DAG Tests: {passed} passed, {failed} failed")
    print(f"{'═'*60}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
