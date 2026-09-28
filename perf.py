"""The USER-only view of the shadow run's reference figures (G4 ANNEX_11, USER 2026-09-28). Standard library only, so the file runs in the
public code-only repository. Everything is computed in memory when the page is opened, from the state branch history (one state per
session: the last commit whose last_processed_session is that session) and the input records the latest state names (after the 13:30
finalization the state names the finalized record); nothing is written anywhere. Reference figures of the shadow run, not a strategy
evaluation; the report-table items outside the ANNEX_11 exception (track_c/ops/dashboard_sync.py) are not computed."""
from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

try:  # inside AutoTrader
    from track_c.ops.dashboard.view import CASH_SLEEVE, CODE_LABELS_KO, SLEEVE_OF, STOCK_SLEEVE, build_view
except ImportError:  # the public repository holds these files side by side
    from view import CASH_SLEEVE, CODE_LABELS_KO, SLEEVE_OF, STOCK_SLEEVE, build_view

NOTICE = "모의운용 참고치이며 전략 평가가 아님"  # ANNEX_11 condition (4)
BAND = Decimal("0.05")  # C0 HYBRID_QUARTERLY_CHECK_BAND_5PP: +-5 percentage points around each target
SLEEVE_NAMES = {"BROAD_US_LARGE_ETF": "VOO (S&P 500)", "NASDAQ100_ETF": "QQQM (나스닥 100)", "US_LARGE_VALUE_ETF": "VTV (미국 대형 가치)",
                STOCK_SLEEVE: "개별주 (사용자 선택)", CASH_SLEEVE: "USD 현금"}
SYMBOL_NAMES = {"VOO": "VOO (S&P 500)", "IVV": "IVV (S&P 500)", "QQQM": "QQQM (나스닥 100)", "QQQ": "QQQ (나스닥 100)",
                "VTV": "VTV (미국 대형 가치)"}
# codes that wait for a USER input (an incident record with USER_ACK, a reconciliation or corporate-action USER_ACK, an official source)
ACK_CODES = ("ENGINE_HALT", "CASH_MISMATCH", "QTY_MISMATCH", "SETTLEMENT_DATE_MISMATCH", "CA_BLOCK", "CORPORATE_ACTION_PENDING_BROKER_REPORT",
             "CORPORATE_ACTION_PROVIDER_MISMATCH", "CORPORATE_ACTION_RELEASE_INCOMPLETE", "RECONCILIATION_RELEASE_INCOMPLETE",
             "TICKER_CHANGE_RELEASE_INCOMPLETE", "HELD_TICKER_PRICE_MISSING", "DIVIDEND_PAY_DATE_MISSING")
STATUS_OK, STATUS_HALT, STATUS_ALERT = "정상", "멈춤", "경보"
KST = timezone(timedelta(hours=9))
ZERO = Decimal(0)


def per_session(states: list[dict]) -> dict[str, dict]:
    """{session: the last state (states are oldest first) whose last_processed_session is that session}."""
    out = {}
    for state in states:
        if state.get("last_processed_session"):
            out[state["last_processed_session"]] = state
    return out


def status_of(state: dict) -> str:
    return STATUS_HALT if state.get("halt") else STATUS_ALERT if state.get("alerts") else STATUS_OK


def _cash(state: dict, key: str) -> Decimal:
    return Decimal(state.get("ledger", {}).get("cash_ledger", {}).get(key, "0"))


def _held(state: dict) -> dict[str, Decimal]:
    return {k: Decimal(v) for k, v in state.get("ledger", {}).get("quantities", {}).items() if Decimal(v)}


def daily(states: list[dict], records: dict[str, dict]) -> list[dict]:
    """One row per session with a state and a record holding a close for every holding: valuation in USD and KRW, the deposits
    converted that day and in total, the day's gain net of deposits, the time-weighted return chained so far, and the day's status.
    A session without its own state (caught up inside a later run) or without a price is left out and counted in `gaps`."""
    by_session, latest = per_session(states), (states[-1] if states else {})
    conversions = latest.get("ledger", {}).get("cash_ledger", {}).get("fx_conversions", [])
    flows: dict[str, list[Decimal]] = {}
    for c in conversions:
        f = flows.setdefault(c["day"], [ZERO, ZERO])
        f[0] += Decimal(c["usd"])
        f[1] += Decimal(c["krw"])
    rows, prev, cum_usd, cum_krw, twr_usd, twr_krw = [], None, ZERO, ZERO, Decimal(1), Decimal(1)
    for session in sorted(set(by_session) | set(flows)):
        in_usd, in_krw = flows.get(session, [ZERO, ZERO])
        cum_usd, cum_krw = cum_usd + in_usd, cum_krw + in_krw
        state, record = by_session.get(session), records.get(session)
        if state is None or record is None:  # a halted state keeps its ledger unchanged: valued, with the status 멈춤
            continue
        closes = {k: Decimal(v["close"]) for k, v in record["market"]["bars"].items()}
        held = _held(state)
        if any(k not in closes for k in held):
            continue
        rate = Decimal(record["market"]["fx_usdkrw"])
        usd = sum((q * closes[k] for k, q in held.items()), ZERO) + _cash(state, "USD_AVAILABLE")
        krw = usd * rate + _cash(state, "KRW_AVAILABLE")
        base_usd = (prev["value_usd"] if prev else ZERO) + in_usd  # deposits counted at the start of the day
        base_krw = (prev["value_krw"] if prev else ZERO) + in_krw
        if base_usd > 0:
            twr_usd *= usd / base_usd
        if base_krw > 0:
            twr_krw *= krw / base_krw
        rows.append({"session": session, "value_usd": usd, "value_krw": krw, "usd_krw": rate, "deposit_usd": in_usd, "deposit_krw": in_krw,
                     "deposits_usd": cum_usd, "deposits_krw": cum_krw, "gain_usd": usd - cum_usd, "gain_krw": krw - cum_krw,
                     "day_gain_usd": usd - base_usd, "day_gain_krw": krw - base_krw, "twr_usd": twr_usd - 1, "twr_krw": twr_krw - 1,
                     "status": status_of(state)})
        prev = rows[-1]
    return rows


def calendar_days(states: list[dict], rows: list[dict]) -> list[dict]:
    """Every session with a state: its status (the halt of a session is on the state that kept it as the last processed one) and the
    day's gain where it was computed."""
    gains = {r["session"]: r["day_gain_usd"] for r in rows}
    out = []
    for session, state in sorted(per_session(states).items()):
        day = date.fromisoformat(session)
        out.append({"session": session, "status": status_of(state), "day_gain_usd": gains.get(session),
                    "weekday": day.weekday(), "week": (day - timedelta(days=day.weekday())).isoformat()})
    return out


def holdings(state: dict, record: dict) -> list[dict]:
    """The latest holdings: quantity, close of the last session, valuation, gain against the open lots' USD cost, share of the total."""
    closes = {k: Decimal(v["close"]) for k, v in record["market"]["bars"].items()}
    held = _held(state)
    cost: dict[str, Decimal] = {}
    for lot in state.get("ledger", {}).get("lots", []):
        cost[lot["symbol"]] = cost.get(lot["symbol"], ZERO) + Decimal(lot["cost_usd"])
    total = sum((q * closes[k] for k, q in held.items() if k in closes), ZERO) + _cash(state, "USD_AVAILABLE")
    out = []
    for symbol, qty in sorted(held.items()):
        price = closes.get(symbol)
        value = qty * price if price is not None else None
        out.append({"symbol": symbol, "name": SYMBOL_NAMES.get(symbol, symbol), "sleeve": SLEEVE_NAMES[SLEEVE_OF.get(symbol, STOCK_SLEEVE)],
                    "qty": qty, "price": price, "value": value, "gain": None if value is None else value - cost.get(symbol, ZERO),
                    "share": None if value is None or not total else value / total})
    return out


def price_lines(states: list[dict], records: dict[str, dict]) -> dict[str, list[tuple[str, Decimal]]]:
    """{symbol: [(session, close)]} over the sessions the symbol was held."""
    out: dict[str, list[tuple[str, Decimal]]] = {}
    for session, state in sorted(per_session(states).items()):
        bars = records.get(session, {}).get("market", {}).get("bars", {})
        for symbol in _held(state):
            if symbol in bars:
                out.setdefault(symbol, []).append((session, Decimal(bars[symbol]["close"])))
    return out


def weights(state: dict, record: dict) -> list[dict]:
    """Target and current sleeve weights (the point-in-time computation of view.build_view) with the +-5 percentage point band."""
    view = build_view(state, record)
    current = view.get("CURRENT_EXACT_WEIGHT_POINT_IN_TIME", {})
    out = []
    for sleeve, target in sorted(view["TARGETS"].items(), key=lambda kv: -Decimal(kv[1])):
        t = Decimal(target)
        out.append({"sleeve": SLEEVE_NAMES.get(sleeve, sleeve), "target": t, "low": max(t - BAND, ZERO), "high": t + BAND,
                    "current": Decimal(current[sleeve]) if sleeve in current else None})
    return out


def todo(state: dict) -> list[dict]:
    """The latest alerts with Korean labels; the ones that wait for a USER input first."""
    items = []
    if state.get("halt"):
        items.append({"code": "ENGINE_HALT", "label": f"실행 멈춤: {state['halt'].get('reason')}", "ack": True,
                      "detail": f"incidents/{state['halt'].get('incident_id')}.json 에 사고 기록과 USER_ACK 필요"})
    for pending in state.get("reconciliation", {}).get("official_resolution_pending_user_ack", []):
        items.append({"code": "OFFICIAL_RESOLUTION", "label": "공식 자료 해결 확인 대기", "ack": True, "detail": str(pending.get("event_id", ""))})
    for alert in state.get("alerts", []):
        code = str(alert.get("alert"))
        items.append({"code": code, "label": CODE_LABELS_KO.get(code, code), "ack": code in ACK_CODES,
                      "detail": str(alert.get("symbol") or alert.get("session") or "")})
    return sorted(items, key=lambda i: not i["ack"])


def next_quarterly_check(after: date) -> date:
    """The last weekday of the next March, June, September or December after `after` (NYSE holidays are not known here)."""
    year, month = after.year, after.month
    while True:
        if month in (3, 6, 9, 12):
            last = date(year, month, calendar.monthrange(year, month)[1])
            while last.weekday() >= 5:
                last -= timedelta(days=1)
            if last > after:
                return last
        month, year = (1, year + 1) if month == 12 else (month + 1, year)


def next_main_run(now: datetime) -> datetime:
    """The next 09:30 KST on a weekday (the main run time of G4 S2; whether the schedule is on is not known here)."""
    local = now.astimezone(KST)
    day = local.date() + (timedelta(days=0) if local.time() < time(9, 30) else timedelta(days=1))
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime.combine(day, time(9, 30), KST)


def held_dividends(state: dict) -> list[dict]:
    """Dividends held until a pay date or an official resolution (READINESS D12, ANNEX_10) that are not released yet."""
    rows = state.get("ledger", {}).get("corporate_action_ledger", [])
    released = {r.get("hold_id") or r.get("id") for r in rows if r.get("op") in ("dividend_pay_date_found", "official_resolution_ack")}
    return [{"id": r["id"], "symbol": r.get("symbol"), "ex_date": r.get("ex_date") or r.get("day")} for r in rows
            if r.get("op") == "dividend_pay_date_missing" and r["id"] not in released]


def deposits(state: dict) -> list[dict]:
    return [{"day": c["day"], "krw": Decimal(c["krw"]), "usd": Decimal(c["usd"]), "rate": Decimal(c["rate"])}
            for c in state.get("ledger", {}).get("cash_ledger", {}).get("fx_conversions", [])]
