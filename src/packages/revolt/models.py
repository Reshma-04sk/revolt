"""Domain models and schemas for ReVolt Battery Management Platform.

Includes SmartScan provenance tracking, explainable assessment results,
and circular economy lifecycle models.
"""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class BatteryChemistry(StrEnum):
    NMC = "NMC"  # Nickel Manganese Cobalt (3.6-3.7V nom)
    LFP = "LFP"  # Lithium Iron Phosphate (3.2V nom)
    LCO = "LCO"  # Lithium Cobalt Oxide (3.7V nom)
    LMO = "LMO"  # Lithium Manganese Oxide (3.7V nom)
    NCA = "NCA"  # Nickel Cobalt Aluminum (3.6V nom)
    OTHER = "OTHER"


class OriginalApplication(StrEnum):
    EV = "EV"  # Electric Vehicle / Light EV
    LAPTOP = "LAPTOP"  # Laptop / Tablet
    SMARTPHONE = "SMARTPHONE"  # Mobile Phone
    POWER_BANK = "POWER_BANK"  # Portable Power Bank
    POWER_TOOL = "POWER_TOOL"  # Cordless Drill / Power Tool
    ESS = "ESS"  # Energy Storage System / Solar Backup
    ENERGY_STORAGE = "ENERGY_STORAGE"  # Energy Storage System alias
    OTHER = "OTHER"


class PhysicalCondition(StrEnum):
    GOOD = "GOOD"  # Clean, no swelling, no corrosion
    SCRATCHED = "SCRATCHED"  # Minor surface marks, intact casing
    SWOLLEN_MILD = "SWOLLEN_MILD"  # Slight puffing, warning sign
    SWOLLEN_SEVERE = "SWOLLEN_SEVERE"  # Significant bulging - CRITICAL RED FLAG
    PUNCTURED_CRACKED = "PUNCTURED_CRACKED"  # Breached envelope - CRITICAL RED FLAG
    LEAKING = "LEAKING"  # Fluid or strong chemical odor - CRITICAL RED FLAG
    CORRODED_TERMINALS = "CORRODED_TERMINALS"  # Heavy terminal oxidation
    THERMAL_RESIDUE = "THERMAL_RESIDUE"  # Scorching, melted wrap - CRITICAL RED FLAG


class TemperatureHistory(StrEnum):
    NORMAL = "NORMAL"  # Operated within normal ranges (< 45°C)
    ELEVATED = "ELEVATED"  # Periodic warmth (45°C - 55°C)
    OVERHEATED = "OVERHEATED"  # Known high-temp events (> 60°C)
    EXTREME = "EXTREME"  # Thermal runaway or fire event - CRITICAL RED FLAG
    UNKNOWN = "UNKNOWN"  # No telemetry available


class RecommendedPathway(StrEnum):
    REUSE = "REUSE"  # Second-life stationary storage or light-duty use
    REFURBISH = "REFURBISH"  # Cell-level balancing, repackaging, or BMS repair
    RECYCLE = "RECYCLE"  # Hydrometallurgical material recovery (Li, Co, Ni)
    HAZARDOUS = "HAZARDOUS"  # Immediate quarantine & specialist hazmat handling
    PENDING_VERIFICATION = "PENDING_VERIFICATION"  # Missing critical measurements
    PENDING = "PENDING"  # Awaiting initial assessment


class LifecycleStatus(StrEnum):
    REGISTERED = "REGISTERED"
    ASSESSED = "ASSESSED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    AWAITING_COLLECTION = "AWAITING_COLLECTION"
    IN_TRANSIT = "IN_TRANSIT"
    RECEIVED_AT_FACILITY = "RECEIVED_AT_FACILITY"
    ROUTED_FOR_PROCESSING = "ROUTED_FOR_PROCESSING"
    PROCESSING = "PROCESSING"
    REUSED = "REUSED"
    REFURBISHED = "REFURBISHED"
    RECYCLED = "RECYCLED"
    SPECIALIST_HANDLING = "SPECIALIST_HANDLING"
    COMPLETED = "COMPLETED"


class LogisticsType(StrEnum):
    HAZMAT_PICKUP = "HAZMAT_PICKUP"
    STANDARD_PICKUP = "STANDARD_PICKUP"
    DEPOT_DROP_OFF = "DEPOT_DROP_OFF"


class FieldSource(StrEnum):
    USER_ENTERED = "USER_ENTERED"
    OCR_EXTRACTED = "OCR_EXTRACTED"
    VERIFIED_SPEC = "VERIFIED_SPEC"
    TECHNICIAN_MEASURED = "TECHNICIAN_MEASURED"
    SIMULATED = "SIMULATED"
    UNKNOWN = "UNKNOWN"


class FieldProvenance(BaseModel):
    rated_capacity: FieldSource = FieldSource.USER_ENTERED
    measured_capacity: FieldSource = FieldSource.UNKNOWN
    nominal_voltage: FieldSource = FieldSource.USER_ENTERED
    measured_voltage: FieldSource = FieldSource.UNKNOWN
    model_identity: FieldSource = FieldSource.USER_ENTERED
    chemistry: FieldSource = FieldSource.USER_ENTERED
    cycle_count: FieldSource = FieldSource.UNKNOWN
    physical_condition: FieldSource = FieldSource.USER_ENTERED


class TimelineEvent(BaseModel):
    id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: LifecycleStatus
    title: str
    description: str
    actor: str = "System"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssessmentResult(BaseModel):
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    pathway: RecommendedPathway
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Calibrated safety confidence reflecting epistemic certainty (not mere form completeness)",
    )
    confidence_basis: str = Field(
        default="",
        description="Calibrated rationale and evidentiary basis for the safety confidence score",
    )
    data_completeness_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Telemetry completeness metric (distinguished from safety confidence)",
    )
    soh_percentage: float | None = Field(
        default=None,
        description="Calculated State of Health (remaining/rated capacity * 100)",
    )
    is_hazardous: bool = False
    safety_warnings: list[str] = Field(default_factory=list)
    contributing_factors: list[str] = Field(default_factory=list)
    recommended_next_steps: list[str] = Field(default_factory=list)
    missing_telemetry: list[str] = Field(default_factory=list)
    requires_lab_verification: bool = False
    engine_version: str = "ReVolt-Deterministic-Rules-v1.3"
    disclaimer: str = (
        "Prototype assessment engine — explainable deterministic rule evaluation. "
        "Not a certified laboratory safety determination. Hazardous batteries require "
        "immediate physical quarantine."
    )


class BatteryBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100, description="Battery label or asset ID")
    device_model: str = Field(
        default="", max_length=100, description="OEM device model or cell part number"
    )
    chemistry: BatteryChemistry
    original_application: OriginalApplication
    age_months: int = Field(..., ge=0, le=360, description="Estimated age in months")
    rated_capacity_mah: float = Field(
        ..., gt=0, description="Original factory rated capacity in mAh"
    )
    measured_capacity_mah: float | None = Field(
        default=None,
        ge=0,
        description="Measured remaining capacity in mAh",
    )
    nominal_voltage_v: float = Field(..., gt=0, le=1000, description="Nominal voltage in Volts")
    measured_voltage_v: float | None = Field(
        default=None,
        ge=0,
        le=1000,
        description="Measured open-circuit voltage in Volts",
    )
    cycle_count: int | None = Field(
        default=None,
        ge=0,
        le=20000,
        description="Charge-discharge cycle count if recorded",
    )
    temperature_history: TemperatureHistory = TemperatureHistory.UNKNOWN
    physical_condition: PhysicalCondition = PhysicalCondition.GOOD
    owner_notes: str = Field(default="", max_length=1000)
    photo_data_url: str | None = Field(
        default=None,
        description="Base64 or URL preview of battery photo or label",
    )
    provenance: FieldProvenance = Field(default_factory=FieldProvenance)
    data_completeness_pct: float = Field(
        default=50.0,
        ge=0.0,
        le=100.0,
        description="Data completeness index based on available fields (not a health score)",
    )
    ocr_raw_text: str | None = Field(
        default=None, description="Raw text detected by OCR engine if scanned"
    )
    ocr_detected_fields: dict[str, Any] = Field(
        default_factory=dict, description="Parsed fields extracted from label image"
    )

    @model_validator(mode="after")
    def validate_field_provenance(self) -> "BatteryBase":
        """Reconciles field values with provenance.

        Positive measurements default to USER_ENTERED if unspecified.
        Default 0.0 values remain UNKNOWN unless explicitly marked as measured.
        """
        if self.measured_voltage_v is not None and self.measured_voltage_v > 0 and self.provenance.measured_voltage == FieldSource.UNKNOWN:
            self.provenance.measured_voltage = FieldSource.USER_ENTERED
        if self.measured_capacity_mah is not None and self.measured_capacity_mah > 0 and self.provenance.measured_capacity == FieldSource.UNKNOWN:
            self.provenance.measured_capacity = FieldSource.USER_ENTERED
        if self.cycle_count is not None and self.cycle_count > 0 and self.provenance.cycle_count == FieldSource.UNKNOWN:
            self.provenance.cycle_count = FieldSource.USER_ENTERED
        return self


class BatteryCreate(BatteryBase):
    pass


class BatteryUpdate(BaseModel):
    name: str | None = None
    device_model: str | None = None
    physical_condition: PhysicalCondition | None = None
    measured_voltage_v: float | None = None
    measured_capacity_mah: float | None = None
    cycle_count: int | None = None
    temperature_history: TemperatureHistory | None = None
    owner_notes: str | None = None
    provenance: FieldProvenance | None = None


class TelemetryInjectionPayload(BaseModel):
    """Payload for Mock Telemetry Lab bench testing."""
    measured_voltage_v: float = Field(..., ge=0, le=1000, description="Measured pack open-circuit voltage")
    measured_capacity_mah: float = Field(..., ge=0, description="Discharge capacity measured in mAh")
    cycle_count: int | None = Field(default=None, ge=0, le=20000)
    internal_resistance_mohm: float | None = Field(default=None, ge=0, description="AC internal impedance in mOhm")
    temperature_history: TemperatureHistory = TemperatureHistory.NORMAL
    physical_condition: PhysicalCondition = PhysicalCondition.GOOD
    technician_notes: str = Field(default="", max_length=500)


class Facility(BaseModel):
    id: str
    name: str
    facility_type: str  # e.g., "Authorized Hydrometallurgical Recycler", "Certified Refurbisher"
    address: str
    city: str
    state: str
    latitude: float
    longitude: float
    phone: str
    email: str
    supported_pathways: list[RecommendedPathway]
    supported_chemistries: list[BatteryChemistry]
    services_offered: list[str]
    certifications: list[str]  # e.g., ["R2v3", "ISO 14001", "CPCB Authorized"]
    operating_hours: str = "Mon-Fri 08:00 - 18:00"
    is_demo_data: bool = True


class ScheduleBookingCreate(BaseModel):
    facility_id: str
    logistics_type: LogisticsType
    scheduled_date: str  # YYYY-MM-DD
    time_slot: str  # e.g., "09:00 - 12:00"
    pickup_address: str | None = None
    contact_name: str
    contact_phone: str
    special_instructions: str | None = None


class ScheduleBooking(ScheduleBookingCreate):
    booking_id: str
    booked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    facility_name: str
    is_simulated: bool = True


class Battery(BatteryBase):
    id: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    status: LifecycleStatus = LifecycleStatus.REGISTERED
    recommended_pathway: RecommendedPathway = RecommendedPathway.PENDING
    assessment: AssessmentResult | None = None
    assigned_facility_id: str | None = None
    assigned_facility_name: str | None = None
    booking: ScheduleBooking | None = None
    timeline: list[TimelineEvent] = Field(default_factory=list)
    is_demo_data: bool = False


class ImpactAnalytics(BaseModel):
    total_registered: int
    total_assessed: int
    total_awaiting_verification: int = 0
    total_awaiting_collection: int
    total_in_transit: int
    total_routed_for_processing: int = 0
    total_completed: int
    reused_count: int
    refurbished_count: int
    recycled_count: int
    hazardous_count: int
    specialist_handling_count: int = 0
    pending_count: int
    estimated_landfill_diversion_kg: float
    estimated_co2_avoided_kg: float
    estimated_lithium_carbonate_kg: float
    estimated_cobalt_kg: float
    estimated_nickel_kg: float
    methodology_note: str = (
        "Estimates calculated using standardized life-cycle assessment (LCA) coefficients: "
        "~73 kg CO2e avoided per kWh of second-life reuse; hydrometallurgical material yields "
        "derived from average elemental composition per chemistry. Demo dataset included."
    )
