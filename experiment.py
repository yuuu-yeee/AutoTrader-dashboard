"""The experiment account screens (EXPERIMENT_ACCOUNT_CONTRACT_V2 dashboard; Session 2 Q1-4). One slot at a time, within the G4 ANNEX_11
items: summary cards, valuation over time, holdings, trades and alerts, computed in memory when the page opens from the slot's state
(ops/experiment-state) and the experiment's stored closes and USD/KRW (AutoTrader-ops-inputs experiment/). Standard library only: the file
runs in the public code-only repository and never imports the experiment package. Nothing here takes two slots or C0 together."""
from __future__ import annotations

from bisect import bisect_right
from decimal import Decimal

NOTICE = "EXPERIMENTAL_PAPER_NON_CLAIM — 검증되지 않은 탐색 실험, 연구 증거 및 실제자금 근거로 사용 금지"
CODES_KO = {"SLOT_HALTED": "슬롯 멈춤", "BUY_CANCELLED_NO_PRICE": "시가 없어 매수 취소", "SELL_WAITING_NO_PRICE": "시가 없어 매도 대기",
            "BUY_BELOW_MINIMUM": "최소 주문 금액 미만", "HELD_SYMBOL_NO_PRICE": "보유 종목 시세 없음",
            "ENTRY_LIMITED_BY_CASH": "현금 부족으로 진입 제한", "DIVIDEND_PAY_DATE_MISSING": "배당 지급일 없음(보류)",
            "PRICE_CROSS_CHECK_MISMATCH": "교차검사 종가 불일치", "PRICE_CROSS_CHECK_UNAVAILABLE": "교차검사 불가"}
REASONS_KO = {"ENTRY_SIGNAL": "진입 신호", "STOP_LOSS": "손절 (-8%)", "RSI_EXIT": "RSI 청산", "TIME_EXIT": "보유 기간 청산"}
ZERO = Decimal(0)


def core(state: dict) -> dict:
    """The slot's latest state (provisional until its finalization run)."""
    return state["latest"]


def start(state: dict) -> dict:
    """{krw, usd, rate, session} of the slot's one deposit and FX conversion."""
    fx = next((e for e in core(state)["events"] if e["type"] == "FX"), None)
    if fx is None:
        return {}
    return {"krw": Decimal(fx["krw"]), "usd": Decimal(fx["usd"]), "rate": Decimal(fx["rate"]), "session": fx["day"]}


def sessions(state: dict) -> list[str]:
    return [d["session"] for d in core(state)["daily"]]


def rate_on(fx: dict[str, str], day: str) -> Decimal | None:
    days = sorted(fx)
    i = bisect_right(days, day)
    return Decimal(fx[days[i - 1]]) if i else None


def daily(state: dict, closes: dict[str, dict], fx: dict[str, str]) -> list[dict]:
    """One row per recorded session with a close for every holding: value in USD and KRW, change against the start (no further deposit,
    so the time-weighted return equals the change against the start)."""
    s, rows = start(state), []
    if not s:
        return rows
    for d in core(state)["daily"]:
        bars = closes.get(d["session"], {})
        held = {k: Decimal(v) for k, v in d["quantities"].items() if Decimal(v)}
        rate = rate_on(fx, d["session"])
        if rate is None or any(k not in bars for k in held):
            continue
        usd = Decimal(d["usd"]) + sum((q * Decimal(bars[k]["c"]) for k, q in held.items()), ZERO)
        krw = usd * rate
        rows.append({"session": d["session"], "value_usd": usd, "value_krw": krw, "usd_krw": rate, "gain_usd": usd - s["usd"],
                     "gain_krw": krw - s["krw"], "return_usd": usd / s["usd"] - 1, "return_krw": krw / s["krw"] - 1})
    return rows


def holdings(state: dict, bars: dict) -> list[dict]:
    c, out = core(state), []
    last = c["daily"][-1] if c["daily"] else {"quantities": {}, "usd": "0"}
    held = {k: Decimal(v) for k, v in last["quantities"].items() if Decimal(v)}
    total = Decimal(last["usd"]) + sum((q * Decimal(bars[k]["c"]) for k, q in held.items() if k in bars), ZERO)
    for symbol, qty in sorted(held.items()):
        pos = c["positions"].get(symbol, {})
        buy = next((t for t in reversed(c["trades"]) if t["symbol"] == symbol and t["side"] == "BUY"), None)
        cost = Decimal(buy["qty"]) * Decimal(buy["price"]) + Decimal(buy["fee"]) if buy else None
        price = Decimal(bars[symbol]["c"]) if symbol in bars else None
        value = qty * price if price is not None else None
        out.append({"symbol": symbol, "qty": qty, "entry_session": pos.get("entry_session"), "entry_price": pos.get("entry_price"),
                    "price": price, "value": value, "gain": None if value is None or cost is None else value - cost,
                    "share": None if value is None or not total else value / total})
    return out


def trades(state: dict) -> list[dict]:
    return [dict(t, reason_ko=REASONS_KO.get(t["reason"], t["reason"])) for t in reversed(core(state)["trades"])]


def alerts(state: dict) -> list[dict]:
    c = core(state)
    out = [{"code": a["alert"], "label": CODES_KO.get(a["alert"], a["alert"]),
            "detail": str(a.get("symbol") or a.get("reason") or a.get("ex_date") or "")} for a in c["alerts"]]
    if c.get("halt"):
        out.insert(0, {"code": "SLOT_HALTED", "label": CODES_KO["SLOT_HALTED"], "detail": c["halt"]["reason"]})
    return out


def pending(state: dict) -> list[dict]:
    return [{"side": o["side"], "symbol": o["symbol"], "reason_ko": REASONS_KO.get(o["reason"], o["reason"])} for o in core(state)["pending"]]
