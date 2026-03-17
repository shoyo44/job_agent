from agent.manager_agent import ManagerAgent


def test_manager_build_profile_from_goal_with_llm(monkeypatch):
    monkeypatch.setattr("config.USER_TARGET_ROLES", ["ML Engineer"])
    monkeypatch.setattr("config.USER_TARGET_LOCATIONS", ["Bangalore"])
    monkeypatch.setattr("config.USER_WORK_MODE", "any")
    monkeypatch.setattr("config.USER_MIN_SALARY", 0)

    agent = ManagerAgent()

    def fake_llm_json(*args, **kwargs):
        return {
            "roles": ["AI Engineer"],
            "locations": ["Remote"],
            "work_mode": "remote",
            "min_salary": 20,
            "extra_keywords": ["llm"],
        }

    monkeypatch.setattr(agent, "ask_llm_json", fake_llm_json)
    profile = agent.build_profile_from_goal("Apply for remote AI jobs")

    assert profile.roles == ["AI Engineer"]
    assert profile.locations == ["Remote"]
    assert profile.work_mode == "remote"
    assert profile.min_salary == 20
    assert profile.extra_keywords == ["llm"]


def test_manager_fallback_profile_fields(monkeypatch):
    monkeypatch.setattr("config.USER_TARGET_ROLES", ["ML Engineer"])
    monkeypatch.setattr("config.USER_TARGET_LOCATIONS", ["Bangalore"])
    monkeypatch.setattr("config.USER_WORK_MODE", "any")
    monkeypatch.setattr("config.USER_MIN_SALARY", 0)

    agent = ManagerAgent()
    monkeypatch.setattr(agent, "ask_llm_json", lambda *args, **kwargs: {})

    profile = agent.build_profile_from_goal(
        "Find data scientist jobs in Pune remote with 15 lpa"
    )

    assert "Data Scientist" in profile.roles
    assert "Pune" in profile.locations
    assert profile.work_mode == "remote"
    assert profile.min_salary == 15
