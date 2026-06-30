"""The agent loop: ties together LLM + tools + conversation memory."""
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from config import LLM_MODEL, MAX_TOOL_TURNS
from tools import TOOLS, TOOLS_BY_NAME
from system_prompt import build_system_message

# ANSI colors for terminal — dim gray for Jarvis's internal "thinking" lines
DIM = "\033[2m"
RESET = "\033[0m"

llm = ChatGroq(model=LLM_MODEL).bind_tools(TOOLS)

conversation = []  # built up across turns


def _think(message):
    """Print an internal-thinking line in dim gray."""
    print(f"{DIM}Jarvis (thinking): {message}{RESET}")


def ask_jarvis(user_text):
    system_msg = build_system_message(user_text)
    messages = [system_msg] + [m for m in conversation if not isinstance(m, SystemMessage)]
    messages.append(HumanMessage(content=user_text))

    for turn in range(MAX_TOOL_TURNS):
        try:
            response = llm.invoke(messages)
        except Exception as e:
            err_msg = str(e)
            if "tool_use_failed" in err_msg or "Failed to" in err_msg:
                _think("tool call failed, trying a different approach")
                fallback = "I'm having trouble using my tools right now — try asking again."
                conversation.append(HumanMessage(content=user_text))
                conversation.append(SystemMessage(content=fallback))
                return fallback
            raise

        messages.append(response)
        if not response.tool_calls:
            conversation.append(HumanMessage(content=user_text))
            conversation.append(response)
            return response.content

        for call in response.tool_calls:
            tool_fn = TOOLS_BY_NAME.get(call["name"])
            if tool_fn is None:
                result = f"Unknown tool: {call['name']}"
            else:
                try:
                    result = tool_fn.invoke(call["args"])
                except Exception as e:
                    result = f"Tool error: {e}"

            # Compact preview so long tool outputs don't flood the terminal
            preview = str(result).replace("\n", " ")
            if len(preview) > 120:
                preview = preview[:120] + "..."
            _think(f"used {call['name']} → {preview}")

            messages.append(ToolMessage(content=str(result), tool_call_id=call["id"]))

    _think("okay, I have enough info — answering now")
    messages.append(HumanMessage(content="Stop using tools and give me a final answer now based on what you've found."))
    response = llm.invoke(messages)
    conversation.append(HumanMessage(content=user_text))
    conversation.append(response)
    return response.content