from __future__ import annotations

from typing import Any

from quantbench.agent.llm import record_llm_usage
from quantbench.literature.paper import Paper

_SYSTEM_PROMPT = (
    "You are a quantitative-research reading assistant. The user has highlighted a passage in a "
    "finance paper and is asking about it. Answer ONLY from the provided passage and page context; "
    "if the answer isn't in the provided text, say so rather than guessing. Be concise and concrete. "
    "When the passage describes a factor/signal, explain how one would implement and test it. "
    "Answer in the user's language."
)


def answer_selection_question(
    llm,
    paper: Paper,
    *,
    selection: str,
    page: int | None,
    question: str,
    usage_sink: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Grounded Q&A over a highlighted PDF selection (the 'ask about this
    selection' flow). Grounds the model on the selection plus the surrounding
    page text so answers stay tied to the paper. Returns {answer, grounded_page}.
    A single bounded chat call - not a tool-using sub-agent - because this is an
    interactive, latency-sensitive reading aid, not a research run."""
    page_context = ""
    if page is not None:
        pages = paper.page_range_text(max(1, page - 1), page + 1)
        page_context = "\n\n".join(f"[page {p.page_number}]\n{p.text}" for p in pages)

    user_content = (
        f"Paper: {paper.citation()}\n\n"
        f"Highlighted passage:\n\"\"\"\n{selection.strip()}\n\"\"\"\n\n"
        f"Surrounding page context:\n{page_context or '(none provided)'}\n\n"
        f"Question: {question.strip()}"
    )
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    response = llm.chat(messages)
    record_llm_usage(response, getattr(llm, "model", "unknown"), usage_sink, step="literature_qa")
    answer = response.choices[0].message.content or ""
    return {"answer": answer.strip(), "grounded_page": page}
