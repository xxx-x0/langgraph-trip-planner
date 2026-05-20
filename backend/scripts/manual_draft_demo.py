"""手测脚本：跑完整 draft 流程，每一步 dump 到 /tmp/draft_*.json

需后端服务已启动 (python run.py)。
"""
import asyncio
import json
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
OUT = Path("/tmp")


async def main():
    async with httpx.AsyncClient(timeout=180.0) as client:
        # 1. 跑 from-selections/stream
        body = {
            "request": {
                "city": "北京", "start_date": "2026-06-01", "end_date": "2026-06-02",
                "travel_days": 2, "transportation": "公共交通",
                "accommodation": "经济型酒店", "preferences": ["历史文化"],
                "food_preference": "本地特色",
            },
            "selected_attractions": [
                {"name": "故宫博物院", "location": {"longitude": 116.397128, "latitude": 39.916527}},
                {"name": "颐和园", "location": {"longitude": 116.273, "latitude": 39.999}},
            ],
            "day_assignments": None,
            "weather_info": "",
            "user_id": "manual_test",
        }
        draft_id = None
        async with client.stream(
            "POST", f"{BASE}/api/trip/draft/from-selections/stream",
            json=body,
        ) as resp:
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    print("[SSE]", evt.get("type"), evt.get("message", "")[:60])
                    if evt.get("type") == "complete":
                        draft_id = evt.get("draft_id")
        assert draft_id, "未拿到 draft_id"
        print(f"\n✅ 草稿 ID: {draft_id}")

        # 2. GET draft
        r = await client.get(f"{BASE}/api/trip/draft/{draft_id}")
        (OUT / f"draft_{draft_id}_skeleton.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2)
        )
        print(f"📝 dump → /tmp/draft_{draft_id}_skeleton.json")

        # 3. assemble day 0
        r = await client.post(f"{BASE}/api/trip/draft/{draft_id}/day/0/assemble", json={})
        (OUT / f"draft_{draft_id}_day0_assembled.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2)
        )
        print(f"📝 dump → /tmp/draft_{draft_id}_day0_assembled.json")

        # 4. recompute day 0 with re-ordered attractions
        r = await client.post(
            f"{BASE}/api/trip/draft/{draft_id}/day/0/recompute",
            json={"attractions_order": ["颐和园", "故宫博物院"], "meals": []},
        )
        print(f"  → recompute: {len(r.json()['day_detail']['route_segments'])} segments")

        # 5. finalize
        async with client.stream(
            "POST", f"{BASE}/api/trip/draft/{draft_id}/finalize",
        ) as resp:
            trip_id = None
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    evt = json.loads(line[6:])
                    print("[FIN]", evt.get("type"))
                    if evt.get("type") == "complete":
                        trip_id = evt.get("trip_id")
            assert trip_id, "finalize 未返回 trip_id"
            print(f"\n✅ 已定稿: trip_id={trip_id}")


if __name__ == "__main__":
    asyncio.run(main())
