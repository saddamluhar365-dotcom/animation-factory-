from datetime import datetime, timezone, timedelta
from core.duration import validate_duration, scene_count
from core.continuity.validator import validate_state_transition
from core.research.ranker import freshness
from core.audio.timeline import AudioEvent, validate_events
from core.qc.rules import validate_vertical


def test_duration_bounds():
    assert validate_duration(1) == 1
    assert validate_duration(180) == 180
    assert scene_count(90) == 9
    for value in (0, 181):
        try: validate_duration(value)
        except ValueError: pass
        else: raise AssertionError("invalid duration accepted")


def test_physical_state_cannot_drop_object():
    errors = validate_state_transition({"objects": {"cup": {"size": "small"}}}, {"objects": {}})
    assert "object disappeared: cup" in errors


def test_freshness_decays():
    recent = datetime.now(timezone.utc).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()
    assert freshness(recent) > freshness(old)


def test_audio_bounds():
    assert validate_events([AudioEvent(1, 2, "sfx", "step.wav")], 3) == []
    assert validate_events([AudioEvent(-1, 2, "sfx", "bad.wav")], 3)


def test_vertical_qc():
    assert validate_vertical(10, 1080, 1920) == []
    assert validate_vertical(10, 1920, 1080)
