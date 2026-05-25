# Hotel Rates Multimodal Timeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore AIGoHotel prices and booking links, make route segments choose usable transport fallbacks, and make result timelines reflect user meals and configurable day start times.

**Architecture:** Normalize AIGoHotel schema drift in the hotel service/parser boundary, so graph nodes keep consuming stable hotel dictionaries. Make route resolution produce one structured `RouteSegment` per waypoint pair through distance-aware mode candidates and a readable fallback. Persist timeline order and effective start-time data through draft finalization so the frontend can render user-added meals and configurable departure times instead of reconstructing a reduced timeline.

**Tech Stack:** Python, FastAPI, Pydantic, pytest, Vue 3, TypeScript, Ant Design Vue, Vite, AMap MCP, AIGoHotel MCP.

---

## File Map

- Modify `backend/app/services/aigohotel_mcp_service.py` for current nested SearchHotels and GetHotelDetail argument shapes.
- Modify `backend/app/agents/langgraph_agent/nodes/search.py` and `backend/tests/agents/test_search_hotels.py` for `hotel_id`, `bookingUrl`, and object-shaped price parsing.
- Modify `backend/app/agents/langgraph_agent/utils/route.py` plus route tests for mode fallback and readable no-transit handling.
- Modify `backend/app/models/schemas.py`, draft/finalize services, and schema/finalize tests for default and per-day start times plus `timeline_order` persistence.
- Modify `frontend/src/types/index.ts`, request/form surfaces, draft day cards, and result timeline components for start-time controls and meal-aware ordering.

### Task 1: Restore AIGoHotel Price And Link Fields

**Files:**
- Modify: `backend/tests/agents/test_search_hotels.py`
- Modify: `backend/app/agents/langgraph_agent/nodes/search.py`
- Modify: `backend/app/services/aigohotel_mcp_service.py`

- [ ] **Step 1: Write failing parser tests**

Add coverage for:

```python
def test_parse_aigohotel_hotels_reads_price_object_booking_url_and_hotel_id():
    hotels = _parse_aigohotel_hotels({
        "hotelInformationList": [{
            "hotelId": 572174,
            "name": "麗枫酒店",
            "bookingUrl": "https://rollinggo.example/hotel",
            "price": {"hasPrice": True, "lowestPrice": 350, "currency": "CNY"},
        }]
    })
    assert hotels[0]["hotel_id"] == 572174
    assert hotels[0]["price"] == 350
    assert hotels[0]["currency"] == "CNY"
    assert hotels[0]["detail_url"] == "https://rollinggo.example/hotel"
```

- [ ] **Step 2: Write failing service argument tests**

Assert SearchHotels receives `checkInParam` and `filterOptions`, and GetHotelDetail can receive date and occupancy objects.

- [ ] **Step 3: Verify the tests fail**

Run focused hotel tests with backend venv pytest.

- [ ] **Step 4: Implement parser and service normalization**

Map the current MCP field shapes while preserving old numeric-price compatibility.

### Task 2: Add Multimodal Route Fallback

**Files:**
- Modify or add focused route tests under `backend/tests/agents/`
- Modify: `backend/app/agents/langgraph_agent/utils/route.py`

- [ ] **Step 1: Write failing route tests**

Cover:

- nearby waypoint pairs prefer walking candidates over transit.
- a transit response with `transits: []` does not expose raw response text.
- failed preferred mode falls back to another route candidate or readable estimate.

- [ ] **Step 2: Verify route tests fail**

Run focused route tests with pytest.

- [ ] **Step 3: Implement distance-aware mode candidates**

Generate candidate mode order by distance and user preference, parse only usable responses, and fall back to a readable structured segment.

- [ ] **Step 4: Verify route tests pass**

Run the focused route tests and existing route assembly tests.

### Task 3: Persist Timeline Order And Start Times

**Files:**
- Modify: `backend/app/models/schemas.py`
- Modify: `backend/app/api/routes/trip_draft.py`
- Modify: `backend/app/agents/langgraph_agent/finalize/pipeline.py`
- Modify: schema, draft endpoint, and finalize tests

- [ ] **Step 1: Write failing schema/finalize tests**

Cover:

- `TripRequest` accepts a default day start time.
- `DayEditRequest` accepts a day override.
- `DayDetail` and finalized `DayPlan` preserve `day_start_time` and `timeline_order`.

- [ ] **Step 2: Verify tests fail**

Run focused schema, draft endpoint, and finalize tests.

- [ ] **Step 3: Implement time fields and persistence**

Apply precedence of day override over request default over system default. Preserve timeline order in final DayPlan output.

- [ ] **Step 4: Verify backend timeline tests pass**

Run the focused backend suites.

### Task 4: Update Draft And Result Timeline UI

**Files:**
- Modify: `frontend/src/types/index.ts`
- Modify request form/API payload surfaces needed for default start time
- Modify: `frontend/src/components/draft/DayCard.vue`
- Modify: `frontend/src/views/DraftView.vue`
- Modify: `frontend/src/components/DayTimeline.vue`

- [ ] **Step 1: Add frontend types and payload fields**

Expose request default day start time, day override time, and timeline order to TypeScript.

- [ ] **Step 2: Add Draft single-day start-time control**

Show current effective day start time in DayCard and emit a recompute/save mutation when changed.

- [ ] **Step 3: Render Result timeline from saved order when available**

Use `timeline_order` to include user-added `main` and other dining categories, while keeping old TripPlan fallback generation.

- [ ] **Step 4: Remove fixed result start anchor**

Use the saved effective start time for timeline calculations, with a system default when older data has none.

### Task 5: Verify

- [ ] **Step 1: Run focused backend tests**

Include hotel parsing/service tests, route tests, schema/draft/finalize tests, and affected existing suites.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Browser verification**

Check:

- AIGoHotel-backed result hotel cards can show restored price and booking link for fresh generated data.
- short route segments do not show raw no-transit objects.
- user-added meal categories appear in result timeline.
- request default start time and draft per-day override alter result timeline starts.
