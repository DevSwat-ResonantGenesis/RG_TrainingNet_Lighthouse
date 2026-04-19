# RG_TrainingNet_Lighthouse

The **bootstrap/discovery node** for the Training Network. Every new node (miner, chain node, validator) contacts a Lighthouse first to discover peers and join the mesh.

> **Part of the Training Network** (3 repos):
> - **RG_TrainingNet_Chain** — Raft consensus chain, block production
> - **RG_TrainingNet_Mining** — Gradient aggregation, sharded training, RGT rewards
> - **RG_TrainingNet_Lighthouse** (this) — Peer discovery, network beacon

> **Not to be confused with:**
> - **RG_DSID_Blockchain** — Internal audit/governance ledger (completely separate chain)
> - **RG_DSID_Node** — DSID execution layer (agent runtime, not training)

## Role in the Architecture

```
┌──────────────┐     REGISTER      ┌─────────────────┐
│  New Miner   │ ─────────────────▶│   LIGHTHOUSE     │
│  (CLASS_H)   │ ◀───────────────  │   (Bootstrap)    │
└──────────────┘    WELCOME +      │                  │
                    peer list      │  Peer Registry   │
                                   │  Health Monitor  │
┌──────────────┐     DISCOVER      │  Discovery TCP   │
│  Chain Node  │ ─────────────────▶│                  │
│              │ ◀───────────────  └─────────────────┘
└──────────────┘    PEERS list
```

| Module | Depends On Lighthouse |
|--------|----------------------|
| **RG_TrainingNet_Mining** | Miners register here to discover tasks + validators |
| **RG_TrainingNet_Chain** | Chain nodes register here to discover consensus peers |

## Components

| File | Purpose |
|------|---------|
| `peer_registry.py` | Central peer storage: register, heartbeat, discovery, eviction, banning |
| `discovery_server.py` | TCP server: handles REGISTER, HEARTBEAT, DISCOVER, DEREGISTER messages |
| `routers.py` | REST API for programmatic peer management |
| `main.py` | FastAPI app + TCP server lifecycle |
| `config.py` | Service configuration |

## Peer Types

| Type | Who | Purpose |
|------|-----|---------|
| `miner` | CLASS_F/G/H nodes | Training task workers |
| `validator` | CLASS_F Lighthouse nodes | Genesis validators, param servers |
| `chain` | Full nodes | Run distributed blockchain consensus |
| `lighthouse` | Other lighthouses | Cross-discovery between lighthouse replicas |

## TCP Discovery Protocol

```
Client → Lighthouse:  {"type": "register", "peer_id": "...", "peer_type": "miner", "address": "10.0.0.5", "p2p_port": 8600}
Lighthouse → Client:  {"type": "welcome", "peers": [...], "peer_count": 42}

Client → Lighthouse:  {"type": "heartbeat", "peer_id": "..."}
Lighthouse → Client:  {"type": "ack"}

Client → Lighthouse:  {"type": "discover", "peer_type": "validator", "limit": 10}
Lighthouse → Client:  {"type": "peers", "peers": [...]}
```

## REST API Endpoints

```
POST /lighthouse/register          — Register a peer (returns bootstrap peer list)
POST /lighthouse/heartbeat         — Send heartbeat
POST /lighthouse/discover          — Discover peers by type/class
POST /lighthouse/deregister/{id}   — Graceful deregister
POST /lighthouse/ban/{id}          — Ban a peer
GET  /lighthouse/peers             — List all peers
GET  /lighthouse/peers/{id}        — Get specific peer
GET  /lighthouse/validators        — List validators
GET  /lighthouse/miners            — List miners
GET  /lighthouse/chain-nodes       — List chain nodes
GET  /lighthouse/stats             — Server + registry stats
GET  /lighthouse/health            — Health check
```

## Running

```bash
docker build -t rg-lighthouse .
docker run -p 8000:8000 -p 8600:8600 \
  -e NODE_ID=lighthouse-0 \
  -e P2P_PORT=8600 \
  rg-lighthouse
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | `lighthouse-0` | Lighthouse node ID |
| `P2P_PORT` | `8600` | TCP discovery port |
| `P2P_MAX_PEERS` | `500` | Max peers in registry |
| `PING_INTERVAL` | `30` | Seconds between pings |
| `PEER_TIMEOUT` | `120` | Seconds before marking peer stale |
| `BOOTSTRAP_LIGHTHOUSES` | `[]` | Other lighthouse addresses for cross-discovery |
