"""The experiment account screens (EXPERIMENT_ACCOUNT_CONTRACT_V2 dashboard; Session 2 Q1-4; CONTRACT_V4 USER decision (b)). One slot at a
time within the G4 ANNEX_11 items (summary cards, valuation over time, holdings, trades and alerts), and, by CONTRACT_V4, the X2 screens
(stage bands, automatic changes, effective parameters, scores, optimizations, stop) and the comparison of experiment slots (valuation
indexed to 100 at each start, gain and return in USD and KRW, maximum drawdown, closed trades, win rate, total gain / total loss). All
computed in memory when the page opens from the slots' states (ops/experiment-state) and the experiment's stored closes and USD/KRW
(AutoTrader-ops-inputs experiment/). Standard library only: the file runs in the public code-only repository and never imports the
experiment package or a C0 module; nothing here takes C0 figures."""
from __future__ import annotations

from bisect import bisect_right
from decimal import Decimal

NOTICE = "EXPERIMENTAL_PAPER_NON_CLAIM — 검증되지 않은 탐색 실험, 연구 증거 및 실제자금 근거로 사용 금지"
CODES_KO = {"SLOT_HALTED": "슬롯 멈춤", "BUY_CANCELLED_NO_PRICE": "시가 없어 매수 취소", "SELL_WAITING_NO_PRICE": "시가 없어 매도 대기",
            "BUY_BELOW_MINIMUM": "최소 주문 금액 미만", "HELD_SYMBOL_NO_PRICE": "보유 종목 시세 없음",
            "ENTRY_LIMITED_BY_CASH": "현금 부족으로 진입 제한", "DIVIDEND_PAY_DATE_MISSING": "배당 지급일 없음(보류)",
            "PRICE_CROSS_CHECK_MISMATCH": "교차검사 종가 불일치", "PRICE_CROSS_CHECK_UNAVAILABLE": "교차검사 불가",
            "BUY_NOT_FILLED_NO_OPEN": "시가 없어 매수 안 함", "REGIME_UNAVAILABLE": "시장 국면 계산 불가 (준비 기간)"}
REASONS_KO = {"ENTRY_SIGNAL": "진입 신호", "STOP_LOSS": "손절 (-8%)", "RSI_EXIT": "RSI 청산", "TIME_EXIT": "보유 기간 청산",
              "ENTRY_SCORE": "점수 진입", "TARGET": "목표 (SMA20 회복)", "STOP": "손절 (k × ATR14)", "TIME": "보유 기간 청산"}
STAGES_KO = {"AGGRESSIVE": "공격", "NORMAL": "보통", "CAUTIOUS": "조심", "PAUSED": "중단"}
CHANGES_KO = {"REGIME": "1층 국면 전환", "PERFORMANCE_LOWER": "2층 낮춤", "PERFORMANCE_RESTORE": "2층 복귀", "FINAL_STAGE": "최종 단계 변경",
              "OPTIMIZATION": "최적화 실행", "EMERGENCY_STOP": "비상 정지", "EMERGENCY_STOP_RELEASED": "정지 해제 (USER)", "SLOT_ENDED": "슬롯 종료"}
ZERO = Decimal(0)
NONE = "없음"  # a bare "-" renders as a list bullet in a table cell


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
    ended = c.get("halt") or c.get("end")
    if ended:
        out.insert(0, {"code": "SLOT_HALTED", "label": CODES_KO["SLOT_HALTED"], "detail": ended["reason"]})
    return out


def pending(state: dict) -> list[dict]:
    return [{"side": o["side"], "symbol": o["symbol"], "reason_ko": REASONS_KO.get(o["reason"], o["reason"])} for o in core(state)["pending"]]


# ---------------------------------------------------------------- CONTRACT_V4 (b): experiment slots side by side (never C0)
def closed_trades(state: dict) -> list[dict]:
    """The slot's closed trades with their net USD result (fees included): X2 records it on the SELL; for X1 a SELL is matched with the
    latest BUY of the symbol before it (X1 sells whole positions)."""
    out, last_buy = [], {}
    for t in core(state)["trades"]:
        if t["side"] == "BUY":
            last_buy[t["symbol"]] = t
        elif t.get("pnl_usd") is not None:
            out.append({"session": t["session"], "symbol": t["symbol"], "net_usd": Decimal(t["pnl_usd"])})
        elif t["symbol"] in last_buy:
            b = last_buy.pop(t["symbol"])
            net = Decimal(t["qty"]) * Decimal(t["price"]) - Decimal(t["fee"]) - (Decimal(b["qty"]) * Decimal(b["price"]) + Decimal(b["fee"]))
            out.append({"session": t["session"], "symbol": t["symbol"], "net_usd": net})
    return out


def trade_stats(closed: list[dict]) -> dict:
    wins = [c["net_usd"] for c in closed if c["net_usd"] > 0]
    losses = [-c["net_usd"] for c in closed if c["net_usd"] < 0]
    total_loss = sum(losses, ZERO)
    return {"closed": len(closed), "win_rate": Decimal(len(wins)) / len(closed) if closed else None,
            "gain_to_loss": sum(wins, ZERO) / total_loss if total_loss else None}


def max_drawdown(rows: list[dict], key: str) -> Decimal | None:
    """The largest fall of value_<key> from its running peak, as a fraction of that peak (CONTRACT_V4 (b), experiment slots only)."""
    peak, worst = None, ZERO
    for r in rows:
        value = r[f"value_{key}"]
        peak = value if peak is None or value > peak else peak
        worst = max(worst, (peak - value) / peak)
    return worst if rows else None


def indexed(rows: list[dict], state: dict) -> list[dict]:
    """Valuation indexed to 100 at the slot's start (USD and KRW)."""
    s = start(state)
    return [{"session": r["session"], "usd": r["value_usd"] / s["usd"] * 100, "krw": r["value_krw"] / s["krw"] * 100} for r in rows]


def comparison(states: dict[str, dict], closes: dict[str, dict], fx: dict[str, str]) -> list[dict]:
    """One row per experiment slot: gain and return (USD, KRW) at its last valued session, maximum drawdown, closed trades, win rate,
    total gain / total loss, and its indexed valuation."""
    out = []
    for slot, state in states.items():
        rows = daily(state, closes, fx)
        last = rows[-1] if rows else {}
        out.append({"slot": slot, "session": last.get("session"), "gain_usd": last.get("gain_usd"), "gain_krw": last.get("gain_krw"),
                    "return_usd": last.get("return_usd"), "return_krw": last.get("return_krw"), "max_drawdown_usd": max_drawdown(rows, "usd"),
                    "max_drawdown_krw": max_drawdown(rows, "krw"), **trade_stats(closed_trades(state)),
                    "indexed": indexed(rows, state) if rows else []})
    return out


def _pct(value: Decimal | None, signed: bool = False) -> str:
    return NONE if value is None else (f"{value * 100:+.2f}%" if signed else f"{value * 100:.2f}%")


def _money(value: Decimal | None, unit: str) -> str:
    if value is None:
        return NONE
    return f"{'+' if value >= 0 else '-'}${abs(value):,.2f}" if unit == "usd" else f"{value:+,.0f}원"


def comparison_table(rows: list[dict]) -> list[dict]:
    """The comparison rows as the screen shows them (Korean labels, formatted text)."""
    return [{"슬롯": r["slot"], "기준 장": r["session"] or NONE, "손익 (달러)": _money(r["gain_usd"], "usd"), "손익 (원화)": _money(r["gain_krw"], "krw"),
             "시작 대비 (달러)": _pct(r["return_usd"], True), "시작 대비 (원화)": _pct(r["return_krw"], True),
             "최대 낙폭 (달러)": _pct(r["max_drawdown_usd"]), "최대 낙폭 (원화)": _pct(r["max_drawdown_krw"]), "종료 거래": r["closed"],
             "승률": _pct(r["win_rate"]), "총이익/총손실": NONE if r["gain_to_loss"] is None else f"{r['gain_to_loss']:.2f}"} for r in rows]


# ---------------------------------------------------------------- CONTRACT_V4: the X2 screens
def is_adaptive(state: dict) -> bool:
    return "stage" in core(state)


def stage_bands(state: dict) -> list[dict]:
    return [{"session": d["session"], "stage": d["stage"], "label": STAGES_KO.get(d["stage"], d["stage"]), "stopped": d.get("stopped", False)}
            for d in core(state)["daily"]]


def _shown(value) -> str:
    if value is None:
        return NONE
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    return STAGES_KO.get(value, str(value))


def change_marks(changes: list[dict]) -> list[dict]:
    """The automatic changes of the final steps (changes.jsonl), newest first; stage codes in Korean, parameters as name=value."""
    return [{"session": c["session"], "kind": c["kind"], "label": CHANGES_KO.get(c["kind"], c["kind"]), "before": _shown(c.get("before")),
             "after": _shown(c.get("after")), "reason": c.get("reason", "")} for c in reversed(changes)]


def effective(state: dict) -> dict:
    c = core(state)
    return {"params": c["params"], "stage": c["stage"], "stage_ko": STAGES_KO.get(c["stage"], c["stage"]), "layer1": c["regime"]["effective"],
            "layer2": c["layer2"]["cap"], "stop": c["stop"], "end": c.get("end"), "since_optimization": c["optimizer"]["since"],
            "last_optimization": c["optimizer"]["last"]}


def score_rows(state: dict, recent: int = 20) -> list[dict]:
    """A/B/C/D and total of the held symbols (at their purchase) and of the recent purchases."""
    c, out = core(state), []
    for symbol, pos in sorted(c["positions"].items()):
        out.append({"symbol": symbol, "session": pos["entry_session"], "held": True, **pos["scores"], "threshold": pos["threshold"],
                    "stage": STAGES_KO.get(pos["stage"], pos["stage"])})
    for t in reversed(c["trades"]):
        if len(out) >= recent:
            break
        if t["side"] == "BUY" and t["symbol"] not in c["positions"]:
            out.append({"symbol": t["symbol"], "session": t["session"], "held": False, **t["scores"], "threshold": t["threshold"],
                        "stage": STAGES_KO.get(t["stage"], t["stage"])})
    return out


def optimization_rows(state: dict) -> list[dict]:
    rows = []
    for o in reversed(core(state)["optimizations"]):
        best = o["top"][0] if o["top"] else None
        rows.append({"session": o["session"], "method": o["method"], "evaluated": o["evaluated"], "runtime_seconds": o["runtime_seconds"],
                     "adopted": o["adopted"], "reason": o["reason"], "current_objective": (o["current"] or {}).get("objective"),
                     "best_objective": best["objective"] if best else None, "best_params": best["params"] if best else None,
                     "adopted_params": o["adopted_params"]})
    return rows
