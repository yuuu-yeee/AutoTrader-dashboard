# AutoTrader-dashboard

Phase 7 모의운용 대시보드 코드만 있는 공개 저장소다. 원본은 비공개 저장소 AutoTrader의 `track_c/ops/dashboard`이고, 이 저장소는 자동 복사본이다.

- 데이터, 상태, 비밀값, 계좌 정보는 이 저장소에 영구히 두지 않는다 (G4 ANNEX_3 I-2).
- 앱은 Streamlit Community Cloud에서 비공개로 배포한다. 보는 사람은 USER 한 명이다.
- 데이터 읽기는 USER가 Streamlit Secrets에 넣은 읽기 전용 토큰(`OPS_READ_TOKEN`)으로만 한다.
- 화면은 지금 시점 값만 보여 준다. 과거 값과 내려받기 기능은 없다.
