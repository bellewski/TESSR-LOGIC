"""Safe command execution layer with allowlist restrictions."""
import subprocess
import shlex
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Allowlisted command prefixes for MVP
ALLOWED_COMMANDS = {
    "python": ["python", "python3"],
    "node": ["node", "npm", "npx"],
    "pip": ["pip", "pip3"],
    "git": ["git"],
    "echo": ["echo"],
    "ls": ["ls", "dir"],
}

BLOCKED_PATTERNS = [
    "rm -rf",
    "del /f",
    "format",
    ":(){",
    "$()",
    "`",
    "&&",
    "||",
    ">",
    "|",
    ";",
]


def is_command_allowed(command: str) -> tuple[bool, str]:
    """Check if a command is in the allowlist and not using blocked patterns."""
    cmd_lower = command.lower().strip()

    for pattern in BLOCKED_PATTERNS:
        if pattern in cmd_lower:
            return False, f"Blocked pattern detected: {pattern}"

    parts = shlex.split(command)
    if not parts:
        return False, "Empty command"

    base_cmd = Path(parts[0]).name.lower().replace(".exe", "")
    for group, allowed in ALLOWED_COMMANDS.items():
        if base_cmd in allowed:
            return True, ""

    return False, f"Command '{base_cmd}' is not in the allowlist"


def run_safe_command(command: str, cwd: str | None = None, timeout: int = 30) -> dict:
    """Execute a command only if it passes allowlist checks."""
    allowed, reason = is_command_allowed(command)
    if not allowed:
        logger.warning("Blocked command execution: %s — %s", command, reason)
        return {"success": False, "stdout": "", "stderr": reason, "returncode": -1}

    try:
        result = subprocess.run(
            shlex.split(command),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,  # Never use shell=True
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": f"Command timed out after {timeout}s", "returncode": -1}
    except FileNotFoundError as e:
        return {"success": False, "stdout": "", "stderr": f"Command not found: {e}", "returncode": -1}
    except Exception as e:
        logger.error("safe_exec error: %s", e)
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}
