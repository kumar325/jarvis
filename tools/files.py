"""File management tools. All ops sandboxed to SANDBOX directory."""
import shutil
from langchain_core.tools import tool
from config import SANDBOX

def safe_path(name):
    target = (SANDBOX / name).resolve()
    if not str(target).startswith(str(SANDBOX)):
        raise ValueError("Path escapes the sandbox — not allowed.")
    return target

@tool
def create_file(name: str, content: str = "") -> str:
    """Create a new text file in the sandbox with the given name and content."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    path.write_text(content, encoding="utf-8")
    return f"Created file '{name}'."

@tool
def read_file(name: str) -> str:
    """Read and return the contents of a file in the sandbox."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    if not path.exists():
        return f"File '{name}' does not exist."
    if not path.is_file():
        return f"'{name}' is not a readable file."
    return path.read_text(encoding="utf-8")

@tool
def list_files() -> str:
    """List all files currently in the sandbox folder."""
    files = [f.name for f in SANDBOX.iterdir() if f.is_file()]
    return "Files: " + ", ".join(files) if files else "The sandbox is empty."

@tool
def move_file(name: str, new_name: str) -> str:
    """Move or rename a file within the sandbox. Use new_name as the destination filename."""
    if not name or not new_name:
        return "Error: both source and destination filenames are required."
    src = safe_path(name)
    dst = safe_path(new_name)
    if not src.exists():
        return f"File '{name}' does not exist."
    if not src.is_file():
        return f"'{name}' is not a movable file."
    shutil.move(str(src), str(dst))
    return f"Moved '{name}' to '{new_name}'."

@tool
def request_delete(name: str) -> str:
    """Request deletion of a file. This does NOT delete it — it asks the user to confirm first.
    Always call this before confirm_delete. After calling, tell the user what will be deleted
    and ask them to confirm out loud."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    if not path.exists():
        return f"File '{name}' does not exist, nothing to delete."
    if not path.is_file():
        return f"'{name}' is not a deletable file."
    return f"Ready to delete '{name}'. Ask the user to confirm before calling confirm_delete."

@tool
def confirm_delete(name: str) -> str:
    """Permanently delete a file. ONLY call this after the user has clearly said yes
    to a deletion you previously requested with request_delete."""
    if not name or not name.strip():
        return "Error: filename is required."
    path = safe_path(name)
    if not path.exists():
        return f"File '{name}' does not exist."
    if not path.is_file():
        return f"'{name}' is not a deletable file."
    path.unlink()
    return f"Deleted '{name}'."