"""
Core isolation guard — invoked by PreToolUse hook.
If the file being edited is in core/, forces user confirmation.
Usage: python3 tools/core_guard.py <file_path>
Exit 1 = block (ask), Exit 0 = allow
"""
import sys

if len(sys.argv) < 2:
    sys.exit(0)

path = sys.argv[1]

# Normalize path separators
path_normalized = path.replace("\\", "/")

if "/core/" in path_normalized or path_normalized.startswith("core/"):
    print(
        f"\n⚠️  SECURE CORE PROTECTION\n"
        f"You are about to edit: {path}\n"
        f"This is in core/ (Secure Core — webhook verify, secret handling, idempotency).\n"
        f"Human review required. Are you sure? Run `make verify` after any change.\n"
    )
    sys.exit(1)  # exit 1 → hook triggers 'ask' permission decision

sys.exit(0)
