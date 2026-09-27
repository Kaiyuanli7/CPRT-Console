"""Map raw seller names on listings to parent insurance groups.

First matching pattern wins; subsidiary brands roll up to the parent
(e.g. National General -> Allstate). Exact-name overrides set on the Data
quality tab take priority over the patterns.
"""
from __future__ import annotations

import re

CARRIER_PATTERNS: list[tuple[str, str]] = [
    ("State Farm", r"STATE\s*FARM"),
    ("Progressive", r"PROGRESSIVE"),
    ("GEICO", r"GEICO|GOVERNMENT\s+EMPLOYEES"),
    ("Allstate", r"ALLSTATE|ESURANCE|NATIONAL\s+GENERAL|ENCOMPASS|DIRECT\s+GENERAL"),
    ("USAA", r"\bUSAA\b|UNITED\s+SERVICES\s+AUTO"),
    ("Farmers", r"FARMERS\s+(INS|GROUP|EXCH|MUTUAL)|BRISTOL\s+WEST|21ST\s+CENTURY|FOREMOST"),
    ("Liberty Mutual", r"LIBERTY\s+MUTUAL|SAFECO"),
    ("Nationwide", r"NATIONWIDE"),
    ("Travelers", r"TRAVELERS"),
    ("American Family", r"AMERICAN\s+FAMILY|\bAMFAM\b"),
    ("AAA / Auto Club", r"\bAAA\b|AUTO\s+CLUB|\bCSAA\b|\bACG\b"),
    ("Erie", r"\bERIE\s+(INS|INDEMNITY|FAMILY)"),
    ("Kemper", r"KEMPER|INFINITY\s+(INS|AUTO|P&C)"),
    ("Mercury", r"MERCURY\s+(INS|CAS|GEN)"),
    ("The Hartford", r"HARTFORD"),
    ("Auto-Owners", r"AUTO[-\s]OWNERS"),
]
GROUPS = [name for name, _ in CARRIER_PATTERNS] + ["Other insurer", "Non-insurance", "Unknown"]
NOT_INSURANCE = {"Other insurer", "Non-insurance", "Unknown"}

OTHER_INSURER = re.compile(
    r"\bINS(URANCE)?\b|\bINS\s+CO\b|MUTUAL|CASUALTY|INDEMNITY|ASSURANCE|UNDERWRITERS|RECIPROCAL|\bP&C\b", re.I)
NON_INSURANCE = re.compile(
    r"DEALER|MOTORS|AUTO\s+SALES|AUTO\s+GROUP|RENTAL|RENT\s+A\s+CAR|ENTERPRISE|HERTZ|AVIS|BUDGET|"
    r"BANK|CREDIT|FINANCE|FINANCIAL|LEASING|LEASE|FLEET|CHARIT|DONAT|KARS\s+4|CITY\s+OF|COUNTY|"
    r"POLICE|STATE\s+OF|TOWING|TOW\b|RECOVERY|IMPOUND|CASH\s+FOR\s+CARS|COPART\s+DIRECT", re.I)
_COMPILED = [(name, re.compile(pat, re.I)) for name, pat in CARRIER_PATTERNS]


def normalize_name(seller) -> str:
    return re.sub(r"\s+", " ", str(seller or "")).strip().upper()


def canonical(seller_raw, overrides: dict | None = None) -> str:
    """Parent insurer, or 'Other insurer' / 'Non-insurance' / 'Unknown'."""
    s = normalize_name(seller_raw)
    if not s or s.lower() in {"nan", "none", "n/a", "na", "-"}:
        return "Unknown"
    if overrides:
        hit = overrides.get(s)
        if hit:
            return hit
    for name, rx in _COMPILED:
        if rx.search(s):
            return name
    if NON_INSURANCE.search(s):
        return "Non-insurance"
    if OTHER_INSURER.search(s):
        return "Other insurer"
    return "Unknown"


def is_insurer(group: str) -> bool:
    return group not in ("Non-insurance", "Unknown")
