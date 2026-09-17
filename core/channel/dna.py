from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from core.channel.models import ChannelDNA, RecipeRecord
from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)


class ChannelDNAEngine:
    """Computes distributions, content saturation, and persistent Channel DNA."""

    def __init__(self, db: MemoryDB):
        self.db = db

    def generate_dna(self, channel_profile_id: int) -> ChannelDNA:
        recipes = self.db.get_recipes(channel_profile_id)
        videos = self.db.get_channel_videos(channel_profile_id, only_shorts=True)

        if not recipes and not videos:
            # Default fallback DNA
            default_dna = {
                "channel_profile_id": channel_profile_id,
                "dominant_cuisine": "Fusion",
                "signature_style": "Silent cinematic vertical culinary Short with ASMR sound effects",
                "pacing": "3-5 second visual beats with physical continuity",
                "primary_ingredients_distribution": {},
                "cooking_methods_distribution": {},
                "dish_categories_distribution": {},
                "total_recipes_analyzed": 0,
            }
            default_sat = {
                "overused_ingredients": [],
                "underrepresented_categories": ["street food", "snack / appetizer", "dessert"],
                "saturation_score": 0.0,
            }
            self.db.save_channel_dna(channel_profile_id, default_dna, default_sat)
            return ChannelDNA(channel_profile_id, default_dna, default_sat)

        total_rec = len(recipes) or 1
        ing_counter = Counter([r.get("primary_ingredient", "mixed") for r in recipes if r.get("primary_ingredient")])
        cuisine_counter = Counter([r.get("cuisine", "Fusion") for r in recipes if r.get("cuisine")])
        method_counter = Counter([r.get("cooking_method", "fry") for r in recipes if r.get("cooking_method")])
        cat_counter = Counter([r.get("dish_category", "main course") for r in recipes if r.get("dish_category")])

        # Calculate percentages
        ing_dist = {k: round(v / total_rec * 100, 1) for k, v in ing_counter.most_common(10)}
        cuisine_dist = {k: round(v / total_rec * 100, 1) for k, v in cuisine_counter.most_common(5)}
        method_dist = {k: round(v / total_rec * 100, 1) for k, v in method_counter.most_common(5)}
        cat_dist = {k: round(v / total_rec * 100, 1) for k, v in cat_counter.most_common(5)}

        # Overused ingredients (>25% share if total recipes >= 3)
        overused = [k for k, pct in ing_dist.items() if pct >= 25.0 and total_rec >= 3 and k != "mixed"]

        dominant_cuisine = cuisine_counter.most_common(1)[0][0] if cuisine_counter else "Fusion"
        dominant_method = method_counter.most_common(1)[0][0] if method_counter else "saute"

        dna_profile = {
            "channel_profile_id": channel_profile_id,
            "dominant_cuisine": dominant_cuisine,
            "dominant_cooking_method": dominant_method,
            "signature_style": f"Cinematic {dominant_cuisine} vertical culinary Short; emphasis on sizzling textures and rich natural lighting",
            "pacing": "Dynamic rhythmic cutting with physical ingredient continuity and ASMR sound effects",
            "primary_ingredients_distribution": ing_dist,
            "cuisines_distribution": cuisine_dist,
            "cooking_methods_distribution": method_dist,
            "dish_categories_distribution": cat_dist,
            "total_recipes_analyzed": total_rec,
            "total_shorts_analyzed": len(videos),
        }

        saturation_metrics = {
            "overused_ingredients": overused,
            "saturated_cooking_methods": [k for k, pct in method_dist.items() if pct >= 35.0 and total_rec >= 3],
            "saturation_score": round(len(overused) * 0.25, 2),
            "diversity_ratio": round(len(ing_counter) / total_rec, 2) if total_rec > 0 else 1.0,
        }

        self.db.save_channel_dna(channel_profile_id, dna_profile, saturation_metrics)
        return ChannelDNA(channel_profile_id, dna_profile, saturation_metrics)
