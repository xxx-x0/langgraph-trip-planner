from app.agents.langgraph_agent.utils.strategy_extract import (
    match_names_to_pool,
    normalize_name,
)


def test_normalize_strips_common_suffixes():
    assert normalize_name("故宫博物院") == "故宫"
    assert normalize_name("颐和园景区") == "颐和园"
    assert normalize_name("天坛公园") == "天坛"
    assert normalize_name("北京大学") == "北京大学"  # 不应删"学"


def test_match_to_pool_finds_fuzzy():
    pool = [
        {"poi_id": "1", "name": "故宫博物院"},
        {"poi_id": "2", "name": "颐和园"},
        {"poi_id": "3", "name": "天坛"},
    ]
    # 攻略文本中可能写"故宫"或"天坛公园"
    matched = match_names_to_pool(["故宫", "天坛公园", "长城"], pool)
    ids = sorted([m["poi_id"] for m in matched])
    assert ids == ["1", "3"]


def test_match_to_pool_handles_empty():
    assert match_names_to_pool([], [{"poi_id": "1", "name": "X"}]) == []
    assert match_names_to_pool(["A"], []) == []
