"""ReVolt Deterministic Battery Assessment Engine.

A transparent, explainable decision engine evaluating lithium-ion battery health,
chemistry-specific operating windows, degradation factors, and critical safety hazards.

Label: Prototype assessment engine — explainable deterministic rule evaluation.
Not a certified laboratory safety determination.
"""

from datetime import UTC, datetime

from src.packages.revolt.models import (
    AssessmentResult,
    BatteryBase,
    BatteryChemistry,
    FieldSource,
    PhysicalCondition,
    RecommendedPathway,
    TemperatureHistory,
)

# Chemistry-specific voltage limits (per cell / normalized)
CHEMISTRY_VOLTAGE_LIMITS = {
    BatteryChemistry.NMC: {
        "nominal": 3.7,
        "safe_min": 3.0,
        "safe_max": 4.2,
        "critical_min": 2.0,  # Copper dendrite formation below this
        "critical_max": 4.35,  # Electrolyte decomposition / thermal runaway risk
    },
    BatteryChemistry.LFP: {
        "nominal": 3.2,
        "safe_min": 2.5,
        "safe_max": 3.65,
        "critical_min": 1.8,
        "critical_max": 3.85,
    },
    BatteryChemistry.LCO: {
        "nominal": 3.7,
        "safe_min": 3.0,
        "safe_max": 4.2,
        "critical_min": 2.2,
        "critical_max": 4.35,
    },
    BatteryChemistry.LMO: {
        "nominal": 3.7,
        "safe_min": 3.0,
        "safe_max": 4.2,
        "critical_min": 2.2,
        "critical_max": 4.30,
    },
    BatteryChemistry.NCA: {
        "nominal": 3.6,
        "safe_min": 3.0,
        "safe_max": 4.2,
        "critical_min": 2.0,
        "critical_max": 4.35,
    },
    BatteryChemistry.OTHER: {
        "nominal": 3.7,
        "safe_min": 2.8,
        "safe_max": 4.2,
        "critical_min": 1.8,
        "critical_max": 4.4,
    },
}

# Critical physical hazard conditions that mandate quarantine
CRITICAL_PHYSICAL_HAZARDS = {
    PhysicalCondition.SWOLLEN_SEVERE: (
        "Severe cell pouch bulging / internal pressure buildup detected"
    ),
    PhysicalCondition.PUNCTURED_CRACKED: (
        "Physical breach, puncture, or cracked casing exposing core"
    ),
    PhysicalCondition.LEAKING: "Electrolyte chemical leakage or toxic odor detected",
    PhysicalCondition.THERMAL_RESIDUE: "Charring, melted insulation, or combustion soot detected",
}


def assess_battery(battery: BatteryBase) -> AssessmentResult:
    """Evaluates battery condition and telemetry to determine a safe, optimal pathway.

    Follows a strict hierarchy:
    1. Independent Safety Red Flags (Mandatory HAZARDOUS isolation pathway regardless of telemetry)
    2. Measured Critical Electrical Hazards (Undervoltage dendrite or overvoltage runaway)
    3. Telemetry Completeness & Insufficient Data Check (PENDING_VERIFICATION)
    4. Circular Qualification (REUSE vs REFURBISH vs RECYCLE)
    """
    safety_warnings: list[str] = []
    contributing_factors: list[str] = []
    missing_telemetry: list[str] = []

    # 1. Telemetry completeness tracking (distinct from safety confidence)
    telemetry_points = 0
    max_telemetry_points = 5

    # Determine if electrical telemetry is genuinely measured vs unknown/default-zero
    is_voltage_known = (
        battery.measured_voltage_v is not None
        and battery.provenance.measured_voltage != FieldSource.UNKNOWN
    )
    is_capacity_known = (
        battery.measured_capacity_mah is not None
        and battery.provenance.measured_capacity != FieldSource.UNKNOWN
    )
    is_cycles_known = (
        battery.cycle_count is not None
        and battery.provenance.cycle_count != FieldSource.UNKNOWN
    )

    limits = CHEMISTRY_VOLTAGE_LIMITS.get(
        battery.chemistry, CHEMISTRY_VOLTAGE_LIMITS[BatteryChemistry.OTHER]
    )
    series_cells = max(1, round(battery.nominal_voltage_v / limits["nominal"]))

    # Measured voltage telemetry
    cell_voltage: float | None = None
    if is_voltage_known:
        telemetry_points += 1
        assert battery.measured_voltage_v is not None
        cell_voltage = battery.measured_voltage_v / series_cells
        contributing_factors.append(
            f"Voltage Telemetry: {battery.measured_voltage_v:.2f}V pack (~{cell_voltage:.2f}V/cell "
            f"across {series_cells}S; {battery.chemistry.value} nominal {limits['nominal']}V)"
        )
    else:
        if battery.measured_voltage_v == 0.0 or battery.measured_voltage_v == 0:
            missing_telemetry.append("Measured voltage is default 0 / UNKNOWN (not an actual reading).")
        else:
            missing_telemetry.append("Open-circuit measured voltage missing.")

    # Measured capacity telemetry & SoH
    soh_percentage: float | None = None
    if is_capacity_known:
        telemetry_points += 1
        assert battery.measured_capacity_mah is not None
        soh_percentage = round((battery.measured_capacity_mah / battery.rated_capacity_mah) * 100, 1)
        contributing_factors.append(
            f"State of Health (SoH): {soh_percentage}% "
            f"({battery.measured_capacity_mah:.0f} mAh / {battery.rated_capacity_mah:.0f} mAh)"
        )
    else:
        if battery.measured_capacity_mah == 0.0 or battery.measured_capacity_mah == 0:
            missing_telemetry.append("Measured capacity is default 0 / UNKNOWN (not an actual reading).")
        else:
            missing_telemetry.append(
                "Measured remaining usable capacity missing (printed label shows rated only)."
            )

    # Cycles
    if is_cycles_known:
        telemetry_points += 1
        contributing_factors.append(
            f"Recorded Cycles: {battery.cycle_count} charge cycles completed"
        )
    else:
        missing_telemetry.append("Cycle count telemetry not recorded by user/BMS.")

    # Thermal history
    if battery.temperature_history != TemperatureHistory.UNKNOWN:
        telemetry_points += 1
        contributing_factors.append(
            f"Thermal Profile: {battery.temperature_history.value} operating history"
        )
    else:
        missing_telemetry.append("Thermal excursion history unmonitored.")

    # Physical inspection
    telemetry_points += 1
    contributing_factors.append(f"Physical Inspection: {battery.physical_condition.value}")

    data_completeness = round(telemetry_points / max_telemetry_points, 2)

    # -------------------------------------------------------------
    # STAGE 1: INDEPENDENT PHYSICAL & THERMAL RED FLAGS
    # -------------------------------------------------------------
    is_physical_hazard = battery.physical_condition in CRITICAL_PHYSICAL_HAZARDS
    is_thermal_hazard = battery.temperature_history == TemperatureHistory.EXTREME

    if is_physical_hazard or is_thermal_hazard:
        if is_physical_hazard:
            hazard_desc = CRITICAL_PHYSICAL_HAZARDS[battery.physical_condition]
            safety_warnings.append(f"CRITICAL SAFETY VIOLATION: {hazard_desc}.")
        if is_thermal_hazard:
            safety_warnings.append(
                "THERMAL RUNAWAY HAZARD: Extreme temperature event recorded. "
                "High risk of cell internal short circuit or off-gassing."
            )
        recommended_next_steps = [
            "IMMEDIATELY ISOLATE: Place battery into a non-flammable, sand-filled or vermiculite fire-safe container.",
            "DO NOT ATTEMPT RECHARGE OR TESTING: Do not connect to any load, charger, or multimeter probe.",
            "QUARANTINE TRANSPORT: Schedule dispatch exclusively through a certified hazardous materials (Hazmat / UN3480) courier.",
            "SPECIALIST RECOVERY: Route to an authorized hazardous disposal and high-containment pyrometallurgical facility.",
        ]
        return AssessmentResult(
            assessed_at=datetime.now(UTC),
            pathway=RecommendedPathway.HAZARDOUS,
            confidence_score=0.98,
            confidence_basis=(
                "High safety confidence (0.98): Independently established critical physical breach "
                "or thermal runaway history mandates immediate physical quarantine regardless of electrical telemetry."
            ),
            data_completeness_score=data_completeness,
            soh_percentage=soh_percentage,
            is_hazardous=True,
            safety_warnings=safety_warnings,
            contributing_factors=contributing_factors,
            recommended_next_steps=recommended_next_steps,
            missing_telemetry=missing_telemetry,
            requires_lab_verification=False,
        )

    # -------------------------------------------------------------
    # STAGE 2: MEASURED CRITICAL ELECTRICAL HAZARDS
    # -------------------------------------------------------------
    if is_voltage_known and cell_voltage is not None:
        if cell_voltage <= limits["critical_min"]:
            safety_warnings.append(
                f"SEVERE UNDERVOLTAGE RISK: Cell voltage {cell_voltage:.2f}V is below "
                f"critical threshold {limits['critical_min']}V. Severe risk of copper anode "
                f"dissolution and internal micro-shorts upon recharge."
            )
            recommended_next_steps = [
                "IMMEDIATELY ISOLATE: Place battery into a non-flammable, sand-filled or vermiculite fire-safe container.",
                "DO NOT ATTEMPT RECHARGE OR TESTING: Do not connect to any load, charger, or multimeter probe.",
                "QUARANTINE TRANSPORT: Schedule dispatch exclusively through a certified hazardous materials (Hazmat / UN3480) courier.",
                "SPECIALIST RECOVERY: Route to an authorized hazardous disposal and high-containment pyrometallurgical facility.",
            ]
            return AssessmentResult(
                assessed_at=datetime.now(UTC),
                pathway=RecommendedPathway.HAZARDOUS,
                confidence_score=0.96,
                confidence_basis=(
                    f"High safety confidence (0.96): Verified cell voltage ({cell_voltage:.2f}V) is at or below "
                    f"copper dissolution threshold ({limits['critical_min']}V). Catastrophic internal short hazard."
                ),
                data_completeness_score=data_completeness,
                soh_percentage=soh_percentage,
                is_hazardous=True,
                safety_warnings=safety_warnings,
                contributing_factors=contributing_factors,
                recommended_next_steps=recommended_next_steps,
                missing_telemetry=missing_telemetry,
                requires_lab_verification=False,
            )
        elif cell_voltage >= limits["critical_max"]:
            safety_warnings.append(
                f"CRITICAL OVERVOLTAGE HAZARD: Cell voltage {cell_voltage:.2f}V exceeds "
                f"safe ceiling {limits['critical_max']}V. Severe risk of cathode phase change, "
                f"oxygen release, and active thermal runaway."
            )
            recommended_next_steps = [
                "IMMEDIATELY ISOLATE: Place battery into a non-flammable, sand-filled or vermiculite fire-safe container.",
                "DO NOT ATTEMPT RECHARGE OR TESTING: Do not connect to any load, charger, or multimeter probe.",
                "QUARANTINE TRANSPORT: Schedule dispatch exclusively through a certified hazardous materials (Hazmat / UN3480) courier.",
                "SPECIALIST RECOVERY: Route to an authorized hazardous disposal and high-containment pyrometallurgical facility.",
            ]
            return AssessmentResult(
                assessed_at=datetime.now(UTC),
                pathway=RecommendedPathway.HAZARDOUS,
                confidence_score=0.96,
                confidence_basis=(
                    f"High safety confidence (0.96): Verified cell voltage ({cell_voltage:.2f}V) exceeds "
                    f"thermal runaway ceiling ({limits['critical_max']}V). Immediate fire hazard."
                ),
                data_completeness_score=data_completeness,
                soh_percentage=soh_percentage,
                is_hazardous=True,
                safety_warnings=safety_warnings,
                contributing_factors=contributing_factors,
                recommended_next_steps=recommended_next_steps,
                missing_telemetry=missing_telemetry,
                requires_lab_verification=False,
            )

    # -------------------------------------------------------------
    # STAGE 3: INSUFFICIENT EVIDENCE (Unmeasured Telemetry)
    # -------------------------------------------------------------
    if not is_voltage_known or not is_capacity_known:
        if not is_voltage_known and not is_capacity_known:
            contributing_factors.append(
                "Insufficient electrical telemetry: Capacity, voltage, and cycle count are unmeasured."
            )
        else:
            contributing_factors.append(
                "Insufficient electrical telemetry: Operational voltage or capacity is unmeasured."
            )
        safety_warnings.append(
            "Missing measurements must not be treated as proof of health or safety."
        )
        recommended_next_steps = [
            "LAB BENCH VERIFICATION REQUIRED: Measured electrical telemetry (voltage/capacity) is incomplete.",
            "Route battery to an authorized facility for open-circuit voltage check.",
            "Conduct controlled 0.2C laboratory test to establish verified State of Health.",
            "Perform AC impedance spectroscopy to verify cell internal resistance.",
        ]
        return AssessmentResult(
            assessed_at=datetime.now(UTC),
            pathway=RecommendedPathway.PENDING_VERIFICATION,
            confidence_score=0.40,
            confidence_basis=(
                "Low safety confidence (0.40): Essential electrical telemetry is unmeasured or unverified. "
                "Data completeness is not proof of safety; laboratory bench testing is required before circular routing."
            ),
            data_completeness_score=data_completeness,
            soh_percentage=None,
            is_hazardous=False,
            safety_warnings=safety_warnings,
            contributing_factors=contributing_factors,
            recommended_next_steps=recommended_next_steps,
            missing_telemetry=missing_telemetry,
            requires_lab_verification=True,
        )

    # -------------------------------------------------------------
    # STAGE 4: CIRCULAR QUALIFICATION (Both Voltage & Capacity Verified)
    # -------------------------------------------------------------
    assert soh_percentage is not None
    assert cell_voltage is not None

    # Minor warnings (non-quarantine)
    if cell_voltage < limits["safe_min"]:
        safety_warnings.append(
            f"Depleted cell voltage: {cell_voltage:.2f}V is below nominal operational minimum "
            f"({limits['safe_min']}V). Requires slow trickle restoration."
        )
    if battery.temperature_history == TemperatureHistory.OVERHEATED:
        safety_warnings.append(
            "Thermal stress: Operating history indicates prior elevated temperatures (>60°C). "
            "Accelerated SEI layer growth expected."
        )
    if battery.physical_condition == PhysicalCondition.SWOLLEN_MILD:
        safety_warnings.append(
            "Mild swelling detected: Early pouch gas accumulation. Unsuitable for second-life reuse; "
            "requires controlled discharge and recycling."
        )

    # A. REUSE: High residual health, intact casing (no SWOLLEN_MILD, no CORRODED_TERMINALS), normal voltage window
    if (
        soh_percentage >= 75.0
        and (battery.cycle_count is None or battery.cycle_count <= 1200)
        and battery.physical_condition in [PhysicalCondition.GOOD, PhysicalCondition.SCRATCHED]
        and battery.temperature_history in [TemperatureHistory.NORMAL, TemperatureHistory.UNKNOWN]
        and cell_voltage >= limits["safe_min"]
    ):
        contributing_factors.append(
            f"High residual health ({soh_percentage}%) and intact casing qualify unit for stationary second-life."
        )
        recommended_next_steps = [
            "Perform standardized 0.2C capacity verification and impedance spectroscopy.",
            "Format and match modules for stationary solar energy storage (BESS) or backup UPS.",
            "Apply ReVolt Second-Life Digital Passport QR code.",
            "Dispatch to an authorized Second-Life Integration partner.",
        ]
        return AssessmentResult(
            assessed_at=datetime.now(UTC),
            pathway=RecommendedPathway.REUSE,
            confidence_score=0.92 if is_cycles_known else 0.86,
            confidence_basis=(
                "High safety confidence (0.92): Multi-point verified electrical telemetry (voltage, discharge capacity) "
                "conforms with chemistry operational window and intact physical casing qualifies unit for BESS reuse."
                if is_cycles_known else
                "Moderate-high safety confidence (0.86): Verified voltage and capacity meet reuse thresholds; cycle count unrecorded."
            ),
            data_completeness_score=data_completeness,
            soh_percentage=soh_percentage,
            is_hazardous=False,
            safety_warnings=safety_warnings,
            contributing_factors=contributing_factors,
            recommended_next_steps=recommended_next_steps,
            missing_telemetry=missing_telemetry,
            requires_lab_verification=False,
        )

    # B. REFURBISH: Moderate health (60-75%) OR minor repairable issues (corroded terminals), BUT NOT SWOLLEN_MILD
    if (
        (60.0 <= soh_percentage < 75.0)
        or battery.physical_condition == PhysicalCondition.CORRODED_TERMINALS
    ) and battery.physical_condition != PhysicalCondition.SWOLLEN_MILD:
        contributing_factors.append(
            f"Moderate degradation ({soh_percentage}%) or terminal/BMS anomaly detected; economical restoration viable."
        )
        recommended_next_steps = [
            "Refer to certified battery refurbishment laboratory for cell-level diagnostic scanning.",
            "Conduct active cell balancing and replace degraded BMS protection board if necessary.",
            "Clean or replace oxidized busbars / terminal connectors.",
            "Re-certify pack capacity according to secondary market safety standards (UL 1974 / IEC 62619).",
        ]
        return AssessmentResult(
            assessed_at=datetime.now(UTC),
            pathway=RecommendedPathway.REFURBISH,
            confidence_score=0.85,
            confidence_basis=(
                "Moderate safety confidence (0.85): Verified degradation or terminal oxidation requires professional "
                "cell balancing and BMS re-certification under UL 1974 before secondary deployment."
            ),
            data_completeness_score=data_completeness,
            soh_percentage=soh_percentage,
            is_hazardous=False,
            safety_warnings=safety_warnings,
            contributing_factors=contributing_factors,
            recommended_next_steps=recommended_next_steps,
            missing_telemetry=missing_telemetry,
            requires_lab_verification=True,
        )

    # C. RECYCLE: Severe degradation (< 60%), high cycles (> 1800), or mild puffing
    contributing_factors.append(
        f"End-of-life state reached (SoH {soh_percentage}% < 60%, cycles > 1800, or casing gas puffing). "
        f"Economic second-life unfeasible."
    )
    recommended_next_steps = [
        "Discharge cell safely to 0V or inert state using saline bath or resistive bank.",
        "Route to an authorized hydrometallurgical recycling plant for black mass separation.",
        "Target 95%+ recovery rate of critical minerals: Lithium, Cobalt, Nickel, and Copper.",
        "Issue digital recycling certificate and verify carbon credit reduction.",
    ]
    return AssessmentResult(
        assessed_at=datetime.now(UTC),
        pathway=RecommendedPathway.RECYCLE,
        confidence_score=0.90,
        confidence_basis=(
            "High safety confidence (0.90): Significant capacity degradation (<60%), high cycles (>1800), "
            "or internal gas evolution renders second-life unfeasible; closed-loop hydrometallurgical recycling indicated."
        ),
        data_completeness_score=data_completeness,
        soh_percentage=soh_percentage,
        is_hazardous=False,
        safety_warnings=safety_warnings,
        contributing_factors=contributing_factors,
        recommended_next_steps=recommended_next_steps,
        missing_telemetry=missing_telemetry,
        requires_lab_verification=False,
    )
