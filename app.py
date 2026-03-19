# ============================================================
# VELLA_MTF — LONG/SHORT UNIFIED ENGINE (BNBUSDT)
# BASE: BR8 (v8 SHORT)
# DONOR: BR7 LONG E1
# MTF: 15m regime filter + 5m entry/exit execution
# TP1 + TRAILING: BR8 concept inoculated (양방향 대칭)
# ============================================================

import os
import sys
import time
import signal
import logging
import requests
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Deque, Tuple
from collections import deque

# ============================================================
# CFG
# ============================================================

CFG = {
    # -------------------------
    # BASIC
    # -------------------------
    "01_TRADE_SYMBOL":          "BNBUSDT",
    "02_INTERVAL":              "5m",
    "02b_HTF_INTERVAL":         "15m",
    "03_CAPITAL_BASE_USDT":     1500.0,
    "04_LEVERAGE":              1,

    # -------------------------
    # SHORT ENTRY EMA (5m / FROZEN from BR8)
    # -------------------------
    "10_EMA_FAST":              8,
    "11_EMA_MID":               14,
    "12_EMA_ARENA":             30,
    "13_TOUCH_TOLERANCE":       0.002,
    "14_SLOPE_THRESHOLD":       0.002,
    "15_SWING_LOOKBACK":        4,
    "23_ENTRY2_ENABLE":         True,

    # -------------------------
    # LONG ENTRY EMA (5m / from BR7)
    # -------------------------
    "10L_EMA_FAST":             8,
    "11L_EMA_MID":              11,

    # -------------------------
    # HTF EMA (15m → 방향 필터 (Trend))
    # -------------------------
    "16_HTF_EMA_FAST":          5,
    "17_HTF_EMA_MID":           10,
    "18_HTF_EMA_SLOW":          30,

    # -------------------------
    # SLOPE FILTER (LONG E1 / from BR7)
    # -------------------------
    "60_FILTER_SLOPE_ENABLE":   True,
    "61_SLOPE_BARS":            2,
    "62_SLOPE_MIN_PCT":         0.003,

    # -------------------------
    # EXIT EMA (5m execution)
    # -------------------------
    "30_EXIT_FAST_EMA":         4,
    "31_EXIT_MID_EMA":          9,

    # -------------------------
    # EXIT THRESHOLD (15분봉 EMA 간격을 이용 EXIT을 "허용"하는 스위치)
    # -------------------------
    "70_SHORT_EXIT_THRESHOLD_PCT": 0.003,
    "71_LONG_EXIT_THRESHOLD_PCT":  0.003,

    # -------------------------
    # SL / TIMEOUT
    # -------------------------
    "40_SL_ENABLE":             True,
    "41_SL_PCT":                0.8,
    "50_TIMEOUT_EXIT_ENABLE":   False,
    "51_TIMEOUT_BARS":          60,

    # -------------------------
    # TP1 + TRAILING (BR8 concept / 양방향 공용)
    # -------------------------
    "80_TP1_ENABLE":            True,
    "81_TP1_PCT":               0.004,   # 0.004 = 0.4%
    "82_TP1_PARTIAL_PCT":       0.50,
    "83_TRAIL_ENABLE":          True,
    "84_TRAIL_CALLBACK_PCT":    0.004,

    # -------------------------
    # ENGINE
    # -------------------------
    "90_KLINE_LIMIT":           1500,
    "91_POLL_SEC":              5,
    "92_LOG_LEVEL":             "INFO",

    # -------------------------
    # 검증용 로그 토글 — 실가동 기본값 False
    # 93: E2 후보 출력
    # 94: EXIT 상세 판단 로그
    # -------------------------
    "93_E2_CANDIDATE_LOG_ENABLE":  False,
    "94_EXIT_DEBUG_LOG_ENABLE":    False,

    # -------------------------
    # SYNC retry(거래소 체결 → 포지션 조회 → 엔진 상태 동기화)
    # -------------------------
    "95_SYNC_RETRY_COUNT":      3,
    "96_SYNC_RETRY_DELAY_SEC":  1.0,
}

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(logging, CFG["92_LOG_LEVEL"], logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("VELLA_MTF")

# ============================================================
# BINANCE
# ============================================================

try:
    from binance.client import Client
    from binance.enums import SIDE_BUY, SIDE_SELL, ORDER_TYPE_MARKET
except Exception:
    Client = None
    SIDE_BUY = "BUY"
    SIDE_SELL = "SELL"
    ORDER_TYPE_MARKET = "MARKET"

BINANCE_FUTURES_KLINES = "https://fapi.binance.com/fapi/v1/klines"

def init_client() -> "Client":
    if Client is None:
        raise RuntimeError("python-binance missing")
    api_key    = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    return Client(api_key, api_secret)

def set_leverage(client: "Client", symbol: str, leverage: int) -> None:
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
    except Exception as e:
        log.error(f"set_leverage failed: {e}")

def fetch_klines_futures(symbol: str, interval: str, limit: int) -> Optional[List[Any]]:
    try:
        r = requests.get(
            BINANCE_FUTURES_KLINES,
            params={"symbol": symbol, "interval": interval, "limit": limit},
            timeout=5,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.error(f"fetch_klines_futures: {e}")
        return None

def fetch_klines_15m(symbol: str, limit: int) -> Optional[List[Any]]:
    return fetch_klines_futures(symbol, CFG["02b_HTF_INTERVAL"], limit)

def get_futures_lot_size(client: "Client", symbol: str) -> Optional[Dict[str, Decimal]]:
    try:
        info = client.futures_exchange_info()
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                for f in s["filters"]:
                    if f["filterType"] == "LOT_SIZE":
                        return {
                            "stepSize": Decimal(f["stepSize"]),
                            "minQty":   Decimal(f["minQty"]),
                            "maxQty":   Decimal(f["maxQty"]),
                        }
        return None
    except Exception as e:
        log.error(f"get_futures_lot_size: {e}")
        return None

# ============================================================
# QTY
# ============================================================

def calculate_quantity(qty_raw, lot: Dict[str, Decimal]) -> Optional[str]:
    if lot is None:
        return None
    qty_decimal = Decimal(str(qty_raw))
    step = lot["stepSize"]
    qty  = (qty_decimal / step).quantize(Decimal("1"), rounding=ROUND_DOWN) * step
    if qty < lot["minQty"]:
        return None
    if qty > lot["maxQty"]:
        qty = lot["maxQty"]
    precision = abs(step.as_tuple().exponent)
    return f"{qty:.{precision}f}"

def normalize_qty_str(qty_str: str, lot: Dict[str, Decimal]) -> Optional[str]:
    if lot is None:
        return None
    qty_decimal = Decimal(qty_str)
    step = lot["stepSize"]
    qty  = (qty_decimal / step).quantize(Decimal("1"), rounding=ROUND_DOWN) * step
    if qty < lot["minQty"]:
        return None
    if qty > lot["maxQty"]:
        qty = lot["maxQty"]
    precision = abs(step.as_tuple().exponent)
    return f"{qty:.{precision}f}"

# ============================================================
# PARTIAL QTY 계산 (TP1 전용)
# dust 방지: partial < minQty → FULL 승격
#            remaining < minQty → FULL 승격
# 반환: (partial_qty_str, remaining_qty_str) or None (→ FULL 승격)
# ============================================================

def calc_partial_qty(
    qty_full_str: str,
    partial_pct: float,
    lot: Dict[str, Decimal],
) -> Optional[Tuple[str, str]]:
    if lot is None:
        return None
    step      = lot["stepSize"]
    min_qty   = lot["minQty"]
    precision = abs(step.as_tuple().exponent)

    qty_full    = Decimal(qty_full_str)
    qty_partial = (qty_full * Decimal(str(partial_pct)) / step).quantize(
        Decimal("1"), rounding=ROUND_DOWN
    ) * step
    qty_remain  = qty_full - qty_partial

    if qty_partial < min_qty:
        return None
    if qty_remain < min_qty:
        return None

    return (
        f"{qty_partial:.{precision}f}",
        f"{qty_remain:.{precision}f}",
    )

# ============================================================
# _sync_with_retry
# 주문 후 거래소 포지션 재조회 — retry 구조
# 반환:
#   ("OK",   qty_str)   → 포지션 확인, 잔량 정상
#   ("GONE", None)      → 포지션 완전 소멸 확인
#   ("FAIL", None)      → retry 소진 후에도 조회 실패
# side 검증 포함: 조회된 side가 기대 side와 다르면 FAIL
# API 호출 전 선행 sleep — Race Condition 방지
# ============================================================

def _sync_with_retry(
    client,
    symbol: str,
    lot: Dict[str, Decimal],
    expected_side: str,
    retries: int,
    delay: float,
) -> Tuple[str, Optional[str]]:
    for attempt in range(1, retries + 1):
        time.sleep(delay)  # API 호출 전 선행 sleep (반영 지연 대기)
        try:
            positions = client.futures_position_information(symbol=symbol)
            for pos in positions:
                if pos["symbol"] == symbol:
                    amt = float(pos["positionAmt"])
                    if abs(amt) < 1e-9:
                        log.info(f"[SYNC_RETRY] attempt={attempt} → GONE")
                        return ("GONE", None)
                    # side 검증
                    actual_side = "LONG" if amt > 0 else "SHORT"
                    if actual_side != expected_side:
                        log.warning(
                            f"[SYNC_RETRY] side mismatch: expected={expected_side} actual={actual_side}"
                        )
                        return ("FAIL", None)
                    qty_str = calculate_quantity(abs(amt), lot)
                    if qty_str is None:
                        log.warning(f"[SYNC_RETRY] attempt={attempt} qty below minQty")
                        return ("GONE", None)
                    log.info(f"[SYNC_RETRY] attempt={attempt} → OK qty={qty_str}")
                    return ("OK", qty_str)
            # 심볼 자체가 없으면 GONE
            return ("GONE", None)
        except Exception as e:
            log.error(f"[SYNC_RETRY] attempt={attempt} error: {e}")
    log.error(f"[SYNC_RETRY] all {retries} attempts failed → FAIL")
    return ("FAIL", None)

# ============================================================
# _fetch_entry_price
# FULL EXIT 잔량 발생 시 거래소 평균 entry_price 재조회
# 반환: float (갱신된 entry_price) or None (조회 실패 → 기존값 유지)
# ============================================================

def _fetch_entry_price(
    client,
    symbol: str,
    expected_side: str,
) -> Optional[float]:
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if pos["symbol"] == symbol:
                amt = float(pos["positionAmt"])
                if abs(amt) < 1e-9:
                    return None
                actual_side = "LONG" if amt > 0 else "SHORT"
                if actual_side != expected_side:
                    return None
                ep = float(pos["entryPrice"])
                if ep > 0:
                    return ep
        return None
    except Exception as e:
        log.error(f"_fetch_entry_price: {e}")
        return None

# ============================================================
# IncrementalEMA
# ============================================================

class IncrementalEMA:
    def __init__(self, period: int):
        self.period  = period
        self.k       = 2.0 / (period + 1)
        self.value   = None
        self.ready   = False
        self._buf: List[float] = []
        self._history: Deque[float] = deque()

    def update(self, price: float) -> None:
        if not self.ready:
            self._buf.append(price)
            if len(self._buf) >= self.period:
                self.value = sum(self._buf) / len(self._buf)
                self.ready = True
                self._buf  = []
        else:
            self.value = price * self.k + self.value * (1.0 - self.k)
        if self.ready:
            self._history.append(self.value)

    def get(self) -> Optional[float]:
        return self.value if self.ready else None

    def get_prev(self) -> Optional[float]:
        if len(self._history) >= 2:
            return self._history[-2]
        return None

    def get_lookback(self, n: int) -> Optional[float]:
        if len(self._history) > n:
            return self._history[-(n + 1)]
        return None

    def trim_history(self, maxlen: int = 2100) -> None:
        while len(self._history) > maxlen:
            self._history.popleft()

# ============================================================
# STATE
# ============================================================

@dataclass
class Position:
    side:         str
    entry_price:  float
    qty:          str
    entry_bar:    int
    entry_type:   str  = "E1"
    e2_pullback:  Optional[bool] = None
    e2_reentry:   Optional[bool] = None
    # TP1 + TRAILING 상태
    tp1_done:     bool  = False
    tp1_attempted: bool = False   # PARTIAL 주문 성공 후 즉시 True — 중복 발동 차단
    trail_low:    float = float("inf")
    trail_high:   float = float("-inf")

@dataclass
class EngineState:
    bar:            int           = 0
    last_open_time: Optional[int] = None
    position:       Optional[Position] = None

    close_history: Deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    high_history:  Deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    low_history:   Deque[float] = field(default_factory=lambda: deque(maxlen=2000))

    ema_fast:      IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["10_EMA_FAST"]))
    ema_mid:       IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["11_EMA_MID"]))
    ema_arena:     IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["12_EMA_ARENA"]))

    ema_long_fast: IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["10L_EMA_FAST"]))
    ema_long_mid:  IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["11L_EMA_MID"]))

    ema_exit_fast: IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["30_EXIT_FAST_EMA"]))
    ema_exit_mid:  IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["31_EXIT_MID_EMA"]))

    htf_ema_fast:  IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["16_HTF_EMA_FAST"]))
    htf_ema_mid:   IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["17_HTF_EMA_MID"]))
    htf_ema_slow:  IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["18_HTF_EMA_SLOW"]))
    htf_last_open_time: Optional[int] = None

    short_exit_ready:     bool          = False
    long_exit_ready:      bool          = False
    short_exit_ready_bar: Optional[int] = None
    long_exit_ready_bar:  Optional[int] = None

    prev_arena_state: Optional[bool] = None

# ============================================================
# WARMUP CHECK
# ============================================================

def _warmup_done(st: EngineState) -> bool:
    swing  = int(CFG["15_SWING_LOOKBACK"])
    needed = max(
        CFG["10_EMA_FAST"],
        CFG["11_EMA_MID"],
        CFG["12_EMA_ARENA"],
        CFG["10L_EMA_FAST"],
        CFG["11L_EMA_MID"],
        CFG["30_EXIT_FAST_EMA"],
        CFG["31_EXIT_MID_EMA"],
        swing + 2,
        62,
    )
    bars_ok = st.bar >= needed
    htf_ok  = (
        st.htf_ema_fast.ready and
        st.htf_ema_mid.ready  and
        st.htf_ema_slow.ready
    )
    return bars_ok and htf_ok

# ============================================================
# 15m UPDATE — limit=2 (incremental EMA이므로 직전 완료봉 1개면 충분)
# ============================================================

def update_15m_emas(st: EngineState, symbol: str) -> None:
    kl_15m = fetch_klines_15m(symbol, 2)
    if not kl_15m or len(kl_15m) < 2:
        return
    completed_15m = kl_15m[0]   # limit=2 시 index 0 = 직전 완료봉
    open_time_15m = int(completed_15m[0])
    if st.htf_last_open_time == open_time_15m:
        return
    close_15m = float(completed_15m[4])
    st.htf_ema_fast.update(close_15m)
    st.htf_ema_mid.update(close_15m)
    st.htf_ema_slow.update(close_15m)
    st.htf_last_open_time = open_time_15m
    st.htf_ema_fast.trim_history()
    st.htf_ema_mid.trim_history()
    st.htf_ema_slow.trim_history()
    log.debug(
        f"[15m UPDATE] open_time={open_time_15m} close={close_15m:.6f} "
        f"htf_fast={st.htf_ema_fast.get()} htf_mid={st.htf_ema_mid.get()} htf_slow={st.htf_ema_slow.get()}"
    )

# ============================================================
# 15m REGIME
# ============================================================

def get_15m_regime(st: EngineState) -> str:
    f = st.htf_ema_fast.get()
    m = st.htf_ema_mid.get()
    s = st.htf_ema_slow.get()
    if f is None or m is None or s is None:
        return "NONE"
    if s > m > f:
        return "SHORT"
    if f > m > s:
        return "LONG"
    return "NONE"

# ============================================================
# 15m EXIT-READY CHECK
# ============================================================

def check_15m_exit_ready(st: EngineState) -> None:
    if st.position is None:
        return
    f = st.htf_ema_fast.get()
    m = st.htf_ema_mid.get()
    if f is None or m is None or m == 0:
        return

    if st.position.side == "SHORT" and not st.short_exit_ready:
        # SHORT 과열: 15m EMA_FAST가 EMA_MID 아래로 충분히 벌어진 상태
        spread = (m - f) / m
        if spread > float(CFG["70_SHORT_EXIT_THRESHOLD_PCT"]):
            st.short_exit_ready     = True
            st.short_exit_ready_bar = st.bar
            log.info(
                f"[EXIT_READY] SHORT ON | htf_fast={f:.6f} htf_mid={m:.6f} "
                f"spread={spread:.4%} bar={st.bar}"
            )

    if st.position.side == "LONG" and not st.long_exit_ready:
        # LONG 과열: 15m EMA_FAST가 EMA_MID 위로 충분히 벌어진 상태
        spread = (f - m) / m
        if spread > float(CFG["71_LONG_EXIT_THRESHOLD_PCT"]):
            st.long_exit_ready     = True
            st.long_exit_ready_bar = st.bar
            log.info(
                f"[EXIT_READY] LONG ON | htf_fast={f:.6f} htf_mid={m:.6f} "
                f"spread={spread:.4%} bar={st.bar}"
            )

    if CFG["94_EXIT_DEBUG_LOG_ENABLE"] and st.position is not None:
        side = st.position.side
        rdy  = st.short_exit_ready if side == "SHORT" else st.long_exit_ready
        rbar = st.short_exit_ready_bar if side == "SHORT" else st.long_exit_ready_bar
        thr  = CFG["70_SHORT_EXIT_THRESHOLD_PCT"] if side == "SHORT" else CFG["71_LONG_EXIT_THRESHOLD_PCT"]
        # spread 방향도 수정된 공식 기준으로 출력
        spread_debug = (m - f) / m if side == "SHORT" else (f - m) / m
        log.debug(
            f"[EXIT_READY_STATUS] side={side} ready={rdy} bar={st.bar} "
            f"ready_bar={rbar} htf_fast={f} htf_mid={m} spread={spread_debug:.4%} threshold={thr}"
        )

# ============================================================
# SHORT ENTRY SIGNALS (BR8 FROZEN)
# ============================================================

def short_entry_signals(st: EngineState):
    if get_15m_regime(st) != "SHORT":
        return "", None, None
    if not _warmup_done(st):
        return "", None, None

    fast  = st.ema_fast
    mid   = st.ema_mid
    arena = st.ema_arena

    if not (fast.ready and mid.ready and arena.ready):
        return "", None, None

    fast_now  = fast.get()
    fast_prev = fast.get_prev()
    mid_now   = mid.get()
    mid_prev  = mid.get_prev()
    arena_now = arena.get()

    if fast_prev is None or mid_prev is None:
        return "", None, None

    if not (fast_now < arena_now):
        return "", None, None

    swing_lookback  = int(CFG["15_SWING_LOOKBACK"])
    slope_threshold = float(CFG["14_SLOPE_THRESHOLD"])
    ref = fast.get_lookback(swing_lookback)
    if ref is None or ref == 0:
        return "", None, None
    if (fast_now - ref) / ref > -slope_threshold:
        return "", None, None

    e1_signal = (fast_prev >= mid_prev) and (fast_now < mid_now)

    tolerance = float(CFG["13_TOUCH_TOLERANCE"])
    if len(st.high_history) < 2 or len(st.close_history) < 1:
        return "", None, None

    high_m2  = st.high_history[-2]
    close_c  = st.close_history[-1]
    pullback  = high_m2 >= fast_prev * (1.0 - tolerance)
    reentry   = close_c < fast_now
    e2_signal = pullback and reentry

    if CFG["93_E2_CANDIDATE_LOG_ENABLE"]:
        log.info(
            f"[SHORT_E2_CANDIDATE] pullback={pullback} reentry={reentry} "
            f"fast_prev={fast_prev:.6f} fast_now={fast_now:.6f} "
            f"close={close_c:.6f} high[-2]={high_m2:.6f} "
            f"threshold_hi={fast_prev * (1.0 - tolerance):.6f}"
        )

    if e1_signal:
        return "E1", None, None
    if CFG["23_ENTRY2_ENABLE"] and e2_signal:
        return "E2", pullback, reentry
    return "", None, None

# ============================================================
# LONG ENTRY SIGNALS (BR7 E1 + SHORT E2 대칭 E2)
# ============================================================

def long_entry_signals(st: EngineState):
    if get_15m_regime(st) != "LONG":
        return "", None, None
    if not _warmup_done(st):
        return "", None, None

    fast = st.ema_long_fast
    mid  = st.ema_long_mid

    if not (fast.ready and mid.ready):
        return "", None, None

    fast_now  = fast.get()
    fast_prev = fast.get_prev()
    mid_now   = mid.get()
    mid_prev  = mid.get_prev()

    if fast_prev is None or mid_prev is None:
        return "", None, None

    cross_up  = (fast_prev <= mid_prev) and (fast_now > mid_now)
    e1_signal = False
    if cross_up:
        if CFG["60_FILTER_SLOPE_ENABLE"]:
            bars = int(CFG["61_SLOPE_BARS"])
            ref  = mid.get_lookback(bars)
            if ref is not None and ref != 0:
                slope_pct = (mid_now - ref) / ref
                if slope_pct >= float(CFG["62_SLOPE_MIN_PCT"]):
                    e1_signal = True
        else:
            e1_signal = True

    e2_signal = False
    pullback  = None
    reentry   = None
    if CFG["23_ENTRY2_ENABLE"]:
        tolerance = float(CFG["13_TOUCH_TOLERANCE"])
        if len(st.low_history) >= 2 and len(st.close_history) >= 1:
            low_m2   = st.low_history[-2]
            close_c  = st.close_history[-1]
            pullback  = low_m2 <= fast_prev * (1.0 + tolerance)
            reentry   = close_c > fast_now
            e2_signal = pullback and reentry

            if CFG["93_E2_CANDIDATE_LOG_ENABLE"]:
                log.info(
                    f"[LONG_E2_CANDIDATE] pullback={pullback} reentry={reentry} "
                    f"fast_prev={fast_prev:.6f} fast_now={fast_now:.6f} "
                    f"close={close_c:.6f} low[-2]={low_m2:.6f} "
                    f"threshold_lo={fast_prev * (1.0 + tolerance):.6f}"
                )

    if e1_signal:
        return "E1", None, None
    if e2_signal:
        return "E2", pullback, reentry
    return "", None, None

# ============================================================
# 5m EXIT EXECUTION
# 반환: Tuple[str, Optional[str]]
#   ("NONE",    None)
#   ("FULL",    reason_str)
#   ("PARTIAL", partial_qty_str)
#
# 우선순위:
#   [1] SL
#   [2] TIMEOUT
#   [3] TP1 partial  ← SYNC 차단 / tp1_attempted 차단
#   [4] TRAILING     ← SYNC 차단 / tp1_done 이후만
#   [5] 기존 EMA EXIT
# ============================================================

def exit_execution_5m(
    st: EngineState,
    lot: Dict[str, Decimal],
) -> Tuple[str, Optional[str]]:
    pos = st.position
    if pos is None:
        return ("NONE", None)

    close      = st.close_history[-1]
    cur_high   = st.high_history[-1]  if len(st.high_history) >= 1 else None
    cur_low    = st.low_history[-1]   if len(st.low_history) >= 1 else None
    prev_close = st.close_history[-2] if len(st.close_history) >= 2 else None
    prev_high  = st.high_history[-2]  if len(st.high_history) >= 2 else None
    prev_low   = st.low_history[-2]   if len(st.low_history) >= 2 else None

    # ---- [1] SL ----
    if CFG["40_SL_ENABLE"]:
        sl = float(CFG["41_SL_PCT"]) / 100.0
        if pos.side == "SHORT" and close >= pos.entry_price * (1.0 + sl):
            log.info(f"[EXIT_SL] SHORT close={close} >= SL={pos.entry_price * (1.0 + sl):.6f}")
            return ("FULL", "SL")
        if pos.side == "LONG" and close <= pos.entry_price * (1.0 - sl):
            log.info(f"[EXIT_SL] LONG close={close} <= SL={pos.entry_price * (1.0 - sl):.6f}")
            return ("FULL", "SL")

    # ---- [2] TIMEOUT ----
    if CFG["50_TIMEOUT_EXIT_ENABLE"]:
        if pos.entry_type != "SYNC":
            if (st.bar - pos.entry_bar) >= int(CFG["51_TIMEOUT_BARS"]):
                log.info(f"[EXIT_TIMEOUT] bars={st.bar - pos.entry_bar}")
                return ("FULL", "TIMEOUT")

    # ---- [3] TP1 PARTIAL — SYNC 차단 / tp1_attempted 차단 ----
    if (
        CFG["80_TP1_ENABLE"]
        and not pos.tp1_done
        and not pos.tp1_attempted
        and pos.entry_type != "SYNC"
    ):
        tp1_pct     = float(CFG["81_TP1_PCT"])
        partial_pct = float(CFG["82_TP1_PARTIAL_PCT"])

        if pos.side == "SHORT":
            tp1_target = pos.entry_price * (1.0 - tp1_pct)
            if close <= tp1_target:
                result = calc_partial_qty(pos.qty, partial_pct, lot)
                if result is None:
                    log.info(
                        f"[TP1_FULL_UPGRADE] SHORT dust → FULL | close={close:.6f} "
                        f"target={tp1_target:.6f}"
                    )
                    return ("FULL", "TP1_FULL")
                partial_qty_str, _ = result
                log.info(
                    f"[TP1] SHORT partial | close={close:.6f} target={tp1_target:.6f} "
                    f"partial_qty={partial_qty_str}"
                )
                return ("PARTIAL", partial_qty_str)

        elif pos.side == "LONG":
            tp1_target = pos.entry_price * (1.0 + tp1_pct)
            if close >= tp1_target:
                result = calc_partial_qty(pos.qty, partial_pct, lot)
                if result is None:
                    log.info(
                        f"[TP1_FULL_UPGRADE] LONG dust → FULL | close={close:.6f} "
                        f"target={tp1_target:.6f}"
                    )
                    return ("FULL", "TP1_FULL")
                partial_qty_str, _ = result
                log.info(
                    f"[TP1] LONG partial | close={close:.6f} target={tp1_target:.6f} "
                    f"partial_qty={partial_qty_str}"
                )
                return ("PARTIAL", partial_qty_str)

    # ---- [4] TRAILING — SYNC 차단 / tp1_done 이후만 ----
    if CFG["83_TRAIL_ENABLE"] and pos.tp1_done and pos.entry_type != "SYNC":
        callback = float(CFG["84_TRAIL_CALLBACK_PCT"])

        if pos.side == "SHORT":
            if close < pos.trail_low:
                pos.trail_low = close
            trail_stop = pos.trail_low * (1.0 + callback)
            if CFG["94_EXIT_DEBUG_LOG_ENABLE"]:
                log.debug(
                    f"[TRAIL_STATUS] SHORT trail_low={pos.trail_low:.6f} "
                    f"trail_stop={trail_stop:.6f} close={close:.6f}"
                )
            if close >= trail_stop:
                log.info(
                    f"[EXIT_TRAIL] SHORT | close={close:.6f} >= trail_stop={trail_stop:.6f} "
                    f"trail_low={pos.trail_low:.6f}"
                )
                return ("FULL", "TRAIL")

        elif pos.side == "LONG":
            if close > pos.trail_high:
                pos.trail_high = close
            trail_stop = pos.trail_high * (1.0 - callback)
            if CFG["94_EXIT_DEBUG_LOG_ENABLE"]:
                log.debug(
                    f"[TRAIL_STATUS] LONG trail_high={pos.trail_high:.6f} "
                    f"trail_stop={trail_stop:.6f} close={close:.6f}"
                )
            if close <= trail_stop:
                log.info(
                    f"[EXIT_TRAIL] LONG | close={close:.6f} <= trail_stop={trail_stop:.6f} "
                    f"trail_high={pos.trail_high:.6f}"
                )
                return ("FULL", "TRAIL")

    # ---- [5] 기존 EMA EXIT ----
    ef      = st.ema_exit_fast.get()
    em      = st.ema_exit_mid.get()
    ef_prev = st.ema_exit_fast.get_prev()
    em_prev = st.ema_exit_mid.get_prev()

    if ef is None or em is None or ef_prev is None or em_prev is None:
        return ("NONE", None)

    if pos.side == "SHORT" and st.short_exit_ready:
        if st.short_exit_ready_bar is not None and st.bar <= st.short_exit_ready_bar:
            return ("NONE", None)

        cond_a    = (ef_prev > em_prev) and (ef > em) and (close > em)
        cond_b    = (ef_prev <= em_prev) and (ef > em) and (close > em)
        struct_ok = (
            prev_close is not None and prev_high is not None and cur_high is not None and
            close > prev_close and cur_high > prev_high
        )
        result = (cond_a or cond_b) and struct_ok

        if CFG["94_EXIT_DEBUG_LOG_ENABLE"]:
            log.debug(
                f"[EXIT_EXEC_DECISION] SHORT | cond_a={cond_a} cond_b={cond_b} "
                f"struct_ok={struct_ok} result={result} "
                f"ef={ef:.6f} em={em:.6f} close={close:.6f}"
            )

        if result:
            label = "2봉연속+구조" if cond_a else "교차+종가+구조"
            log.info(
                f"[EXIT_5m] SHORT {label} | ef={ef:.6f} em={em:.6f} "
                f"ef_prev={ef_prev:.6f} em_prev={em_prev:.6f} "
                f"close={close:.6f} prev_close={prev_close:.6f} "
                f"cur_high={cur_high:.6f} prev_high={prev_high:.6f}"
            )
            return ("FULL", "EMA_EXIT")

    if pos.side == "LONG" and st.long_exit_ready:
        if st.long_exit_ready_bar is not None and st.bar <= st.long_exit_ready_bar:
            return ("NONE", None)

        cond_a    = (ef_prev < em_prev) and (ef < em) and (close < em)
        cond_b    = (ef_prev >= em_prev) and (ef < em) and (close < em)
        struct_ok = (
            prev_close is not None and prev_low is not None and cur_low is not None and
            close < prev_close and cur_low < prev_low
        )
        result = (cond_a or cond_b) and struct_ok

        if CFG["94_EXIT_DEBUG_LOG_ENABLE"]:
            log.debug(
                f"[EXIT_EXEC_DECISION] LONG | cond_a={cond_a} cond_b={cond_b} "
                f"struct_ok={struct_ok} result={result} "
                f"ef={ef:.6f} em={em:.6f} close={close:.6f}"
            )

        if result:
            label = "2봉연속+구조" if cond_a else "교차+종가+구조"
            log.info(
                f"[EXIT_5m] LONG {label} | ef={ef:.6f} em={em:.6f} "
                f"ef_prev={ef_prev:.6f} em_prev={em_prev:.6f} "
                f"close={close:.6f} prev_close={prev_close:.6f} "
                f"cur_low={cur_low:.6f} prev_low={prev_low:.6f}"
            )
            return ("FULL", "EMA_EXIT")

    return ("NONE", None)

# ============================================================
# EXECUTION
# ============================================================

def place_short_entry(client, symbol, capital_usdt, lot):
    try:
        ticker   = client.futures_symbol_ticker(symbol=symbol)
        price    = float(ticker["price"])
        notional = float(capital_usdt) * int(CFG["04_LEVERAGE"])
        qty_str  = calculate_quantity(notional / price, lot)
        if qty_str is None:
            log.error("place_short_entry: qty calculation failed")
            return None
        client.futures_create_order(
            symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty_str,
        )
        # 실체결가 확정 — 주문 후 재조회
        retries = int(CFG["95_SYNC_RETRY_COUNT"])
        delay   = float(CFG["96_SYNC_RETRY_DELAY_SEC"])
        actual_entry = price  # fallback
        for attempt in range(1, retries + 1):
            try:
                time.sleep(delay)
                positions = client.futures_position_information(symbol=symbol)
                for pos in positions:
                    if pos["symbol"] == symbol:
                        amt = float(pos["positionAmt"])
                        if amt < 0:
                            ep = float(pos["entryPrice"])
                            if ep > 0:
                                actual_entry = ep
                                log.info(
                                    f"[ENTRY_PRICE_SYNC] SHORT attempt={attempt} "
                                    f"ticker={price:.6f} actual={actual_entry:.6f}"
                                )
                                break
                else:
                    continue
                break
            except Exception as e:
                log.warning(f"[ENTRY_PRICE_SYNC] SHORT attempt={attempt} error: {e}")
        return {"entry_price": actual_entry, "qty": qty_str}
    except Exception as e:
        log.error(f"place_short_entry: {e}")
        return None

def place_short_exit(client, symbol, qty, lot):
    try:
        qty2 = normalize_qty_str(qty, lot)
        if qty2 is None:
            log.error("place_short_exit: qty too small")
            return False
        client.futures_create_order(
            symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty2, reduceOnly=True,
        )
        return True
    except Exception as e:
        log.error(f"place_short_exit: {e}")
        return False

def place_short_partial_exit(client, symbol, partial_qty_str, lot):
    try:
        qty2 = normalize_qty_str(partial_qty_str, lot)
        if qty2 is None:
            log.error("place_short_partial_exit: qty too small")
            return False
        client.futures_create_order(
            symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty2, reduceOnly=True,
        )
        return True
    except Exception as e:
        log.error(f"place_short_partial_exit: {e}")
        return False

def place_long_entry(client, symbol, capital_usdt, lot):
    try:
        ticker   = client.futures_symbol_ticker(symbol=symbol)
        price    = float(ticker["price"])
        notional = float(capital_usdt) * int(CFG["04_LEVERAGE"])
        qty_str  = calculate_quantity(notional / price, lot)
        if qty_str is None:
            log.error("place_long_entry: qty calculation failed")
            return None
        client.futures_create_order(
            symbol=symbol, side=SIDE_BUY, type=ORDER_TYPE_MARKET, quantity=qty_str,
        )
        # 실체결가 확정 — 주문 후 재조회
        retries = int(CFG["95_SYNC_RETRY_COUNT"])
        delay   = float(CFG["96_SYNC_RETRY_DELAY_SEC"])
        actual_entry = price  # fallback
        for attempt in range(1, retries + 1):
            try:
                time.sleep(delay)
                positions = client.futures_position_information(symbol=symbol)
                for pos in positions:
                    if pos["symbol"] == symbol:
                        amt = float(pos["positionAmt"])
                        if amt > 0:
                            ep = float(pos["entryPrice"])
                            if ep > 0:
                                actual_entry = ep
                                log.info(
                                    f"[ENTRY_PRICE_SYNC] LONG attempt={attempt} "
                                    f"ticker={price:.6f} actual={actual_entry:.6f}"
                                )
                                break
                else:
                    continue
                break
            except Exception as e:
                log.warning(f"[ENTRY_PRICE_SYNC] LONG attempt={attempt} error: {e}")
        return {"entry_price": actual_entry, "qty": qty_str}
    except Exception as e:
        log.error(f"place_long_entry: {e}")
        return None

def place_long_exit(client, symbol, qty, lot):
    try:
        qty2 = normalize_qty_str(qty, lot)
        if qty2 is None:
            log.error("place_long_exit: qty too small")
            return False
        client.futures_create_order(
            symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty2, reduceOnly=True,
        )
        return True
    except Exception as e:
        log.error(f"place_long_exit: {e}")
        return False

def place_long_partial_exit(client, symbol, partial_qty_str, lot):
    try:
        qty2 = normalize_qty_str(partial_qty_str, lot)
        if qty2 is None:
            log.error("place_long_partial_exit: qty too small")
            return False
        client.futures_create_order(
            symbol=symbol, side=SIDE_SELL, type=ORDER_TYPE_MARKET, quantity=qty2, reduceOnly=True,
        )
        return True
    except Exception as e:
        log.error(f"place_long_partial_exit: {e}")
        return False

# ============================================================
# _apply_bar
# ============================================================

def _apply_bar(st: EngineState, close: float, high: float, low: float) -> None:
    st.close_history.append(close)
    st.high_history.append(high)
    st.low_history.append(low)

    st.ema_fast.update(close)
    st.ema_mid.update(close)
    st.ema_arena.update(close)
    st.ema_long_fast.update(close)
    st.ema_long_mid.update(close)
    st.ema_exit_fast.update(close)
    st.ema_exit_mid.update(close)

    st.ema_fast.trim_history()
    st.ema_mid.trim_history()
    st.ema_arena.trim_history()
    st.ema_long_fast.trim_history()
    st.ema_long_mid.trim_history()
    st.ema_exit_fast.trim_history()
    st.ema_exit_mid.trim_history()

# ============================================================
# ENGINE LOOP
# ============================================================

STOP = False

def _sig_handler(_sig, _frame):
    global STOP
    STOP = True

signal.signal(signal.SIGINT,  _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)

def _reset_exit_state(st: EngineState) -> None:
    st.short_exit_ready     = False
    st.long_exit_ready      = False
    st.short_exit_ready_bar = None
    st.long_exit_ready_bar  = None

def engine():
    client   = init_client()
    symbol   = CFG["01_TRADE_SYMBOL"]
    interval = CFG["02_INTERVAL"]
    capital  = float(CFG["03_CAPITAL_BASE_USDT"])

    set_leverage(client, symbol, int(CFG["04_LEVERAGE"]))

    lot = get_futures_lot_size(client, symbol)
    if lot is None:
        raise RuntimeError("lot_size retrieval failed")

    st = EngineState()

    retries = int(CFG["95_SYNC_RETRY_COUNT"])
    delay   = float(CFG["96_SYNC_RETRY_DELAY_SEC"])

    # ---- SYNC ----
    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if pos["symbol"] == symbol:
                amt = float(pos["positionAmt"])
                if amt != 0:
                    side    = "LONG" if amt > 0 else "SHORT"
                    qty_str = calculate_quantity(abs(amt), lot)
                    if qty_str is None:
                        log.error("[SYNC] qty calculation failed, skipping sync")
                    else:
                        st.position = Position(
                            side=side,
                            entry_price=float(pos["entryPrice"]),
                            qty=qty_str,
                            entry_bar=st.bar,
                            entry_type="SYNC",
                        )
                        log.info(f"[SYNC] {side} qty={qty_str} entry={st.position.entry_price}")
                break
    except Exception as e:
        log.error(f"position sync failed: {e}")

    log.info(
        f"START VELLA_MTF | symbol={symbol} interval={interval} htf={CFG['02b_HTF_INTERVAL']} "
        f"capital={capital} lev={CFG['04_LEVERAGE']} "
        f"| SHORT_ENTRY_EMA=({CFG['10_EMA_FAST']},{CFG['11_EMA_MID']},{CFG['12_EMA_ARENA']}) "
        f"| LONG_ENTRY_EMA=({CFG['10L_EMA_FAST']},{CFG['11L_EMA_MID']}) "
        f"| HTF_EMA=({CFG['16_HTF_EMA_FAST']},{CFG['17_HTF_EMA_MID']},{CFG['18_HTF_EMA_SLOW']}) "
        f"| EXIT_EMA=({CFG['30_EXIT_FAST_EMA']},{CFG['31_EXIT_MID_EMA']}) "
        f"| SHORT_THR={CFG['70_SHORT_EXIT_THRESHOLD_PCT']} LONG_THR={CFG['71_LONG_EXIT_THRESHOLD_PCT']} "
        f"| TP1={CFG['80_TP1_ENABLE']} TP1_PCT={CFG['81_TP1_PCT']} PARTIAL={CFG['82_TP1_PARTIAL_PCT']} "
        f"| TRAIL={CFG['83_TRAIL_ENABLE']} CALLBACK={CFG['84_TRAIL_CALLBACK_PCT']} "
        f"| SYNC_RETRY={retries} DELAY={delay} "
        f"| E2_LOG={CFG['93_E2_CANDIDATE_LOG_ENABLE']} EXIT_DEBUG={CFG['94_EXIT_DEBUG_LOG_ENABLE']}"
    )

    # ======================================
    # COLD START: 5m warmup — limit=1500
    # ======================================
    kl_init = fetch_klines_futures(symbol, interval, int(CFG["90_KLINE_LIMIT"]))
    if not kl_init:
        raise RuntimeError("COLD START: 5m kline fetch failed")

    for k in kl_init[:-1]:
        _apply_bar(st, float(k[4]), float(k[2]), float(k[3]))
    st.bar = len(st.close_history)
    st.last_open_time = int(kl_init[-2][0])
    log.info(f"[BOOT] 5m warmup complete: {st.bar} bars")

    # ======================================
    # COLD START: 15m warmup — limit=1500
    # ======================================
    kl_15m_init = fetch_klines_15m(symbol, int(CFG["90_KLINE_LIMIT"]))
    if kl_15m_init:
        completed_15m_bars = kl_15m_init[:-1]
        for k in completed_15m_bars:
            close_15m = float(k[4])
            st.htf_ema_fast.update(close_15m)
            st.htf_ema_mid.update(close_15m)
            st.htf_ema_slow.update(close_15m)
        if completed_15m_bars:
            st.htf_last_open_time = int(completed_15m_bars[-1][0])
        log.info(
            f"[BOOT] 15m warmup complete: {len(completed_15m_bars)} bars "
            f"| htf_fast={st.htf_ema_fast.get()} htf_mid={st.htf_ema_mid.get()} htf_slow={st.htf_ema_slow.get()} "
            f"| regime={get_15m_regime(st)} | warmup_done={_warmup_done(st)}"
        )
    else:
        log.warning("[BOOT] 15m kline fetch failed — regime will be NONE until 15m data arrives")

    # ======================================
    # MAIN LOOP — 5m polling limit=2
    # ======================================
    while not STOP:
        try:
            # cold start 이후 메인루프는 limit=2만 요청 (직전 완료봉 + 현재봉)
            kl = fetch_klines_futures(symbol, interval, 2)
            if not kl or len(kl) < 2:
                time.sleep(CFG["91_POLL_SEC"])
                continue

            completed = kl[0]   # limit=2 시 index 0 = 직전 완료봉
            open_time = int(completed[0])

            if st.last_open_time == open_time:
                time.sleep(CFG["91_POLL_SEC"])
                continue

            st.last_open_time = open_time
            st.bar += 1

            _apply_bar(st, float(completed[4]), float(completed[2]), float(completed[3]))

            # ---- 15m UPDATE ----
            update_15m_emas(st, symbol)

            # ---- REGIME ----
            regime = get_15m_regime(st)

            # ---- 15m EXIT-READY CHECK ----
            check_15m_exit_ready(st)

            # ---- ARENA LOG ----
            if st.ema_fast.ready and st.ema_arena.ready:
                short_arena_now = st.ema_fast.get() < st.ema_arena.get()
                if short_arena_now != st.prev_arena_state:
                    log.info(f"[ARENA] fast<arena={'ON' if short_arena_now else 'OFF'}")
                    st.prev_arena_state = short_arena_now

            # ======================================
            # NO POSITION → ENTRY
            # ======================================
            if st.position is None:
                _reset_exit_state(st)

                if regime == "SHORT":
                    entry_type, pb, re = short_entry_signals(st)
                    if entry_type:
                        order = place_short_entry(client, symbol, capital, lot)
                        if order:
                            st.position = Position(
                                side="SHORT",
                                entry_price=float(order["entry_price"]),
                                qty=order["qty"],
                                entry_bar=st.bar,
                                entry_type=entry_type,
                                e2_pullback=pb,
                                e2_reentry=re,
                            )
                            extra = f" pullback={pb} reentry={re}" if entry_type == "E2" else ""
                            log.info(
                                f"[ENTRY] SHORT type={entry_type} qty={st.position.qty} "
                                f"price={st.position.entry_price} bar={st.bar} regime={regime} "
                                f"fast={st.ema_fast.get():.6f} mid={st.ema_mid.get():.6f} "
                                f"arena={st.ema_arena.get():.6f}{extra}"
                            )
                        else:
                            log.error("[ENTRY_FAIL] SHORT order failed")

                elif regime == "LONG":
                    entry_type, pb, re = long_entry_signals(st)
                    if entry_type:
                        order = place_long_entry(client, symbol, capital, lot)
                        if order:
                            st.position = Position(
                                side="LONG",
                                entry_price=float(order["entry_price"]),
                                qty=order["qty"],
                                entry_bar=st.bar,
                                entry_type=entry_type,
                                e2_pullback=pb,
                                e2_reentry=re,
                            )
                            extra = f" pullback={pb} reentry={re}" if entry_type == "E2" else ""
                            log.info(
                                f"[ENTRY] LONG type={entry_type} qty={st.position.qty} "
                                f"price={st.position.entry_price} bar={st.bar} regime={regime} "
                                f"long_fast={st.ema_long_fast.get():.6f} long_mid={st.ema_long_mid.get():.6f}{extra}"
                            )
                        else:
                            log.error("[ENTRY_FAIL] LONG order failed")

            # ======================================
            # POSITION EXISTS → EXIT CHECK
            # ======================================
            else:
                if st.position.entry_bar == st.bar:
                    continue

                exit_signal, exit_detail = exit_execution_5m(st, lot)

                # ---- PARTIAL (TP1) ----
                if exit_signal == "PARTIAL":
                    partial_qty_str = exit_detail
                    side = st.position.side

                    if side == "SHORT":
                        ok = place_short_partial_exit(client, symbol, partial_qty_str, lot)
                    else:
                        ok = place_long_partial_exit(client, symbol, partial_qty_str, lot)

                    if ok:
                        # 주문 성공 즉시 tp1_attempted = True — 중복 발동 차단
                        st.position.tp1_attempted = True

                        # retry sync 로 잔량 확정
                        sync_status, actual_qty = _sync_with_retry(
                            client, symbol, lot, side, retries, delay
                        )
                        if sync_status == "OK" and actual_qty is not None:
                            close_now = st.close_history[-1]
                            st.position.tp1_done = True
                            st.position.qty      = actual_qty
                            if side == "SHORT":
                                st.position.trail_low  = close_now
                            else:
                                st.position.trail_high = close_now
                            log.info(
                                f"[TP1_DONE] {side} partial_qty={partial_qty_str} "
                                f"remain_qty={actual_qty} trail_ref={close_now:.6f} bar={st.bar}"
                            )
                        elif sync_status == "GONE":
                            log.warning("[TP1] partial ok but position gone — closing local state")
                            st.position = None
                            _reset_exit_state(st)
                        else:
                            # FAIL — tp1_attempted True로 재발동 차단, qty 갱신은 보류
                            log.error(
                                f"[TP1_SYNC_FAIL] {side} retry sync failed — "
                                f"tp1_attempted=True (중복 차단), qty 미갱신, 다음 바 계속"
                            )
                    else:
                        log.error(f"[TP1_FAIL] {side} partial order failed — tp1_attempted stays False")

                # ---- FULL EXIT ----
                elif exit_signal == "FULL":
                    side = st.position.side
                    if side == "SHORT":
                        ok = place_short_exit(client, symbol, st.position.qty, lot)
                    else:
                        ok = place_long_exit(client, symbol, st.position.qty, lot)

                    if ok:
                        # 주문 성공 → retry sync 로 포지션 소멸 확인
                        sync_status, actual_qty = _sync_with_retry(
                            client, symbol, lot, side, retries, delay
                        )
                        if sync_status == "GONE":
                            log.info(
                                f"[EXIT] {side} reason={exit_detail} confirmed GONE "
                                f"close={st.close_history[-1]} entry={st.position.entry_price} "
                                f"tp1_done={st.position.tp1_done} bar={st.bar}"
                            )
                            st.position = None
                            _reset_exit_state(st)
                        elif sync_status == "OK" and actual_qty is not None:
                            # 잔량 남아 있음 — qty + entry_price 재동기화 후 포지션 유지
                            new_entry = _fetch_entry_price(client, symbol, side)
                            st.position.qty = actual_qty
                            if new_entry is not None:
                                log.warning(
                                    f"[EXIT_PARTIAL_FILL] {side} reason={exit_detail} "
                                    f"remain qty={actual_qty} "
                                    f"entry_price updated {st.position.entry_price:.6f} → {new_entry:.6f}"
                                )
                                st.position.entry_price = new_entry
                            else:
                                log.warning(
                                    f"[EXIT_PARTIAL_FILL] {side} reason={exit_detail} "
                                    f"remain qty={actual_qty} entry_price fetch failed — keeping old"
                                )
                        else:
                            log.error(
                                f"[EXIT_SYNC_FAIL] {side} reason={exit_detail} "
                                f"retry sync failed — position kept for next bar"
                            )
                    else:
                        log.error(f"[EXIT_FAIL] {side} reason={exit_detail} order failed (position kept)")

        except Exception as e:
            log.error(f"engine loop error: {e}")
            time.sleep(CFG["91_POLL_SEC"])

    log.info("STOP VELLA_MTF")

if __name__ == "__main__":
    engine()