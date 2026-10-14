"""FastAPI route handlers for ReVolt platform."""

from datetime import UTC, datetime
from typing import Annotated, Any
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from src.packages.revolt.models import (
    Battery,
    BatteryChemistry,
    BatteryCreate,
    BatteryUpdate,
    Facility,
    FieldSource,
    ImpactAnalytics,
    LifecycleStatus,
    RecommendedPathway,
    ScheduleBookingCreate,
    TelemetryInjectionPayload,
)
from src.packages.revolt.ocr import LABEL_PRESETS, parse_battery_label_text
from src.packages.revolt.storage import revolt_repo

router = APIRouter(prefix="/api/v1/revolt", tags=["ReVolt Platform"])


class StatusUpdatePayload(BaseModel):
    status: LifecycleStatus
    note: str = ""
    actor: str = "User"


class SmartScanParseRequest(BaseModel):
    raw_text: str


@router.get("/overview", summary="Executive overview telemetry and safety alerts")
async def get_overview() -> dict[str, Any]:
    """Provides high-level dashboard KPIs, circular pathway distribution, and safety quarantine alerts."""
    analytics = revolt_repo.get_analytics()
    all_batteries = revolt_repo.get_all_batteries()

    # Find any active hazardous quarantined batteries for the safety banner.
    # Exclude units that have already reached terminal/COMPLETED lifecycle status (neutralized/processed).
    hazardous_batteries: list[dict[str, Any]] = []
    for b in all_batteries:
        if b.recommended_pathway == RecommendedPathway.HAZARDOUS and b.status != LifecycleStatus.COMPLETED:
            is_sim = (
                b.provenance.measured_voltage == FieldSource.SIMULATED
                or b.provenance.physical_condition == FieldSource.SIMULATED
                or b.provenance.measured_capacity == FieldSource.SIMULATED
            )
            hazardous_batteries.append(
                {
                    "id": b.id,
                    "name": b.name,
                    "chemistry": b.chemistry.value,
                    "status": b.status.value,
                    "warnings": b.assessment.safety_warnings if b.assessment else ["Physical or electrical hazard"],
                    "registered_at": b.registered_at.isoformat(),
                    "is_simulated": is_sim,
                    "is_demo_data": getattr(b, "is_demo_data", False),
                    "measured_voltage_v": b.measured_voltage_v,
                    "physical_condition": b.physical_condition.value,
                    "provenance": {
                        "measured_voltage": b.provenance.measured_voltage.value,
                        "physical_condition": b.provenance.physical_condition.value,
                        "measured_capacity": b.provenance.measured_capacity.value,
                    },
                }
            )

    # Prioritize genuine physical warehouse hazards first (newest first), followed by simulated virtual test bench hazards (newest first)
    hazardous_batteries.sort(
        key=lambda x: (
            1 if x["is_simulated"] else 0,
            -datetime.fromisoformat(x["registered_at"]).timestamp(),
        )
    )

    genuine_count = sum(1 for b in hazardous_batteries if not b["is_simulated"])
    simulated_count = sum(1 for b in hazardous_batteries if b["is_simulated"])

    # Recent activities flattened from timelines
    recent_activities: list[dict[str, Any]] = []
    for b in all_batteries:
        for ev in b.timeline:
            recent_activities.append(
                {
                    "battery_id": b.id,
                    "battery_name": b.name,
                    "event_id": ev.id,
                    "timestamp": ev.timestamp.isoformat(),
                    "status": ev.status.value,
                    "title": ev.title,
                    "description": ev.description,
                    "actor": ev.actor,
                }
            )
    recent_activities.sort(key=lambda x: x["timestamp"], reverse=True)
    recent_activities = recent_activities[:12]

    return {
        "kpis": {
            "total_registered": analytics.total_registered,
            "total_assessed": analytics.total_assessed,
            "awaiting_collection": analytics.total_awaiting_collection,
            "in_transit": analytics.total_in_transit,
            "completed": analytics.total_completed,
            "pending_verification": analytics.total_awaiting_verification,
            "landfill_diversion_kg": analytics.estimated_landfill_diversion_kg,
            "co2_avoided_kg": analytics.estimated_co2_avoided_kg,
        },
        "pathway_distribution": {
            "reuse": analytics.reused_count,
            "refurbish": analytics.refurbished_count,
            "recycle": analytics.recycled_count,
            "hazardous": analytics.hazardous_count,
            "pending": analytics.pending_count,
        },
        "safety_alert": {
            "has_critical_hazards": len(hazardous_batteries) > 0,
            "quarantined_count": len(hazardous_batteries),
            "genuine_count": genuine_count,
            "simulated_count": simulated_count,
            "is_simulated": hazardous_batteries[0]["is_simulated"] if hazardous_batteries else False,
            "quarantined_batteries": hazardous_batteries,
        },
        "recent_activities": recent_activities,
    }


@router.get("/batteries", response_model=list[Battery], summary="List registered batteries")
async def list_batteries(
    search: Annotated[str | None, Query(description="Search by ID, name, or chemistry")] = None,
    pathway: Annotated[RecommendedPathway | None, Query(description="Filter by recommended pathway")] = None,
    chemistry: Annotated[BatteryChemistry | None, Query(description="Filter by battery chemistry")] = None,
    lifecycle_status: Annotated[LifecycleStatus | None, Query(alias="status", description="Filter by status")] = None,
) -> list[Battery]:
    """Retrieves all registered batteries matching filter criteria."""
    return revolt_repo.get_all_batteries(
        search=search,
        pathway=pathway,
        chemistry=chemistry,
        status=lifecycle_status,
    )


@router.post(
    "/batteries",
    response_model=Battery,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new battery asset",
)
async def create_battery(payload: BatteryCreate) -> Battery:
    """Registers a new spent battery into the ReVolt circular lifecycle pipeline."""
    return revolt_repo.create_battery(payload)


@router.get("/batteries/{battery_id}", response_model=Battery, summary="Retrieve battery passport")
async def get_battery(battery_id: str) -> Battery:
    """Retrieves complete battery record, explainable assessment, and audit timeline."""
    b = revolt_repo.get_battery(battery_id)
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battery '{battery_id}' not found",
        )
    return b


@router.patch("/batteries/{battery_id}", response_model=Battery, summary="Update battery parameters")
async def update_battery(battery_id: str, payload: BatteryUpdate) -> Battery:
    """Updates battery condition, telemetry measurements, or notes."""
    b = revolt_repo.update_battery(battery_id, payload)
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battery '{battery_id}' not found",
        )
    return b


@router.post("/batteries/{battery_id}/assess", response_model=Battery, summary="Run AI assessment engine")
async def assess_battery_endpoint(battery_id: str) -> Battery:
    """Invokes deterministic rule evaluation against battery telemetry and conditions."""
    b = revolt_repo.assess_battery_record(battery_id)
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battery '{battery_id}' not found",
        )
    return b


@router.post("/batteries/{battery_id}/telemetry", response_model=Battery, summary="Inject Mock Telemetry Lab bench test")
async def inject_telemetry_endpoint(battery_id: str, payload: TelemetryInjectionPayload) -> Battery:
    """Applies lab bench multimeter/cycler measurements to a battery and runs assessment."""
    b = revolt_repo.inject_telemetry(battery_id, payload)
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battery '{battery_id}' not found",
        )
    return b


@router.get(
    "/batteries/{battery_id}/transitions",
    response_model=list[LifecycleStatus],
    summary="Get valid next lifecycle transitions",
)
async def get_battery_transitions(battery_id: str) -> list[LifecycleStatus]:
    """Retrieves allowed next lifecycle statuses for a battery based on state-machine and safety rules."""
    b = revolt_repo.get_battery(battery_id)
    if not b:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Battery '{battery_id}' not found",
        )
    return revolt_repo.get_valid_transitions(battery_id)


@router.patch("/batteries/{battery_id}/status", response_model=Battery, summary="Advance lifecycle status")
@router.post("/batteries/{battery_id}/status", response_model=Battery, summary="Advance lifecycle status")
async def update_battery_status(battery_id: str, payload: StatusUpdatePayload) -> Battery:
    """Transitions battery lifecycle state enforcing state-machine business rules."""
    try:
        b = revolt_repo.update_status(
            battery_id=battery_id,
            new_status=payload.status,
            note=payload.note,
            actor=payload.actor,
        )
        if not b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Battery '{battery_id}' not found",
            )
        return b
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.post("/batteries/{battery_id}/schedule", response_model=Battery, summary="Schedule simulated logistics")
async def schedule_logistics(battery_id: str, payload: ScheduleBookingCreate) -> Battery:
    """Books simulated collection or drop-off with an authorized facility."""
    try:
        b = revolt_repo.schedule_booking(battery_id, payload)
        if not b:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Battery '{battery_id}' not found",
            )
        return b
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


@router.get("/facilities", response_model=list[Facility], summary="List authorized processing facilities")
async def list_facilities(
    pathway: Annotated[RecommendedPathway | None, Query(description="Filter by supported circular pathway")] = None,
    chemistry: Annotated[BatteryChemistry | None, Query(description="Filter by supported chemistry")] = None,
    query: Annotated[str | None, Query(description="Search facilities by name, city, or capability")] = None,
) -> list[Facility]:
    """Retrieves directory of certified recyclers, refurbishers, and hazmat quarantine depots."""
    return revolt_repo.get_facilities(pathway=pathway, chemistry=chemistry, query=query)


@router.get("/analytics", response_model=ImpactAnalytics, summary="Circular impact metrics")
async def get_impact_analytics() -> ImpactAnalytics:
    """Returns real-time carbon avoidance, critical minerals recovery, and diversion statistics."""
    return revolt_repo.get_analytics()


@router.get("/smartscan/presets", summary="Get industrial label presets for SmartScan")
async def get_smartscan_presets() -> dict[str, Any]:
    """Returns realistic commercial presets for rapid OCR demonstration."""
    return LABEL_PRESETS


@router.post("/smartscan/parse", summary="Parse label text via SmartScan OCR engine")
async def parse_smartscan_text(payload: SmartScanParseRequest) -> dict[str, Any]:
    """Extracts battery specifications, voltage, capacity, and field provenance from label text."""
    return parse_battery_label_text(payload.raw_text)
