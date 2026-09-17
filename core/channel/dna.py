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
        analyses = self.db.get_video_analyses(channel_profile_id, limit=10)

        total_rec = len(recipes)
        total_vid = len(videos)
        total_analyses = len(analyses)

        # 1. Recipe & Content distribution
        ing_counter = Counter([r.get("primary_ingredient", "mixed") for r in recipes if r.get("primary_ingredient")])
        cuisine_counter = Counter([r.get("cuisine", "Fusion") for r in recipes if r.get("cuisine")])
        method_counter = Counter([r.get("cooking_method", "fry") for r in recipes if r.get("cooking_method")])
        cat_counter = Counter([r.get("dish_category", "main course") for r in recipes if r.get("dish_category")])

        divisor = total_rec or 1
        ing_dist = {k: round(v / divisor * 100, 1) for k, v in ing_counter.most_common(10)}
        cuisine_dist = {k: round(v / divisor * 100, 1) for k, v in cuisine_counter.most_common(5)}
        method_dist = {k: round(v / divisor * 100, 1) for k, v in method_counter.most_common(5)}
        cat_dist = {k: round(v / divisor * 100, 1) for k, v in cat_counter.most_common(5)}

        dominant_cuisine = cuisine_counter.most_common(1)[0][0] if cuisine_counter else "Fusion"
        dominant_method = method_counter.most_common(1)[0][0] if method_counter else "sizzle & saute"

        # Overused ingredients (>25% share if total recipes >= 3)
        overused = [k for k, pct in ing_dist.items() if pct >= 25.0 and total_rec >= 3 and k != "mixed"]

        # 2. Extract characteristics from deep video analyses
        warmth_values = []
        shot_durations = []
        cpms = []
        all_anchors: list[str] = []
        winning_traits: list[str] = []
        weak_patterns: list[str] = []

        for a_row in analyses:
            data = a_row.get("analysis") or {}
            v_style = data.get("visual_style") or {}
            w = v_style.get("warmth_ratio")
            if w and isinstance(w, (int, float)):
                warmth_values.append(float(w))

            pacing = data.get("pacing") or {}
            sd = pacing.get("avg_shot_duration")
            if sd and isinstance(sd, (int, float)):
                shot_durations.append(float(sd))
            cpm_val = pacing.get("cuts_per_minute")
            if cpm_val and isinstance(cpm_val, (int, float)):
                cpms.append(float(cpm_val))

            anchors = data.get("consistency_anchors") or []
            if isinstance(anchors, list):
                all_anchors.extend(anchors)

            wins = data.get("successful_characteristics") or []
            if isinstance(wins, list):
                winning_traits.extend(wins)

            weaks = data.get("weak_patterns_identified") or []
            if isinstance(weaks, list):
                weak_patterns.extend(weaks)

        avg_warmth = round(sum(warmth_values) / len(warmth_values), 2) if warmth_values else 1.42
        avg_shot_dur = round(sum(shot_durations) / len(shot_durations), 2) if shot_durations else 2.2
        avg_cpm = round(sum(cpms) / len(cpms), 1) if cpms else 27.0

        unique_anchors = list(dict.fromkeys(all_anchors))[:5]
        if not unique_anchors:
            unique_anchors = [
                "consistent warm directional macro lighting with soft rim fill",
                "consistent chef hands in natural culinary technique with neutral sleeves",
                "consistent solid dark cutting board and matte cookware",
                "consistent shallow depth of field with creamy background bokeh",
                "photorealistic 8k vertical 9:16 framing, no text, no watermark",
            ]

        # 3. Construct 10 Facets of Channel DNA
        # Facet 1: Winning Style DNA
        winning_style_dna = {
            "signature": f"Cinematic {dominant_cuisine} vertical culinary Short; macro food textures, golden lighting, and ASMR Foley",
            "aesthetic_target": "Warm golden amber tone, tactile closeups, high kinetic continuity",
            "successful_characteristics": list(dict.fromkeys(winning_traits))[:5] or [
                "Sub-2-second immediate visual and acoustic sizzle hook",
                "Continuous physical utensil contact without object teleportation",
                "Action-synced crisp ASMR sound effects with zero artificial voiceover",
                "Irresistible macro plating reveal with steaming presentation",
            ],
            "quality_tier": "Tier-1 High Production Short",
        }

        # Facet 2: Content / Recipe DNA
        content_recipe_dna = {
            "dominant_cuisine": dominant_cuisine,
            "dominant_cooking_method": dominant_method,
            "cuisines_distribution": cuisine_dist,
            "cooking_methods_distribution": method_dist,
            "primary_ingredients_distribution": ing_dist,
            "dish_categories_distribution": cat_dist,
            "total_recipes_recorded": total_rec,
        }

        # Facet 3: Visual DNA
        visual_dna = {
            "aspect_ratio": "9:16",
            "resolution": [1080, 1920],
            "warmth_ratio": avg_warmth,
            "palette": "warm golden amber, rich culinary wood tones, appetizing warm highlights",
            "lighting": "warm directional macro spotlight, rim lighting, soft warm fill",
            "framing": "vertical 9:16 macro closeup, shallow depth of field, centered focal subject",
            "consistency_anchors": unique_anchors,
        }

        # Facet 4: Animation DNA
        animation_dna = {
            "target_fps": 60.0,
            "easing": "cubic_ease_in_out",
            "camera_motion_profiles": [
                "macro_push_in",
                "cinematic_drift",
                "dynamic_tilt",
                "reveal_pull_out",
                "parallax_shimmer",
            ],
            "motion_fluidity_score": 0.95,
            "anti_slideshow": True,
        }

        # Facet 5: Audio / ASMR DNA
        audio_asmr_dna = {
            "has_audio": True,
            "target_lufs": -14.0,
            "prevent_clipping": True,
            "foley_layers": [
                "ambient_presence",
                "crisp_sizzle",
                "wood_chop",
                "liquid_pour",
                "metallic_clink",
                "scrape_friction",
            ],
            "voiceover_rule": "No spoken dialogue; non-verbal natural human culinary appreciation sounds only",
            "peak_limiter": "alimiter=limit=0.88",
        }

        # Facet 6: Pacing DNA
        pacing_dna = {
            "avg_shot_duration": avg_shot_dur,
            "target_shot_range": [1.5, 3.2],
            "cadence": "fast_paced_high_retention",
            "cuts_per_minute": avg_cpm,
            "max_shot_duration": 4.5,
            "transitions": ["motion_cut", "subtle_crossfade", "dip_to_color"],
        }

        # Facet 7: Story DNA
        story_dna = {
            "structure": "3-Act Micro-Story",
            "act_1_hook": "Immediate vertical macro reveal (<2.0s) establishing tactile ingredient tension",
            "act_2_build": "Progressive transformation sequence with rhythmic cutting and sensory Foley",
            "act_3_payoff": "Plating reveal, steam rising, crispy bite crunch climax",
        }

        # Facet 8: Quality Rules
        quality_rules = [
            "Must be vertical 9:16 (1080x1920) composition",
            "Must be native 60.0 FPS output",
            "Camera movement must use non-linear cubic easing (no static slideshow feel)",
            "Audio must feature multi-layer action-synced ASMR Foley and ambient room tone",
            "Physical continuity must be maintained (no ingredient teleportation)",
            "Zero placeholder images or mock audio allowed in production",
            "Concept must be novel (not duplicate of existing recipe memory)",
        ]

        # Facet 9: Avoid / Bad Patterns
        avoid_bad_patterns = list(dict.fromkeys(weak_patterns))[:5] or [
            "Static slideshow feel with zero camera movement",
            "Shots lingering longer than 4.5 seconds without motion or cut",
            "Cold, washed-out, or flat daylight lighting",
            "Missing or unsynchronized Foley audio",
            "Audio clipping or excessive peak loudness",
            "Repetitive, duplicate, or near-identical dish names or ingredient combinations",
            "Text overlays, watermarks, or artificial spoken speech",
        ]

        # Facet 10: Previously Used Recipes / Topics
        previously_used_recipes = [r.get("normalized_recipe_name") for r in recipes if r.get("normalized_recipe_name")]

        dna_profile = {
            "channel_profile_id": channel_profile_id,
            "dominant_cuisine": dominant_cuisine,
            "dominant_cooking_method": dominant_method,
            "signature_style": winning_style_dna["signature"],
            "pacing": f"Dynamic {avg_shot_dur}s shot cadence ({avg_cpm} cuts/min) with physical continuity and ASMR sound effects",
            "primary_ingredients_distribution": ing_dist,
            "cuisines_distribution": cuisine_dist,
            "cooking_methods_distribution": method_dist,
            "dish_categories_distribution": cat_dist,
            "total_recipes_analyzed": total_rec,
            "total_shorts_analyzed": total_vid,
            "total_deep_analyzed_shorts": total_analyses,
            # 10 Facets
            "winning_style_dna": winning_style_dna,
            "content_recipe_dna": content_recipe_dna,
            "visual_dna": visual_dna,
            "animation_dna": animation_dna,
            "audio_asmr_dna": audio_asmr_dna,
            "pacing_dna": pacing_dna,
            "story_dna": story_dna,
            "quality_rules": quality_rules,
            "avoid_bad_patterns": avoid_bad_patterns,
            "previously_used_recipes": previously_used_recipes,
        }

        saturation_metrics = {
            "overused_ingredients": overused,
            "saturated_cooking_methods": [k for k, pct in method_dist.items() if pct >= 35.0 and total_rec >= 3],
            "saturation_score": round(len(overused) * 0.25, 2),
            "diversity_ratio": round(len(ing_counter) / (total_rec or 1), 2) if total_rec > 0 else 1.0,
            "deep_analyses_coverage": f"{total_analyses}/10",
        }

        self.db.save_channel_dna(channel_profile_id, dna_profile, saturation_metrics)
        return ChannelDNA(channel_profile_id, dna_profile, saturation_metrics)
