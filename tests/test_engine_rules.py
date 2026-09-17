from core.audio.timeline import AudioEvent, AudioTimeline
from core.continuity.validator import validate_plan_continuity
from core.contracts import ProjectPlan, SceneBeat, ScenePlan


def test_audio_timeline_is_sorted_and_bounded():
    timeline = AudioTimeline(10)
    timeline.add(AudioEvent(4.0, 5.0, "sfx", "tap", 0.4))
    timeline.add(AudioEvent(1.0, 3.0, "ambience", "wind", 0.2))
    assert timeline.validate() == []
    assert [e.start for e in timeline.events] == [1.0, 4.0]


def test_continuity_accepts_physical_action():
    plan = ProjectPlan(5, "x", [ScenePlan(1, 0, 5, [SceneBeat(0, 2, "character picks up cup", "move")], "cup")])
    assert validate_plan_continuity(plan) == []


def test_continuity_rejects_explicit_teleport_instruction():
    plan = ProjectPlan(5, "x", [ScenePlan(1, 0, 5, [SceneBeat(0, 2, "cup teleports to table", "move")], "cup")])
    assert validate_plan_continuity(plan)
