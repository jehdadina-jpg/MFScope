"""
AMFI Ingestion Client
=====================
Pulls NAV data from two public, ToS-safe sources:

1. NAVAll.txt  — AMFI's daily NAV file (semicolon-delimited)
2. mfapi.in    — community REST API for per-scheme historical NAV

Uses SQLite INSERT OR IGNORE throughout — completely safe to re-run.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import settings
from backend.db.models import FundCategory
from backend.db.session import AsyncSessionLocal


# ── Category inference ────────────────────────────────────────────────────────

_CATEGORY_KEYWORDS: list[tuple[re.Pattern, FundCategory]] = [
    (re.compile(r"defense|defence", re.I),                     FundCategory.DEFENSE),
    (re.compile(r"\bpsu\b", re.I),                             FundCategory.PSU),
    (re.compile(r"banking|financial service", re.I),           FundCategory.BANKING_FINANCIAL),
    (re.compile(r"pharma|health", re.I),                       FundCategory.PHARMA_HEALTHCARE),
    (re.compile(r"\bit\b|technology|tech fund", re.I),         FundCategory.IT_TECHNOLOGY),
    (re.compile(r"infra", re.I),                               FundCategory.INFRASTRUCTURE),
    (re.compile(r"consumption|fmcg|consumer", re.I),           FundCategory.CONSUMPTION),
    (re.compile(r"energy|power|oil", re.I),                    FundCategory.ENERGY),
    (re.compile(r"nifty.?next.?50", re.I),                     FundCategory.INDEX_NIFTY_NEXT50),
    (re.compile(r"nifty.?50\b|nifty50", re.I),                 FundCategory.INDEX_NIFTY50),
    (re.compile(r"sensex", re.I),                              FundCategory.INDEX_SENSEX),
    (re.compile(r"index|etf", re.I),                           FundCategory.INDEX_OTHER),
    (re.compile(r"large.?&.?mid|large.?mid", re.I),            FundCategory.LARGE_MID_CAP),
    (re.compile(r"large.?cap", re.I),                          FundCategory.LARGE_CAP),
    (re.compile(r"mid.?cap", re.I),                            FundCategory.MID_CAP),
    (re.compile(r"small.?cap", re.I),                          FundCategory.SMALL_CAP),
    (re.compile(r"flexi.?cap", re.I),                          FundCategory.FLEXI_CAP),
    (re.compile(r"multi.?cap", re.I),                          FundCategory.MULTI_CAP),
    (re.compile(r"elss|tax.?sav", re.I),                       FundCategory.ELSS),
    (re.compile(r"overnight", re.I),                           FundCategory.OVERNIGHT),
    (re.compile(r"liquid", re.I),                              FundCategory.LIQUID),
    (re.compile(r"short.?dur", re.I),                          FundCategory.SHORT_DURATION),
    (re.compile(r"corporate.?bond", re.I),                     FundCategory.CORPORATE_BOND),
    (re.compile(r"gilt", re.I),                                FundCategory.GILT),
    (re.compile(r"aggressive.?hybrid", re.I),                  FundCategory.AGGRESSIVE_HYBRID),
    (re.compile(r"balanced.?advantage|dynamic.?asset", re.I),  FundCategory.BALANCED_ADVANTAGE),
    (re.compile(r"multi.?asset", re.I),                        FundCategory.MULTI_ASSET),
    (re.compile(r"international|global|overseas|fof", re.I),   FundCategory.INTERNATIONAL),
    (re.compile(r"sectoral|thematic", re.I),                   FundCategory.SECTORAL_OTHER),
    (re.compile(r"hybrid", re.I),                              FundCategory.MULTI_ASSET),
    (re.compile(r"debt|bond|income|credit", re.I),             FundCategory.DEBT_OTHER),
]


def _infer_category(name: str) -> str:
    for pattern, cat in _CATEGORY_KEYWORDS:
        if pattern.search(name):
            return cat.value
    return FundCategory.OTHER.value


def _infer_plan(name: str) -> str:
    n = name.upper()
    if "DIRECT" in n:
        return "Direct"
    if "REGULAR" in n:
        return "Regular"
    return "Unknown"


def _infer_option(name: str) -> str:
    n = name.upper()
    if "IDCW" in n or "DIVIDEND" in n:
        return "Dividend"
    return "Growth"


def _parse_nav_date(raw: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ── HTTP ─────────────────────────────────────────────────────────────────────

@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
async def _get(url: str, timeout: float = 30.0) -> httpx.Response:
    async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
        r = await client.get(url, headers={"User-Agent": "MFScope/0.1 (educational)"})
        r.raise_for_status()
        return r


# ── Main client ───────────────────────────────────────────────────────────────

class AMFIClient:

    # ── Scheme master ─────────────────────────────────────────────────────────

    async def fetch_scheme_master(self) -> int:
        """
        Pull full scheme list from mfapi.in and INSERT OR IGNORE into scheme table.
        Returns count of newly inserted rows.
        """
        logger.info("Fetching scheme master from mfapi.in …")
        resp = await _get(settings.amfi_scheme_url)
        schemes_raw: list[dict] = resp.json()
        logger.info(f"  {len(schemes_raw)} schemes in API response")

        rows = []
        for item in schemes_raw:
            code = str(item.get("schemeCode", "")).strip()
            name = (item.get("schemeName") or "").strip()
            if not code or not name:
                continue
            rows.append({
                "scheme_code": code,
                "scheme_name": name,
                "amc_name":    name.split(" ")[0],
                "category":    _infer_category(name),
                "plan_type":   _infer_plan(name),
                "option_type": _infer_option(name),
            })

        if not rows:
            return 0

        inserted = 0
        from backend.db.session import engine
        async with engine.begin() as conn:
            for r in rows:
                res = await conn.execute(
                    text("""
                        INSERT OR IGNORE INTO scheme
                            (scheme_code, scheme_name, amc_name, category,
                             plan_type, option_type, is_active)
                        VALUES
                            (:scheme_code, :scheme_name, :amc_name, :category,
                             :plan_type, :option_type, 1)
                    """),
                    r,
                )
                inserted += 1

        logger.info(f"Scheme master done — {inserted} new rows inserted.")
        return inserted

    # ── Daily NAV ─────────────────────────────────────────────────────────────

    async def fetch_latest_nav(self) -> int:
        """
        Download NAVAll.txt and INSERT OR IGNORE today's NAV rows.
        Also creates any missing scheme rows encountered.
        Returns the number of NAV rows inserted.
        """
        logger.info("Fetching NAVAll.txt from AMFI …")
        resp = await _get(settings.amfi_nav_url)
        records = self._parse_nav_all(resp.text)
        logger.info(f"  Parsed {len(records)} NAV rows")

        if not records:
            return 0

        # ── Step 1: upsert all schemes from NAVAll ────────────────────────
        from backend.db.session import engine
        inserted = 0

        async with engine.begin() as conn:
            for r in records:
                await conn.execute(
                    text("""
                        INSERT OR IGNORE INTO scheme
                            (scheme_code, isin_growth, isin_div_reinvest,
                             scheme_name, amc_name, category,
                             plan_type, option_type, is_active)
                        VALUES
                            (:code, :isin_g, :isin_d,
                             :name, :amc, :cat, :plan, :opt, 1)
                    """),
                    {
                        "code":   r["scheme_code"],
                        "isin_g": r["isin_growth"],
                        "isin_d": r["isin_div"],
                        "name":   r["scheme_name"],
                        "amc":    r["scheme_name"].split(" ")[0],
                        "cat":    _infer_category(r["scheme_name"]),
                        "plan":   _infer_plan(r["scheme_name"]),
                        "opt":    _infer_option(r["scheme_name"]),
                    },
                )
        # engine.begin() auto-commits on exit

        # ── Step 2: fresh connection — build code→id map ──────────────────
        async with engine.connect() as conn:
            res2 = await conn.execute(text("SELECT scheme_code, id FROM scheme"))
            code_to_id: dict[str, int] = {row[0]: row[1] for row in res2.all()}

        # ── Step 3: insert NAV rows ───────────────────────────────────────
        async with engine.begin() as conn:
            for r in records:
                sid = code_to_id.get(r["scheme_code"])
                if sid is None:
                    continue
                await conn.execute(
                    text("""
                        INSERT OR IGNORE INTO nav_record (scheme_id, nav_date, nav)
                        VALUES (:sid, :nav_date, :nav)
                    """),
                    {"sid": sid, "nav_date": r["nav_date"].isoformat(), "nav": r["nav"]},
                )
                inserted += 1

        logger.info(f"NAV upsert done — {inserted} rows inserted.")
        return inserted

    def _parse_nav_all(self, content: str) -> list[dict[str, Any]]:
        records: list[dict] = []
        reader = csv.reader(io.StringIO(content), delimiter=";")
        for row in reader:
            if len(row) < 6:
                continue
            code     = row[0].strip()
            isin_g   = row[1].strip() or None
            isin_d   = row[2].strip() or None
            name     = row[3].strip()
            nav_str  = row[4].strip()
            date_str = row[5].strip()

            if not code.isdigit():
                continue
            try:
                nav_val = float(nav_str)
            except ValueError:
                continue
            nav_date = _parse_nav_date(date_str)
            if nav_date is None:
                continue

            records.append({
                "scheme_code": code,
                "isin_growth": isin_g,
                "isin_div":    isin_d,
                "scheme_name": name,
                "nav":         nav_val,
                "nav_date":    nav_date,
            })
        return records

    # ── Historical backfill (single scheme) ───────────────────────────────────

    async def backfill_history(self, scheme_code: str, days: int = 365) -> int:
        url = f"{settings.amfi_scheme_url}/{scheme_code}"
        try:
            resp = await _get(url, timeout=20.0)
        except Exception as exc:
            logger.warning(f"backfill {scheme_code}: {exc}")
            return 0

        nav_data: list[dict] = resp.json().get("data", [])
        cutoff = date.today() - timedelta(days=days)

        async with AsyncSessionLocal() as session:
            row = await session.execute(
                text("SELECT id FROM scheme WHERE scheme_code = :code"),
                {"code": scheme_code},
            )
            scheme_row = row.first()
            if not scheme_row:
                return 0
            sid = scheme_row[0]

            inserted = 0
            for entry in nav_data:
                nav_date = _parse_nav_date(entry.get("date", ""))
                if nav_date is None or nav_date < cutoff:
                    continue
                try:
                    nav_val = float(entry["nav"])
                except (ValueError, KeyError):
                    continue

                res = await session.execute(
                    text("""
                        INSERT OR IGNORE INTO nav_record (scheme_id, nav_date, nav)
                        VALUES (:sid, :nav_date, :nav)
                    """),
                    {"sid": sid, "nav_date": nav_date.isoformat(), "nav": nav_val},
                )
                inserted += res.rowcount

            await session.commit()

        return inserted
