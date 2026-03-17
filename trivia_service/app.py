import asyncio
import os
import random
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Configuration from environment
# ---------------------------------------------------------------------------
INSTANCE_NAME = os.getenv("INSTANCE_NAME", "trivia-svc-unknown")
INSTANCE_PORT = int(os.getenv("INSTANCE_PORT", "5001"))
REGISTRY_URL  = os.getenv("REGISTRY_URL", "http://localhost:8000")

HEARTBEAT_INTERVAL = 5      # seconds between heartbeats
MAX_REGISTER_RETRIES = 10   # startup registration attempts

# ---------------------------------------------------------------------------
# Trivia facts (no external API dependency)
# ---------------------------------------------------------------------------
TRIVIA_FACTS = [
    "Honey never spoils — archaeologists found 3,000-year-old honey in Egyptian tombs still perfectly edible.",
    "A group of flamingos is called a flamboyance.",
    "Octopuses have three hearts and blue blood.",
    "The shortest war in history lasted 38–45 minutes: the Anglo-Zanzibar War of 1896.",
    "A day on Venus is longer than a year on Venus.",
    "Bananas are berries, but strawberries are not — botanically speaking.",
    "The Eiffel Tower can grow up to 15 cm taller in summer due to thermal expansion.",
    "Cleopatra lived closer in time to the Moon landing than to the construction of the Great Pyramid.",
    "Oxford University is older than the Aztec Empire.",
    "Wombat droppings are cube-shaped — the only known animal to produce cubic feces.",
    "There are more possible chess games than atoms in the observable universe.",
    "The unicorn is the national animal of Scotland.",
    "A bolt of lightning contains enough energy to toast roughly 100,000 slices of bread.",
    "Crows can recognize and remember individual human faces for years.",
    "The inventor of the Pringles can, Fredric Baur, had some of his ashes buried in one.",
    "Sharks are older than trees — they've existed for over 400 million years.",
    "The letter 'Q' does not appear in any U.S. state name.",
    "A snail can sleep for up to 3 years during drought conditions.",
    "Hot water can freeze faster than cold water under certain conditions (the Mpemba effect).",
    "A single cloud can weigh more than a million pounds despite appearing weightless.",
]

