from __future__ import annotations

import difflib
import logging
from typing import Any

from core.channel.models import NoveltyStatus, NoveltyVerdict, RecipeRecord
from core.channel.recipe_extractor import normalize_recipe_name
from core.db.memory import MemoryDB

logger = logging.getLogger(__name__)


def jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


class RecipeNoveltyEngine:
    """Enforces a hard no-repeat novelty check against channel recipe memory."""

    def __init__(self, db: MemoryDB):
        self.db = db

    def evaluate(
        self,
        channel_profile_id: int,
        candidate: str | dict[str, Any] | RecipeRecord,
    ) -> NoveltyVerdict:
        existing_recipes = self.db.get_recipes(channel_profile_id)
        return self.evaluate_against_recipes(candidate, existing_recipes)

    def evaluate_against_recipes(
        self,
        candidate: str | dict[str, Any] | RecipeRecord,
        existing_recipes: list[dict[str, Any] | RecipeRecord],
    ) -> NoveltyVerdict:
        if not existing_recipes:
            return NoveltyVerdict(
                status=NoveltyStatus.NOVEL,
                score=1.0,
                reasons=["Channel recipe memory is empty; candidate is fully novel."],
            )

        # Parse candidate fields
        if isinstance(candidate, str):
            c_name = candidate
            c_norm = normalize_recipe_name(candidate)
            c_primary = ""
            c_secondaries: list[str] = []
            c_method = ""
        elif isinstance(candidate, RecipeRecord):
            c_name = candidate.recipe_name
            c_norm = candidate.normalized_recipe_name or normalize_recipe_name(c_name)
            c_primary = candidate.primary_ingredient.lower()
            c_secondaries = [s.lower() for s in candidate.secondary_ingredients]
            c_method = candidate.cooking_method.lower()
        else:
            c_name = candidate.get("recipe_name", candidate.get("title", ""))
            c_norm = candidate.get("normalized_recipe_name") or normalize_recipe_name(c_name)
            c_primary = str(candidate.get("primary_ingredient", "")).lower()
            c_secondaries = [str(s).lower() for s in candidate.get("secondary_ingredients", [])]
            c_method = str(candidate.get("cooking_method", "")).lower()

        c_words = set(c_norm.split())
        c_ing_set = set([c_primary] + c_secondaries) if c_primary else set(c_secondaries)

        highest_sim = 0.0
        worst_verdict: NoveltyVerdict | None = None

        for rec in existing_recipes:
            r_norm = (
                rec.normalized_recipe_name
                if isinstance(rec, RecipeRecord)
                else rec.get("normalized_recipe_name", "")
            ) or normalize_recipe_name(rec.recipe_name if isinstance(rec, RecipeRecord) else rec.get("recipe_name", ""))
            r_name = rec.recipe_name if isinstance(rec, RecipeRecord) else rec.get("recipe_name", "")
            r_vid = rec.channel_video_id if isinstance(rec, RecipeRecord) else rec.get("channel_video_id")

            # 1. Exact normalized name match
            if c_norm == r_norm:
                return NoveltyVerdict(
                    status=NoveltyStatus.DUPLICATE,
                    score=0.0,
                    reasons=[f"Exact duplicate of existing channel recipe: '{r_name}'"],
                    matched_recipe=r_name,
                    matched_video_id=str(r_vid) if r_vid else None,
                )

            # 2. String sequence similarity (e.g. "butter chicken" vs "chicken butter")
            seq_ratio = difflib.SequenceMatcher(None, c_norm, r_norm).ratio()
            r_words = set(r_norm.split())
            name_jaccard = jaccard_similarity(c_words, r_words)

            if seq_ratio >= 0.85 or name_jaccard >= 0.80:
                return NoveltyVerdict(
                    status=NoveltyStatus.DUPLICATE,
                    score=round(1.0 - max(seq_ratio, name_jaccard), 2),
                    reasons=[f"Near-exact title match ({round(max(seq_ratio, name_jaccard)*100)}%) with '{r_name}'"],
                    matched_recipe=r_name,
                    matched_video_id=str(r_vid) if r_vid else None,
                )

            # 3. Ingredient & method overlap
            r_primary = (
                rec.primary_ingredient if isinstance(rec, RecipeRecord) else rec.get("primary_ingredient", "")
            ).lower()
            r_sec = rec.secondary_ingredients if isinstance(rec, RecipeRecord) else (rec.get("secondary_ingredients") or [])
            r_secondaries = [str(s).lower() for s in r_sec]
            r_method = (rec.cooking_method if isinstance(rec, RecipeRecord) else rec.get("cooking_method", "")).lower()

            r_ing_set = set([r_primary] + r_secondaries) if r_primary else set(r_secondaries)

            ing_overlap = jaccard_similarity(c_ing_set, r_ing_set) if c_ing_set and r_ing_set else 0.0
            method_match = bool(c_method and r_method and (c_method == r_method or c_method in r_method or r_method in c_method))
            primary_match = bool(c_primary and r_primary and c_primary == r_primary)

            if primary_match and ing_overlap >= 0.65 and method_match:
                return NoveltyVerdict(
                    status=NoveltyStatus.NEAR_DUPLICATE,
                    score=round(1.0 - ing_overlap, 2),
                    reasons=[
                        f"High ingredient overlap ({round(ing_overlap*100)}%) and matching cooking method ({c_method}) with '{r_name}'"
                    ],
                    matched_recipe=r_name,
                    matched_video_id=str(r_vid) if r_vid else None,
                )

            current_sim = max(seq_ratio, name_jaccard, ing_overlap)
            if current_sim > highest_sim:
                highest_sim = current_sim
                if current_sim >= 0.60:
                    worst_verdict = NoveltyVerdict(
                        status=NoveltyStatus.NEAR_DUPLICATE,
                        score=round(1.0 - current_sim, 2),
                        reasons=[f"High semantic similarity ({round(current_sim*100)}%) with '{r_name}'"],
                        matched_recipe=r_name,
                        matched_video_id=str(r_vid) if r_vid else None,
                    )
                elif current_sim >= 0.35:
                    worst_verdict = NoveltyVerdict(
                        status=NoveltyStatus.LOW_SIMILARITY,
                        score=round(1.0 - current_sim, 2),
                        reasons=[f"Acceptable moderate overlap ({round(current_sim*100)}%) with '{r_name}'"],
                        matched_recipe=r_name,
                        matched_video_id=str(r_vid) if r_vid else None,
                    )

        if worst_verdict:
            return worst_verdict

        return NoveltyVerdict(
            status=NoveltyStatus.NOVEL,
            score=round(1.0 - highest_sim, 2),
            reasons=["Concept is fully novel compared to all channel recipes."],
        )
