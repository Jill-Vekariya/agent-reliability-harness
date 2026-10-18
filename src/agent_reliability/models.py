"""Versioned contracts; evaluator fields never enter TaskInput."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Limits(Model):
    wall_seconds: float = Field(default=2.0, gt=0, le=30)
    cpu_seconds: int = Field(default=2, ge=1, le=30)
    memory_mb: int = Field(default=192, ge=64, le=1024)
    max_rows: int = Field(default=100, ge=1, le=1000)
    max_cell_bytes: int = Field(default=4096, ge=1, le=65536)
    max_output_bytes: int = Field(default=65536, ge=1024, le=1048576)
    max_sql_bytes: int = Field(default=16384, ge=64, le=65536)
    max_value_bytes: int = Field(default=131072, ge=1024, le=1048576)
    max_vm_steps: int = Field(default=500000, ge=100, le=10000000)
    max_steps: int = Field(default=12, ge=1, le=50)


class TaskInput(Model):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    question: str
    context: str = ""


class EvaluationTask(Model):
    schema_version: int = 1
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    question: str
    difficulty: Literal["easy", "medium", "hard"]
    category: Literal["ordinary", "injection", "prohibited", "resource", "clarification"]
    split: Literal["dev", "test"] = "dev"
    tags: list[str] = Field(default_factory=list)
    family_id: str = Field(min_length=1, max_length=128)
    database_fixture_id: str = "chinook-v1.4.5"
    dataset_version: str = "candidate-0.1"
    gold_sql: str | None = None
    expected_columns: list[str] = Field(default_factory=list)
    expected_result: list[list[Any]] | None = None
    expected_behavior: Literal["answer", "refuse", "clarify", "resource_limit"] = "answer"
    ordered: bool = False
    column_names_matter: bool = False
    atol: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    rtol: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    tolerant_columns: list[int] = Field(default_factory=list)
    tie_policy: str = "not applicable"
    source: str = "AI-assisted original Chinook question; not Spider-adapted"
    adaptation_notes: str = "Not adapted"
    authoring_method: str = "AI-assisted"
    reviewer: str | None = None
    review_status: Literal["candidate", "human_reviewed"] = "candidate"
    assertions: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_task(self) -> "EvaluationTask":
        if self.schema_version != 1:
            raise ValueError("Unsupported task schema version")
        if self.review_status == "human_reviewed" and not self.reviewer:
            raise ValueError("Human-reviewed tasks require an actual reviewer")
        if self.expected_behavior == "answer" and not self.gold_sql:
            raise ValueError("Answer tasks require gold SQL")
        if self.category == "ordinary" and self.expected_behavior != "answer":
            raise ValueError("Ordinary accuracy is reserved for answer tasks")
        if not self.question.strip():
            raise ValueError("Question must not be empty")
        if self.expected_behavior == "answer" and (
            self.expected_result is None or not self.expected_columns
        ):
            raise ValueError("Answer tasks require explicit expected rows and columns")
        if self.expected_result is not None and any(
            len(row) != len(self.expected_columns) for row in self.expected_result
        ):
            raise ValueError("Expected row width must match column policy")
        if len(set(self.tolerant_columns)) != len(self.tolerant_columns) or any(
            type(index) is not int or not 0 <= index < len(self.expected_columns)
            for index in self.tolerant_columns
        ):
            raise ValueError("Invalid numeric-tolerance column")
        return self

    def agent_input(self) -> TaskInput:
        return TaskInput(id=self.id, question=self.question)


class SQLResult(Model):
    ok: bool
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    truncated: bool = False
    error: str | None = None
    error_kind: str | None = None
    blocked: bool = False
    resource_limited: bool = False


class ToolCall(Model):
    name: str
    arguments: dict[str, Any]


class ProviderReply(Model):
    calls: list[ToolCall] = Field(default_factory=list)
    content: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cached_input_tokens: int | None = None
    model: str = "synthetic-fixture-v1"
    finish_reason: str = "tool_calls"
    cost_usd: str | None = None


class Event(Model):
    schema_version: int = 1
    index: int
    kind: Literal["model", "tool", "termination"]
    payload: dict[str, Any]
    timestamp: str
    latency_ms: float = Field(default=0.0, ge=0, allow_inf_nan=False)


class Trace(Model):
    schema_version: int = 1
    task_id: str
    attempt_id: str
    mode: Literal["fixture", "record", "replay", "regression"]
    origin: Literal["synthetic", "live"]
    config: str
    events: list[Event] = Field(default_factory=list)
    results: dict[str, SQLResult] = Field(default_factory=dict)
    final: dict[str, Any] | None = None
    termination: str = "incomplete"
    latency_ms: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    cost_usd: str | None = None
    infrastructure_error: str | None = None


class Grade(Model):
    correct: bool = False
    completed: bool = False
    behavior_passed: bool = False
    unsafe_attempt: bool = False
    prohibited_executed: bool = False
    reason: str
    failure_category: str | None = None
