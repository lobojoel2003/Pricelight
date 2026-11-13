# SPDX-License-Identifier: AGPL-3.0-or-later
"""Plain-language names for commonly shopped services.

Hospital files describe services in chargemaster shorthand
("MRI BRN W/O & W/DYE"). For well-known codes we show a consumer-friendly
label instead, written for this project, plus search keywords. The list is
modeled on the CMS "shoppable services" list (45 CFR 180.60) and
extended with a few everyday services.

Codes are identifiers; the labels below are our own words, not official
code descriptors.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Service:
    code_type: str
    code: str
    label: str
    category: str
    setting: str
    #: Rough national reference payment in USD, used only to generate demo data.
    base: float
    keywords: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.code_type}:{self.code}"


IMAGING = "Imaging"
PROCEDURES = "Procedures & surgery"
LABS = "Lab tests"
VISITS = "Visits & therapy"
MATERNITY = "Pregnancy & childbirth"
STAYS = "Hospital stays"

# fmt: off
SERVICES: tuple[Service, ...] = (
    # Imaging
    Service("CPT", "70553", "MRI of the brain, without and with contrast", IMAGING, "outpatient", 460, ("mri", "head", "brain scan", "magnetic resonance")),
    Service("CPT", "70551", "MRI of the brain, without contrast", IMAGING, "outpatient", 310, ("mri", "head", "brain scan")),
    Service("CPT", "72148", "MRI of the lower back (lumbar spine), without contrast", IMAGING, "outpatient", 290, ("mri", "back", "spine", "lumbar")),
    Service("CPT", "73721", "MRI of the knee or other leg joint, without contrast", IMAGING, "outpatient", 280, ("mri", "knee", "joint", "leg")),
    Service("CPT", "70450", "CT scan of the head, without contrast", IMAGING, "outpatient", 160, ("ct", "cat scan", "head", "brain")),
    Service("CPT", "74177", "CT scan of the abdomen and pelvis, with contrast", IMAGING, "outpatient", 330, ("ct", "cat scan", "belly", "stomach", "abdomen")),
    Service("CPT", "71046", "Chest X-ray, 2 views", IMAGING, "outpatient", 42, ("xray", "x-ray", "chest", "lungs")),
    Service("CPT", "72110", "X-ray of the lower spine, 4 or more views", IMAGING, "outpatient", 62, ("xray", "x-ray", "back", "spine")),
    Service("CPT", "76700", "Ultrasound of the abdomen, complete", IMAGING, "outpatient", 125, ("ultrasound", "sonogram", "abdomen")),
    Service("CPT", "76805", "Pregnancy ultrasound, after the first trimester", MATERNITY, "outpatient", 135, ("ultrasound", "sonogram", "pregnancy", "baby")),
    Service("CPT", "77067", "Screening mammogram, both breasts", IMAGING, "outpatient", 135, ("mammogram", "breast", "screening")),
    # Procedures
    Service("CPT", "45378", "Colonoscopy, diagnostic", PROCEDURES, "outpatient", 760, ("colonoscopy", "scope", "colon")),
    Service("CPT", "45380", "Colonoscopy with biopsy", PROCEDURES, "outpatient", 860, ("colonoscopy", "biopsy", "colon")),
    Service("HCPCS", "G0121", "Screening colonoscopy, average risk", PROCEDURES, "outpatient", 720, ("colonoscopy", "screening", "colon cancer")),
    Service("CPT", "43239", "Upper GI endoscopy with biopsy", PROCEDURES, "outpatient", 710, ("endoscopy", "egd", "stomach", "scope")),
    Service("CPT", "47562", "Gallbladder removal, laparoscopic", PROCEDURES, "outpatient", 3600, ("gallbladder", "cholecystectomy", "surgery")),
    Service("CPT", "49505", "Inguinal hernia repair, age 5 or older", PROCEDURES, "outpatient", 2900, ("hernia", "surgery", "groin")),
    Service("CPT", "29881", "Knee arthroscopy with meniscus repair", PROCEDURES, "outpatient", 2800, ("knee", "arthroscopy", "meniscus", "scope")),
    Service("CPT", "66984", "Cataract removal with lens implant", PROCEDURES, "outpatient", 1900, ("cataract", "eye", "lens")),
    Service("CPT", "42820", "Tonsil and adenoid removal, under age 12", PROCEDURES, "outpatient", 1800, ("tonsils", "tonsillectomy", "adenoids", "child")),
    Service("CPT", "64483", "Lower-back epidural steroid injection", PROCEDURES, "outpatient", 620, ("epidural", "injection", "back pain", "spine")),
    # Labs
    Service("CPT", "80048", "Basic metabolic panel", LABS, "outpatient", 9, ("blood test", "bmp", "electrolytes")),
    Service("CPT", "80053", "Comprehensive metabolic panel", LABS, "outpatient", 11, ("blood test", "cmp", "liver", "kidney")),
    Service("CPT", "80061", "Lipid panel (cholesterol)", LABS, "outpatient", 13, ("cholesterol", "blood test", "lipids")),
    Service("CPT", "85025", "Complete blood count (CBC) with differential", LABS, "outpatient", 8, ("cbc", "blood count", "blood test")),
    Service("CPT", "84443", "Thyroid test (TSH)", LABS, "outpatient", 17, ("thyroid", "tsh", "blood test")),
    Service("CPT", "83036", "Hemoglobin A1c (diabetes test)", LABS, "outpatient", 10, ("a1c", "diabetes", "blood sugar")),
    Service("CPT", "84153", "PSA test (prostate)", LABS, "outpatient", 18, ("psa", "prostate", "blood test")),
    Service("CPT", "81003", "Urinalysis, automated", LABS, "outpatient", 3, ("urine test", "urinalysis")),
    # Visits & therapy
    Service("CPT", "99203", "Office visit, new patient (30-44 minutes)", VISITS, "outpatient", 115, ("doctor visit", "new patient", "appointment")),
    Service("CPT", "99213", "Office visit, returning patient (20-29 minutes)", VISITS, "outpatient", 92, ("doctor visit", "follow up", "appointment")),
    Service("CPT", "99285", "Emergency room visit, high severity", VISITS, "outpatient", 470, ("er", "emergency", "urgent")),
    Service("CPT", "93000", "Electrocardiogram (ECG/EKG)", VISITS, "outpatient", 17, ("ecg", "ekg", "heart")),
    Service("CPT", "95810", "Overnight sleep study", VISITS, "outpatient", 660, ("sleep study", "sleep apnea", "polysomnography")),
    Service("CPT", "97110", "Physical therapy exercises, 15 minutes", VISITS, "outpatient", 31, ("physical therapy", "pt", "rehab")),
    Service("CPT", "90837", "Psychotherapy session, 60 minutes", VISITS, "outpatient", 155, ("therapy", "counseling", "mental health")),
    # Pregnancy & childbirth
    Service("CPT", "59400", "Routine pregnancy care with vaginal delivery", MATERNITY, "both", 2550, ("childbirth", "delivery", "pregnancy", "baby")),
    Service("CPT", "59510", "Routine pregnancy care with cesarean delivery", MATERNITY, "both", 2950, ("c-section", "cesarean", "childbirth", "baby")),
    Service("MS-DRG", "807", "Vaginal delivery hospital stay, no complications", MATERNITY, "inpatient", 5600, ("childbirth", "delivery", "labor", "baby")),
    Service("MS-DRG", "788", "C-section hospital stay, no complications", MATERNITY, "inpatient", 8600, ("c-section", "cesarean", "childbirth", "baby")),
    # Hospital stays
    Service("MS-DRG", "470", "Hip or knee replacement, without major complications", STAYS, "inpatient", 13200, ("knee replacement", "hip replacement", "joint", "surgery")),
    Service("MS-DRG", "460", "Spinal fusion (not neck), without major complications", STAYS, "inpatient", 27500, ("spinal fusion", "back surgery", "spine")),
    Service("MS-DRG", "473", "Neck (cervical) spinal fusion, without complications", STAYS, "inpatient", 16500, ("neck", "spinal fusion", "cervical")),
    Service("MS-DRG", "743", "Uterine and ovary procedures, non-cancer, without complications", STAYS, "inpatient", 7100, ("hysterectomy", "uterus", "ovary", "surgery")),
    Service("MS-DRG", "871", "Sepsis treatment with major complications", STAYS, "inpatient", 12400, ("sepsis", "infection")),
    Service("MS-DRG", "291", "Heart failure treatment with major complications", STAYS, "inpatient", 9600, ("heart failure", "chf", "cardiac")),
    Service("MS-DRG", "194", "Pneumonia treatment with complications", STAYS, "inpatient", 6600, ("pneumonia", "lungs", "infection")),
    Service("MS-DRG", "392", "Digestive disorder stay, without major complications", STAYS, "inpatient", 5100, ("gastroenteritis", "stomach", "digestive")),
)
# fmt: on

BY_KEY: dict[str, Service] = {s.key: s for s in SERVICES}

#: Billing code systems that identify the same service across hospitals.
SEARCHABLE_CODE_TYPES: tuple[str, ...] = (
    "CPT",
    "HCPCS",
    "MS-DRG",
    "APR-DRG",
    "DRG",
    "AP-DRG",
    "APS-DRG",
    "TRIS-DRG",
    "MS-LTC-DRG",
    "CDT",
    "EAPG",
    "APC",
    "HIPPS",
    "CMG",
)

_CATEGORY_BY_TYPE = {
    "MS-DRG": STAYS,
    "APR-DRG": STAYS,
    "DRG": STAYS,
    "AP-DRG": STAYS,
    "APS-DRG": STAYS,
    "TRIS-DRG": STAYS,
    "MS-LTC-DRG": STAYS,
    "CDT": "Dental",
}


def category_for(code_type: str, code: str) -> str:
    """Best-effort category for a code that is not in the curated list."""
    service = BY_KEY.get(f"{code_type}:{code}")
    if service is not None:
        return service.category
    if code_type in _CATEGORY_BY_TYPE:
        return _CATEGORY_BY_TYPE[code_type]
    if code_type == "CPT" and code[:5].isdigit():
        n = int(code[:5])
        if 70000 <= n < 80000:
            return IMAGING
        if 80000 <= n < 90000:
            return LABS
        if 10000 <= n < 70000:
            return PROCEDURES
        if n >= 90000:
            return VISITS
    if code_type == "HCPCS" and code[:1] == "J":
        return "Drugs"
    return "Other services"
