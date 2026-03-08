# ============================================================
# VELLA_BR7 — LONG ENGINE
# ENTRY LOGIC: v10 backtest_long 100% 미러 (ARENA/E1/E2/slope/tolerance/swing)
# EXIT LOGIC: EMA CROSS EXIT (exit_fast < exit_mid)
# EXECUTION: v9 proven plumbing (qty str / reduceOnly / closed-bar)
# ============================================================

import os
import sys
import time
import signal
import logging
import requests
from decimal import Decimal, ROUND_DOWN
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Deque
from collections import deque

# ============================================================
# CFG
# ============================================================

CFG = {
    "01_TRADE_SYMBOL": "CCUSDT",
    "02_INTERVAL": "5m",
    "03_CAPITAL_BASE_USDT": 10.0,
    "04_LEVERAGE": 1,

    # ---- ENTRY EMA (옵티 정합) ----
    "10_EMA_FAST": 5,
    "11_EMA_MID": 10,
    "12_EMA_ARENA": 30,
    "13_TOUCH_TOLERANCE": 0.001,
    "14_SLOPE_THRESHOLD": 0.0005,  # 실전 진입 수가 과도하게 줄면 0.0005 튜닝 후보
    "15_SWING_LOOKBACK": 5,

    "23_ENTRY2_ENABLE": True,

    # ---- EXIT EMA (CROSS EXIT) ----
    "30_EXIT_FAST_EMA": 4,
    "31_EXIT_MID_EMA": 8,

    "40_SL_ENABLE": False,
    "41_SL_PCT": 2.0,

    "50_TIMEOUT_EXIT_ENABLE": False,
    "51_TIMEOUT_BARS": 60,

    "90_KLINE_LIMIT": 1500,
    "91_POLL_SEC": 7,
    "92_LOG_LEVEL": "INFO",
}

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=getattr(logging, CFG["92_LOG_LEVEL"], logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("VELLA_BR7_LONG")

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
    api_key = os.getenv("BINANCE_API_KEY")
    api_secret = os.getenv("BINANCE_API_SECRET")
    if not api_key or not api_secret:
        raise RuntimeError("Missing BINANCE_API_KEY / BINANCE_API_SECRET")
    return Client(api_key, api_secret)

def set_leverage(client: "Client", symbol: str, leverage: int) -> None:
    try:
        client.futures_change_leverage(symbol=symbol, leverage=leverage)
        log.info(f"[LEVERAGE] {symbol} leverage={leverage}")
    except Exception as e:
        log.error(f"set_leverage failed: {e}")

def verify_account_safety(client: "Client", symbol: str, capital_usdt: float, lot: Dict[str, Decimal]) -> bool:
    try:
        pos_mode = client.futures_get_position_mode()
        if pos_mode.get("dualSidePosition", True):
            log.error("[SAFETY] HEDGE MODE 감지. ONE_WAY 모드로 변경 후 재시작하세요.")
            return False

        info = client.futures_exchange_info()
        for s in info["symbols"]:
            if s["symbol"] == symbol:
                for f in s["filters"]:
                    if f["filterType"] == "MIN_NOTIONAL":
                        min_notional = float(f["notional"])
                        notional = float(capital_usdt) * float(CFG["04_LEVERAGE"])
                        if notional < min_notional:
                            log.error(f"[SAFETY] 주문금액 {notional:.2f} USDT < MIN_NOTIONAL {min_notional:.2f} USDT.")
                            return False
                        break
                break

        log.info("[SAFETY] ONE_WAY ✅ | MIN_NOTIONAL ✅")
        return True

    except Exception as e:
        log.error(f"verify_account_safety: {e}")
        return False

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
# QTY (str 통일)
# ============================================================

def calculate_quantity(qty_raw, lot: Dict[str, Decimal]) -> Optional[str]:
    if lot is None:
        return None
    qty_decimal = Decimal(str(qty_raw))
    step = lot["stepSize"]
    qty  = (qty_decimal / step).quantize(Decimal("1"), rounding=ROUND_DOWN) * step
    if qty < lot["minQty"]:
        log.error(f"qty {qty} < minQty {lot['minQty']}")
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
        log.error(f"exit qty {qty} < minQty {lot['minQty']}")
        return None
    if qty > lot["maxQty"]:
        qty = lot["maxQty"]
    precision = abs(step.as_tuple().exponent)
    return f"{qty:.{precision}f}"

# ============================================================
# EMA — incremental (옵티 동일 방식)
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
    side:        str
    entry_price: float
    qty:         str
    entry_bar:   int
    entry_type:  str = "E1"

@dataclass
class EngineState:
    bar:            int            = 0
    last_open_time: Optional[int]  = None
    position:       Optional[Position] = None

    close_history: Deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    high_history:  Deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    low_history:   Deque[float] = field(default_factory=lambda: deque(maxlen=2000))

    ema_fast:      IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["10_EMA_FAST"]))
    ema_mid:       IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["11_EMA_MID"]))
    ema_arena:     IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["12_EMA_ARENA"]))
    ema_exit_fast: IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["30_EXIT_FAST_EMA"]))
    ema_exit_mid:  IncrementalEMA = field(default_factory=lambda: IncrementalEMA(CFG["31_EXIT_MID_EMA"]))

    prev_arena_state: Optional[bool] = None

# ============================================================
# WARMUP
# ============================================================

def _warmup_done(st: EngineState) -> bool:
    swing  = int(CFG["15_SWING_LOOKBACK"])
    needed = max(
        CFG["10_EMA_FAST"],
        CFG["11_EMA_MID"],
        CFG["12_EMA_ARENA"],
        CFG["30_EXIT_FAST_EMA"],
        CFG["31_EXIT_MID_EMA"],
        swing + 2,
        62,
    )
    return st.bar >= needed

# ============================================================
# ENTRY SIGNALS
# ============================================================

def long_entry_signals(st: EngineState) -> str:
    """반환: 'E1' / 'E2' / ''"""
    if not _warmup_done(st):
        return ""

    fast  = st.ema_fast
    mid   = st.ema_mid
    arena = st.ema_arena

    if not (fast.ready and mid.ready and arena.ready):
        return ""

    fast_now  = fast.get()
    fast_prev = fast.get_prev()
    mid_now   = mid.get()
    mid_prev  = mid.get_prev()
    arena_now = arena.get()

    if fast_prev is None or mid_prev is None:
        return ""

    # 공통 게이트: 종가 > EMA30 가 1차, EMA5/EMA10 > EMA30 가 2차
    close_now  = st.close_history[-1]
    long_arena = (close_now > arena_now) and (fast_now > arena_now) and (mid_now > arena_now)
    if not long_arena:
        log.debug(f"[ARENA_BLOCK] close={close_now:.8f} fast={fast_now:.8f} mid={mid_now:.8f} arena={arena_now:.8f}")
        return ""

    # Slope
    swing_lookback  = int(CFG["15_SWING_LOOKBACK"])
    slope_threshold = float(CFG["14_SLOPE_THRESHOLD"])
    ref = fast.get_lookback(swing_lookback)
    if ref is None or ref == 0:
        return ""
    slope_val = (fast_now - ref) / ref
    if slope_val < slope_threshold:
        return ""

    # E1: Golden cross — 변경 없음
    e1_signal = (fast_prev <= mid_prev) and (fast_now > mid_now)

    # E2: 눌림 후 재상승
    # [수정] 직전 캔들 종가도 EMA30 위였는지 추가 확인 → V자 가짜 반등 오진 방지
    tolerance = float(CFG["13_TOUCH_TOLERANCE"])
    if len(st.low_history) < 2 or len(st.close_history) < 2:
        return ""

    arena_prev = arena.get_prev()
    if arena_prev is None:
        return ""

    pullback              = st.low_history[-2] <= fast_prev * (1.0 + tolerance)
    reentry               = st.close_history[-1] > fast_now
    prev_close_above_arena = st.close_history[-2] > arena_prev  # [수정] 직전 종가 EMA30 위 확인
    e2_signal             = pullback and reentry and prev_close_above_arena

    log.debug(
        f"[ENTRY_CHECK] close={close_now:.8f} arena={arena_now:.8f} long_arena={long_arena} "
        f"slope={slope_val:.6f} e1={e1_signal} e2={e2_signal} "
        f"prev_close_above_arena={prev_close_above_arena}"
    )

    if e1_signal:
        return "E1"
    if CFG["23_ENTRY2_ENABLE"] and e2_signal:
        return "E2"
    return ""

# ============================================================
# EXIT
# ============================================================

def exit_signal(st: EngineState) -> bool:
    pos = st.position
    if pos is None:
        return False

    close = st.close_history[-1]

    if CFG["40_SL_ENABLE"]:
        sl = float(CFG["41_SL_PCT"]) / 100.0
        if close <= pos.entry_price * (1.0 - sl):
            log.info(f"[EXIT_SL] close={close} <= SL={pos.entry_price * (1.0 - sl)}")
            return True

    if CFG["50_TIMEOUT_EXIT_ENABLE"]:
        if pos.entry_type != "SYNC":
            if (st.bar - pos.entry_bar) >= int(CFG["51_TIMEOUT_BARS"]):
                log.info(f"[EXIT_TIMEOUT] bars={st.bar - pos.entry_bar}")
                return True

    ef = st.ema_exit_fast.get()
    em = st.ema_exit_mid.get()
    if ef is None or em is None:
        return False
    if ef < em:
        log.info(f"[EXIT_EMA_CROSS] ef={ef:.8f} em={em:.8f} close={close:.8f}")
        return True
    return False

# ============================================================
# EXECUTION
# ============================================================

def place_long_entry(client: "Client", symbol: str, capital_usdt: float, lot: Dict[str, Decimal]) -> Optional[Dict[str, Any]]:
    try:
        ticker   = client.futures_symbol_ticker(symbol=symbol)
        price    = float(ticker["price"])
        leverage = int(CFG["04_LEVERAGE"])
        notional = float(capital_usdt) * float(leverage)
        qty_raw  = notional / price
        qty_str  = calculate_quantity(qty_raw, lot)
        if qty_str is None:
            log.error("entry: qty calculation failed")
            return None
        order = client.futures_create_order(
            symbol=symbol,
            side=SIDE_BUY,
            type=ORDER_TYPE_MARKET,
            quantity=qty_str,
        )
        try:
            filled = client.futures_get_order(symbol=symbol, orderId=order["orderId"])
            avg_price = float(filled.get("avgPrice", 0))
            entry_price = avg_price if avg_price > 0 else price
        except Exception:
            entry_price = price
        return {"entry_price": entry_price, "qty": qty_str}
    except Exception as e:
        log.error(f"place_long_entry: {e}")
        return None

def place_long_exit(client: "Client", symbol: str, qty: str, lot: Dict[str, Decimal]) -> bool:
    try:
        qty2 = normalize_qty_str(qty, lot)
        if qty2 is None:
            log.error("exit: qty too small")
            return False
        client.futures_create_order(
            symbol=symbol,
            side=SIDE_SELL,
            type=ORDER_TYPE_MARKET,
            quantity=qty2,
            reduceOnly=True
        )
        return True
    except Exception as e:
        log.error(f"place_long_exit: {e}")
        return False

# ============================================================
# ENGINE LOOP
# ============================================================

STOP = False
def _sig_handler(_sig, _frame):
    global STOP
    STOP = True
signal.signal(signal.SIGINT, _sig_handler)
signal.signal(signal.SIGTERM, _sig_handler)

def _apply_bar(st: EngineState, close: float, high: float, low: float) -> None:
    st.close_history.append(close)
    st.high_history.append(high)
    st.low_history.append(low)

    st.ema_fast.update(close)
    st.ema_mid.update(close)
    st.ema_arena.update(close)
    st.ema_exit_fast.update(close)
    st.ema_exit_mid.update(close)

    st.ema_fast.trim_history()
    st.ema_mid.trim_history()
    st.ema_arena.trim_history()
    st.ema_exit_fast.trim_history()
    st.ema_exit_mid.trim_history()

def engine():
    client   = init_client()
    symbol   = CFG["01_TRADE_SYMBOL"]
    interval = CFG["02_INTERVAL"]
    capital  = float(CFG["03_CAPITAL_BASE_USDT"])

    set_leverage(client, symbol, int(CFG["04_LEVERAGE"]))

    lot = get_futures_lot_size(client, symbol)
    if lot is None:
        raise RuntimeError("lot_size retrieval failed")

    if not verify_account_safety(client, symbol, capital, lot):
        raise RuntimeError("계정 안전 확인 실패. 로그 확인 후 재시작하세요.")

    st = EngineState()

    try:
        positions = client.futures_position_information(symbol=symbol)
        for pos in positions:
            if pos['symbol'] == symbol:
                position_amt = float(pos['positionAmt'])
                if position_amt > 0:
                    sync_qty_str = calculate_quantity(abs(position_amt), lot)
                    if sync_qty_str is None:
                        log.error("[SYNC] qty calculation failed, skipping sync")
                    else:
                        st.position = Position(
                            side="LONG",
                            entry_price=float(pos['entryPrice']),
                            qty=sync_qty_str,
                            entry_bar=st.bar,
                            entry_type="SYNC"
                        )
                        log.info(f"[SYNC] Existing LONG position detected: qty={st.position.qty} entry={st.position.entry_price}")
                    break
    except Exception as e:
        log.error(f"position sync failed: {e}")

    log.info(
        f"START BR7 LONG | symbol={symbol} interval={interval} capital={capital} lev={CFG['04_LEVERAGE']} "
        f"| ENTRY_EMA=({CFG['10_EMA_FAST']},{CFG['11_EMA_MID']},{CFG['12_EMA_ARENA']}) "
        f"| EXIT_EMA=({CFG['30_EXIT_FAST_EMA']},{CFG['31_EXIT_MID_EMA']})"
    )

    while not STOP:
        try:
            kl = fetch_klines_futures(symbol, interval, int(CFG["90_KLINE_LIMIT"]))
            if not kl:
                time.sleep(CFG["91_POLL_SEC"])
                continue

            completed = kl[-2]
            open_time = int(completed[0])

            if st.last_open_time == open_time:
                time.sleep(CFG["91_POLL_SEC"])
                continue

            if not st.close_history:
                for k in kl[:-1]:
                    _apply_bar(st, float(k[4]), float(k[2]), float(k[3]))
                st.bar = len(st.close_history)
                st.last_open_time = int(kl[-2][0])
                log.info(f"[BOOT] {st.bar} bars loaded, EMA warm-up complete={_warmup_done(st)}")
                continue

            st.last_open_time = open_time
            st.bar += 1

            _apply_bar(st, float(completed[4]), float(completed[2]), float(completed[3]))

            if st.ema_fast.ready and st.ema_arena.ready:
                close_now      = st.close_history[-1]
                arena_now      = st.ema_arena.get()
                long_arena_now = (
                    (close_now > arena_now) and
                    (st.ema_fast.get() > arena_now) and
                    (st.ema_mid.get() > arena_now)
                )
                if long_arena_now != st.prev_arena_state:
                    if long_arena_now:
                        log.info(f"[ARENA] 통과 close={close_now:.8f} > arena={arena_now:.8f}")
                    else:
                        log.info(f"[ARENA] 차단 close={close_now:.8f} arena={arena_now:.8f}")
                    st.prev_arena_state = long_arena_now

            if st.position is None:
                entry_type = long_entry_signals(st)

                if entry_type:
                    order = place_long_entry(client, symbol, capital, lot)
                    if order:
                        st.position = Position(
                            side="LONG",
                            entry_price=float(order["entry_price"]),
                            qty=order["qty"],
                            entry_bar=st.bar,
                            entry_type=entry_type
                        )
                        log.info(f"[ENTRY] LONG type={entry_type} qty={st.position.qty} entry={st.position.entry_price} bar={st.bar}")
                    else:
                        log.error("[ENTRY_FAIL] order failed")
            else:
                if st.position.entry_bar == st.bar:
                    continue

                if exit_signal(st):
                    ok = place_long_exit(client, symbol, st.position.qty, lot)
                    if ok:
                        log.info(f"[EXIT] LONG type={st.position.entry_type} close={st.close_history[-1]} entry={st.position.entry_price} bar={st.bar}")
                        st.position = None
                        continue
                    else:
                        log.error("[EXIT_FAIL] order failed (position kept)")

        except Exception as e:
            log.error(f"engine loop error: {e}")
            time.sleep(CFG["91_POLL_SEC"])

    log.info("STOP BR7 LONG")

if __name__ == "__main__":
    engine()