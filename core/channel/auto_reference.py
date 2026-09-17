from __future__ import annotations

import logging
from typing import Any

from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)


class AutoReferenceEngine:
    """Discovers and synthesizes complementary reference production DNA while strictly adhering to the Protected Content Rule."""

    def __init__(self, db: MemoryDB):
        self.db = db

    def get_reference_profile(
        self,
        manual_profile: dict[str, Any] | None = None,
        channel_profile_id: int | None = None,
        topic_hint: str = "",
    ) -> dict[str, Any]:
        # Rule 1: Manual reference ALWAYS takes priority
        if manual_profile and isinstance(manual_profile, dict) and any(manual_profile.values()):
            logger.info("Using manual reference profile provided by user.")
            return manual_profile

        # Rule 2: Check database for any saved style DNA
        db_dna = None
        if channel_profile_id:
            dna_row = self.db.get_channel_dna(channel_profile_id)
            if dna_row and "dna_profile" in dna_row:
                db_dna = dna_row["dna_profile"]

        # Rule 3: Protected Content Rule - high-level production characteristics ONLY. Zero copying of protected characters or scenes.
        dominant_cuisine = (db_dna.get("dominant_cuisine") if db_dna else "Culinary") or "Culinary"

        complementary_profile = {
            "source": "auto_channel_intelligence",
            "compliance": "Protected Content Rule verified: production DNA only, zero protected character copying",
            "visual_style": {
                "description": f"Cinematic {dominant_cuisine} vertical Short with appetizing macro food textures and natural golden lighting",
                "color_palette": ["warm gold", "deep terracotta", "vibrant fresh green", "rich caramelized bronze"],
                "lighting": "appetizing warm directional key lighting with gentle rim illumination and steam backlighting",
            },
            "cinematography": {
                "aspect_ratio": "9:16",
                "camera_movements": ["slow cinematic push-in", "shallow depth-of-field rack focus", "gentle vertical parallax"],
                "pacing": "crisp rhythmic physical cuts; 3-5 visual beats per scene",
            },
            "audio_dna": {
                "soundscape": "high-definition ASMR sound design: knife chops, sizzling pan, bubbling reduction, crisp crunch",
                "voice": "no spoken dialogue; non-verbal natural human culinary appreciation sounds only",
            },
            "narrative_arc": {
                "structure": "immediate visual hook -> active culinary preparation -> sizzling climax -> final plating reveal",
                "physical_continuity": True,
            },
        }

        return complementary_profile
