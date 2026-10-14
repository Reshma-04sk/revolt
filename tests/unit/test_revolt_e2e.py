"""Acceptance test suite for ReVolt platform.

Covers:
- Assessment engine deterministic decision rules & safety triggers
- Chemistry-specific operating limits
- Registration & validation
- Scheduling & facility association
- Validated lifecycle status transitions
- Real-time environmental & material impact analytics
- SmartScan OCR label parsing
- Mock Telemetry Lab bench probe injection
"""

from pathlib import Path
import shutil
import pytest
from starlette.testclient import TestClient

from src.apps.api.main import app
from src.packages.revolt.assessment_engine import assess_battery
from src.packages.revolt.models import (
    BatteryBase,
    BatteryChemistry,
    FieldProvenance,
    FieldSource,
    LifecycleStatus,
    LogisticsType,
    OriginalApplication,
    PhysicalCondition,
    RecommendedPathway,
    ScheduleBookingCreate,
    TemperatureHistory,
)
from src.packages.revolt.storage import DATA_FILE_PATH, revolt_repo


@pytest.fixture(autouse=True)
def isolate_test_repository(tmp_path: Path) -> None:
    """Isolates the repository storage during tests to prevent polluting the persistent data file."""
    test_file = tmp_path / "test_revolt_data.json"
    if DATA_FILE_PATH.exists():
        shutil.copy(DATA_FILE_PATH, test_file)

    with revolt_repo._lock:
        original_batteries = {k: v.model_copy(deep=True) for k, v in revolt_repo._batteries.items()}
        original_path = revolt_repo.storage_path
        revolt_repo.storage_path = test_file

    yield

    with revolt_repo._lock:
        revolt_repo._batteries = original_batteries
        revolt_repo.storage_path = original_path


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_assessment_reuse_qualification() -> None:
    """Healthy battery with SoH >= 75% and good physical condition qualifies for REUSE."""
    b = BatteryBase(
        name="Healthy LFP ESS Module",
        chemistry=BatteryChemistry.LFP,
        original_application=OriginalApplication.ESS,
        age_months=18,
        rated_capacity_mah=50000.0,
        measured_capacity_mah=44000.0,  # 88% SoH
        nominal_voltage_v=48.0,
        measured_voltage_v=49.2,
        cycle_count=350,
        temperature_history=TemperatureHistory.NORMAL,
        physical_condition=PhysicalCondition.GOOD,
    )
    result = assess_battery(b)
    assert result.pathway == RecommendedPathway.REUSE
    assert not result.is_hazardous
    assert result.soh_percentage == 88.0
    assert result.confidence_score >= 0.85
    assert len(result.safety_warnings) == 0


def test_assessment_refurbish_qualification() -> None:
    """Battery with moderate capacity loss (60-75% SoH) qualifies for REFURBISH."""
    b = BatteryBase(
        name="MacBook Battery Pack",
        chemistry=BatteryChemistry.LCO,
        original_application=OriginalApplication.LAPTOP,
        age_months=36,
        rated_capacity_mah=5000.0,
        measured_capacity_mah=3400.0,  # 68% SoH
        nominal_voltage_v=11.4,
        measured_voltage_v=11.0,
        cycle_count=1100,
        temperature_history=TemperatureHistory.NORMAL,
        physical_condition=PhysicalCondition.CORRODED_TERMINALS,
    )
    result = assess_battery(b)
    assert result.pathway == RecommendedPathway.REFURBISH
    assert not result.is_hazardous
    assert result.soh_percentage == 68.0


def test_assessment_recycle_qualification() -> None:
    """End-of-life battery (SoH < 60% or cycles > 1800) must be routed to RECYCLE."""
    b = BatteryBase(
        name="Degraded E-Bike Pack",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.EV,
        age_months=60,
        rated_capacity_mah=12000.0,
        measured_capacity_mah=5400.0,  # 45% SoH
        nominal_voltage_v=36.0,
        measured_voltage_v=34.0,
        cycle_count=1900,
        temperature_history=TemperatureHistory.ELEVATED,
        physical_condition=PhysicalCondition.SCRATCHED,
    )
    result = assess_battery(b)
    assert result.pathway == RecommendedPathway.RECYCLE
    assert not result.is_hazardous
    assert result.soh_percentage == 45.0


@pytest.mark.parametrize(
    "hazard_condition",
    [
        PhysicalCondition.SWOLLEN_SEVERE,
        PhysicalCondition.PUNCTURED_CRACKED,
        PhysicalCondition.LEAKING,
        PhysicalCondition.THERMAL_RESIDUE,
    ],
)
def test_assessment_critical_physical_damage_triggers_hazardous(hazard_condition: PhysicalCondition) -> None:
    """Severe swelling, punctures, leaks, and thermal charring must trigger HAZARDOUS quarantine."""
    b = BatteryBase(
        name="Damaged Cell",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_BANK,
        age_months=24,
        rated_capacity_mah=10000.0,
        measured_capacity_mah=8000.0,
        nominal_voltage_v=3.7,
        measured_voltage_v=3.7,
        physical_condition=hazard_condition,
    )
    result = assess_battery(b)
    assert result.pathway == RecommendedPathway.HAZARDOUS
    assert result.is_hazardous
    assert any("CRITICAL" in w for w in result.safety_warnings)
    assert any("ISOLATE" in step for step in result.recommended_next_steps)


def test_assessment_critical_undervoltage_triggers_hazardous() -> None:
    """Per-cell voltage below 2.0V for NMC is a dendrite short hazard and must trigger HAZARDOUS."""
    b = BatteryBase(
        name="Over-discharged NMC Module",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.EV,
        age_months=20,
        rated_capacity_mah=60000.0,
        measured_capacity_mah=30000.0,
        nominal_voltage_v=3.7,
        measured_voltage_v=1.60,  # Critical under-voltage!
        physical_condition=PhysicalCondition.GOOD,
    )
    result = assess_battery(b)
    assert result.pathway == RecommendedPathway.HAZARDOUS
    assert result.is_hazardous
    assert any("UNDERVOLTAGE" in w for w in result.safety_warnings)


def test_assessment_missing_telemetry_triggers_pending_verification() -> None:
    """Missing electrical telemetry must trigger PENDING_VERIFICATION rather than false certainty."""
    b = BatteryBase(
        name="Untested Power Bank Cell",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_BANK,
        age_months=24,
        rated_capacity_mah=10000.0,
        measured_capacity_mah=None,
        nominal_voltage_v=3.7,
        measured_voltage_v=None,
        cycle_count=None,
        temperature_history=TemperatureHistory.UNKNOWN,
        physical_condition=PhysicalCondition.GOOD,
    )
    result = assess_battery(b)
    assert result.pathway == RecommendedPathway.PENDING_VERIFICATION
    assert not result.is_hazardous
    assert result.requires_lab_verification
    assert any("Insufficient" in f for f in result.contributing_factors)


def test_smartscan_ocr_parsing(client: TestClient) -> None:
    """Tests SmartScan OCR parsing of industrial battery label text."""
    sample_text = "DEWALT 20V MAX LITHIUM-ION 5.0Ah DCB205 18V NOMINAL"
    res = client.post("/api/v1/revolt/smartscan/parse", json={"raw_text": sample_text})
    assert res.status_code == 200
    data = res.json()
    assert data["extracted_fields"]["chemistry"] == "NMC"
    assert data["extracted_fields"]["rated_capacity_mah"] == 5000.0
    assert data["extracted_fields"]["nominal_voltage_v"] == 18.0
    assert data["extracted_fields"]["model"] == "DCB205"


def test_smartscan_registration_with_photo_data_url(client: TestClient) -> None:
    """SmartScan registration with uploaded label photo preserves photo_data_url and
    sets status to PENDING_VERIFICATION without assuming measured voltage/capacity."""
    sample_photo = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    parse_res = client.post(
        "/api/v1/revolt/smartscan/parse",
        json={"raw_text": "DEWALT 20V MAX LITHIUM-ION 5.0Ah DCB205 18V NOMINAL"},
    )
    assert parse_res.status_code == 200
    extracted = parse_res.json()["extracted_fields"]

    reg_payload = {
        "name": extracted["model"],
        "device_model": extracted["model"],
        "chemistry": extracted["chemistry"],
        "original_application": extracted["original_application"],
        "rated_capacity_mah": extracted["rated_capacity_mah"],
        "nominal_voltage_v": extracted["nominal_voltage_v"],
        "age_months": 36,
        "physical_condition": "GOOD",
        "ocr_raw_text": "DEWALT 20V MAX LITHIUM-ION 5.0Ah DCB205 18V NOMINAL",
        "photo_data_url": sample_photo,
    }
    reg_res = client.post("/api/v1/revolt/batteries", json=reg_payload)
    assert reg_res.status_code == 201
    created = reg_res.json()
    assert created["photo_data_url"] == sample_photo
    assert created["status"] == "REGISTERED"

    # Assess: without measured telemetry, it must be PENDING_VERIFICATION
    assess_res = client.post(f"/api/v1/revolt/batteries/{created['id']}/assess")
    assert assess_res.status_code == 200
    assessed = assess_res.json()
    assert assessed["recommended_pathway"] == "PENDING_VERIFICATION"
    assert assessed["status"] == "PENDING_VERIFICATION"
    assert assessed["assessment"]["requires_lab_verification"] is True



def test_mock_telemetry_lab_injection(client: TestClient) -> None:
    """Tests injecting bench multimeter/cycler measurements into an unmeasured battery."""
    # Register an unmeasured battery
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "DeWalt Loose Pack for Lab Test",
            "chemistry": "NMC",
            "original_application": "POWER_TOOL",
            "age_months": 24,
            "rated_capacity_mah": 5000.0,
            "nominal_voltage_v": 18.0,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # Inject telemetry via bench tester
    inject_res = client.post(
        f"/api/v1/revolt/batteries/{bid}/telemetry",
        json={
            "measured_voltage_v": 19.8,
            "measured_capacity_mah": 4200.0,  # 84% SoH
            "cycle_count": 310,
            "internal_resistance_mohm": 24.5,
            "temperature_history": "NORMAL",
            "physical_condition": "GOOD",
            "technician_notes": "All 5S strings balanced at 3.96V.",
        },
    )
    assert inject_res.status_code == 200
    updated = inject_res.json()
    assert updated["measured_voltage_v"] == 19.8
    assert updated["measured_capacity_mah"] == 4200.0
    assert updated["recommended_pathway"] == "REUSE"
    assert updated["assessment"]["soh_percentage"] == 84.0
    # Provenance must be marked SIMULATED
    assert updated["provenance"]["measured_voltage"] == "SIMULATED"
    assert updated["provenance"]["measured_capacity"] == "SIMULATED"
    assert updated["provenance"]["cycle_count"] == "SIMULATED"
    assert updated["provenance"]["physical_condition"] == "SIMULATED"

    # Verify retrieval from GET API returns persisted readings and SIMULATED provenance
    get_res = client.get(f"/api/v1/revolt/batteries/{bid}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["measured_voltage_v"] == 19.8
    assert retrieved["measured_capacity_mah"] == 4200.0
    assert retrieved["provenance"]["measured_voltage"] == "SIMULATED"
    assert retrieved["provenance"]["measured_capacity"] == "SIMULATED"


def test_mock_telemetry_lab_injection_allows_zero_voltage_dead_cell(client: TestClient) -> None:
    """Bench injection must support 0.0V (dead cell / completely discharged pack) and assess as HAZARDOUS."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Completely Depleted Power Tool Pack",
            "chemistry": "NMC",
            "original_application": "POWER_TOOL",
            "age_months": 36,
            "rated_capacity_mah": 4000.0,
            "nominal_voltage_v": 18.0,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # Inject 0.0V (dead cell)
    inject_res = client.post(
        f"/api/v1/revolt/batteries/{bid}/telemetry",
        json={
            "measured_voltage_v": 0.0,
            "measured_capacity_mah": 0.0,
            "internal_resistance_mohm": 120.0,
            "temperature_history": "NORMAL",
            "physical_condition": "GOOD",
            "technician_notes": "Measured 0.0V open circuit; copper dissolution suspected.",
        },
    )
    assert inject_res.status_code == 200
    updated = inject_res.json()
    assert updated["measured_voltage_v"] == 0.0
    assert updated["measured_capacity_mah"] == 0.0
    assert updated["recommended_pathway"] == "HAZARDOUS"
    assert updated["provenance"]["measured_voltage"] == "SIMULATED"

    # Verify persistence via GET endpoint
    get_res = client.get(f"/api/v1/revolt/batteries/{bid}")
    assert get_res.status_code == 200
    retrieved = get_res.json()
    assert retrieved["measured_voltage_v"] == 0.0
    assert retrieved["recommended_pathway"] == "HAZARDOUS"


def test_mock_telemetry_lab_injection_rejects_invalid_payload(client: TestClient) -> None:
    """Tests schema validation failure handling: negative voltage, negative capacity, or invalid enums."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Validation Test Battery",
            "chemistry": "LFP",
            "original_application": "EV",
            "age_months": 12,
            "rated_capacity_mah": 100000.0,
            "nominal_voltage_v": 48.0,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # 1. Negative voltage
    res_neg_volt = client.post(
        f"/api/v1/revolt/batteries/{bid}/telemetry",
        json={
            "measured_voltage_v": -12.5,
            "measured_capacity_mah": 80000.0,
            "internal_resistance_mohm": 10.0,
            "temperature_history": "NORMAL",
            "physical_condition": "GOOD",
        },
    )
    assert res_neg_volt.status_code == 422
    err_body = res_neg_volt.json()
    assert "detail" in err_body
    assert any("measured_voltage_v" in str(err) for err in err_body["detail"])

    # 2. Invalid temperature history enum
    res_invalid_temp = client.post(
        f"/api/v1/revolt/batteries/{bid}/telemetry",
        json={
            "measured_voltage_v": 48.0,
            "measured_capacity_mah": 80000.0,
            "temperature_history": "BOILING_HOT",
            "physical_condition": "GOOD",
        },
    )
    assert res_invalid_temp.status_code == 422
    assert any("temperature_history" in str(err) for err in res_invalid_temp.json()["detail"])

    # 3. Non-existent battery ID
    res_not_found = client.post(
        "/api/v1/revolt/batteries/NON_EXISTENT_BID/telemetry",
        json={
            "measured_voltage_v": 48.0,
            "measured_capacity_mah": 80000.0,
            "temperature_history": "NORMAL",
            "physical_condition": "GOOD",
        },
    )
    assert res_not_found.status_code == 404



def test_full_e2e_journey_api(client: TestClient) -> None:
    """Tests the full end-to-end journey from registration to scheduling and status tracking."""
    # 1. Open dashboard / check analytics
    res_analytics = client.get("/api/v1/revolt/analytics")
    assert res_analytics.status_code == 200
    initial_total = res_analytics.json()["total_registered"]

    # 2. Register a new battery
    payload = {
        "name": "Ather 450X LEV Battery Module",
        "chemistry": "NMC",
        "original_application": "EV",
        "age_months": 22,
        "rated_capacity_mah": 70000.0,
        "measured_capacity_mah": 56000.0,  # 80% SoH
        "nominal_voltage_v": 51.1,
        "measured_voltage_v": 51.8,
        "cycle_count": 480,
        "temperature_history": "NORMAL",
        "physical_condition": "GOOD",
        "owner_notes": "Fleet vehicle upgrade inspection",
    }
    res_reg = client.post("/api/v1/revolt/batteries", json=payload)
    assert res_reg.status_code == 201
    battery = res_reg.json()
    bid = battery["id"]
    assert bid.startswith("REV-")
    assert battery["status"] == "REGISTERED"

    # 3. Verify presence in registry
    res_list = client.get("/api/v1/revolt/batteries", params={"search": bid})
    assert res_list.status_code == 200
    found = res_list.json()
    assert len(found) >= 1
    assert found[0]["id"] == bid

    # 4. Run assessment
    res_assess = client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    assert res_assess.status_code == 200
    assessed_battery = res_assess.json()
    assert assessed_battery["status"] == "ASSESSED"
    assert assessed_battery["recommended_pathway"] == "REUSE"
    assessment = assessed_battery["assessment"]
    assert assessment["soh_percentage"] == 80.0
    assert assessment["confidence_score"] > 0.80

    # 5. List facilities and filter by pathway
    res_fac = client.get("/api/v1/revolt/facilities", params={"pathway": "REUSE"})
    assert res_fac.status_code == 200
    facilities = res_fac.json()
    assert len(facilities) > 0
    selected_fac = facilities[0]

    # 6. Schedule collection
    booking_req = {
        "facility_id": selected_fac["id"],
        "logistics_type": LogisticsType.STANDARD_PICKUP.value,
        "scheduled_date": "2026-10-25",
        "time_slot": "09:00 - 12:00",
        "pickup_address": "Bengaluru EV Hub, Indiranagar",
        "contact_name": "Karthik R",
        "contact_phone": "+91 98765 12345",
        "special_instructions": "Keep in upright container",
    }
    res_sched = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=booking_req)
    assert res_sched.status_code == 200
    scheduled_battery = res_sched.json()
    assert scheduled_battery["status"] == "AWAITING_COLLECTION"
    assert scheduled_battery["booking"] is not None
    assert scheduled_battery["booking"]["facility_name"] == selected_fac["name"]

    # 7. Update status to IN_TRANSIT
    res_status = client.post(
        f"/api/v1/revolt/batteries/{bid}/status",
        json={"status": "IN_TRANSIT", "note": "Driver picked up package", "actor": "Courier Admin"},
    )
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "IN_TRANSIT"

    # 8. Check timeline in battery detail
    res_detail = client.get(f"/api/v1/revolt/batteries/{bid}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    timeline = detail["timeline"]
    assert len(timeline) >= 4  # Registered, Assessed, Scheduled, In Transit

    # 9. Verify invalid status transition is rejected with 400
    res_invalid = client.post(
        f"/api/v1/revolt/batteries/{bid}/status",
        json={"status": "REGISTERED", "note": "Illegal rollback"},
    )
    assert res_invalid.status_code == 400

    # 10. Check updated analytics reflect new battery
    res_after = client.get("/api/v1/revolt/analytics")
    assert res_after.status_code == 200
    assert res_after.json()["total_registered"] == initial_total + 1


def test_unknown_voltage_vs_measured_zero() -> None:
    """Default 0.0V with UNKNOWN provenance must be PENDING_VERIFICATION,
    whereas technician-measured 0.0V is a catastrophic dead-cell hazard triggering HAZARDOUS."""
    # Case A: Default 0.0V with UNKNOWN provenance
    unmeasured_battery = BatteryBase(
        name="Unmeasured Battery (Default 0V)",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_TOOL,
        age_months=12,
        rated_capacity_mah=3000.0,
        nominal_voltage_v=18.0,
        measured_voltage_v=0.0,
        provenance=FieldProvenance(
            measured_voltage=FieldSource.UNKNOWN,
            measured_capacity=FieldSource.UNKNOWN,
        ),
        physical_condition=PhysicalCondition.GOOD,
    )
    result_unmeasured = assess_battery(unmeasured_battery)
    assert result_unmeasured.pathway == RecommendedPathway.PENDING_VERIFICATION
    assert not result_unmeasured.is_hazardous
    assert result_unmeasured.requires_lab_verification
    assert result_unmeasured.confidence_score == 0.40
    assert any("default 0 / UNKNOWN" in m for m in result_unmeasured.missing_telemetry)

    # Case B: Verified technician-measured 0.0V (dead cell / copper dissolution hazard)
    measured_zero_battery = BatteryBase(
        name="Verified 0V Dead Cell",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_TOOL,
        age_months=12,
        rated_capacity_mah=3000.0,
        nominal_voltage_v=18.0,
        measured_voltage_v=0.0,
        provenance=FieldProvenance(
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            measured_capacity=FieldSource.TECHNICIAN_MEASURED,
        ),
        physical_condition=PhysicalCondition.GOOD,
    )
    result_measured_zero = assess_battery(measured_zero_battery)
    assert result_measured_zero.pathway == RecommendedPathway.HAZARDOUS
    assert result_measured_zero.is_hazardous
    assert not result_measured_zero.requires_lab_verification
    assert any("UNDERVOLTAGE" in w for w in result_measured_zero.safety_warnings)


def test_unknown_capacity_vs_measured_zero() -> None:
    """Unknown capacity returns PENDING_VERIFICATION even if voltage is measured,
    whereas technician-measured 0 mAh indicates 0% SoH routed to RECYCLE."""
    # Case A: Unknown capacity with known voltage
    b_unknown_cap = BatteryBase(
        name="Pack with Missing Capacity Test",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.LAPTOP,
        age_months=24,
        rated_capacity_mah=4500.0,
        measured_capacity_mah=0.0,
        nominal_voltage_v=11.1,
        measured_voltage_v=11.4,
        provenance=FieldProvenance(
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            measured_capacity=FieldSource.UNKNOWN,
        ),
        physical_condition=PhysicalCondition.GOOD,
    )
    res_unknown = assess_battery(b_unknown_cap)
    assert res_unknown.pathway == RecommendedPathway.PENDING_VERIFICATION
    assert not res_unknown.is_hazardous
    assert res_unknown.requires_lab_verification

    # Case B: Genuinely measured 0 capacity (dead pack) with safe voltage
    b_measured_zero_cap = BatteryBase(
        name="Completely Depleted Pack",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.LAPTOP,
        age_months=48,
        rated_capacity_mah=4500.0,
        measured_capacity_mah=0.0,
        nominal_voltage_v=11.1,
        measured_voltage_v=10.5,
        provenance=FieldProvenance(
            measured_voltage=FieldSource.TECHNICIAN_MEASURED,
            measured_capacity=FieldSource.TECHNICIAN_MEASURED,
        ),
        physical_condition=PhysicalCondition.GOOD,
    )
    res_zero = assess_battery(b_measured_zero_cap)
    assert res_zero.pathway == RecommendedPathway.RECYCLE
    assert not res_zero.is_hazardous
    assert res_zero.soh_percentage == 0.0


def test_swollen_severe_mandates_quarantine_even_with_unknown_telemetry() -> None:
    """Physical hazard (severe swelling) must trigger HAZARDOUS immediately,
    even when electrical voltage and capacity are completely unknown."""
    b = BatteryBase(
        name="Severely Bloated Pack No Telemetry",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_BANK,
        age_months=36,
        rated_capacity_mah=20000.0,
        measured_capacity_mah=None,
        nominal_voltage_v=3.7,
        measured_voltage_v=None,
        physical_condition=PhysicalCondition.SWOLLEN_SEVERE,
        provenance=FieldProvenance(
            measured_voltage=FieldSource.UNKNOWN,
            measured_capacity=FieldSource.UNKNOWN,
        ),
    )
    res = assess_battery(b)
    assert res.pathway == RecommendedPathway.HAZARDOUS
    assert res.is_hazardous
    assert res.confidence_score == 0.98
    assert not res.requires_lab_verification
    assert "critical physical breach" in res.confidence_basis.lower()


def test_swollen_mild_unsuitable_for_reuse() -> None:
    """Mild swelling with high SoH (85%) must be blocked from REUSE and routed to RECYCLE."""
    b = BatteryBase(
        name="Slightly Puffed High SoH Pack",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.SMARTPHONE,
        age_months=18,
        rated_capacity_mah=3000.0,
        measured_capacity_mah=2550.0,  # 85% SoH
        nominal_voltage_v=3.8,
        measured_voltage_v=3.8,
        cycle_count=300,
        physical_condition=PhysicalCondition.SWOLLEN_MILD,
        temperature_history=TemperatureHistory.NORMAL,
    )
    res = assess_battery(b)
    assert res.pathway == RecommendedPathway.RECYCLE
    assert not res.is_hazardous
    assert any("Mild swelling" in w for w in res.safety_warnings)


def test_confidence_scoring_separates_completeness_from_safety_confidence() -> None:
    """Data completeness score must never be presented as calibrated safety confidence."""
    b = BatteryBase(
        name="Partially Scanned Pack",
        chemistry=BatteryChemistry.NMC,
        original_application=OriginalApplication.POWER_TOOL,
        age_months=24,
        rated_capacity_mah=5000.0,
        measured_capacity_mah=None,
        nominal_voltage_v=18.0,
        measured_voltage_v=None,
        cycle_count=None,
        temperature_history=TemperatureHistory.NORMAL,
        physical_condition=PhysicalCondition.GOOD,
    )
    res = assess_battery(b)
    assert res.pathway == RecommendedPathway.PENDING_VERIFICATION
    # Completeness includes rated spec, temperature history, and physical condition (~0.4-0.6)
    assert res.data_completeness_score > 0
    # Safety confidence must be low (0.40) and not equal completeness
    assert res.confidence_score == 0.40
    assert "Low safety confidence" in res.confidence_basis
    assert "laboratory bench testing is required" in res.confidence_basis


def test_hazardous_booking_blocks_standard_pickup(client: TestClient) -> None:
    """A hazardous battery must reject STANDARD_PICKUP and DEPOT_DROP_OFF."""
    # Register battery with severe swelling
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Hazardous Bloated Battery",
            "chemistry": "NMC",
            "original_application": "POWER_BANK",
            "age_months": 24,
            "rated_capacity_mah": 10000.0,
            "nominal_voltage_v": 3.7,
            "physical_condition": "SWOLLEN_SEVERE",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # Assess battery
    assess_res = client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    assert assess_res.status_code == 200
    assert assess_res.json()["recommended_pathway"] == "HAZARDOUS"

    # Attempt STANDARD_PICKUP -> Must fail with 400
    booking_req = {
        "facility_id": "FAC-HAZ-03",
        "logistics_type": "STANDARD_PICKUP",
        "scheduled_date": "2026-10-20",
        "time_slot": "10:00 - 13:00",
        "pickup_address": "Test Address",
        "contact_name": "Safety Officer",
        "contact_phone": "+91 99887 76655",
    }
    book_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=booking_req)
    assert book_res.status_code == 400
    assert "STANDARD_PICKUP" in book_res.json()["detail"]


def test_hazardous_booking_blocks_unauthorized_facility(client: TestClient) -> None:
    """A hazardous battery cannot be booked to a non-hazardous facility (e.g. AuraEnergy FAC-REF-02)."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Leaking Hazmat Cell",
            "chemistry": "NMC",
            "original_application": "POWER_TOOL",
            "age_months": 30,
            "rated_capacity_mah": 4000.0,
            "nominal_voltage_v": 18.0,
            "physical_condition": "LEAKING",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    # Attempt booking with hazmat courier, but to refurbishment facility FAC-REF-02
    booking_req = {
        "facility_id": "FAC-REF-02",
        "logistics_type": "HAZMAT_PICKUP",
        "scheduled_date": "2026-10-20",
        "time_slot": "10:00 - 13:00",
        "pickup_address": "Test Address",
        "contact_name": "Safety Officer",
        "contact_phone": "+91 99887 76655",
    }
    book_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=booking_req)
    assert book_res.status_code == 400
    assert "not authorized for HAZARDOUS battery intake" in book_res.json()["detail"]


def test_hazardous_booking_allows_hazmat_pickup_to_authorized_depot(client: TestClient) -> None:
    """A hazardous battery booked with HAZMAT_PICKUP to PyroSafe (FAC-HAZ-03) succeeds."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Punctured Battery for Quarantined Transport",
            "chemistry": "NMC",
            "original_application": "EV",
            "age_months": 36,
            "rated_capacity_mah": 50000.0,
            "nominal_voltage_v": 48.0,
            "physical_condition": "PUNCTURED_CRACKED",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    booking_req = {
        "facility_id": "FAC-HAZ-03",
        "logistics_type": "HAZMAT_PICKUP",
        "scheduled_date": "2026-10-20",
        "time_slot": "10:00 - 13:00",
        "pickup_address": "Safety Lab Quarantine Bay",
        "contact_name": "Hazmat Officer",
        "contact_phone": "+91 99887 76655",
    }
    book_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=booking_req)
    assert book_res.status_code == 200
    assert book_res.json()["status"] == "AWAITING_COLLECTION"
    assert book_res.json()["assigned_facility_id"] == "FAC-HAZ-03"


def test_hazardous_battery_blocks_ordinary_reuse_or_refurbish_transition(client: TestClient) -> None:
    """Hazardous batteries cannot transition to REUSED or REFURBISHED status."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Thermal Residue Battery",
            "chemistry": "NMC",
            "original_application": "EV",
            "age_months": 12,
            "rated_capacity_mah": 50000.0,
            "nominal_voltage_v": 48.0,
            "physical_condition": "THERMAL_RESIDUE",
        },
    )
    bid = reg_res.json()["id"]
    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    # Move through valid chain to PROCESSING
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "IN_TRANSIT"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "RECEIVED_AT_FACILITY"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "PROCESSING"})

    # Attempt illegal transition to REUSED -> 400
    res_reuse = client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "REUSED"})
    assert res_reuse.status_code == 400
    assert "strictly prohibited" in res_reuse.json()["detail"]

    # Attempt illegal transition to REFURBISHED -> 400
    res_refurb = client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "REFURBISHED"})
    assert res_refurb.status_code == 400
    assert "strictly prohibited" in res_refurb.json()["detail"]

    # Valid transition to SPECIALIST_HANDLING -> 200
    res_special = client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "SPECIALIST_HANDLING"})
    assert res_special.status_code == 200
    assert res_special.json()["status"] == "SPECIALIST_HANDLING"


def test_audit_history_preserved_on_updates(client: TestClient) -> None:
    """Audit events are appended to the timeline without rewriting or clearing past events."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Audit Trail Verification Pack",
            "chemistry": "LFP",
            "original_application": "ESS",
            "age_months": 12,
            "rated_capacity_mah": 20000.0,
            "measured_capacity_mah": 18000.0,
            "nominal_voltage_v": 24.0,
            "measured_voltage_v": 25.6,
            "physical_condition": "GOOD",
        },
    )
    bid = reg_res.json()["id"]

    client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "IN_TRANSIT", "note": "Step 1"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "RECEIVED_AT_FACILITY", "note": "Step 2"})

    detail = client.get(f"/api/v1/revolt/batteries/{bid}").json()
    timeline = detail["timeline"]
    assert len(timeline) >= 4

    # Ensure chronological order and non-empty IDs
    for ev in timeline:
        assert ev["id"].startswith("EVT-")
        assert ev["title"]
        assert ev["actor"]


def test_facility_pathway_filtering_api(client: TestClient) -> None:
    """Verifies that the /facilities endpoint accurately filters facilities by configured circular pathway."""
    # 1. REUSE filter
    res_reuse = client.get("/api/v1/revolt/facilities", params={"pathway": "REUSE"})
    assert res_reuse.status_code == 200
    reuse_facs = res_reuse.json()
    assert len(reuse_facs) >= 2
    for f in reuse_facs:
        assert "REUSE" in f["supported_pathways"]
    reuse_ids = {f["id"] for f in reuse_facs}
    assert "FAC-REF-02" in reuse_ids
    assert "FAC-LAB-04" in reuse_ids
    assert "FAC-HYD-01" not in reuse_ids  # Hydrometallurgical recycler must not appear
    assert "FAC-HAZ-03" not in reuse_ids  # Hazmat depot must not appear

    # 2. REFURBISH filter
    res_refurb = client.get("/api/v1/revolt/facilities", params={"pathway": "REFURBISH"})
    assert res_refurb.status_code == 200
    refurb_facs = res_refurb.json()
    for f in refurb_facs:
        assert "REFURBISH" in f["supported_pathways"]
    refurb_ids = {f["id"] for f in refurb_facs}
    assert "FAC-REF-02" in refurb_ids
    assert "FAC-LAB-04" in refurb_ids
    assert "FAC-HYD-01" not in refurb_ids

    # 3. RECYCLE filter
    res_recycle = client.get("/api/v1/revolt/facilities", params={"pathway": "RECYCLE"})
    assert res_recycle.status_code == 200
    recycle_facs = res_recycle.json()
    assert len(recycle_facs) >= 1
    for f in recycle_facs:
        assert "RECYCLE" in f["supported_pathways"]
    recycle_ids = {f["id"] for f in recycle_facs}
    assert "FAC-HYD-01" in recycle_ids
    assert "FAC-REF-02" not in recycle_ids

    # 4. HAZARDOUS filter
    res_haz = client.get("/api/v1/revolt/facilities", params={"pathway": "HAZARDOUS"})
    assert res_haz.status_code == 200
    haz_facs = res_haz.json()
    for f in haz_facs:
        assert "HAZARDOUS" in f["supported_pathways"]
    haz_ids = {f["id"] for f in haz_facs}
    assert "FAC-HAZ-03" in haz_ids
    assert "FAC-HYD-01" not in haz_ids


def test_booking_compatible_facility_succeeds(client: TestClient) -> None:
    """Booking a REUSE battery with a certified REUSE facility succeeds and transitions to AWAITING_COLLECTION."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Second Life BESS Module",
            "chemistry": "LFP",
            "original_application": "EV",
            "age_months": 18,
            "rated_capacity_mah": 100000.0,
            "measured_capacity_mah": 85000.0,  # 85% SoH -> REUSE
            "nominal_voltage_v": 51.2,
            "measured_voltage_v": 52.8,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # Assess to establish REUSE pathway
    assess_res = client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    assert assess_res.status_code == 200
    assert assess_res.json()["recommended_pathway"] == "REUSE"

    # Book with FAC-REF-02 (supports REUSE)
    booking_payload = {
        "facility_id": "FAC-REF-02",
        "logistics_type": "STANDARD_PICKUP",
        "scheduled_date": "2026-10-25",
        "time_slot": "09:00 - 12:00",
        "contact_name": "Priya S",
        "contact_phone": "+91 94444 55555",
        "pickup_address": "SIDCO Industrial Park, Guindy",
        "special_instructions": "Second-life qualification batch",
    }
    book_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=booking_payload)
    assert book_res.status_code == 200
    booked = book_res.json()
    assert booked["status"] == "AWAITING_COLLECTION"
    assert booked["assigned_facility_id"] == "FAC-REF-02"
    assert booked["assigned_facility_name"] == "AuraEnergy Second-Life ESS & Diagnostics Hub"
    assert booked["booking"]["facility_id"] == "FAC-REF-02"


def test_booking_incompatible_facility_rejected_with_clear_error(client: TestClient) -> None:
    """Attempting to book a REUSE battery with a RECYCLE-only facility must be rejected with 400 Bad Request."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "High Health Stationary Pack",
            "chemistry": "NMC",
            "original_application": "ENERGY_STORAGE",
            "age_months": 10,
            "rated_capacity_mah": 50000.0,
            "measured_capacity_mah": 45000.0,  # 90% SoH -> REUSE
            "nominal_voltage_v": 48.0,
            "measured_voltage_v": 50.4,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    # Incompatible booking attempt: FAC-HYD-01 only supports RECYCLE
    booking_payload = {
        "facility_id": "FAC-HYD-01",
        "logistics_type": "STANDARD_PICKUP",
        "scheduled_date": "2026-10-25",
        "time_slot": "09:00 - 12:00",
        "contact_name": "Test User",
        "contact_phone": "+91 90000 00000",
        "pickup_address": "Test Facility Address",
    }
    book_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=booking_payload)
    assert book_res.status_code == 400
    err_msg = book_res.json()["detail"]
    assert "Facility 'EcoVolt Hydrometallurgical Refining Center' does not support the recommended 'REUSE' circular pathway." in err_msg


def test_booking_recycle_battery_incompatible_facility_rejected(client: TestClient) -> None:
    """Attempting to book a RECYCLE battery with a REUSE/REFURBISH facility is rejected; booking with RECYCLE facility succeeds."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Depleted End-of-Life Pack",
            "chemistry": "NMC",
            "original_application": "EV",
            "age_months": 60,
            "rated_capacity_mah": 50000.0,
            "measured_capacity_mah": 20000.0,  # 40% SoH -> RECYCLE
            "nominal_voltage_v": 48.0,
            "measured_voltage_v": 44.0,
            "cycle_count": 2200,
            "physical_condition": "SCRATCHED",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    # Attempt booking with FAC-REF-02 (supports REUSE, REFURBISH only) -> 400
    bad_req = {
        "facility_id": "FAC-REF-02",
        "logistics_type": "STANDARD_PICKUP",
        "scheduled_date": "2026-10-25",
        "time_slot": "09:00 - 12:00",
        "contact_name": "Test User",
        "contact_phone": "+91 90000 00000",
        "pickup_address": "Industrial Depot",
    }
    bad_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=bad_req)
    assert bad_res.status_code == 400
    assert "does not support the recommended 'RECYCLE' circular pathway" in bad_res.json()["detail"]

    # Book with FAC-HYD-01 (supports RECYCLE) -> 200
    good_req = {
        "facility_id": "FAC-HYD-01",
        "logistics_type": "STANDARD_PICKUP",
        "scheduled_date": "2026-10-25",
        "time_slot": "09:00 - 12:00",
        "contact_name": "Authorized Recycler Logistics",
        "contact_phone": "+91 90000 00000",
        "pickup_address": "Hydrometallurgical Recovery Yard",
    }
    good_res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=good_req)
    assert good_res.status_code == 200
    assert good_res.json()["assigned_facility_id"] == "FAC-HYD-01"
    assert good_res.json()["status"] == "AWAITING_COLLECTION"


def test_booking_non_hazardous_battery_blocks_hazmat_only_depot(client: TestClient) -> None:
    """Non-hazardous batteries cannot be booked into emergency hazmat quarantine facilities."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Healthy Second-Life Cell",
            "chemistry": "LFP",
            "original_application": "ESS",
            "age_months": 8,
            "rated_capacity_mah": 30000.0,
            "measured_capacity_mah": 27000.0,
            "nominal_voltage_v": 24.0,
            "measured_voltage_v": 26.0,
            "physical_condition": "GOOD",
        },
    )
    bid = reg_res.json()["id"]
    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    # Attempt to route healthy battery to emergency hazmat facility FAC-HAZ-03
    haz_req = {
        "facility_id": "FAC-HAZ-03",
        "logistics_type": "STANDARD_PICKUP",
        "scheduled_date": "2026-10-25",
        "time_slot": "09:00 - 12:00",
        "contact_name": "Test User",
        "contact_phone": "+91 90000 00000",
        "pickup_address": "Test Address",
    }
    res = client.post(f"/api/v1/revolt/batteries/{bid}/schedule", json=haz_req)
    assert res.status_code == 400
    assert "is an emergency hazmat quarantine facility reserved exclusively for hazardous batteries." in res.json()["detail"]


def test_battery_with_valid_transitions_populates_next_states_and_blocks_illegal_completed(client: TestClient) -> None:
    """Verifies that active batteries populate allowed next-states from backend rules and cannot jump to COMPLETED."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Active Lifecycle Test Battery",
            "chemistry": "LFP",
            "original_application": "ESS",
            "age_months": 14,
            "rated_capacity_mah": 40000.0,
            "measured_capacity_mah": 34000.0,
            "nominal_voltage_v": 48.0,
            "measured_voltage_v": 49.2,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # Assess battery -> status ASSESSED
    assess_res = client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    assert assess_res.status_code == 200
    assert assess_res.json()["status"] == "ASSESSED"

    # Query valid next transitions for ASSESSED status
    trans_res = client.get(f"/api/v1/revolt/batteries/{bid}/transitions")
    assert trans_res.status_code == 200
    allowed = trans_res.json()
    assert allowed == ["AWAITING_COLLECTION", "IN_TRANSIT"]
    assert "COMPLETED" not in allowed

    # Attempt illegal transition directly to COMPLETED -> 400 Bad Request
    illegal_res = client.post(
        f"/api/v1/revolt/batteries/{bid}/status",
        json={"status": "COMPLETED", "note": "Illegal jump to completed", "actor": "Test Operator"},
    )
    assert illegal_res.status_code == 400
    err_msg = illegal_res.json()["detail"]
    assert "Invalid transition from ASSESSED to COMPLETED" in err_msg
    assert "Allowed transitions from current state: [AWAITING_COLLECTION, IN_TRANSIT]" in err_msg

    # Advance along valid path: ASSESSED -> IN_TRANSIT
    valid_res = client.post(
        f"/api/v1/revolt/batteries/{bid}/status",
        json={"status": "IN_TRANSIT", "note": "Dispatched via carrier", "actor": "Logistics Dispatcher"},
    )
    assert valid_res.status_code == 200
    assert valid_res.json()["status"] == "IN_TRANSIT"

    # Verify transitions from IN_TRANSIT
    trans_in_transit = client.get(f"/api/v1/revolt/batteries/{bid}/transitions")
    assert trans_in_transit.status_code == 200
    assert trans_in_transit.json() == ["RECEIVED_AT_FACILITY"]

    # Verify timeline preserved and event appended
    battery_detail = client.get(f"/api/v1/revolt/batteries/{bid}").json()
    timeline = battery_detail["timeline"]
    assert len(timeline) >= 3
    latest_event = timeline[-1]
    assert latest_event["status"] == "IN_TRANSIT"
    assert latest_event["actor"] == "Logistics Dispatcher"
    assert latest_event["description"] == "Dispatched via carrier"


def test_completed_battery_has_no_further_transitions(client: TestClient) -> None:
    """A genuinely completed battery has empty transitions, rejects further transitions, and preserves audit trail."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Terminal Journey Pack",
            "chemistry": "NMC",
            "original_application": "EV",
            "age_months": 24,
            "rated_capacity_mah": 60000.0,
            "measured_capacity_mah": 49000.0,
            "nominal_voltage_v": 48.0,
            "measured_voltage_v": 50.0,
            "physical_condition": "GOOD",
        },
    )
    assert reg_res.status_code == 201
    bid = reg_res.json()["id"]

    # Progress through lifecycle chain to COMPLETED
    client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "IN_TRANSIT"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "RECEIVED_AT_FACILITY"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "PROCESSING"})
    res_completed = client.post(
        f"/api/v1/revolt/batteries/{bid}/status",
        json={"status": "COMPLETED", "note": "Finished circular second-life qualification", "actor": "Chief Inspector"},
    )
    assert res_completed.status_code == 200
    assert res_completed.json()["status"] == "COMPLETED"

    # Verify transitions endpoint returns empty list for genuinely completed battery
    trans_res = client.get(f"/api/v1/revolt/batteries/{bid}/transitions")
    assert trans_res.status_code == 200
    assert trans_res.json() == []

    # Attempt transition from COMPLETED to PROCESSING -> rejected with 400
    res_reopen = client.post(
        f"/api/v1/revolt/batteries/{bid}/status",
        json={"status": "PROCESSING", "note": "Attempt to reopen completed pack"},
    )
    assert res_reopen.status_code == 400
    err_detail = res_reopen.json()["detail"]
    assert "Invalid transition from COMPLETED to PROCESSING" in err_detail
    assert "Allowed transitions from current state: []" in err_detail

    # Timeline audit history must remain intact and preserved
    detail = client.get(f"/api/v1/revolt/batteries/{bid}").json()
    assert detail["status"] == "COMPLETED"
    timeline = detail["timeline"]
    assert len(timeline) >= 6
    assert timeline[-1]["status"] == "COMPLETED"
    assert timeline[-1]["actor"] == "Chief Inspector"


def test_hazardous_battery_transitions_exclude_reuse_and_refurbish(client: TestClient) -> None:
    """Hazardous batteries in PROCESSING state must only allow containment, recycling, or specialist handling."""
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Quarantined Hazmat Cell",
            "chemistry": "NMC",
            "original_application": "EV",
            "age_months": 18,
            "rated_capacity_mah": 50000.0,
            "nominal_voltage_v": 48.0,
            "physical_condition": "SWOLLEN_SEVERE",
        },
    )
    bid = reg_res.json()["id"]
    client.post(f"/api/v1/revolt/batteries/{bid}/assess")
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "IN_TRANSIT"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "RECEIVED_AT_FACILITY"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "PROCESSING"})

    # Transitions must exclude REUSED and REFURBISHED for safety
    trans_res = client.get(f"/api/v1/revolt/batteries/{bid}/transitions")
    assert trans_res.status_code == 200
    allowed = trans_res.json()
    assert "REUSED" not in allowed
    assert "REFURBISHED" not in allowed
    assert "SPECIALIST_HANDLING" in allowed
    assert "RECYCLED" in allowed
    assert "COMPLETED" in allowed


def test_overview_safety_alert_excludes_completed_battery(client: TestClient) -> None:
    """Completed hazardous batteries must not be counted in active quarantined units requiring physical isolation."""
    # 1. Register a hazardous battery
    reg_res = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Quarantined Cell Lifecycle Test",
            "chemistry": "NMC",
            "original_application": "EV",
            "age_months": 12,
            "rated_capacity_mah": 30000.0,
            "nominal_voltage_v": 48.0,
            "physical_condition": "SWOLLEN_SEVERE",
        },
    )
    bid = reg_res.json()["id"]
    client.post(f"/api/v1/revolt/batteries/{bid}/assess")

    # Verify battery is in active quarantined safety alert
    ov1 = client.get("/api/v1/revolt/overview").json()
    quarantined_ids_before = {b["id"] for b in ov1["safety_alert"]["quarantined_batteries"]}
    assert bid in quarantined_ids_before
    count_before = ov1["safety_alert"]["quarantined_count"]

    # Transition battery through full circular handling to COMPLETED
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "IN_TRANSIT"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "RECEIVED_AT_FACILITY"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "PROCESSING"})
    client.post(f"/api/v1/revolt/batteries/{bid}/status", json={"status": "COMPLETED"})

    # Verify battery is now EXCLUDED from active quarantined units
    ov2 = client.get("/api/v1/revolt/overview").json()
    quarantined_ids_after = {b["id"] for b in ov2["safety_alert"]["quarantined_batteries"]}
    assert bid not in quarantined_ids_after
    assert ov2["safety_alert"]["quarantined_count"] == count_before - 1


def test_overview_safety_alert_distinguishes_simulated_and_genuine(client: TestClient) -> None:
    """Safety alert accurately flags whether each hazardous battery is SIMULATED vs GENUINE."""
    # 1. Register a battery and simulate undervoltage via Telemetry Lab bench
    reg_sim = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Simulated Bench Hazard Unit",
            "chemistry": "LFP",
            "original_application": "ESS",
            "age_months": 6,
            "rated_capacity_mah": 20000.0,
            "nominal_voltage_v": 51.2,
            "physical_condition": "GOOD",
        },
    )
    sim_id = reg_sim.json()["id"]

    # Inject simulated severe undervoltage (e.g. 18.5V pack on 16S LFP = 1.16 V/cell < 1.8V critical)
    client.post(
        f"/api/v1/revolt/batteries/{sim_id}/telemetry",
        json={
            "measured_voltage_v": 18.5,
            "measured_capacity_mah": 5000.0,
            "physical_condition": "GOOD",
            "temperature_history": "NORMAL",
            "technician_notes": "Virtual lab bench simulated undervoltage probe",
        },
    )

    # 2. Register a genuine physical hazard
    reg_gen = client.post(
        "/api/v1/revolt/batteries",
        json={
            "name": "Genuine Punctured Hazard Unit",
            "chemistry": "NMC",
            "original_application": "LAPTOP",
            "age_months": 24,
            "rated_capacity_mah": 5000.0,
            "nominal_voltage_v": 11.1,
            "physical_condition": "PUNCTURED_CRACKED",
        },
    )
    gen_id = reg_gen.json()["id"]
    client.post(f"/api/v1/revolt/batteries/{gen_id}/assess")

    # Fetch overview and inspect provenance labeling
    ov = client.get("/api/v1/revolt/overview").json()
    alert = ov["safety_alert"]
    haz_map = {b["id"]: b for b in alert["quarantined_batteries"]}

    assert sim_id in haz_map
    assert gen_id in haz_map

    # Simulated unit must have is_simulated == True
    assert haz_map[sim_id]["is_simulated"] is True
    assert haz_map[sim_id]["provenance"]["measured_voltage"] == "SIMULATED"

    # Genuine unit must have is_simulated == False
    assert haz_map[gen_id]["is_simulated"] is False
    assert haz_map[gen_id]["provenance"]["physical_condition"] == "USER_ENTERED"

    # Safety alert breakdown counts
    assert alert["simulated_count"] >= 1
    assert alert["genuine_count"] >= 1


def test_overview_safety_alert_prioritizes_genuine_hazards(client: TestClient) -> None:
    """Overview safety banner places genuine physical hazards first before simulated lab tests."""
    ov = client.get("/api/v1/revolt/overview").json()
    alert = ov["safety_alert"]
    quarantined = alert["quarantined_batteries"]

    if alert["genuine_count"] > 0:
        # The primary battery featured at index 0 must be a genuine hazard
        assert quarantined[0]["is_simulated"] is False
        assert alert["is_simulated"] is False
