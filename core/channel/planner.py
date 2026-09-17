from __future__ import annotations

import json
import logging
from typing import Any

from core.channel.auto_reference import AutoReferenceEngine
from core.channel.content_gap import ContentGapEngine
from core.channel.dna import ChannelDNAEngine
from core.channel.models import ChannelProfile, NoveltyStatus
from core.channel.novelty import RecipeNoveltyEngine
from core.continuity.validator import validate_plan_continuity
from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.db.memory import MemoryDB
from core.duration import distribute_duration, scene_count, validate_duration

logger = logging.getLogger(__name__)


class ChannelAwarePlanner:
    """Intelligent planner supporting all 7 input modes, especially Mode C (Channel-only)."""

    def __init__(self, db: MemoryDB):
        self.db = db
        self.novelty_engine = RecipeNoveltyEngine(db)
        self.dna_engine = ChannelDNAEngine(db)
        self.gap_engine = ContentGapEngine(db)
        self.auto_ref_engine = AutoReferenceEngine(db)

    def determine_mode(
        self,
        channel_profile: dict[str, Any] | ChannelProfile | None,
        prompt: str | None,
        manual_references: list[str] | dict[str, Any] | None,
    ) -> str:
        has_channel = bool(channel_profile)
        has_prompt = bool(prompt and prompt.strip())
        has_refs = bool(
            manual_references
            and (
                (isinstance(manual_references, list) and len(manual_references) > 0)
                or (isinstance(manual_references, dict) and any(manual_references.values()))
            )
        )

        if has_channel and has_prompt and has_refs:
            return "Mode A (Channel + Prompt + Manual References)"
        if has_channel and has_prompt and not has_refs:
            return "Mode B (Channel + Prompt)"
        if has_channel and not has_prompt and not has_refs:
            return "Mode C (Channel Only)"
        if not has_channel and has_prompt and has_refs:
            return "Mode D (Prompt + Manual References)"
        if not has_channel and has_prompt and not has_refs:
            return "Mode E (Prompt Only)"
        if not has_channel and not has_prompt and has_refs:
            return "Mode F (Manual References Only)"
        return "Mode G (Duration Only)"

    def create_plan(
        self,
        duration: int,
        prompt: str | None = None,
        channel_profile: dict[str, Any] | ChannelProfile | None = None,
        manual_references: dict[str, Any] | list[str] | None = None,
        status_cb=lambda s: None,
    ) -> ProjectPlan:
        duration = validate_duration(duration)

        # 1. Resolve channel profile if not provided but active in DB
        prof_obj: ChannelProfile | None = None
        if channel_profile:
            prof_obj = channel_profile if isinstance(channel_profile, ChannelProfile) else ChannelProfile.from_dict(channel_profile)
        else:
            db_p = self.db.get_channel_profile()
            if db_p:
                prof_obj = ChannelProfile.from_dict(db_p)

        mode = self.determine_mode(prof_obj, prompt, manual_references)
        status_cb(f"Channel Intelligence: Planning Short using {mode}...")

        # 2. Determine concept & recipe title
        recipe_concept: dict[str, Any] = {}
        chosen_title = ""

        if prompt and prompt.strip():
            chosen_title = prompt.strip()
            # Extract structured culinary signals from user prompt
            from core.channel.recipe_extractor import RecipeExtractor
            extractor = RecipeExtractor(self.db)
            extracted = extractor.extract({"title": chosen_title})
            recipe_concept = {
                "recipe_name": chosen_title,
                "normalized_recipe_name": extracted.normalized_recipe_name or chosen_title.lower(),
                "primary_ingredient": extracted.primary_ingredient or "mixed",
                "secondary_ingredients": extracted.secondary_ingredients,
                "cooking_method": extracted.cooking_method or "saute & sizzle",
                "dish_category": extracted.dish_category,
                "cuisine": extracted.cuisine,
            }

            # Quality Check: Reject generic/low-quality single-word or vague inputs
            low_quality_triggers = {"food", "short", "cook", "cooking", "something", "video", "tasty food", "make food", "recipe"}
            if chosen_title.lower().strip() in low_quality_triggers or len(chosen_title.strip().split()) < 2:
                status_cb(f"Channel Intelligence: Low-quality/generic concept '{chosen_title}' detected. Upgrading with channel culinary DNA...")
                recipe_concept = self.gap_engine.pick_novel_concept(prof_obj.id if prof_obj else None)
                chosen_title = recipe_concept.get("recipe_name", "Artisanal Sizzling Garlic Butter Crunch")
        elif prof_obj and prof_obj.id:
            # Mode C: Channel only! Query content gaps & pick novel recipe
            status_cb("Channel Intelligence: Analyzing content gaps and novelty memory...")
            recipe_concept = self.gap_engine.pick_novel_concept(prof_obj.id)
            chosen_title = recipe_concept.get("recipe_name", "Chef Signature Crispy Delight")
        else:
            # Mode F or Mode G
            chosen_title = "Crispy Golden Garlic Potato Bites"
            recipe_concept = {
                "recipe_name": chosen_title,
                "primary_ingredient": "potato",
                "cooking_method": "deep fry",
            }

        # 3. Novelty Engine Check (Hard no-repeat rule against Recipe Memory & Channel DNA)
        novelty_verdict = None
        if prof_obj and prof_obj.id:
            novelty_verdict = self.novelty_engine.evaluate(prof_obj.id, recipe_concept)
            if not novelty_verdict.is_acceptable:
                status_cb(
                    f"Channel Intelligence: Detected duplicate '{chosen_title}' ({novelty_verdict.status.value}) against '{novelty_verdict.matched_recipe}'. "
                    "Regenerating novel concept from content gaps..."
                )
                logger.warning(
                    "Proposed recipe '%s' flagged as %s against channel recipe '%s'. Searching alternative novel concept...",
                    chosen_title,
                    novelty_verdict.status.value,
                    novelty_verdict.matched_recipe,
                )
                recipe_concept = self.gap_engine.pick_novel_concept(prof_obj.id)
                chosen_title = recipe_concept.get("recipe_name", "Original Artisanal Creation")
                novelty_verdict = self.novelty_engine.evaluate(prof_obj.id, recipe_concept)

        # 4. Improvement Signals & Reference Discovery (Protected Content Rule compliant)
        improvement_signals = []
        if prof_obj and prof_obj.id:
            improvement_signals = self.db.get_improvement_signals(prof_obj.id)

        manual_prof_dict = manual_references if isinstance(manual_references, dict) else None
        ref_profile = self.auto_ref_engine.get_reference_profile(
            manual_profile=manual_prof_dict,
            channel_profile_id=prof_obj.id if prof_obj else None,
            topic_hint=chosen_title,
        )
        if improvement_signals:
            ref_profile["improvement_signals"] = [s.get("recommendation", "") for s in improvement_signals[:3]]

        # 5. Build Scenes with physical continuity & ASMR audio timeline enforcing Channel DNA
        plan = self._synthesize_project_plan(
            title=chosen_title,
            duration=duration,
            concept=recipe_concept,
            reference_profile=ref_profile,
            channel_profile=prof_obj,
        )

        # Log checklist
        novelty_str = f"{novelty_verdict.status.value} (Score: {novelty_verdict.score})" if novelty_verdict else "N/A (No active channel)"
        logger.info(
            "\n[Channel Intelligence Checklist]\n"
            "--------------------------------\n"
            "• Channel Profile: %s\n"
            "• Input Mode: %s\n"
            "• Chosen Concept: %s\n"
            "• Novelty Check: %s\n"
            "• Reference Engine: %s\n"
            "• Duration: %d seconds (%d scenes)\n"
            "--------------------------------",
            f"{prof_obj.title} ({prof_obj.handle})" if prof_obj else "None",
            mode,
            chosen_title,
            novelty_str,
            ref_profile.get("source", "manual"),
            plan.duration,
            len(plan.scenes),
        )

        return plan

    def _synthesize_project_plan(
        self,
        title: str,
        duration: int,
        concept: dict[str, Any],
        reference_profile: dict[str, Any],
        channel_profile: ChannelProfile | None = None,
    ) -> ProjectPlan:
        count = scene_count(duration)
        durations = distribute_duration(duration, count)
        scenes: list[ScenePlan] = []
        cursor = 0.0

        primary_ing = concept.get("ingredient") or concept.get("primary_ingredient") or "culinary ingredients"
        method = concept.get("method") or concept.get("cooking_method") or "sizzle"
        flavor = concept.get("flavor") or "savory herb"

        # Extract Channel DNA facets if available
        channel_dna_data: dict[str, Any] = {}
        if channel_profile and channel_profile.id:
            dna_row = self.db.get_channel_dna(channel_profile.id)
            if dna_row:
                channel_dna_data = dna_row.get("dna_profile") or {}
            else:
                cdna = self.dna_engine.generate_dna(channel_profile.id)
                channel_dna_data = cdna.dna_profile

        vis_dna = channel_dna_data.get("visual_dna") or {}
        anim_dna = channel_dna_data.get("animation_dna") or {}
        lighting = vis_dna.get("lighting") or "warm directional macro spotlight with soft rim fill"
        palette = vis_dna.get("palette") or "warm golden amber, rich culinary wood tones"
        anchors = vis_dna.get("consistency_anchors") or [
            f"consistent {lighting}",
            "consistent chef hands in natural culinary technique with neutral sleeves",
            "consistent solid dark cutting board and matte cookware",
            "consistent shallow depth of field with creamy background bokeh",
            "photorealistic 8k vertical 9:16 framing, no text, no watermark",
        ]
        camera_motions = anim_dna.get("camera_motion_profiles") or [
            "macro_push_in",
            "cinematic_drift",
            "dynamic_tilt",
            "reveal_pull_out",
            "parallax_shimmer",
        ]

        for i, span in enumerate(durations, 1):
            end = cursor + span
            beats: list[SceneBeat] = []
            cam_motion = camera_motions[(i - 1) % len(camera_motions)]

            if i == 1:
                actions = [
                    f"immediate vertical macro reveal of fresh {primary_ing}",
                    f"chef hands slice {primary_ing} on solid wooden board with crisp rhythm",
                    "knife contact remains physically continuous on cutting board",
                    f"hold on glistening cut texture of {primary_ing}",
                ]
                scene_type = "Opening Visual Hook & Prep"
                audio_events = [
                    {"type": "sfx", "name": "knife_chop", "timestamp": round(cursor + 0.5, 2), "duration": 1.2},
                    {"type": "ambient", "name": "kitchen_ambience", "timestamp": round(cursor, 2), "duration": round(span, 2)},
                ]
            elif i == count:
                actions = [
                    f"final plated presentation of {title} in {lighting}",
                    "chef garnishes plate with fresh herbs and delicate drizzle",
                    "hand lifts first crispy bite revealing steaming interior texture",
                    "hold on irresistible macro food climax",
                ]
                scene_type = "Climax & Reveal"
                audio_events = [
                    {"type": "sfx", "name": "crisp_bite_crunch", "timestamp": round(cursor + 1.0, 2), "duration": 1.5},
                    {"type": "ambient", "name": "kitchen_ambience", "timestamp": round(cursor, 2), "duration": round(span, 2)},
                ]
            else:
                actions = [
                    f"heat pan and add seasoned {primary_ing}",
                    f"active {method} action creating golden sizzling crust",
                    "seasoning with aromatic spices, smoke and steam rising naturally",
                    "toss pan gently maintaining continuous utensil contact",
                ]
                scene_type = f"Active Culinary Action ({method})"
                audio_events = [
                    {"type": "sfx", "name": "sizzling_pan", "timestamp": round(cursor + 0.3, 2), "duration": 2.0},
                    {"type": "ambient", "name": "kitchen_ambience", "timestamp": round(cursor, 2), "duration": round(span, 2)},
                ]

            for b_idx, act in enumerate(actions):
                bs = cursor + span * b_idx / len(actions)
                be = cursor + span * (b_idx + 1) / len(actions)
                camera = cam_motion if b_idx == 0 else "shallow depth-of-field macro focus"
                beats.append(SceneBeat(round(bs, 3), round(be, 3), act, camera))

            v_prompt = (
                f"Cinematic vertical 9:16 culinary Short scene {i} of {count} for '{title}'; "
                f"{scene_type}; active physical interaction with {primary_ing}; "
                f"{lighting}; {palette}; macro texture focus; "
                f"{', '.join(anchors[:3])}; "
                "continuous object presence without teleportation; no text, no subtitles, no watermark, no dialogue"
            )

            continuity = {
                "objects_must_persist": True,
                "no_teleportation": True,
                "primary_ingredient": primary_ing,
                "scene_type": scene_type,
                "consistency_anchors": anchors,
            }

            scenes.append(ScenePlan(i, round(cursor, 3), round(end, 3), beats, v_prompt, audio_events, continuity))
            cursor = end

        # Attach Channel DNA into style
        style_copy = dict(reference_profile)
        if channel_dna_data:
            style_copy["channel_dna"] = channel_dna_data

        return ProjectPlan(
            duration=duration,
            title=title,
            scenes=scenes,
            style=style_copy,
            character={"type": "chef_hands", "visual_continuity": True},
        )
