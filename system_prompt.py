"""Build the dynamic system prompt with retrieved preference examples and user profile."""
from langchain_core.messages import SystemMessage
from preferences import retrieve_examples
from user_profile import get_profile_summary


def build_system_message(current_query):
    base = (
        "You are Jarvis, a helpful voice assistant. "
        "You can manage files in a sandbox and search the web using your tools. "
        "Keep spoken replies short, 1-2 sentences. "
        "WEB SEARCH: Use web_search whenever the user asks about current events, news, "
        "weather, sports scores, stock prices, recent releases, or anything that may have "
        "changed recently. Do not guess from memory — if you're not certain the information "
        "is current and accurate, search. Do NOT search for general knowledge, definitions, "
        "math, coding help, or things in our conversation history. "
        "QUERY SPECIFICITY: When using web_search, write specific queries with disambiguators. "
        "For a place, include state and country (e.g., 'Laguna Beach California USA weather' "
        "not 'Laguna Beach weather'). For people, include context (e.g., 'Tim Cook Apple CEO' "
        "not 'Tim Cook'). For events, include the year. Specific queries return correct results. "
        "GROUNDING: When the user disputes information you got from web_search, do not "
        "simply agree with them. Either re-search to verify, or stick with your sourced "
        "answer and tell them where it came from. Do not invent numbers to match the "
        "user's claim. "
        "AFTER you've gathered enough information from a tool to answer the user's question, "
        "STOP using tools and give the answer in plain text. Do NOT call additional tools "
        "unrelated to what the user asked. One tool call is usually enough — only chain "
        "tools if the user explicitly asks for multiple things in one request. "
        "FILE DELETION: To delete a file, first call request_delete, then tell the user "
        "exactly what will be deleted and ask them to confirm. Only call confirm_delete "
        "after the user clearly says yes. If they say no or seem unsure, do not delete."
    )

    # Inject user profile (from URL onboarding) if available
    profile_summary = get_profile_summary()
    if profile_summary:
        base += f"\n\nWHAT YOU KNOW ABOUT THE USER:\n{profile_summary}"

    # Inject retrieved preference examples (in-context RLHF)
    good, bad = retrieve_examples(current_query)
    if good or bad:
        base += "\n\nLEARNED USER PREFERENCES:"
    if good:
        base += "\n\nThe user rated these past responses HIGHLY — imitate their style:"
        for ex in good:
            base += f"\n  User asked: \"{ex['query']}\"\n  You said: \"{ex['reply']}\""
    if bad:
        base += "\n\nThe user rated these past responses POORLY — avoid this style:"
        for ex in bad:
            base += f"\n  User asked: \"{ex['query']}\"\n  You said: \"{ex['reply']}\""

    return SystemMessage(content=base)