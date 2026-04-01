"""
DISCOVERY SERVER
================

TCP server that handles P2P discovery protocol messages.
New nodes connect here first to bootstrap into the network.

Protocol:
1. New node connects to Lighthouse TCP port (8600)
2. Sends REGISTER message with its peer_id, type, capabilities
3. Lighthouse responds with WELCOME + peer list
4. Node periodically sends HEARTBEAT to stay active
5. Node can send DISCOVER to get updated peer lists

STATUS: PRODUCTION IMPLEMENTATION
UPDATED: 2026-04-01
PURPOSE: P2P bootstrap and peer discovery for decentralized network
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .peer_registry import PeerRegistry, peer_registry, PeerType

logger = logging.getLogger(__name__)


class LighthouseMessageType(str, Enum):
    # Incoming from peers
    REGISTER = "register"
    HEARTBEAT = "heartbeat"
    DISCOVER = "discover"
    DEREGISTER = "deregister"
    PING = "ping"

    # Outgoing from lighthouse
    WELCOME = "welcome"
    PEERS = "peers"
    PONG = "pong"
    ERROR = "error"
    ACK = "ack"


class DiscoveryServer:
    """
    TCP server for P2P peer discovery.
    
    This is the first thing a new node contacts when joining the network.
    It maintains the peer registry and serves discovery requests.
    """

    def __init__(self, node_id: str = "lighthouse-0", port: int = 8600, registry: PeerRegistry = None):
        self.node_id = node_id
        self.port = port
        self.registry = registry or peer_registry

        self._server = None
        self._running = False
        self._tasks = []
        self._connections = 0
        self._total_connections = 0
        self._started_at = None

    async def start(self):
        """Start the discovery TCP server."""
        self._running = True
        self._started_at = datetime.now(timezone.utc).isoformat()

        self._server = await asyncio.start_server(
            self._handle_connection,
            "0.0.0.0",
            self.port,
        )

        # Background tasks
        self._tasks.append(asyncio.create_task(self._health_sweep_loop()))

        logger.info(f"Lighthouse discovery server started on port {self.port}")

    async def stop(self):
        """Stop the discovery server."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
        logger.info("Lighthouse discovery server stopped")

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle an incoming peer connection."""
        addr = writer.get_extra_info("peername")
        self._connections += 1
        self._total_connections += 1

        try:
            while self._running:
                data = await asyncio.wait_for(reader.readline(), timeout=30)
                if not data:
                    break

                try:
                    msg = json.loads(data.decode().strip())
                except json.JSONDecodeError:
                    await self._send(writer, {"type": LighthouseMessageType.ERROR.value, "error": "invalid json"})
                    break

                response = await self._handle_message(msg, addr)
                if response:
                    await self._send(writer, response)

        except asyncio.TimeoutError:
            pass
        except ConnectionResetError:
            pass
        except Exception as e:
            logger.debug(f"Connection error from {addr}: {e}")
        finally:
            self._connections -= 1
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

    async def _send(self, writer: asyncio.StreamWriter, data: Dict):
        """Send JSON response."""
        writer.write(json.dumps(data).encode() + b"\n")
        await writer.drain()

    async def _handle_message(self, msg: Dict, addr: tuple) -> Optional[Dict]:
        """Route and handle incoming message."""
        msg_type = msg.get("type", "")

        if msg_type == LighthouseMessageType.PING.value:
            return {
                "type": LighthouseMessageType.PONG.value,
                "node_id": self.node_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        elif msg_type == LighthouseMessageType.REGISTER.value:
            return await self._handle_register(msg, addr)

        elif msg_type == LighthouseMessageType.HEARTBEAT.value:
            return await self._handle_heartbeat(msg)

        elif msg_type == LighthouseMessageType.DISCOVER.value:
            return await self._handle_discover(msg)

        elif msg_type == LighthouseMessageType.DEREGISTER.value:
            return await self._handle_deregister(msg)

        else:
            return {
                "type": LighthouseMessageType.ERROR.value,
                "error": f"unknown message type: {msg_type}",
            }

    async def _handle_register(self, msg: Dict, addr: tuple) -> Dict:
        """Handle peer registration."""
        peer_id = msg.get("peer_id", str(uuid4()))
        peer_type = msg.get("peer_type", "miner")
        address = msg.get("address") or addr[0]
        p2p_port = msg.get("p2p_port", 8600)
        api_port = msg.get("api_port", 8000)

        try:
            peer = await self.registry.register(
                peer_id=peer_id,
                peer_type=peer_type,
                address=address,
                p2p_port=p2p_port,
                api_port=api_port,
                node_version=msg.get("node_version", "0.1.0"),
                capabilities=msg.get("capabilities", []),
                miner_class=msg.get("miner_class"),
                gpu_type=msg.get("gpu_type"),
                vram_gb=msg.get("vram_gb"),
            )

            # Return welcome with peer list for bootstrapping
            peers = self.registry.discover_peers(
                peer_type=None,
                limit=20,
                exclude=[peer_id],
            )

            return {
                "type": LighthouseMessageType.WELCOME.value,
                "peer_id": peer_id,
                "lighthouse_id": self.node_id,
                "peers": peers,
                "peer_count": len(self.registry.peers),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except ValueError as e:
            return {
                "type": LighthouseMessageType.ERROR.value,
                "error": str(e),
            }

    async def _handle_heartbeat(self, msg: Dict) -> Dict:
        """Handle peer heartbeat."""
        peer_id = msg.get("peer_id")
        if not peer_id:
            return {"type": LighthouseMessageType.ERROR.value, "error": "missing peer_id"}

        success = await self.registry.heartbeat(
            peer_id=peer_id,
            chain_height=msg.get("chain_height", 0),
            consensus_role=msg.get("consensus_role"),
        )

        if success:
            return {"type": LighthouseMessageType.ACK.value, "peer_id": peer_id}
        else:
            return {
                "type": LighthouseMessageType.ERROR.value,
                "error": "peer not registered — send REGISTER first",
            }

    async def _handle_discover(self, msg: Dict) -> Dict:
        """Handle peer discovery request."""
        peer_type = msg.get("peer_type")
        limit = msg.get("limit", 20)
        exclude = msg.get("exclude", [])
        miner_class = msg.get("miner_class")

        peers = self.registry.discover_peers(
            peer_type=peer_type,
            limit=limit,
            exclude=exclude,
            miner_class=miner_class,
        )

        return {
            "type": LighthouseMessageType.PEERS.value,
            "peers": peers,
            "total_known": len(self.registry.peers),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    async def _handle_deregister(self, msg: Dict) -> Dict:
        """Handle peer deregistration (graceful shutdown)."""
        peer_id = msg.get("peer_id")
        if not peer_id:
            return {"type": LighthouseMessageType.ERROR.value, "error": "missing peer_id"}

        success = await self.registry.deregister(peer_id)
        return {"type": LighthouseMessageType.ACK.value, "removed": success}

    async def _health_sweep_loop(self):
        """Periodically sweep for stale/dead peers."""
        while self._running:
            await asyncio.sleep(60)
            await self.registry.sweep_stale_peers()
            stats = self.registry.get_stats()
            logger.debug(
                f"Health sweep: {stats['total_peers']} peers "
                f"({stats['by_status'].get('active', 0)} active, "
                f"{stats['by_status'].get('stale', 0)} stale, "
                f"{stats['by_status'].get('dead', 0)} dead)"
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get discovery server statistics."""
        return {
            "node_id": self.node_id,
            "port": self.port,
            "running": self._running,
            "active_connections": self._connections,
            "total_connections": self._total_connections,
            "started_at": self._started_at,
            "registry": self.registry.get_stats(),
        }


# Global instance
discovery_server = DiscoveryServer()
