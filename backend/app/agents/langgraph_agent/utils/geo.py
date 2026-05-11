import math
import re
from typing import List, Dict, Optional


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def _cluster_attractions_by_proximity(attractions: List[Dict], num_days: int) -> List[List[Dict]]:
    n = len(attractions)
    if n == 0:
        return []
    if n <= num_days:
        return [[a] for a in attractions]

    dist_matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            d = _haversine_distance(
                attractions[i]["latitude"], attractions[i]["longitude"],
                attractions[j]["latitude"], attractions[j]["longitude"]
            )
            dist_matrix[i][j] = d
            dist_matrix[j][i] = d

    clusters = [[i] for i in range(n)]

    while len(clusters) > num_days:
        min_dist = float("inf")
        merge_i, merge_j = 0, 1
        for i in range(len(clusters)):
            for j in range(i + 1, len(clusters)):
                cluster_dist = min(
                    dist_matrix[a][b]
                    for a in clusters[i]
                    for b in clusters[j]
                )
                if cluster_dist < min_dist:
                    min_dist = cluster_dist
                    merge_i, merge_j = i, j

        clusters[merge_i] = clusters[merge_i] + clusters[merge_j]
        clusters.pop(merge_j)

    return [[attractions[i] for i in cluster] for cluster in clusters]


def _order_cluster_by_tsp(cluster: List[Dict]) -> List[Dict]:
    if len(cluster) <= 2:
        return cluster

    ordered = [cluster[0]]
    remaining = list(cluster[1:])

    while remaining:
        last = ordered[-1]
        nearest_idx = 0
        nearest_dist = float("inf")
        for i, attr in enumerate(remaining):
            d = _haversine_distance(last["latitude"], last["longitude"], attr["latitude"], attr["longitude"])
            if d < nearest_dist:
                nearest_dist = d
                nearest_idx = i
        ordered.append(remaining.pop(nearest_idx))

    return ordered


def _select_top_attractions(clusters: List[List[Dict]], max_per_day: int = 3) -> List[List[Dict]]:
    result = []
    for cluster in clusters:
        if len(cluster) <= max_per_day:
            result.append(cluster)
        else:
            if len(cluster) > 1:
                center_lat = sum(a["latitude"] for a in cluster) / len(cluster)
                center_lon = sum(a["longitude"] for a in cluster) / len(cluster)
                scored = []
                for attr in cluster:
                    d = _haversine_distance(center_lat, center_lon, attr["latitude"], attr["longitude"])
                    scored.append((attr, d))
                scored.sort(key=lambda x: x[1])
                result.append([s[0] for s in scored[:max_per_day]])
            else:
                result.append(cluster[:max_per_day])
    return result


def _format_cluster_info(clusters: List[List[Dict]], all_attractions: List[Dict], dist_matrix: List[List[float]], trimmed: bool = False) -> str:
    lines = ["=== 每日景点分组建议（基于地理位置聚类） ===", ""]

    if trimmed:
        lines.append("⚠️ 景点数量超过每天3个的上限，已按距离聚类中心最近的原则筛选，保留每天最多3个景点")
        lines.append("")

    for day_idx, cluster in enumerate(clusters):
        lines.append(f"第{day_idx + 1}天建议景点:")
        for order_idx, attr in enumerate(cluster):
            lines.append(f"  {order_idx + 1}. {attr['name']} ({attr['longitude']:.4f}, {attr['latitude']:.4f})")

        if len(cluster) > 1:
            max_dist = 0
            for i in range(len(cluster)):
                for j in range(i + 1, len(cluster)):
                    ci = all_attractions.index(cluster[i])
                    cj = all_attractions.index(cluster[j])
                    max_dist = max(max_dist, dist_matrix[ci][cj])
            lines.append(f"  组内最大距离: {max_dist:.1f}km")
        lines.append("")

    selected_names = set()
    for cluster in clusters:
        for attr in cluster:
            selected_names.add(attr["name"])

    lines.append("=== 选中景点间距离矩阵 (km) ===")
    lines.append("")

    selected_attrs = [a for a in all_attractions if a["name"] in selected_names]
    if len(selected_attrs) > 1:
        name_col_width = max(len(a["name"]) for a in selected_attrs) + 2
        header = " " * name_col_width
        for attr in selected_attrs:
            header += f"{attr['name'][:6]:>8}"
        lines.append(header)

        for i, attr in enumerate(selected_attrs):
            ci = all_attractions.index(attr)
            row = f"{attr['name'][:name_col_width - 1]:<{name_col_width}}"
            for j, attr_j in enumerate(selected_attrs):
                if i == j:
                    row += f"{'--':>8}"
                else:
                    cj = all_attractions.index(attr_j)
                    row += f"{dist_matrix[ci][cj]:>7.1f}"
            lines.append(row)

    return "\n".join(lines)


def _extract_coordinates_regex(text: str) -> List[Dict]:
    attractions = []

    amap_location_pattern = re.compile(
        r'"?name"?\s*[:=]\s*["\']([^"\']+)["\'].*?'
        r'"?location"?\s*[:=]\s*["\']([\d.]+)\s*,\s*([\d.]+)["\']',
        re.DOTALL | re.IGNORECASE
    )
    for m in amap_location_pattern.finditer(text):
        name = m.group(1).strip()
        try:
            lon = float(m.group(2))
            lat = float(m.group(3))
            if 73 < lon < 136 and 3 < lat < 54:
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except ValueError:
            continue

    if attractions:
        return attractions

    name_lon_lat = re.compile(
        r'"?name"?\s*[:=]\s*["\']([^"\']+)["\'].*?'
        r'"?longitude"?\s*[:=]\s*["\']?([\d.]+)["\']?.*?'
        r'"?latitude"?\s*[:=]\s*["\']?([\d.]+)["\']?',
        re.DOTALL | re.IGNORECASE
    )
    for m in name_lon_lat.finditer(text):
        name = m.group(1).strip()
        try:
            lon = float(m.group(2))
            lat = float(m.group(3))
            if 73 < lon < 136 and 3 < lat < 54:
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except ValueError:
            continue

    if attractions:
        return attractions

    lon_lat_name = re.compile(
        r'"?longitude"?\s*[:=]\s*["\']?([\d.]+)["\']?.*?'
        r'"?latitude"?\s*[:=]\s*["\']?([\d.]+)["\']?.*?'
        r'"?name"?\s*[:=]\s*["\']([^"\']+)["\']',
        re.DOTALL | re.IGNORECASE
    )
    for m in lon_lat_name.finditer(text):
        name = m.group(3).strip()
        try:
            lon = float(m.group(1))
            lat = float(m.group(2))
            if 73 < lon < 136 and 3 < lat < 54:
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except ValueError:
            continue

    if attractions:
        return attractions

    location_pattern = re.compile(
        r'"?(?:location|坐标)"?\s*[:=]\s*\{[^}]*?"?lon(?:gitude)?"?\s*[:=]\s*["\']?([\d.]+)["\']?\s*,\s*"?lat(?:itude)?"?\s*[:=]\s*["\']?([\d.]+)["\']?',
        re.DOTALL | re.IGNORECASE
    )
    name_pattern = re.compile(r'"?name"?\s*[:=]\s*["\']([^"\']+)["\']', re.IGNORECASE)

    locations = list(location_pattern.finditer(text))
    names = name_pattern.findall(text)

    for i, m in enumerate(locations):
        try:
            lon = float(m.group(1))
            lat = float(m.group(2))
            if 73 < lon < 136 and 3 < lat < 54:
                name = names[i].strip() if i < len(names) else f"景点{i+1}"
                attractions.append({"name": name, "longitude": lon, "latitude": lat})
        except (ValueError, IndexError):
            continue

    return attractions
