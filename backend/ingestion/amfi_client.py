"""
AMFI ingestion
==============
Two public, ToS-safe sources:

1. ``NAVAll.txt`` — AMFI's own daily file.  Grouped and semicolon-delimited,
   it carries the scheme's registered SEBI category, its fund house, and its
   plan/option share class alongside today's NAV.
2. ``api.mfapi.in`` — community mirror of per-scheme NAV history, used to
   backfill the years AMFI's daily file does not contain.

Format note
-----------
AMFI's file now has **eight** columns::

    Scheme Code;ISIN Growth;ISIN Div Reinvest;Scheme Name;Plan;Option;NAV;Date

and is grouped by ``Open Ended Schemes(<SEBI category>)`` headers with a fund
house line under each.  The previous parser assumed the older six-column
layout and read the *Plan* column where the NAV should be, so ``float(...)``
raised on every row and the daily pull silently imported nothing — which is
why the database had stalled three weeks behind.  Both the header grouping and
the plan/option columns are now read, and they are strictly better data than
anything inferrable from the scheme name.

Writes go through ``executemany`` with ``ON CONFLICT DO NOTHING``; the old
row-at-a-time loop issued ~14,000 round trips per daily pull.
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Sequence

import httpx
from loguru import logger
from sqlalchemy import text
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.analytics.amfi_categories import (
    classify,
    clean_amc,
    is_standard_share_class,
    normalise_option,
    normalise_plan,
)
from backend.config import settings
from backend.db.session import engine

USER_AGENT = "MFScope/1.0 (personal research; contact via repository)"

#: mfapi.in is a volunteer-run mirror.  Stay well inside polite limits.
BACKFILL_CONCURRENCY = 12
BACKFILL_TIMEOUT = 25.0

#: SQLite takes one writer at a time.  Fanning 12 concurrent fetches straight
#: into the database is what produced "database is locked"; the fetches stay
#: parallel and only the commits queue behind this.
_WRITE_LOCK = asyncio.Lock()


def _parse_date(raw: str) -> date | None:
    for fmt in ("%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=12))
async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    response = await client.get(url, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response


class AMFIClient:
    """Downloads and persists AMFI scheme + NAV data."""

    # ── NAVAll.txt ───────────────────────────────────────────────────────────

    def parse_nav_all(self, content: str) -> list[dict[str, Any]]:
        """
        Parse the grouped NAVAll.txt into flat records.

        State machine: a line with no semicolons is either a category header
        (it starts with the scheme structure) or a fund house name.  Everything
        else is a data row belonging to the most recent header/house pair.
        """
        records: list[dict[str, Any]] = []
        header = ""
        fund_house = ""

        for line in content.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if ";" not in stripped:
                lowered = stripped.lower()
                if lowered.startswith(("open ended", "close ended", "closed ended", "interval")):
                    header = stripped
                else:
                    fund_house = stripped
                continue

            parts = next(csv.reader(io.StringIO(stripped), delimiter=";"), [])
            if len(parts) < 8:
                continue

            code = parts[0].strip()
            if not code.isdigit():
                continue

            name = parts[3].strip()
            nav_raw = parts[6].strip()
            nav_date = _parse_date(parts[7])
            if nav_date is None:
                continue
            try:
                nav = float(nav_raw)
            except ValueError:
                continue          # "N.A." appears for schemes that did not price
            if nav <= 0:
                continue

            category, asset_class, structure = classify(header, name)
            raw_option = parts[5].strip()

            records.append(
                {
                    "scheme_code": code,
                    "isin_growth": parts[1].strip() or None,
                    "isin_div": parts[2].strip() or None,
                    "scheme_name": name,
                    "amc_name": clean_amc(fund_house) if fund_house else "Unknown",
                    "category": category,
                    "asset_class": asset_class,
                    "structure": structure,
                    "plan_type": normalise_plan(parts[4], name),
                    "option_type": normalise_option(raw_option, name),
                    "standard_class": is_standard_share_class(raw_option, name),
                    "nav": nav,
                    "nav_date": nav_date,
                }
            )

        return records

    async def fetch_latest_nav(self) -> dict[str, int]:
        """Download NAVAll.txt, upsert schemes and insert the day's NAV rows."""
        logger.info("Fetching NAVAll.txt from AMFI …")
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            response = await _get(client, settings.amfi_nav_url)

        records = self.parse_nav_all(response.text)
        if not records:
            logger.error("NAVAll.txt parsed to zero rows — the file layout may have changed.")
            return {"schemes": 0, "nav_rows": 0}

        nav_dates = {r["nav_date"] for r in records}
        logger.info(
            f"Parsed {len(records)} NAV rows across {len({r['amc_name'] for r in records})} "
            f"fund houses, dated {min(nav_dates)} → {max(nav_dates)}."
        )

        schemes_written = await self._upsert_schemes(records)
        nav_written = await self._insert_navs(records)
        return {"schemes": schemes_written, "nav_rows": nav_written}

    async def _upsert_schemes(self, records: Sequence[dict[str, Any]]) -> int:
        """
        Insert new schemes and refresh the classification of existing ones.

        AMFI's own category is authoritative, so an existing row is updated
        rather than left with whatever the name-based guess produced.
        """
        payload = [
            {
                "scheme_code": r["scheme_code"],
                "isin_growth": r["isin_growth"],
                "isin_div_reinvest": r["isin_div"],
                "scheme_name": r["scheme_name"],
                "amc_name": r["amc_name"],
                "category": r["category"],
                "asset_class": r["asset_class"],
                "plan_type": r["plan_type"],
                "option_type": r["option_type"],
            }
            for r in records
            if r["standard_class"]
        ]
        if not payload:
            return 0

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO scheme
                        (scheme_code, isin_growth, isin_div_reinvest, scheme_name,
                         amc_name, category, asset_class, plan_type, option_type,
                         amfi_classified, is_active, is_investable, nav_count)
                    VALUES
                        (:scheme_code, :isin_growth, :isin_div_reinvest, :scheme_name,
                         :amc_name, :category, :asset_class, :plan_type, :option_type,
                         1, 1, 0, 0)
                    ON CONFLICT(scheme_code) DO UPDATE SET
                        scheme_name = excluded.scheme_name,
                        isin_growth = COALESCE(excluded.isin_growth, scheme.isin_growth),
                        amc_name    = excluded.amc_name,
                        category    = excluded.category,
                        asset_class = excluded.asset_class,
                        plan_type   = excluded.plan_type,
                        option_type = excluded.option_type,
                        amfi_classified = 1
                    """
                ),
                payload,
            )
        logger.info(f"Scheme master synced: {len(payload)} rows.")
        return len(payload)

    async def _insert_navs(self, records: Sequence[dict[str, Any]]) -> int:
        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT scheme_code, id FROM scheme"))
            code_to_id = {code: scheme_id for code, scheme_id in rows.all()}

        payload = [
            {
                "sid": code_to_id[r["scheme_code"]],
                "nav_date": r["nav_date"].isoformat(),
                "nav": r["nav"],
            }
            for r in records
            if r["scheme_code"] in code_to_id
        ]
        if not payload:
            return 0

        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO nav_record (scheme_id, nav_date, nav) "
                    "VALUES (:sid, :nav_date, :nav) "
                    "ON CONFLICT(scheme_id, nav_date) DO NOTHING"
                ),
                payload,
            )
        logger.info(f"NAV rows offered: {len(payload)} (duplicates ignored).")
        return len(payload)

    # ── Historical backfill ──────────────────────────────────────────────────

    async def backfill_history(
        self,
        scheme_codes: Iterable[str],
        years: int = 11,
        concurrency: int = BACKFILL_CONCURRENCY,
        progress_every: int = 250,
    ) -> dict[str, int]:
        """
        Pull per-scheme NAV history from mfapi.in for the given scheme codes.

        This is the step that turns a one-print scheme into something the
        metric layer can actually measure.  Requests are bounded by a
        semaphore and failures are counted rather than raised — one dead
        scheme code must not abort a 3,000-scheme backfill.
        """
        codes = list(dict.fromkeys(str(c) for c in scheme_codes))
        if not codes:
            return {"schemes": 0, "rows": 0, "failed": 0}

        async with engine.connect() as conn:
            rows = await conn.execute(text("SELECT scheme_code, id FROM scheme"))
            code_to_id = {code: scheme_id for code, scheme_id in rows.all()}

        cutoff = date.today() - timedelta(days=365 * years)
        semaphore = asyncio.Semaphore(concurrency)
        stats = {"schemes": 0, "rows": 0, "failed": 0}
        buffer: list[dict[str, Any]] = []
        lock = asyncio.Lock()

        limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=concurrency)
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=BACKFILL_TIMEOUT, limits=limits
        ) as client:

            async def fetch_one(code: str) -> None:
                scheme_id = code_to_id.get(code)
                if scheme_id is None:
                    return
                async with semaphore:
                    try:
                        response = await _get(client, f"{settings.amfi_scheme_url}/{code}")
                        history = response.json().get("data") or []
                    except Exception as exc:
                        stats["failed"] += 1
                        logger.debug(f"backfill {code}: {type(exc).__name__}: {exc}")
                        return

                rows_out: list[dict[str, Any]] = []
                for entry in history:
                    nav_date = _parse_date(entry.get("date", ""))
                    if nav_date is None or nav_date < cutoff:
                        continue
                    try:
                        nav = float(entry["nav"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if nav <= 0:
                        continue
                    rows_out.append(
                        {"sid": scheme_id, "nav_date": nav_date.isoformat(), "nav": nav}
                    )

                async with lock:
                    buffer.extend(rows_out)
                    stats["schemes"] += 1
                    stats["rows"] += len(rows_out)
                    if len(buffer) >= 40_000:
                        pending, buffer[:] = list(buffer), []
                    else:
                        pending = []
                if pending:
                    await self._bulk_nav_insert(pending)
                if stats["schemes"] % progress_every == 0:
                    logger.info(
                        f"  backfill … {stats['schemes']}/{len(codes)} schemes, "
                        f"{stats['rows']:,} NAV rows, {stats['failed']} failed"
                    )

            await asyncio.gather(*(fetch_one(code) for code in codes))

        if buffer:
            await self._bulk_nav_insert(buffer)

        logger.info(
            f"Backfill complete: {stats['schemes']} schemes, {stats['rows']:,} NAV rows, "
            f"{stats['failed']} failures."
        )
        return stats

    async def _bulk_nav_insert(self, rows: Sequence[dict[str, Any]]) -> None:
        if not rows:
            return
        async with _WRITE_LOCK, engine.begin() as conn:
            for start in range(0, len(rows), 10_000):
                await conn.execute(
                    text(
                        "INSERT INTO nav_record (scheme_id, nav_date, nav) "
                        "VALUES (:sid, :nav_date, :nav) "
                        "ON CONFLICT(scheme_id, nav_date) DO NOTHING"
                    ),
                    list(rows[start : start + 10_000]),
                )

    # ── Backwards-compatible shim ────────────────────────────────────────────

    async def fetch_scheme_master(self) -> int:
        """
        Kept for callers that expect the old two-step seed.  The scheme master
        now arrives with the NAV file, so this simply delegates.
        """
        result = await self.fetch_latest_nav()
        return result["schemes"]
