"""Dashboard view model (G4 ANNEX_2 D-2, D-3; ANNEX_3). Standard library only, so the same file runs in the public code-only repository
AutoTrader-dashboard. Every value is point-in-time and computed when the page is opened from the committed state and the input record of
its last session; nothing is written anywhere and there is no history, chart, table of past values or file export.

Screen fields are an allow-list. The forbidden-key table is a hash-pinned copy of G4 prohibited_report_keys; exceptions are per field
only (ANNEX_3 K-1): CURRENT_TOTAL_EQUITY_POINT_IN_TIME and CURRENT_EXACT_WEIGHT_POINT_IN_TIME. Any other field whose name contains a
forbidden token or a weight or valuation word fails (K-2, REVIEWER rule)."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

# copy of G4 prohibited_report_keys (frozen contract 89f9f48); tests/track_c/test_ops_dashboard.py checks it against track_c/ops/reporting.py
PROHIBITED_REPORT_ITEMS = (
    ("change against the previous day or the start", ("change_since", "vs_prev", "since_start", "daily_change", "증감")),
    ("PnL", ("pnl", "profit_and_loss", "손익")),
    ("return", ("return", "rate_of_return", "yield", "pct", "percent", "수익률")),
    ("cumulative return", ("cumulative", "누적")),
    ("equity curve", ("equity_curve", "equity_series", "nav", "평가금액_곡선")),
    ("drawdown", ("drawdown", "mdd")),
    ("historical equity table or chart", ("history", "series", "chart", "그래프")),
    ("total equity in a committed report (allowed in the run notification only)", ("total_equity", "market_value", "평가금액")),
    ("unrealized gain in a committed report", ("unrealized", "미실현")),
    ("per-symbol daily valuation", ("position_value", "daily_value", "평가액")),
    ("full daily close snapshot", ("close_snapshot", "closing_prices", "종가")),
    ("daily valuation FX rate", ("valuation_fx", "평가_환율")),
    ("exact current weight", ("position_weight", "sleeve_weight", "current_weight", "현재_비중")),
    ("risk and benchmark statistics (C1 contract V2 harness list)", ("cagr", "sharpe", "sortino", "volatility", "alpha", "beta",
                                                                    "excess_return", "tracking_error", "information_ratio",
                                                                    "benchmark_comparison")),
)
TABLE_SHA256 = "2d5595ad5f8886f27b8a478616b5671494d83421ded6886f7172192f1401b24d"
TOKENS = tuple(t for _, tokens in PROHIBITED_REPORT_ITEMS for t in tokens)
ALLOWED_POINT_IN_TIME = ("CURRENT_TOTAL_EQUITY_POINT_IN_TIME", "CURRENT_EXACT_WEIGHT_POINT_IN_TIME")  # ANNEX_3 K-1
VALUATION_WORDS = ("weight", "equity", "value", "valuation", "worth", "비중", "평가")  # REVIEWER rule (R-3 C1)
SCREEN_FIELDS = ("LAST_RUN_SESSION", "LAST_RUN_TIME_UTC", "RUN_STATUS", "ALERTS", "HOLDING_QUANTITIES", "CASH_USD", "TARGETS",
                 "POINT_IN_TIME_STATUS", *ALLOWED_POINT_IN_TIME)
# C0_AMENDMENT_2 sleeves (tests check this against track_c.sleeves); every other symbol is in the stock sleeve
SLEEVE_OF = {"VOO": "BROAD_US_LARGE_ETF", "IVV": "BROAD_US_LARGE_ETF", "QQQM": "NASDAQ100_ETF", "QQQ": "NASDAQ100_ETF",
             "VTV": "US_LARGE_VALUE_ETF"}
STOCK_SLEEVE, CASH_SLEEVE = "USER_DISCRETIONARY_STOCK_SLEEVE", "USD_CASH"
LABELS_KO = {"LAST_RUN_SESSION": "마지막 처리 장", "LAST_RUN_TIME_UTC": "마지막 실행 시각(UTC)", "RUN_STATUS": "실행 상태", "ALERTS": "경보",
             "HOLDING_QUANTITIES": "보유 수량", "CASH_USD": "현금(USD)", "TARGETS": "목표 비중", "POINT_IN_TIME_STATUS": "지금 시점 계산",
             "CURRENT_EXACT_WEIGHT_POINT_IN_TIME": "지금 시점의 정확한 비중", "CURRENT_TOTAL_EQUITY_POINT_IN_TIME": "지금 시점 총금액(USD)"}


class ScreenError(ValueError):
    pass


def table_sha256() -> str:
    table = [[item, list(tokens)] for item, tokens in PROHIBITED_REPORT_ITEMS]
    return hashlib.sha256(json.dumps(table, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()


def _norm(text: str) -> str:
    return text.strip().lower().replace(" ", "_").replace("-", "_")


def _words(text: str) -> list[str]:
    """English words: split at every character that is not a letter or digit (the underscore included) and at a case boundary
    (TotalReturn -> total, return; NAVValue -> nav, value)."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    return [w for w in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if w]


def _forms(word: str) -> set[str]:
    """The word and its forms without a final S or ES (RETURNS -> return, CLOSES -> close)."""
    forms = {word}
    if len(word) > 2 and word.endswith("s"):
        forms.add(word[:-1])
    if len(word) > 3 and word.endswith("es"):
        forms.add(word[:-2])
    return forms


def _contains_token(text: str, token: str) -> bool:
    """An English token (one or more words joined by _) matches a run of whole words, a word also in its singular form; a Korean token
    matches as a substring."""
    needle = _norm(token)
    if not needle.isascii():
        return needle in _norm(text)
    parts, words = needle.split("_"), _words(text)
    return any(all(p in _forms(w) for p, w in zip(parts, words[i:i + len(parts)])) for i in range(len(words) - len(parts) + 1))


def build_view(state: dict, record: dict | None, last_run_time_utc: str | None = None) -> dict:
    """The screen fields. Point-in-time values need the input record of the state's last session with a close for every holding."""
    ledger = state.get("ledger", {})
    quantities = {k: Decimal(v) for k, v in ledger.get("quantities", {}).items() if Decimal(v)}
    cash = ledger.get("cash_ledger", {})
    usd, reserved = Decimal(cash.get("USD_AVAILABLE", "0")), Decimal(cash.get("SLEEVE_RESERVED_USD", "0"))
    halt = state.get("halt")
    view = {"LAST_RUN_SESSION": state.get("last_processed_session"), "LAST_RUN_TIME_UTC": last_run_time_utc,
            "RUN_STATUS": f"HALTED:{halt['reason']}" if halt else "OK", "ALERTS": [str(a.get("alert")) for a in state.get("alerts", [])],
            "HOLDING_QUANTITIES": {k: str(v) for k, v in sorted(quantities.items())}, "CASH_USD": str(usd),
            "TARGETS": dict(state.get("target_weights", {}))}
    closes = {}
    if record and record.get("session") == state.get("last_processed_session"):
        closes = {k: Decimal(v["close"]) for k, v in record["market"]["bars"].items()}
    if not quantities or any(k not in closes for k in quantities):
        view["POINT_IN_TIME_STATUS"] = "PRICES_UNAVAILABLE"
        return view
    sleeves = {k: Decimal(0) for k in view["TARGETS"]}
    for symbol, qty in quantities.items():
        sleeve = SLEEVE_OF.get(symbol, STOCK_SLEEVE)
        sleeves[sleeve] = sleeves.get(sleeve, Decimal(0)) + qty * closes[symbol]
    sleeves[STOCK_SLEEVE] = sleeves.get(STOCK_SLEEVE, Decimal(0)) + reserved  # ADDENDUM_2 g: the reserve is in the stock sleeve
    sleeves[CASH_SLEEVE] = sleeves.get(CASH_SLEEVE, Decimal(0)) + usd - reserved
    total = sum(sleeves.values(), Decimal(0))
    view["POINT_IN_TIME_STATUS"] = "COMPUTED_ON_OPEN"
    view["CURRENT_EXACT_WEIGHT_POINT_IN_TIME"] = {k: str(v / total) for k, v in sorted(sleeves.items())}
    view["CURRENT_TOTAL_EQUITY_POINT_IN_TIME"] = str(total)
    return view


def screen_problems(view: dict) -> list[str]:
    """ANNEX_3 K-1..K-3 and the REVIEWER rule; X-4: no list of past values (ALERTS is a list of alert names)."""
    problems = []
    for name, value in view.items():
        if name not in SCREEN_FIELDS:
            problems.append(f"FIELD_NOT_ALLOWED:{name}")
        if name not in ALLOWED_POINT_IN_TIME and (any(_contains_token(name, t) for t in TOKENS)
                                                  or any(w in _norm(name) for w in VALUATION_WORDS)):
            problems.append(f"FIELD_NAME_FORBIDDEN:{name}")
        if isinstance(value, list) and (name != "ALERTS" or any(not isinstance(v, str) for v in value)):
            problems.append(f"LIST_VALUE_NOT_ALLOWED:{name}")
        for key in value if isinstance(value, dict) else ():
            if any(_contains_token(str(key), t) for t in TOKENS):
                problems.append(f"NESTED_KEY_FORBIDDEN:{name}.{key}")
        text = json.dumps(value, ensure_ascii=False)  # not lower-cased first: _words needs the case boundaries
        problems += [f"TOKEN_IN_VALUE:{name}:{t}" for t in TOKENS if _contains_token(text, t)]
    problems += [f"TOKEN_IN_LABEL:{k}:{t}" for k, label in LABELS_KO.items() for t in TOKENS if _contains_token(label, t)]
    if table_sha256() != TABLE_SHA256:
        problems.append("FORBIDDEN_TABLE_HASH_MISMATCH")
    return problems


def check_screen(view: dict) -> dict:
    problems = screen_problems(view)
    if problems:
        raise ScreenError(f"SCREEN_CHECK_FAILED:{len(problems)}")  # the problems name fields, never values (X-1)
    return view


def render_rows(view: dict) -> list[tuple[str, str]]:
    """(Korean label, text) rows in a fixed order; weights with 6 decimals, USD amounts with 2."""
    rows = []
    for name in SCREEN_FIELDS:
        if name not in view:
            continue
        value = view[name]
        if name == "CURRENT_EXACT_WEIGHT_POINT_IN_TIME":
            targets = view.get("TARGETS", {})
            text = "; ".join(f"{k} {Decimal(v):.6f} (목표 {Decimal(targets.get(k, '0')):.2f})" for k, v in value.items())
        elif name in ("CURRENT_TOTAL_EQUITY_POINT_IN_TIME", "CASH_USD"):
            text = f"{Decimal(value):,.2f}"
        elif isinstance(value, dict):
            text = "; ".join(f"{k} {v}" for k, v in value.items()) or "-"
        elif isinstance(value, list):
            text = ", ".join(value) or "없음"
        else:
            text = "-" if value is None else str(value)
        rows.append((LABELS_KO[name], text))
    return rows
