import json

import pytest

from _fakes import FakeLLMClient
from quantbench.agent.subagent import SubAgent, run_subagent
from quantbench.skills.registry import Skill, SkillRegistry


def _agent(registry=None, max_turns=1):
    return SubAgent(
        name="test-agent",
        system_prompt="You are a test sub-agent.",
        registry=registry or SkillRegistry(),
        max_turns=max_turns,
        output_schema={"type": "object"},
    )


def test_run_subagent_parses_bare_json_final_answer():
    payload = {"verdict": "PROMISING", "critique": "looks fine"}
    llm = FakeLLMClient([("text", json.dumps(payload))])

    result = run_subagent(llm, _agent(), {"code": "def compute(df): ..."})

    assert result == payload


def test_run_subagent_strips_markdown_fence():
    payload = {"verdict": "WEAK"}
    fenced = f"```json\n{json.dumps(payload)}\n```"
    llm = FakeLLMClient([("text", fenced)])

    result = run_subagent(llm, _agent(), {})

    assert result == payload


def test_run_subagent_extracts_json_after_prose_reasoning():
    """Real DeepSeek behavior with tool use: prose reasoning, then a fenced
    ```json block. re.fullmatch on the whole message would miss it - the parser
    must find the fenced block despite the leading prose."""
    payload = {"verdict": "PROMISING", "critique": "ok"}
    content = (
        "Let me think about this. The evidence points one way.\n"
        "Now I'll construct the JSON.\n\n"
        f"```json\n{json.dumps(payload)}\n```"
    )
    llm = FakeLLMClient([("text", content)])

    assert run_subagent(llm, _agent(), {}) == payload


def test_run_subagent_extracts_bare_object_embedded_in_prose():
    """No code fence at all - a bare {...} object surrounded by prose."""
    payload = {"verdict": "WEAK", "note": "has a } brace and \"quoted {\" string"}
    content = f'Here is my answer: {json.dumps(payload)} - let me know if you need more.'
    llm = FakeLLMClient([("text", content)])

    assert run_subagent(llm, _agent(), {}) == payload


def test_run_subagent_dispatches_tool_calls_before_final_answer():
    registry = SkillRegistry()
    calls = []

    def _lookup(query: str) -> dict:
        calls.append(query)
        return {"answer": 42}

    registry.register(Skill("lookup", "look something up", {"type": "object", "properties": {}}, _lookup))

    script = [
        ("tools", [("lookup", {"query": "hello"})]),
        ("text", json.dumps({"verdict": "STRONG"})),
    ]
    llm = FakeLLMClient(script)

    result = run_subagent(llm, _agent(registry=registry, max_turns=3), {})

    assert result == {"verdict": "STRONG"}
    assert calls == ["hello"]


def test_run_subagent_raises_when_max_turns_exhausted_without_final_answer():
    registry = SkillRegistry()
    registry.register(Skill("noop", "does nothing", {"type": "object", "properties": {}}, lambda: {}))
    script = [("tools", [("noop", {})]), ("tools", [("noop", {})])]
    llm = FakeLLMClient(script)

    with pytest.raises(RuntimeError, match="did not produce a final answer"):
        run_subagent(llm, _agent(registry=registry, max_turns=2), {})


def test_run_subagent_raises_on_malformed_json():
    llm = FakeLLMClient([("text", "not json at all")])

    with pytest.raises(json.JSONDecodeError):
        run_subagent(llm, _agent(), {})


def test_run_subagent_raises_on_non_object_json():
    llm = FakeLLMClient([("text", "[1, 2, 3]")])

    with pytest.raises(ValueError, match="must be a JSON object"):
        run_subagent(llm, _agent(), {})
