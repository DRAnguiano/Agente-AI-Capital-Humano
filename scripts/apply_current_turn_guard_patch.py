from pathlib import Path

APP_PATH = Path("app/app.py")

text = APP_PATH.read_text(encoding="utf-8")

old = "from .orchestrator import orchestrate_message\n"
new = "from .orchestrator_guard import orchestrate_message\n"

if new in text:
    print("OK: app.py already uses orchestrator_guard")
elif old in text:
    text = text.replace(old, new, 1)
    APP_PATH.write_text(text, encoding="utf-8")
    print("OK: app.py now imports orchestrator_guard")
else:
    raise SystemExit("ERROR: could not find orchestrator import in app/app.py")
