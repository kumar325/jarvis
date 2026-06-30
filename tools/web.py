"""Web search and result verification tools."""
import os
from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from tavily import TavilyClient
from config import LLM_MODEL
from user_profile import learn_from_url


tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))

# A tool-less LLM used by verify_search_result to fact-check retrievals
llm_raw = ChatGroq(model=LLM_MODEL)

@tool
def web_search(query: str) -> str:
    """Search the web for current information. Use this for news, current events,
    weather, sports scores, facts you're not sure about, or anything that might have
    changed recently. Returns a short summary of the top results."""
    try:
        result = tavily.search(
            query=query,
            max_results=3,
            search_depth="basic",
            include_answer=True,
        )
        out = ""
        if result.get("answer"):
            out += f"Quick answer: {result['answer']}\n\n"
        out += "Sources:\n"
        for r in result.get("results", []):
            out += f"- {r['title']}: {r['content'][:800]}\n"
        return out
    except Exception as e:
        return f"Search failed: {e}"

@tool
def verify_search_result(question: str, retrieved_data: str) -> str:
    """Check if retrieved web data actually answers the user's question.
    Returns 'OK' if the data matches what was asked, or describes what's wrong."""
    check = llm_raw.invoke([
        SystemMessage(content="You are a fact-checker. Reply 'OK' if the retrieved data clearly answers the question. Otherwise describe the mismatch in one sentence."),
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