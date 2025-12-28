# ============================================================
# VELLA V7 — app.py
# (CFG 기준서 기반, 초기 골격)
# ============================================================

# ============================================================
# VELLA V7 — CFG INPUT
# SOURCE: V7 CFG CONSTITUTION (SINGLE SOURCE OF TRUTH)
# ============================================================

CFG = {

    # =====================================================
    # [ STEP 1 ] 거래 대상 · 자본 · 손실 한계
    # ROLE: ENGINE LIMIT / CAPITAL BOUNDARY
    # =====================================================

    "01_TRADE_SYMBOL": "TIAUSDT",      # 01 TRADE_SYMBOL
    # 설명: 거래 종목 (선물 심볼)
    # 추천값: "TIAUSDT"
    # 튜닝의미: 종목 교체 시 엔진 재사용


    "02_CAPITAL_BASE_USDT": 60,        # 02 CAPITAL_BASE_USDT
    # 설명: 기준 투자금 (포지션 사이즈 계산 기준)
    # 단위: USDT
    # 추천값: 60
    # 의미: 전략 성능 비교 기준선 고정


    "03_CAPITAL_USE_FIXED": True,      # 03 CAPITAL_USE_FIXED
    # 설명: 항상 고정 금액 사용 여부
    # 추천값: True
    # 효과: 잔고 변동 → 전략 성능 오염 방지


    "04_CAPITAL_MAX_LOSS_PCT": 10.0,   # 04 CAPITAL_MAX_LOSS_PCT
    # 설명: 엔진 전체 기준 누적 손실 한계 (%)
    # 기준: CAPITAL_BASE_USDT
    #
    # 계산:
    # (실현 + 미실현 손익)
    # ≤ -CAPITAL_BASE_USDT * (CAPITAL_MAX_LOSS_PCT / 100)
    #
    # 의미:
    # cfg에서 정한 % 손실 도달 시
    # → 엔진 전체 거래 즉시 중단
    #
    # 규칙:
    # - 주문/포지션 단위 ❌
    # - 엔진 전체 ⭕
    # - 재시작해도 리셋 ❌ (STATE 유지)
    # - 수동 리셋만 허용
    #
    # 로그:
    # "ENGINE_MAX_LOSS_HIT"



    # =====================================================
    # [ STEP 2 ] 엔진 / 실행 스위치
    # ROLE: ENGINE MASTER SWITCH
    # =====================================================

    "05_ENGINE_ENABLE": True,            # 05 ENGINE_ENABLE
    # 설명: 엔진 마스터 스위치
    # 추천값: True
    # 효과: systemd 유지 + 거래만 즉시 중단

    "06_ENTRY_CANDIDATE_ENABLE": True,   # 06 ENTRY_CANDIDATE_ENABLE
    # 설명: 후보 생성 ON/OFF
    # 추천값: True
    # 효과: 분석·로그만 남기기 가능

    "07_ENTRY_EXEC_ENABLE": True,        # 07 ENTRY_EXEC_ENABLE
    # 설명: 실제 주문 실행 허용 여부
    # 추천값: True
    # 효과: “후보는 쌓되 주문 차단” 가능


    # =====================================================
    # [ STEP 3 ] 후보 생성 (SIMPLE & WIDE)
    # ROLE: CANDIDATE GENERATOR
    # =====================================================

    "08_CAND_BODY_BELOW_EMA": True,     # 08 CAND_BODY_BELOW_EMA
    # 후보결정:
    # “봉이 진행 중일 때, 가격이 EMA9 아래를 ‘실제 침투’한 순간 후보 확정”
    #
    # ❗ 시장 판단 ❌
    # ❗ 비트 판단 ❌
    # ❗ 필터 ❌
    # → “가능성 있는 놈은 전부 후보”


    # =====================================================
    # [ STEP 4 ] BTC SESSION BIAS
    # ROLE: EXECUTION GATE — MARKET CONTEXT
    # =====================================================

    "09_BTC_SESSION_BIAS_ENABLE": False,   # 09 BTC_SESSION_BIAS_ENABLE
    # 설명: BTC 일봉 기준가 대비 하락일 때만 실행 허용
    # 추천값: True

    # HARD SPEC (고정)
    # BTC_SESSION_TIMEFRAME = "1D"
    # BTC_SESSION_TIMEZONE  = "UTC"
    # BTC_SESSION_OPEN_TIME = "00:00"


    # =====================================================
    # [ STEP 5 ] 시장이 ‘살아 있는가?’ (EMA 경사도)
    # ROLE: EXECUTION GATE — MARKET ACTIVITY
    # =====================================================

    "10_EMA_SLOPE_MIN_PCT": 0.0,      # 10 EMA_SLOPE_MIN_PCT
    # 설명: EMA9의 기울기(변화율)가 이 값 이상일 때만 실행을 허용한다.
    # 추천값: 0.05
    # 추천범위: 0.03 ~ 0.15
    # 의미 (중1)
    # 값이 작다 → 살짝만 움직여도 “움직이는 장”
    # 값이 크다 → 확실히 기울 때만 실행
    # 사유: 횡보장에서 쓸데없는 재진입 차단
    # 성격: 필터 ❌ / 실행 허용 조건 ⭕

    "11_EMA_SLOPE_LOOKBACK_BARS": 1,   # 11 EMA_SLOPE_LOOKBACK_BARS
    # 설명: EMA 기울기를 계산할 때 최근 몇 개 봉을 기준으로 볼지 정한다.
    # 추천값: 3
    # 추천범위: 2 ~ 5
    # 의미 (중1)
    # 2 → 최근 움직임에 민감 (빠름)
    # 5 → 흐름 위주 (안정)
    # 사유: 순간 튐(노이즈) 제거


    # =====================================================
    # [ STEP 6 ] 가격 행동 확인 (속도 vs 확신)
    # ROLE: EXECUTION GATE — PRICE CONFIRMATION
    # =====================================================

    "12_EXECUTION_MIN_PRICE_MOVE_PCT": 0.0,   # 12 EXECUTION_MIN_PRICE_MOVE_PCT
    # 설명:
    # 후보가 생성된 이후,
    # 가격이 후보 기준점 대비 최소 이 퍼센트만큼
    # “추가로 더 이동했을 때만” 실행을 허용한다.
    # 추천값: 0.05
    # 추천범위: 0.03 ~ 0.15
    # 사유:
    # · EMA 침투 직후 미세한 흔들림에서의 실행 방지
    # · “진짜로 움직이기 시작했는지”를 가격으로 확인
    # 성격:
    # · 필터 ❌
    # · 실행 확신 게이트 ⭕
    # 직관:
    # 👉 “후보가 생긴 뒤, 이전 가격보다 조금이라도 더 내려가면 실행”

    "13_EXECUTION_ONLY_ON_NEW_LOW": False,     # 13 EXECUTION_ONLY_ON_NEW_LOW
    # 설명:
    # 후보가 생성된 이후,
    # 직전 저점을 실제로 갱신했을 때만 실행을 허용한다.
    # 추천값: False
    # 추천범위: True / False
    # 사유:
    # · 횡보장에서 위·아래 흔들림 제거
    # · ‘떨어지고 있다’는 사실을 구조적으로 확인
    # 성격:
    # · SHORT 전용 전략에서 매우 강력한 확신 게이트

    # --------------------------------------------------
    # [ 12 / 13 실행 규칙 — OR 규칙 (중요) ]
    # --------------------------------------------------
    # - 두 옵션은 항상 OR 규칙만 허용한다.
    # - AND 조건은 설계 위반이다.
    # 이유:
    # - 12 = 속도 확보
    # - 13 = 확신 확보


    # =====================================================
    # [ STEP 7 ] 실행 속도 제어 (최소 쿨다운 보험)
    # ROLE: EXECUTION TEMPO CONTROL
    # =====================================================

    "14_STATE_COOLDOWN_ENABLE": False,     # 14 STATE_COOLDOWN_ENABLE
    # 설명: RANGE / TREND 상태에 따라
    #       실행 쿨다운을 다르게 적용할지 여부
    #
    # 핵심 전제 (중요):
    # · RANGE / TREND 상태는
    #   별도의 시장 상태 모듈이 아니다.
    # · **EMA_SLOPE_MIN_PCT / EMA_SLOPE_LOOKBACK_BARS**
    #   계산 결과를 그대로 사용해 판단한다.
    # · EMA 경사도가 약하면 → RANGE
    #   EMA 경사도가 뚜렷하면 → TREND로 간주한다.
    #
    # 질문 형태 설명:
    # “EMA가 거의 움직이지 않는 횡보장과,
    #  EMA가 분명히 기울어진 추세장에서
    #  쿨다운을 똑같이 쓰는 게 맞을까?”
    #
    # 추천값: True
    #
    # 효과:
    # · RANGE(횡보) 구간에서는
    #   → 연타·미세 흔들림 진입을 강하게 억제
    # · TREND(추세) 구간에서는
    #   → 기회를 끊지 않고 유지
    #
    # 동작 방식:
    # · True  → EMA 경사도 기준으로
    #          RANGE 시 15번,
    #          TREND 시 16번 쿨다운 적용
    # · False → 시장 상태 구분 없이
    #          항상 동일한 쿨다운만 사용


    "15_COOLDOWN_RANGE_BARS": 0,          # 15 COOLDOWN_RANGE_BARS
    # 설명: EMA 경사도가 기준 미만일 때
    #       (RANGE, 횡보로 판단될 경우)
    #       적용되는 실행 쿨다운
    #
    # 의미 (중1):
    # “EMA가 거의 기울지 않는 횡보장에서는
    #  얼마나 쉬었다가 다시 들어갈까?”
    #
    # 추천값: 4
    # 추천범위: 2 ~ 6
    # · 2: 횡보에서도 다시 빨리 진입 (공격적)
    # · 4: 횡보 연타를 확실히 줄이는 균형값
    # · 6: 횡보 구간은 거의 건드리지 않음 (보수)
    #
    # 체감 설명:
    # · 값 4 = 5분봉 4개 = 약 20분 쉼
    #
    # 효과:
    # · 횡보 구간에서의 연타·미세 흔들림 실행을 억제
    # · 실행 이후 폭주를 막는 핵심 레버
    #
    # 주의 (설계 고정):
    # · 이 옵션은 필터가 아니다.
    # · 후보 생성을 막지 않는다.
    # · 실행 가능 판정 이후,
    #   실행 간격을 조절하는 **보험 장치**다.


    "16_COOLDOWN_TREND_BARS": 0,          # 16 COOLDOWN_TREND_BARS
    # 설명: EMA 경사도가 기준 이상일 때
    #       (TREND, 추세로 판단될 경우)
    #       적용되는 실행 쿨다운
    #
    # 의미 (중1):
    # “EMA가 분명히 기울어 있는 추세장에서는
    #  얼마나 빨리 다시 들어갈까?”
    #
    # 추천값: 1
    # 추천범위: 0 ~ 1
    # · 0: 청산 직후 다음 봉 바로 재진입 가능
    #      “추세는 끊기지 않는다” 철학
    #      가장 공격적
    # · 1: 한 봉(5분) 쉬고 재진입
    #      휩쏘 한 번 거르고 들어가는 안정형
    #
    # 효과:
    # · 추세 구간에서 기회를 끊지 않고 유지
    #
    # 주의 (설계 고정):
    # · 이 옵션은 필터가 아니다.
    # · 후보 생성을 막지 않는다.
    # · 실행 가능 판정 이후,
    #   재진입 속도를 조절하는 **실행 템포 옵션**이다.


    # =====================================================
    # [ STEP 8 ] 실행 안전장치 (실매매 보호)
    # ROLE: EXECUTION SAFETY GUARD
    # =====================================================
    # >>> “이 주문을 지금 이 가격·이 환경에서 실행해도 되나?”
    # → 실행 단위 판단임을 더 명확히 함

    "17_ENTRY_MAX_PER_CYCLE": 5,        # 17 ENTRY_MAX_PER_CYCLE
    # 설명: 한 사이클에서 허용하는 최대 엔트리 수
    # 추천값: 1
    # 역할:
    # · 단기 폭주 방지
    # · 로직 오류 시 연속 주문 차단

    "18_MAX_ENTRIES_PER_DAY": 20,        # 18 MAX_ENTRIES_PER_DAY
    # 설명: 하루 최대 엔트리 수
    # 추천값: 20
    # 역할:
    # · 비정상 시장/버그 상황에서
    #   손실을 “횟수 기준”으로 제한

    "19_DATA_STALE_BLOCK": False,         # 19 DATA_STALE_BLOCK
    # 설명: 가격 데이터가 일정 시간 이상 갱신되지 않으면 실행 차단
    # 추천값: True
    # 사유: 지연·누락 데이터로 인한 오체결/미체결 사고 방지
    # 역할: 후보 유지 / 실행만 차단 (EXECUTION SAFETY)

    "20_EXECUTION_SPREAD_GUARD_ENABLE": False,  # 20 EXECUTION_SPREAD_GUARD_ENABLE
    # 설명: 실행 시점 스프레드가 과도하면 실행 차단
    # 추천값: True
    # 사유: 슬리피지·호가 공백 구간에서의 체결 품질 보호
    # 역할: 후보 유지 / 실행만 차단 (EXECUTION SAFETY)


    # =====================================================
    # [ STEP 9 ] 재진입 관리 · 후보 정리
    # ROLE: ENGINE SUPPORT — REENTRY / CANDIDATE HYGIENE
    # =====================================================

    "21_ENTRY_COOLDOWN_BARS": 0,        # 21 ENTRY_COOLDOWN_BARS
    # 설명: 엔트리 후 최소 대기 봉
    # 추천값: 2
    # 효과: 횡보 연타 폭주 방지

    "22_ENTRY_COOLDOWN_AFTER_EXIT": 0,  # 22 ENTRY_COOLDOWN_AFTER_EXIT
    # 설명: 청산 직후 재진입 대기
    # 추천값: 1
    # 효과: 휩쏘 감소

    "23_REENTRY_SAME_REASON_BLOCK": False,  # 23 REENTRY_SAME_REASON_BLOCK
    # 설명: 동일 사유 반복 진입 차단
    # 추천값: True
    # 효과: “새 정보”만 진입 허용

    "24_ENTRY_LOOKBACK_BARS": 1,        # 24 ENTRY_LOOKBACK_BARS
    # 설명: 과거 N봉 재진입 탐색 범위
    # 추천값: 5
    # 효과: 연타 억제 강도 조절

    "25_REENTRY_PRICE_TOL_PCT": 100,   # 25 REENTRY_PRICE_TOL_PCT
    # 설명: “같은 자리”로 간주하는 가격 허용 오차 비율
    # 단위: %
    # 추천값: 0.15
    # 효과: 횡보장에서 같은 자리 반복 진입 억제

    "26_CAND_POOL_TTL_BARS": 999,         # 26 CAND_POOL_TTL_BARS
    # 설명: 후보 유지 최대 봉 수(TTL)
    # 추천값: 6
    # 효과: 오래된 후보 자동 폐기 / 후보 풀 정리

    "27_CAND_POOL_MAX_SIZE": 999,         # 27 CAND_POOL_MAX_SIZE
    # 설명: 최대 후보 개수
    # 추천값: 3
    # 효과: 후보 과잉 방지

    "28_CAND_MIN_GAP_BARS": 0,          # 28 CAND_MIN_GAP_BARS
    # 설명: 후보 생성 최소 간격
    # 추천값: 1
    # 효과: 후보 중복 완충



    # =====================================================
    # [ STEP 10 ] 변동성 보호 (보조 안전)
    # ROLE: ENGINE SUPPORT — MANUAL SAFETY
    # =====================================================

    "29_VOLATILITY_BLOCK_ENABLE": False,     # 29 VOLATILITY_BLOCK_ENABLE
    # 설명: 과도한 변동성 구간에서 “실행만” 차단할지 여부
    # 추천값: False
    #
    # 역할 (명확화):
    # · 후보 생성에는 **절대 영향 없음**
    # · 실행 판단 단계에서만 작동하는 “보조 차단 게이트”
    #
    # 사용 의도 (중요):
    # · BTC_REGIME / EMA_SLOPE와 **동급 핵심 필터가 아님**
    # · 시장 구조 판단용 ❌
    # · “오늘은 데이터도 불안하고, 장도 이상하다” 같은
    #   **운영자 개입 상황에서만 사용하는 수동 안전장치**
    #
    # 설계 고정 문장:
    # · 이 옵션은 기본 OFF를 전제로 한다.
    # · 이 옵션을 상시 ON으로 쓰기 시작하면,
    #   V7의 “필터 최소화 원칙”을 위반한 것이다.

    "30_VOLATILITY_MAX_PCT": 2.5,            # 30 VOLATILITY_MAX_PCT
    # 설명: 변동성이 이 퍼센트 이상일 경우 실행 차단
    # 추천값: 2.5
    # 단위: %
    #
    # 작동 조건:
    # · VOLATILITY_BLOCK_ENABLE = True 일 때만 유효
    # · 실행 판단 단계에서만 체크
    #
    # 주의 (설계 고정):
    # · 이 값은 “시장 판단 기준”이 아니다.
    # · 단기 급변·데이터 튐·이상 캔들에 대한
    #   **임시 보호선**으로만 사용한다.


    # =====================================================
    # [ STEP 11 ] 로그 / 관측 전용
    # ROLE: OBSERVABILITY ONLY
    # =====================================================

    "31_LOG_CANDIDATES": True,     # 31 LOG_CANDIDATES
    # 설명: 후보 생성 로그
    # 추천값: True
    # 효과: 튜닝의 출발점

    "32_LOG_EXECUTIONS": True,     # 32 LOG_EXECUTIONS
    # 설명: 주문·체결 로그
    # 추천값: True
    # 효과: 실전 단일 진실


    # =====================================================
    # [ STEP 12 ] FAIL-SAFE / 엔진 보호
    # ROLE: ENGINE FAIL-SAFE
    # =====================================================

    "33_ENGINE_FAIL_FAST_ENABLE": True,     # 33 ENGINE_FAIL_FAST_ENABLE
    # 설명: 치명 오류 발생 시 즉시 엔진 중단 여부
    # 추천값: True
    # 효과:
    # · 조용히 망가진 상태로 계속 도는 것 방지
    # · 이상 징후 발생 즉시 정지 → 원인 추적 가능

    "34_ENGINE_FAIL_NOTIFY_ONLY": True,     # 34 ENGINE_FAIL_NOTIFY_ONLY
    # 설명: 실패 시 알림만 하고 자동 재시도 금지
    # 추천값: True
    # 효과:
    # · 자동 복구 폭주 방지
    # · 사람 개입 전제 운영






}



# ============================================================
# BTC_CTX BUILDER — REAL BINANCE DATA (UTC 00:00)
# SOURCE: V7 CFG CONSTITUTION / STEP 4
# ============================================================

from binance.client import Client
from datetime import datetime, timezone

def build_btc_ctx_real(client: Client, logger=print):
    """
    btc_ctx:
      - current: BTCUSDT 현재가
      - open_1d_utc: BTCUSDT 1D UTC 시가 (00:00)
    """

    symbol = "BTCUSDT"
    interval = Client.KLINE_INTERVAL_1DAY

    # 1) 현재가
    ticker = client.get_symbol_ticker(symbol=symbol)
    current = float(ticker["price"])

    # 2) 오늘 UTC 00:00 일봉 시가
    klines = client.get_klines(symbol=symbol, interval=interval, limit=2)
    if not klines or len(klines) < 1:
        raise RuntimeError("BTC_CTX_BUILD_FAIL: NO_KLINES")

    # 가장 최신 일봉의 시가 = UTC 00:00 기준
    open_1d_utc = float(klines[-1][1])

    logger(f"BTC_CTX_BUILD: current={current} open_1d_utc={open_1d_utc}")

    return {
        "current": current,
        "open_1d_utc": open_1d_utc,
    }





# ============================================================
# [ STEP 1 ] 거래 대상 · 자본 · 손실 한계
# ROLE: ENGINE LIMIT / CAPITAL BOUNDARY
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_1_engine_limit(cfg, state, logger=print):
    """
    STEP 1 — ENGINE LIMIT / CAPITAL BOUNDARY
    - 판단 ❌ / 체크만 ⭕
    - 실패 시 즉시 엔진 중단
    """

    # --------------------------------------------------------
    # CFG 존재 검증 (조용히 통과 금지)
    # --------------------------------------------------------
    required_keys = [
        "01_TRADE_SYMBOL",
        "02_CAPITAL_BASE_USDT",
        "03_CAPITAL_USE_FIXED",
        "04_CAPITAL_MAX_LOSS_PCT",
    ]
    for k in required_keys:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP1: {k}")

    # --------------------------------------------------------
    # 01 TRADE_SYMBOL
    # --------------------------------------------------------
    trade_symbol = cfg["01_TRADE_SYMBOL"]
    if not isinstance(trade_symbol, str) or not trade_symbol:
        raise RuntimeError("STEP1_INVALID_TRADE_SYMBOL")

    # --------------------------------------------------------
    # 02 CAPITAL_BASE_USDT
    # --------------------------------------------------------
    capital_base = cfg["02_CAPITAL_BASE_USDT"]
    if not isinstance(capital_base, (int, float)) or capital_base <= 0:
        raise RuntimeError("STEP1_INVALID_CAPITAL_BASE_USDT")

    # --------------------------------------------------------
    # 03 CAPITAL_USE_FIXED
    # (STEP 1에서는 값 존재만 확인, 실제 사용은 이후 STEP)
    # --------------------------------------------------------
    capital_use_fixed = cfg["03_CAPITAL_USE_FIXED"]
    if not isinstance(capital_use_fixed, bool):
        raise RuntimeError("STEP1_INVALID_CAPITAL_USE_FIXED")

    # --------------------------------------------------------
    # 04 CAPITAL_MAX_LOSS_PCT
    # ENGINE 전체 기준 누적 손실 한계
    # (실현 + 미실현 손익)
    # --------------------------------------------------------
    max_loss_pct = cfg["04_CAPITAL_MAX_LOSS_PCT"]
    if not isinstance(max_loss_pct, (int, float)) or max_loss_pct <= 0:
        raise RuntimeError("STEP1_INVALID_CAPITAL_MAX_LOSS_PCT")

    realized_pnl   = state.get("realized_pnl", 0.0)
    unrealized_pnl = state.get("unrealized_pnl", 0.0)
    total_pnl = realized_pnl + unrealized_pnl

    max_allowed_loss = -capital_base * (max_loss_pct / 100.0)

    if total_pnl <= max_allowed_loss:
        logger("ENGINE_MAX_LOSS_HIT")
        return False

    # --------------------------------------------------------
    # PASS
    # --------------------------------------------------------
    logger("STEP1_PASS")
    return True


# ============================================================
# [ STEP 2 ] 엔진 / 실행 스위치
# ROLE: ENGINE MASTER SWITCH
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_2_engine_switch(cfg, logger=print):
    """
    STEP 2 — ENGINE MASTER SWITCH
    - 허용/차단 스위치만 판정
    - 후보/실행 로직 개입 ❌
    """

    required_keys = [
        "05_ENGINE_ENABLE",
        "06_ENTRY_CANDIDATE_ENABLE",
        "07_ENTRY_EXEC_ENABLE",
    ]
    for k in required_keys:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP2: {k}")

    for k in required_keys:
        if not isinstance(cfg[k], bool):
            raise RuntimeError(f"STEP2_INVALID_BOOL: {k}")

    if not cfg["05_ENGINE_ENABLE"]:
        logger("STEP2_DENY: ENGINE_ENABLE=False")
        return False

    logger(
        f"STEP2_PASS: "
        f"CANDIDATE_ENABLE={cfg['06_ENTRY_CANDIDATE_ENABLE']} "
        f"EXEC_ENABLE={cfg['07_ENTRY_EXEC_ENABLE']}"
    )
    return True


# ============================================================
# [ STEP 3 ] 후보 생성
# ROLE: CANDIDATE GENERATOR
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_3_generate_candidates(cfg, market, state, logger=print):
    """
    STEP 3 — CANDIDATE GENERATOR
    - 후보 생성만 수행
    - 실행/필터/판단 ❌
    """

    # CFG 존재 검증
    if "08_CAND_BODY_BELOW_EMA" not in cfg:
        raise RuntimeError("CFG_MISSING_KEY_STEP3: 08_CAND_BODY_BELOW_EMA")

    candidates = []

    if not cfg["08_CAND_BODY_BELOW_EMA"]:
        logger("STEP3_SKIP: CAND_BODY_BELOW_EMA=False")
        return candidates

    # ⚠️ 실제 EMA/가격 로직은 다음 단계
    # 지금은 “후보 생성 파이프라인이 살아 있는지”만 확인

    logger("STEP3_CANDIDATE_GENERATOR_READY")
    return candidates


# ============================================================
# [ STEP 4 ] BTC SESSION BIAS
# ROLE: EXECUTION GATE — MARKET CONTEXT
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_4_btc_session_bias(cfg, btc_ctx, logger=print):
    """
    STEP 4 — BTC SESSION BIAS
    - 후보는 유지
    - 실행만 허용/차단
    """

    # CFG 존재 검증
    if "09_BTC_SESSION_BIAS_ENABLE" not in cfg:
        raise RuntimeError("CFG_MISSING_KEY_STEP4: 09_BTC_SESSION_BIAS_ENABLE")

    # 비활성화 시 즉시 통과
    if not cfg["09_BTC_SESSION_BIAS_ENABLE"]:
        logger("STEP4_SKIP: BTC_SESSION_BIAS_DISABLE")
        return True

    # BTC 컨텍스트 필수화 (중요)
    if btc_ctx is None:
        logger("STEP4_DENY: BTC_CTX_NONE")
        return False

    for k in ("current", "open_1d_utc"):
        if k not in btc_ctx:
            raise RuntimeError(f"BTC_CTX_MISSING_KEY_STEP4: {k}")

        if not isinstance(btc_ctx[k], (int, float)):
            raise RuntimeError(f"BTC_CTX_INVALID_TYPE_STEP4: {k}")

    current = float(btc_ctx["current"])
    open_1d = float(btc_ctx["open_1d_utc"])

    # 기준 로그 (디버그/검증용)
    logger(f"STEP4_CHECK: current={current} open_1d_utc={open_1d}")

    # 실행 허용 조건 (단 하나)
    if current < open_1d:
        logger("STEP4_PASS: BTC_BELOW_1D_OPEN")
        return True

    logger("STEP4_DENY: BTC_SESSION_BIAS_DENY")
    return False


# ============================================================
# EMA_CTX BUILD
# SOURCE: V7 CFG CONSTITUTION (STEP 5 / STEP 7 공용)
# ============================================================

def build_ema_ctx(candles, ema_period=9, lookback=3):
    """
    ema_ctx:
      - slope_pct: 최근 lookback 기준 EMA 기울기(%)
    """
    if candles is None or len(candles) < ema_period + lookback:
        return None

    # EMA 계산
    def ema(values, period):
        k = 2 / (period + 1)
        e = values[0]
        for v in values[1:]:
            e = v * k + e * (1 - k)
        return e

    closes = [c["close"] for c in candles]
    ema_series = []
    for i in range(ema_period, len(closes) + 1):
        ema_series.append(ema(closes[:i], ema_period))

    if len(ema_series) < lookback + 1:
        return None

    e_now = ema_series[-1]
    e_prev = ema_series[-1 - lookback]
    if e_prev == 0:
        return None

    slope_pct = ((e_now - e_prev) / abs(e_prev)) * 100.0
    return {"slope_pct": slope_pct}



# ============================================================
# [ STEP 5 ] EMA SLOPE (MARKET ACTIVITY)
# ROLE: EXECUTION GATE — MARKET ACTIVITY
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_5_ema_slope(cfg, ema_ctx, logger=print):
    """
    STEP 5 — EMA SLOPE
    - 후보 유지
    - 실행만 허용/차단
    - CTX 배선 전(None) 단계에서는 READY로 통과
    """

    # --------------------------------------------------------
    # CFG 존재 검증
    # --------------------------------------------------------
    required_keys = [
        "10_EMA_SLOPE_MIN_PCT",
        "11_EMA_SLOPE_LOOKBACK_BARS",
    ]
    for k in required_keys:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP5: {k}")

    # --------------------------------------------------------
    # CTX 연결 전 단계 (STRAIGHT 배선 단계)
    # --------------------------------------------------------
    if ema_ctx is None:
        logger("STEP5_READY: EMA_CTX_NONE")
        return True

    # --------------------------------------------------------
    # CTX 구조 검증
    # --------------------------------------------------------
    if not isinstance(ema_ctx, dict):
        raise RuntimeError("EMA_CTX_INVALID_STEP5: NOT_DICT")

    slope_pct = ema_ctx.get("slope_pct")
    if not isinstance(slope_pct, (int, float)):
        raise RuntimeError("EMA_CTX_INVALID_STEP5: slope_pct")

    # --------------------------------------------------------
    # 기준 로그
    # --------------------------------------------------------
    logger(f"STEP5_CHECK: slope_pct={slope_pct:.4f}")

    # --------------------------------------------------------
    # 실행 허용 조건
    # --------------------------------------------------------
    if abs(slope_pct) >= cfg["10_EMA_SLOPE_MIN_PCT"]:
        logger("STEP5_PASS: EMA_SLOPE_OK")
        return True

    logger("STEP5_DENY: EMA_SLOPE_TOO_FLAT")
    return False







# ============================================================
# [ STEP 6 ] PRICE CONFIRMATION (12 / 13 OR)
# ROLE: EXECUTION GATE — PRICE CONFIRMATION
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_6_price_confirmation(cfg, price_ctx, logger=print):
    """
    STEP 6 — PRICE CONFIRMATION
    - 12 / 13 OR 규칙
    - 실행 허용/차단만 판정
    """

    for k in ["12_EXECUTION_MIN_PRICE_MOVE_PCT", "13_EXECUTION_ONLY_ON_NEW_LOW"]:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP6: {k}")

    # 연결 확인 단계
    if price_ctx is None:
        logger("STEP6_READY: PRICE_CTX_NONE")
        return True

    # price_ctx 예시:
    # {
    #   "move_pct": float,   # 후보 기준 대비 추가 이동 %
    #   "is_new_low": bool   # 직전 저점 갱신 여부
    # }

    cond_speed   = price_ctx.get("move_pct", 0.0) >= cfg["12_EXECUTION_MIN_PRICE_MOVE_PCT"]
    cond_confirm = price_ctx.get("is_new_low", False) if cfg["13_EXECUTION_ONLY_ON_NEW_LOW"] else False

    if cond_speed or cond_confirm:
        logger("STEP6_PASS: PRICE_CONFIRM_OK")
        return True

    logger("STEP6_DENY: PRICE_CONFIRM_FAIL")
    return False



# ============================================================
# [ STEP 7 ] 실행 속도 제어 (최소 쿨다운 보험)
# ROLE: EXECUTION TEMPO CONTROL
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_7_execution_cooldown(cfg, ema_ctx, logger=print):
    """
    STEP 7 — EXECUTION TEMPO CONTROL
    - 이 스텝은 실행 가능 상태를 TRUE로 만들 수 없다.
    - ‘얼마나 쉴지’(bars)만 결정한다.
    """

    required = [
        "14_STATE_COOLDOWN_ENABLE",
        "15_COOLDOWN_RANGE_BARS",
        "16_COOLDOWN_TREND_BARS",
        "10_EMA_SLOPE_MIN_PCT",  # RANGE/TREND 판정에 필요
    ]
    for k in required:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP7: {k}")

    # 연결 확인 단계
    if ema_ctx is None:
        logger("STEP7_READY: EMA_CTX_NONE")
        return 0

    # False면: 시장 상태 구분 없이 동일 쿨다운(여기서는 RANGE값을 단일값으로 사용)
    if not cfg["14_STATE_COOLDOWN_ENABLE"]:
        logger("STEP7_COOLDOWN_FIXED")
        return cfg["15_COOLDOWN_RANGE_BARS"]

    slope_pct = ema_ctx.get("slope_pct", 0.0)

    # EMA 경사도 기준 이상이면 TREND, 미만이면 RANGE
    if slope_pct >= cfg["10_EMA_SLOPE_MIN_PCT"]:
        logger("STEP7_COOLDOWN_TREND")
        return cfg["16_COOLDOWN_TREND_BARS"]

    logger("STEP7_COOLDOWN_RANGE")
    return cfg["15_COOLDOWN_RANGE_BARS"]



# ============================================================
# [ STEP 8 ] EXECUTION SAFETY GUARD
# ROLE: EXECUTION SAFETY GUARD
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_8_execution_safety_guard(cfg, safety_ctx, logger=print):
    """
    STEP 8 — EXECUTION SAFETY GUARD
    - 실행 단위 안전 차단만 수행
    - 실행 가능 상태를 TRUE로 만들 수 없다
    """

    required = [
        "17_ENTRY_MAX_PER_CYCLE",
        "18_MAX_ENTRIES_PER_DAY",
        "19_DATA_STALE_BLOCK",
        "20_EXECUTION_SPREAD_GUARD_ENABLE",
    ]
    for k in required:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP8: {k}")

    # 연결 확인 단계
    if safety_ctx is None:
        logger("STEP8_READY: SAFETY_CTX_NONE")
        return True

    # safety_ctx 예시:
    # {
    #   "entries_this_cycle": int,
    #   "entries_today": int,
    #   "data_stale": bool,
    #   "spread_ok": bool,
    # }

    if safety_ctx.get("entries_this_cycle", 0) >= cfg["17_ENTRY_MAX_PER_CYCLE"]:
        logger("STEP8_DENY: ENTRY_MAX_PER_CYCLE")
        return False

    if safety_ctx.get("entries_today", 0) >= cfg["18_MAX_ENTRIES_PER_DAY"]:
        logger("STEP8_DENY: MAX_ENTRIES_PER_DAY")
        return False

    if cfg["19_DATA_STALE_BLOCK"] and safety_ctx.get("data_stale", False):
        logger("STEP8_DENY: DATA_STALE")
        return False

    if cfg["20_EXECUTION_SPREAD_GUARD_ENABLE"] and not safety_ctx.get("spread_ok", True):
        logger("STEP8_DENY: SPREAD_GUARD")
        return False

    logger("STEP8_PASS: SAFETY_OK")
    return True



# ============================================================
# [ STEP 9 ] REENTRY / CANDIDATE HYGIENE
# ROLE: ENGINE SUPPORT — REENTRY / CANDIDATE HYGIENE
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_9_reentry_candidate_hygiene(cfg, reentry_ctx, logger=print):
    """
    STEP 9 — REENTRY / CANDIDATE HYGIENE
    - 실행 판단 결과를 TRUE로 만들 수 없다.
    - 이미 TRUE인 실행을 DELAY/BLOCK만 가능.
    """

    required = [
        "21_ENTRY_COOLDOWN_BARS",
        "22_ENTRY_COOLDOWN_AFTER_EXIT",
        "23_REENTRY_SAME_REASON_BLOCK",
        "24_ENTRY_LOOKBACK_BARS",
        "25_REENTRY_PRICE_TOL_PCT",
        "26_CAND_POOL_TTL_BARS",
        "27_CAND_POOL_MAX_SIZE",
        "28_CAND_MIN_GAP_BARS",
    ]
    for k in required:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP9: {k}")

    # 연결 확인 단계
    if reentry_ctx is None:
        logger("STEP9_READY: REENTRY_CTX_NONE")
        return True

    # 실제 로직은 다음 단계에서 연결
    logger("STEP9_PASS: HYGIENE_OK")
    return True



# ============================================================
# [ STEP 10 ] VOLATILITY PROTECTION (MANUAL SAFETY)
# ROLE: ENGINE SUPPORT — MANUAL SAFETY
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_10_volatility_protection(cfg, vol_ctx, logger=print):
    """
    STEP 10 — VOLATILITY PROTECTION
    - 실행 판단 결과를 TRUE로 만들 수 없다.
    - 이미 TRUE인 실행을 BLOCK만 가능.
    """

    for k in ["29_VOLATILITY_BLOCK_ENABLE", "30_VOLATILITY_MAX_PCT"]:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP10: {k}")

    # 연결 확인 단계
    if vol_ctx is None:
        logger("STEP10_READY: VOL_CTX_NONE")
        return True

    if not cfg["29_VOLATILITY_BLOCK_ENABLE"]:
        logger("STEP10_SKIP: VOL_BLOCK_DISABLED")
        return True

    if vol_ctx.get("vol_pct", 0.0) >= cfg["30_VOLATILITY_MAX_PCT"]:
        logger("STEP10_DENY: VOLATILITY_TOO_HIGH")
        return False

    logger("STEP10_PASS: VOL_OK")
    return True



# ============================================================
# [ STEP 11 ] OBSERVABILITY ONLY
# ROLE: OBSERVABILITY ONLY
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_11_observability(cfg, obs_ctx, logger=print):
    """
    STEP 11 — OBSERVABILITY ONLY
    - 판단/차단/허용 개입 ❌
    - 로그 출력 여부만 관리
    """

    for k in ["31_LOG_CANDIDATES", "32_LOG_EXECUTIONS"]:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP11: {k}")

    # 연결 확인 단계
    if obs_ctx is None:
        logger("STEP11_READY: OBS_CTX_NONE")
        return True

    if cfg["31_LOG_CANDIDATES"]:
        logger("STEP11_LOG: CANDIDATES_ENABLED")

    if cfg["32_LOG_EXECUTIONS"]:
        logger("STEP11_LOG: EXECUTIONS_ENABLED")

    return True



# ============================================================
# [ STEP 12 ] ENGINE FAIL-SAFE
# ROLE: ENGINE FAIL-SAFE
# SOURCE: V7 CFG CONSTITUTION
# ============================================================

def step_12_engine_fail_safe(cfg, fail_ctx, logger=print):
    """
    STEP 12 — ENGINE FAIL-SAFE
    - 치명 오류 시 엔진을 어떻게 멈출지 결정
    - 실행 판단을 TRUE로 만들 수 없다
    """

    for k in ["33_ENGINE_FAIL_FAST_ENABLE", "34_ENGINE_FAIL_NOTIFY_ONLY"]:
        if k not in cfg:
            raise RuntimeError(f"CFG_MISSING_KEY_STEP12: {k}")

    # 연결 확인 단계
    if fail_ctx is None:
        logger("STEP12_READY: FAIL_CTX_NONE")
        return True

    # fail_ctx 예시:
    # {
    #   "fatal_error": bool,
    #   "error_msg": str
    # }

    if fail_ctx.get("fatal_error", False):
        logger(f"STEP12_FATAL: {fail_ctx.get('error_msg', 'UNKNOWN')}")

        if cfg["33_ENGINE_FAIL_FAST_ENABLE"]:
            return False  # 즉시 엔진 중단

        # FAIL_FAST 비활성화 시
        if cfg["34_ENGINE_FAIL_NOTIFY_ONLY"]:
            logger("STEP12_NOTIFY_ONLY")
            return False

    return True







# ============================================================
# BINANCE REAL FETCHER (SPOT, PUBLIC)
# ============================================================

import requests
from datetime import datetime, timezone

class BinanceFetcher:
    BASE_URL = "https://api.binance.com"

    def get_current_price(self, symbol: str) -> float:
        url = f"{self.BASE_URL}/api/v3/ticker/price"
        r = requests.get(url, params={"symbol": symbol}, timeout=5)
        r.raise_for_status()
        return float(r.json()["price"])

    def get_utc_1d_open(self, symbol: str) -> float:
        """
        UTC 00:00 기준 일봉 시가
        """
        url = f"{self.BASE_URL}/api/v3/klines"
        params = {
            "symbol": symbol,
            "interval": "1d",
            "limit": 1
        }
        r = requests.get(url, params=params, timeout=5)
        r.raise_for_status()

        kline = r.json()[0]
        open_price = float(kline[1])  # 시가
        open_time = datetime.fromtimestamp(kline[0] / 1000, tz=timezone.utc)

        # 방어: UTC 00:00 아닌 데이터면 즉시 오류
        if not (open_time.hour == 0 and open_time.minute == 0):
            raise RuntimeError(f"BTC_1D_OPEN_NOT_UTC_00: {open_time.isoformat()}")

        return open_price



# ============================================================
# BTC CONTEXT BUILDER (REAL DATA, UTC)
# ============================================================

def build_btc_ctx(fetcher, logger=print):
    current_price = fetcher.get_current_price("BTCUSDT")
    open_1d_utc   = fetcher.get_utc_1d_open("BTCUSDT")

    logger(
        f"BTC_CTX_REAL: current={current_price} open_1d_utc={open_1d_utc}"
    )

    return {
        "current": current_price,
        "open_1d_utc": open_1d_utc,
    }













def app_run():
    print("VELLA V7 APP START")

    # STEP 1 단독 실행 모드
    state = {
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }

    ok = step_1_engine_limit(CFG, state)
    if not ok:
        print("ENGINE STOPPED AT STEP 1")
        return

    print("STEP 1 COMPLETE")


    # STEP 2
    if not step_2_engine_switch(CFG):
        print("ENGINE STOPPED AT STEP 2")
        return


     # STEP 3
    candidates = step_3_generate_candidates(CFG, market=None, state=state)
    print(f"STEP 3 COMPLETE: candidates={len(candidates)}")



    # ============================================================
    # BTC_CTX (REAL)
    # ============================================================
    from binance.client import Client

    btc_ctx = None  # 실패 시 STEP 4에서 자연스럽게 DENY

    try:
        client = Client(
            api_key="여기에_실제_BINANCE_API_KEY",
            api_secret="여기에_실제_BINANCE_API_SECRET",
        )

        btc_ctx = build_btc_ctx_real(client)

    except Exception as e:
        print(f"BINANCE_CLIENT_INIT_WARNING (IGNORED): {e}")
        # ❗ 엔진 중단 ❌
        # ❗ btc_ctx=None 유지



    # ============================================================
    # STEP 4
    # ============================================================
    if not step_4_btc_session_bias(CFG, btc_ctx):
        print("ENGINE STOPPED AT STEP 4")
        return

    print("STEP 4 COMPLETE")




    # STEP 5
    if not step_5_ema_slope(CFG, ema_ctx):
        print("ENGINE STOPPED AT STEP 5")
        return



    # STEP 6
    price_ctx = None  # 지금은 연결 확인용
    if not step_6_price_confirmation(CFG, price_ctx):
        print("ENGINE STOPPED AT STEP 6")
        return
    print("STEP 6 COMPLETE")


    # STEP 7
    ema_ctx = None  # 지금은 연결 확인용
    cooldown_bars = step_7_execution_cooldown(CFG, ema_ctx)
    print(f"STEP 7 COMPLETE: cooldown_bars={cooldown_bars}")



    # STEP 8
    safety_ctx = None  # 지금은 연결 확인용
    if not step_8_execution_safety_guard(CFG, safety_ctx):
        print("ENGINE STOPPED AT STEP 8")
        return
    print("STEP 8 COMPLETE")



    # STEP 9
    reentry_ctx = None  # 지금은 연결 확인용
    if not step_9_reentry_candidate_hygiene(CFG, reentry_ctx):
        print("ENGINE STOPPED AT STEP 9")
        return
    print("STEP 9 COMPLETE")



    # STEP 10
    vol_ctx = None  # 지금은 연결 확인용
    if not step_10_volatility_protection(CFG, vol_ctx):
        print("ENGINE STOPPED AT STEP 10")
        return
    print("STEP 10 COMPLETE")



    # STEP 11
    obs_ctx = None  # 지금은 연결 확인용
    if not step_11_observability(CFG, obs_ctx):
        print("ENGINE STOPPED AT STEP 11")
        return
    print("STEP 11 COMPLETE")



    # STEP 12
    fail_ctx = None  # 지금은 연결 확인용
    if not step_12_engine_fail_safe(CFG, fail_ctx):
        print("ENGINE STOPPED AT STEP 12")
        return
    print("STEP 12 COMPLETE")







if __name__ == "__main__":
    app_run()
