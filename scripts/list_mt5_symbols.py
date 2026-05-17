"""List all MT5 symbols matching a pattern — helps find correct symbol names."""
import sys

try:
    import MetaTrader5 as mt5
except ImportError:
    print("ERROR: MetaTrader5 not installed.")
    sys.exit(1)

if not mt5.initialize():
    print("MT5 initialize failed:", mt5.last_error())
    sys.exit(1)

search_terms = ["WIN", "WDO", "IND", "DOL"]

print("Searching for Brazilian futures symbols in MT5 terminal...")
print("(Only symbols visible in Market Watch will appear)\n")

all_symbols = mt5.symbols_get()
if all_symbols is None:
    print("No symbols found. Make sure symbols are visible in Market Watch.")
    print("In MT5: right-click Market Watch > Show All, then search for WIN/WDO")
    mt5.shutdown()
    sys.exit(0)

found = []
for sym in all_symbols:
    name_upper = sym.name.upper()
    for term in search_terms:
        if term in name_upper:
            found.append(sym.name)
            break

if found:
    print(f"Found {len(found)} matching symbols:")
    for name in sorted(found):
        info = mt5.symbol_info(name)
        tick = mt5.symbol_info_tick(name)
        last = tick.last if tick else 0.0
        print(f"  {name:<20} last={last:.2f}")
else:
    print("No WIN/WDO/IND/DOL symbols found in Market Watch.")
    print()
    print("To add them:")
    print("  1. In MT5, press Ctrl+M to open Market Watch")
    print("  2. Right-click > Symbols")
    print("  3. Search 'WIN' and add WINM25 (or current contract)")
    print("  4. Search 'WDO' and add WDOM25 (or current contract)")
    print()
    print("All available symbols (first 30):")
    for sym in list(all_symbols)[:30]:
        print(f"  {sym.name}")

mt5.shutdown()
