"""
PEER REGISTRY
=============

Central peer registry for the Lighthouse bootstrap node.
Tracks all known peers by category (miner, chain, validator),
monitors liveness, and provides peer lists for new nodes joining the network.

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-04-01
PURPOSE: P2P peer discovery and health tracking
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)


class PeerType(str, Enum):
    MINER = "miner"              # CLASS_F/G/H — training nodes
    CHAIN = "chain"              # External blockchain full nodes
    VALIDATOR = "validator"      # CLASS_F — genesis validators (also mine)
    LIGHTHOUSE = "lighthouse"    # Other lighthouse bootstrap nodes


class PeerStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    DEAD = "dead"
    BANNED = "banned"


@dataclass
class RegisteredPeer:
    """A peer registered with the Lighthouse."""
    peer_id: str
    peer_type: PeerType
    address: str
    p2p_port: int
    api_port: int = 8000
    node_version: str = "0.1.0"
    capabilities: List[str] = field(default_factory=list)
    
    # Status tracking
    status: PeerStatus = PeerStatus.ACTIVE
    registered_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_heartbeat: float = field(default_factory=time.time)
    heartbeat_count: int = 0
    missed_heartbeats: int = 0
    
    # Miner-specific fields
    miner_class: Optional[str] = None     # validator_miner, core_miner, miner
    gpu_type: Optional[str] = None
    vram_gb: Optional[float] = None
    
    # Chain-specific fields
    chain_height: int = 0
    consensus_role: Optional[str] = None  # leader, follower, candidate
    
    # Trust / reputation
    trust_score: float = 1.0
    tasks_completed: int = 0
    tasks_failed: int = 0

    @property
    def endpoint(self) -> str:
        return f"{self.address}:{self.p2p_port}"

    @property
    def api_endpoint(self) -> str:
        return f"http://{self.address}:{self.api_port}"

    @property
    def uptime_seconds(self) -> float:
        try:
            reg_time = datetime.fromisoformat(self.registered_at)
            return (datetime.now(timezone.utc) - reg_time).total_seconds()
        except:
            return 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "peer_type": self.peer_type.value,
            "address": self.address,
            "p2p_port": self.p2p_port,
            "api_port": self.api_port,
            "node_version": self.node_version,
            "capabilities": self.capabilities,
            "status": self.status.value,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "heartbeat_count": self.heartbeat_count,
            "missed_heartbeats": self.missed_heartbeats,
            "miner_class": self.miner_class,
            "gpu_type": self.gpu_type,
            "vram_gb": self.vram_gb,
            "chain_height": self.chain_height,
            "consensus_role": self.consensus_role,
            "trust_score": round(self.trust_score, 4),
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }

    def to_discovery_dict(self) -> Dict[str, Any]:
        """Minimal info returned during peer discovery."""
        return {
            "peer_id": self.peer_id,
            "peer_type": self.peer_type.value,
            "address": self.address,
            "p2p_port": self.p2p_port,
            "api_port": self.api_port,
            "capabilities": self.capabilities,
            "miner_class": self.miner_class,
        }


class PeerRegistry:
    """
    Central registry of all peers in the ResonantGenesis network.
    
    The Lighthouse maintains this registry and serves it to new
    nodes joining the network. It's the "phone book" of the P2P mesh.
    """

    def __init__(self, peer_timeout: int = 120, max_peers: int = 500):
        self.peers: Dict[str, RegisteredPeer] = {}
        self.banned_peers: Set[str] = set()
        self.peer_timeout = peer_timeout  # seconds before marking stale
        self.max_peers = max_peers
        self._lock = asyncio.Lock()

    async def register(
        self,
        peer_id: str,
        peer_type: str,
        address: str,
        p2p_port: int,
        api_port: int = 8000,
        node_version: str = "0.1.0",
        capabilities: List[str] = None,
        miner_class: str = None,
        gpu_type: str = None,
        vram_gb: float = None,
    ) -> RegisteredPeer:
        """Register a new peer or re-register an existing one."""
        async with self._lock:
            if peer_id in self.banned_peers:
                raise ValueError(f"Peer {peer_id} is banned")

            if peer_id in self.peers:
                # Re-register: update info, reset heartbeat
                peer = self.peers[peer_id]
                peer.address = address
                peer.p2p_port = p2p_port
                peer.api_port = api_port
                peer.node_version = node_version
                peer.status = PeerStatus.ACTIVE
                peer.last_heartbeat = time.time()
                peer.missed_heartbeats = 0
                if capabilities:
                    peer.capabilities = capabilities
                if miner_class:
                    peer.miner_class = miner_class
                if gpu_type:
                    peer.gpu_type = gpu_type
                if vram_gb is not None:
                    peer.vram_gb = vram_gb
                logger.info(f"Re-registered peer {peer_id} ({peer_type}) at {address}:{p2p_port}")
                return peer

            if len(self.peers) >= self.max_peers:
                # Evict oldest stale peer
                self._evict_stale()
                if len(self.peers) >= self.max_peers:
                    raise ValueError("Peer registry full")

            peer = RegisteredPeer(
                peer_id=peer_id,
                peer_type=PeerType(peer_type),
                address=address,
                p2p_port=p2p_port,
                api_port=api_port,
                node_version=node_version,
                capabilities=capabilities or [],
                miner_class=miner_class,
                gpu_type=gpu_type,
                vram_gb=vram_gb,
            )
            self.peers[peer_id] = peer
            logger.info(f"Registered new peer {peer_id} ({peer_type}) at {address}:{p2p_port}")
            return peer

    async def heartbeat(self, peer_id: str, chain_height: int = 0, consensus_role: str = None) -> bool:
        """Record a heartbeat from a peer."""
        peer = self.peers.get(peer_id)
        if not peer:
            return False

        peer.last_heartbeat = time.time()
        peer.heartbeat_count += 1
        peer.missed_heartbeats = 0
        peer.status = PeerStatus.ACTIVE

        if chain_height:
            peer.chain_height = chain_height
        if consensus_role:
            peer.consensus_role = consensus_role

        return True

    async def deregister(self, peer_id: str) -> bool:
        """Remove a peer from the registry."""
        async with self._lock:
            if peer_id in self.peers:
                del self.peers[peer_id]
                logger.info(f"Deregistered peer {peer_id}")
                return True
            return False

    async def ban_peer(self, peer_id: str, reason: str = "") -> bool:
        """Ban a peer from re-registering."""
        async with self._lock:
            self.banned_peers.add(peer_id)
            if peer_id in self.peers:
                self.peers[peer_id].status = PeerStatus.BANNED
                del self.peers[peer_id]
            logger.warning(f"Banned peer {peer_id}: {reason}")
            return True

    def discover_peers(
        self,
        peer_type: str = None,
        limit: int = 20,
        exclude: List[str] = None,
        miner_class: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Discover peers matching criteria.
        This is the core discovery endpoint — what new nodes call to find the network.
        """
        exclude = set(exclude or [])
        results = []

        for peer in self.peers.values():
            if peer.status != PeerStatus.ACTIVE:
                continue
            if peer.peer_id in exclude:
                continue
            if peer_type and peer.peer_type.value != peer_type:
                continue
            if miner_class and peer.miner_class != miner_class:
                continue
            results.append(peer.to_discovery_dict())

        # Sort by trust score descending, then by heartbeat recency
        results.sort(key=lambda p: p.get("peer_id", ""))
        return results[:limit]

    def get_validators(self) -> List[Dict[str, Any]]:
        """Get all active validator nodes (for consensus bootstrap)."""
        return self.discover_peers(peer_type="validator")

    def get_miners(self, miner_class: str = None) -> List[Dict[str, Any]]:
        """Get active miners, optionally filtered by class."""
        return self.discover_peers(peer_type="miner", miner_class=miner_class)

    def get_chain_nodes(self) -> List[Dict[str, Any]]:
        """Get active chain full nodes."""
        return self.discover_peers(peer_type="chain")

    async def sweep_stale_peers(self):
        """Mark peers as stale/dead based on heartbeat timeout."""
        now = time.time()
        for peer in list(self.peers.values()):
            if peer.status == PeerStatus.BANNED:
                continue

            elapsed = now - peer.last_heartbeat
            if elapsed > self.peer_timeout * 3:
                peer.status = PeerStatus.DEAD
                peer.missed_heartbeats += 1
            elif elapsed > self.peer_timeout:
                peer.status = PeerStatus.STALE
                peer.missed_heartbeats += 1

    def _evict_stale(self):
        """Evict dead/stale peers to make room."""
        dead = [pid for pid, p in self.peers.items() if p.status == PeerStatus.DEAD]
        for pid in dead:
            del self.peers[pid]

        if len(self.peers) >= self.max_peers:
            stale = [pid for pid, p in self.peers.items() if p.status == PeerStatus.STALE]
            stale.sort(key=lambda pid: self.peers[pid].last_heartbeat)
            for pid in stale[:10]:
                del self.peers[pid]

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        type_counts = {}
        status_counts = {}
        for peer in self.peers.values():
            type_counts[peer.peer_type.value] = type_counts.get(peer.peer_type.value, 0) + 1
            status_counts[peer.status.value] = status_counts.get(peer.status.value, 0) + 1

        return {
            "total_peers": len(self.peers),
            "banned_peers": len(self.banned_peers),
            "max_peers": self.max_peers,
            "by_type": type_counts,
            "by_status": status_counts,
            "peer_timeout": self.peer_timeout,
        }


# Global instance
peer_registry = PeerRegistry()
