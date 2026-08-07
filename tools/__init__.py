"""Expose all tools as a single TOOLS list.

Three tools are deliberately NOT bound, all for the same reason: each lets the model write
to user_profile.json mid-conversation, which is a second personalization channel alongside
the cold-start profile. With any of them live, an Arch 2 result can't be attributed to the
cold start alone (see system_prompt.py). They still exist in tools/web.py for the jarvis.py
CLI and the eval harness.

`remember` / `forget` — append or drop individual facts.

`learn_about_user` — the worst of the three, and unbound last. It wraps learn_from_url,
which OVERWRITES profile["summary"] outright. A participant volunteering a link mid-session
("here's my LinkedIn") during the internship task would replace the profile that was seeded
before the session — so the cold start would no longer be a cold start, and if it happened
during the first arm the second arm would then run against a different profile entirely.
Nothing downstream records that it happened. Seeding belongs in reset_user_state.py, once
per participant, before the session starts.
"""
from tools.files import (
    create_file, read_file, list_files,
    move_file, request_delete, confirm_delete,
)
from tools.web import (
    web_search, verify_search_result,
)

TOOLS = [
    create_file, read_file, list_files, move_file,
    request_delete, confirm_delete,
    web_search, verify_search_result,
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}