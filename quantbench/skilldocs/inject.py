from __future__ import annotations

from quantbench.skilldocs.doc import SkillDoc


def build_augmented_system_prompt(base_prompt: str, skills: list[SkillDoc]) -> str:
    if not skills:
        return base_prompt
    sections = [
        base_prompt.rstrip(),
        "",
        "## Injected QuantBench Workflow Skills",
        "The base system rules above remain mandatory. The following Skills are additional workflow guidance for this request.",
    ]
    for skill in skills:
        sections.extend(
            [
                "",
                f"### Skill: {skill.name}",
                f"Description: {skill.description}",
                skill.body.strip(),
            ]
        )
        if skill.attachments:
            sections.append(f"Attached files available via read_skill_file: {', '.join(skill.attachments)}")
    return "\n".join(sections)
