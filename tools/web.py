"""Web search, result verification, URL profile learning, and fact memory tools."""
import os
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from tavily import TavilyClient
from config import LLM_MODEL
from user_profile import learn_from_url, remember_fact, forget_fact

tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
llm_raw = ChatGroq(model=LLM_MODEL)


@tool
def web_search(query: str) -> str:
    """Search the web for current information. Use this for news, current events,
    weather, sports scores, facts you're not sure about, or anything that might have
    changed recently. Returns a short summary of the top results."""
    try:
        result = tavily.search(
            query=query,
            max_results=5,
            search_depth="advanced",  # richer per-result content; 2x credits but better grounding
            include_answer=True,
        )
        out = ""
        if result.get("answer"):
            out += f"Quick answer: {result['answer']}\n\n"
        out += "Sources:\n"
        for r in result.get("results", []):
            out += f"- {r['title']}: {r['content'][:1500]}\n"
        return out
    except Exception as e:
        return f"Search failed: {e}"


@tool
def verify_search_result(question: str, retrieved_data: str) -> str:
    """Check if retrieved web data actually answers the user's question.
    Returns 'OK' if the data matches what was asked, or describes what's wrong.
    Be especially strict about: location matching the query, dates matching,
    and consistency between sources. If different sources in the data contradict
    each other (e.g., two different scores for the same match), flag it."""
    check = llm_raw.invoke([
        SystemMessage(content=(
            "You are a fact-checker. Reply 'OK' if the retrieved data clearly and "
            "consistently answers the question. Otherwise describe the problem in "
            "one sentence. Watch for: wrong entity (e.g., wrong city/country), wrong "
            "date, OR internal contradictions where multiple sources in the data give "
            "different facts. Be skeptical — if anything looks off, do not say OK."
        )),
        HumanMessage(content=f"Question: {question}\n\nRetrieved data:\n{retrieved_data}")
    ])
    return check.content


@tool
def learn_about_user(url: str) -> str:
    """Fetch a URL (the user's personal webpage, blog, GitHub profile, or social media link)
    and learn about the user so Jarvis can personalize future responses. Returns a summary
    of what was learned. Use ONLY when the user explicitly asks Jarvis to learn about them
    from a URL — e.g., 'read my GitHub' or 'check this profile and learn about me'."""
    return learn_from_url(url)


@tool
def remember(fact: str) -> str:
    """Save a fact about the user to long-term memory. Use this whenever the user shares
    something they want you to remember, or any preference/personal detail that would help
    future conversations — e.g., 'I'm vegetarian', 'my partner's name is Asha', 'I prefer
    short answers', 'I work night shifts'. The fact should be a complete, self-contained
    sentence (e.g., 'The user is vegetarian' not just 'vegetarian')."""
    return remember_fact(fact)


@tool
def forget(topic: str) -> str:
    """Remove remembered facts that match a topic or phrase. Use when the user says
    'forget that I...' or 'don't remember that anymore'. Pass a few keywords from the
    fact to remove (e.g., 'vegetarian' will remove any remembered fact mentioning that)."""
    return forget_fact(topic)