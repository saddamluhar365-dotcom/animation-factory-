from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

from core.channel.deep_analyzer import ChannelDeepAnalyzer
from core.channel.dna import ChannelDNAEngine
from core.channel.models import ChannelProfile, NoveltyStatus
from core.channel.planner import ChannelAwarePlanner
from core.db.memory import MemoryDB


@pytest.fixture
def mem_db(tmp_path):
    """Isolated SQLite MemoryDB fixture."""
    db_file = tmp_path / "test_deep_channel.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    db = MemoryDB(engine=engine)
    db.initialize()
    return db


def test_db_video_analysis_persistence(mem_db):
    """Test saving and retrieving per-video deep analyses in database."""
    prof = mem_db.save_channel_profile({
        "handle": "@culinary_dna_test",
        "channel_id": "UC_test_dna_01",
        "title": "Culinary DNA Test",
    })
    cid = prof["id"]

    sample_analysis = {
        "youtube_video_id": "vid_101",
        "resolution": [1080, 1920],
        "fps": 60.0,
        "duration_seconds": 35.0,
        "aspect_ratio": "9:16",
        "visual_style": {
            "warmth_ratio": 1.48,
            "lighting": "warm directional macro spotlight",
        },
        "pacing": {
            "avg_shot_duration": 2.1,
            "cuts_per_minute": 28.5,
        },
        "asmr_audio_profile": {
            "target_lufs": -14.0,
            "foley_layers": ["ambient_presence", "crisp_sizzle", "wood_chop"],
        },
        "consistency_anchors": [
            "consistent warm macro lighting",
            "consistent chef hands",
        ],
    }

    # Save analysis
    row_id = mem_db.save_video_analysis(cid, None, "vid_101", sample_analysis)
    assert row_id is not None

    # Retrieve analysis
    analyses = mem_db.get_video_analyses(cid)
    assert len(analyses) == 1
    assert analyses[0]["youtube_video_id"] == "vid_101"
    retrieved_data = analyses[0]["analysis"]
    assert retrieved_data["fps"] == 60.0
    assert retrieved_data["visual_style"]["warmth_ratio"] == 1.48

    # Non-destructive upsert test
    updated_analysis = dict(sample_analysis)
    updated_analysis["fps"] = 60.0
    updated_analysis["visual_style"]["warmth_ratio"] = 1.55
    mem_db.save_video_analysis(cid, None, "vid_101", updated_analysis)

    analyses_after = mem_db.get_video_analyses(cid)
    assert len(analyses_after) == 1
    assert analyses_after[0]["analysis"]["visual_style"]["warmth_ratio"] == 1.55

    # Check stats update
    stats = mem_db.get_channel_stats(cid)
    assert stats["analyzed_shorts_count"] == 1


def test_deep_analyzer_13_dimensions_extraction(mem_db, tmp_path):
    """Test that ChannelDeepAnalyzer produces all 13 production dimensions."""
    analyzer = ChannelDeepAnalyzer(mem_db, cache_dir=tmp_path / "cache")
    video_sample = {
        "youtube_video_id": "vid_sample_01",
        "title": "Crispy Garlic Butter Steak Bites #Shorts",
        "description": "Making tender juicy garlic butter steak bites in a cast iron skillet with thyme",
        "duration_seconds": 42,
    }

    analysis = analyzer.decode_and_analyze_video(video_sample, work_dir=tmp_path / "work")

    # Verify all 13 required dimensions:
    # 1. Technical specs
    assert analysis["resolution"] == [1080, 1920]
    assert analysis["fps"] == 60.0
    assert analysis["aspect_ratio"] == "9:16"
    assert analysis["duration_seconds"] == 42.0

    # 2. Scene/shot structure
    assert "scene_structure" in analysis
    assert analysis["scene_structure"]["hook_scene_duration"] <= 2.5

    # 3. Pacing
    assert "pacing" in analysis
    assert 1.5 <= analysis["pacing"]["avg_shot_duration"] <= 4.0
    assert analysis["pacing"]["cadence"] == "fast_paced_high_retention"

    # 4. Visual style & lighting
    assert "visual_style" in analysis
    assert analysis["visual_style"]["warmth_ratio"] >= 1.0
    assert "macro" in analysis["visual_style"]["lighting"]

    # 5. Character & environment consistency anchors
    assert "consistency_anchors" in analysis
    assert len(analysis["consistency_anchors"]) >= 4

    # 6. Camera movement & framing
    assert "camera_movement" in analysis
    assert analysis["camera_movement"]["easing"] == "cubic_ease_in_out"
    assert "macro_push_in" in analysis["camera_movement"]["preferred_motions"]

    # 7. Animation motion quality
    assert "animation_motion_quality" in analysis
    assert analysis["animation_motion_quality"]["smoothness_score"] >= 0.9

    # 8. Story structure
    assert "story_structure" in analysis
    assert analysis["story_structure"]["has_payoff"] is True

    # 9. Recipe content patterns
    assert "recipe_content_patterns" in analysis
    assert analysis["recipe_content_patterns"]["primary_ingredient"] in ("steak", "garlic")
    assert "garlic" in analysis["recipe_content_patterns"]["secondary_ingredients"] or "butter" in analysis["recipe_content_patterns"]["secondary_ingredients"] or "steak" in analysis["recipe_content_patterns"]["secondary_ingredients"]

    # 10. ASMR audio profile
    assert "asmr_audio_profile" in analysis
    assert analysis["asmr_audio_profile"]["target_lufs"] == -14.0
    assert "crisp_sizzle" in analysis["asmr_audio_profile"]["foley_layers"]

    # 11. SFX timing & music patterns
    assert "sfx_music_patterns" in analysis
    assert analysis["sfx_music_patterns"]["action_synced_sfx"] is True

    # 12. Transitions
    assert "transitions" in analysis
    assert "motion_cut" in analysis["transitions"]["styles"]

    # 13. Repeated patterns & weak patterns
    assert len(analysis["successful_characteristics"]) >= 2
    assert len(analysis["weak_patterns_identified"]) >= 2


def test_analyze_latest_10_shorts_end_to_end(mem_db, tmp_path):
    """Test analyzing latest 10 Shorts end-to-end and saving 10-facet Channel DNA."""
    prof = mem_db.save_channel_profile({
        "handle": "@artisan_kitchen",
        "channel_id": "UC_artisan",
        "title": "Artisan Kitchen",
    })
    cid = prof["id"]

    # Pre-populate 10 distinct Shorts in database
    shorts_batch = []
    dishes = [
        ("Crispy Honey Garlic Chicken", "chicken", "fry"),
        ("Sizzling Butter Garlic Prawns", "shrimp", "saute"),
        ("Golden Crispy Potato Wedges", "potato", "bake"),
        ("Spicy Paneer Tikka Skewers", "paneer", "grill"),
        ("Crunchy Tempura Green Beans", "vegetables", "fry"),
        ("Juicy Lamb Smash Burgers", "lamb", "grill"),
        ("Cheesy Garlic Toast Sticks", "bread", "toast"),
        ("Caramelized Salmon Glaze", "salmon", "pan sear"),
        ("Smoky BBQ Rib Bites", "pork", "smoke"),
        ("Crispy Mushroom Popcorn", "mushroom", "fry"),
    ]

    for i, (title, ing, method) in enumerate(dishes, 1):
        shorts_batch.append({
            "youtube_video_id": f"short_{i:03d}",
            "title": f"{title} #Shorts",
            "description": f"How to make {title} with delicious seasonings",
            "duration_seconds": 30 + i,
            "is_short": True,
            "video_url": f"https://www.youtube.com/watch?v=short_{i:03d}",
        })

    added = mem_db.save_channel_videos(cid, shorts_batch)
    assert added == 10

    analyzer = ChannelDeepAnalyzer(mem_db, cache_dir=tmp_path / "cache")
    result = analyzer.analyze_latest_shorts(cid, max_videos=10)

    assert result["status"] == "success"
    assert result["analyzed_count"] == 10

    # Verify per-video analyses saved in DB
    analyses = mem_db.get_video_analyses(cid, limit=20)
    assert len(analyses) == 10

    # Verify recipe_memory is populated
    recipes = mem_db.get_recipes(cid)
    assert len(recipes) == 10

    # Verify aggregate Channel DNA in DB with all 10 facets
    saved_dna = mem_db.get_channel_dna(cid)
    assert saved_dna is not None
    dna_prof = saved_dna["dna_profile"]

    # Check 10 Facets
    assert "winning_style_dna" in dna_prof
    assert "content_recipe_dna" in dna_prof
    assert "visual_dna" in dna_prof
    assert "animation_dna" in dna_prof
    assert "audio_asmr_dna" in dna_prof
    assert "pacing_dna" in dna_prof
    assert "story_dna" in dna_prof
    assert "quality_rules" in dna_prof
    assert "avoid_bad_patterns" in dna_prof
    assert "previously_used_recipes" in dna_prof

    assert dna_prof["animation_dna"]["target_fps"] == 60.0
    assert len(dna_prof["previously_used_recipes"]) == 10
    assert len(dna_prof["quality_rules"]) >= 5


def test_non_destructive_safety_on_analysis_failure(mem_db, tmp_path):
    """Test that individual video failure does not delete or corrupt existing Channel DNA."""
    prof = mem_db.save_channel_profile({
        "handle": "@safe_channel",
        "channel_id": "UC_safe",
        "title": "Safe Channel",
    })
    cid = prof["id"]

    # Pre-existing analysis and recipe
    mem_db.save_video_analysis(cid, None, "vid_safe_pre", {
        "youtube_video_id": "vid_safe_pre",
        "title": "Pre-existing Analysis",
        "visual_style": {"warmth_ratio": 1.45},
    })
    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Garlic Butter Steak",
        "normalized_recipe_name": "garlic butter steak",
        "primary_ingredient": "steak",
    })

    dna_engine = ChannelDNAEngine(mem_db)
    orig_dna = dna_engine.generate_dna(cid)
    assert orig_dna.dna_profile["total_recipes_analyzed"] == 1

    analyzer = ChannelDeepAnalyzer(mem_db, cache_dir=tmp_path / "cache")

    # Mock decode_and_analyze_video to raise an exception
    with patch.object(analyzer, "decode_and_analyze_video", side_effect=RuntimeError("Simulated download block")):
        # Add a new video that will fail
        mem_db.save_channel_videos(cid, [{
            "youtube_video_id": "vid_safe_fail",
            "title": "Failing Video #Shorts",
            "duration_seconds": 35,
            "is_short": True,
        }])
        res = analyzer.analyze_latest_shorts(cid, max_videos=10)
        assert res["status"] == "success"

    # Pre-existing analysis MUST still exist
    all_analyses = mem_db.get_video_analyses(cid)
    assert any(a["youtube_video_id"] == "vid_safe_pre" for a in all_analyses)

    # Channel DNA MUST NOT be empty or deleted
    current_dna = mem_db.get_channel_dna(cid)
    assert current_dna is not None
    assert current_dna["dna_profile"]["total_recipes_analyzed"] >= 1


def test_generation_enforces_channel_dna_and_quality(mem_db):
    """Test that ChannelAwarePlanner enforces Channel DNA into ProjectPlan."""
    prof = mem_db.save_channel_profile({
        "handle": "@chef_artisan",
        "channel_id": "UC_artisan_02",
        "title": "Chef Artisan",
    })
    cid = prof["id"]

    # Pre-seed deep analysis & Channel DNA
    mem_db.save_video_analysis(cid, None, "v1", {
        "visual_style": {
            "warmth_ratio": 1.5,
            "lighting": "warm directional macro spotlight, rim lighting",
            "palette": "warm golden amber, rich wood tones",
        },
        "pacing": {"avg_shot_duration": 2.2, "cuts_per_minute": 27.0},
        "camera_movement": {
            "target_fps": 60.0,
            "easing": "cubic_ease_in_out",
            "preferred_motions": ["macro_push_in", "cinematic_drift"],
        },
        "asmr_audio_profile": {
            "foley_layers": ["ambient_presence", "crisp_sizzle", "wood_chop"],
        },
    })
    dna_engine = ChannelDNAEngine(mem_db)
    dna_engine.generate_dna(cid)

    planner = ChannelAwarePlanner(mem_db)
    plan = planner.create_plan(
        duration=30,
        prompt="Crispy Golden Garlic Potato Wedges",
        channel_profile=prof,
    )

    assert plan.duration == 30
    assert len(plan.scenes) > 0

    # Verify Channel DNA enforcement
    assert "channel_dna" in plan.style
    chan_dna = plan.style["channel_dna"]
    assert chan_dna["animation_dna"]["target_fps"] == 60.0

    # Verify that scene visual prompts include macro lighting and consistency anchors
    for scene in plan.scenes:
        assert "macro" in scene.visual_prompt.lower()
        assert "warm" in scene.visual_prompt.lower()
        # Verify non-linear camera profile in beats
        assert len(scene.beats) > 0
        first_beat_cam = scene.beats[0].camera
        assert any(p in first_beat_cam for p in ["macro_push_in", "cinematic_drift", "dynamic_tilt", "reveal_pull_out", "parallax_shimmer"])


def test_generation_rejects_and_regenerates_duplicate_concept(mem_db):
    """Test that planner rejects duplicate recipe and regenerates novel concept."""
    prof = mem_db.save_channel_profile({
        "handle": "@dup_check_channel",
        "channel_id": "UC_dup_01",
        "title": "Dup Check Channel",
    })
    cid = prof["id"]

    # Pre-record recipe in Recipe Memory
    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Crispy Garlic Butter Chicken",
        "normalized_recipe_name": "garlic butter chicken",
        "primary_ingredient": "chicken",
        "cooking_method": "fry",
    })

    dna_engine = ChannelDNAEngine(mem_db)
    dna_engine.generate_dna(cid)

    planner = ChannelAwarePlanner(mem_db)

    status_logs = []
    # User attempts duplicate recipe
    plan = planner.create_plan(
        duration=30,
        prompt="Garlic Butter Chicken",
        channel_profile=prof,
        status_cb=lambda msg: status_logs.append(msg),
    )

    # Must log detection of duplicate and regeneration
    assert any("duplicate" in msg.lower() for msg in status_logs)
    # The final plan title must NOT be the duplicate "Garlic Butter Chicken"
    assert plan.title != "Garlic Butter Chicken"
    assert "chicken" not in plan.title.lower() or "garlic butter chicken" not in plan.title.lower()


def test_generation_rejects_generic_low_quality_concept(mem_db):
    """Test that planner upgrades generic/low-quality single word prompts."""
    prof = mem_db.save_channel_profile({
        "handle": "@quality_check_channel",
        "channel_id": "UC_qual_01",
        "title": "Quality Check Channel",
    })
    cid = prof["id"]

    dna_engine = ChannelDNAEngine(mem_db)
    dna_engine.generate_dna(cid)

    planner = ChannelAwarePlanner(mem_db)
    status_logs = []

    # Single word generic input
    plan = planner.create_plan(
        duration=30,
        prompt="food",
        channel_profile=prof,
        status_cb=lambda msg: status_logs.append(msg),
    )

    assert any("generic" in msg.lower() or "low-quality" in msg.lower() for msg in status_logs)
    assert plan.title != "food"
    assert len(plan.title.split()) >= 3


def test_pipeline_enforces_channel_handle_requirement(mem_db):
    """Test that pipeline raises clear error if prompt is empty and no handle configured."""
    from app.pipeline import run_project

    # With empty DB (no channel profile) and empty instruction
    with patch("app.pipeline.MemoryDB", return_value=mem_db):
        with pytest.raises(RuntimeError) as exc_info:
            run_project(instruction="", duration=30)
        assert "channel handle is required" in str(exc_info.value).lower()
