"""
Tests for convergecast module.

Uses mocking to test without live Yggdrasil network.
"""

import asyncio
import pytest
from typing import Dict, List, Optional

from convergecast import (
    TopologyInfo,
    TreePosition,
    derive_tree_position,
    AsyncYggdrasilClient,
    ConvergeCast,
    ConvergeCastResult,
    MessageType,
)

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio(loop_scope="function")


# ============================================================
# Test Data Fixtures
# ============================================================

def make_topology(our_key: str, tree: List[Dict]) -> TopologyInfo:
    """Helper to create test topology."""
    return TopologyInfo(
        our_ipv6="200:1234::1",
        our_public_key=our_key,
        peers=[],
        tree=tree
    )


# Tree structure for tests:
#
#           ROOT (key_root)
#           /            \
#     NODE_A (key_a)   NODE_B (key_b)
#       /      \
#  LEAF_1    LEAF_2
# (key_l1)   (key_l2)

TREE_DATA = [
    {"public_key": "key_root", "parent": ""},
    {"public_key": "key_a", "parent": "key_root"},
    {"public_key": "key_b", "parent": "key_root"},
    {"public_key": "key_l1", "parent": "key_a"},
    {"public_key": "key_l2", "parent": "key_a"},
]


# ============================================================
# Tree Position Tests
# ============================================================

class TestDeriveTreePosition:
    """Tests for derive_tree_position function."""
    
    def test_root_node(self):
        """Root has no parent and has children."""
        topo = make_topology("key_root", TREE_DATA)
        pos = derive_tree_position(topo)
        
        assert pos.our_key == "key_root"
        assert pos.parent is None
        assert pos.is_root is True
        assert pos.is_leaf is False
        assert pos.children == {"key_a", "key_b"}
        
    def test_internal_node(self):
        """Internal node has parent and children."""
        topo = make_topology("key_a", TREE_DATA)
        pos = derive_tree_position(topo)
        
        assert pos.our_key == "key_a"
        assert pos.parent == "key_root"
        assert pos.is_root is False
        assert pos.is_leaf is False
        assert pos.children == {"key_l1", "key_l2"}
        
    def test_leaf_node(self):
        """Leaf has parent but no children."""
        topo = make_topology("key_l1", TREE_DATA)
        pos = derive_tree_position(topo)
        
        assert pos.our_key == "key_l1"
        assert pos.parent == "key_a"
        assert pos.is_root is False
        assert pos.is_leaf is True
        assert pos.children == set()
        
    def test_single_node_tree(self):
        """Single node is both root and leaf."""
        topo = make_topology("lonely", [{"public_key": "lonely", "parent": ""}])
        pos = derive_tree_position(topo)
        
        assert pos.is_root is True
        assert pos.is_leaf is True
        assert pos.children == set()
        
    def test_empty_string_parent_is_root(self):
        """Empty string parent means root."""
        tree = [{"public_key": "node1", "parent": ""}]
        topo = make_topology("node1", tree)
        pos = derive_tree_position(topo)
        
        assert pos.is_root is True
        assert pos.parent is None
        
    def test_none_parent_is_root(self):
        """None parent means root."""
        tree = [{"public_key": "node1", "parent": None}]
        topo = make_topology("node1", tree)
        pos = derive_tree_position(topo)
        
        assert pos.is_root is True


# ============================================================
# Dict Merge Tests
# ============================================================

class TestDictMerge:
    """Tests for dictionary merge logic."""
    
    def test_simple_merge(self):
        """Non-overlapping keys are combined."""
        result = ConvergeCast._merge_dicts(
            {"a": 1, "b": 2},
            {"c": 3, "d": 4}
        )
        assert result == {"a": 1, "b": 2, "c": 3, "d": 4}
        
    def test_overlay_wins(self):
        """Overlay values override base."""
        result = ConvergeCast._merge_dicts(
            {"a": 1, "b": 2},
            {"b": 99, "c": 3}
        )
        assert result == {"a": 1, "b": 99, "c": 3}
        
    def test_empty_base(self):
        """Merging into empty dict."""
        result = ConvergeCast._merge_dicts({}, {"a": 1})
        assert result == {"a": 1}
        
    def test_empty_overlay(self):
        """Merging empty overlay."""
        result = ConvergeCast._merge_dicts({"a": 1}, {})
        assert result == {"a": 1}


# ============================================================
# Mock Client for Testing
# ============================================================

class MockYggdrasilClient:
    """Mock client for testing convergecast without network."""
    
    def __init__(self):
        self.sent_messages: List[tuple] = []  # (dest_key, msg)
        self.incoming_messages: asyncio.Queue = asyncio.Queue()
        
    async def send_msg(self, dest_key: str, msg: Dict) -> bool:
        self.sent_messages.append((dest_key, msg))
        return True
        
    async def recv(self, timeout: Optional[float] = None) -> Optional[Dict]:
        try:
            if timeout:
                return await asyncio.wait_for(
                    self.incoming_messages.get(),
                    timeout=timeout
                )
            return self.incoming_messages.get_nowait()
        except (asyncio.TimeoutError, asyncio.QueueEmpty):
            return None


# ============================================================
# Convergecast Tests
# ============================================================

class TestConvergeCastLeaf:
    """Tests for leaf node convergecast behavior."""
    
    async def test_leaf_sends_to_parent(self):
        """Leaf immediately sends its data to parent."""
        client = MockYggdrasilClient()
        tree_pos = TreePosition(
            our_key="key_l1",
            parent="key_a",
            children=set(),
            is_root=False,
            is_leaf=True
        )
        
        cc = ConvergeCast(client, tree_pos, session_id="test1")
        result = await cc.run({"value": 42}, timeout=1.0)
        
        # Should have sent to parent
        assert len(client.sent_messages) == 1
        dest, msg = client.sent_messages[0]
        assert dest == "key_a"
        assert msg["type"] == MessageType.CONVERGECAST_DATA
        assert msg["session_id"] == "test1"
        assert msg["data"] == {"value": 42}
        
        # Result should indicate success
        assert result.success is True
        assert result.data == {"value": 42}
        assert result.is_root is False
        

class TestConvergeCastInternal:
    """Tests for internal node convergecast behavior."""
    
    async def test_waits_for_children(self):
        """Internal node waits for children before sending to parent."""
        client = MockYggdrasilClient()
        tree_pos = TreePosition(
            our_key="key_a",
            parent="key_root",
            children={"key_l1", "key_l2"},
            is_root=False,
            is_leaf=False
        )
        
        cc = ConvergeCast(client, tree_pos, session_id="test2")
        
        # Simulate children sending data
        async def inject_child_data():
            await asyncio.sleep(0.05)
            await client.incoming_messages.put({
                "from_key": "key_l1",
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "test2",
                    "from": "key_l1",
                    "data": {"leaf1_val": 10}
                }
            })
            await asyncio.sleep(0.05)
            await client.incoming_messages.put({
                "from_key": "key_l2", 
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "test2",
                    "from": "key_l2",
                    "data": {"leaf2_val": 20}
                }
            })
            
        # Run convergecast and child injection concurrently
        inject_task = asyncio.create_task(inject_child_data())
        result = await cc.run({"internal_val": 5}, timeout=2.0)
        await inject_task
        
        # Should have received from both children
        assert result.success is True
        assert result.received_from == {"key_l1", "key_l2"}
        assert result.missing_children == set()
        
        # Data should be merged
        assert result.data["internal_val"] == 5
        assert result.data["leaf1_val"] == 10
        assert result.data["leaf2_val"] == 20
        
        # Should have sent merged data to parent
        assert len(client.sent_messages) == 1
        dest, msg = client.sent_messages[0]
        assert dest == "key_root"
        assert msg["data"]["leaf1_val"] == 10
        
    async def test_timeout_with_missing_child(self):
        """Reports missing children on timeout."""
        client = MockYggdrasilClient()
        tree_pos = TreePosition(
            our_key="key_a",
            parent="key_root",
            children={"key_l1", "key_l2"},
            is_root=False,
            is_leaf=False
        )
        
        cc = ConvergeCast(client, tree_pos, session_id="test3")
        
        # Only one child responds
        async def inject_one_child():
            await asyncio.sleep(0.05)
            await client.incoming_messages.put({
                "from_key": "key_l1",
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "test3",
                    "from": "key_l1",
                    "data": {"leaf1_val": 10}
                }
            })
            
        inject_task = asyncio.create_task(inject_one_child())
        result = await cc.run({"internal_val": 5}, timeout=0.3)
        await inject_task
        
        # Should report partial success
        assert result.success is False
        assert result.received_from == {"key_l1"}
        assert result.missing_children == {"key_l2"}
        
        # Still sends what we have to parent
        assert len(client.sent_messages) == 1


class TestConvergeCastRoot:
    """Tests for root node convergecast behavior."""
    
    async def test_root_does_not_send(self):
        """Root collects but does not forward."""
        client = MockYggdrasilClient()
        tree_pos = TreePosition(
            our_key="key_root",
            parent=None,
            children={"key_a", "key_b"},
            is_root=True,
            is_leaf=False
        )
        
        cc = ConvergeCast(client, tree_pos, session_id="test4")
        
        # Simulate children
        async def inject_children():
            await asyncio.sleep(0.05)
            await client.incoming_messages.put({
                "from_key": "key_a",
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "test4",
                    "from": "key_a",
                    "data": {"subtree_a": 100}
                }
            })
            await asyncio.sleep(0.05)
            await client.incoming_messages.put({
                "from_key": "key_b",
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "test4",
                    "from": "key_b", 
                    "data": {"subtree_b": 200}
                }
            })
            
        inject_task = asyncio.create_task(inject_children())
        result = await cc.run({"root_val": 1}, timeout=2.0)
        await inject_task
        
        # Root should NOT send any messages
        assert len(client.sent_messages) == 0
        
        # Root has final aggregated result
        assert result.is_root is True
        assert result.success is True
        assert result.data == {"root_val": 1, "subtree_a": 100, "subtree_b": 200}


class TestConvergeCastSessionIsolation:
    """Tests that different sessions don't interfere."""
    
    async def test_ignores_other_sessions(self):
        """Messages from other sessions are ignored."""
        client = MockYggdrasilClient()
        tree_pos = TreePosition(
            our_key="key_a",
            parent="key_root",
            children={"key_l1"},
            is_root=False,
            is_leaf=False
        )
        
        cc = ConvergeCast(client, tree_pos, session_id="session_A")
        
        async def inject_mixed_messages():
            await asyncio.sleep(0.05)
            # Wrong session - should be ignored
            await client.incoming_messages.put({
                "from_key": "key_l1",
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "session_B",
                    "from": "key_l1",
                    "data": {"wrong": "data"}
                }
            })
            await asyncio.sleep(0.05)
            # Correct session
            await client.incoming_messages.put({
                "from_key": "key_l1",
                "data": {
                    "type": MessageType.CONVERGECAST_DATA,
                    "session_id": "session_A",
                    "from": "key_l1",
                    "data": {"correct": "data"}
                }
            })
            
        inject_task = asyncio.create_task(inject_mixed_messages())
        result = await cc.run({"local": 1}, timeout=2.0)
        await inject_task
        
        # Should only have correct session data
        assert "wrong" not in result.data
        assert result.data["correct"] == "data"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
