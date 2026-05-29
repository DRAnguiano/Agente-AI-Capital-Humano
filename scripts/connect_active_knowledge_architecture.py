from pathlib import Path

APP_PATH = Path("app/app.py")

text = APP_PATH.read_text(encoding="utf-8")

replacements = {
    "from .orchestrator import orchestrate_message\n": "from .graphs.hr_graph import run_hr_graph_message\n",
    "from app.orchestrator import orchestrate_message\n": "from app.graphs.hr_graph import run_hr_graph_message\n",
}

changed = False
for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new, 1)
        changed = True

call_patterns = [
    "result = orchestrate_message(\n",
    "        result = orchestrate_message(\n",
]
for pattern in call_patterns:
    if pattern in text:
        text = text.replace(pattern, pattern.replace("orchestrate_message", "run_hr_graph_message"))
        changed = True

if not changed:
    print("OK: app.py already appears connected or import/call pattern was not found")
else:
    APP_PATH.write_text(text, encoding="utf-8")
    print("OK: app.py connected to app.graphs.hr_graph.run_hr_graph_message")
