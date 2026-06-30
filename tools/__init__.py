"""Expose all tools as a single TOOLS list."""
from tools.files import (
    create_file, read_file, list_files,
    move_file, request_delete, confirm_delete,
)
from tools.web import (
    web_search, verify_search_result, learn_about_user,
    remember, forget,
)

TOOLS = [
    create_file, read_file, list_files, move_file,
    request_delete, confirm_delete,
    web_search, verify_search_result, learn_about_user,
    remember, forget,
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}