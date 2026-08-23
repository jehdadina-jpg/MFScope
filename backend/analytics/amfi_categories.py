"""
AMFI scheme-type → canonical category
=====================================
``NAVAll.txt`` is not a flat CSV.  It is grouped, and the group headers carry
AMFI's own SEBI classification:

    Open Ended Schemes(Equity Scheme - Large & Mid Cap Fund)
    Aditya Birla Sun Life Mutual Fund
    119551;INF209KA12Z1;INF209KA13Z9;<name>;Direct Plan;IDCW;106.88;21-Aug-2026

That header is authoritative — it is the classification the fund is actually
registered under, not a guess from its marketing name.  Reading it removes the
entire class of errors that name-matching produces ("BANK OF INDIA Liquid
Fund" is not a banking-sector fund).

Two AMFI buckets are deliberately too coarse for a screener:

* ``Sectoral/ Thematic`` lumps a pharma fund with a defence fund;
* ``Index Funds`` lumps a Nifty 50 tracker with a smallcap tracker.

For those two — and only those two — we refine the AMFI bucket with the
name-based rules in :mod:`backend.analytics.taxonomy`, because ranking a
Nifty 50 tracker against a smallcap tracker is not a like-for-like comparison.
"""

from __future__ import annotations

import re
from functools import lru_cache

from backend.analytics.taxonomy import (
    COMMODITY,
    DEBT,
    EQUITY,
    HYBRID,
    INDEX,
    INTERNATIONAL,
    OTHER_CLASS,
    SOLUTION,
    infer_category,
)

#: Normalised AMFI leaf name → (canonical category, asset class).
_AMFI_MAP: dict[str, tuple[str, str]] = {
    # ── Equity ───────────────────────────────────────────────────────────────
    "large cap fund": ("Large Cap", EQUITY),
    "large & mid cap fund": ("Large & Mid Cap", EQUITY),
    "mid cap fund": ("Mid Cap", EQUITY),
    "small cap fund": ("Small Cap", EQUITY),
    "multi cap fund": ("Multi Cap", EQUITY),
    "flexi cap fund": ("Flexi Cap", EQUITY),
    "focused fund": ("Focused", EQUITY),
    "value fund": ("Value / Contra", EQUITY),
    "contra fund": ("Value / Contra", EQUITY),
    "dividend yield fund": ("Dividend Yield", EQUITY),
    "elss": ("ELSS", EQUITY),
    "elss- tax saver fund": ("ELSS", EQUITY),
    "elss tax saver fund": ("ELSS", EQUITY),
    "growth": ("Flexi Cap", EQUITY),

    # ── Hybrid ───────────────────────────────────────────────────────────────
    "aggressive hybrid fund": ("Aggressive Hybrid", HYBRID),
    "conservative hybrid fund": ("Conservative Hybrid", HYBRID),
    "balanced hybrid fund": ("Balanced Hybrid", HYBRID),
    "arbitrage fund": ("Arbitrage", HYBRID),
    "equity savings": ("Equity Savings", HYBRID),
    "equity savings fund": ("Equity Savings", HYBRID),
    "multi asset allocation": ("Multi Asset Allocation", HYBRID),
    "multi asset allocation fund": ("Multi Asset Allocation", HYBRID),
    "dynamic asset allocation or balanced advantage": ("Balanced Advantage", HYBRID),
    "balanced advantage fund/ dynamic asset allocation": ("Balanced Advantage", HYBRID),

    # ── Debt ─────────────────────────────────────────────────────────────────
    "overnight fund": ("Overnight", DEBT),
    "liquid fund": ("Liquid", DEBT),
    "liquid": ("Liquid", DEBT),
    "ultra short duration fund": ("Ultra Short Duration", DEBT),
    "ultra short term fund": ("Ultra Short Duration", DEBT),
    "ultra short to short term fund": ("Ultra Short Duration", DEBT),
    "low duration fund": ("Low Duration", DEBT),
    "money market fund": ("Money Market", DEBT),
    "money market": ("Money Market", DEBT),
    "short duration fund": ("Short Duration", DEBT),
    "short term fund": ("Short Duration", DEBT),
    "medium duration fund": ("Medium Duration", DEBT),
    "medium term fund": ("Medium Duration", DEBT),
    "medium to long duration fund": ("Medium to Long Duration", DEBT),
    "medium to long term fund": ("Medium to Long Duration", DEBT),
    "long duration fund": ("Long Duration", DEBT),
    "long term fund": ("Long Duration", DEBT),
    "corporate bond fund": ("Corporate Bond", DEBT),
    "credit risk fund": ("Credit Risk", DEBT),
    "banking and psu fund": ("Banking & PSU Debt", DEBT),
    "banking and psu debt fund": ("Banking & PSU Debt", DEBT),
    "gilt fund": ("Gilt", DEBT),
    "gilt": ("Gilt", DEBT),
    "gilt fund with 10 year constant duration": ("Gilt - 10Y Constant", DEBT),
    "10-year constant maturity gilt fund": ("Gilt - 10Y Constant", DEBT),
    "floater fund": ("Floater", DEBT),
    "floating interest rates fund": ("Floater", DEBT),
    "dynamic bond": ("Dynamic Bond", DEBT),
    "dynamic term fund": ("Dynamic Bond", DEBT),
    "income": ("Debt - Other", DEBT),
    "other debt scheme": ("Debt - Other", DEBT),

    # ── Closed-ended wrappers ────────────────────────────────────────────────
    "fixed term plan": ("Fixed Maturity Plan", DEBT),

    # ── Commodity ────────────────────────────────────────────────────────────
    "gold etf": ("Gold", COMMODITY),
    "silver etf": ("Silver", COMMODITY),

    # ── ETFs & index ─────────────────────────────────────────────────────────
    "equity etf": ("Index - Other", INDEX),
    "debt etf": ("Target Maturity", DEBT),
    "hybrid etf": ("Index - Other", INDEX),
    "other  etfs": ("Index - Other", INDEX),
    "other etfs": ("Index - Other", INDEX),
    "other etf": ("Index - Other", INDEX),
    "index funds": ("Index - Other", INDEX),
    "equity funds": ("Index - Other", INDEX),
    "debt funds": ("Target Maturity", DEBT),
    "hybrid fund": ("Index - Other", INDEX),

    # ── International ────────────────────────────────────────────────────────
    "etfs investing overseas": ("International / FoF", INTERNATIONAL),
    "fof overseas": ("International / FoF", INTERNATIONAL),
    "fund of funds investing overseas": ("International / FoF", INTERNATIONAL),

    # ── Domestic fund of funds ───────────────────────────────────────────────
    "fof domestic": ("Fund of Funds", HYBRID),
    "fund of funds scheme (domestic)": ("Fund of Funds", HYBRID),

    # ── Solution oriented ────────────────────────────────────────────────────
    "retirement fund": ("Retirement", SOLUTION),
    "children's fund": ("Children's", SOLUTION),
    "childrens fund": ("Children's", SOLUTION),
    "life cycle fund with maturity of 10 years": ("Retirement", SOLUTION),
    "life cycle fund with maturity of 15 years": ("Retirement", SOLUTION),
}

#: AMFI buckets that are too coarse and get refined by the name-based rules.
_REFINE = {"sectoral/ thematic", "sectoral fund", "thematic fund", "sectoral/thematic"}
_INDEX_REFINE = {"index funds", "equity funds", "equity etf", "other etfs", "other  etfs",
                 "other etf", "hybrid etf", "hybrid fund"}
#: "FoF Domestic" holds two unlike things: multi-asset feeder funds, and
#: single-commodity feeders.  A silver feeder tracks silver — ranking it
#: against a domestic balanced FoF compares a 52%-volatility commodity fund
#: with a 6%-volatility allocation product.
_FOF_REFINE = {"fof domestic", "fund of funds scheme (domestic)"}

_SECTOR_FALLBACK = ("Thematic", EQUITY)

_HEADER = re.compile(r"^(?P<structure>Open Ended|Close Ended|Interval Fund)\s*(Schemes?)?\s*\((?P<body>.*)\)\s*$", re.I)


@lru_cache(maxsize=512)
def parse_header(header: str) -> tuple[str, str]:
    """
    Split ``Open Ended Schemes(Equity Scheme - Large Cap Fund)`` into
    ``("Open Ended", "large cap fund")``.
    """
    match = _HEADER.match(header.strip())
    if not match:
        return "Unknown", header.strip().lower()
    body = match.group("body").strip()
    # Drop the family prefix ("Equity Scheme - ", "Income/Debt Oriented Schemes - ").
    if " - " in body:
        body = body.rsplit(" - ", 1)[1]
    return match.group("structure").title(), body.strip().lower()


def classify(header: str, scheme_name: str) -> tuple[str, str, str]:
    """
    Resolve ``(category, asset_class, structure)`` for one scheme.

    AMFI's own classification wins; the name-based rules are used only to
    refine buckets AMFI leaves deliberately broad, and as a fallback for
    headers we have never seen.
    """
    structure, leaf = parse_header(header)

    if leaf in _REFINE:
        category, asset_class = infer_category(scheme_name)
        if asset_class != EQUITY or not category.startswith(("Sectoral", "Thematic")):
            category, asset_class = _SECTOR_FALLBACK
        return category, asset_class, structure

    if leaf in _INDEX_REFINE:
        category, asset_class = infer_category(scheme_name)
        if asset_class == INDEX:
            return category, INDEX, structure
        if asset_class in (COMMODITY, INTERNATIONAL, DEBT):
            # Gold/Silver/overseas/target-maturity trackers belong with their
            # underlying asset, not with equity index funds.
            return category, asset_class, structure
        return "Index - Other", INDEX, structure

    if leaf in _FOF_REFINE:
        category, asset_class = infer_category(scheme_name)
        if asset_class in (COMMODITY, INTERNATIONAL):
            return category, asset_class, structure
        if asset_class == INDEX:
            return category, INDEX, structure
        return "Fund of Funds", HYBRID, structure

    mapped = _AMFI_MAP.get(leaf)
    if mapped is not None:
        category, asset_class = mapped
        if structure != "Open Ended" and asset_class == DEBT:
            return "Fixed Maturity Plan", DEBT, structure
        return category, asset_class, structure

    category, asset_class = infer_category(scheme_name)
    return category, asset_class or OTHER_CLASS, structure


# ── Plan / option normalisation ───────────────────────────────────────────────

_NON_STANDARD = re.compile(
    r"unclaimed|discontinued|defunct|bonus|institutional|super\s*institutional|"
    r"retail\s*plan|investor\s*education|redemption|donation|\bi\.e\.f\b",
    re.I,
)
_IS_IDCW = re.compile(r"idcw|dividend|payout|reinvest|income\s*distribution|\bidwc\b|\bdcw\b", re.I)
_IS_GROWTH = re.compile(r"growth|cumulative", re.I)


def normalise_plan(raw: str, scheme_name: str) -> str:
    value = (raw or "").strip().lower()
    if "direct" in value:
        return "Direct"
    if "regular" in value or "retail" in value:
        return "Regular"
    return "Direct" if "direct" in scheme_name.lower() else "Regular"


def normalise_option(raw: str, scheme_name: str) -> str:
    """
    Growth vs IDCW.  IDCW wins on ties: an option string that mentions both
    ("IDCW - Payout & Growth") is a payout share class and its NAV gaps down.
    """
    value = (raw or "").strip()
    if not value:
        value = scheme_name
    if _IS_IDCW.search(value):
        return "IDCW"
    if _IS_GROWTH.search(value):
        return "Growth"
    return "Growth"


def is_standard_share_class(raw_option: str, scheme_name: str) -> bool:
    """
    False for wound-up, unclaimed-money and legacy institutional share classes.
    They are still published, but nobody can buy them.
    """
    return not _NON_STANDARD.search(f"{raw_option or ''} {scheme_name}")


def clean_amc(fund_house_line: str) -> str:
    """``Aditya Birla Sun Life Mutual Fund`` → ``Aditya Birla Sun Life``."""
    name = re.sub(r"\s*mutual\s*fund\s*$", "", fund_house_line.strip(), flags=re.I)
    return re.sub(r"\s+", " ", name).strip() or fund_house_line.strip()
