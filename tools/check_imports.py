"""
Asserts that core/ never imports from app/.
One-way dependency: app/ -> contracts/ <- core/
"""
import ast
import pathlib
import sys

ROOT = pathlib.Path(__file__).parent.parent
CORE = ROOT / "core"

errors = []

for py_file in CORE.rglob("*.py"):
    tree = ast.parse(py_file.read_text())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = ""
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
            if module.startswith("app.") or module == "app":
                rel = py_file.relative_to(ROOT)
                errors.append(f"{rel}:{node.lineno}: core imports app ({module!r})")

if errors:
    print("FAIL — import direction violation:")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)

print("OK — core/ does not import app/")
