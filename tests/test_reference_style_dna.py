from __future__ import annotations
import json
from pathlib import Path
import pytest
from core.reference.analyzer import ReferenceAnalyzer
from core.reference.synthesis import build_master_style


def test_reference_analyzer_extracts_style_dna(tmp_path: Path):
    analyzer = ReferenceAnalyzer()
    ref = Path("assets/references/videoplayback.mp4")
    if not ref.exists():
        pytest.skip("videoplayback.mp4 not present in assets/references")

    profile = analyzer.analyze(ref, tmp_path / "work")
    assert "style_dna" in profile
    dna = profile["style_dna"]

    # Target high-FPS: 60 fps
    assert dna["fps"] == 60
    assert dna["aspect_ratio"] == "9:16"
    assert "visual_style" in dna
    assert "warmth_ratio" in dna["visual_style"]
    assert "palette" in dna["visual_style"]
    assert "lighting" in dna["visual_style"]

    # Camera dynamics
    assert "camera_dynamics" in dna
    assert dna["camera_dynamics"]["target_fps"] == 60
    assert "macro_push_in" in dna["camera_dynamics"]["preferred_motions"]

    # Pacing
    assert "pacing" in dna
    assert dna["pacing"]["avg_shot_duration"] > 0
    assert dna["pacing"]["cadence"] in ("fast_paced_high_retention", "dynamic_standard", "deliberate_atmospheric")

    # Audio & ASMR profile
    assert "audio_profile" in dna
    assert "asmr_layers" in dna["audio_profile"]
    assert "crisp_sizzle" in dna["audio_profile"]["asmr_layers"]

    # Visual consistency anchors
    assert "consistency_anchors" in dna
    assert len(dna["consistency_anchors"]) >= 3

    # Protected content rule
    assert dna["protected_content_compliant"] is True


def test_build_master_style_combines_dna():
    profiles = [
        {
            "schema_version": 2,
            "source_hash": "hash1",
            "technical": {"width": 1080, "height": 1920, "fps": 60.0},
            "style_dna": {
                "fps": 60,
                "resolution": [1080, 1920],
                "aspect_ratio": "9:16",
                "visual_style": {"palette": "warm amber", "lighting": "macro spotlight"},
                "camera_dynamics": {"target_fps": 60, "preferred_motions": ["macro_push_in"]},
                "pacing": {"avg_shot_duration": 2.2, "cadence": "fast_paced_high_retention"},
                "audio_profile": {"asmr_layers": ["crisp_sizzle", "wood_chop"]},
                "consistency_anchors": ["consistent warm macro lighting"],
                "protected_content_compliant": True,
            },
        }
    ]
    master = build_master_style(profiles)
    assert master["schema_version"] == 2
    assert "style_dna" in master
    assert master["style_dna"]["fps"] == 60
    assert master["style_dna"]["aspect_ratio"] == "9:16"
