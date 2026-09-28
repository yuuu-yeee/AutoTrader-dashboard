# AutoTrader-dashboard

Phase 7 모의운용 대시보드 코드만 있는 공개 저장소다. 원본은 비공개 저장소 AutoTrader의 `track_c/ops/dashboard`이고, 이 저장소는 자동 복사본이다.

- 데이터, 상태, 비밀값, 계좌 정보는 이 저장소에 영구히 두지 않는다 (G4 ANNEX_3 I-2).
- 앱은 Streamlit Community Cloud에서 비공개로 배포한다. 보는 사람은 USER 한 명이다.
- 데이터 읽기는 USER가 Streamlit Secrets에 넣은 읽기 전용 토큰(`OPS_READ_TOKEN`)으로만 한다.
- 모의운용 참고치 화면(G4 ANNEX_11, USER 결정 2026-09-28): 평가금액 추이, 손익, 시간가중수익률, 보유 종목과 가격을 화면을 열 때 메모리에서만 계산한다. 어디에도 저장하지 않고 내려받기 기능은 없다. 모의운용 참고치이며 전략 평가가 아니다.
- 실험 계좌 화면(EXPERIMENT_ACCOUNT_CONTRACT_V2): 맨 위에서 계좌를 고르고, 실험 계좌 안에서는 슬롯 하나씩만 본다. EXPERIMENTAL_PAPER_NON_CLAIM — 검증되지 않은 탐색 실험이며 연구 증거나 실제자금 근거로 쓰지 않는다. 두 계좌나 여러 슬롯을 함께 계산하는 화면은 없다.
