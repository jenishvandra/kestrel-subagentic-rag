"""Shared structured-output schemas for subagents and the supervisor."""

from typing import Literal, Optional
from pydantic import BaseModel, Field

Department = Literal["hr", "it", "finance"]


class Finding(BaseModel):
    """One rule found by a subagent, always traceable to a specific clause."""
    rule: str = Field(..., description="The rule in plain words.")
    section: str = Field(..., description="Clause/section number, e.g. '6.4'.")
    page: int = Field(..., description="Page number in the source PDF.")
    doc_id: str = Field(..., description="Document ID, e.g. 'KSPL-FIN-POL-003'.")
    version: str = Field(..., description="Document version, e.g. '3.0'.")
    effective_date: str = Field(..., description="Effective date, ISO format.")


class SubagentResult(BaseModel):
    """Fixed output format every subagent must return (Phase 3)."""
    department: Department
    covered: bool = Field(..., description="True if at least one relevant rule was found.")
    findings: list[Finding] = Field(default_factory=list)
    gaps: list[str] = Field(
        default_factory=list,
        description="Parts of the task this department's documents do not answer.",
    )


class SupervisorPlanItem(BaseModel):
    department: Department
    task_message: str = Field(
        ..., description="A complete, standalone task message for this department's subagent."
    )


class SupervisorPlan(BaseModel):
    departments: list[Department] = Field(default_factory=list)
    plan_items: list[SupervisorPlanItem] = Field(default_factory=list)
    reason: str = Field(..., description="One-line reason for the routing decision.")


class EmployeeProfile(BaseModel):
    name: Optional[str] = None
    grade: Optional[str] = Field(None, description="G1 to G7")
    office: Optional[str] = Field(None, description="Pune, Mumbai or Bengaluru")
    joining_date: Optional[str] = None
    current_city: Optional[str] = Field(
        None, description="City relevant to the question, if different from office, e.g. for travel."
    )
