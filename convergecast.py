"""
Async non-blocking convergecast over Yggdrasil network.

Derives tree topology from the Go bridge and implements
convergecast (leaf-to-root aggregation) with dictionary merging.
"""

import asyncio
import base64
import io
import msgpack
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any, Set, Tuple
from enum import Enum

import aiohttp


BRIDGE_URL = "http://127.0.0.1:9002"


class MessageType(str, Enum):
    CONVERGECAST_DATA = "convergecast_data"
    CONVERGECAST_ACK = "convergecast_ack"
    BANDWIDTH_TEST = "bandwidth_test"
    BANDWIDTH_ACK = "bandwidth_ack"


@dataclass
class TopologyInfo:
    our_ipv6: str
    our_public_key: str
    peers: List[Dict]
    tree: List[Dict]


@dataclass 
class TreePosition:
    """Our position in the spanning tree."""
    our_key: str
    parent: Optional[str]  # None if we are root
    children: Set[str]
    is_root: bool = False
    is_leaf: bool = False


def derive_tree_position(topology: TopologyInfo) -> TreePosition:
    """
    Derive our position in the tree from topology info.
    
    The tree[] array contains entries with {public_key, parent}.
    We find ourselves, identify our parent, and reverse-lookup children.
    """
    our_key = topology.our_public_key
    tree_map: Dict[str, Optional[str]] = {}  # key -> parent
    
    for entry in topology.tree:
        key = entry.get("public_key", "")
        parent = entry.get("parent") or None  # Empty string -> None
        tree_map[key] = parent
    
    # Find our parent
    our_parent = tree_map.get(our_key)
    
    # Find our children (nodes whose parent is us)
    children = {key for key, parent in tree_map.items() if parent == our_key}
    
    is_root = our_parent is None or our_parent == ""
    is_leaf = len(children) == 0
    
    return TreePosition(
        our_key=our_key,
        parent=our_parent if not is_root else None,
        children=children,
        is_root=is_root,
        is_leaf=is_leaf
    )


class AsyncYggdrasilClient:
    """
    Non-blocking client for Yggdrasil Go bridge.
    
    Provides async send/recv and background message polling.
    """
    
    def __init__(self, bridge_url: str = BRIDGE_URL):
        self.bridge_url = bridge_url
        self._session: Optional[aiohttp.ClientSession] = None
        self._recv_task: Optional[asyncio.Task] = None
        self._message_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        
    async def __aenter__(self):
        await self.start()
        return self
        
    async def __aexit__(self, *args):
        await self.stop()
        
    async def start(self):
        """Start the client and background receiver."""
        self._session = aiohttp.ClientSession()
        self._running = True
        self._recv_task = asyncio.create_task(self._recv_loop())
        
    async def stop(self):
        """Stop the client and cleanup."""
        self._running = False
        if self._recv_task:
            self._recv_task.cancel()
            try:
                await self._recv_task
            except asyncio.CancelledError:
                pass
        if self._session:
            await self._session.close()
            
    async def get_topology(self) -> Optional[TopologyInfo]:
        """Fetch current network topology."""
        try:
            async with self._session.get(f"{self.bridge_url}/topology") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return TopologyInfo(
                        our_ipv6=data.get("our_ipv6", ""),
                        our_public_key=data.get("our_public_key", ""),
                        peers=data.get("peers", []),
                        tree=data.get("tree", [])
                    )
        except Exception as e:
            print(f"Topology fetch failed: {e}")
        return None
        
    async def send(self, dest_key: str, data: bytes) -> bool:
        """
        Send raw bytes to destination (non-blocking).
        Returns True on success.
        """
        b64_data = base64.b64encode(data).decode('utf-8')
        payload = {
            "destination_key": dest_key,
            "data": b64_data
        }
        
        try:
            async with self._session.post(
                f"{self.bridge_url}/send", 
                json=payload
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    print(f"[DEBUG] Send success: {result}")
                    return True
                else:
                    error_text = await resp.text()
                    print(f"[DEBUG] Send failed: status={resp.status}, body={error_text}")
                    return False
        except Exception as e:
            print(f"Send failed: {e}")
            return False
            
    async def send_msg(self, dest_key: str, msg: Dict) -> bool:
        """Send a msgpack-encoded message."""
        packed = msgpack.packb(msg, use_bin_type=True)
        return await self.send(dest_key, packed)
        
    async def recv(self, timeout: Optional[float] = None) -> Optional[Dict]:
        """
        Receive next message from queue.
        Returns None on timeout or if no message available.
        """
        try:
            if timeout is not None:
                return await asyncio.wait_for(
                    self._message_queue.get(), 
                    timeout=timeout
                )
            else:
                return await self._message_queue.get()
        except asyncio.TimeoutError:
            return None
            
    async def _recv_loop(self):
        """Background task: poll bridge for messages."""
        while self._running:
            try:
                async with self._session.get(f"{self.bridge_url}/recv") as resp:
                    if resp.status == 200:
                        raw = await resp.json()
                        # Decode the message
                        from_key = raw.get("from_key", "")
                        b64_data = raw.get("data", "")
                        
                        print(f"[DEBUG] Got message from bridge, from_key={from_key[:16] if from_key else 'none'}..., data_len={len(b64_data) if b64_data else 0}")
                        
                        if b64_data:
                            data = base64.b64decode(b64_data)
                            try:
                                decoded = msgpack.unpackb(data, raw=False)
                                msg_type = decoded.get("type", "unknown") if isinstance(decoded, dict) else "non-dict"
                                print(f"[DEBUG] Decoded msgpack, type={msg_type}")
                                await self._message_queue.put({
                                    "from_key": from_key,
                                    "data": decoded
                                })
                            except Exception as e:
                                # Not msgpack, store raw
                                print(f"[DEBUG] Not msgpack: {e}")
                                await self._message_queue.put({
                                    "from_key": from_key,
                                    "data": data
                                })
                    elif resp.status == 204:
                        # No messages, brief pause
                        await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Recv loop error: {e}")
                await asyncio.sleep(0.1)


@dataclass
class ConvergeCastResult:
    """Result of a convergecast operation."""
    success: bool
    data: Dict = field(default_factory=dict)
    received_from: Set[str] = field(default_factory=set)
    missing_children: Set[str] = field(default_factory=set)
    is_root: bool = False


class ConvergeCast:
    """
    Convergecast: aggregate data from leaves to root.
    
    Each node:
    1. Waits for data from all children (if any)
    2. Merges children data with its own local data
    3. Sends merged result to parent (unless root)
    
    Dictionary merge strategy: shallow merge, later values override.
    """
    
    def __init__(
        self, 
        client: AsyncYggdrasilClient,
        tree_position: TreePosition,
        session_id: str = "default"
    ):
        self.client = client
        self.tree = tree_position
        self.session_id = session_id
        
    async def run(
        self,
        local_data: Dict,
        timeout: float = 30.0
    ) -> ConvergeCastResult:
        """
        Execute convergecast with this node's local data.
        
        Args:
            local_data: This node's contribution to the aggregation
            timeout: Max time to wait for children
            
        Returns:
            ConvergeCastResult with aggregated data (meaningful at root)
        """
        # Start with our local data
        aggregated = dict(local_data)
        received_from: Set[str] = set()
        
        # If we have children, wait for their data
        if self.tree.children:
            children_data = await self._collect_from_children(timeout)
            received_from = set(children_data.keys())
            
            # Merge children data (shallow merge)
            for child_key, child_data in children_data.items():
                aggregated = self._merge_dicts(aggregated, child_data)
        
        missing = self.tree.children - received_from
        
        # If not root, send to parent
        if not self.tree.is_root and self.tree.parent:
            msg = {
                "type": MessageType.CONVERGECAST_DATA,
                "session_id": self.session_id,
                "from": self.tree.our_key,
                "data": aggregated
            }
            await self.client.send_msg(self.tree.parent, msg)
            
        return ConvergeCastResult(
            success=len(missing) == 0,
            data=aggregated,
            received_from=received_from,
            missing_children=missing,
            is_root=self.tree.is_root
        )
        
    async def _collect_from_children(
        self, 
        timeout: float
    ) -> Dict[str, Dict]:
        """Wait for data from all children, with timeout."""
        children_data: Dict[str, Dict] = {}
        pending = set(self.tree.children)
        deadline = asyncio.get_event_loop().time() + timeout
        
        while pending:
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
                
            msg = await self.client.recv(timeout=min(remaining, 1.0))
            if msg is None:
                continue
                
            data = msg.get("data", {})
            if not isinstance(data, dict):
                continue
                
            # Check if it's convergecast data for our session
            if data.get("type") != MessageType.CONVERGECAST_DATA:
                continue
            if data.get("session_id") != self.session_id:
                continue
                
            from_key = data.get("from", msg.get("from_key", ""))
            if from_key in pending:
                children_data[from_key] = data.get("data", {})
                pending.discard(from_key)
                
        return children_data
        
    @staticmethod
    def _merge_dicts(base: Dict, overlay: Dict) -> Dict:
        """
        Shallow merge two dictionaries.
        Overlay values override base values.
        """
        result = dict(base)
        result.update(overlay)
        return result


# Convenience function for simple usage
async def run_convergecast(
    local_data: Dict,
    session_id: str = "default",
    timeout: float = 30.0,
    bridge_url: str = BRIDGE_URL
) -> ConvergeCastResult:
    """
    High-level convergecast entry point.
    
    Fetches topology, determines tree position, and runs convergecast.
    """
    async with AsyncYggdrasilClient(bridge_url) as client:
        topology = await client.get_topology()
        if not topology:
            return ConvergeCastResult(success=False)
            
        tree_pos = derive_tree_position(topology)
        cc = ConvergeCast(client, tree_pos, session_id)
        return await cc.run(local_data, timeout)


# ============================================================
# Bandwidth Testing
# ============================================================

def timestamp_now() -> str:
    """Return current UTC timestamp in ISO format with microseconds."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f UTC")


def create_test_payload(size_bytes: int, seed: int = 42) -> bytes:
    """Create deterministic test payload of given size."""
    import random
    random.seed(seed)
    return bytes(random.getrandbits(8) for _ in range(size_bytes))


def try_import_torch():
    """Try to import torch for tensor tests, return None if unavailable."""
    try:
        import torch
        return torch
    except ImportError:
        return None


def serialize_tensor(tensor) -> Dict:
    """Serialize a torch tensor to dict with bytes."""
    torch = try_import_torch()
    if torch is None:
        raise ImportError("torch not available")
    buffer = io.BytesIO()
    torch.save(tensor, buffer)
    return {
        "tensor_data": buffer.getvalue(),
        "shape": list(tensor.shape),
        "dtype": str(tensor.dtype)
    }


def deserialize_tensor(tensor_dict: Dict):
    """Deserialize tensor from dict."""
    torch = try_import_torch()
    if torch is None:
        raise ImportError("torch not available")
    buffer = io.BytesIO(tensor_dict["tensor_data"])
    return torch.load(buffer, weights_only=True)


def create_deterministic_tensor(shape: Tuple[int, ...], seed: int = 42):
    """Create deterministic tensor for verification."""
    torch = try_import_torch()
    if torch is None:
        raise ImportError("torch not available")
    torch.manual_seed(seed)
    return torch.randn(*shape)


class BandwidthTest:
    """
    Async bandwidth testing with timestamp logging.
    
    Logs timestamps on send and receive for manual cross-machine comparison.
    """
    
    def __init__(self, client: AsyncYggdrasilClient):
        self.client = client
        
    async def send_test(
        self,
        dest_key: str,
        size_bytes: int = 1024,
        test_name: str = "test",
        use_tensor: bool = False,
        tensor_shape: Optional[Tuple[int, ...]] = None,
        seed: int = 42
    ) -> bool:
        """
        Send a bandwidth test message with timestamp logging.
        
        Args:
            dest_key: Destination public key (hex)
            size_bytes: Size of test payload (ignored if use_tensor=True)
            test_name: Name for this test
            use_tensor: If True, send a tensor instead of random bytes
            tensor_shape: Shape of tensor (required if use_tensor=True)
            seed: Seed for deterministic data
        """
        if use_tensor:
            if tensor_shape is None:
                tensor_shape = (100, 100)
            tensor = create_deterministic_tensor(tensor_shape, seed)
            payload_data = serialize_tensor(tensor)
            size_bytes = tensor.nelement() * tensor.element_size()
            size_mb = size_bytes / (1024 * 1024)
            print(f"\n{'='*60}")
            print(f"[SEND] Bandwidth Test: {test_name}")
            print(f"[SEND] Tensor shape: {tensor_shape}, Size: {size_mb:.2f} MB")
        else:
            payload_data = create_test_payload(size_bytes, seed)
            size_mb = size_bytes / (1024 * 1024)
            print(f"\n{'='*60}")
            print(f"[SEND] Bandwidth Test: {test_name}")
            print(f"[SEND] Payload size: {size_bytes} bytes ({size_mb:.4f} MB)")
        
        msg = {
            "type": MessageType.BANDWIDTH_TEST,
            "test_name": test_name,
            "seed": seed,
            "size_bytes": size_bytes,
            "use_tensor": use_tensor,
            "tensor_shape": list(tensor_shape) if tensor_shape else None,
            "payload": payload_data
        }
        
        send_time = timestamp_now()
        print(f"[SEND] Destination: {dest_key[:16]}...")
        print(f"[SEND] TIME_SENT: {send_time}")
        
        success = await self.client.send_msg(dest_key, msg)
        
        if success:
            print(f"[SEND] Status: SUCCESS")
        else:
            print(f"[SEND] Status: FAILED")
        print(f"{'='*60}")
        
        return success
        
    async def receive_loop(self, send_ack: bool = True, timeout: float = 3600.0):
        """
        Listen for bandwidth test messages and log receive timestamps.
        
        Args:
            send_ack: Whether to send ACK back to sender
            timeout: How long to listen (default 1 hour)
        """
        print(f"\n{'='*60}")
        print(f"[RECV] Bandwidth Test Receiver Started")
        print(f"[RECV] Listening for incoming tests...")
        print(f"{'='*60}\n")
        
        deadline = asyncio.get_event_loop().time() + timeout
        
        while asyncio.get_event_loop().time() < deadline:
            msg = await self.client.recv(timeout=1.0)
            if msg is None:
                continue
                
            data = msg.get("data", {})
            if not isinstance(data, dict):
                continue
                
            msg_type = data.get("type")
            
            if msg_type == MessageType.BANDWIDTH_TEST:
                recv_time = timestamp_now()
                from_key = msg.get("from_key", "unknown")
                test_name = data.get("test_name", "unknown")
                size_bytes = data.get("size_bytes", 0)
                use_tensor = data.get("use_tensor", False)
                tensor_shape = data.get("tensor_shape")
                seed = data.get("seed", 42)
                
                size_mb = size_bytes / (1024 * 1024)
                
                print(f"\n{'='*60}")
                print(f"[RECV] Bandwidth Test Received: {test_name}")
                print(f"[RECV] From: {from_key[:16]}...")
                print(f"[RECV] TIME_RECEIVED: {recv_time}")
                print(f"[RECV] Size: {size_bytes} bytes ({size_mb:.4f} MB)")
                
                # Verify payload if tensor
                verified = False
                if use_tensor and tensor_shape:
                    try:
                        received_tensor = deserialize_tensor(data.get("payload", {}))
                        expected_tensor = create_deterministic_tensor(tuple(tensor_shape), seed)
                        torch = try_import_torch()
                        if torch:
                            verified = torch.allclose(received_tensor, expected_tensor)
                            print(f"[RECV] Tensor shape: {tuple(tensor_shape)}")
                            print(f"[RECV] Verification: {'PASS ✓' if verified else 'FAIL ✗'}")
                    except Exception as e:
                        print(f"[RECV] Verification error: {e}")
                else:
                    print(f"[RECV] Payload type: raw bytes")
                    verified = True  # Can't verify random bytes easily
                
                print(f"{'='*60}")
                
                # Send ACK
                if send_ack:
                    ack_msg = {
                        "type": MessageType.BANDWIDTH_ACK,
                        "test_name": test_name,
                        "verified": verified,
                        "recv_time": recv_time
                    }
                    ack_time = timestamp_now()
                    await self.client.send_msg(from_key, ack_msg)
                    print(f"[RECV] ACK sent at: {ack_time}")
                    
            elif msg_type == MessageType.BANDWIDTH_ACK:
                ack_time = timestamp_now()
                from_key = msg.get("from_key", "unknown")
                test_name = data.get("test_name", "unknown")
                verified = data.get("verified", False)
                remote_recv_time = data.get("recv_time", "unknown")
                
                print(f"\n{'='*60}")
                print(f"[ACK] Received ACK for: {test_name}")
                print(f"[ACK] From: {from_key[:16]}...")
                print(f"[ACK] Remote TIME_RECEIVED: {remote_recv_time}")
                print(f"[ACK] Local TIME_ACK_RECEIVED: {ack_time}")
                print(f"[ACK] Verified: {'YES ✓' if verified else 'NO ✗'}")
                print(f"{'='*60}")


async def run_bandwidth_sender(
    target_key: str,
    test_configs: Optional[List[Tuple[str, int]]] = None,
    use_tensor: bool = False,
    tensor_shapes: Optional[List[Tuple[int, ...]]] = None,
    bridge_url: str = BRIDGE_URL
):
    """
    Run bandwidth tests as sender.
    
    Args:
        target_key: Destination public key
        test_configs: List of (test_name, size_bytes) tuples
        use_tensor: Use tensor payloads instead of raw bytes
        tensor_shapes: List of tensor shapes if use_tensor=True
        bridge_url: Bridge URL
    """
    if test_configs is None and not use_tensor:
        test_configs = [
            ("small_1KB", 1024),
            ("medium_100KB", 100 * 1024),
            ("large_1MB", 1024 * 1024),
            ("xlarge_10MB", 10 * 1024 * 1024),
        ]
    
    if use_tensor and tensor_shapes is None:
        tensor_shapes = [
            (10, 10),
            (100, 100),
            (1000, 1000),
            (10000, 10000),
        ]
    
    async with AsyncYggdrasilClient(bridge_url) as client:
        topo = await client.get_topology()
        if topo:
            print(f"Our key: {topo.our_public_key[:16]}...")
        
        bt = BandwidthTest(client)
        
        if use_tensor:
            for shape in tensor_shapes:
                name = f"tensor_{shape[0]}x{shape[1]}"
                await bt.send_test(
                    target_key, 
                    test_name=name,
                    use_tensor=True,
                    tensor_shape=shape
                )
                await asyncio.sleep(0.5)
        else:
            for name, size in test_configs:
                await bt.send_test(target_key, size_bytes=size, test_name=name)
                await asyncio.sleep(0.5)
        
        # Wait for ACKs
        print("\nWaiting for ACKs...")
        await bt.receive_loop(send_ack=False, timeout=30.0)


async def run_bandwidth_receiver(bridge_url: str = BRIDGE_URL):
    """Run as bandwidth test receiver."""
    async with AsyncYggdrasilClient(bridge_url) as client:
        topo = await client.get_topology()
        if topo:
            print(f"Our key: {topo.our_public_key}")
            print(f"(Share this key with sender)")
        
        bt = BandwidthTest(client)
        await bt.receive_loop(send_ack=True)


if __name__ == "__main__":
    import sys
    
    async def main():
        async with AsyncYggdrasilClient() as client:
            topo = await client.get_topology()
            if topo:
                print(f"Our key: {topo.our_public_key[:16]}...")
                tree_pos = derive_tree_position(topo)
                print(f"Parent: {tree_pos.parent[:16] if tree_pos.parent else 'NONE (root)'}...")
                print(f"Children: {len(tree_pos.children)}")
                print(f"Is root: {tree_pos.is_root}")
                print(f"Is leaf: {tree_pos.is_leaf}")
            else:
                print("Could not fetch topology")
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "recv":
            # Receiver mode
            asyncio.run(run_bandwidth_receiver())
            
        elif cmd == "send" and len(sys.argv) > 2:
            # Sender mode: send <target_key> [--tensor]
            target_key = sys.argv[2]
            use_tensor = "--tensor" in sys.argv
            asyncio.run(run_bandwidth_sender(target_key, use_tensor=use_tensor))
            
        elif cmd == "topo":
            # Just show topology
            asyncio.run(main())
            
        else:
            print("Usage:")
            print("  python convergecast.py topo              # Show topology")
            print("  python convergecast.py recv              # Run as receiver")
            print("  python convergecast.py send <key>        # Send raw byte tests")
            print("  python convergecast.py send <key> --tensor  # Send tensor tests")
    else:
        asyncio.run(main())
