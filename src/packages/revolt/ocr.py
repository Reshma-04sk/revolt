"""SmartScan OCR and Battery Specification Parser for ReVolt.

Provides deterministic label text extraction, regular-expression telemetry parsing,
realistic commercial sample presets, and field provenance tagging.
"""

import re
from typing import Any
from src.packages.revolt.models import (
    BatteryChemistry,
    FieldProvenance,
    FieldSource,
    OriginalApplication,
    PhysicalCondition,
    TemperatureHistory,
)

# Standard label presets for realistic industrial & consumer testing
LABEL_PRESETS: dict[str, dict[str, Any]] = {
    "dewalt_dcb205": {
        "title": "DeWalt 20V Max 5.0Ah Pack (Power Tool)",
        "raw_text": (
            "DEWALT INDUSTRIAL TOOL CO.\n"
            "MODEL: DCB205  TYPE: 1\n"
            "20V MAX* LITHIUM ION  5.0Ah  90Wh\n"
            "18V NOMINAL  5S2P 18650 NMC CELLS\n"
            "WARNING: DO NOT INCINERATE OR SHORT TERMINALS."
        ),
        "name": "DeWalt 20V Max 5.0Ah Pack",
        "device_model": "DCB205 / 18650-5S2P",
        "chemistry": BatteryChemistry.NMC,
        "original_application": OriginalApplication.POWER_TOOL,
        "age_months": 36,
        "rated_capacity_mah": 5000.0,
        "nominal_voltage_v": 18.0,
    },
    "tata_nexon_lfp": {
        "title": "Tata Nexon EV Sub-Pack (51.2V 105Ah LFP)",
        "raw_text": (
            "TATA MOTORS PASSENGER VEHICLES LTD.\n"
            "TRACTION BATTERY MODULE - 16S1P LFP PRISMATIC\n"
            "NOMINAL VOLTAGE: 51.2V (3.2V x 16)\n"
            "RATED CAPACITY: 105.0 Ah (5.37 kWh)\n"
            "CHEMISTRY: LiFePO4 / LFP\n"
            "PART NO: TM-EV-BATT-MOD4\n"
            "STANDARD: AIS-038 REV 2 / UN 38.3"
        ),
        "name": "Tata Nexon EV Sub-Module (16S LFP)",
        "device_model": "TM-EV-BATT-MOD4",
        "chemistry": BatteryChemistry.LFP,
        "original_application": OriginalApplication.EV,
        "age_months": 28,
        "rated_capacity_mah": 105000.0,
        "nominal_voltage_v": 51.2,
    },
    "macbook_a1989": {
        "title": "Apple MacBook Pro A1989 Pack (LCO 3S)",
        "raw_text": (
            "APPLE INC. MODEL A1989\n"
            "RECHARGEABLE LI-ION POLYMER BATTERY\n"
            "APN: 020-02497  3ICP7/63/83\n"
            "11.41V === 58.0Wh  5086mAh\n"
            "CAUTION: RISK OF FIRE IF REPLACED BY INCORRECT TYPE."
        ),
        "name": "MacBook Pro A1989 Battery Pack",
        "device_model": "Apple A1989 / 020-02497",
        "chemistry": BatteryChemistry.LCO,
        "original_application": OriginalApplication.LAPTOP,
        "age_months": 42,
        "rated_capacity_mah": 5086.0,
        "nominal_voltage_v": 11.4,
    },
    "hero_lectro_ebike": {
        "title": "Hero Lectro E-Bike 36V 10.4Ah Pack (NMC)",
        "raw_text": (
            "HERO LECTRO E-BICYCLE BATTERY PACK\n"
            "MODEL: HL-3610-NMC  10S4P 18650\n"
            "RATED: 36V DC  10.4Ah  374.4Wh\n"
            "CHARGE CUT-OFF: 42.0V  DISCHARGE CUT-OFF: 30.0V\n"
            "MADE IN INDIA  IP65 WATER RESISTANT"
        ),
        "name": "Hero Lectro E-Bike Pack (36V 10S)",
        "device_model": "HL-3610-NMC",
        "chemistry": BatteryChemistry.NMC,
        "original_application": OriginalApplication.EV,
        "age_months": 50,
        "rated_capacity_mah": 10400.0,
        "nominal_voltage_v": 36.0,
    },
    "tesla_2170_cell": {
        "title": "Tesla / Panasonic 21700 Cylindrical Cell (NCA)",
        "raw_text": (
            "PANASONIC / TESLA GIGAFACTORY NEVADA\n"
            "MODEL 21700-NCA RECHARGEABLE HIGH DRAIN CELL\n"
            "3.6V NOMINAL  4.8Ah (4800mAh)  17.3Wh\n"
            "MAX DISCHARGE: 15A CONTINUOUS\n"
            "CAUTION: DO NOT SHORT CIRCUIT"
        ),
        "name": "Tesla Model 3 2170 Cell",
        "device_model": "Panasonic 2170-NCA",
        "chemistry": BatteryChemistry.NCA,
        "original_application": OriginalApplication.EV,
        "age_months": 30,
        "rated_capacity_mah": 4800.0,
        "nominal_voltage_v": 3.6,
    },
}


def parse_battery_label_text(raw_text: str) -> dict[str, Any]:
    """Extracts battery specifications from label text with field confidence and provenance tracking."""
    text_upper = raw_text.upper()

    # 1. Chemistry Extraction
    detected_chemistry = BatteryChemistry.NMC
    chemistry_source = FieldSource.UNKNOWN
    if any(k in text_upper for k in ["LIFEPO4", "LFP", "IRON PHOSPHATE"]):
        detected_chemistry = BatteryChemistry.LFP
        chemistry_source = FieldSource.OCR_EXTRACTED
    elif any(k in text_upper for k in ["LCO", "COBALT OXIDE", "LI-ION POLYMER", "LITHIUM POLYMER"]):
        detected_chemistry = BatteryChemistry.LCO
        chemistry_source = FieldSource.OCR_EXTRACTED
    elif any(k in text_upper for k in ["NCA", "NICKEL COBALT ALUMINUM"]):
        detected_chemistry = BatteryChemistry.NCA
        chemistry_source = FieldSource.OCR_EXTRACTED
    elif any(k in text_upper for k in ["LMO", "MANGANESE"]):
        detected_chemistry = BatteryChemistry.LMO
        chemistry_source = FieldSource.OCR_EXTRACTED
    elif any(k in text_upper for k in ["NMC", "NCM", "LITHIUM ION", "LI-ION"]):
        detected_chemistry = BatteryChemistry.NMC
        chemistry_source = FieldSource.OCR_EXTRACTED

    # 2. Voltage Extraction
    # Matches patterns like 51.2V, 20V MAX, 18V NOMINAL, 3.7V, 11.41V
    detected_voltage: float | None = None
    voltage_source = FieldSource.UNKNOWN
    v_matches = re.findall(r"(\d+(?:\.\d+)?)\s*V(?:OLT|OLTS|MAX|\s*MAX|\s*NOMINAL|\s*NOM)?", text_upper)
    if v_matches:
        # If multiple voltages found (e.g. 20V MAX and 18V NOMINAL), prefer NOMINAL if present
        if "NOMINAL" in text_upper or "NOM" in text_upper:
            nom_match = re.search(r"(\d+(?:\.\d+)?)\s*V(?:\s*NOMINAL|\s*NOM)", text_upper)
            if nom_match:
                detected_voltage = float(nom_match.group(1))
            else:
                detected_voltage = float(v_matches[0])
        else:
            detected_voltage = float(v_matches[0])
        voltage_source = FieldSource.OCR_EXTRACTED

    # 3. Rated Capacity Extraction
    # Matches mAh, Ah, Wh
    detected_capacity_mah: float | None = None
    capacity_source = FieldSource.UNKNOWN

    mah_match = re.search(r"(\d+(?:\.\d+)?)\s*MAH", text_upper)
    if mah_match:
        detected_capacity_mah = float(mah_match.group(1))
        capacity_source = FieldSource.OCR_EXTRACTED
    else:
        ah_match = re.search(r"(\d+(?:\.\d+)?)\s*AH", text_upper)
        if ah_match:
            detected_capacity_mah = float(ah_match.group(1)) * 1000.0
            capacity_source = FieldSource.OCR_EXTRACTED
        else:
            wh_match = re.search(r"(\d+(?:\.\d+)?)\s*WH", text_upper)
            if wh_match and detected_voltage and detected_voltage > 0:
                wh_val = float(wh_match.group(1))
                detected_capacity_mah = round((wh_val / detected_voltage) * 1000.0, 1)
                capacity_source = FieldSource.OCR_EXTRACTED

    # 4. Device Model / Part Number Extraction
    detected_model: str = ""
    model_source = FieldSource.UNKNOWN
    model_match = re.search(r"(?:MODEL|TYPE|PART(?:\s+NO)?|APN)\s*[:#]?\s*([A-Za-z0-9\-_/]+)", text_upper)
    if model_match:
        detected_model = model_match.group(1).strip()
        model_source = FieldSource.OCR_EXTRACTED
    else:
        # Check standalone part/model numbers like DCB205, A1989, 21700, HL-3610
        alt_match = re.search(r"\b([A-Z]{2,4}[0-9]{3,5}[A-Z0-9\-]*|[A-Z][0-9]{4})\b", text_upper)
        if alt_match:
            detected_model = alt_match.group(1).strip()
            model_source = FieldSource.OCR_EXTRACTED

    # 5. Application Inferences
    detected_app = OriginalApplication.OTHER
    if any(k in text_upper for k in ["TRACTION", "EV", "VEHICLE", "E-BICYCLE", "E-BIKE"]):
        detected_app = OriginalApplication.EV
    elif any(k in text_upper for k in ["TOOL", "DRILL", "CORDLESS"]):
        detected_app = OriginalApplication.POWER_TOOL
    elif any(k in text_upper for k in ["MACBOOK", "LAPTOP", "NOTEBOOK"]):
        detected_app = OriginalApplication.LAPTOP
    elif any(k in text_upper for k in ["PHONE", "SMARTPHONE", "MOBILE"]):
        detected_app = OriginalApplication.SMARTPHONE
    elif any(k in text_upper for k in ["SOLAR", "ESS", "STORAGE", "UPS"]):
        detected_app = OriginalApplication.ESS

    # Provenance structure
    provenance = FieldProvenance(
        rated_capacity=capacity_source,
        nominal_voltage=voltage_source,
        model_identity=model_source,
        chemistry=chemistry_source,
        measured_capacity=FieldSource.UNKNOWN,
        measured_voltage=FieldSource.UNKNOWN,
        cycle_count=FieldSource.UNKNOWN,
        physical_condition=FieldSource.USER_ENTERED,
    )

    extracted_fields = {
        "model": detected_model or "Unknown Model",
        "chemistry": detected_chemistry.value,
        "nominal_voltage_v": detected_voltage or 3.7,
        "rated_capacity_mah": detected_capacity_mah or 5000.0,
        "original_application": detected_app.value,
    }

    # Completeness percentage: rated specs known = ~50%, live measurements missing
    completeness = 50.0
    if detected_voltage and detected_capacity_mah:
        completeness = 60.0

    return {
        "raw_text": raw_text,
        "extracted_fields": extracted_fields,
        "provenance": provenance,
        "data_completeness_pct": completeness,
    }
