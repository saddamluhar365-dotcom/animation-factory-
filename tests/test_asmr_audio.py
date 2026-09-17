from __future__ import annotations
import shutil
from pathlib import Path
import pytest
from core.audio.timeline import AudioEvent, AudioTimeline
from core.audio.asmr import synthesize_rich_asmr_audio
from core.qc.engine import ffprobe_json


def test_synthesize_rich_asmr_audio(tmp_path: Path):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg not available")

    timeline = AudioTimeline(3.0)
    timeline.add(AudioEvent(0.0, 3.0, "ambience", "environment", 0.20))
    timeline.add(AudioEvent(0.5, 1.2, "sfx", "chop", 0.25, True))
    timeline.add(AudioEvent(1.4, 2.4, "sfx", "sizzle", 0.25, True))
    timeline.add(AudioEvent(2.2, 2.8, "sfx", "clink", 0.22, True))

    out_audio = tmp_path / "rich_asmr.m4a"
    res = synthesize_rich_asmr_audio(duration=3.0, timeline=timeline, output=out_audio)
    assert res.exists()
    assert res.stat().st_size > 1000

    info = ffprobe_json(res)
    audio = next(s for s in info["streams"] if s["codec_type"] == "audio")
    assert audio["codec_name"] == "aac"
    assert audio["sample_rate"] == "48000"
    assert audio["channels"] == 2
