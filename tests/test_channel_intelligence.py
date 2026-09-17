from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine

from core.channel.auto_reference import AutoReferenceEngine
from core.channel.content_gap import ContentGapEngine
from core.channel.dna import ChannelDNAEngine
from core.channel.improvement import ImprovementEngine
from core.channel.models import ChannelProfile, NoveltyStatus
from core.channel.novelty import RecipeNoveltyEngine
from core.channel.planner import ChannelAwarePlanner
from core.channel.recipe_extractor import RecipeExtractor, normalize_recipe_name
from core.channel.resolver import ChannelResolver, channel_id_to_uploads_playlist, normalize_handle
from core.channel.sync import ChannelSyncEngine, is_short_video, parse_iso8601_duration
from core.continuity.validator import validate_plan_continuity
from core.db.memory import MemoryDB


@pytest.fixture
def mem_db(tmp_path):
    """Isolated SQLite MemoryDB fixture for channel testing."""
    db_file = tmp_path / "test_channel.db"
    engine = create_engine(f"sqlite:///{db_file.as_posix()}", future=True)
    db = MemoryDB(engine=engine)
    db.initialize()
    return db


# -------------------------------------------------------------
# 1. Handle Normalization & Channel Resolver Tests
# -------------------------------------------------------------

def test_handle_normalization():
    assert normalize_handle("@imaginator_officials") == "@imaginator_officials"
    assert normalize_handle("imaginator_officials") == "@imaginator_officials"
    assert normalize_handle("https://www.youtube.com/@imaginator_officials") == "@imaginator_officials"
    assert normalize_handle("https://youtube.com/channel/UC1234567890abcdefghij") == "UC1234567890abcdefghij"
    assert normalize_handle("") == ""


def test_channel_id_to_uploads_playlist():
    assert channel_id_to_uploads_playlist("UC_x5XG1OV2P6uZZ5FSM9Ttw") == "UU_x5XG1OV2P6uZZ5FSM9Ttw"
    assert channel_id_to_uploads_playlist("UCabcdef1234567890") == "UUabcdef1234567890"


def test_channel_resolver_fallback():
    resolver = ChannelResolver(api_key=None)
    profile = resolver.resolve("@imaginator_officials")
    assert profile.handle == "@imaginator_officials"
    assert profile.channel_id.startswith("UC")
    assert profile.uploads_playlist_id.startswith("UU")
    assert "Imaginator" in profile.title


def test_channel_resolver_api_mock():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "items": [
            {
                "id": "UCtest1234567890123456",
                "snippet": {
                    "title": "Chef Test Channel",
                    "description": "Culinary shorts test",
                    "customUrl": "@cheftest",
                },
                "contentDetails": {
                    "relatedPlaylists": {
                        "uploads": "UUtest1234567890123456"
                    }
                },
                "statistics": {
                    "subscriberCount": "50000",
                    "videoCount": "120"
                }
            }
        ]
    }

    with patch("requests.get", return_value=mock_resp):
        resolver = ChannelResolver(api_key="fake_key")
        profile = resolver.resolve("@cheftest")
        assert profile.channel_id == "UCtest1234567890123456"
        assert profile.uploads_playlist_id == "UUtest1234567890123456"
        assert profile.title == "Chef Test Channel"
        assert profile.subscriber_count == 50000


# -------------------------------------------------------------
# 2. Database Channel Persistence & CRUD
# -------------------------------------------------------------

def test_database_channel_profile_crud(mem_db):
    prof_data = {
        "handle": "@imaginator_officials",
        "channel_id": "UC_test_chan_001",
        "uploads_playlist_id": "UU_test_chan_001",
        "title": "Imaginator Official",
        "subscriber_count": 10000,
        "video_count": 45,
    }
    saved = mem_db.save_channel_profile(prof_data)
    assert saved["id"] is not None
    assert saved["handle"] == "@imaginator_officials"

    retrieved = mem_db.get_channel_profile(handle="@imaginator_officials")
    assert retrieved is not None
    assert retrieved["title"] == "Imaginator Official"

    # Also retrievable without leading @
    retrieved2 = mem_db.get_channel_profile(handle="imaginator_officials")
    assert retrieved2 is not None
    assert retrieved2["id"] == saved["id"]

    # Update settings
    mem_db.update_channel_settings(saved["id"], prevent_recipe_repeats=False, video_count=50)
    updated = mem_db.get_channel_profile(profile_id=saved["id"])
    assert updated["prevent_recipe_repeats"] == 0
    assert updated["video_count"] == 50


# -------------------------------------------------------------
# 3. Video Sync & Shorts Detection
# -------------------------------------------------------------

def test_shorts_detection_heuristics():
    assert is_short_video("Crispy Chicken Bites #Shorts", "Quick recipe", 45) is True
    assert is_short_video("Long Documentary on Food", "Full video", 1200) is False
    assert is_short_video("Pasta Recipe", "No tag", 160) is True
    assert is_short_video("Cooking Video", "Check it out", 0, video_url="https://youtube.com/shorts/abc1234") is True


def test_parse_iso8601_duration():
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT1M15S") == 75
    assert parse_iso8601_duration("PT2H3M4S") == 7384
    assert parse_iso8601_duration("INVALID") == 0


def test_channel_video_sync_and_deduplication(mem_db):
    prof = mem_db.save_channel_profile({
        "handle": "@culinary_star",
        "channel_id": "UC_star_01",
        "uploads_playlist_id": "UU_star_01",
        "title": "Culinary Star",
    })
    cid = prof["id"]

    videos_batch_1 = [
        {"youtube_video_id": "vid001", "title": "Crispy Butter Chicken #Shorts", "duration_seconds": 55, "is_short": True},
        {"youtube_video_id": "vid002", "title": "Garlic Naan Bread #Shorts", "duration_seconds": 40, "is_short": True},
    ]

    added_1 = mem_db.save_channel_videos(cid, videos_batch_1)
    assert added_1 == 2

    videos = mem_db.get_channel_videos(cid)
    assert len(videos) == 2

    # Sync batch 2 with duplicate vid001 (should update, not duplicate)
    videos_batch_2 = [
        {"youtube_video_id": "vid001", "title": "Crispy Butter Chicken (Updated) #Shorts", "duration_seconds": 55, "is_short": True},
        {"youtube_video_id": "vid003", "title": "Paneer Tikka Skewers #Shorts", "duration_seconds": 50, "is_short": True},
    ]

    added_2 = mem_db.save_channel_videos(cid, videos_batch_2)
    assert added_2 == 1  # vid003 is new, vid001 is updated

    all_videos = mem_db.get_channel_videos(cid)
    assert len(all_videos) == 3  # exactly 3 unique videos

    stats = mem_db.get_channel_stats(cid)
    assert stats["video_count"] == 3
    assert stats["shorts_count"] == 3


# -------------------------------------------------------------
# 4. Recipe Extraction & Normalization
# -------------------------------------------------------------

def test_recipe_normalization():
    assert normalize_recipe_name("How to Make Crispy Garlic Butter Chicken! #Shorts") == "garlic butter chicken"
    assert normalize_recipe_name("Tasty Street Food Paneer Tikka Recipe") == "paneer tikka"
    assert normalize_recipe_name("Authentic Italian Spaghetti Carbonara (Easy)") == "italian spaghetti carbonara"


def test_recipe_extraction(mem_db):
    extractor = RecipeExtractor(mem_db)
    sample_video = {
        "id": 1,
        "title": "Crispy Garlic Butter Chicken | Easy Dinner #Shorts",
        "description": "Making juicy chicken breast with minced garlic, melted butter and fresh parsley",
    }
    record = extractor.extract(sample_video)
    assert record.primary_ingredient == "chicken"
    assert "garlic" in record.secondary_ingredients or "butter" in record.secondary_ingredients
    assert record.normalized_recipe_name == "garlic butter chicken"
    assert "ingredient_signature" in record.signatures
    assert "novelty_signature" in record.signatures


# -------------------------------------------------------------
# 5. Recipe Novelty Engine (Hard No-Repeat Rules)
# -------------------------------------------------------------

def test_recipe_novelty_exact_duplicate(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@test_chef", "channel_id": "UC_chef"})
    cid = prof["id"]

    # Save existing recipe
    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Crispy Butter Chicken",
        "normalized_recipe_name": "butter chicken",
        "primary_ingredient": "chicken",
        "secondary_ingredients": ["butter", "cream", "garlic"],
        "cooking_method": "simmer",
    })

    novelty_engine = RecipeNoveltyEngine(mem_db)

    # 1. Exact duplicate candidate
    exact_candidate = "Butter Chicken"
    verdict1 = novelty_engine.evaluate(cid, exact_candidate)
    assert verdict1.status == NoveltyStatus.DUPLICATE
    assert verdict1.is_acceptable is False
    assert "Exact duplicate" in verdict1.reasons[0]


def test_recipe_novelty_ingredient_and_semantic_overlap(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@test_chef2", "channel_id": "UC_chef2"})
    cid = prof["id"]

    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Crispy Garlic Butter Chicken",
        "normalized_recipe_name": "garlic butter chicken",
        "primary_ingredient": "chicken",
        "secondary_ingredients": ["garlic", "butter"],
        "cooking_method": "fry",
    })

    novelty_engine = RecipeNoveltyEngine(mem_db)

    # Near duplicate candidate with identical primary ingredient, high secondary overlap, and same cooking method
    near_dup = {
        "recipe_name": "Butter Garlic Fried Chicken",
        "normalized_recipe_name": "butter garlic fried chicken",
        "primary_ingredient": "chicken",
        "secondary_ingredients": ["butter", "garlic"],
        "cooking_method": "fry",
    }
    verdict = novelty_engine.evaluate(cid, near_dup)
    assert verdict.is_acceptable is False
    assert verdict.status in (NoveltyStatus.NEAR_DUPLICATE, NoveltyStatus.DUPLICATE)


def test_recipe_novelty_novel_concept_accepted(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@test_chef3", "channel_id": "UC_chef3"})
    cid = prof["id"]

    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Butter Chicken",
        "normalized_recipe_name": "butter chicken",
        "primary_ingredient": "chicken",
        "cooking_method": "simmer",
    })

    novelty_engine = RecipeNoveltyEngine(mem_db)

    # Completely different concept: Chocolate Lava Cake or Crispy Potato Bites
    novel_candidate = {
        "recipe_name": "Crispy Golden Garlic Potato Bites",
        "normalized_recipe_name": "golden garlic potato bites",
        "primary_ingredient": "potato",
        "secondary_ingredients": ["garlic", "herb"],
        "cooking_method": "deep fry",
    }
    verdict = novelty_engine.evaluate(cid, novel_candidate)
    assert verdict.is_acceptable is True
    assert verdict.status == NoveltyStatus.NOVEL
    assert verdict.score >= 0.70


# -------------------------------------------------------------
# 6. Channel DNA & Saturation Engine
# -------------------------------------------------------------

def test_channel_dna_and_saturation(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@dna_test", "channel_id": "UC_dna"})
    cid = prof["id"]

    # Add 4 recipes, 3 of which use chicken
    for i, title in enumerate(["Butter Chicken", "Chicken Tikka", "Chicken Masala", "Paneer Bhurji"]):
        mem_db.save_recipe_record({
            "channel_profile_id": cid,
            "recipe_name": title,
            "normalized_recipe_name": title.lower(),
            "primary_ingredient": "chicken" if i < 3 else "paneer",
            "cuisine": "Indian",
            "cooking_method": "simmer",
            "dish_category": "curry / gravy",
        })

    dna_engine = ChannelDNAEngine(mem_db)
    dna = dna_engine.generate_dna(cid)

    assert dna.dna_profile["dominant_cuisine"] == "Indian"
    assert dna.dna_profile["total_recipes_analyzed"] == 4
    # Chicken is 75%, so it should be flagged as overused
    assert "chicken" in dna.saturation_metrics["overused_ingredients"]


# -------------------------------------------------------------
# 7. Content Gap Engine
# -------------------------------------------------------------

def test_content_gap_detection(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@gap_test", "channel_id": "UC_gap"})
    cid = prof["id"]

    # All recipes are chicken
    for title in ["Butter Chicken", "Chicken Tikka", "Chicken Masala"]:
        mem_db.save_recipe_record({
            "channel_profile_id": cid,
            "recipe_name": title,
            "normalized_recipe_name": title.lower(),
            "primary_ingredient": "chicken",
            "cuisine": "Indian",
            "cooking_method": "simmer",
            "dish_category": "curry / gravy",
        })

    gap_engine = ContentGapEngine(mem_db)
    gaps = gap_engine.find_content_gaps(cid)

    # Chicken is overused; non-chicken ingredients should be in underused list
    assert "chicken" in gaps["overused_ingredients"]
    assert "potato" in gaps["underused_ingredients"] or "paneer" in gaps["underused_ingredients"]

    # Novel concept proposal should NOT use chicken
    concept = gap_engine.pick_novel_concept(cid)
    assert concept["ingredient"] != "chicken"


# -------------------------------------------------------------
# 8. Improvement Engine
# -------------------------------------------------------------

def test_improvement_engine_signals(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@imp_test", "channel_id": "UC_imp"})
    cid = prof["id"]

    dna_engine = ChannelDNAEngine(mem_db)
    dna_engine.generate_dna(cid)

    imp_engine = ImprovementEngine(mem_db)
    signals = imp_engine.generate_recommendations(cid)

    assert len(signals) >= 2
    areas = [s.area for s in signals]
    assert "audio_asmr" in areas
    assert "visual_hook" in areas

    saved_signals = mem_db.get_improvement_signals(cid)
    assert len(saved_signals) >= 2


# -------------------------------------------------------------
# 9. Auto Reference Discovery & Protected Content Rule
# -------------------------------------------------------------

def test_auto_reference_protected_content_rule(mem_db):
    prof = mem_db.save_channel_profile({"handle": "@ref_test", "channel_id": "UC_ref"})
    cid = prof["id"]

    ref_engine = AutoReferenceEngine(mem_db)
    auto_profile = ref_engine.get_reference_profile(manual_profile=None, channel_profile_id=cid)

    assert auto_profile["source"] == "auto_channel_intelligence"
    assert "Protected Content Rule verified" in auto_profile["compliance"]
    assert "visual_style" in auto_profile
    assert "audio_dna" in auto_profile
    assert auto_profile["audio_dna"]["voice"] == "no spoken dialogue; non-verbal natural human culinary appreciation sounds only"


def test_manual_reference_takes_priority(mem_db):
    ref_engine = AutoReferenceEngine(mem_db)
    manual_data = {
        "source": "manual_user_upload",
        "style": "custom cinematic neon",
    }
    result = ref_engine.get_reference_profile(manual_profile=manual_data, channel_profile_id=1)
    assert result == manual_data
    assert result["source"] == "manual_user_upload"


# -------------------------------------------------------------
# 10. ChannelAwarePlanner & All 7 Modes
# -------------------------------------------------------------

def test_planner_mode_determination(mem_db):
    planner = ChannelAwarePlanner(mem_db)
    prof = ChannelProfile(id=1, handle="@test")

    assert "Mode A" in planner.determine_mode(prof, "Make food", {"profile": "data"})
    assert "Mode B" in planner.determine_mode(prof, "Make food", None)
    assert "Mode C" in planner.determine_mode(prof, None, None)
    assert "Mode D" in planner.determine_mode(None, "Make food", {"profile": "data"})
    assert "Mode E" in planner.determine_mode(None, "Make food", None)
    assert "Mode F" in planner.determine_mode(None, None, {"profile": "data"})
    assert "Mode G" in planner.determine_mode(None, None, None)


def test_planner_mode_c_channel_only(mem_db):
    """Mode C: User provides NO prompt and NO references; channel intelligence creates plan."""
    prof = mem_db.save_channel_profile({
        "handle": "@imaginator_officials",
        "channel_id": "UC_imaginator",
        "title": "Imaginator Officials",
    })
    cid = prof["id"]

    # Pre-populate some existing recipes
    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Butter Chicken",
        "normalized_recipe_name": "butter chicken",
        "primary_ingredient": "chicken",
    })

    planner = ChannelAwarePlanner(mem_db)

    # Call with duration=60, prompt=None, manual_references=None
    plan = planner.create_plan(
        duration=60,
        prompt=None,
        channel_profile=prof,
        manual_references=None,
    )

    assert plan.duration == 60
    assert len(plan.scenes) > 0
    # Plan continuity rules must pass
    continuity_errors = validate_plan_continuity(plan)
    assert len(continuity_errors) == 0
    # The novel concept selected must NOT duplicate existing "butter chicken"
    assert plan.title.lower() != "butter chicken"


def test_planner_mode_g_duration_only(mem_db):
    """Mode G: No channel, no prompt, no manual references."""
    planner = ChannelAwarePlanner(mem_db)
    plan = planner.create_plan(duration=30, prompt=None, channel_profile=None, manual_references=None)
    assert plan.duration == 30
    assert len(plan.scenes) > 0
    assert validate_plan_continuity(plan) == []


def test_user_prompt_duplicate_rejection_and_regeneration(mem_db):
    """User provides a duplicate prompt; system detects duplicate and regenerates novel concept."""
    prof = mem_db.save_channel_profile({
        "handle": "@imaginator_officials",
        "channel_id": "UC_dup_test",
        "prevent_recipe_repeats": True,
    })
    cid = prof["id"]
    mem_db.save_recipe_record({
        "channel_profile_id": cid,
        "recipe_name": "Crispy French Fries",
        "normalized_recipe_name": "french fries",
        "primary_ingredient": "potato",
        "cooking_method": "deep fry",
    })

    planner = ChannelAwarePlanner(mem_db)
    statuses = []
    plan = planner.create_plan(
        duration=30,
        prompt="French Fries",
        channel_profile=prof,
        status_cb=lambda s: statuses.append(s),
    )
    assert any("Detected duplicate" in s for s in statuses)
    assert plan.title.lower() != "french fries"
    assert validate_plan_continuity(plan) == []


def test_final_acceptance_channel_only_pipeline(monkeypatch, tmp_path):
    """
    Final acceptance test:
    @channel_handle + NO prompt + NO manual reference
    -> channel analysis -> recipe memory -> duplicate check -> content gaps
    -> auto references -> improvement analysis -> new plan -> existing generation pipeline.
    """
    import io, shutil
    from PIL import Image
    import app.pipeline as pipeline

    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg required for end-to-end acceptance test")

    projects_dir = tmp_path / "projects"
    output_dir = tmp_path / "output"
    data_dir = tmp_path / "data"
    projects_dir.mkdir()
    output_dir.mkdir()
    data_dir.mkdir()

    sqlite_url = f"sqlite:///{(data_dir / 'memory.db').as_posix()}"
    monkeypatch.setenv("YT_AUTO_DB_URL", sqlite_url)
    monkeypatch.setattr(pipeline, "PROJECTS", projects_dir)
    monkeypatch.setattr(pipeline, "OUTPUT", output_dir)
    monkeypatch.setattr(pipeline, "load_config", lambda: {"reference_profile": {}})

    # Mock HF image generator
    def _create_img():
        img = Image.new("RGB", (1080, 1920), color=(80, 120, 160))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()

    monkeypatch.setattr(pipeline, "hf_text_to_image", lambda prompt: _create_img())

    # 1. Permanent channel configuration
    db = MemoryDB(sqlite_url)
    db.initialize()
    resolver = ChannelResolver()
    channel_profile = resolver.resolve("@imaginator_officials")
    saved_prof = db.save_channel_profile(channel_profile.to_dict())
    cid = saved_prof["id"]

    # 2. Existing channel videos & recipe memory (saturation: chicken)
    existing_videos = [
        {"youtube_video_id": "v1", "title": "Butter Chicken Curry #Shorts", "duration_seconds": 45, "is_short": True},
        {"youtube_video_id": "v2", "title": "Chicken Tikka Skewers #Shorts", "duration_seconds": 50, "is_short": True},
    ]
    db.save_channel_videos(cid, existing_videos)

    extractor = RecipeExtractor(db)
    for v in existing_videos:
        extractor.extract_and_save(cid, v)

    # Pre-existing recipes check
    pre_recipes = db.get_recipes(cid)
    assert len(pre_recipes) == 2

    # 3. Compute Channel DNA and Improvement Signals
    dna_engine = ChannelDNAEngine(db)
    dna_engine.generate_dna(cid)
    imp_engine = ImprovementEngine(db)
    imp_engine.generate_recommendations(cid)

    # 4. Run pipeline with NO prompt ("") and NO manual references (config has empty reference_profile)
    status_updates = []
    final_video = pipeline.run_project(
        instruction="",
        duration=1,
        status_cb=lambda s: status_updates.append(s),
    )

    # 5. Verify results
    assert final_video.exists()
    assert final_video.is_file()
    assert final_video.suffix == ".mp4"
    assert final_video.stat().st_size > 1024

    # Verify Channel Intelligence steps executed
    assert any("Mode C (Channel Only)" in s for s in status_updates)
    assert any("Analyzing content gaps" in s for s in status_updates)
    assert any("QC PASS" in s for s in status_updates)

    # Verify that the newly generated recipe is registered in Recipe Memory
    post_recipes = db.get_recipes(cid)
    assert len(post_recipes) == 3  # 2 existing + 1 newly registered!
    new_recipe = post_recipes[0]  # sorted by created_at DESC
    assert new_recipe["recipe_name"] != ""
    assert new_recipe["recipe_name"].lower() not in ["butter chicken", "chicken tikka"]
