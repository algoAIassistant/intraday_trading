"""
research_build_shared_master_universe_us_common_stocks.py
Side:  research — universe builder layer

Purpose:
  Build the shared master U.S. common-stock universe from Massive.com
  reference data. Produces three output files consumed by all research scripts.

Filter logic (first pass):
  A ticker is accepted into the clean list only if ALL of the following hold:
    1. type == "CS"             (common stock — not ETF, ADR, warrant, preferred)
    2. market == "stocks"       (exchange-listed equities)
    3. currency_name == "usd"   (USD-denominated)
    4. primary_exchange in ACCEPTED_EXCHANGES
         XNYS  NYSE
         XNAS  NASDAQ
         XASE  NYSE American (AMEX)
    5. Ticker passes format check:
         - 1 to 5 characters
         - letters only OR letters.letters (e.g. BRK.A)
         - does NOT end in suffixes associated with non-common instruments:
           W, WS, WI, R, RT, U, Z (warrants, rights, units, notes)
         Note: Massive type=CS should already exclude most of these,
         but the format check is a defensive second layer.
    6. name is non-empty
    7. primary_exchange is non-empty

Retry/waitlist pass:
  A ticker is placed on the retry_waitlist if the first pass rejects it for
  any reason OTHER than an explicit exclusion (exchange outside accepted set
  or type != "CS"). Specifically, waitlist triggers are:
    - name missing or empty
    - primary_exchange missing or empty
    - cik missing (soft flag — does not block promotion on retry)
  For each waitlisted ticker, the builder re-fetches full details via
  client.get_ticker_details() and re-applies the same filter.
  Tickers that pass on retry are promoted to the clean list.
  Tickers that still fail remain in the waitlist output with failure_reason.

SPY / QQQ:
  SPY and QQQ are NOT included in this common-stock universe.
  They are ETFs (type != "CS") and belong in a dedicated market reference cache.
  The Massive type filter naturally excludes them.

Outputs (written to 0_1_shared_master_universe/):
  shared_symbol_lists/
    shared_master_symbol_list_us_common_stocks__<DATE>.csv
      columns: ticker, name, primary_exchange, cik

  shared_metadata/
    shared_master_metadata_us_common_stocks__<DATE>.csv
      columns: ticker, name, market, locale, primary_exchange, type,
               active, currency_name, cik, composite_figi,
               share_class_figi, last_updated_utc

  shared_validation_reports/
    shared_master_retry_waitlist__<DATE>.csv
      columns: ticker, name, primary_exchange, type, failure_reason, retry_outcome

    shared_master_build_validation_report__<DATE>.txt
      human-readable run summary: counts, filter breakdown, retry results

Auth:
  Requires MASSIVE_API_KEY environment variable.

Dependencies:
  pip install -U massive pandas pyarrow
"""

import os
import re
import sys
import datetime
import pandas as pd
from massive import RESTClient

# -- Paths --------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT  = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", ".."))

SYMBOL_LIST_DIR = os.path.join(REPO_ROOT, "0_1_shared_master_universe", "shared_symbol_lists")
METADATA_DIR    = os.path.join(REPO_ROOT, "0_1_shared_master_universe", "shared_metadata")
VALIDATION_DIR  = os.path.join(REPO_ROOT, "0_1_shared_master_universe", "shared_validation_reports")

for d in [SYMBOL_LIST_DIR, METADATA_DIR, VALIDATION_DIR]:
    os.makedirs(d, exist_ok=True)

TODAY = datetime.date.today().strftime("%Y_%m_%d")

# -- Filter config ------------------------------------------------------------

ACCEPTED_EXCHANGES = {"XNYS", "XNAS", "XASE"}   # NYSE, NASDAQ, NYSE American

# Ticker format: 1-5 uppercase letters, optionally followed by dot + 1-2 letters
_TICKER_FORMAT = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")

# Suffixes that indicate non-common instruments (case-insensitive end match)
_EXCLUDED_SUFFIXES = re.compile(r"(W|WS|WI|R|RT|U|Z)$")

# Auth
_KEY_ENV = "MASSIVE_API_KEY"


def _get_api_key() -> str:
    key = os.environ.get(_KEY_ENV, "").strip()
    if not key:
        raise EnvironmentError(
            f"{_KEY_ENV} is not set.\n  export {_KEY_ENV}=<your_key>"
        )
    return key


# -- Normalization ------------------------------------------------------------

def _ticker_format_ok(ticker: str) -> bool:
    if not _TICKER_FORMAT.match(ticker):
        return False
    # Strip dot-suffix before checking instrument suffix
    base = ticker.split(".")[0]
    if _EXCLUDED_SUFFIXES.search(base):
        return False
    return True


def _to_record(t) -> dict:
    """Flatten a Massive Ticker object to a plain dict."""
    return {
        "ticker":           getattr(t, "ticker",           None),
        "name":             getattr(t, "name",             None),
        "market":           getattr(t, "market",           None),
        "locale":           getattr(t, "locale",           None),
        "primary_exchange": getattr(t, "primary_exchange", None),
        "type":             getattr(t, "type",             None),
        "active":           getattr(t, "active",           None),
        "currency_name":    getattr(t, "currency_name",    None),
        "cik":              getattr(t, "cik",              None),
        "composite_figi":   getattr(t, "composite_figi",  None),
        "share_class_figi": getattr(t, "share_class_figi",None),
        "last_updated_utc": getattr(t, "last_updated_utc",None),
    }


def _classify(rec: dict) -> tuple[bool, str]:
    """
    Returns (accepted: bool, failure_reason: str).
    failure_reason is empty string when accepted.
    """
    t = rec.get("ticker", "") or ""
    reasons = []

    if rec.get("type") != "CS":
        return False, f"type={rec.get('type')} not CS"
    if rec.get("market") != "stocks":
        return False, f"market={rec.get('market')} not stocks"
    if rec.get("currency_name") != "usd":
        return False, f"currency={rec.get('currency_name')} not usd"
    if rec.get("primary_exchange") not in ACCEPTED_EXCHANGES:
        return False, f"exchange={rec.get('primary_exchange')} not in accepted set"
    if not t or not _ticker_format_ok(t):
        return False, f"ticker format rejected: {t!r}"

    # Soft fields — go to waitlist rather than hard reject
    if not rec.get("name"):
        reasons.append("name missing")
    if not rec.get("primary_exchange"):
        reasons.append("primary_exchange missing")

    if reasons:
        return False, "; ".join(reasons)

    return True, ""


# -- Main ---------------------------------------------------------------------

def main():
    api_key = _get_api_key()
    client  = RESTClient(api_key=api_key)

    print("=" * 60)
    print("research_build_shared_master_universe_us_common_stocks")
    print(f"Run date   : {TODAY}")
    print(f"Source     : Massive.com (type=CS, market=stocks, active=True)")
    print(f"Exchanges  : {sorted(ACCEPTED_EXCHANGES)}")
    print("=" * 60)

    # -- First pass: fetch all CS tickers -------------------------------------

    print("\nPass 1: fetching all active CS tickers from Massive ...")
    raw_records  = []
    fetch_errors = 0

    try:
        for t in client.list_tickers(
            market="stocks",
            type="CS",
            active=True,
            limit=1000,
        ):
            raw_records.append(_to_record(t))
    except Exception as exc:
        print(f"  ERROR during list_tickers fetch: {exc}")
        sys.exit(1)

    print(f"  Raw records fetched: {len(raw_records)}")

    # -- Classify first pass --------------------------------------------------

    clean_records    = []
    waitlist_records = []  # soft-fail only: missing name/exchange
    hard_rejected    = 0   # wrong type/exchange/currency/format — never retried

    HARD_REJECT_PREFIXES = ("type=", "market=", "currency=", "exchange=", "ticker format")

    for rec in raw_records:
        accepted, reason = _classify(rec)
        if accepted:
            clean_records.append(rec)
        else:
            is_hard = any(reason.startswith(p) for p in HARD_REJECT_PREFIXES)
            if is_hard:
                hard_rejected += 1
            else:
                waitlist_records.append({**rec, "failure_reason": reason, "retry_outcome": "pending"})

    print(f"  Pass 1 accepted     : {len(clean_records)}")
    print(f"  Hard rejected       : {hard_rejected}  (wrong type/exchange/currency/format)")
    print(f"  Waitlist (soft fail): {len(waitlist_records)}")

    # -- Retry pass -----------------------------------------------------------

    retry_promoted = 0
    retry_still_failed = 0

    if waitlist_records:
        print(f"\nPass 2: retrying {len(waitlist_records)} waitlisted tickers individually ...")
        updated_waitlist = []
        for entry in waitlist_records:
            ticker = entry.get("ticker", "")
            try:
                detail = client.get_ticker_details(ticker)
                rec2   = _to_record(detail)
                accepted2, reason2 = _classify(rec2)
                if accepted2:
                    clean_records.append(rec2)
                    entry["retry_outcome"] = "promoted"
                    retry_promoted += 1
                else:
                    entry["retry_outcome"] = f"still_failed: {reason2}"
                    retry_still_failed += 1
                    updated_waitlist.append(entry)
            except Exception as exc:
                entry["retry_outcome"] = f"fetch_error: {exc}"
                retry_still_failed += 1
                updated_waitlist.append(entry)
        waitlist_records = updated_waitlist
        print(f"  Retry promoted      : {retry_promoted}")
        print(f"  Still failed        : {retry_still_failed}")
    else:
        print("\nPass 2: no waitlisted tickers - retry pass skipped.")

    total_clean = len(clean_records)
    print(f"\nFinal clean universe : {total_clean} tickers")

    # -- Write symbol list ----------------------------------------------------

    sym_df = pd.DataFrame(clean_records)[["ticker", "name", "primary_exchange", "cik"]].sort_values("ticker").reset_index(drop=True)
    sym_file = os.path.join(SYMBOL_LIST_DIR, f"shared_master_symbol_list_us_common_stocks__{TODAY}.csv")
    sym_df.to_csv(sym_file, index=False)
    print(f"\nSymbol list  -> {sym_file}  ({len(sym_df)} rows)")

    # -- Write metadata -------------------------------------------------------

    meta_cols = ["ticker", "name", "market", "locale", "primary_exchange", "type",
                 "active", "currency_name", "cik", "composite_figi", "share_class_figi", "last_updated_utc"]
    meta_df = pd.DataFrame(clean_records)[meta_cols].sort_values("ticker").reset_index(drop=True)
    meta_file = os.path.join(METADATA_DIR, f"shared_master_metadata_us_common_stocks__{TODAY}.csv")
    meta_df.to_csv(meta_file, index=False)
    print(f"Metadata     -> {meta_file}  ({len(meta_df)} rows)")

    # -- Write retry/waitlist -------------------------------------------------

    wl_cols = ["ticker", "name", "primary_exchange", "type", "failure_reason", "retry_outcome"]
    wl_df = pd.DataFrame(waitlist_records)[wl_cols] if waitlist_records else pd.DataFrame(columns=wl_cols)
    wl_file = os.path.join(VALIDATION_DIR, f"shared_master_retry_waitlist__{TODAY}.csv")
    wl_df.to_csv(wl_file, index=False)
    print(f"Retry waitlist-> {wl_file}  ({len(wl_df)} rows)")

    # -- Write validation report ----------------------------------------------

    exchange_counts = sym_df["primary_exchange"].value_counts().to_dict()

    report_lines = [
        "shared_master_build_validation_report",
        f"run_date          : {TODAY}",
        f"source            : Massive.com (type=CS, market=stocks, active=True)",
        f"accepted_exchanges: {sorted(ACCEPTED_EXCHANGES)}",
        "",
        "--- Counts ---",
        f"raw_fetched       : {len(raw_records)}",
        f"hard_rejected     : {hard_rejected}",
        f"waitlisted_pass1  : {len(waitlist_records) + retry_promoted}",
        f"retry_promoted    : {retry_promoted}",
        f"retry_still_failed: {retry_still_failed}",
        f"final_clean       : {total_clean}",
        "",
        "--- Exchange breakdown (clean universe) ---",
    ]
    for exch, cnt in sorted(exchange_counts.items()):
        report_lines.append(f"  {exch:<8}: {cnt}")
    report_lines += [
        "",
        "--- Filter logic applied ---",
        "  type == CS",
        "  market == stocks",
        "  currency_name == usd",
        f"  primary_exchange in {sorted(ACCEPTED_EXCHANGES)}",
        "  ticker: 1-5 uppercase letters (with optional .X or .XX suffix)",
        "  ticker: no warrant/right/unit/note suffix (W WS WI R RT U Z)",
        "  name: non-empty",
        "",
        "--- Retry logic ---",
        "  Soft-fail tickers (missing name or exchange) placed on waitlist.",
        "  One retry pass: individual get_ticker_details() call per waitlisted ticker.",
        "  Anything still failing after retry remains in retry_waitlist output.",
        "",
        f"--- Output files ---",
        f"  symbol_list : {sym_file}",
        f"  metadata    : {meta_file}",
        f"  waitlist    : {wl_file}",
    ]

    report_text = "\n".join(report_lines)
    report_file = os.path.join(VALIDATION_DIR, f"shared_master_build_validation_report__{TODAY}.txt")
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"Validation   -> {report_file}")

    print("\nDone.")


if __name__ == "__main__":
    main()
