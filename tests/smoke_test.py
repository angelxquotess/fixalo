"""tests/smoke_test.py — test rapidi offline per fix e addon (no API)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ok, fail = 0, 0

def check(name, fn):
    global ok, fail
    try:
        fn()
        ok += 1
        print(f"  ✅ {name}")
    except Exception as e:
        fail += 1
        print(f"  ❌ {name}: {e}")

print("== Smoke test addon ==")
from addons import fun_tools, productivity, network_tools

check("calc", lambda: (_ for _ in ()).throw(AssertionError())
      if fun_tools.calc("2+2*3") != "8" else None)
check("convert km->mi", lambda: (_ for _ in ()).throw(AssertionError())
      if "0.62" not in fun_tools.convert(1, "km", "mi") else None)
check("gen_password len", lambda: (_ for _ in ()).throw(AssertionError())
      if len(fun_tools.gen_password(20)) != 20 else None)
check("note_add/list", lambda: (_ for _ in ()).throw(AssertionError())
      if not productivity.note_list() and not productivity.note_add("test") else None)
check("text_transform", lambda: (_ for _ in ()).throw(AssertionError())
      if fun_tools.text_transform("ciao", "upper") != "CIAO" else None)
check("registry size", lambda: (_ for _ in ()).throw(AssertionError())
      if len(__import__("addons").REGISTRY) < 60 else None)

print("== Smoke test fix (import & sintassi) ==")
check("main.py compila", lambda: compile(
    Path("main.py").read_text(encoding="utf-8"), "main.py", "exec"))
check("ui.py compila", lambda: compile(
    Path("ui.py").read_text(encoding="utf-8"), "ui.py", "exec"))
check("jarvis_perf importabile", lambda: __import__("jarvis_perf"))

print(f"\nRisultato: {ok} OK, {fail} falliti")
sys.exit(1 if fail else 0)
