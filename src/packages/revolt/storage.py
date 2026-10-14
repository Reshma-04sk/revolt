"""Persistence and repository layer for ReVolt platform.

Stores battery records, assessments, facilities, and simulated bookings.
Supports file-backed JSON persistence so data persists across server restarts,
with thread-safe access and pre-seeded demonstration data.
"""

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.packages.revolt.assessment_engine import assess_battery
from src.packages.revolt.models import (
    AssessmentResult,
    Battery,
    BatteryBase,
    BatteryChemistry,
    BatteryCreate,
    BatteryUpdate,
    Facility,
    FieldProvenance,
    FieldSource,
    ImpactAnalytics,
    LifecycleStatus,
    LogisticsType,
    OriginalApplication,
    PhysicalCondition,
    RecommendedPathway,
    ScheduleBooking,
    ScheduleBookingCreate,
    TelemetryInjectionPayload,
    TemperatureHistory,
    TimelineEvent,
)

logger = logging.getLogger("revolt.storage")

DATA_FILE_PATH = Path(os.environ.get("REVOLT_DATA_PATH", "revolt_data.json"))

VALID_TRANSITIONS: dict[LifecycleStatus, list[LifecycleStatus]] = {
    LifecycleStatus.REGISTERED: [LifecycleStatus.ASSESSED, LifecycleStatus.PENDING_VERIFICATION],
    LifecycleStatus.PENDING_VERIFICATION: [LifecycleStatus.ASSESSED],
    LifecycleStatus.ASSESSED: [LifecycleStatus.AWAITING_COLLECTION, LifecycleStatus.IN_TRANSIT],
    LifecycleStatus.AWAITING_COLLECTION: [LifecycleStatus.IN_TRANSIT, LifecycleStatus.RECEIVED_AT_FACILITY],
    LifecycleStatus.IN_TRANSIT: [LifecycleStatus.RECEIVED_AT_FACILITY],
    LifecycleStatus.RECEIVED_AT_FACILITY: [LifecycleStatus.PROCESSING, LifecycleStatus.ROUTED_FOR_PROCESSING],
    LifecycleStatus.ROUTED_FOR_PROCESSING: [LifecycleStatus.PROCESSING],
    LifecycleStatus.PROCESSING: [
        LifecycleStatus.COMPLETED,
        LifecycleStatus.REUSED,
        LifecycleStatus.REFURBISHED,
        LifecycleStatus.RECYCLED,
        LifecycleStatus.SPECIALIST_HANDLING,
    ],
    LifecycleStatus.REUSED: [LifecycleStatus.COMPLETED],
    LifecycleStatus.REFURBISHED: [LifecycleStatus.COMPLETED],
    LifecycleStatus.RECYCLED: [LifecycleStatus.COMPLETED],
    LifecycleStatus.SPECIALIST_HANDLING: [LifecycleStatus.COMPLETED],
    LifecycleStatus.COMPLETED: [],
}

# Seed Facilities (Realistic authorized recycling, refurbishing, and hazmat centers)
DEFAULT_FACILITIES: list[Facility] = [
    Facility(
        id="FAC-HYD-01",
        name="EcoVolt Hydrometallurgical Refining Center",
        facility_type="Authorized Hydrometallurgical Recycler",
        address="Plot 42, SIPCOT Industrial Park, Sriperumbudur",
        city="Chennai",
        state="Tamil Nadu",
        latitude=12.9815,
        longitude=79.9722,
        phone="+91 44 2716 8800",
        email="intake@ecovolt-refining.in",
        supported_pathways=[RecommendedPathway.RECYCLE],
        supported_chemistries=[
            BatteryChemistry.NMC,
            BatteryChemistry.LFP,
            BatteryChemistry.LCO,
            BatteryChemistry.NCA,
        ],
        services_offered=[
            "Direct Hydrometallurgical Leaching",
            "Black Mass Separation (95%+ Mineral Purity)",
            "Electrolyte Neutralization",
            "Automated Cathode/Anode Mechanical Shredding",
        ],
        certifications=["CPCB / TNPCB Authorized Recycler", "ISO 14001:2015", "R2v3 Certified"],
        operating_hours="Mon-Sat 08:30 - 18:30",
    ),
    Facility(
        id="FAC-REF-02",
        name="AuraEnergy Second-Life ESS & Diagnostics Hub",
        facility_type="Certified Refurbisher & ESS Integrator",
        address="3rd Phase, Guindy Industrial Estate",
        city="Chennai",
        state="Tamil Nadu",
        latitude=13.0067,
        longitude=80.2023,
        phone="+91 44 4920 1122",
        email="diagnostics@auraenergy.in",
        supported_pathways=[RecommendedPathway.REUSE, RecommendedPathway.REFURBISH],
        supported_chemistries=[
            BatteryChemistry.LFP,
            BatteryChemistry.NMC,
            BatteryChemistry.LCO,
        ],
        services_offered=[
            "Cell-Level Impedance Spectroscopy (EIS)",
            "BMS Firmware Recalibration & Balancing",
            "Solar ESS Second-Life Pack Assembly (UL 1974 Standard)",
            "Courier Depot Drop-Off & Automated Testing",
        ],
        certifications=["UL 1974 Repurposing Facility", "BIS Certified", "ISO 9001:2015"],
        operating_hours="Mon-Fri 09:00 - 18:00",
    ),
    Facility(
        id="FAC-HAZ-03",
        name="PyroSafe Hazardous Battery Containment & Neutralization",
        facility_type="Emergency Hazmat Quarantined Depot",
        address="Sector 9, Oragadam Auto Ancillary Cluster",
        city="Kanchipuram",
        state="Tamil Nadu",
        latitude=12.8362,
        longitude=79.9511,
        phone="+91 44 8830 9999",
        email="emergency@pyrosafe-hazmat.in",
        supported_pathways=[RecommendedPathway.HAZARDOUS],
        supported_chemistries=[
            BatteryChemistry.NMC,
            BatteryChemistry.LFP,
            BatteryChemistry.LCO,
            BatteryChemistry.LMO,
            BatteryChemistry.NCA,
            BatteryChemistry.OTHER,
        ],
        services_offered=[
            "24/7 Fire-Safe Vermiculite Quarantine Storage",
            "Deep Thermal Inerting & Saline Immersion",
            "Explosion-Proof Controlled Battery Crushing",
            "Hazmat UN 3480 Specialist Logistics Dispatch",
        ],
        certifications=["Petroleum & Explosives Safety Organization (PESO) Quarantine Permit", "UN 3480 Hazmat Transport Compliance"],
        operating_hours="24/7 Rapid Emergency Response",
    ),
    Facility(
        id="FAC-LAB-04",
        name="ReCell Pack Restoration & Cell Balancing Lab",
        facility_type="Specialized Battery Refurbishment Lab",
        address="SIDCO Industrial Estate, Kurichi",
        city="Coimbatore",
        state="Tamil Nadu",
        latitude=10.9328,
        longitude=76.9697,
        phone="+91 422 267 4433",
        email="intake@recell-labs.com",
        supported_pathways=[RecommendedPathway.REFURBISH, RecommendedPathway.REUSE],
        supported_chemistries=[
            BatteryChemistry.LFP,
            BatteryChemistry.NMC,
        ],
        services_offered=[
            "Active Cell Balancing & Re-Binning",
            "Laser Busbar Re-welding & Thermal Pad Replacement",
            "High-Rate Cycle Validation Testing",
            "BMS Protection Board Replacement",
        ],
        certifications=["ISO 17025 Testing Laboratory", "IEC 62619 Secondary Cells"],
        operating_hours="Mon-Sat 09:00 - 18:00",
    ),
]


def _create_initial_seed_batteries() -> list[Battery]:
    """Generates realistic demonstration battery records across all circular pathways."""
    now = datetime.now(timezone.utc)

    # 1. Tata Nexon EV LFP Module -> High SoH -> REUSE
    b1_base = BatteryBase(
        name="Tata Nexon EV Mod-4 (LFP 16S)",
        device_model="Tata Nexon EV / 16S1P Prismatic",
        chemistry=BatteryChemistry.LFP,
        original_application=OriginalApplication.EV,
        age_months=28,
        rated_capacity_mah=105000.0,
        measured_capacity_mah=88200.0,  # 84% SoH
        nominal_voltage_v=51.2,
        measured_voltage_v=52.4,  # ~3.27V/cell (normal)
        cycle_count=620,
        temperature_history=TemperatureHistory.NORMAL,
        physical_condition=PhysicalCondition.GOOD,
        owner_notes="Decommissioned during early fleet upgrade; clean cell busbars and pristine casing.",
        provenance=FieldProvenance(
            rated_capacity=FieldSource.VERIFIED_SPEC,
            nominal_voltage=FieldSource.VERIFIED_SPEC,
            measured_capacity=FieldSource.TECHNICIAN_MEASURED,
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            cycle_count=FieldSource.TECHNICIAN_MEASURED,
            chemistry=FieldSource.VERIFIED_SPEC,
            physical_condition=FieldSource.TECHNICIAN_MEASURED,
        ),
        data_completeness_pct=100.0,
    )
    b1_assessment = assess_battery(b1_base)
    b1 = Battery(
        id="REV-2026-0041",
        registered_at=now,
        status=LifecycleStatus.ASSESSED,
        recommended_pathway=b1_assessment.pathway,
        assessment=b1_assessment,
        is_demo_data=True,
        timeline=[
            TimelineEvent(
                id="EVT-001",
                timestamp=now,
                status=LifecycleStatus.REGISTERED,
                title="Battery Registered",
                description="Fleet operator logged 51.2V LFP module for secondary life triage.",
                actor="Fleet Logistics Admin",
            ),
            TimelineEvent(
                id="EVT-002",
                timestamp=now,
                status=LifecycleStatus.ASSESSED,
                title="Assessment Complete",
                description="Evaluation completed: 84.0% SoH qualifies for stationary solar ESS second-life.",
                actor="ReVolt Assessment Engine",
            ),
        ],
        **b1_base.model_dump(),
    )

    # 2. MacBook Pro A1989 LCO Pack -> Corroded Terminals -> REFURBISH
    b2_base = BatteryBase(
        name="MacBook Pro A1989 Battery Pack",
        device_model="Apple A1989 / 020-02497",
        chemistry=BatteryChemistry.LCO,
        original_application=OriginalApplication.LAPTOP,
        age_months=42,
        rated_capacity_mah=5086.0,
        measured_capacity_mah=3458.0,  # 68% SoH
        nominal_voltage_v=11.4,
        measured_voltage_v=10.9,  # ~3.63V/cell
        cycle_count=1140,
        temperature_history=TemperatureHistory.NORMAL,
        physical_condition=PhysicalCondition.CORRODED_TERMINALS,
        owner_notes="Minor corrosion on flex cable connector. Cells mechanically sound.",
        provenance=FieldProvenance(
            rated_capacity=FieldSource.OCR_EXTRACTED,
            nominal_voltage=FieldSource.OCR_EXTRACTED,
            measured_capacity=FieldSource.TECHNICIAN_MEASURED,
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            cycle_count=FieldSource.TECHNICIAN_MEASURED,
            chemistry=FieldSource.OCR_EXTRACTED,
            physical_condition=FieldSource.USER_ENTERED,
        ),
        data_completeness_pct=100.0,
    )
    b2_assessment = assess_battery(b2_base)
    b2 = Battery(
        id="REV-2026-0082",
        registered_at=now,
        status=LifecycleStatus.AWAITING_COLLECTION,
        recommended_pathway=b2_assessment.pathway,
        assessment=b2_assessment,
        assigned_facility_id="FAC-REF-02",
        assigned_facility_name="AuraEnergy Second-Life ESS & Diagnostics Hub",
        booking=ScheduleBooking(
            booking_id="BK-2026-8812",
            facility_id="FAC-REF-02",
            facility_name="AuraEnergy Second-Life ESS & Diagnostics Hub",
            logistics_type=LogisticsType.STANDARD_PICKUP,
            scheduled_date="2026-10-18",
            time_slot="10:00 - 13:00",
            pickup_address="Tech Support Center, Anna Nagar, Chennai",
            contact_name="Arun Kumar",
            contact_phone="+91 98765 43210",
            special_instructions="Fragile electronic connector; pack in antistatic pouch.",
        ),
        is_demo_data=True,
        timeline=[
            TimelineEvent(
                id="EVT-003",
                timestamp=now,
                status=LifecycleStatus.REGISTERED,
                title="Battery Registered",
                description="Laptop repair center submitted high-cycle battery pack.",
                actor="Service Tech",
            ),
            TimelineEvent(
                id="EVT-004",
                timestamp=now,
                status=LifecycleStatus.ASSESSED,
                title="Assessment Complete",
                description="Evaluation: 68.0% SoH and corroded connector requires professional refurbishment.",
                actor="ReVolt Assessment Engine",
            ),
            TimelineEvent(
                id="EVT-005",
                timestamp=now,
                status=LifecycleStatus.AWAITING_COLLECTION,
                title="Collection Scheduled",
                description="Simulated courier pickup scheduled with AuraEnergy Diagnostics Hub.",
                actor="User",
            ),
        ],
        **b2_base.model_dump(),
    )

    # 3. Severely Bloated Pouch -> Undervoltage 1.65V -> HAZARDOUS QUARANTINE
    b3_base = BatteryBase(
        name="PowerBank X20 Pouch Cell (Bloated)",
        device_model="Generic 1S Pouch / 806090",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_BANK,
        age_months=36,
        rated_capacity_mah=20000.0,
        measured_capacity_mah=6200.0,  # 31% SoH
        nominal_voltage_v=3.7,
        measured_voltage_v=1.65,  # DANGEROUS UNDERVOLTAGE < 2.0V!
        cycle_count=850,
        temperature_history=TemperatureHistory.OVERHEATED,
        physical_condition=PhysicalCondition.SWOLLEN_SEVERE,
        owner_notes="Severe swelling cracked the plastic outer casing. Emitting faint sweet chemical smell.",
        provenance=FieldProvenance(
            rated_capacity=FieldSource.USER_ENTERED,
            nominal_voltage=FieldSource.USER_ENTERED,
            measured_capacity=FieldSource.TECHNICIAN_MEASURED,
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            cycle_count=FieldSource.USER_ENTERED,
            chemistry=FieldSource.USER_ENTERED,
            physical_condition=FieldSource.USER_ENTERED,
        ),
        data_completeness_pct=100.0,
    )
    b3_assessment = assess_battery(b3_base)
    b3 = Battery(
        id="REV-2026-0099",
        registered_at=now,
        status=LifecycleStatus.ASSESSED,
        recommended_pathway=b3_assessment.pathway,
        assessment=b3_assessment,
        is_demo_data=True,
        timeline=[
            TimelineEvent(
                id="EVT-006",
                timestamp=now,
                status=LifecycleStatus.REGISTERED,
                title="Hazardous Battery Logged",
                description="Consumer battery entered with severe casing bulge.",
                actor="E-Waste Drop Desk",
            ),
            TimelineEvent(
                id="EVT-007",
                timestamp=now,
                status=LifecycleStatus.ASSESSED,
                title="CRITICAL HAZARD DETECTED",
                description="Immediate quarantine triggered: Severe swelling and 1.65V dendrite risk.",
                actor="ReVolt Safety Engine",
            ),
        ],
        **b3_base.model_dump(),
    )

    # 4. Hero Lectro E-Bike Pack -> Low SoH 45% -> RECYCLE
    b4_base = BatteryBase(
        name="Hero Lectro E-Bike Pack (36V 10S)",
        device_model="HL-3610-NMC / 10S4P",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.EV,
        age_months=58,
        rated_capacity_mah=10400.0,
        measured_capacity_mah=4680.0,  # 45% SoH
        nominal_voltage_v=36.0,
        measured_voltage_v=34.2,
        cycle_count=1950,
        temperature_history=TemperatureHistory.ELEVATED,
        physical_condition=PhysicalCondition.SCRATCHED,
        owner_notes="End-of-service pack with high internal resistance. No physical punctures.",
        provenance=FieldProvenance(
            rated_capacity=FieldSource.OCR_EXTRACTED,
            nominal_voltage=FieldSource.OCR_EXTRACTED,
            measured_capacity=FieldSource.TECHNICIAN_MEASURED,
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            cycle_count=FieldSource.TECHNICIAN_MEASURED,
            chemistry=FieldSource.OCR_EXTRACTED,
            physical_condition=FieldSource.TECHNICIAN_MEASURED,
        ),
        data_completeness_pct=100.0,
    )
    b4_assessment = assess_battery(b4_base)
    b4 = Battery(
        id="REV-2026-0105",
        registered_at=now,
        status=LifecycleStatus.PROCESSING,
        recommended_pathway=b4_assessment.pathway,
        assessment=b4_assessment,
        assigned_facility_id="FAC-HYD-01",
        assigned_facility_name="EcoVolt Hydrometallurgical Refining Center",
        booking=ScheduleBooking(
            booking_id="BK-2026-4419",
            facility_id="FAC-HYD-01",
            facility_name="EcoVolt Hydrometallurgical Refining Center",
            logistics_type=LogisticsType.STANDARD_PICKUP,
            scheduled_date="2026-10-10",
            time_slot="09:00 - 12:00",
            pickup_address="Green Fleet Hub, Ambattur Industrial Estate",
            contact_name="Deepak Raj",
            contact_phone="+91 94444 11223",
        ),
        is_demo_data=True,
        timeline=[
            TimelineEvent(
                id="EVT-008",
                timestamp=now,
                status=LifecycleStatus.REGISTERED,
                title="Battery Registered",
                description="E-bike battery registered for recycling triage.",
                actor="Green Fleet Manager",
            ),
            TimelineEvent(
                id="EVT-009",
                timestamp=now,
                status=LifecycleStatus.ASSESSED,
                title="Assessment Complete",
                description="End-of-life SoH 45% routed to hydrometallurgical recycling.",
                actor="ReVolt Assessment Engine",
            ),
            TimelineEvent(
                id="EVT-010",
                timestamp=now,
                status=LifecycleStatus.IN_TRANSIT,
                title="Picked Up by EcoVolt Logistics",
                description="Battery collected from Ambattur Depot.",
                actor="Logistics Courier",
            ),
            TimelineEvent(
                id="EVT-011",
                timestamp=now,
                status=LifecycleStatus.PROCESSING,
                title="Received & Shredding Started",
                description="Cell safely discharged; automated black mass extraction in progress.",
                actor="Facility Intake Operator",
            ),
        ],
        **b4_base.model_dump(),
    )

    # 5. iPhone 13 Li-Cobalt -> Newly Registered (Unassessed)
    b5_base = BatteryBase(
        name="iPhone 13 Li-Cobalt Cell",
        device_model="Apple A2633 / 616-00858",
        chemistry=BatteryChemistry.LCO,
        original_application=OriginalApplication.SMARTPHONE,
        age_months=30,
        rated_capacity_mah=3227.0,
        measured_capacity_mah=2710.0,
        nominal_voltage_v=3.85,
        measured_voltage_v=3.82,
        cycle_count=710,
        temperature_history=TemperatureHistory.NORMAL,
        physical_condition=PhysicalCondition.GOOD,
        owner_notes="Upgraded device; battery still holds good charge.",
        provenance=FieldProvenance(
            rated_capacity=FieldSource.USER_ENTERED,
            nominal_voltage=FieldSource.USER_ENTERED,
            measured_capacity=FieldSource.USER_ENTERED,
            measured_voltage=FieldSource.USER_ENTERED,
            cycle_count=FieldSource.USER_ENTERED,
            chemistry=FieldSource.USER_ENTERED,
            physical_condition=FieldSource.USER_ENTERED,
        ),
        data_completeness_pct=100.0,
    )
    b5 = Battery(
        id="REV-2026-0120",
        registered_at=now,
        status=LifecycleStatus.REGISTERED,
        recommended_pathway=RecommendedPathway.PENDING,
        assessment=None,
        is_demo_data=True,
        timeline=[
            TimelineEvent(
                id="EVT-012",
                timestamp=now,
                status=LifecycleStatus.REGISTERED,
                title="Battery Registered",
                description="Logged into ReVolt registry via customer drop portal.",
                actor="Retail Customer",
            )
        ],
        **b5_base.model_dump(),
    )

    # 6. DeWalt 20V Max Pack -> SmartScan OCR Extracted -> PENDING_VERIFICATION
    b6_base = BatteryBase(
        name="DeWalt 20V Max Pack (Loose Module)",
        device_model="DCB205 / 18650-5S2P",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_TOOL,
        age_months=36,
        rated_capacity_mah=5000.0,
        measured_capacity_mah=None,  # Missing - Needs Telemetry Lab test!
        nominal_voltage_v=18.0,
        measured_voltage_v=None,  # Missing - Needs Telemetry Lab test!
        cycle_count=None,
        temperature_history=TemperatureHistory.UNKNOWN,
        physical_condition=PhysicalCondition.GOOD,
        owner_notes="Found in workshop cleanup; label scanned via SmartScan OCR. No multimeter readings yet.",
        provenance=FieldProvenance(
            rated_capacity=FieldSource.OCR_EXTRACTED,
            nominal_voltage=FieldSource.OCR_EXTRACTED,
            model_identity=FieldSource.OCR_EXTRACTED,
            chemistry=FieldSource.OCR_EXTRACTED,
            measured_capacity=FieldSource.UNKNOWN,
            measured_voltage=FieldSource.UNKNOWN,
            cycle_count=FieldSource.UNKNOWN,
            physical_condition=FieldSource.USER_ENTERED,
        ),
        data_completeness_pct=50.0,
        ocr_raw_text="DEWALT 20V MAX* LITHIUM ION 5.0Ah DCB205 18V NOM",
        ocr_detected_fields={
            "model": "DCB205",
            "rated_capacity_mah": 5000.0,
            "nominal_voltage_v": 18.0,
            "chemistry": "NMC",
        },
    )
    b6_assessment = assess_battery(b6_base)
    b6 = Battery(
        id="REV-2026-0210",
        registered_at=now,
        status=LifecycleStatus.PENDING_VERIFICATION,
        recommended_pathway=b6_assessment.pathway,
        assessment=b6_assessment,
        is_demo_data=True,
        timeline=[
            TimelineEvent(
                id="EVT-013",
                timestamp=now,
                status=LifecycleStatus.REGISTERED,
                title="SmartScan Registered",
                description="Battery label scanned; rated specs extracted via OCR.",
                actor="SmartScan Portal",
            ),
            TimelineEvent(
                id="EVT-014",
                timestamp=now,
                status=LifecycleStatus.PENDING_VERIFICATION,
                title="Pending Laboratory Verification",
                description="Missing operational voltage & capacity; routed for lab verification.",
                actor="ReVolt Assessment Engine",
            ),
        ],
        **b6_base.model_dump(),
    )

    return [b1, b2, b3, b4, b5, b6]


class ReVoltRepository:
    """Thread-safe file-backed repository for ReVolt battery records."""

    def __init__(self, storage_path: Path = DATA_FILE_PATH) -> None:
        self.storage_path = storage_path
        self._lock = threading.RLock()
        self._batteries: dict[str, Battery] = {}
        self._facilities: dict[str, Facility] = {f.id: f for f in DEFAULT_FACILITIES}
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        """Loads state from disk if exists, otherwise seeds demonstration records."""
        with self._lock:
            if self.storage_path.exists():
                try:
                    with open(self.storage_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    batteries_data = data.get("batteries", [])
                    for item in batteries_data:
                        try:
                            b = Battery.model_validate(item)
                            self._batteries[b.id] = b
                        except Exception as parse_err:
                            logger.warning("Skipping malformed battery record: %s", parse_err)
                    logger.info("Loaded %d batteries from %s", len(self._batteries), self.storage_path)
                    if len(self._batteries) > 0:
                        return
                except Exception as err:
                    logger.warning("Failed to load existing ReVolt data file (%s), re-seeding: %s", self.storage_path, err)

            # Seed demo data if file was empty or missing
            for b in _create_initial_seed_batteries():
                self._batteries[b.id] = b
            self._save_to_disk_unlocked()
            logger.info("Seeded %d demo batteries into storage", len(self._batteries))

    def _save_to_disk_unlocked(self) -> None:
        """Serializes repository state to disk safely (must be called inside lock)."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "batteries": [b.model_dump(mode="json") for b in self._batteries.values()],
            }
            tmp_path = self.storage_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            # Atomic replacement
            if tmp_path.exists():
                os.replace(tmp_path, self.storage_path)
        except Exception as err:
            logger.error("Failed to write ReVolt data to %s: %s", self.storage_path, err)

    def get_all_batteries(
        self,
        search: str | None = None,
        pathway: RecommendedPathway | None = None,
        chemistry: BatteryChemistry | None = None,
        status: LifecycleStatus | None = None,
    ) -> list[Battery]:
        """Returns sorted list of batteries matching optional filter criteria."""
        with self._lock:
            items = list(self._batteries.values())

        # Sort newest first
        items.sort(key=lambda x: x.registered_at, reverse=True)

        if search:
            query = search.strip().lower()
            items = [
                b
                for b in items
                if query in b.id.lower()
                or query in b.name.lower()
                or query in b.chemistry.value.lower()
                or query in b.original_application.value.lower()
                or (b.owner_notes and query in b.owner_notes.lower())
            ]

        if pathway:
            items = [b for b in items if b.recommended_pathway == pathway]

        if chemistry:
            items = [b for b in items if b.chemistry == chemistry]

        if status:
            items = [b for b in items if b.status == status]

        return items

    def get_battery(self, battery_id: str) -> Battery | None:
        with self._lock:
            return self._batteries.get(battery_id)

    def create_battery(self, data: BatteryCreate) -> Battery:
        """Registers a new battery, generates unique ID, and creates initial timeline event."""
        unique_num = (uuid.uuid4().int % 9000) + 1000
        year = datetime.now(timezone.utc).year
        battery_id = f"REV-{year}-{unique_num}"

        now = datetime.now(timezone.utc)
        timeline_event = TimelineEvent(
            id=f"EVT-{uuid.uuid4().hex[:6]}",
            timestamp=now,
            status=LifecycleStatus.REGISTERED,
            title="Battery Registered",
            description=f"Battery {data.name} entered into ReVolt digital registry.",
            actor="User",
        )

        battery = Battery(
            id=battery_id,
            registered_at=now,
            status=LifecycleStatus.REGISTERED,
            recommended_pathway=RecommendedPathway.PENDING,
            assessment=None,
            timeline=[timeline_event],
            is_demo_data=False,
            **data.model_dump(),
        )

        with self._lock:
            self._batteries[battery_id] = battery
            self._save_to_disk_unlocked()

        logger.info("Created new battery record %s (%s)", battery.id, battery.name)
        return battery

    def update_battery(self, battery_id: str, data: BatteryUpdate) -> Battery | None:
        with self._lock:
            b = self._batteries.get(battery_id)
            if not b:
                return None

            update_dict = data.model_dump(exclude_unset=True)
            for k, v in update_dict.items():
                setattr(b, k, v)

            # Re-run assessment if telemetry changed and already assessed
            if b.status != LifecycleStatus.REGISTERED and b.assessment is not None:
                new_assessment = assess_battery(b)
                b.assessment = new_assessment
                b.recommended_pathway = new_assessment.pathway

            self._save_to_disk_unlocked()
            return b

    def inject_telemetry(self, battery_id: str, telemetry: TelemetryInjectionPayload) -> Battery | None:
        """Injects workbench multimeter and cycler measurements, updating provenance and assessment."""
        with self._lock:
            b = self._batteries.get(battery_id)
            if not b:
                return None

            b.measured_voltage_v = telemetry.measured_voltage_v
            b.measured_capacity_mah = telemetry.measured_capacity_mah
            if telemetry.cycle_count is not None:
                b.cycle_count = telemetry.cycle_count
            b.temperature_history = telemetry.temperature_history
            b.physical_condition = telemetry.physical_condition

            if telemetry.technician_notes:
                b.owner_notes = (b.owner_notes + " | Telemetry Lab: " + telemetry.technician_notes).strip(" | ")

            # Update provenance to simulated
            b.provenance.measured_voltage = FieldSource.SIMULATED
            b.provenance.measured_capacity = FieldSource.SIMULATED
            if telemetry.cycle_count is not None:
                b.provenance.cycle_count = FieldSource.SIMULATED
            b.provenance.physical_condition = FieldSource.SIMULATED
            b.data_completeness_pct = 100.0

            # Execute deterministic assessment
            assessment = assess_battery(b)
            b.assessment = assessment
            b.recommended_pathway = assessment.pathway
            if b.status in {LifecycleStatus.REGISTERED, LifecycleStatus.PENDING_VERIFICATION}:
                b.status = LifecycleStatus.ASSESSED

            resistance_txt = f", IR: {telemetry.internal_resistance_mohm} mOhm" if telemetry.internal_resistance_mohm else ""
            b.timeline.append(
                TimelineEvent(
                    id=f"EVT-{uuid.uuid4().hex[:6]}",
                    timestamp=datetime.now(timezone.utc),
                    status=b.status,
                    title="Mock Telemetry Bench Injection (Simulated)",
                    description=(
                        f"Multimeter OCV: {telemetry.measured_voltage_v:.2f}V, "
                        f"Capacity: {telemetry.measured_capacity_mah:.0f} mAh{resistance_txt}. "
                        f"Assessed: {assessment.pathway.value} (Confidence: {assessment.confidence_score * 100:.0f}%)."
                    ),
                    actor="Mock Telemetry Bench (Simulated)",
                )
            )

            self._save_to_disk_unlocked()
            return b

    def assess_battery_record(self, battery_id: str) -> Battery | None:
        """Runs the deterministic assessment engine against the battery record."""
        with self._lock:
            b = self._batteries.get(battery_id)
            if not b:
                return None

            assessment = assess_battery(b)
            b.assessment = assessment
            b.recommended_pathway = assessment.pathway

            # Progress lifecycle status if still in REGISTERED or PENDING_VERIFICATION state
            if b.status in {LifecycleStatus.REGISTERED, LifecycleStatus.PENDING_VERIFICATION}:
                if assessment.pathway == RecommendedPathway.PENDING_VERIFICATION:
                    b.status = LifecycleStatus.PENDING_VERIFICATION
                else:
                    b.status = LifecycleStatus.ASSESSED

            # Add timeline event
            event_title = "Critical Hazard Detected" if assessment.is_hazardous else f"Assessment Complete: {assessment.pathway.value}"
            desc = (
                f"Evaluation completed. Recommended pathway: {assessment.pathway.value}. "
                f"Confidence: {assessment.confidence_score * 100:.0f}%."
            )
            if assessment.is_hazardous:
                desc += " Immediate quarantine and specialist hazmat protocol triggered."

            b.timeline.append(
                TimelineEvent(
                    id=f"EVT-{uuid.uuid4().hex[:6]}",
                    timestamp=datetime.now(timezone.utc),
                    status=b.status,
                    title=event_title,
                    description=desc,
                    actor="ReVolt Assessment Engine",
                )
            )

            self._save_to_disk_unlocked()
            return b

    def _get_valid_transitions_unlocked(self, b: Battery) -> list[LifecycleStatus]:
        allowed = list(VALID_TRANSITIONS.get(b.status, []))
        is_hazardous = (
            b.recommended_pathway == RecommendedPathway.HAZARDOUS
            or (b.assessment is not None and b.assessment.is_hazardous)
        )
        if is_hazardous:
            allowed = [s for s in allowed if s not in {LifecycleStatus.REUSED, LifecycleStatus.REFURBISHED}]
        return allowed

    def get_valid_transitions(self, battery_id: str) -> list[LifecycleStatus]:
        """Returns valid next lifecycle statuses for a battery according to transition rules and safety constraints."""
        with self._lock:
            b = self._batteries.get(battery_id)
            if not b:
                return []
            return self._get_valid_transitions_unlocked(b)

    def update_status(
        self,
        battery_id: str,
        new_status: LifecycleStatus,
        note: str = "",
        actor: str = "User",
    ) -> Battery | None:
        """Updates battery lifecycle status with strict transition verification."""
        with self._lock:
            b = self._batteries.get(battery_id)
            if not b:
                return None

            # Enforce logistics safety: hazardous battery cannot transition to REUSED or REFURBISHED
            is_hazardous = (
                b.recommended_pathway == RecommendedPathway.HAZARDOUS
                or (b.assessment is not None and b.assessment.is_hazardous)
            )
            if is_hazardous and new_status in {LifecycleStatus.REUSED, LifecycleStatus.REFURBISHED}:
                raise ValueError(
                    f"Safety violation: Battery '{b.id}' is quarantined as HAZARDOUS. "
                    f"Transition to {new_status.value} is strictly prohibited. "
                    f"Hazardous units must only undergo specialist containment, neutralization, or certified recycling."
                )

            allowed = self._get_valid_transitions_unlocked(b)
            if new_status not in allowed:
                allowed_str = ", ".join(s.value for s in allowed)
                raise ValueError(
                    f"Invalid transition from {b.status.value} to {new_status.value}. "
                    f"Allowed transitions from current state: [{allowed_str}]"
                )

            b.status = new_status
            b.timeline.append(
                TimelineEvent(
                    id=f"EVT-{uuid.uuid4().hex[:6]}",
                    timestamp=datetime.now(timezone.utc),
                    status=new_status,
                    title=f"Status Changed: {new_status.value}",
                    description=note or f"Lifecycle transitioned to {new_status.value}.",
                    actor=actor,
                )
            )

            self._save_to_disk_unlocked()
            return b

    def get_facilities(
        self,
        pathway: RecommendedPathway | None = None,
        chemistry: BatteryChemistry | None = None,
        query: str | None = None,
    ) -> list[Facility]:
        """Returns facilities matching optional pathway and chemistry filters."""
        facilities = list(self._facilities.values())

        if pathway:
            facilities = [f for f in facilities if pathway in f.supported_pathways]

        if chemistry:
            facilities = [f for f in facilities if chemistry in f.supported_chemistries]

        if query:
            q = query.strip().lower()
            facilities = [
                f
                for f in facilities
                if q in f.name.lower()
                or q in f.city.lower()
                or q in f.facility_type.lower()
                or any(q in s.lower() for s in f.services_offered)
            ]

        return facilities

    def get_facility(self, facility_id: str) -> Facility | None:
        return self._facilities.get(facility_id)

    def schedule_booking(self, battery_id: str, booking_req: ScheduleBookingCreate) -> Battery | None:
        """Associates a selected facility and creates a simulated collection/drop-off booking."""
        with self._lock:
            b = self._batteries.get(battery_id)
            if not b:
                return None

            fac = self._facilities.get(booking_req.facility_id)
            if not fac:
                raise ValueError(f"Facility '{booking_req.facility_id}' not found")

            # Enforce logistics safety for HAZARDOUS batteries
            is_hazardous = (
                b.recommended_pathway == RecommendedPathway.HAZARDOUS
                or (b.assessment is not None and b.assessment.is_hazardous)
            )

            if is_hazardous:
                # Hazardous batteries CANNOT use standard pickup or public drop-off
                if booking_req.logistics_type != LogisticsType.HAZMAT_PICKUP:
                    raise ValueError(
                        f"Safety violation: Battery '{b.id}' is quarantined as HAZARDOUS. "
                        f"STANDARD_PICKUP and DEPOT_DROP_OFF are strictly prohibited. "
                        f"Logistics must use verified HAZMAT_PICKUP (UN 3480 certified courier)."
                    )

                # Facility MUST support HAZARDOUS containment
                if RecommendedPathway.HAZARDOUS not in fac.supported_pathways:
                    raise ValueError(
                        f"Logistics routing error: Facility '{fac.name}' is not authorized for "
                        f"HAZARDOUS battery intake. Hazardous batteries must be booked with an authorized "
                        f"hazmat containment facility (e.g. PyroSafe FAC-HAZ-03)."
                    )
            else:
                # Non-hazardous batteries cannot route to hazardous-only containment facilities
                if fac.supported_pathways == [RecommendedPathway.HAZARDOUS]:
                    raise ValueError(
                        f"Facility '{fac.name}' is an emergency hazmat quarantine facility reserved exclusively for hazardous batteries."
                    )
                # Verify facility supports the circular pathway if recommended
                if b.recommended_pathway in {
                    RecommendedPathway.REUSE,
                    RecommendedPathway.REFURBISH,
                    RecommendedPathway.RECYCLE,
                }:
                    if b.recommended_pathway not in fac.supported_pathways:
                        raise ValueError(
                            f"Facility '{fac.name}' does not support the recommended '{b.recommended_pathway.value}' circular pathway."
                        )

            booking_id = f"BK-{datetime.now(timezone.utc).year}-{uuid.uuid4().hex[:6].upper()}"
            booking = ScheduleBooking(
                booking_id=booking_id,
                booked_at=datetime.now(timezone.utc),
                facility_name=fac.name,
                is_simulated=True,
                **booking_req.model_dump(),
            )

            b.assigned_facility_id = fac.id
            b.assigned_facility_name = fac.name
            b.booking = booking

            # Transition status to AWAITING_COLLECTION if currently ASSESSED or REGISTERED
            if b.status in {LifecycleStatus.REGISTERED, LifecycleStatus.ASSESSED, LifecycleStatus.PENDING_VERIFICATION}:
                b.status = LifecycleStatus.AWAITING_COLLECTION

            logistics_label = "Courier Pickup" if booking.logistics_type != LogisticsType.DEPOT_DROP_OFF else "Depot Drop-Off"
            b.timeline.append(
                TimelineEvent(
                    id=f"EVT-{uuid.uuid4().hex[:6]}",
                    timestamp=datetime.now(timezone.utc),
                    status=b.status,
                    title=f"Logistics Scheduled: {logistics_label}",
                    description=(
                        f"Simulated booking #{booking_id} with {fac.name} for {booking.scheduled_date} ({booking.time_slot})."
                    ),
                    actor=booking.contact_name or "User",
                )
            )

            self._save_to_disk_unlocked()
            return b

    def get_analytics(self) -> ImpactAnalytics:
        """Computes real-time metrics across all registered battery records."""
        with self._lock:
            batteries = list(self._batteries.values())

        total_registered = len(batteries)
        total_assessed = sum(1 for b in batteries if b.status != LifecycleStatus.REGISTERED)
        total_awaiting_verification = sum(1 for b in batteries if b.status == LifecycleStatus.PENDING_VERIFICATION)
        total_awaiting_collection = sum(1 for b in batteries if b.status == LifecycleStatus.AWAITING_COLLECTION)
        total_in_transit = sum(1 for b in batteries if b.status == LifecycleStatus.IN_TRANSIT)
        total_routed_for_processing = sum(1 for b in batteries if b.status == LifecycleStatus.ROUTED_FOR_PROCESSING)
        total_completed = sum(1 for b in batteries if b.status in {LifecycleStatus.COMPLETED, LifecycleStatus.REUSED, LifecycleStatus.REFURBISHED, LifecycleStatus.RECYCLED})

        reused_count = sum(1 for b in batteries if b.recommended_pathway == RecommendedPathway.REUSE)
        refurbished_count = sum(1 for b in batteries if b.recommended_pathway == RecommendedPathway.REFURBISH)
        recycled_count = sum(1 for b in batteries if b.recommended_pathway == RecommendedPathway.RECYCLE)
        hazardous_count = sum(1 for b in batteries if b.recommended_pathway == RecommendedPathway.HAZARDOUS)
        specialist_handling_count = sum(1 for b in batteries if b.status == LifecycleStatus.SPECIALIST_HANDLING)
        pending_count = sum(1 for b in batteries if b.recommended_pathway in {RecommendedPathway.PENDING, RecommendedPathway.PENDING_VERIFICATION})

        # Environmental & Mineral Impact Calculations
        total_kwh_reused = sum(
            (b.rated_capacity_mah * b.nominal_voltage_v) / 1_000_000.0
            for b in batteries
            if b.recommended_pathway == RecommendedPathway.REUSE
        )
        total_kwh_recycled = sum(
            (b.rated_capacity_mah * b.nominal_voltage_v) / 1_000_000.0
            for b in batteries
            if b.recommended_pathway == RecommendedPathway.RECYCLE
        )
        total_weight_diverted_kg = sum(
            max(0.15, (b.rated_capacity_mah * b.nominal_voltage_v) / 150_000.0)
            for b in batteries
            if b.status != LifecycleStatus.REGISTERED
        )

        co2_avoided_kg = round(total_kwh_reused * 73.0, 2)
        lce_kg = round(total_kwh_recycled * 0.08, 3)
        cobalt_kg = round(
            sum(
                (b.rated_capacity_mah * b.nominal_voltage_v / 1_000_000.0) * 0.15
                for b in batteries
                if b.recommended_pathway == RecommendedPathway.RECYCLE and b.chemistry in {BatteryChemistry.NMC, BatteryChemistry.LCO}
            ),
            3,
        )
        nickel_kg = round(
            sum(
                (b.rated_capacity_mah * b.nominal_voltage_v / 1_000_000.0) * 0.35
                for b in batteries
                if b.recommended_pathway == RecommendedPathway.RECYCLE and b.chemistry in {BatteryChemistry.NMC, BatteryChemistry.NCA}
            ),
            3,
        )

        return ImpactAnalytics(
            total_registered=total_registered,
            total_assessed=total_assessed,
            total_awaiting_verification=total_awaiting_verification,
            total_awaiting_collection=total_awaiting_collection,
            total_in_transit=total_in_transit,
            total_routed_for_processing=total_routed_for_processing,
            total_completed=total_completed,
            reused_count=reused_count,
            refurbished_count=refurbished_count,
            recycled_count=recycled_count,
            hazardous_count=hazardous_count,
            specialist_handling_count=specialist_handling_count,
            pending_count=pending_count,
            estimated_landfill_diversion_kg=round(total_weight_diverted_kg, 2),
            estimated_co2_avoided_kg=co2_avoided_kg,
            estimated_lithium_carbonate_kg=lce_kg,
            estimated_cobalt_kg=cobalt_kg,
            estimated_nickel_kg=nickel_kg,
        )


# Singleton repository instance
revolt_repo = ReVoltRepository()
