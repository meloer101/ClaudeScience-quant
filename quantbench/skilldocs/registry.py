from __future__ import annotations

from pathlib import Path

from quantbench.config import SKILL_DOCS_DIR, USER_SKILL_DOCS_DIR
from quantbench.settings import is_skill_enabled, load_settings
from quantbench.skilldocs.doc import SkillDoc, parse_skill_md


class SkillRegistryDocs:
    def __init__(self, docs_dir: Path | list[Path] | tuple[Path, ...] | None = None, *, include_disabled: bool = False) -> None:
        if docs_dir is None:
            self.docs_dirs = [USER_SKILL_DOCS_DIR, SKILL_DOCS_DIR]
        elif isinstance(docs_dir, (list, tuple)):
            self.docs_dirs = [Path(item) for item in docs_dir]
        else:
            self.docs_dirs = [Path(docs_dir)]
        self.include_disabled = include_disabled

    def load_all(self) -> list[SkillDoc]:
        by_name: dict[str, SkillDoc] = {}
        settings = load_settings()
        for docs_dir in self.docs_dirs:
            if not docs_dir.exists():
                continue
            scope = "user" if docs_dir == USER_SKILL_DOCS_DIR else "project"
            paths = [*docs_dir.glob("*/SKILL.md"), *docs_dir.glob("*.md")]
            for path in sorted(paths, key=lambda item: (item.parent.name if item.name == "SKILL.md" else item.stem, item.name)):
                doc = parse_skill_md(path)
                if not self.include_disabled and not is_skill_enabled(doc.name, settings):
                    continue
                attachments = _skill_attachments(path.parent) if path.name == "SKILL.md" else []
                by_name[doc.name] = SkillDoc(
                    name=doc.name,
                    description=doc.description,
                    triggers=doc.triggers,
                    body=doc.body,
                    path=doc.path,
                    attachments=attachments,
                    scope=scope,
                )
        return sorted(by_name.values(), key=lambda doc: doc.name)

    def get(self, name: str) -> SkillDoc:
        for doc in self.load_all():
            if doc.name == name:
                return doc
        raise FileNotFoundError(name)

    def match(self, request_text: str, *, limit: int = 3) -> list[SkillDoc]:
        text = request_text.lower()
        trigger_matches: list[tuple[int, SkillDoc]] = []
        description_matches: list[tuple[int, SkillDoc]] = []
        for doc in self.load_all():
            score = sum(1 for trigger in doc.triggers if trigger.lower() in text)
            if score:
                trigger_matches.append((score, doc))
            elif _description_match_count(doc.description, text) >= 2:
                description_matches.append((1, doc))
        trigger_matches.sort(key=lambda item: (-item[0], item[1].name))
        description_matches.sort(key=lambda item: (-item[0], item[1].name))
        matches = [*trigger_matches, *description_matches]
        return [doc for _, doc in matches[:limit]]


def _skill_attachments(skill_dir: Path) -> list[str]:
    files = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        files.append(path.relative_to(skill_dir).as_posix())
    return files


def _description_match_count(description: str, text: str) -> int:
    separators = str.maketrans({"/": " ", "-": " ", "_": " ", ".": " ", ",": " ", "(": " ", ")": " "})
    words = {
        word
        for word in description.lower().translate(separators).split()
        if len(word) >= 4 and word not in {"workflow", "analysis", "research", "quantbench"}
    }
    return sum(1 for word in words if word in text)
