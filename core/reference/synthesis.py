from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone


def build_master_style(profiles: list[dict]) -> dict:
    if not profiles:
        return {
            "schema_version": 2,
            "characteristics": {},
            "provenance": [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "style_dna": {
                "fps": 60,
                "resolution": [1080, 1920],
                "aspect_ratio": "9:16",
                "visual_style": {
                    "palette": "warm golden amber, rich culinary tones",
                    "lighting": "warm directional macro spotlight, rim light",
                    "camera_language": "cinematic macro motion, smooth push-in with gentle parallax",
                    "description": "Premium cinematic macro style with rich warm lighting and tactile textures",
                },
                "camera_dynamics": {
                    "target_fps": 60,
                    "preferred_motions": ["macro_push_in", "cinematic_drift", "dynamic_tilt", "reveal_pull_out"],
                    "easing": "cubic_ease_in_out",
                },
                "pacing": {"avg_shot_duration": 2.2, "cadence": "fast_paced_high_retention", "cuts_per_minute": 27.0},
                "audio_profile": {
                    "asmr_layers": ["ambient_presence", "crisp_sizzle", "wood_chop", "liquid_pour", "metallic_clink"],
                    "asmr_capable": True,
                },
                "consistency_anchors": [
                    "consistent warm directional macro lighting",
                    "consistent character hands in natural culinary technique with neutral sleeves",
                    "consistent dark walnut cutting board and matte cookware",
                    "consistent shallow depth of field with soft creamy bokeh background",
                ],
                "protected_content_compliant": True,
            },
        }

    technical = [p.get("technical", {}) for p in profiles]
    ratios = [f"{x.get('width')}x{x.get('height')}" for x in technical if x.get("width") and x.get("height")]

    # Collect style_dna components if present
    dnas = [p.get("style_dna", {}) for p in profiles if p.get("style_dna")]
    if dnas:
        # Prefer the most complete style dna
        primary_dna = dnas[0]
        fps = max((d.get("fps", 60) for d in dnas), default=60)
        resolution = primary_dna.get("resolution", [1080, 1920])
        aspect_ratio = primary_dna.get("aspect_ratio", "9:16")
        visual_style = primary_dna.get("visual_style", {})
        camera_dynamics = primary_dna.get("camera_dynamics", {})
        pacing = primary_dna.get("pacing", {})
        audio_profile = primary_dna.get("audio_profile", {})
        consistency_anchors = primary_dna.get("consistency_anchors", [])
    else:
        fps = 60
        resolution = [1080, 1920]
        aspect_ratio = "9:16"
        visual_style = {
            "palette": "warm golden amber, rich culinary tones",
            "lighting": "warm directional macro spotlight, rim light",
            "camera_language": "cinematic macro motion, smooth push-in with gentle parallax",
            "description": "Premium cinematic macro style with rich warm lighting and tactile textures",
        }
        camera_dynamics = {
            "target_fps": 60,
            "preferred_motions": ["macro_push_in", "cinematic_drift", "dynamic_tilt", "reveal_pull_out"],
            "easing": "cubic_ease_in_out",
        }
        pacing = {"avg_shot_duration": 2.2, "cadence": "fast_paced_high_retention", "cuts_per_minute": 27.0}
        audio_profile = {
            "asmr_layers": ["ambient_presence", "crisp_sizzle", "wood_chop", "liquid_pour", "metallic_clink"],
            "asmr_capable": True,
        }
        consistency_anchors = [
            "consistent warm directional macro lighting",
            "consistent character hands in natural culinary technique with neutral sleeves",
            "consistent dark walnut cutting board and matte cookware",
            "consistent shallow depth of field with soft creamy bokeh background",
        ]

    master_dna = {
        "fps": fps,
        "resolution": resolution,
        "aspect_ratio": aspect_ratio,
        "visual_style": visual_style,
        "camera_dynamics": camera_dynamics,
        "pacing": pacing,
        "audio_profile": audio_profile,
        "consistency_anchors": consistency_anchors,
        "protected_content_compliant": True,
    }

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "provenance": [p.get("source_hash") for p in profiles],
        "reference_count": len(profiles),
        "characteristics": {
            "aspect_ratios": Counter(ratios).most_common(),
            "analysis_frame_counts": [p.get("visual_features", {}).get("frame_count", 0) for p in profiles],
            "audio_coverage": sum(bool(p.get("audio_extracted")) for p in profiles) / len(profiles),
            "fps_target": fps,
        },
        "style_dna": master_dna,
    }
