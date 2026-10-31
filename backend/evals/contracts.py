"""Versioned, offline-only contracts; no database, SDK client or model initialization."""
import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = 'trip-eval-v1'
EVALUATOR_VERSION = 'rules-v1.1'
RULES = ('T-VALID T-ELIG T-FACT T-MARGIN T-RANK T-DISCLOSE T-OUTCOME '
         'R-LOCK R-REMOVED R-MANUAL R-MEAL R-FACT R-DURATION R-REST R-WINDOW '
         'R-INTENT R-ROUTE R-DISCLOSE S-PERSIST S-TRACE J-INTENT J-TRADEOFF').split()
HARD_RULES = set(RULES)-{'T-RANK','R-INTENT','R-ROUTE','S-TRACE','J-INTENT','J-TRADEOFF'}
REFERENCE_RULES = {'T-ELIG','T-MARGIN','T-RANK','R-WINDOW','R-INTENT','R-ROUTE'}
Status = Literal['PASS','FAIL','ERROR','NOT_APPLICABLE','NOT_EVALUATED']
Layer = Literal['model','system','observability','judge']


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Assertion(Strict):
    rule_id: str
    layer: Layer
    applicable: bool
    reason: str
    evaluator_version: str = EVALUATOR_VERSION

    @model_validator(mode='after')
    def known(self):
        if self.rule_id not in RULES:
            raise ValueError('unknown rule')
        if self.evaluator_version!=EVALUATOR_VERSION:
            raise ValueError('unsupported evaluator version')
        return self


class Annotation(Strict):
    status: Literal['pending_human','confirmed','disputed'] = 'pending_human'
    author_kind: Literal['agent_draft','human'] = 'agent_draft'
    reviewer: str | None = None
    reviewed_at: str | None = None
    confirmed_reference_sha256: str | None = None
    pending_items: list[str]
    rationale: str

    @model_validator(mode='after')
    def confirmation(self):
        if self.status=='confirmed' and (not self.reviewer or not self.reviewed_at or
            not self.confirmed_reference_sha256 or self.pending_items):
            raise ValueError('confirmation requires named human, date, exact reference hash and no pending items')
        return self


class Case(Strict):
    schema_version: Literal['trip-eval-v1'] = SCHEMA_VERSION
    case_id: str = Field(pattern=r'^(T(0[1-9]|1[0-8])|R(0[1-9]|1[0-2]))$')
    case_version: str
    title: str
    target: Literal['ticket_recommendation','day_rearrangement']
    split: Literal['dev','holdout']
    family: str
    execution_mode: Literal['live_model_with_replay','injected_failure','no_model']
    tool_mode: Literal['replay'] = 'replay'
    data_origin: Literal['synthetic','mixed_historical_itinerary_and_new_capture','mixed_historical_day_and_new_route_capture']
    sources: list[dict[str, Any]]
    clock: str
    random_seed: int
    input_path: str
    reference_path: str
    route_path: str | None = None
    input_sha256: str
    reference_sha256: str
    route_sha256: str | None = None
    expected_assertions: list[Assertion]
    annotation: Annotation
    limitations: list[str]

    @model_validator(mode='after')
    def invariants(self):
        pairs=[(a.rule_id,a.layer) for a in self.expected_assertions]
        if len(pairs)!=len(set(pairs)):
            raise ValueError('duplicate assertion')
        if self.annotation.status=='confirmed' and self.annotation.confirmed_reference_sha256!=self.reference_sha256:
            raise ValueError('reference changed since human confirmation')
        if self.case_id.startswith('T') != (self.target=='ticket_recommendation'):
            raise ValueError('case target mismatch')
        return self


class Observation(Strict):
    """Evidence collected by a future isolated runner; never filled from the reference.

    Missing evidence stays None. Do not fill missing lists/hashes with empty success values.
    final_output is the native ticket response or native DayDetail. raw_model is the
    uncorrected parsed model suggestion. before/latest/after are captured saved JSON.
    """
    schema_version: Literal['trip-eval-v1'] = SCHEMA_VERSION
    case_id: str
    case_version: str
    input_sha256: str
    run_id: str
    trace_id: str | None = None
    experiment_id: str | None = None
    repetition: int = Field(default=1,ge=1)
    usage: dict[str, Any] | None = None
    timings: dict[str, float] | None = None
    execution_status: Literal['success','error','timeout','cancelled','conflict','rejected']
    http_status: int | None = None
    business_outcome: str | None = None
    raw_model: dict[str, Any] | None = None
    model_status: Literal['success','error','timeout','cancelled','not_called'] | None = None
    final_output: dict[str, Any] | None = None
    eligible_ids: list[str] | None = None
    candidate_checks: list[dict[str, Any]] | None = None
    before_state: dict[str, Any] | None = None
    latest_state: dict[str, Any] | None = None
    after_state: dict[str, Any] | None = None
    checkpoint_statuses: dict[str, int] | None = None
    trace: dict[str, Any] | None = None
    actual_model_calls: int | None = Field(default=None,ge=0)
    external_calls_after_cancel: int | None = Field(default=None,ge=0)
    recovery_count: int | None = Field(default=None,ge=0)
    route_deadline_seconds: float | None = None
    judge: dict[str, Any] | None = None
    provenance: Literal['live_model_with_replay','injected_failure','no_model','scorer_selftest','baseline','replay_model']


class Check(Strict):
    rule_id: str
    layer: Layer
    status: Status
    score: float | None
    expected: Any = None
    actual: Any = None
    evidence_paths: list[str] = Field(default_factory=list)
    reason: str
    evaluator_version: str = EVALUATOR_VERSION
    reference_status: str
    provisional: bool


class JudgeCalibration(Strict):
    """Trusted operator-supplied review record, never part of an LLM response."""
    reviewer: str = Field(min_length=1)
    reviewed_at: str
    sample_count: Literal[12]
    human_agreement: int = Field(ge=10,le=12)
    repeat_agreement: int = Field(ge=10,le=12)
    judge_version: str
    evidence_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
