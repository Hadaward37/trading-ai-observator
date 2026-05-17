"""Quick diagnostic: test MT5 connection and symbol info."""
import sys
import datetime

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 not installed. Run: pip install MetaTrader5")
    sys.exit(1)

print("=" * 40)
print("MT5 Connection Diagnostic")
print("=" * 40)

ok = mt5.initialize()
if not ok:
    err = mt5.last_error()
    print("initialize() FAILED:", err)
    print()
    print("Checklist:")
    print("  1. MT5 (Clear) must be open and logged in")
    print("  2. Tools > Options > Expert Advisors > Allow DLL imports")
    sys.exit(1)

info = mt5.terminal_info()
acc = mt5.account_info()

print("Connected    :", info.connected if info else "N/A")
print("Build        :", info.build if info else "N/A")
print("Company      :", info.company if info else "N/A")
print("Login        :", acc.login if acc else "N/A")
print("Server       :", acc.server if acc else "N/A")
print("Balance      :", acc.balance if acc else "N/A")
print()

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
try:
    from app.config import settings
    symbols = settings.mt5_symbols_list
except Exception:
    symbols = ["WINM26", "WDOM26"]
for sym in symbols:
    sym_info = mt5.symbol_info(sym)
    if sym_info is None:
        print(f"[{sym}] NOT FOUND in terminal — check symbol name")
        continue

    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        print(f"[{sym}] found but no tick data (market may be closed)")
        continue

    ts = datetime.datetime.fromtimestamp(tick.time)
    print(f"[{sym}] bid={tick.bid:.2f}  ask={tick.ask:.2f}  last={tick.last:.2f}  time={ts}")

print()

# Test copy_ticks_from
first_sym = symbols[0] if symbols else "WINM26"
print(f"Testing copy_ticks_from on {first_sym} (last 5 seconds)...")
from_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=5)
ticks = mt5.copy_ticks_from(first_sym, from_dt, 100, mt5.COPY_TICKS_ALL)
if ticks is not None and len(ticks) > 0:
    print(f"  Got {len(ticks)} ticks")
    t = ticks[-1]
    print(f"  Last tick: time_msc={t['time_msc']}  last={t['last']:.2f}  flags={t['flags']}")
else:
    err = mt5.last_error()
    print(f"  No ticks returned (market closed or error: {err})")

mt5.shutdown()
print()
print("OK — MT5 diagnostic complete")
