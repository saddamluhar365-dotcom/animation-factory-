from core.contracts import ProjectPlan, SceneBeat, ScenePlan
from core.duration import scene_count, validate_duration


def test_duration_bounds_and_scene_count():
    assert validate_duration(1) == 1
    assert validate_duration(180) == 180
    assert scene_count(90) == 9


def test_plan_contract_is_serializable():
    plan = ProjectPlan(10, "test", [ScenePlan(1, 0, 10, [SceneBeat(0, 2, "beat", "move")], "prompt")])
    data = plan.to_dict()
    assert data["duration"] == 10
    assert data["scenes"][0]["beats"][0]["start"] == 0
