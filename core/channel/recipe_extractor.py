from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from core.channel.models import RecipeRecord
from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)

# Common stop words for normalizing recipe names
RECIPE_STOP_WORDS = {
    "recipe", "recipes", "how", "to", "make", "easy", "quick", "tasty", "delicious",
    "crispy", "crunchy", "famous", "street", "food", "style", "shorts", "short",
    "video", "viral", "trend", "trending", "authentic", "best", "super", "yummy",
    "simple", "homemade", "diy", "asmr", "satisfying", "secret", "village",
    "dinner", "lunch", "breakfast", "meal", "idea", "ideas",
}

KNOWN_INGREDIENTS = [
    "chicken", "paneer", "potato", "potatoes", "cheese", "garlic", "egg", "eggs",
    "pasta", "rice", "mushroom", "mushrooms", "tomato", "tomatoes", "onion", "onions",
    "spinach", "butter", "cream", "chili", "chilies", "ginger", "coriander", "beef",
    "mutton", "fish", "prawn", "prawns", "shrimp", "noodles", "bread", "chocolate",
    "milk", "yogurt", "lemon", "lime", "lentil", "lentils", "dal", "chickpeas",
    "tofu", "capsicum", "bell pepper", "cauliflower", "cabbage", "corn",
]

KNOWN_CUISINES = {
    "indian": ["curry", "tikka", "masala", "biryani", "paneer", "dal", "tandoori", "samosa", "dosa", "roti", "naan", "chaat", "paratha"],
    "italian": ["pasta", "pizza", "spaghetti", "risotto", "lasagna", "carbonara", "pesto", "ravioli"],
    "mexican": ["taco", "burrito", "quesadilla", "salsa", "guacamole", "nachos", "fajita", "enchilada"],
    "asian": ["noodles", "ramen", "dumpling", "sushi", "stir fry", "fried rice", "wonton", "dim sum", "teriyaki"],
    "american": ["burger", "sandwich", "wings", "fries", "bbq", "mac and cheese", "hot dog"],
    "middle eastern": ["hummus", "falafel", "shawarma", "kebab", "pita", "tahini", "baklava"],
}

KNOWN_METHODS = [
    "deep fry", "shallow fry", "fry", "fried", "bake", "baked", "roast", "roasted",
    "grill", "grilled", "simmer", "simmered", "boil", "boiled", "saute", "sauteed",
    "steam", "steamed", "tandoor", "tandoori", "smoke", "smoked", "caramelize",
]


def normalize_recipe_name(title: str) -> str:
    """Normalize recipe title to a canonical key."""
    # Remove hashtags and bracketed text
    clean = re.sub(r"#\S+", "", title)
    clean = re.sub(r"\[.*?\]|\(.*?\)", "", clean)
    # Lowercase and keep letters, numbers, spaces
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", clean.lower())
    words = clean.split()
    filtered = [w for w in words if w not in RECIPE_STOP_WORDS and len(w) > 1]
    if not filtered:
        return "unnamed_recipe"
    return " ".join(filtered)


class RecipeExtractor:
    """Extracts structured culinary and storytelling intelligence from video data."""

    def __init__(self, db: MemoryDB):
        self.db = db

    def extract_and_save(self, channel_profile_id: int, video_data: dict[str, Any]) -> RecipeRecord:
        record = self.extract(video_data)
        record.channel_profile_id = channel_profile_id
        record.channel_video_id = video_data.get("id")

        rec_dict = record.to_dict()
        saved_id = self.db.save_recipe_record(rec_dict)
        record.id = saved_id
        return record

    def extract(self, video_data: dict[str, Any]) -> RecipeRecord:
        title = video_data.get("title", "")
        desc = video_data.get("description", "")
        norm_name = normalize_recipe_name(title)
        full_text = f"{title} {desc}".lower()

        # Try heuristics
        primary_ing = self._find_primary_ingredient(norm_name, full_text)
        secondary_ings = self._find_secondary_ingredients(full_text, primary_ing)
        cuisine = self._detect_cuisine(full_text)
        method = self._detect_cooking_method(full_text)
        category = self._detect_category(full_text, norm_name)
        flavor = self._detect_flavor(full_text)
        env = "rustic kitchen" if any(w in full_text for w in ["outdoor", "village", "fire", "clay", "wood"]) else "modern kitchen"

        # Construct signatures
        ing_sig = f"{primary_ing}:" + ",".join(sorted(secondary_ings))
        topic_sig = f"{category}:{cuisine}:{norm_name}"
        story_sig = f"hook->prep({method})->sizzle({primary_ing})->taste_reveal"
        vis_sig = "cinematic_vertical_macro_lighting"
        nov_sig = hashlib.sha256(f"{norm_name}|{ing_sig}".encode("utf-8")).hexdigest()[:16]

        sigs = {
            "ingredient_signature": ing_sig,
            "topic_signature": topic_sig,
            "story_signature": story_sig,
            "visual_signature": vis_sig,
            "novelty_signature": nov_sig,
        }

        # Build clean recipe title from words
        display_name = title.split("|")[0].split("-")[0].split("#")[0].strip()
        if not display_name:
            display_name = norm_name.title()

        return RecipeRecord(
            recipe_name=display_name,
            normalized_recipe_name=norm_name,
            dish_category=category,
            cuisine=cuisine,
            region=cuisine,
            primary_ingredient=primary_ing,
            secondary_ingredients=secondary_ings,
            cooking_method=method,
            flavor_profile=flavor,
            environment=env,
            signatures=sigs,
        )

    def _find_primary_ingredient(self, norm_name: str, full_text: str) -> str:
        # Check normalized title first
        for ing in KNOWN_INGREDIENTS:
            if ing in norm_name:
                return ing
        # Check full text
        for ing in KNOWN_INGREDIENTS:
            if ing in full_text:
                return ing
        return "mixed"

    def _find_secondary_ingredients(self, full_text: str, primary: str) -> list[str]:
        found = []
        for ing in KNOWN_INGREDIENTS:
            if ing != primary and ing in full_text:
                found.append(ing)
        return found[:5]

    def _detect_cuisine(self, full_text: str) -> str:
        scores: dict[str, int] = {}
        for cuisine, keywords in KNOWN_CUISINES.items():
            count = sum(1 for kw in keywords if kw in full_text)
            if count > 0:
                scores[cuisine] = count
        if scores:
            best = max(scores.items(), key=lambda item: item[1])[0]
            return best.capitalize()
        return "Fusion"

    def _detect_cooking_method(self, full_text: str) -> str:
        for m in KNOWN_METHODS:
            if m in full_text:
                return m
        return "saute & simmer"

    def _detect_category(self, full_text: str, norm_name: str) -> str:
        if any(w in full_text for w in ["dessert", "cake", "sweet", "ice cream", "cookie", "halwa", "kheer"]):
            return "dessert"
        if any(w in full_text for w in ["snack", "bite", "crispy", "finger food", "appetizer"]):
            return "snack / appetizer"
        if any(w in full_text for w in ["curry", "gravy", "masala"]):
            return "curry / gravy"
        if any(w in full_text for w in ["rice", "biryani", "pulao"]):
            return "rice dish"
        if any(w in full_text for w in ["bread", "roti", "naan", "paratha"]):
            return "bread"
        if any(w in full_text for w in ["drink", "shake", "smoothie", "juice", "tea", "coffee"]):
            return "beverage"
        return "main course"

    def _detect_flavor(self, full_text: str) -> str:
        if any(w in full_text for w in ["spicy", "hot", "fire", "tikha"]):
            return "spicy & aromatic"
        if any(w in full_text for w in ["sweet", "sugar", "honey"]):
            return "sweet & rich"
        if any(w in full_text for w in ["tangy", "chatpata", "sour", "lemon"]):
            return "tangy & savory"
        if any(w in full_text for w in ["creamy", "butter", "cheese"]):
            return "rich & creamy"
        return "savory & flavorful"
