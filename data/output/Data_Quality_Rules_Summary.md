# Data Quality Rules Generation Summary

**Project:** Industry Ontology - Contactors & Relays Data Quality
**Generated:** January 27, 2026
**Output File:** `Data_Quality_Rules.xlsx`

---

## 1. Overview

This document summarizes the data quality rules generated for manufacturers' contactors, relays, and related electrical control products. The rules follow a standardized format and cover validation, normalization, and default value assignments.

### Key Statistics

| Metric | Value |
|--------|-------|
| Total Rules Generated | 188 |
| Product Categories | 9 |
| Unique Attributes Covered | 75+ |
| Validation Rules | 105 |
| Normalization Rules | 71 |
| Default Rules | 12 |

---

## 2. Rule Format Specification

All rules follow a consistent tab-separated format with four columns:

| Column | Description | Example |
|--------|-------------|---------|
| **Category** | Product category the rule applies to | Contactors, Relays, Limit Switches |
| **Attribute** | The specific data attribute | zz_Contact Current Rating |
| **Rule type** | Type of rule | Validation, Normalization, Default |
| **Rule** | The rule logic/description | Anything outside 6 A – 800 A is not valid |

### Rule Types Explained

| Type | Purpose | When Applied |
|------|---------|--------------|
| **Validation** | Checks if data values are valid/acceptable | Data ingestion, quality checks |
| **Normalization** | Standardizes format and terminology | Data transformation, ETL |
| **Default** | Assigns values when data is missing | Data enrichment, gap filling |

---

## 3. Categories Covered

### 3.1 Contactors (87 rules)
Primary category covering power contactors, auxiliary contactors, mini contactors, and reversing contactors.

**Key Attributes:**
- Contact Current Rating (6A - 800A range)
- Control Voltage (24V - 400V standard values)
- Utilization Category (AC-1, AC-3, AC-4, etc.)
- Number of Poles (1-4)
- Mechanical/Electrical Durability
- Frame Size (ABB AF series)
- IP Rating (IEC 60529)
- Horsepower Ratings (multiple voltage/phase combinations)

### 3.2 Relays (32 rules)
Covers thermal overload relays, electronic overload relays, solid state relays, and control relays.

**Key Attributes:**
- Relay Type
- Setting Range (0.1A - 800A)
- Trip Class (Class 10, 20, 30)
- Reset Type (Manual/Automatic)
- Contact Form (SPST, SPDT, DPDT)
- Phase Loss Protection

### 3.3 Limit Switches (24 rules)
Industrial limit switches with various actuator types.

**Key Attributes:**
- Head Type (Rotary, Linear, Wobble)
- Actuator Type (Lever, Plunger, Roller)
- Voltage Rating (24-250V AC/DC)
- Contact Form
- Operating Force/Travel
- Mechanical Life

### 3.4 Motor Controllers (9 rules)
DOL starters, star-delta starters, soft starters, and VFDs.

**Key Attributes:**
- Controller Type
- Motor Power
- Starting Current
- Overload/Short Circuit Protection

### 3.5 Accessories (10 rules)
Auxiliary contact blocks, surge suppressors, timer modules, and mounting adapters.

**Key Attributes:**
- Accessory Type
- For Use With (compatibility)
- Contact Configuration

### 3.6 Capacitor Contactors (4 rules)
Specialized contactors for power factor correction.

**Key Attributes:**
- Capacitor Rating (kvar)
- Inrush Current Limiting
- Switching Frequency

### 3.7 Vacuum Contactors (3 rules)
Medium voltage vacuum contactors.

**Key Attributes:**
- Vacuum Interrupter Rating
- Breaking Capacity
- Arc Voltage

### 3.8 Lighting Contactors (4 rules)
Electrically held and mechanically held lighting contactors.

**Key Attributes:**
- Holding Type
- Ballast Load Rating
- Pilot Light

### 3.9 All Categories (15 rules)
Common rules applicable across all product categories.

**Key Attributes:**
- 80 Character Description
- Material Number
- Vendor Name
- UPC Code
- Color/Material

---

## 4. Standards Referenced

The rules align with the following industry standards:

| Standard | Description | Applied To |
|----------|-------------|------------|
| **IEC 60038** | Standard voltages | Voltage validation |
| **IEC 60529** | IP Rating codes | Enclosure protection |
| **IEC 60947-4-1** | Contactors and motor starters | Current ratings, utilization categories |
| **UL 508** | Industrial control equipment | Approvals validation |
| **NEMA ICS 2** | Industrial control devices | NEMA sizes |

---

## 5. Sample Rules by Category

### Contactors - Validation Examples
```
zz_Contact Current Rating    Anything outside 6 A – 800 A is not valid
zz_Utilization Category      Must be one of IEC 60947-4-1: AC-1, AC-2, AC-3, AC-4...
zz_IP Rating                 Must match IEC 60529 pattern: IP[0-6][0-9]
zz_Mechanical Durability     Must be between 100,000 and 30,000,000 operations
```

### Contactors - Normalization Examples
```
zz_Number of Poles           "3P", "3 Pole", "Three Pole" normalize to 3
zz_Mounting Type             "On Rail", "35mm rail" becomes "DIN Rail"
zz_Frequency                 "50Hz", "50 Hz", "50HZ" normalize to "50 Hz"
zz_Utilization Category      "AC3", "AC 3", "ac-3" normalize to "AC-3"
```

### Contactors - Default Examples
```
zz_Control Voltage           If AC and frequency missing, default to 50/60 Hz
zz_IP Rating                 If terminal cover present and no rating, default to IP20
zz_Ambient Temperature       If not specified, default to "40°C max"
```

### Relays - Examples
```
zz_Trip Class (Validation)   Must be one of: Class 5, Class 10, Class 10A, Class 20, Class 30
zz_Trip Class (Default)      If not specified, default to "Class 10"
zz_Reset Type (Normalization) "Auto", "auto-reset" normalize to "Automatic"
```

### Limit Switches - Examples
```
zz_Actuator Type (Validation)  If IP Rating > IP65, must be Booted or Sealed
zz_Head Type (Normalization)   "Booted", "sealed" move to zz_Actuator Type
zz_Voltage Rating (Validation) Supported ranges: 24-250 V AC or 24-250 V DC
```

---

## 6. Rule Distribution

### By Category
```
Contactors              ████████████████████████████████████████████  87 (46.3%)
Relays                  ████████████████  32 (17.0%)
Limit Switches          ████████████  24 (12.8%)
All Categories          ████████  15 (8.0%)
Accessories             █████  10 (5.3%)
Motor Controllers       █████  9 (4.8%)
Capacitor Contactors    ██  4 (2.1%)
Lighting Contactors     ██  4 (2.1%)
Vacuum Contactors       ██  3 (1.6%)
```

### By Rule Type
```
Validation              ████████████████████████████████████████████████████  105 (55.9%)
Normalization           ████████████████████████████████████  71 (37.8%)
Default                 ██████  12 (6.4%)
```

---

## 7. Implementation Notes

### Data Flow
```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐
│ Raw Data    │────>│ Validation Rules │────>│ Valid/Invalid   │
│ Ingestion   │     │ (105 rules)      │     │ Flag            │
└─────────────┘     └──────────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │ Normalization    │────>│ Standardized    │
                    │ Rules (71 rules) │     │ Values          │
                    └──────────────────┘     └─────────────────┘
                            │
                            ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │ Default Rules    │────>│ Complete        │
                    │ (12 rules)       │     │ Records         │
                    └──────────────────┘     └─────────────────┘
```

### Priority Order
1. **Validation** - Apply first to identify invalid data
2. **Normalization** - Apply to valid data for standardization
3. **Default** - Apply last to fill missing values

### Cross-Field Dependencies
Some rules have dependencies on other attributes:
- `zz_Contact Current Rating` depends on `zz_Type` (Auxiliary = null)
- `zz_Actuator Type` depends on `zz_IP Rating` (IP65+ = Booted/Sealed)
- `zz_Electrical Durability` must be ≤ `zz_Mechanical Durability`
- `zz_Mounting Type` can depend on `Frame Width`

---

## 8. File Outputs

| File | Location | Description |
|------|----------|-------------|
| Data_Quality_Rules.xlsx | `data/output/` | Complete rules in Excel format |
| Data_Quality_Rules_Summary.md | `data/output/` | This summary document |

### Excel File Features
- Color-coded rows by category
- Frozen header row
- Auto-filters enabled
- Optimized column widths
- Text wrapping for rule descriptions

---

## 9. Next Steps

1. **Review & Validate** - Subject matter experts review rules for accuracy
2. **Prioritize** - Identify critical rules for initial implementation
3. **Implement** - Integrate rules into data pipeline
4. **Test** - Validate rules against sample data
5. **Monitor** - Track rule violations and refine thresholds

---

## 10. Appendix: Attribute Quick Reference

### Voltage Attributes
| Attribute | Standard Values |
|-----------|-----------------|
| zz_Control Voltage | 24, 48, 110, 120, 220, 230, 240 V |
| zz_Operating Voltage | 24, 48, 110, 220, 230, 240, 400, 480, 690 V |
| zz_Coil Voltage | 24, 48, 110, 120, 220, 230, 240, 400 V |

### Current Attributes
| Attribute | Valid Range |
|-----------|-------------|
| zz_Contact Current Rating | 6 - 800 A |
| zz_Current Rating | 6 - 2050 A |
| zz_Setting Range (Relays) | 0.1 - 800 A |

### Utilization Categories (IEC 60947-4-1)
| Category | Application |
|----------|-------------|
| AC-1 | Non-inductive or slightly inductive loads |
| AC-2 | Slip-ring motors: starting, switching off |
| AC-3 | Squirrel-cage motors: starting, switching off during running |
| AC-4 | Squirrel-cage motors: starting, plugging, reversing, inching |

### ABB Frame Sizes
```
AF09, AF16, AF26, AF38, AF52, AF65, AF96, AF116, AF140,
AF190, AF260, AF305, AF370, AF460, AF580, AF750, AF1350, AF2050
```

---

*Document generated as part of the Data Quality Rules Derivation Project*
