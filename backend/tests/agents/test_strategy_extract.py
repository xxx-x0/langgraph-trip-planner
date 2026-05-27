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


def test_normalize_strips_long_suffix_first():
    """更长的后缀优先匹配，避免 '九寨沟风景区' -> '九寨沟风'"""
    assert normalize_name("九寨沟风景区") == "九寨沟"
    assert normalize_name("张家界国家森林公园") == "张家界国家"
    # 注：上面会去 "森林公园" 整段。如果业务上希望保留 "张家界"，需要更智能的策略
    # 但单层后缀剥离对常见 case 已够用


def test_match_to_pool_rejects_short_substring_false_positives():
    """短字符不应导致误匹配"""
    pool = [
        {"poi_id": "1", "name": "故宫小学"},  # 不是景点，干扰项
        {"poi_id": "2", "name": "故宫博物院"},  # 真景点
    ]
    matched = match_names_to_pool(["故宫"], pool)
    # 应该只匹配 normalize 后等于 "故宫" 的那个
    assert [m["poi_id"] for m in matched] == ["2"]


def test_match_to_pool_rejects_single_char_match():
    """单字符 cand 不应匹配任何 pool 项"""
    pool = [{"poi_id": "1", "name": "天坛"}]
    matched = match_names_to_pool(["天"], pool)
    assert matched == []


def test_match_to_pool_allows_short_exact_match():
    """但 normalize 完全相等的短名应该匹配（如 '故宫' = '故宫'）"""
    pool = [{"poi_id": "1", "name": "故宫"}]
    matched = match_names_to_pool(["故宫"], pool)
    assert [m["poi_id"] for m in matched] == ["1"]
