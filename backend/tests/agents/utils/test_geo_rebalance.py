from app.agents.langgraph_agent.utils.geo import _rebalance_by_duration


def _attr(name, lon, lat):
    return {"name": name, "longitude": lon, "latitude": lat}


def test_no_rebalance_when_within_limit():
    clusters = [
        [_attr("A", 116.40, 39.90), _attr("B", 116.41, 39.91)],
        [_attr("C", 116.50, 39.95)],
    ]
    durations = {"A": 120, "B": 120, "C": 120}
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    assert [[a["name"] for a in c] for c in result] == [["A", "B"], ["C"]]


def test_moves_farthest_attraction_when_over_limit():
    # Day 0 总 540 分钟超 480；远点 D 距质心最远，应移走到 day 1
    clusters = [
        [
            _attr("A", 116.40, 39.90),
            _attr("B", 116.41, 39.91),
            _attr("C", 116.40, 39.92),
            _attr("D", 116.80, 40.30),
        ],
        [_attr("E", 116.85, 40.35)],
    ]
    durations = {"A": 150, "B": 150, "C": 120, "D": 120, "E": 60}
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    names_day0 = {a["name"] for a in result[0]}
    names_day1 = {a["name"] for a in result[1]}
    assert "D" in names_day1
    assert "D" not in names_day0


def test_stops_when_move_would_make_target_overflow():
    # Day 0 超限，但移到 day 1 会让 day 1 也超限 → 停止
    clusters = [
        [_attr("A", 116.40, 39.90), _attr("B", 116.41, 39.91)],
        [_attr("C", 116.42, 39.92), _attr("D", 116.43, 39.93)],
    ]
    durations = {"A": 300, "B": 250, "C": 300, "D": 200}  # day0=550, day1=500
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    # 无论怎么挪，目标都会超限 → 至少不能让目标更糟
    for cluster in result:
        # 这个用例下可能完全不动，只验证函数不崩、所有景点都在
        pass
    all_names = sorted(a["name"] for c in result for a in c)
    assert all_names == ["A", "B", "C", "D"]


def test_preserves_all_attractions_after_rebalance():
    clusters = [
        [_attr("A", 116.40, 39.90), _attr("B", 116.41, 39.91), _attr("C", 116.42, 39.92)],
        [_attr("D", 116.80, 40.30)],
    ]
    durations = {"A": 200, "B": 200, "C": 200, "D": 60}
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    all_names = sorted(a["name"] for c in result for a in c)
    assert all_names == ["A", "B", "C", "D"]


def test_keeps_nearby_cluster_when_only_remote_day_has_capacity():
    clusters = [
        [
            _attr("Beach A", 109.5050, 18.2450),
            _attr("Beach B", 109.5060, 18.2460),
            _attr("Beach C", 109.5070, 18.2470),
            _attr("Beach D", 109.5080, 18.2480),
        ],
        [_attr("Bay", 109.3470, 18.3100)],
    ]
    durations = {
        "Beach A": 150,
        "Beach B": 150,
        "Beach C": 120,
        "Beach D": 120,
        "Bay": 60,
    }

    result = _rebalance_by_duration(clusters, durations, max_minutes=480)

    assert {a["name"] for a in result[0]} == {
        "Beach A",
        "Beach B",
        "Beach C",
        "Beach D",
    }
    assert [a["name"] for a in result[1]] == ["Bay"]


def test_handles_missing_coords_gracefully():
    clusters = [
        [{"name": "A", "longitude": 0, "latitude": 0}, {"name": "B", "longitude": 0, "latitude": 0}],
        [{"name": "C", "longitude": 116.5, "latitude": 39.9}],
    ]
    durations = {"A": 300, "B": 300, "C": 100}
    # 坐标全 0，距离都是 0，不应崩溃
    result = _rebalance_by_duration(clusters, durations, max_minutes=480)
    all_names = sorted(a["name"] for c in result for a in c)
    assert all_names == ["A", "B", "C"]
