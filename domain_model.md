# Domain Model: Industrial Components (Dynamic)

> **Domain**: Industrial Component
> **Sub-Domain**: Electrical Equipment (and others)
> **Focus Entity**: Dynamic (e.g., Contactor, Relay, Switch, Sensor)
> **Version**: 2.0 (Dynamic Architecture)
> **Standards Basis**: IEC 60947 series, NEMA ICS, UNSPSC, and category-specific standards

---

## 1. Dynamic Domain Architecture

### 1.1 Overview
The Schema Builder V0 has evolved from a static, single-category model to a **dynamic, multi-category knowledge engine**. It uses a flexible "Knowledge Base" approach where the domain backbone is loaded contextually based on the product category being processed.

### 1.2 Key Capabilities
- **Dynamic Category Support**: The system can switch contexts (e.g., from Contactors to Relays) at runtime, loading the appropriate ontological backbone from `knowledge_base/`.
- **Chain of Thought (CoT) Reasoning**: The AI reasoning engine now explains *why* a specific attribute, rule, or hierarchy path is chosen, based on the functional purpose of the entity.
- **Multi-View Lenses**: The core schema is projected into three distinct views:
    1.  **Supply Chain (ERP)**: Focus on procurement, standards, and logistics.
    2.  **Ecommerce (Sales)**: Focus on discovery, merchandising, and search facets.
    3.  **Analytical (Data Quality)**: Focus on completeness and governance.

### 1.3 System Boundaries (Dynamic)
The system boundaries adapt to the focus entity. For a **Contactor**, the boundary includes the coil and contacts. For a **Sensor**, it includes the sensing element and output interface.

---

## 2. Interactive Workflow (UI)

The system is accessible via a **Streamlit UI** (`schema_builder_ui/app.py`) that guides users through the schema generation process:

1.  **Upload**: Users upload raw product data (Excel/CSV/JSON).
2.  **Category Selection**: Users select the target category (e.g., "Contactors", "Relays") from a dynamic list populated by `Electrical_Components.docx`.
3.  **Pipeline Execution**:
    - **Normalization**: Derives rules to standardize messy data.
    - **Hierarchy**: Resolves UNSPSC and Ecommerce paths.
    - **Attribute Resolution**: Generates the "Golden Schema" with CoT reasoning.
4.  **Results**: Users view and download standardized data and schemas.

---

## 3. Domain Model: Contactors (Reference Implementation)

*(The following sections detail the specific model for Contactors, which serves as the template for other categories)*

### 3.1 Domain Overview
...

**Industrial Components** encompass standardized, manufactured physical objects
used in the construction, operation, and maintenance of industrial systems.
Each component class is defined by international standards, carries a fixed set
of intrinsic electrical/mechanical properties, and exists within a supply chain
that requires structured product data for procurement, engineering, and commerce.

### 1.2 Sub-Domain Summary

**Electrical Equipment** covers devices used in low-voltage power distribution,
motor control, protection, and switching. Products in this sub-domain are
governed primarily by the IEC 60947 family (international) and NEMA ICS
(North American). Every device has rated values that define the electrical
conditions under which it may safely and reliably operate.

### 1.3 Focus Entity — Contactor

A **contactor** is an electromechanically operated switching device designed for
repeatedly establishing and interrupting power circuit current under normal
operating conditions, including overload conditions. Unlike a circuit breaker,
a contactor is not intended to interrupt short-circuit current.

### 1.4 Functional Purpose

| Function                   | Description                                                                 |
|----------------------------|-----------------------------------------------------------------------------|
| Power circuit switching    | Connect/disconnect electrical loads (motors, lighting, heating, capacitors) |
| Remote control             | Enable switching from a distant control point via low-voltage coil signal   |
| Automated control          | Interface with PLCs, timers, sensors for programmatic load management       |
| Motor starting/stopping    | Primary device in DOL, star-delta, and reversing motor starter circuits     |
| Repeated operation         | Designed for high switching frequency (up to millions of mechanical cycles) |

### 1.5 System Boundaries

```
┌─────────────────────────────────────────────────────────────┐
│                    POWER DISTRIBUTION SYSTEM                 │
│  ┌─────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐ │
│  │ Supply   │──▶│ Protection│──▶│CONTACTOR │──▶│  Load   │ │
│  │ (Mains)  │   │ (MCCB/   │   │          │   │ (Motor/ │ │
│  │          │   │  Fuse)    │   │          │   │  Heater)│ │
│  └─────────┘   └───────────┘   └────┬─────┘   └─────────┘ │
│                                      │                       │
│                              ┌───────┴───────┐               │
│                              │ CONTROL SYSTEM │               │
│                              │ (PLC / Manual  │               │
│                              │  / Safety)     │               │
│                              └───────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

**Physical boundary**: The contactor device — main contacts, auxiliary contacts,
electromagnetic coil, arc suppression chamber, terminals, and housing.

**Logical boundary**: The rated operating envelope defined by utilization
category, voltage/current ratings, and environmental limits.

**Information boundary**: Product specifications, datasheet values, certification
records, ordering data, and lifecycle parameters.

### 1.6 Interacting Systems

| System                        | Interaction Type       | Direction |
|-------------------------------|------------------------|-----------|
| Motor Control Center (MCC)    | Physical containment   | Inbound   |
| Circuit breaker / Fuse        | Short-circuit protection| Upstream  |
| Overload relay                | Thermal protection     | Downstream|
| PLC / Control panel           | Control signal (coil)  | Inbound   |
| Variable Frequency Drive (VFD)| Bypass / coordination  | Parallel  |
| Safety relay / E-stop         | Safety interlock       | Inbound   |
| Building Management System    | Monitoring / telemetry | Outbound  |
| Power supply (mains)          | Energy source          | Upstream  |
| Electrical load (motor, etc.) | Switched load          | Downstream|

---

## 2. Entities

### 2.1 Primary Entities

| Entity                  | Type     | Description                                                                                       |
|-------------------------|----------|---------------------------------------------------------------------------------------------------|
| **Contactor**           | Physical | The switching device itself; the root entity of this model                                        |
| **Main Contact**        | Physical | Power-carrying contact element that establishes/interrupts the load circuit                       |
| **Auxiliary Contact**   | Physical | Low-current contact for signaling, interlocking, and control circuit feedback                     |
| **Electromagnetic Coil**| Physical | Solenoid that generates the magnetic force to actuate the contact bridge                          |
| **Arc Chamber**         | Physical | Arc suppression system (deion plates, magnetic blowout) that extinguishes switching arcs          |
| **Contact Bridge**      | Physical | Movable element carrying the moving contacts; driven by the armature                              |

### 2.2 Supporting Infrastructure

| Entity                  | Type     | Description                                                                                       |
|-------------------------|----------|---------------------------------------------------------------------------------------------------|
| **Terminal**            | Physical | Connection point for external wiring (main circuit and control circuit)                           |
| **Enclosure / Housing** | Physical | Protective body; defines IP rating, mounting footprint, and material composition                  |
| **Mounting System**     | Physical | DIN rail clip, panel-mount holes, or adapter plate for physical installation                      |
| **Mechanical Interlock**| Physical | Device preventing simultaneous closure of two contactors (reversing / transfer applications)      |
| **Surge Suppressor**    | Physical | RC circuit or varistor fitted across the coil to suppress voltage transients                      |

### 2.3 Control and Monitoring

| Entity                  | Type     | Description                                                                                       |
|-------------------------|----------|---------------------------------------------------------------------------------------------------|
| **Control Circuit**     | Logical  | The low-voltage circuit that energizes/de-energizes the coil                                      |
| **Overload Relay**      | Physical | Thermal or electronic relay paired with the contactor for motor overload protection               |
| **Timer Module**        | Physical | On-delay or off-delay timer for timed control sequences                                          |
| **Auxiliary Contact Block** | Physical | Add-on module providing additional auxiliary contacts                                         |

### 2.4 Safety and Protection

| Entity                  | Type     | Description                                                                                       |
|-------------------------|----------|---------------------------------------------------------------------------------------------------|
| **Short-Circuit Protection Device** | Physical | Upstream fuse or circuit breaker coordinated with the contactor              |
| **Safety Interlock**    | Logical  | Logic constraint ensuring safe operating sequences (e.g., anti-parallel interlock)                |
| **Coordination Type**   | Logical  | IEC 60947-4-1 Type 1 or Type 2 short-circuit coordination classification                         |

### 2.5 Standards, Governance, and Commerce

| Entity                  | Type     | Description                                                                                       |
|-------------------------|----------|---------------------------------------------------------------------------------------------------|
| **IEC 60947-4-1**       | Standard | International standard for contactors and motor-starters                                          |
| **IEC 60947-1**         | Standard | General rules for low-voltage switchgear and controlgear                                          |
| **NEMA ICS 2**          | Standard | North American standard for industrial control devices (contactors)                               |
| **UNSPSC**              | Taxonomy | United Nations product classification (code 39121004 for contactors)                              |
| **Manufacturer**        | External | Company that designs and produces the contactor (ABB, Siemens, Schneider, Eaton, etc.)            |
| **Certification Body**  | External | Organization granting compliance marks (UL, CSA, TÜV, GOST)                                      |
| **Product Family**      | Logical  | Manufacturer's product line grouping (e.g., Schneider TeSys Deca, Siemens SIRIUS 3RT2)           |

---

## 3. Property Model

### 3.1 Contactor — Electrical Characteristics

| Property                        | Data Type    | Unit   | Structural Role    | Standards Ref         |
|---------------------------------|-------------|--------|--------------------|-----------------------|
| Rated operational voltage (Ue)  | Scalar      | V      | Variant-defining   | IEC 60947-4-1 §4.3.1 |
| Rated operational current (Ie)  | Scalar      | A      | Variant-defining   | IEC 60947-4-1 §4.3.2 |
| Rated insulation voltage (Ui)   | Scalar      | V      | Descriptive        | IEC 60947-1 §4.3.1   |
| Rated impulse withstand (Uimp)  | Scalar      | kV     | Descriptive        | IEC 60947-1 §4.3.1   |
| Number of poles                 | Scalar      | —      | Variant-defining   | IEC 60947-4-1 §4.3   |
| Utilization category            | Enumeration | —      | Contextual         | IEC 60947-4-1 §4.4   |
| Rated frequency                 | Enumeration | Hz     | Variant-defining   | IEC 60947-4-1 §4.3   |
| Voltage type                    | Enumeration | —      | Variant-defining   | IEC 60947-4-1 §4.3   |
| Making capacity                 | Scalar      | A      | Descriptive        | IEC 60947-4-1 §4.3.5 |
| Breaking capacity               | Scalar      | A      | Descriptive        | IEC 60947-4-1 §4.3.5 |
| Conditional short-circuit (Iq)  | Scalar      | kA     | Descriptive        | IEC 60947-4-1 §4.3.6 |
| NEMA size                       | Enumeration | —      | Variant-defining   | NEMA ICS 2            |
| Horsepower rating               | Conditional | HP     | Variant-defining   | NEMA ICS 2            |

### 3.2 Contactor — Coil Characteristics

| Property                        | Data Type    | Unit   | Structural Role    | Standards Ref         |
|---------------------------------|-------------|--------|--------------------|-----------------------|
| Rated coil voltage (Us)         | Scalar      | V      | Variant-defining   | IEC 60947-4-1 §4.3.4 |
| Coil voltage type               | Enumeration | —      | Variant-defining   | IEC 60947-4-1 §4.3.4 |
| Coil power (pick-up)            | Scalar      | W / VA | Descriptive        | Manufacturer spec     |
| Coil power (holding)            | Scalar      | W / VA | Descriptive        | Manufacturer spec     |
| Coil resistance                 | Scalar      | Ω      | Descriptive        | Manufacturer spec     |
| Operating voltage range         | Range       | %Ue    | Descriptive        | IEC 60947-4-1 §4.3.4 |
| Pick-up voltage (min)           | Scalar      | %Ue    | Descriptive        | IEC 60947-4-1         |
| Drop-out voltage (max)          | Scalar      | %Ue    | Descriptive        | IEC 60947-4-1         |

### 3.3 Contactor — Contact Characteristics

| Property                        | Data Type    | Unit   | Structural Role    | Standards Ref         |
|---------------------------------|-------------|--------|--------------------|-----------------------|
| Contact configuration           | Composite   | —      | Variant-defining   | IEC 60947-4-1 §4.3   |
| Number of NO contacts           | Scalar      | —      | Variant-defining   | IEC 60947-4-1         |
| Number of NC contacts           | Scalar      | —      | Variant-defining   | IEC 60947-4-1         |
| Contact material                | Enumeration | —      | Descriptive        | Manufacturer spec     |
| Contact resistance (initial)    | Scalar      | mΩ     | Descriptive        | IEC 60947-4-1         |
| Contact rating (auxiliary)      | Scalar      | A      | Descriptive        | IEC 60947-5-1         |

### 3.4 Contactor — Mechanical / Durability Characteristics

| Property                        | Data Type    | Unit             | Structural Role | Standards Ref         |
|---------------------------------|-------------|------------------|-----------------|-----------------------|
| Mechanical durability           | Scalar      | million ops      | Descriptive     | IEC 60947-4-1 §B     |
| Electrical durability           | Scalar      | million ops      | Descriptive     | IEC 60947-4-1 §B     |
| Maximum operating frequency     | Scalar      | ops/hour         | Descriptive     | IEC 60947-4-1         |
| Pick-up time                    | Scalar      | ms               | Descriptive     | Manufacturer spec     |
| Drop-out time                   | Scalar      | ms               | Descriptive     | Manufacturer spec     |

### 3.5 Contactor — Physical / Environmental Characteristics

| Property                        | Data Type    | Unit   | Structural Role | Standards Ref         |
|---------------------------------|-------------|--------|-----------------|-----------------------|
| Dimensions (H × W × D)         | Composite   | mm     | Descriptive     | Manufacturer spec     |
| Weight                          | Scalar      | kg     | Descriptive     | Manufacturer spec     |
| Mounting type                   | Enumeration | —      | Variant-defining| Manufacturer spec     |
| Degree of protection (IP)       | Enumeration | —      | Descriptive     | IEC 60529             |
| Pollution degree                | Enumeration | —      | Descriptive     | IEC 60947-1 §6.1.3   |
| Ambient temperature range       | Range       | °C     | Descriptive     | IEC 60947-4-1         |
| Storage temperature range       | Range       | °C     | Descriptive     | Manufacturer spec     |
| Altitude limit                  | Scalar      | m      | Descriptive     | IEC 60947-1 §6.1.1   |
| Vibration resistance            | Scalar      | g / Hz | Descriptive     | IEC 60068             |

### 3.6 Contactor — Terminal / Connection Characteristics

| Property                        | Data Type    | Unit   | Structural Role | Standards Ref         |
|---------------------------------|-------------|--------|-----------------|-----------------------|
| Terminal type                   | Enumeration | —      | Variant-defining| Manufacturer spec     |
| Wire size range                 | Range       | mm²/AWG| Descriptive     | Manufacturer spec     |
| Tightening torque               | Scalar      | Nm     | Descriptive     | Manufacturer spec     |
| Stripping length                | Scalar      | mm     | Descriptive     | Manufacturer spec     |
| Number of terminals             | Scalar      | —      | Descriptive     | Manufacturer spec     |

### 3.7 Contactor — Safety / Protection Characteristics

| Property                        | Data Type    | Unit   | Structural Role | Standards Ref         |
|---------------------------------|-------------|--------|-----------------|-----------------------|
| Dielectric strength             | Scalar      | V      | Descriptive     | IEC 60947-1           |
| Isolation voltage               | Scalar      | V      | Descriptive     | IEC 60947-1           |
| Surge current rating            | Scalar      | A      | Descriptive     | Manufacturer spec     |
| Short-circuit coordination type | Enumeration | —      | Descriptive     | IEC 60947-4-1 §B     |
| Built-in surge suppressor       | Boolean     | —      | Descriptive     | Manufacturer spec     |

### 3.8 Contactor — Standards / Compliance

| Property                        | Data Type    | Unit   | Structural Role | Standards Ref         |
|---------------------------------|-------------|--------|-----------------|-----------------------|
| IEC compliance                  | Boolean     | —      | Descriptive     | IEC 60947-4-1         |
| UL listing                      | Boolean     | —      | Descriptive     | UL 508                |
| CSA certification               | Boolean     | —      | Descriptive     | CSA C22.2             |
| CE marking                      | Boolean     | —      | Descriptive     | EU LVD/EMC            |
| GOST certification              | Boolean     | —      | Descriptive     | GOST R                |
| RoHS compliance                 | Boolean     | —      | Descriptive     | EU 2011/65/EU         |

### 3.9 Contactor — Identification / Commercial Attributes

| Property                        | Data Type    | Unit   | Structural Role | Standards Ref         |
|---------------------------------|-------------|--------|-----------------|-----------------------|
| Manufacturer                    | Enumeration | —      | Identity        | —                     |
| Product family / Series         | Enumeration | —      | Identity        | —                     |
| Part number / Catalog number    | Scalar      | —      | Identity        | —                     |
| UNSPSC code                     | Scalar      | —      | Identity        | UNSPSC                |
| Product type                    | Enumeration | —      | Identity        | —                     |
| Product description             | Scalar      | —      | Descriptive     | —                     |

### 3.10 Overload Relay — Key Properties

| Property                        | Data Type    | Unit   | Structural Role | Standards Ref         |
|---------------------------------|-------------|--------|-----------------|-----------------------|
| Current setting range           | Range       | A      | Variant-defining| IEC 60947-4-1 §4.7   |
| Trip class                      | Enumeration | —      | Variant-defining| IEC 60947-4-1 §4.7.3 |
| Reset mode                      | Enumeration | —      | Descriptive     | Manufacturer spec     |
| Phase-loss sensitivity          | Boolean     | —      | Descriptive     | IEC 60947-4-1         |

---

## 4. Ontology Triplets

### 4.1 Namespace Prefixes

```turtle
@prefix fso:   <http://schema.industrial-component.org/fso/> .
@prefix iec:   <http://schema.industrial-component.org/iec60947/> .
@prefix rdf:   <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:  <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd:   <http://www.w3.org/2001/XMLSchema#> .
@prefix skos:  <http://www.w3.org/2004/02/skos/core#> .
```

### 4.2 Type Classification

```turtle
fso:Contactor              rdf:type           fso:SwitchingDevice .
fso:SwitchingDevice        rdfs:subClassOf    fso:ElectricalEquipment .
fso:ElectricalEquipment    rdfs:subClassOf    fso:IndustrialComponent .

fso:MainContact            rdf:type           fso:ContactElement .
fso:AuxiliaryContact       rdf:type           fso:ContactElement .
fso:ElectromagneticCoil    rdf:type           fso:ActuatingElement .
fso:ArcChamber             rdf:type           fso:ProtectionElement .
fso:OverloadRelay          rdf:type           fso:ProtectionDevice .

fso:IEC_Contactor          rdfs:subClassOf    fso:Contactor .
fso:NEMA_Contactor         rdfs:subClassOf    fso:Contactor .
```

### 4.3 Physical Containment (Part-of Hierarchy)

```turtle
fso:Contactor    fso:hasComponent    fso:MainContact .
fso:Contactor    fso:hasComponent    fso:AuxiliaryContact .
fso:Contactor    fso:hasComponent    fso:ElectromagneticCoil .
fso:Contactor    fso:hasComponent    fso:ArcChamber .
fso:Contactor    fso:hasComponent    fso:ContactBridge .
fso:Contactor    fso:hasComponent    fso:Terminal .
fso:Contactor    fso:hasComponent    fso:Enclosure .
fso:Contactor    fso:hasComponent    fso:MountingSystem .

fso:ContactBridge    fso:carries        fso:MainContact .
fso:ArcChamber       fso:suppressesArcOf fso:MainContact .
```

### 4.4 Functional Relationships

```turtle
fso:Contactor              fso:switches          fso:PowerCircuit .
fso:ElectromagneticCoil    fso:actuates          fso:ContactBridge .
fso:ControlCircuit         fso:energizes         fso:ElectromagneticCoil .
fso:MainContact            fso:conducts          fso:LoadCurrent .
fso:AuxiliaryContact       fso:signals           fso:ControlCircuit .
fso:OverloadRelay          fso:protects          fso:ElectricalLoad .
fso:OverloadRelay          fso:pairedWith        fso:Contactor .
fso:MechanicalInterlock    fso:prevents          fso:SimultaneousClosure .
fso:SurgeSuppressor        fso:protectsCoilOf    fso:Contactor .
```

### 4.5 Energy and Control Flow

```turtle
fso:PowerSupply    fso:suppliesPowerTo     fso:Contactor .
fso:Contactor      fso:deliversPowerTo     fso:ElectricalLoad .
fso:ControlSignal  fso:triggersCoilOf      fso:Contactor .
fso:Contactor      fso:feedbackVia         fso:AuxiliaryContact .

fso:ShortCircuitProtection  fso:protectsUpstreamOf  fso:Contactor .
fso:OverloadRelay           fso:monitorsDownstreamOf fso:Contactor .
```

### 4.6 Attribute Dependencies (Inter-Property Relationships)

```turtle
iec:RatedOperationalCurrent   fso:conditionalOn     iec:UtilizationCategory .
iec:RatedOperationalCurrent   fso:coDeterminedWith  iec:RatedOperationalVoltage .
iec:HorsepowerRating          fso:conditionalOn     iec:SupplyVoltage .
iec:HorsepowerRating          fso:conditionalOn     iec:Phase .
iec:ElectricalDurability      fso:conditionalOn     iec:UtilizationCategory .
iec:MakingCapacity            fso:derivedFrom       iec:RatedOperationalCurrent .
iec:BreakingCapacity          fso:derivedFrom       iec:RatedOperationalCurrent .
iec:ContactConfiguration      fso:composedOf        iec:NOContactCount .
iec:ContactConfiguration      fso:composedOf        iec:NCContactCount .
iec:AmbientTempDerating       fso:constrains        iec:RatedOperationalCurrent .
iec:Altitude                  fso:constrains        iec:RatedOperationalVoltage .
iec:CoilPowerPickup           fso:derivedFrom       iec:CoilVoltage .
iec:CoilPowerPickup           fso:derivedFrom       iec:CoilResistance .
iec:NumberOfPoles             fso:constrains        iec:ContactConfiguration .
```

### 4.7 Standards and Governance

```turtle
fso:Contactor     fso:conformsTo       iec:IEC_60947_4_1 .
fso:Contactor     fso:conformsTo       fso:NEMA_ICS_2 .
fso:Contactor     fso:classifiedIn     fso:UNSPSC_39121004 .
fso:Contactor     fso:manufacturedBy   fso:Manufacturer .
fso:Contactor     fso:certifiedBy      fso:CertificationBody .
fso:Contactor     fso:belongsTo        fso:ProductFamily .

fso:Manufacturer  fso:produces         fso:ProductFamily .
fso:ProductFamily fso:contains         fso:Contactor .
```

### 4.8 Attribute Assignments (Property → Entity)

```turtle
fso:Contactor    fso:hasProperty    iec:RatedOperationalVoltage .
fso:Contactor    fso:hasProperty    iec:RatedOperationalCurrent .
fso:Contactor    fso:hasProperty    iec:NumberOfPoles .
fso:Contactor    fso:hasProperty    iec:UtilizationCategory .
fso:Contactor    fso:hasProperty    iec:RatedFrequency .
fso:Contactor    fso:hasProperty    fso:MountingType .
fso:Contactor    fso:hasProperty    fso:IPRating .
fso:Contactor    fso:hasProperty    fso:Weight .
fso:Contactor    fso:hasProperty    fso:Dimensions .

fso:ElectromagneticCoil  fso:hasProperty  iec:RatedCoilVoltage .
fso:ElectromagneticCoil  fso:hasProperty  fso:CoilPower .
fso:ElectromagneticCoil  fso:hasProperty  fso:CoilResistance .

fso:MainContact          fso:hasProperty  fso:ContactMaterial .
fso:MainContact          fso:hasProperty  fso:ContactResistance .

fso:AuxiliaryContact     fso:hasProperty  iec:AuxiliaryContactRating .
fso:AuxiliaryContact     fso:hasProperty  fso:ContactConfiguration .
```

---

## 5. Terminology

### 5.1 Core Electrical Terms

| Term                         | Definition                                                                                           | Functional Role                                                 |
|------------------------------|------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| Rated operational voltage (Ue)| Voltage value assigned by the manufacturer for which the contactor's performance is stated          | Primary variant-defining parameter; co-determined with Ie       |
| Rated operational current (Ie)| Current value assigned for a given utilization category and voltage; defines the load capacity       | Primary variant-defining parameter; conditional on Ue and AC-x  |
| Rated insulation voltage (Ui)| Highest voltage value to which dielectric tests and clearance calculations are referred              | Safety parameter; always ≥ Ue                                   |
| Utilization category         | Coded classification (AC-1, AC-3, AC-4, DC-1, etc.) defining the type of load and switching duty    | Contextual parameter that determines Ie derating and durability |
| Making capacity              | Maximum current the contactor can successfully close onto                                            | Derived from Ie × multiplier per utilization category           |
| Breaking capacity            | Maximum current the contactor can successfully interrupt                                             | Derived from Ie × multiplier per utilization category           |
| Conditional short-circuit current (Iq)| Maximum prospective short-circuit current the contactor can withstand when protected by a specified SCPD | Coordination parameter linking contactor to upstream protection |

### 5.2 Utilization Categories (IEC 60947-4-1 §4.4)

| Category | Load Type                                  | Typical Application                          |
|----------|--------------------------------------------|----------------------------------------------|
| AC-1     | Non-inductive or slightly inductive loads   | Resistive heating, distribution               |
| AC-2     | Slip-ring motors: starting, switching off   | Crane motors, hoist motors                    |
| AC-3     | Squirrel-cage motors: starting, switching off during running | General motor control (most common) |
| AC-4     | Squirrel-cage motors: starting, plugging, inching | Reversing, jogging applications        |
| AC-5a    | Discharge lamp control                      | Lighting panels                               |
| AC-5b    | Incandescent lamp control                   | Lighting panels                               |
| AC-6a    | Transformer switching                       | Capacitor banks, transformers                 |
| AC-6b    | Capacitor bank switching                    | Power factor correction                       |
| DC-1     | Non-inductive or slightly inductive DC loads| DC resistive loads                            |
| DC-3     | Shunt motors: starting, switching off       | DC motor control                              |
| DC-5     | Series motors: starting, switching off      | DC traction motors                            |

### 5.3 Mechanical and Durability Terms

| Term                       | Definition                                                                             | Functional Role                                    |
|----------------------------|----------------------------------------------------------------------------------------|----------------------------------------------------|
| Mechanical durability      | Number of no-load operating cycles before mechanical failure                           | Lifecycle parameter; typically 10–30 million ops    |
| Electrical durability      | Number of rated-load operating cycles before contact replacement required              | Lifecycle parameter; conditional on utilization cat.|
| Operating frequency        | Maximum switching operations per hour under rated conditions                           | Application suitability constraint                  |
| Pick-up time               | Time from coil energization to full contact closure                                    | Response speed parameter                            |
| Drop-out time              | Time from coil de-energization to full contact opening                                 | Response speed parameter                            |

### 5.4 Contact and Wiring Terms

| Term                       | Definition                                                                             | Functional Role                                    |
|----------------------------|----------------------------------------------------------------------------------------|----------------------------------------------------|
| Contact configuration      | Composite notation (e.g., 3NO+1NC) describing the arrangement of main and aux contacts| Variant-defining; parsed into NO/NC counts          |
| Normally open (NO)         | Contact that is open when the coil is de-energized; closes when energized              | Main power switching function                       |
| Normally closed (NC)       | Contact that is closed when the coil is de-energized; opens when energized             | Safety interlock and feedback signaling             |
| DIN rail                   | 35mm top-hat rail per EN 60715 for snap-on mounting of modular devices                 | Mounting standard; determines footprint             |
| Terminal type              | Connection method: screw, spring, ring, box lug, cage clamp                            | Installation compatibility constraint               |
| Wire size range            | Acceptable conductor cross-section (mm² or AWG) for each terminal                     | Installation compatibility constraint               |

### 5.5 Protection and Coordination Terms

| Term                         | Definition                                                                             | Functional Role                                  |
|------------------------------|----------------------------------------------------------------------------------------|--------------------------------------------------|
| Coordination Type 1         | Under short-circuit conditions, the contactor and overload relay may not be suitable for further service without repair | Lower cost, acceptable damage |
| Coordination Type 2         | Under short-circuit conditions, the contactor must remain operational; no damage beyond contact welding (which must self-clear) | Higher reliability, required for critical applications |
| SCPD                        | Short-Circuit Protective Device (fuse or circuit breaker) coordinated with the contactor | Upstream protection; determines Iq               |
| IP rating                   | Ingress Protection code per IEC 60529 (e.g., IP20 = finger-safe, no water protection) | Environmental suitability                         |
| Pollution degree            | Micro-environmental classification (1–4) affecting creepage distances                  | Insulation coordination parameter                 |

### 5.6 Standards and Classification Terms

| Term                       | Definition                                                                             | Functional Role                                    |
|----------------------------|----------------------------------------------------------------------------------------|----------------------------------------------------|
| NEMA size                  | North American sizing designation (00, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9) mapping to HP and current ranges | Variant classification for NEMA market         |
| UNSPSC 39121004            | United Nations classification code for "Magnetic contactors"                           | Procurement taxonomy classification                |
| UL 508                     | UL standard for Industrial Control Equipment; UL listing for North American market     | Market access certification                        |
| IEC 60947-4-1              | Primary international standard for contactors and motor-starters                       | Authoritative source for all rated values          |

---

## 6. Operational Logic

### 6.1 Normal Operating Sequence

```
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Control  │────▶│  Coil        │────▶│  Armature    │────▶│  Main        │
│  Signal   │     │  Energized   │     │  Pulled In   │     │  Contacts    │
│  Applied  │     │  (Us)        │     │              │     │  Close       │
└──────────┘     └──────────────┘     └──────────────┘     └──────┬───────┘
                                                                   │
                                                                   ▼
                                                            ┌──────────────┐
                                                            │  Load        │
                                                            │  Current     │
                                                            │  Flows (Ie)  │
                                                            └──────┬───────┘
                                                                   │
                                          (Control signal removed) │
                                                                   ▼
┌──────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Coil     │────▶│  Spring      │────▶│  Main        │────▶│  Arc         │
│  De-ener- │     │  Returns     │     │  Contacts    │     │  Suppression │
│  gized    │     │  Armature    │     │  Separate    │     │  Extinguishes│
└──────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

### 6.2 Energy Flow Model

```
POWER PATH (high current):
  Mains ──▶ SCPD ──▶ Contactor Main Contacts ──▶ Overload Relay ──▶ Motor/Load
                          │
                     (Ie flows when closed)

CONTROL PATH (low current):
  PLC/Button ──▶ Safety Relay ──▶ Coil Terminal (A1) ──▶ Coil ──▶ Return (A2)
                                        │
                                   (Us energizes coil)

FEEDBACK PATH:
  Auxiliary Contact ──▶ PLC Input / Indicator Lamp / Interlock Circuit
```

### 6.3 Conditional Rating Logic

Rated operational current is NOT a single fixed value. It is a **matrix**
indexed by utilization category and voltage:

```
┌──────────────────────────────────────────────────────────┐
│  Ie = f(Utilization Category, Ue, Ambient Temperature)   │
│                                                          │
│  Example for a "40A" contactor (Schneider LC1D40):       │
│    AC-1 @ 440V = 60A                                     │
│    AC-3 @ 440V = 40A                                     │
│    AC-4 @ 440V = 20A                                     │
│    AC-3 @ 440V @ 60°C = 32A  (derating)                 │
│                                                          │
│  Similarly, HP rating is conditional:                    │
│    3-phase @ 480V = 25 HP                                │
│    3-phase @ 240V = 15 HP                                │
│    1-phase @ 240V = 7.5 HP                               │
│    1-phase @ 115V = 3 HP                                 │
└──────────────────────────────────────────────────────────┘
```

### 6.4 Failure Modes and Effects

| Failure Mode              | Cause                                         | Effect                                    | Detection                                  |
|---------------------------|-----------------------------------------------|-------------------------------------------|--------------------------------------------|
| Contact welding           | Excessive inrush current, switching under AC-4 | Contactor fails to open; load runs uncontrolled | Auxiliary contact feedback mismatch     |
| Coil burnout              | Overvoltage, sustained energization, blocked armature | Contactor fails to close; load cannot start | No feedback from auxiliary contact      |
| Arc erosion               | Excessive switching frequency under load       | Contact resistance increases; overheating | Thermal monitoring, increased voltage drop |
| Mechanical fatigue        | Exceeded mechanical durability cycles          | Unreliable operation, chattering          | Vibration, audible noise                   |
| Insulation breakdown      | Overvoltage, contamination, moisture           | Phase-to-phase or phase-to-ground fault   | Dielectric test failure, trip              |
| Spring fatigue            | Exceeded lifecycle, temperature extremes        | Slow or incomplete opening; contact bounce | Timing measurement                         |

### 6.5 Regulatory and Compliance Constraints

| Constraint                                    | Rule                                                                                                    |
|-----------------------------------------------|---------------------------------------------------------------------------------------------------------|
| IEC 60947-4-1 rated values                    | All rated values must be verified by type-testing per the standard                                      |
| Short-circuit coordination                    | Every contactor installation must specify the coordinated SCPD and type (1 or 2)                        |
| Altitude derating                             | Above 2000m, rated insulation voltage and current must be derated per IEC 60947-1 Annex B               |
| Ambient temperature derating                  | Above 40°C (IEC reference), Ie must be derated per manufacturer's derating curve                        |
| NEMA ↔ IEC equivalence                        | NEMA sizes do not directly correspond to IEC frame sizes; cross-reference tables must be used            |
| UL 508 for North American market              | Contactors sold in the US/Canada must carry UL listing or CSA certification                             |
| CE marking for European market                | Contactors must comply with LVD (2014/35/EU) and EMC (2014/30/EU) directives                            |
| RoHS material restrictions                    | Lead, mercury, cadmium, hexavalent chromium, PBB, PBDE restricted per EU 2011/65/EU                     |
| Pollution degree / Overvoltage category       | Installation environment determines minimum creepage and clearance distances                             |

---

## 7. Invariants and Reasoning Rules

### 7.1 Domain Invariants (Always True)

```
INV-01: Ui ≥ Ue
  The rated insulation voltage is always greater than or equal to the
  rated operational voltage.

INV-02: Ie(AC-3) > Ie(AC-4) for the same contactor
  AC-4 (plugging/inching) derates current more than AC-3 (normal motor duty).

INV-03: Ie(AC-1) ≥ Ie(AC-3) ≥ Ie(AC-4)
  Current rating decreases with increasing switching severity.

INV-04: MechanicalDurability >> ElectricalDurability
  Mechanical lifecycle is always at least 10× the electrical lifecycle
  for any given utilization category.

INV-05: NumberOfPoles ≥ NumberOfNOContacts (main)
  The number of poles constrains the maximum main NO contact count.

INV-06: ∀ Contactor: ∃ at least one UtilizationCategory assignment
  Every contactor must be rated for at least one utilization category.

INV-07: CoilVoltage ≠ RatedOperationalVoltage (in general)
  The control circuit voltage (coil) is independent of the power circuit voltage.

INV-08: ∀ installation: ∃ coordinated SCPD
  Every contactor installation requires a specified upstream short-circuit
  protective device for safe operation.

INV-09: ContactConfiguration = f(NO_count, NC_count)
  Contact configuration is a composite derived from the individual
  NO and NC contact counts (e.g., "3NO+1NC").

INV-10: HP_rating = f(voltage, phase, NEMA_size)
  Horsepower rating is never a standalone value; it is always conditional
  on supply voltage and number of phases.
```

### 7.2 Reasoning Rules

```
RULE-01: Variant Identification
  IF two products share the same Manufacturer AND ProductFamily
  BUT differ in any of {Ie, Ue, NumberOfPoles, CoilVoltage, ContactConfiguration}
  THEN they are VARIANTS of the same product line.

RULE-02: Utilization Category Derating
  IF a contactor is rated Ie = X at AC-3
  THEN its AC-4 rating is approximately 0.4×X to 0.6×X
  AND its AC-1 rating is approximately 1.2×X to 1.6×X.

RULE-03: NEMA-to-IEC Cross-Reference
  IF NEMA size = 1
  THEN approximate IEC equivalent is Ie(AC-3) ≈ 27A at 480V
  (Use manufacturer cross-reference tables for precise mapping.)

RULE-04: Contact Configuration Parsing
  IF ContactConfiguration matches pattern /(\d+)(NO|NC)([+](\d+)(NO|NC))*/
  THEN extract individual counts:
    NO_total = Σ(count where type = NO)
    NC_total = Σ(count where type = NC)

RULE-05: Mounting Compatibility
  IF MountingType = "DIN Rail"
  THEN device must have 35mm rail clip AND width is a multiple of module pitch (typically 9mm or 17.5mm).

RULE-06: Coil Voltage Selection
  IF ControlCircuit.voltage = 24V DC
  THEN Contactor.CoilVoltage MUST be 24V DC variant.
  (Coil voltage is selected to match the control system voltage, not the load voltage.)

RULE-07: Overload Relay Sizing
  IF Contactor.Ie(AC-3) = X
  THEN OverloadRelay.SettingRange MUST include the motor FLA
  AND OverloadRelay.MaxCurrent ≥ X.

RULE-08: Auxiliary Contact Interpretation
  IF AuxiliaryContact value contains "||" separator
  THEN split on "||" and parse each segment as an independent contact specification.
  IF format is "2 NO||2 NC" → normalize to "2NO+2NC".

RULE-09: Temperature Derating
  IF AmbientTemperature > 40°C
  THEN Ie must be derated per manufacturer curve.
  Typical derating: ~2% per °C above 40°C.

RULE-10: Altitude Derating
  IF InstallationAltitude > 2000m
  THEN Ui and Ue must be derated per IEC 60947-1 Annex B.
  Typical factor: multiply voltage by (1 - 0.01 × (altitude - 2000) / 100).

RULE-11: Phase and Pole Consistency
  IF Application = "3-phase motor control"
  THEN NumberOfPoles ≥ 3.
  IF NumberOfPoles = 4 AND Application = "3-phase"
  THEN the 4th pole is a switched neutral.

RULE-12: Normalization — Multi-value Separator
  IF any attribute value contains "/" or "," as a separator between discrete values
  THEN normalize separator to " || " (space-pipe-pipe-space).
```

### 7.3 Entity Clusters

```
┌──────────────────────────────────────────────────────────────────┐
│                    CONTACTOR PRODUCT CLUSTER                      │
│                                                                  │
│  ┌─────────────────────────────┐  ┌───────────────────────────┐ │
│  │   POWER PATH CLUSTER        │  │   CONTROL PATH CLUSTER    │ │
│  │   • Main Contact            │  │   • Electromagnetic Coil  │ │
│  │   • Contact Bridge          │  │   • Control Circuit       │ │
│  │   • Arc Chamber             │  │   • Surge Suppressor      │ │
│  │   • Main Terminals          │  │   • Auxiliary Contact     │ │
│  └─────────────────────────────┘  └───────────────────────────┘ │
│                                                                  │
│  ┌─────────────────────────────┐  ┌───────────────────────────┐ │
│  │   PHYSICAL CLUSTER          │  │   PROTECTION CLUSTER      │ │
│  │   • Enclosure / Housing     │  │   • Overload Relay        │ │
│  │   • Mounting System         │  │   • SCPD (Fuse/Breaker)   │ │
│  │   • Mechanical Interlock    │  │   • Coordination Type     │ │
│  │   • Terminals               │  │   • Safety Interlock      │ │
│  └─────────────────────────────┘  └───────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │   GOVERNANCE CLUSTER                                         ││
│  │   • IEC 60947-4-1  • NEMA ICS 2  • UNSPSC                  ││
│  │   • Manufacturer   • Certification Body  • Product Family    ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 7.4 Relationship Clusters

| Cluster                  | Relationships                                                                |
|--------------------------|------------------------------------------------------------------------------|
| **Structural**           | hasComponent, carries, composedOf, partOf                                    |
| **Energy Flow**          | suppliesPowerTo, deliversPowerTo, conducts, switches                         |
| **Control Flow**         | energizes, actuates, triggers, signals, feedbackVia                          |
| **Protection**           | protects, protectsUpstreamOf, monitorsDownstreamOf, suppressesArcOf          |
| **Dependency**           | conditionalOn, coDeterminedWith, derivedFrom, constrains                     |
| **Classification**       | conformsTo, classifiedIn, certifiedBy, subClassOf                            |
| **Commercial**           | manufacturedBy, belongsTo, produces, contains                                |

### 7.5 Backbone Attribute Priority Tiers

For schema design and validation, attributes are prioritized by ontological
necessity. This ordering informs which attributes must always be present
(Tier 1), which should be present for complete modeling (Tier 2), and which
are supplementary (Tier 3).

| Tier   | Attributes                                                                                                  |
|--------|-------------------------------------------------------------------------------------------------------------|
| **T1** | Rated operational current (Ie), Rated operational voltage (Ue), Number of poles, Utilization category, Contact configuration, Coil voltage, Manufacturer, Part number |
| **T2** | Rated insulation voltage (Ui), Rated frequency, Voltage type, Mechanical durability, Electrical durability, Mounting type, Terminal type, IP rating, NEMA size, Product family, Horsepower rating |
| **T3** | Weight, Dimensions, Coil power, Coil resistance, Pick-up/drop-out time, Pollution degree, Altitude limit, Wire size range, Ambient temperature range, Contact material, Surge suppressor, Vibration resistance |

---

*This domain model serves as the canonical backbone for:*
- *Attribute resolution (structural classification, dependency modeling, confidence scoring)*
- *Normalization rules derivation (parsing rules, value canonicalization, multi-value handling)*
- *Hierarchy resolution (UNSPSC mapping, IEC/NEMA classification, manufacturer taxonomy)*
- *Knowledge graph construction (ontology triplets, entity relationships)*
- *Validation rules (invariants, derating logic, cross-attribute consistency)*
