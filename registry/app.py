import asyncio
import time
from contextlib import asynccontextmanager
from typing import Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# In-memory state
# ---------------------------------------------------------------------------
services: Dict[str, Dict[str, dict]] = {}

TTL_SECONDS = 15.0      # instance marked dead if no heartbeat for 15s
PURGE_SECONDS = 30.0    # instance removed from memory after 30s (2x TTL)
SWEEP_INTERVAL = 10.0   # sweep runs every 10s
