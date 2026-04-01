"""RG Lighthouse API Endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from .peer_registry import peer_registry
from .discovery_server import discovery_server

router = APIRouter(prefix="/lighthouse", tags=["lighthouse"])


class PeerRegisterRequest(BaseModel):
    peer_id: str
    peer_type: str = "miner"
    address: str
    p2p_port: int = 8600
    api_port: int = 8000
    node_version: str = "0.1.0"
    capabilities: List[str] = []
    miner_class: Optional[str] = None
    gpu_type: Optional[str] = None
    vram_gb: Optional[float] = None


class HeartbeatRequest(BaseModel):
    peer_id: str
    chain_height: int = 0
    consensus_role: Optional[str] = None


class DiscoverRequest(BaseModel):
    peer_type: Optional[str] = None
    limit: int = 20
    exclude: List[str] = []
    miner_class: Optional[str] = None


@router.post("/register")
async def register_peer(req: PeerRegisterRequest):
    try:
        peer = await peer_registry.register(
            peer_id=req.peer_id, peer_type=req.peer_type,
            address=req.address, p2p_port=req.p2p_port, api_port=req.api_port,
            node_version=req.node_version, capabilities=req.capabilities,
            miner_class=req.miner_class, gpu_type=req.gpu_type, vram_gb=req.vram_gb,
        )
        peers = peer_registry.discover_peers(limit=20, exclude=[req.peer_id])
        return {"status": "registered", "peer": peer.to_dict(), "bootstrap_peers": peers}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    ok = await peer_registry.heartbeat(req.peer_id, req.chain_height, req.consensus_role)
    if not ok:
        raise HTTPException(status_code=404, detail="Peer not registered")
    return {"status": "ok"}


@router.post("/discover")
async def discover_peers(req: DiscoverRequest):
    peers = peer_registry.discover_peers(
        peer_type=req.peer_type, limit=req.limit,
        exclude=req.exclude, miner_class=req.miner_class,
    )
    return {"peers": peers, "count": len(peers), "total": len(peer_registry.peers)}


@router.post("/deregister/{peer_id}")
async def deregister_peer(peer_id: str):
    ok = await peer_registry.deregister(peer_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Peer not found")
    return {"status": "removed"}


@router.post("/ban/{peer_id}")
async def ban_peer(peer_id: str, reason: str = ""):
    await peer_registry.ban_peer(peer_id, reason)
    return {"status": "banned"}


@router.get("/peers")
async def list_peers(peer_type: Optional[str] = None):
    peers = peer_registry.discover_peers(peer_type=peer_type, limit=100)
    return {"peers": peers, "count": len(peers)}


@router.get("/peers/{peer_id}")
async def get_peer(peer_id: str):
    peer = peer_registry.peers.get(peer_id)
    if not peer:
        raise HTTPException(status_code=404, detail="Peer not found")
    return peer.to_dict()


@router.get("/validators")
async def list_validators():
    return {"validators": peer_registry.get_validators()}


@router.get("/miners")
async def list_miners(miner_class: Optional[str] = None):
    return {"miners": peer_registry.get_miners(miner_class)}


@router.get("/chain-nodes")
async def list_chain_nodes():
    return {"chain_nodes": peer_registry.get_chain_nodes()}


@router.get("/stats")
async def get_stats():
    return {**discovery_server.get_stats(), "registry": peer_registry.get_stats()}


@router.get("/health")
async def health():
    stats = peer_registry.get_stats()
    return {
        "service": "rg-lighthouse", "status": "ok",
        "total_peers": stats["total_peers"],
        "active_peers": stats["by_status"].get("active", 0),
    }
