"""AutoTrader Phase 7 shadow dashboard (Streamlit; G4 ANNEX_2, ANNEX_3). Deployed from the public code-only repository with the app set to
private; the USER is the only viewer. Point-in-time values only, computed on every page load; no chart, history, file export, URL
parameter, cache on disk or value in a log or error message."""
from __future__ import annotations

try:  # inside AutoTrader (tests, G3 checks)
    from track_c.ops.dashboard.reader import GitHubReader
    from track_c.ops.dashboard.view import build_view, check_screen, render_rows
except ImportError:  # the public repository holds these files side by side
    from reader import GitHubReader
    from view import build_view, check_screen, render_rows


def load(reader) -> dict:
    state = reader.state()
    session = state.get("last_processed_session")
    digest = state.get("input_snapshot_sha256", {}).get(session) if session else None
    return build_view(state, reader.record(digest) if digest else None, reader.last_run_time_utc())


def main(reader=None) -> None:
    import streamlit as st

    st.set_page_config(page_title="AutoTrader 모의운용", layout="centered")
    st.title("AutoTrader 모의운용 (지금 시점)")
    try:
        reader = reader or GitHubReader(st.secrets["OPS_READ_TOKEN"], st.secrets.get("OPS_MODE", "synthetic"))
        view = check_screen(load(reader))
    except Exception:
        st.error("데이터를 읽지 못했습니다. 설정과 토큰 권한을 확인하세요.")  # X-1: no traceback and no values
        return
    for label, text in render_rows(view):
        st.markdown(f"**{label}**: {text}")
    st.caption("열 때마다 새로 계산합니다. 과거 값과 내려받기 기능은 없습니다.")


if __name__ == "__main__":
    main()
