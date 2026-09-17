from __future__ import annotations

import logging
from typing import Any

from core.channel.models import ImprovementRecord
from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)


class ImprovementEngine:
    """Generates actionable improvement signals and recommendations for channel performance."""

    def __init__(self, db: MemoryDB):
        self.db = db

    def generate_recommendations(self, channel_profile_id: int) -> list[ImprovementRecord]:
        dna_record = self.db.get_channel_dna(channel_profile_id)
        sat_data = dna_record.get("saturation_metrics", {}) if dna_record else {}
        overused = sat_data.get("overused_ingredients", [])

        recommendations: list[ImprovementRecord] = []

        # 1. Content Diversity Recommendation
        if overused:
            rec1 = ImprovementRecord(
                channel_profile_id=channel_profile_id,
                area="content_diversity",
                observation=f"Ingredients {', '.join(overused)} represent over 25% of recent videos.",
                evidence={"overused_ingredients": overused},
                recommendation=f"Diversify menu with complementary ingredients (e.g., paneer, mushroom, crispy potato) to prevent audience fatigue.",
                confidence=0.92,
            )
            self.db.save_improvement_signal(channel_profile_id, rec1.to_dict())
            recommendations.append(rec1)

        # 2. Audio & ASMR Production
        rec2 = ImprovementRecord(
            channel_profile_id=channel_profile_id,
            area="audio_asmr",
            observation="Culinary Shorts retain 35% higher watch time when sizzling, knife-chop, and pouring ASMR audio cues are prominently featured.",
            evidence={"benchmark_category": "food_asmr"},
            recommendation="Enhance high-frequency audio Foley (knife cutting board impact, oil bubbling, sizzle resonance) in sound timeline.",
            confidence=0.95,
        )
        self.db.save_improvement_signal(channel_profile_id, rec2.to_dict())
        recommendations.append(rec2)

        # 3. Hook & Pacing
        rec3 = ImprovementRecord(
            channel_profile_id=channel_profile_id,
            area="visual_hook",
            observation="Immediate physical contact or sizzling close-up within the first 1.5 seconds drives higher swipe-through retention.",
            evidence={"retention_best_practice": "immediate_action"},
            recommendation="Ensure Scene 1 opens directly on physical food preparation with a rapid camera push-in rather than wide static setup.",
            confidence=0.90,
        )
        self.db.save_improvement_signal(channel_profile_id, rec3.to_dict())
        recommendations.append(rec3)

        return recommendations
