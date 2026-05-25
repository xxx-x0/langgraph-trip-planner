# Location Assignment Meals Hotel Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make smart assignment visibly geography-first, separate Draft meal editing from attraction rows, and make Result hotel cards resilient to incomplete external hotel data.

**Architecture:** Keep the Discover preview API as the source of assignment behavior and tighten its duration rebalance guard in the geo utility so proximity remains the primary grouping rule. Keep Draft meal mutations on the existing recompute API while changing the DayCard/AddDiningPopover presentation surface. Normalize hotel descriptions at the AIGoHotel parser boundary and make the HotelCard degrade gracefully when image or price fields are absent.

**Tech Stack:** Python, FastAPI, pytest, Vue 3, TypeScript, Ant Design Vue, Vite.

---

## File Map

- Modify `backend/tests/agents/utils/test_geo_rebalance.py` to pin geography-first duration rebalance behavior.
- Modify `backend/app/agents/langgraph_agent/utils/geo.py` to reject duration moves that would send an attraction to a geographically poor target cluster.
- Modify `backend/tests/agents/test_search_hotels_by_day.py` or add focused parser coverage for hotel field normalization.
- Modify `backend/app/agents/langgraph_agent/nodes/search.py` to clean hotel descriptions and preserve real price parsing only.
- Modify `frontend/src/components/draft/DayCard.vue` to split attraction and meal sections and show localized meal labels.
- Modify `frontend/src/components/draft/AddDiningPopover.vue` so a day-level add control can add meals without a per-attraction anchor.
- Modify `frontend/src/components/HotelCard.vue` to collapse failed/missing images and show price fallback text.

### Task 1: Guard Geography-First Smart Assignment

**Files:**
- Modify: `backend/tests/agents/utils/test_geo_rebalance.py`
- Modify: `backend/app/agents/langgraph_agent/utils/geo.py`

- [ ] **Step 1: Write the failing geo rebalance test**

Add a test with a dense source cluster and a far-away target cluster. Assert the dense cluster is kept together even when its duration exceeds 8 hours and moving one attraction would make totals look better.

- [ ] **Step 2: Verify the new test fails**

Run:

```bash
cd backend && pytest tests/agents/utils/test_geo_rebalance.py -q
```

Expected: the new geography-first test fails because `_rebalance_by_duration` currently scores duration and distance without a maximum distance guard.

- [ ] **Step 3: Implement the smallest geo guard**

Add a proximity threshold or equivalent source-vs-target distance check in `_rebalance_by_duration` so a moved attraction must be meaningfully closer to the target cluster than an obviously remote cluster.

- [ ] **Step 4: Verify the geo suite passes**

Run the same pytest command and confirm all geo rebalance tests pass.

### Task 2: Normalize Hotel Parser Output

**Files:**
- Test: focused hotel parser coverage under `backend/tests/agents/`
- Modify: `backend/app/agents/langgraph_agent/nodes/search.py`

- [ ] **Step 1: Write failing parser tests**

Cover:

```python
def test_parse_aigohotel_hotels_strips_description_markup():
    hotels = _parse_aigohotel_hotels({
        "hotels": [{
            "name": "海景酒店",
            "description": "<p><b>酒店简介</b><br/>步行可到海边</p>",
        }]
    })
    assert hotels[0]["description"] == "酒店简介 步行可到海边"
```

and a numeric price case that proves the parser exposes a real `price` value when the provider returns one.

- [ ] **Step 2: Verify the parser tests fail**

Run the focused test file with pytest and confirm the markup assertion fails against the current raw description.

- [ ] **Step 3: Implement parser normalization**

Use standard-library HTML parsing or a focused helper to strip tags and normalize whitespace before truncating the hotel description. Keep numeric price parsing from existing supported provider keys.

- [ ] **Step 4: Verify focused parser tests pass**

Run the focused parser tests again.

### Task 3: Separate Draft Meals From Attraction Rows

**Files:**
- Modify: `frontend/src/components/draft/DayCard.vue`
- Modify: `frontend/src/components/draft/AddDiningPopover.vue`

- [ ] **Step 1: Change the AddDiningPopover API**

Make `insertAfter` optional and only include `insert_after` in emitted meal payloads when an anchor exists.

- [ ] **Step 2: Split DayCard layout**

Create distinct `景点安排` and `用餐安排` sections. Remove the per-attraction AddDiningPopover from draggable rows and place one add control in the meal section header.

- [ ] **Step 3: Localize meal labels**

Add a small label mapper in DayCard so internal category/type values render as user-facing Chinese labels, including `main -> 正餐`.

- [ ] **Step 4: Keep recompute payloads compatible**

Continue sending current meal records during recompute. Preserve existing `insert_after` values when present and let the backend defaulting path handle new unanchored meals.

### Task 4: Make HotelCard Degrade Gracefully

**Files:**
- Modify: `frontend/src/components/HotelCard.vue`

- [ ] **Step 1: Remove generated image placeholders**

Render the image wrapper only when a provider image exists and has not failed. On `@error`, mark image rendering failed and collapse the wrapper.

- [ ] **Step 2: Add explicit price fallback**

Keep current `price`, `price_range`, and `estimated_cost` display order. Show `价格待确认` when none exist.

- [ ] **Step 3: Keep description display plain and bounded**

Render the normalized description text from the parser and retain the existing expand/collapse behavior for long descriptions.

### Task 5: Verify The Affected Flows

**Files:**
- Verification only

- [ ] **Step 1: Run focused backend tests**

```bash
cd backend && pytest tests/agents/utils/test_geo_rebalance.py tests/api/test_preview_day_assignment.py -q
```

Also run the focused hotel parser test file added in Task 2.

- [ ] **Step 2: Run frontend build**

```bash
cd frontend && npm run build
```

- [ ] **Step 3: Start local frontend if needed**

Use the existing dev server when available, or start `npm run dev` for the frontend and verify the known local pages.

- [ ] **Step 4: Browser verification**

Check:

- Discover day assignment still shows day columns and preserves nearby Sanya attractions together.
- Draft day card has one day-level meal add area, no per-attraction meal add buttons, and user-facing meal labels.
- Result hotel card with missing/broken image has no failure banner, shows cleaned description text, and shows the price fallback when no amount exists.
