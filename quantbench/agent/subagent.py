import json
import re
from dataclasses import dataclass
from typing import Any

from quantbench.skills.registry import SkillRegistry


@dataclass(frozen=True)
class SubAgent:
    name: str
    system_prompt: str
    registry: SkillRegistry  # empty SkillRegistry() for pure-reasoning agents like Critic
    max_turns: int
    output_schema: dict


def run_subagent(llm, agent: SubAgent, user_payload: dict[str, Any]) -> dict[str, Any]:
    """Runs a bounded LLM conversation for a named sub-agent role and returns
    its final answer parsed as JSON. Any tool calls the model makes along the
    way (if agent.registry has tools registered) are dispatched through
    agent.registry.execute, capped at agent.max_turns turns - the same shape
    as the main coordinator loop, but returning parsed JSON instead of raw
    text. Raises on malformed JSON, an unproductive max_turns, or an LLM
    failure - unlike the main coordinator loop, callers are expected to
    define their own role-specific fallback (e.g. run_critic's
    status="unavailable" CriticReport), since no single generic fallback
    shape fits every sub-agent's output schema."""
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": agent.system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
    ]

    for _ in range(agent.max_turns):
        response = llm.chat(messages, tools=agent.registry.schemas())
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
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("sub-agent response must be a JSON object")
    return payload
