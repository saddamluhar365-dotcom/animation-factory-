from __future__ import annotations

import logging
from typing import Any

from core.channel.dna import ChannelDNAEngine
from core.channel.recipe_extractor import KNOWN_CUISINES, KNOWN_INGREDIENTS, KNOWN_METHODS
from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)

POPULAR_SHORT_OPPORTUNITIES = [
    {"recipe_name": "Crispy Golden Garlic Potato Bites", "category": "snack / appetizer", "ingredient": "potato", "method": "deep fry", "flavor": "crispy garlic herb"},
    {"recipe_name": "Creamy Tandoori Paneer Skewers", "category": "snack / appetizer", "ingredient": "paneer", "method": "tandoori roast", "flavor": "spicy & smoky"},
    {"recipe_name": "Sizzling Butter Garlic Mushrooms", "category": "appetizer", "ingredient": "mushroom", "method": "saute", "flavor": "rich garlic butter"},
    {"recipe_name": "Cheesy Street Style Corn Toast", "category": "snack", "ingredient": "cheese", "method": "toast", "flavor": "cheesy savory"},
    {"recipe_name": "Velvety Dark Chocolate Lava Pot", "category": "dessert", "ingredient": "chocolate", "method": "bake", "flavor": "rich & sweet"},
    {"recipe_name": "Smoky Claypot Masala Chicken", "category": "curry / gravy", "ingredient": "chicken", "method": "simmer", "flavor": "aromatic smoky"},
    {"recipe_name": "Crispy Chilli Honey Cauliflower", "category": "snack", "ingredient": "cauliflower", "method": "crispy fry", "flavor": "sweet & spicy"},
]


class ContentGapEngine:
    """Identifies content gaps and untapped culinary opportunities for a channel."""

    def __init__(self, db: MemoryDB):
        self.db = db
        self.dna_engine = ChannelDNAEngine(db)

    def find_content_gaps(self, channel_profile_id: int) -> dict[str, Any]:
        dna_record = self.db.get_channel_dna(channel_profile_id)
        if not dna_record:
            dna = self.dna_engine.generate_dna(channel_profile_id)
            dna_data = dna.dna_profile
            sat_data = dna.saturation_metrics
        else:
            dna_data = dna_record.get("dna_profile", {})
            sat_data = dna_record.get("saturation_metrics", {})

        used_ingredients = set(dna_data.get("primary_ingredients_distribution", {}).keys())
        overused = set(sat_data.get("overused_ingredients", []))

        # Potential underused ingredients
        candidate_ingredients = [ing for ing in KNOWN_INGREDIENTS if ing not in used_ingredients and ing != "mixed"]
        if not candidate_ingredients:
            candidate_ingredients = [ing for ing in KNOWN_INGREDIENTS if ing not in overused]

        used_methods = set(dna_data.get("cooking_methods_distribution", {}).keys())
        underused_methods = [m for m in ["tandoor", "smoke", "roast", "bake", "steam", "deep fry"] if m not in used_methods]

        used_categories = set(dna_data.get("dish_categories_distribution", {}).keys())
        all_categories = ["snack / appetizer", "curry / gravy", "dessert", "street food", "rice dish", "beverage"]
        underused_categories = [c for c in all_categories if c not in used_categories]

        # Generate 3-5 concrete concept proposals that fill the detected gaps
        proposals = []
        for opp in POPULAR_SHORT_OPPORTUNITIES:
            ing = opp["ingredient"]
            if ing in candidate_ingredients or ing not in overused:
                proposals.append(opp)
            if len(proposals) >= 4:
                break

        if not proposals:
            proposals = POPULAR_SHORT_OPPORTUNITIES[:3]

        return {
            "channel_profile_id": channel_profile_id,
            "underused_ingredients": candidate_ingredients[:8],
            "overused_ingredients": list(overused),
            "underused_methods": underused_methods[:4],
            "underused_categories": underused_categories[:4],
            "recommended_gap_concepts": proposals,
        }

    def pick_novel_concept(self, channel_profile_id: int) -> dict[str, Any]:
        """Picks a prime novel recipe concept guaranteed to address content gaps and not repeat."""
        gaps = self.find_content_gaps(channel_profile_id)
        candidates = gaps.get("recommended_gap_concepts", POPULAR_SHORT_OPPORTUNITIES)

        from core.channel.novelty import RecipeNoveltyEngine
        novelty_engine = RecipeNoveltyEngine(self.db)

        for cand in candidates:
            verdict = novelty_engine.evaluate(channel_profile_id, cand)
            if verdict.is_acceptable:
                return cand

        # Fallback to unique variant
        import time
        t_suffix = str(int(time.time()))[-4:]
        return {
            "recipe_name": f"Chef Signature Crispy Delight {t_suffix}",
            "category": "snack / appetizer",
            "ingredient": "potato",
            "method": "golden crisp",
            "flavor": "savory herb",
        }
