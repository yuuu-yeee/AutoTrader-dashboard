"""AutoTrader Phase 7 shadow dashboard (Streamlit; G4 ANNEX_2, ANNEX_3, ANNEX_11). Deployed from the public code-only repository with the
app set to private; the USER is the only viewer. G4 ANNEX_11 (USER 2026-09-28): the reference figures of the shadow run (valuation over
time, gain in USD and KRW, time-weighted return, holdings and their prices) are computed in memory on every page load and never written
(no git, state branch, alert, report, file export, URL parameter, cache on disk, or value in a log or error message)."""
from __future__ import annotations

from datetime import date, datetime, timezone

try:  # inside AutoTrader (tests, G3 checks)
    from track_c.ops.dashboard import experiment, perf
    from track_c.ops.dashboard.reader import GitHubReader
    from track_c.ops.dashboard.view import build_view, check_screen, render_rows
except ImportError:  # the public repository holds these files side by side
    import experiment
    import perf
    from reader import GitHubReader
    from view import build_view, check_screen, render_rows

ACCOUNTS = ["모의운용 (C0)", "실험 계좌"]
STATUS_COLORS = {perf.STATUS_OK: "#2e7d32", perf.STATUS_ALERT: "#ef8f00", perf.STATUS_HALT: "#c62828"}
WEEKDAYS = ["월", "화", "수", "목", "금"]
COMPARED = ["X1-C4R-V1", "X2-ADAPTIVE"]  # EXPERIMENT_ACCOUNT_CONTRACT_V4 (b)
COMPARE_CHOICE = "X1·X2 비교"
STAGE_COLORS = {"AGGRESSIVE": "#1565c0", "NORMAL": "#2e7d32", "CAUTIOUS": "#ef8f00", "PAUSED": "#9e9e9e"}
# ANNEX_11 (1): the element toolbar of charts and tables (data view, save, copy) is hidden; nothing leaves the page
HIDE_TOOLBAR = "<style>[data-testid='stElementToolbar'] {display: none !important;}</style>"


def load(reader) -> dict:
    """The point-in-time view (ANNEX_2/3) of the latest state."""
    state = reader.state()
    session = state.get("last_processed_session")
    digest = state.get("input_snapshot_sha256", {}).get(session) if session else None
    return build_view(state, reader.record(digest) if digest else None, reader.last_run_time_utc())


def load_all(reader) -> dict:
    """ANNEX_11: the state history and the records the latest state names, read in memory."""
    states = reader.state_history()
    latest = states[-1] if states else reader.state()
    records = reader.records(dict(latest.get("input_snapshot_sha256", {})))
    session = latest.get("last_processed_session")
    return {"states": states or [latest], "latest": latest, "records": records, "record": records.get(session) if session else None,
            "last_run": reader.last_run_time_utc()}


def usd(value) -> str:
    return "-" if value is None else f"${value:,.2f}"


def krw(value) -> str:
    return "-" if value is None else f"{value:,.0f}원"


def pct(value) -> str:
    return "-" if value is None else f"{value * 100:+.2f}%"


def signed_usd(value) -> str:
    return "-" if value is None else f"{'+' if value >= 0 else '-'}${abs(value):,.2f}"


def signed_krw(value) -> str:
    return "-" if value is None else f"{value:+,.0f}원"


def summary(st, rows: list[dict]) -> None:
    if not rows:
        st.info("평가할 수 있는 장이 아직 없습니다.")
        return
    last = rows[-1]
    a, b, c = st.columns(3)
    a.metric("총평가 (원화)", krw(last["value_krw"]), signed_krw(last["day_gain_krw"]) + " 오늘")
    a.metric("총평가 (달러)", usd(last["value_usd"]), signed_usd(last["day_gain_usd"]) + " 오늘")
    b.metric("누적 입금 (원화)", krw(last["deposits_krw"]))
    b.metric("누적 입금 (달러 환산)", usd(last["deposits_usd"]))
    c.metric("손익 (원화, 환율 효과 포함)", signed_krw(last["gain_krw"]))
    c.metric("손익 (달러)", signed_usd(last["gain_usd"]))
    d, e, f = st.columns(3)
    d.metric("시간가중수익률 (달러)", pct(last["twr_usd"]))
    e.metric("시간가중수익률 (원화, 환율 효과 포함)", pct(last["twr_krw"]))
    f.metric(f"기준 장 (USD/KRW {last['usd_krw']:,.2f})", last["session"])
    st.caption("손익 = 현재 평가액 − 누적 입금. 시간가중수익률은 입금 영향을 뺀 값입니다(입금은 그날 시작에 들어온 것으로 계산). "
               "가격은 13:30 확정 기준 스냅샷(확정 전이면 첫 관측) 종가입니다.")


def value_chart(st, alt, rows: list[dict]) -> None:
    unit = st.radio("통화", ["달러", "원화"], horizontal=True, key="value_unit")
    key = "usd" if unit == "달러" else "krw"
    data = [{"session": r["session"], "series": name, "amount": float(r[field])} for r in rows
            for name, field in (("평가액", f"value_{key}"), ("누적 입금", f"deposits_{key}"))]
    chart = alt.Chart(alt.Data(values=data)).mark_line(point=True).encode(
        x=alt.X("session:T", title="장"), y=alt.Y("amount:Q", title="달러" if key == "usd" else "원"),
        color=alt.Color("series:N", title=None, scale=alt.Scale(domain=["평가액", "누적 입금"], range=["#1565c0", "#9e9e9e"])),
        strokeDash=alt.StrokeDash("series:N", legend=None, scale=alt.Scale(domain=["평가액", "누적 입금"], range=[[1, 0], [6, 4]])),
        tooltip=[alt.Tooltip("session:T", title="장"), alt.Tooltip("series:N", title="항목"), alt.Tooltip("amount:Q", title="금액", format=",.2f")])
    st.altair_chart(chart, use_container_width=True)


def calendar_chart(st, alt, days: list[dict]) -> None:
    if not days:
        st.info("표시할 장이 없습니다.")
        return
    data = [{"week": d["week"], "weekday": WEEKDAYS[d["weekday"]], "status": d["status"], "day": d["session"][5:],
             "gain": "-" if d["day_gain_usd"] is None else signed_usd(d["day_gain_usd"])} for d in days if d["weekday"] < 5]
    base = alt.Chart(alt.Data(values=data)).encode(x=alt.X("weekday:N", sort=WEEKDAYS, title=None, axis=alt.Axis(orient="top", labelAngle=0)),
                                                   y=alt.Y("week:O", title="주 시작일"))
    tooltip = [alt.Tooltip("day:N", title="날짜"), alt.Tooltip("status:N", title="상태"), alt.Tooltip("gain:N", title="그날 손익(달러)")]
    cells = base.mark_rect(stroke="white").encode(
        color=alt.Color("status:N", title="운영 상태", scale=alt.Scale(domain=list(STATUS_COLORS), range=list(STATUS_COLORS.values()))),
        tooltip=tooltip)
    labels = base.mark_text(color="white", fontSize=11).encode(text="gain:N", tooltip=tooltip)
    st.altair_chart((cells + labels).properties(height=max(120, 34 * len({d["week"] for d in data}))), use_container_width=True)
    st.caption("칸 색은 그날 운영 상태(정상·경보·멈춤), 글자는 입금을 뺀 그날 손익(달러)입니다.")


def weight_chart(st, alt, rows: list[dict]) -> None:
    data = [{"sleeve": r["sleeve"], "target": float(r["target"]), "low": float(r["low"]), "high": float(r["high"]),
             "current": None if r["current"] is None else float(r["current"])} for r in rows]
    order = [r["sleeve"] for r in rows]
    base = alt.Chart(alt.Data(values=data)).encode(y=alt.Y("sleeve:N", sort=order, title=None))
    band = base.mark_bar(color="#bbdefb", opacity=0.6, height=16).encode(x=alt.X("low:Q", title="비중", axis=alt.Axis(format="%")), x2="high:Q")
    current = base.mark_bar(color="#1565c0", height=8).encode(x="current:Q", tooltip=[
        alt.Tooltip("sleeve:N", title="슬리브"), alt.Tooltip("current:Q", title="현재", format=".2%"), alt.Tooltip("target:Q", title="목표", format=".0%")])
    target = base.mark_tick(color="#ffffff", thickness=2, size=18).encode(x="target:Q")
    st.altair_chart((band + current + target).properties(height=46 * len(rows)), use_container_width=True)
    st.caption("연한 띠 = 목표 ±5%p 밴드, 흰 선 = 목표, 파란 막대 = 현재 비중.")


def holdings_table(st, rows: list[dict]) -> None:
    if not rows:
        st.info("보유 종목이 없습니다.")
        return
    st.table([{"티커": r["name"], "슬리브": r["sleeve"], "수량": f"{r['qty']:,.6f}".rstrip("0").rstrip("."), "현재가": usd(r["price"]),
               "평가액": usd(r["value"]), "손익": signed_usd(r["gain"]), "비중": "-" if r["share"] is None else f"{r['share'] * 100:.2f}%"}
              for r in rows])
    st.caption("손익 = 평가액 − 남은 매수 로트의 달러 원가(수수료 포함).")


def price_chart(st, alt, lines: dict) -> None:
    if not lines:
        st.info("보유 기간 가격이 없습니다.")
        return
    symbol = st.selectbox("종목", sorted(lines), format_func=lambda s: perf.SYMBOL_NAMES.get(s, s))
    data = [{"session": s, "close": float(c)} for s, c in lines[symbol]]
    chart = alt.Chart(alt.Data(values=data)).mark_line(point=True).encode(
        x=alt.X("session:T", title="장"), y=alt.Y("close:Q", title="종가(달러)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("session:T", title="장"), alt.Tooltip("close:Q", title="종가", format=",.2f")])
    st.altair_chart(chart, use_container_width=True)


def todo_and_schedule(st, data: dict, now: datetime) -> None:
    latest = data["latest"]
    items = perf.todo(latest)
    st.subheader("경보·할 일")
    if not items:
        st.success("경보 없음")
    for item in items:
        text = f"**{item['label']}** ({item['code']})" + (f" — {item['detail']}" if item["detail"] else "")
        if item["ack"]:
            st.error("USER 확인 필요: " + text)
        else:
            st.markdown("- " + text)
    st.subheader("다가올 일정")
    session = latest.get("last_processed_session")
    after = date.fromisoformat(session) if session else now.date()
    held = perf.held_dividends(latest)
    st.markdown(f"- 다음 리밸런싱 점검일: **{perf.next_quarterly_check(after).isoformat()}** (분기 마지막 평일, 휴장일 미반영)")
    st.markdown(f"- 다음 정규 실행: **{perf.next_main_run(now).strftime('%Y-%m-%d %H:%M')} KST** (09:30 본 실행 기준; 예약 여부는 여기서 알 수 없음)")
    st.markdown("- 보류 배당: " + (", ".join(f"{h['symbol']} (권리락 {h['ex_date']})" for h in held) if held else "없음"))
    st.subheader("입금 내역")
    deps = perf.deposits(latest)
    if deps:
        st.table([{"환전일": d["day"], "원화": krw(d["krw"]), "달러": usd(d["usd"]), "환율": f"{d['rate']:,.2f}"} for d in deps])
    else:
        st.info("입금 내역이 없습니다.")


def compare_page(st, alt, reader) -> None:
    """EXPERIMENT_ACCOUNT_CONTRACT_V4 (b): the experiment slots side by side; no C0 figure is read or shown."""
    try:
        states = {s: reader.experiment_state(s) for s in COMPARED}
        closes = reader.experiment_closes(sorted({d for s in states.values() for d in experiment.sessions(s)}))
        rows = experiment.comparison(states, closes, reader.experiment_fx())
    except Exception:
        st.error("데이터를 읽지 못했습니다. 설정과 토큰 권한을 확인하세요.")
        return
    st.caption("두 실험 슬롯의 시작 시점과 규칙이 달라 같은 날짜의 값도 서로 다른 조건의 결과입니다. 모의운용(C0) 수치는 여기에 없습니다.")
    data = [{"session": p["session"], "slot": r["slot"], "value": float(p["usd"])} for r in rows for p in r["indexed"]]
    if data:
        st.altair_chart(alt.Chart(alt.Data(values=data)).mark_line(point=True).encode(
            x=alt.X("session:T", title="장"), y=alt.Y("value:Q", title="평가금액 (시작 = 100, 달러)", scale=alt.Scale(zero=False)),
            color=alt.Color("slot:N", title="슬롯", scale=alt.Scale(domain=COMPARED, range=["#ef8f00", "#1565c0"])),
            tooltip=[alt.Tooltip("session:T", title="장"), alt.Tooltip("slot:N", title="슬롯"), alt.Tooltip("value:Q", title="지수", format=",.2f")]),
            use_container_width=True)
    else:
        st.info("평가할 수 있는 장이 아직 없습니다.")
    st.table(experiment.comparison_table(rows))
    st.caption("최대 낙폭 = 일별 평가금액이 그때까지의 고점에서 가장 크게 내려간 비율. 승률·총이익/총손실은 종료 거래(수수료 포함 달러 순손익) 기준.")


def adaptive_tabs(st, alt, reader, slot: str, state: dict) -> None:
    """EXPERIMENT_ACCOUNT_CONTRACT_V4: stage bands with the automatic change marks, effective parameters, scores, optimizations."""
    try:
        changes = experiment.change_marks(reader.experiment_changes(slot))
    except Exception:
        changes = []
    eff = experiment.effective(state)
    tabs = st.tabs(["단계·자동 변경", "현재 파라미터", "점수표", "최적화 이력"])
    with tabs[0]:
        bands = experiment.stage_bands(state)
        if bands:
            rows = ["최종 단계", "자동 변경"]
            y = alt.Y("row:N", title=None, sort=rows, scale=alt.Scale(domain=rows))
            layer = alt.Chart(alt.Data(values=[dict(b, row=rows[0]) for b in bands])).mark_tick(thickness=12, size=26).encode(
                x=alt.X("session:T", title="장"), y=y, color=alt.Color("label:N", title="최종 단계", scale=alt.Scale(
                    domain=[experiment.STAGES_KO[s] for s in STAGE_COLORS], range=list(STAGE_COLORS.values()))),
                tooltip=[alt.Tooltip("session:T", title="장"), alt.Tooltip("label:N", title="단계")])
            marks = [{"session": c["session"], "label": c["label"], "row": rows[1]} for c in changes]
            if marks:
                layer = layer + alt.Chart(alt.Data(values=marks)).mark_point(shape="triangle-down", size=90, filled=True, color="#d81b60").encode(
                    x="session:T", y=y, tooltip=[alt.Tooltip("session:T", title="장"), alt.Tooltip("label:N", title="자동 변경")])
            st.altair_chart(layer.properties(height=120), use_container_width=True)
            st.caption("윗줄 색 = 그날 최종 단계(공격·보통·조심·중단), 아랫줄 ▼ = 자동 변경이 기록된 장.")
        if changes:
            st.table([{"장": c["session"], "종류": c["label"], "전": c["before"], "후": c["after"], "이유": c["reason"]}
                      for c in changes[:50]])
        else:
            st.info("자동 변경 기록이 아직 없습니다.")
    with tabs[1]:
        p = eff["params"]
        st.table([{"항목": name, "값": str(p[key])} for name, key in (("가중치 A (눌림)", "wA"), ("가중치 B (반등)", "wB"), ("가중치 C (거래량)", "wC"),
                                                                    ("가중치 D (상대 강도)", "wD"), ("기준점 오프셋", "threshold_offset"),
                                                                    ("손절배수 k", "k"), ("최대 보유일 H", "H"))])
        st.markdown(f"- 최종 단계: **{eff['stage_ko']}** (1층 {experiment.STAGES_KO.get(eff['layer1'], experiment.NONE)}, "
                    f"2층 {experiment.STAGES_KO.get(eff['layer2'], '제한 없음')})")
        st.markdown(f"- 마지막 최적화 이후 종료 거래: {eff['since_optimization']}건 · 마지막 최적화: {eff['last_optimization'] or '없음'}")
    with tabs[2]:
        rows = experiment.score_rows(state)
        if rows:
            st.table([{"티커": r["symbol"], "매수일": r["session"], "보유": "예" if r["held"] else "아니오", "A": f"{r['A']:.1f}", "B": f"{r['B']:.1f}",
                       "C": f"{r['C']:.1f}", "D": f"{r['D']:.1f}", "총점": f"{r['total']:.1f}", "기준점": r["threshold"], "단계": r["stage"]}
                      for r in rows])
        else:
            st.info("점수 기록이 아직 없습니다.")
    with tabs[3]:
        rows = experiment.optimization_rows(state)
        if rows:
            st.table([{"장": r["session"], "방식": r["method"], "후보 수": r["evaluated"], "실행 시간(초)": r["runtime_seconds"],
                       "채택": "예" if r["adopted"] else "아니오", "이유": r["reason"], "현재 목적값": r["current_objective"] or experiment.NONE,
                       "후보 중 가장 큰 목적값": r["best_objective"] or experiment.NONE} for r in rows])
        else:
            st.info("최적화 실행 기록이 아직 없습니다.")


def experiment_page(st, alt, reader) -> None:
    """EXPERIMENT_ACCOUNT_CONTRACT_V2: the notice always on top; one slot selected at a time; no figure of C0. CONTRACT_V4 (b): the
    X1·X2 comparison is one more choice of the slot box."""
    st.title("실험 계좌")
    st.error(experiment.NOTICE)
    try:
        slots = reader.experiment_slots()
        if not slots:
            st.info("실험 슬롯 상태가 아직 없습니다.")
            return
        choices = slots + ([COMPARE_CHOICE] if set(COMPARED) <= set(slots) else [])
        slot = st.selectbox("슬롯", choices, key="slot")
        if slot == COMPARE_CHOICE:
            compare_page(st, alt, reader)
            return
        state = reader.experiment_state(slot)
        closes = reader.experiment_closes(experiment.sessions(state))
        rows = experiment.daily(state, closes, reader.experiment_fx())
    except Exception:
        st.error("데이터를 읽지 못했습니다. 설정과 토큰 권한을 확인하세요.")  # X-1: no traceback and no values
        return
    st.caption(f"슬롯 {slot} · 상태 {state['last_run']['kind']} · 기준 장 {state['latest']['session']} · 이 슬롯만 표시합니다.")
    if experiment.is_adaptive(state):
        eff = experiment.effective(state)
        if eff["end"]:
            st.error(f"슬롯 종료: {eff['end']['reason']}")
        elif eff["stop"]:
            st.error(f"비상 정지 중 (장 {eff['stop']['session']}): 신규 매수와 최적화를 멈추고 보유분은 청산 규칙대로 처리합니다. "
                     "해제는 USER 재개 입력 파일이 필요합니다.")
        else:
            st.info(f"현재 단계: {eff['stage_ko']}")
    if rows:
        last = rows[-1]
        a, b, c = st.columns(3)
        a.metric("평가액 (원화, 환율 효과 포함)", krw(last["value_krw"]))
        a.metric("평가액 (달러)", usd(last["value_usd"]))
        b.metric("손익 (원화)", signed_krw(last["gain_krw"]))
        b.metric("손익 (달러)", signed_usd(last["gain_usd"]))
        c.metric("시작 대비 (원화)", pct(last["return_krw"]))
        c.metric("시작 대비 (달러)", pct(last["return_usd"]))
        st.caption("시작 자금 3,000,000원을 한 번 환전한 뒤 추가 입금이 없으므로, 시작 대비 변화가 시간가중수익률과 같습니다.")
    else:
        st.info("평가할 수 있는 장이 아직 없습니다.")
    tabs = st.tabs(["평가금액 추이", "보유 종목", "거래 내역", "경보"])
    with tabs[0]:
        if rows:
            unit = st.radio("통화", ["달러", "원화"], horizontal=True, key="x_unit")
            key = "usd" if unit == "달러" else "krw"
            data = [{"session": r["session"], "amount": float(r[f"value_{key}"])} for r in rows]
            st.altair_chart(alt.Chart(alt.Data(values=data)).mark_line(point=True).encode(
                x=alt.X("session:T", title="장"), y=alt.Y("amount:Q", title="달러" if key == "usd" else "원", scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip("session:T", title="장"), alt.Tooltip("amount:Q", title="평가액", format=",.2f")]),
                use_container_width=True)
        else:
            st.info("평가할 수 있는 장이 아직 없습니다.")
    with tabs[1]:
        last_session = experiment.sessions(state)[-1] if experiment.sessions(state) else None
        held = experiment.holdings(state, closes.get(last_session, {}) if last_session else {})
        if held:
            st.table([{"티커": h["symbol"], "수량": f"{h['qty']:,.6f}".rstrip("0").rstrip("."), "매수일": h["entry_session"] or "-",
                       "현재가": usd(h["price"]), "평가액": usd(h["value"]), "손익": signed_usd(h["gain"]),
                       "비중": "-" if h["share"] is None else f"{h['share'] * 100:.2f}%"} for h in held])
        else:
            st.info("보유 종목이 없습니다.")
        orders = experiment.pending(state)
        if orders:
            st.markdown("**다음 시가 주문 예정**: " + ", ".join(f"{o['symbol']} {o['side']} ({o['reason_ko']})" for o in orders))
    with tabs[2]:
        done = experiment.trades(state)
        if done:
            st.table([{"장": t["session"], "티커": t["symbol"], "구분": "매수" if t["side"] == "BUY" else "매도", "수량": t["qty"],
                       "체결가": usd(experiment.Decimal(t["price"])), "수수료": usd(experiment.Decimal(t["fee"])), "사유": t["reason_ko"]}
                      for t in done])
        else:
            st.info("거래가 아직 없습니다.")
    with tabs[3]:
        items = experiment.alerts(state)
        if not items:
            st.success("경보 없음")
        for item in items:
            st.markdown(f"- **{item['label']}** ({item['code']})" + (f" — {item['detail']}" if item["detail"] else ""))
    if experiment.is_adaptive(state):
        adaptive_tabs(st, alt, reader, slot, state)


def main(reader=None) -> None:
    import altair as alt
    import streamlit as st

    st.set_page_config(page_title="AutoTrader 모의운용", layout="wide")
    st.markdown(HIDE_TOOLBAR, unsafe_allow_html=True)
    account = st.radio("계좌", ACCOUNTS, horizontal=True, key="account")  # one account at a time; never shown together
    try:
        reader = reader or GitHubReader(st.secrets["OPS_READ_TOKEN"], st.secrets.get("OPS_MODE", "synthetic"))
    except Exception:
        st.error("데이터를 읽지 못했습니다. 설정과 토큰 권한을 확인하세요.")
        return
    if account == ACCOUNTS[1]:
        experiment_page(st, alt, reader)
        return
    st.title("AutoTrader 모의운용")
    st.warning(perf.NOTICE + " (본인 전용 화면, G4 ANNEX_11). 열 때마다 새로 계산하며 어디에도 저장하지 않습니다.")
    try:
        data = load_all(reader)
        view = check_screen(build_view(data["latest"], data["record"], data["last_run"]))
        rows = perf.daily(data["states"], data["records"])
    except Exception:
        st.error("데이터를 읽지 못했습니다. 설정과 토큰 권한을 확인하세요.")  # X-1: no traceback and no values
        return
    summary(st, rows)
    tabs = st.tabs(["평가금액 추이", "일별 손익 달력", "목표 대 현재 비중", "보유 종목", "종목별 주가", "경보·일정·입금", "운영 상태"])
    with tabs[0]:
        if rows:
            value_chart(st, alt, rows)
        else:
            st.info("평가할 수 있는 장이 아직 없습니다.")
    with tabs[1]:
        calendar_chart(st, alt, perf.calendar_days(data["states"], rows))
    with tabs[2]:
        if data["record"] is not None and view.get("POINT_IN_TIME_STATUS") == "COMPUTED_ON_OPEN":
            weight_chart(st, alt, perf.weights(data["latest"], data["record"]))
        else:
            st.info("마지막 장의 가격이 없어 현재 비중을 계산하지 못했습니다.")
    with tabs[3]:
        holdings_table(st, perf.holdings(data["latest"], data["record"]) if data["record"] is not None else [])
    with tabs[4]:
        price_chart(st, alt, perf.price_lines(data["states"], data["records"]))
    with tabs[5]:
        todo_and_schedule(st, data, datetime.now(timezone.utc))
    with tabs[6]:
        for label, text in render_rows(view):
            st.markdown(f"**{label}**: {text}")


if __name__ == "__main__":
    main()
