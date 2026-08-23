"""
Scheme taxonomy
===============
Deterministic parsing of an AMFI scheme name into the facts we actually need:

    AMC  ·  SEBI category  ·  asset class  ·  plan (Direct/Regular)  ·  option (Growth/IDCW)

Why this module exists
----------------------
The previous implementation used ``name.split(" ")[0]`` for the AMC (so
"Aditya Birla Sun Life Frontline Equity" became "Aditya") and a short, badly
ordered keyword list for the category (68% of the 37k schemes landed in
"Other").  Both are load-bearing: the peer group *is* the category, and every
percentile in the product is computed inside a peer group.

The three-step parse
--------------------
Matching against the raw name is what produces howlers like
"BANK OF INDIA Liquid Fund" → *Sectoral - Banking* and
"SBI Automotive … Income Distribution cum Capital Withdrawal" → *Debt*.  The
AMC name and the plan/option suffix are noise for category purposes, so:

1. Identify the AMC from the leading tokens.
2. Identify plan and option from the whole name.
3. **Strip both** and match the category rules against what is left — the part
   of the name that actually describes the mandate.
"""

from __future__ import annotations

import re
from functools import lru_cache

# ── AMC registry ──────────────────────────────────────────────────────────────
# Canonical name → aliases that appear in AMFI scheme names.  Historic names of
# merged or renamed houses are included because the NAV history predates the
# rename and the scheme names were never rewritten.

_AMC_ALIASES: dict[str, tuple[str, ...]] = {
    "Aditya Birla Sun Life": ("aditya birla sun life", "birla sun life", "birla sunlife", "aditya birla"),
    "Axis":                  ("axis",),
    "Bajaj Finserv":         ("bajaj finserv", "bajaj"),
    "Bandhan":               ("bandhan",),
    "Bank of India":         ("bank of india", "boi axa"),
    "Baroda BNP Paribas":    ("baroda bnp paribas", "baroda pioneer", "bnp paribas", "baroda"),
    "Canara Robeco":         ("canara robeco", "canara"),
    "DSP":                   ("dsp blackrock", "dsp merrill lynch", "dsp"),
    "Edelweiss":             ("edelweiss", "jpmorgan india", "jpmorgan", "jp morgan"),
    "Franklin Templeton":    ("franklin templeton", "franklin india", "franklin", "templeton"),
    "Groww":                 ("groww", "indiabulls"),
    "HDFC":                  ("hdfc",),
    "Helios":                ("helios",),
    "HSBC":                  ("hsbc", "l&t", "l & t", "cholamandalam", "fortis"),
    "ICICI Prudential":      ("icici prudential", "icici pru", "prudential icici", "icici"),
    "IDBI":                  ("idbi",),
    "IDFC":                  ("idfc",),
    "IIFL":                  ("iifl", "360 one", "360one"),
    "Invesco":               ("invesco india", "invesco", "religare invesco", "religare", "lotus india"),
    "ITI":                   ("iti",),
    "JM Financial":          ("jm financial", "jm "),
    "Kotak":                 ("kotak mahindra", "kotak"),
    "LIC":                   ("lic mf", "lic nomura", "licmf", "lic mutual", "lic "),
    "Mahindra Manulife":     ("mahindra manulife", "mahindra"),
    "Mirae Asset":           ("mirae asset", "mirae"),
    "Motilal Oswal":         ("motilal oswal", "motilal"),
    "Navi":                  ("navi", "essel"),
    "Nippon India":          ("nippon india", "nippon", "reliance"),
    "NJ":                    ("nj ",),
    "Old Bridge":            ("old bridge",),
    "PGIM India":            ("pgim india", "pgim", "dhfl pramerica", "pramerica", "deutsche", "dws"),
    "PPFAS":                 ("parag parikh", "ppfas"),
    "Quant":                 ("quant ", "escorts"),
    "Quantum":               ("quantum",),
    "Samco":                 ("samco",),
    "SBI":                   ("sbi",),
    "Shriram":               ("shriram",),
    "Sundaram":              ("sundaram", "principal pnb", "principal"),
    "Tata":                  ("tata",),
    "Taurus":                ("taurus", "tauras"),
    "Trust":                 ("trustmf", "trust mutual", "trust "),
    "Union":                 ("union kbc", "union"),
    "Unifi":                 ("unifi",),
    "UTI":                   ("uti",),
    "White Oak":             ("white oak", "whiteoak"),
    "Zerodha":               ("zerodha",),
    # Wound-up or absorbed houses that still own a long NAV tail
    "ABN AMRO":              ("abn amro",),
    "Alliance Capital":      ("alliance capital", "alliance"),
    "Benchmark":             ("benchmark",),
    "Daiwa":                 ("daiwa",),
    "Goldman Sachs":         ("goldman sachs",),
    "Grindlays":             ("grindlays", "standard chartered"),
    "ING":                   ("ing ",),
    "Kothari Pioneer":       ("kothari pioneer", "kothari", "pioneer iti"),
    "Morgan Stanley":        ("morgan stanley",),
    "Peerless":              ("peerless",),
    "Sahara":                ("sahara",),
    "Zurich India":          ("zurich india", "zurich"),
    "Chola":                 ("chola",),
    "Dundee":                ("dundee",),
    "First India":           ("first india",),
    "GIC":                   ("gic ",),
    "Jeevan Bima":           ("jeevan bima",),
    "SUN F&C":               ("sun f&c",),
}

_AMC_LOOKUP: list[tuple[str, str]] = sorted(
    ((alias, canonical) for canonical, aliases in _AMC_ALIASES.items() for alias in aliases),
    key=lambda pair: -len(pair[0]),
)


@lru_cache(maxsize=65536)
def infer_amc(scheme_name: str) -> str:
    """Canonical AMC for a raw AMFI scheme name."""
    lowered = scheme_name.lower().strip()
    for alias, canonical in _AMC_LOOKUP:
        if lowered.startswith(alias):
            return canonical
    padded = f" {lowered} "
    for alias, canonical in _AMC_LOOKUP:
        if f" {alias.strip()} " in padded:
            return canonical
    words = scheme_name.split()
    return " ".join(words[:2]) if words else "Unknown"


@lru_cache(maxsize=65536)
def _amc_prefix_length(scheme_name: str) -> int:
    """Characters at the head of the name occupied by the AMC brand."""
    lowered = scheme_name.lower().strip()
    for alias, _ in _AMC_LOOKUP:
        if lowered.startswith(alias):
            return len(alias)
    return 0


# ── Plan / option ─────────────────────────────────────────────────────────────
# "IDCW" is spelled out in full on a large share of post-2021 scheme names, and
# an unrecognised IDCW plan pollutes the Growth universe with a NAV series that
# gaps down on every payout.

_DIRECT = re.compile(r"\bdirect\b", re.I)
_REGULAR = re.compile(r"\bregular\b|\bretail\b", re.I)
_IDCW = re.compile(
    r"\bidcw\b"
    r"|income\s*dist(ribution)?\.?\s*cum\s*cap(ital)?\.?\s*(withdrawal|wdrl)"
    r"|\bdividend\b|\bdiv\b|\bpayout\b|reinvest|\bbonus\b|\bmip\b",
    re.I,
)
_GROWTH = re.compile(r"\bgrowth\b|cumulative", re.I)

#: Everything below describes the *share class*, not the mandate, and is
#: removed before category matching.
_NOISE = re.compile(
    r"\(?\s*formerly[^)]*\)?"
    r"|income\s*dist(ribution)?\.?\s*cum\s*cap(ital)?\.?\s*(withdrawal|wdrl)"
    r"|\b(direct|regular|retail|institutional|super\s*institutional|wholesale)\b"
    r"|\b(growth|idcw|dividend|payout|reinvestment|reinvest|cumulative|bonus)\b"
    r"|\b(plan|option|scheme|fund)\b\s*$"
    r"|\b(half\s*yearly|quarterly|monthly|fortnightly|weekly|daily|annual)\b"
    r"|\bunclaimed\b|\bsegregated\s*portfolio\b",
    re.I,
)


def infer_plan(scheme_name: str) -> str:
    if _DIRECT.search(scheme_name):
        return "Direct"
    # AMFI omits the word on pre-2013 plans, which predate the Direct regime.
    return "Regular"


def infer_option(scheme_name: str) -> str:
    """IDCW wins: a payout distorts NAV whatever else the name claims."""
    if _IDCW.search(scheme_name):
        return "IDCW"
    if _GROWTH.search(scheme_name):
        return "Growth"
    return "Growth"


@lru_cache(maxsize=65536)
def mandate_text(scheme_name: str) -> str:
    """The scheme name reduced to the part that describes what it invests in."""
    core = scheme_name[_amc_prefix_length(scheme_name):]
    core = _NOISE.sub(" ", core)
    core = re.sub(r"[\-–—_/,()]+", " ", core)
    return re.sub(r"\s+", " ", core).strip()


# ── Asset classes ─────────────────────────────────────────────────────────────

EQUITY = "Equity"
DEBT = "Debt"
HYBRID = "Hybrid"
INDEX = "Index"
COMMODITY = "Commodity"
INTERNATIONAL = "International"
SOLUTION = "Solution"
OTHER_CLASS = "Other"


# ── Category rules ────────────────────────────────────────────────────────────
# (pattern, category, asset_class). Order is significant — most specific first.
# Patterns are matched against ``mandate_text``, never the raw name.

_FOREIGN = (
    r"\bus\b|u\.s\.|america|nasdaq|s&p\s*500|nyse|\bfang\b|global|international|"
    r"overseas|world|foreign|emerging\s*market|greater\s*china|china|japan|taiwan|"
    r"korea|europe|asean|\bmsci\b(?!\s*india)|hang\s*seng|brazil|developed"
)

_RULES: list[tuple[re.Pattern[str], str, str]] = [
    # ── Closed-ended wrappers: tested first because their names frequently
    #    contain words like "equity" that would otherwise misroute them ───────
    (re.compile(r"\bfmp\b|fixed\s*maturity|fixed\s*term|fixed\s*horizon|\bftp\b|\bfhf\b|"
                r"interval\s*(fund|plan)|capital\s*protection|dual\s*advantage|"
                r"\bftif\b|\bfts\b|series\s+\d+.*\bdays?\b", re.I),
     "Fixed Maturity Plan", DEBT),

    # ── Commodity ────────────────────────────────────────────────────────────
    (re.compile(r"\bsilver\b", re.I), "Silver", COMMODITY),
    (re.compile(r"\bgold\b", re.I), "Gold", COMMODITY),

    # ── Solution oriented ────────────────────────────────────────────────────
    (re.compile(r"retirement|pension", re.I), "Retirement", SOLUTION),
    (re.compile(r"children|child\b|young\s*citizen|gift\s*fund", re.I), "Children's", SOLUTION),

    # ── Debt index / target maturity: an "Index Fund" that holds bonds is a
    #    debt product and must be ranked against debt funds, not the Nifty ────
    (re.compile(r"(gilt|\bsdl\b|g-?sec|\bibx\b|\bbond\b|psu\s*debt|banking\s*(and|&)\s*psu)"
                r".*(index|target\s*maturity|\betf\b|roll\s*down)", re.I),
     "Target Maturity", DEBT),
    (re.compile(r"target\s*maturity|roll\s*down", re.I), "Target Maturity", DEBT),
    (re.compile(r"liquid.*\betf\b|\betf\b.*liquid|overnight.*\betf\b", re.I), "Liquid", DEBT),
    # "Banking & PSU Debt" must beat both the PSU and the Banking equity rules.
    (re.compile(r"bank(ing)?\s*(and|&|\+)?\s*psu|psu\s*(and|&)?\s*bank|\bpsu\s*debt\b",
                re.I), "Banking & PSU Debt", DEBT),

    # ── International (before index/FoF so foreign trackers land here) ───────
    (re.compile(_FOREIGN, re.I), "International / FoF", INTERNATIONAL),

    # ── Domestic fund-of-funds ───────────────────────────────────────────────
    (re.compile(r"\bfof\b|fund\s*of\s*funds?|feeder", re.I), "Fund of Funds", HYBRID),

    # ── Index & ETF ──────────────────────────────────────────────────────────
    (re.compile(r"nifty\s*next\s*50|nifty\s*junior", re.I), "Index - Nifty Next 50", INDEX),
    (re.compile(r"equal\s*weight", re.I), "Index - Equal Weight", INDEX),
    (re.compile(r"nifty\s*50(?!\d)|nifty50(?!\d)|nifty\s*fifty", re.I), "Index - Nifty 50", INDEX),
    (re.compile(r"sensex|bse\s*30(?!\d)", re.I), "Index - Sensex", INDEX),
    (re.compile(r"(nifty|bse).{0,12}(mid\s*cap|midcap|150|midsmall)", re.I), "Index - Midcap", INDEX),
    (re.compile(r"(nifty|bse).{0,12}(small\s*cap|smallcap|250)", re.I), "Index - Smallcap", INDEX),
    (re.compile(r"(nifty|bse).{0,16}(bank|financial|\bit\b|pharma|healthcare|auto|"
                r"psu|infra|energy|consum|metal|realty|fmcg|commodit|manufactur|"
                r"defen[cs]e|dividend|alpha|quality|value|momentum|low\s*volatility|\besg\b)",
                re.I), "Index - Sector & Factor", INDEX),
    (re.compile(r"nifty\s*(100|200|500|750)|bse\s*(200|500)|total\s*market|"
                r"broad\s*(base|market)|all\s*cap\s*index", re.I), "Index - Broad Market", INDEX),
    (re.compile(r"\bindex\b|\betf\b|passive|tracking|replicat", re.I), "Index - Other", INDEX),

    # ── Hybrid ───────────────────────────────────────────────────────────────
    (re.compile(r"aggressive\s*hybrid", re.I), "Aggressive Hybrid", HYBRID),
    (re.compile(r"conservative\s*hybrid|monthly\s*income", re.I), "Conservative Hybrid", HYBRID),
    (re.compile(r"balanced\s*advantage|dynamic\s*asset\s*alloc", re.I), "Balanced Advantage", HYBRID),
    (re.compile(r"multi[\s-]*asset", re.I), "Multi Asset Allocation", HYBRID),
    (re.compile(r"equity\s*savings", re.I), "Equity Savings", HYBRID),
    (re.compile(r"arbitrage", re.I), "Arbitrage", HYBRID),
    (re.compile(r"equity\s*(and|&)\s*debt|debt\s*(and|&)\s*equity", re.I), "Aggressive Hybrid", HYBRID),
    (re.compile(r"asset\s*alloc|balanced|\bhybrid\b", re.I), "Balanced Advantage", HYBRID),

    # ── Sectoral / thematic equity ───────────────────────────────────────────
    (re.compile(r"defen[cs]e", re.I), "Sectoral - Defence", EQUITY),
    (re.compile(r"\bpsu\b|public\s*sector", re.I), "Sectoral - PSU", EQUITY),
    (re.compile(r"bank(ing)?\s*(and|&)\s*financial|financial\s*service|\bbfsi\b|"
                r"bank(ing)?\s*(sector|fund)|\bbanking\b(?!\s*(and|&)\s*psu)",
                re.I), "Sectoral - Banking & Financial", EQUITY),
    (re.compile(r"pharma|health\s*care|healthcare|\bhealth\b|life\s*science|medical",
                re.I), "Sectoral - Pharma & Healthcare", EQUITY),
    (re.compile(r"\bit\b|infotech|information\s*technology|\btechnolog|\btech\b|digital",
                re.I), "Sectoral - Technology", EQUITY),
    (re.compile(r"infrastructur|\binfra\b", re.I), "Sectoral - Infrastructure", EQUITY),
    (re.compile(r"consum|\bfmcg\b|retail\s*(sector|theme)", re.I), "Sectoral - Consumption", EQUITY),
    (re.compile(r"energy|\bpower\b|\boil\b|petroleum|natural\s*resource|\bmining\b|metal",
                re.I), "Sectoral - Energy & Resources", EQUITY),
    (re.compile(r"manufactur|\bauto\b|automotive|automobile|transport|logistic",
                re.I), "Sectoral - Manufacturing & Auto", EQUITY),
    (re.compile(r"\bmnc\b|multinational", re.I), "Sectoral - MNC", EQUITY),
    (re.compile(r"\breit\b|real\s*estate|realty|housing", re.I), "Sectoral - Real Estate", EQUITY),
    (re.compile(r"\besg\b|innovat|special\s*(situation|opportunit)|business\s*cycle|"
                r"\bquality\b|\bmomentum\b|\balpha\b|thematic|\btheme\b|rural|"
                r"\bexport\b|\btourism\b|\bservices\b", re.I), "Thematic", EQUITY),

    # ── Diversified equity (SEBI categories) ─────────────────────────────────
    (re.compile(r"\belss\b|tax\s*sav|tax\s*plan|tax\s*relief|tax\s*advantage|"
                r"tax\s*shield|tax\s*gain|long\s*term\s*equity", re.I), "ELSS", EQUITY),
    (re.compile(r"large\s*(and|&)?\s*mid\s*cap|large\s*[-&]\s*mid|emerging\s*blue\s*?chip",
                re.I), "Large & Mid Cap", EQUITY),
    (re.compile(r"large\s*cap|largecap|bluechip|blue\s*chip|top\s*100|frontline",
                re.I), "Large Cap", EQUITY),
    (re.compile(r"mid\s*cap|midcap", re.I), "Mid Cap", EQUITY),
    (re.compile(r"small\s*cap|smallcap|micro\s*cap", re.I), "Small Cap", EQUITY),
    (re.compile(r"flexi\s*cap|flexicap", re.I), "Flexi Cap", EQUITY),
    (re.compile(r"multi\s*[-\s]*cap|multicap", re.I), "Multi Cap", EQUITY),
    (re.compile(r"focus(ed|sed)?\b", re.I), "Focused", EQUITY),
    (re.compile(r"\bvalue\b|contra", re.I), "Value / Contra", EQUITY),
    (re.compile(r"dividend\s*yield", re.I), "Dividend Yield", EQUITY),

    # ── Debt (SEBI categories) ───────────────────────────────────────────────
    (re.compile(r"overnight", re.I), "Overnight", DEBT),
    (re.compile(r"liquid|cash\s*(plus|management|fund)|treasury\s*advantage", re.I), "Liquid", DEBT),
    (re.compile(r"ultra\s*short", re.I), "Ultra Short Duration", DEBT),
    (re.compile(r"low\s*duration", re.I), "Low Duration", DEBT),
    (re.compile(r"money\s*market", re.I), "Money Market", DEBT),
    (re.compile(r"short\s*(term|duration)", re.I), "Short Duration", DEBT),
    (re.compile(r"medium\s*(to\s*long\s*)?(term|duration)", re.I), "Medium Duration", DEBT),
    (re.compile(r"long\s*(term\s*)?duration|long\s*term\s*bond", re.I), "Long Duration", DEBT),
    (re.compile(r"corporate\s*(bond|debt)|credit\s*opportunit", re.I), "Corporate Bond", DEBT),
    (re.compile(r"credit\s*risk", re.I), "Credit Risk", DEBT),
    (re.compile(r"\bgilt\b|government\s*securit|\bg-?sec\b|\bsdl\b", re.I), "Gilt", DEBT),
    (re.compile(r"banking\s*(and|&)\s*psu|\bpsu\s*debt\b", re.I), "Banking & PSU Debt", DEBT),
    (re.compile(r"float(er|ing)", re.I), "Floater", DEBT),
    (re.compile(r"dynamic\s*bond|all\s*seasons|strategic\s*bond", re.I), "Dynamic Bond", DEBT),
    (re.compile(r"\bincome\b|\bbond\b|\bdebt\b|\bcredit\b|\bsavings\b|\bgsf\b",
                re.I), "Debt - Other", DEBT),

    # ── Generic equity fallback (last, so it never steals a specific match) ──
    (re.compile(r"equity|opportunit|\bprima\b|\bvision\b|advantage|discovery|"
                r"\bcore\b|\bemerging\b|\bgrowth\b|\bcapital\b", re.I), "Flexi Cap", EQUITY),
]

CATEGORY_ASSET_CLASS: dict[str, str] = {}
for _pattern, _cat, _cls in _RULES:
    CATEGORY_ASSET_CLASS.setdefault(_cat, _cls)
CATEGORY_ASSET_CLASS["Other"] = OTHER_CLASS

#: Stable display order — broadly "how much equity risk", then wrappers.
CATEGORY_ORDER: list[str] = [
    "Large Cap", "Large & Mid Cap", "Flexi Cap", "Multi Cap", "Mid Cap", "Small Cap",
    "Focused", "Value / Contra", "Dividend Yield", "ELSS",
    "Sectoral - Banking & Financial", "Sectoral - Technology",
    "Sectoral - Pharma & Healthcare", "Sectoral - Infrastructure",
    "Sectoral - Consumption", "Sectoral - Energy & Resources",
    "Sectoral - Manufacturing & Auto", "Sectoral - PSU", "Sectoral - Defence",
    "Sectoral - MNC", "Sectoral - Real Estate", "Thematic",
    "Index - Nifty 50", "Index - Sensex", "Index - Nifty Next 50",
    "Index - Broad Market", "Index - Midcap", "Index - Smallcap",
    "Index - Sector & Factor", "Index - Equal Weight", "Index - Other",
    "Aggressive Hybrid", "Balanced Advantage", "Multi Asset Allocation",
    "Equity Savings", "Conservative Hybrid", "Arbitrage", "Fund of Funds",
    "Gold", "Silver", "International / FoF", "Retirement", "Children's",
    "Overnight", "Liquid", "Ultra Short Duration", "Low Duration", "Money Market",
    "Short Duration", "Medium Duration", "Long Duration", "Corporate Bond",
    "Banking & PSU Debt", "Credit Risk", "Gilt", "Floater", "Dynamic Bond",
    "Target Maturity", "Debt - Other", "Fixed Maturity Plan", "Other",
]


@lru_cache(maxsize=65536)
def infer_category(scheme_name: str) -> tuple[str, str]:
    """``(category, asset_class)`` for a raw AMFI scheme name."""
    core = mandate_text(scheme_name)
    haystack = core or scheme_name
    for pattern, category, asset_class in _RULES:
        if pattern.search(haystack):
            return category, asset_class
    return "Other", OTHER_CLASS


def asset_class_for(category: str) -> str:
    return CATEGORY_ASSET_CLASS.get(category, OTHER_CLASS)


# ── Peer-group resolution ─────────────────────────────────────────────────────

#: Never shown as investable: closed-ended and matured by construction.
EXCLUDED_CATEGORIES = frozenset({"Fixed Maturity Plan"})


def peer_group_for(category: str, asset_class: str) -> str:
    """
    Fallback ranking bucket for categories too small to give a stable
    percentile.  Ranking a fund against three peers is noise, not signal.
    """
    return asset_class or OTHER_CLASS


def parse_scheme(scheme_name: str) -> dict[str, str]:
    """One-shot parse of everything derivable from the scheme name."""
    category, asset_class = infer_category(scheme_name)
    return {
        "amc_name": infer_amc(scheme_name),
        "category": category,
        "asset_class": asset_class,
        "plan_type": infer_plan(scheme_name),
        "option_type": infer_option(scheme_name),
    }
