"""Dashboard view model (G4 ANNEX_2 D-2, D-3; ANNEX_3). Standard library only, so the same file runs in the public code-only repository
AutoTrader-dashboard. Every value is point-in-time and computed when the page is opened from the committed state and the input record of
its last session; nothing is written anywhere and there is no history, chart, table of past values or file export.

Screen fields are an allow-list. The forbidden-key table is a hash-pinned copy of G4 prohibited_report_keys; exceptions are per field
only (ANNEX_3 K-1): CURRENT_TOTAL_EQUITY_POINT_IN_TIME and CURRENT_EXACT_WEIGHT_POINT_IN_TIME. Any other field whose name contains a
forbidden token or a weight or valuation word fails (K-2, REVIEWER rule).

G4 ANNEX_11 (USER 2026-09-28): the USER-only reference figures (valuation over time, gains, time-weighted return, holdings) are computed
in perf.py on page load; this point-in-time view and its check stay as they are and feed the operation status tab and the weights."""
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


# G4 ANNEX_8 A8-2 (REVIEWER): the fixed alert and error codes the engine registers, each with a neutral Korean label. A registered code
# may be shown as it is; any other string (free text) is screened for the forbidden tokens and, in ALERTS, the valuation words too.
# tests/track_c/test_g4_annex_8.py checks that every alert code of the engine is here and that no label holds a forbidden token.
CODE_LABELS_KO = {
    "BAND_BREACH_AFTER_DEPLOYMENT": "배분 후 밴드 이탈", "BUY_BLOCKED": "매수 보류", "BUY_BLOCKED_POLICY_ALERT": "정책 경보로 매수 보류",
    "CA_BLOCK": "기업행동 차단", "CASH_MISMATCH": "현금 대사 불일치", "CORPORATE_ACTION_PENDING_BROKER_REPORT": "증권사 기업행동 보고 대기",
    "CORPORATE_ACTION_RELEASE_INCOMPLETE": "기업행동 차단 해제 미완료", "COST_ABOVE_PLAN": "계획보다 비용 큼",
    "COST_EXCEEDED_PLAN": "계획 비용 초과", "DATA_MISSING": "자료 없음", "DATA_STALE": "자료 지연", "DEPLOYMENT_APPLIED": "코드 배포 적용",
    "DIVIDEND_WITHHOLDING_DIFFERS_FROM_COMPUTED": "원천징수액이 계산과 다름", "ENGINE_HALT": "엔진 정지",
    "FEE_ABOVE_ESTIMATE": "수수료가 추정보다 큼", "FEE_EXCEEDED_ESTIMATE": "수수료 추정 초과", "FILL_OPEN_PRICE_MISSING": "체결 시가 없음",
    "HELD_TICKER_PRICE_MISSING": "보유 종목 시세 없음(티커 확인 필요)", "TICKER_CHANGE_RELEASE_INCOMPLETE": "티커 변경 차단 해제 미완료",  # G4 ANNEX_9
    "HELD_TICKER_PRICE_RESTORED": "보유 종목 시세 복구", "PROVIDER_PRICE_MISMATCH": "제공처 간 시세 불일치",  # G4 ANNEX_10
    "PROVIDER_PRICE_MISMATCH_CLEARED": "제공처 간 시세 불일치 해소", "CORPORATE_ACTION_PROVIDER_MISMATCH": "제공처 간 기업행동 불일치",
    "PRIMARY_ERROR": "주 제공처 자료 오류", "SECONDARY_PRICE_UNAVAILABLE": "보조 제공처 시세 없음",
    "DIVIDEND_PAY_DATE_MISSING": "배당 지급일 없음(보류)",  # READINESS D12
    "FINALIZATION_RECHECK_NO_CHANGE": "13:30 재확인 변경 없음", "FREE_CASH_BELOW_FLOOR": "자유현금 하한 미만", "FX_FINALIZED": "환율 확정",
    "INPUT_REVISED": "입력 수정됨", "PARTIAL_FILL": "부분 체결", "PENDING_REDUCED_TO_FREE_CASH": "대기 현금을 자유현금 한도로 줄임",
    "PLAN_INPUTS_DEFERRED_DATA_MISSING": "자료 없음으로 계획 입력 이월", "POLICY_REJECTION": "정책 거부", "QTY_MISMATCH": "수량 대사 불일치",
    "QTY_WHOLE_OPEN_ABOVE_LIMIT_ZERO_FILL": "시가가 지정 한도 초과로 미체결", "RECONCILIATION_RELEASE_INCOMPLETE": "대사 차단 해제 미완료",
    "RUN_MISSED": "실행 누락", "SETTLEMENT_DATE_DIFFERS_FROM_COMPUTED": "결제일이 계산과 다름", "SETTLEMENT_DATE_MISMATCH": "결제일 대사 불일치",
    "STOCK_NAME_ABOVE_ALERT_WEIGHT": "개별 종목 경보 기준 초과", "STOCK_SLEEVE_ABOVE_TARGET": "개별주 슬리브 목표 초과",
    "USER_ORDER_NOT_PLANNED_DATA_MISSING": "자료 없음으로 사용자 주문 미계획", "USER_ORDER_REJECTED_BY_POLICY": "정책에 따라 사용자 주문 거부",
    "VALUATION_FX_REQUIRED": "환산 환율 필요",
}


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
        text = json.dumps(_free_text(name, value), ensure_ascii=False)  # not lower-cased first: _words needs the case boundaries
        problems += [f"TOKEN_IN_VALUE:{name}:{t}" for t in TOKENS if _contains_token(text, t)]
        if name == "ALERTS":  # A8-2: an unregistered alert string is also screened for the valuation words
            problems += [f"VALUATION_WORD_IN_ALERT:{w}" for w in VALUATION_WORDS if _contains_token(text, w)]
    problems += [f"TOKEN_IN_LABEL:{k}:{t}" for k, label in {**LABELS_KO, **CODE_LABELS_KO}.items() for t in TOKENS if _contains_token(label, t)]
    if table_sha256() != TABLE_SHA256:
        problems.append("FORBIDDEN_TABLE_HASH_MISMATCH")
    return problems


def _free_text(name: str, value: object) -> object:
    """A8-2: the value without the registered codes (an ALERTS entry, or a segment of HALTED:<reason>)."""
    if name == "ALERTS" and isinstance(value, list):
        return [v for v in value if not (isinstance(v, str) and v in CODE_LABELS_KO)]
    if name == "RUN_STATUS" and isinstance(value, str):
        return ":".join(part for part in value.split(":") if part not in CODE_LABELS_KO)
    return value


def code_text(code: str) -> str:
    """A registered code with its Korean label; any other string as it is."""
    return f"{code} ({CODE_LABELS_KO[code]})" if isinstance(code, str) and code in CODE_LABELS_KO else str(code)


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
            text = ", ".join(code_text(v) for v in value) or "없음"  # A8-2: registered codes with their Korean labels
        else:
            text = "-" if value is None else str(value)
        rows.append((LABELS_KO[name], text))
    return rows
