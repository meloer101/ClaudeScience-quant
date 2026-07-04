import json
import re
from dataclasses import dataclass
from typing import Any

from quantbench.agent.llm import record_llm_usage
from quantbench.skills.registry import SkillRegistry


@dataclass(frozen=True)
class SubAgent:
    name: str
    system_prompt: str
    registry: SkillRegistry  # empty SkillRegistry() for pure-reasoning agents like Critic
    max_turns: int
    output_schema: dict


def run_subagent(
    llm,
    agent: SubAgent,
    user_payload: dict[str, Any],
    *,
    usage_sink: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Runs a bounded LLM conversation for a named sub-agent role and returns
    its final answer parsed as JSON. Any tool calls the model makes along the
    way (if agent.registry has tools registered) are dispatched through
    agent.registry.execute, capped at agent.max_turns turns - the same shape
    as the main coordinator loop, but returning parsed JSON instead of raw
    text. Raises on malformed JSON, an unproductive max_turns, or an LLM
    failure - unlike the main coordinator loop, callers are expected to
    define their own role-specific fallback (e.g. run_critic's
    status="unavailable" CriticReport), since no single generic fallback
    shape fits every sub-agent's output schema.

    usage_sink (GAP 5.4): pass ctx.llm_usage so this sub-agent's token/cost
    footprint is visible in the manifest instead of vanishing - Critic and
    the memory-consolidation agent both run through here and were previously
    invisible to any cost accounting."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
    ]

    for _ in range(agent.max_turns):
        response = llm.chat(messages, tools=agent.registry.schemas())
        record_llm_usage(response, getattr(llm, "model", "unknown"), usage_sink, step=f"subagent:{agent.name}")
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None)
        if not tool_calls:
            return _parse_json(message.content or "")

        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in tool_calls
                ],
            }
        )
        for call in tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = agent.registry.execute(call.function.name, args)
            messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(result, default=str)})

    raise RuntimeError(f"sub-agent {agent.name!r} did not produce a final answer within {agent.max_turns} turn(s)")


def _parse_json(content: str) -> dict[str, Any]:
    """Extract a JSON object from a sub-agent's final message. Models don't
    always return pure JSON: some (e.g. DeepSeek with tool use) emit prose
    reasoning followed by a ```json fenced block, or a bare object embedded in
    surrounding text. We try, in order: the whole string; a fenced block found
    anywhere; then the first balanced {...} object. Each candidate is only
    tried after the previous one fails, so a well-behaved pure-JSON response
    (the Critic's usual output) parses on the first attempt exactly as before."""
    text = content.strip()
    for candidate in _json_candidates(text):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            raise ValueError("sub-agent response must be a JSON object")
        return payload
    raise json.JSONDecodeError("no JSON object found in sub-agent response", text or "", 0)


def _json_candidates(text: str):
    yield text
    # Fenced block anywhere in the message (search, not fullmatch, so leading
    # prose like "Now I'll construct the JSON:" doesn't defeat it).
    for match in re.finditer(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL):
        yield match.group(1)
    # First balanced top-level {...} object, respecting strings and escapes.
    balanced = _first_balanced_object(text)
    if balanced is not None:
        yield balanced


def _first_balanced_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
            elif char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        start = text.find("{", start + 1)
    return None
