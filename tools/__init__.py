"""Expose all tools as a single TOOLS list.

`remember` / `forget` are deliberately NOT bound. They let the model write new facts to
user_profile.json mid-conversation, which is a second personalization channel alongside
the cold-start URL profile — with both live, an Arch 2 result can't be attributed to the
profile alone (see system_prompt.py). They still exist in tools/web.py for the jarvis.py
CLI and the eval harness.
"""
from tools.files import (
    create_file, read_file, list_files,
    move_file, request_delete, confirm_delete,
)
from tools.web import (
    web_search, verify_search_result, learn_about_user,
)

TOOLS = [
    create_file, read_file, list_files, move_file,
    request_delete, confirm_delete,
    web_search, verify_search_result, learn_about_user,
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}