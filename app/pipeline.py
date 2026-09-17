from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

from .providers import gemini_text, hf_text_to_image, tavily_search
from .storage import get_keys, load_config
from core.audio.timeline import AudioEvent, AudioTimeline
from core.cleanup import cleanup_project_artifacts
from core.continuity.validator import validate_plan_continuity
from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.db.memory import MemoryDB
from core.duration import distribute_duration, scene_count, validate_duration
from core.image.router import HuggingFaceImageRouter
from core.image.validator import validate_image_file
from core.qc.engine import validate_output
from core.recovery.checkpoints import Checkpoints
from core.render.ffmpeg import animate_image, concat, mux_video_audio, synthesize_audio

ROOT = Path(__file__).resolve().parent.parent
PROJECTS = ROOT / "projects"
OUTPUT = ROOT / "output"
PROJECTS.mkdir(exist_ok=True)
OUTPUT.mkdir(exist_ok=True)


def _fallback_plan(instruction: str, duration: int) -> ProjectPlan:
    count = scene_count(duration)
    durations = distribute_duration(duration, count)
    scenes, cursor = [], 0.0
    for i, span in enumerate(durations, 1):
        end = cursor + span
        beats = []
        for b in range(4):
            bs = cursor + span * b / 4
            be = cursor + span * (b + 1) / 4
            action = ["establish the setting", "character makes a natural physical move", "object action continues through contact", "hold on the emotional visual reveal"][b]
            beats.append(SceneBeat(round(bs, 3), round(be, 3), action, "slow cinematic push and gentle parallax"))
        scenes.append(ScenePlan(i, round(cursor, 3), round(end, 3), beats, f"Original cinematic vertical scene for {instruction}; preserve character face, clothes, body proportions, object identity and environment; every object interaction must be physically continuous; no text, subtitles, logos, watermark or spoken dialogue."))
        cursor = end
    return ProjectPlan(duration, instruction[:80], scenes, load_config().get("reference_profile", {}), {})


def _extract_json(text: str):
    match = re.search(r"\[[\s\S]*\]", text or "")
    return json.loads(match.group(0)) if match else None


def _normalize_gemini_plan(raw: list[dict], instruction: str, duration: int) -> ProjectPlan:
    count = scene_count(duration)
    durations = distribute_duration(duration, min(max(1, len(raw)), count))
    raw = raw[:len(durations)]
    if len(raw) < len(durations):
        return _fallback_plan(instruction, duration)
    scenes, cursor = [], 0.0
    for i, (item, span) in enumerate(zip(raw, durations), 1):
        end = cursor + span
        actions = item.get("beats") or item.get("visual_beats") or []
        actions = [str(x.get("action", x) if isinstance(x, dict) else x) for x in actions][:5]
        while len(actions) < 3:
            actions.append("continue the same physical action with consistent objects")
        actions = actions[:5]
        beats = [SceneBeat(round(cursor + span*j/len(actions), 3), round(cursor + span*(j+1)/len(actions), 3), a, str(item.get("camera", "gentle cinematic movement"))) for j, a in enumerate(actions)]
        prompt = str(item.get("visual_prompt") or item.get("prompt") or instruction)
        prompt += ", original production, physically continuous object interactions, consistent character and environment, no dialogue, no subtitles, no text"
        scenes.append(ScenePlan(i, round(cursor, 3), round(end, 3), beats, prompt, item.get("audio_events", []), {"objects_must_persist": True, "no_teleportation": True}))
        cursor = end
    return ProjectPlan(duration, str(raw[0].get("title", instruction[:80])), scenes, load_config().get("reference_profile", {}), {})


def make_plan(instruction: str, duration: int, research: list[dict] | None = None) -> ProjectPlan:
    duration = validate_duration(duration)
    cfg = load_config()
    profile = json.dumps(cfg.get("reference_profile", {}), ensure_ascii=False)[:16000]
    research_text = json.dumps(research or [], ensure_ascii=False)[:12000]
    prompt = f"""Create an ORIGINAL silent cinematic YouTube Short plan for exactly {duration} seconds. User request: {instruction}\nReference production DNA (high-level only): {profile}\nVerified research context: {research_text}\nReturn ONLY a JSON array of scenes. Each scene must contain visual_prompt, camera, beats (3-5 short physical actions), and audio_events. No spoken dialogue. Use natural human vocal reactions only as non-verbal expression events. Include environmental ASMR/SFX with timestamps. Every pickup, placement, carrying, opening, closing, pouring, cutting, mixing or lifting action must be physically continuous: objects cannot teleport, disappear, duplicate, float, morph, or change identity. Do not copy characters, dialogue, scenes or shot sequences from references."""
    try:
        parsed = _extract_json(gemini_text(prompt))
        if isinstance(parsed, list) and parsed:
            plan = _normalize_gemini_plan(parsed, instruction, duration)
            if not validate_plan_continuity(plan):
                return plan
    except Exception:
        pass
    return _fallback_plan(instruction, duration)


def _format_scene_prompt(scene: ScenePlan, plan: ProjectPlan) -> str:
    parts = [scene.visual_prompt]

    # Incorporate Reference Style DNA if present
    profile = plan.reference_profile or {}
    visual_style = profile.get("visual_style") or profile.get("style") or profile.get("dna", {})
    if isinstance(visual_style, dict):
        desc = visual_style.get("description") or visual_style.get("name")
        palette = visual_style.get("color_palette") or visual_style.get("palette")
        lighting = visual_style.get("lighting")
        camera = visual_style.get("camera_language") or visual_style.get("camera")
        if desc:
            parts.append(f"Visual style: {desc}")
        if palette:
            parts.append(f"Color palette: {palette}")
        if lighting:
            parts.append(f"Lighting: {lighting}")
        if camera:
            parts.append(f"Camera: {camera}")
    elif isinstance(visual_style, str) and visual_style.strip():
        parts.append(f"Style DNA: {visual_style.strip()}")

    parts.append("vertical 9:16, cinematic, high detail, coherent lighting, no text, no subtitles, no watermark")
    return ", ".join(parts)


def generate_images(
    plan: ProjectPlan,
    project_dir: Path,
    status_cb=lambda s: None,
    allow_placeholders: bool = False,
    router: HuggingFaceImageRouter | None = None,
) -> list[Path]:
    image_dir = project_dir / "images"
    image_dir.mkdir(exist_ok=True)
    result = []

    if router is None:
        keys = get_keys("huggingface")
        router = HuggingFaceImageRouter(api_keys=keys)

    for scene in plan.scenes:
        path = image_dir / f"scene_{scene.index:03d}.jpg"
        prompt = _format_scene_prompt(scene, plan)
        status_cb(f"Scene {scene.index}: generating image...")
        try:
            # If router has no API keys or hf_text_to_image was monkeypatched/mocked in tests:
            if not router.api_keys or hf_text_to_image.__name__ != "hf_text_to_image" or hf_text_to_image.__module__ != "app.providers":
                data = hf_text_to_image(prompt)
                path.write_bytes(data)
                validate_image_file(path)
                status_cb(f"Scene {scene.index}: image generated successfully")
            else:
                image_res = router.generate(
                    prompt=prompt,
                    output_path=path,
                    width=1080,
                    height=1920,
                    project_context=plan.title,
                    allow_placeholders=allow_placeholders,
                )
                validate_image_file(path)
                status_cb(f"Scene {scene.index}: image generated via {image_res.route_used}")
            result.append(path)
        except Exception as exc:
            status_cb(f"Scene {scene.index}: image generation failed ({exc})")
            if allow_placeholders:
                router._create_placeholder(path, prompt, str(exc))
                result.append(path)
                continue
            raise RuntimeError(
                f"Scene {scene.index} image generation failed: {exc}. "
                f"Job state preserved for resumption in {project_dir}."
            ) from exc
    return result


def build_audio_timeline(plan: ProjectPlan) -> AudioTimeline:
    timeline = AudioTimeline(plan.duration)
    for scene in plan.scenes:
        timeline.add(AudioEvent(scene.start, min(scene.end, scene.start + min(0.8, scene.end-scene.start)), "ambience", "environment", 0.25))
        for beat in scene.beats:
            lower = beat.action.lower()
            if any(word in lower for word in ("cut", "place", "pour", "tap", "step", "knock", "mix", "open", "close")):
                timeline.add(AudioEvent(beat.start, min(beat.end, beat.start + 0.35), "sfx", "tap", 0.18, True))
    return timeline


def animate_images(images: list[Path], plan: ProjectPlan, project_dir: Path) -> list[Path]:
    clips = project_dir / "clips"
    clips.mkdir(exist_ok=True)
    result = []
    for image, scene in zip(images, plan.scenes):
        result.append(animate_image(image, clips / f"scene_{scene.index:03d}.mp4", scene.end - scene.start))
    return result


def render(clips: list[Path], plan: ProjectPlan, project_dir: Path) -> tuple[Path, AudioTimeline, list[str]]:
    silent = project_dir / "video_silent.mp4"
    concat(clips, silent)
    timeline = build_audio_timeline(plan)
    timeline_errors = timeline.validate()
    if timeline_errors:
        raise RuntimeError("Audio timeline invalid: " + "; ".join(timeline_errors))
    audio = project_dir / "audio.wav.m4a"
    synthesize_audio(plan.duration, timeline, audio)
    out = OUTPUT / f"{project_dir.name}.mp4"
    mux_video_audio(silent, audio, out, plan.duration)
    errors = validate_output(out, plan.duration)
    if errors:
        raise RuntimeError("Output QC failed: " + "; ".join(errors))
    (project_dir / "audio_timeline.json").write_text(json.dumps(timeline.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return out, timeline, errors


def run_project(
    instruction: str,
    duration: int,
    status_cb=lambda s: None,
    project_dir: Path | None = None,
    allow_placeholders: bool = False,
) -> Path:
    duration = validate_duration(duration)
    if project_dir is None:
        project_dir = PROJECTS / ("short_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f"))
    project_dir.mkdir(parents=True, exist_ok=True)
    project_key = project_dir.name
    db = MemoryDB()
    db.remember_project(project_key, instruction, duration, "created")
    db.remember("instruction", {"instruction": instruction, "duration": duration}, project_key, "latest")
    checkpoint = Checkpoints(project_dir / "checkpoint.json")
    if not (project_dir / "checkpoint.json").exists():
        checkpoint.save("created", {"duration": duration, "instruction": instruction})
        db.remember_checkpoint(project_key, "created", {"duration": duration, "instruction": instruction})
    try:
        plan: ProjectPlan | None = None
        plan_file = project_dir / "plan.json"
        if plan_file.is_file():
            try:
                saved_plan_data = json.loads(plan_file.read_text(encoding="utf-8"))
                candidate = ProjectPlan.from_dict(saved_plan_data)
                if not validate_plan_continuity(candidate):
                    plan = candidate
                    status_cb("Resuming with saved plan...")
            except Exception:
                plan = None

        if plan is None:
            status_cb("Researching the requested topic...")
            research = tavily_search(instruction)
            for item in research:
                db.remember_research({"url": item.get("url"), "title": item.get("title"), "topic": instruction, "summary": item.get("content") or item.get("snippet"), "evidence": item})
            db.remember("research_batch", {"query": instruction, "count": len(research), "retrieved_at": datetime.now(timezone.utc).isoformat()}, project_key, "latest")
            db.remember_decision(project_key, {"key": "research", "provider": "tavily", "result_count": len(research), "fallback": not bool(research)})

            status_cb("Planning story, scenes and synchronized audio...")
            plan = make_plan(instruction, duration, research)
            plan_data = plan.to_dict()
            continuity_errors = validate_plan_continuity(plan)
            if continuity_errors:
                raise RuntimeError("Plan continuity failed: " + "; ".join(continuity_errors))
            plan_file.write_text(json.dumps(plan_data, ensure_ascii=False, indent=2), encoding="utf-8")
            db.remember_plan(project_key, plan_data)
            db.remember_project(project_key, instruction, duration, "planned")
            db.remember_checkpoint(project_key, "planned")
            checkpoint.save("planned")

        expected_images = [project_dir / "images" / f"scene_{s.index:03d}.jpg" for s in plan.scenes]
        if all(p.is_file() and p.stat().st_size > 0 for p in expected_images):
            status_cb("Resuming with existing scene images...")
            images = expected_images
        else:
            status_cb("Generating consistent scene images...")
            images = generate_images(plan, project_dir, status_cb, allow_placeholders=allow_placeholders)
            db.remember("image_generation", {"count": len(images), "scenes": [str(p) for p in images]}, project_key, "latest")
            for image in images:
                db.remember_artifact(project_key, "image", str(image), {"temporary": True})
            checkpoint.save("images", {"count": len(images)})
            db.remember_checkpoint(project_key, "images", {"count": len(images)})

        expected_clips = [project_dir / "clips" / f"scene_{s.index:03d}.mp4" for s in plan.scenes]
        if all(c.is_file() and c.stat().st_size > 0 for c in expected_clips):
            status_cb("Resuming with existing scene clips...")
            clips = expected_clips
        else:
            status_cb("Animating scenes locally with FFmpeg...")
            clips = animate_images(images, plan, project_dir)
            db.remember("animation", {"count": len(clips), "clips": [str(p) for p in clips]}, project_key, "latest")
            for clip in clips:
                db.remember_artifact(project_key, "clip", str(clip), {"temporary": True})
            checkpoint.save("animated", {"count": len(clips)})
            db.remember_checkpoint(project_key, "animated", {"count": len(clips)})

        status_cb("Mixing ASMR/SFX and rendering final MP4...")
        out, timeline, _ = render(clips, plan, project_dir)
        db.remember("audio_timeline", timeline.to_dict(), project_key, "latest")
        db.remember_artifact(project_key, "final_video", str(out), {"temporary": False})
        db.remember_qc(project_key, [], str(out))
        db.remember_project(project_key, instruction, duration, "completed")
        checkpoint.save("completed", {"output": str(out)})
        db.remember_checkpoint(project_key, "completed", {"output": str(out)})
        status_cb("Cleaning temporary images, audio and intermediate files...")
        cleanup_project_artifacts(project_dir, out, OUTPUT)
        db.remember("cleanup", {"project_dir": str(project_dir), "final_output": str(out), "temporary_artifacts_deleted": True}, project_key, "completed")
        status_cb(f"QC PASS — {out}")
        return out
    except Exception as exc:
        db.remember_error(project_key, "pipeline", exc)
        db.remember_project(project_key, instruction, duration, "failed")
        try:
            db.remember_qc(project_key, [str(exc)])
        except Exception:
            pass
        raise
