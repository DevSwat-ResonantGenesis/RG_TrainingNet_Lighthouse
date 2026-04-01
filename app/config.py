"""RG Lighthouse configuration."""

import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Service
    SERVICE_NAME: str = "rg-lighthouse"
    SERVICE_VERSION: str = "0.1.0"

    # Node identity
    NODE_ID: str = os.getenv("NODE_ID", "lighthouse-0")

    # P2P Discovery
    P2P_PORT: int = int(os.getenv("P2P_PORT", "8600"))
    P2P_MAX_PEERS: int = int(os.getenv("P2P_MAX_PEERS", "500"))
    PING_INTERVAL: int = int(os.getenv("PING_INTERVAL", "30"))
    DISCOVERY_INTERVAL: int = int(os.getenv("DISCOVERY_INTERVAL", "60"))
    PEER_TIMEOUT: int = int(os.getenv("PEER_TIMEOUT", "120"))

    # Bootstrap (other lighthouses for cross-discovery)
    BOOTSTRAP_LIGHTHOUSES: str = os.getenv("BOOTSTRAP_LIGHTHOUSES", "[]")

    # API
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # Peer categories
    MINER_PEER_QUOTA: int = int(os.getenv("MINER_PEER_QUOTA", "200"))
    CHAIN_PEER_QUOTA: int = int(os.getenv("CHAIN_PEER_QUOTA", "100"))
    VALIDATOR_PEER_QUOTA: int = int(os.getenv("VALIDATOR_PEER_QUOTA", "50"))

    # Redis (for shared peer state across lighthouse replicas)
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://redis:6379/7")

    class Config:
        env_file = ".env"


settings = Settings()
