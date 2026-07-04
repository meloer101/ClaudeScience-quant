from __future__ import annotations

from pathlib import Path

from quantbench.config import SKILL_DOCS_DIR
from quantbench.skilldocs.doc import SkillDoc, parse_skill_md


class SkillRegistryDocs:
    def __init__(self, docs_dir: Path = SKILL_DOCS_DIR) -> None:
        self.docs_dir = Path(docs_dir)

    def load_all(self) -> list[SkillDoc]:
        if not self.docs_dir.exists():
            return []
        paths = [*self.docs_dir.glob("*/SKILL.md"), *self.docs_dir.glob("*.md")]
        docs = []
        for path in sorted(paths, key=lambda item: (item.parent.name if item.name == "SKILL.md" else item.stem, item.name)):
            doc = parse_skill_md(path)
            if path.name == "SKILL.md":
                doc = SkillDoc(
                    name=doc.name,
                    description=doc.description,
                    triggers=doc.triggers,
                    body=doc.body,
                    path=doc.path,
                    attachments=_skill_attachments(path.parent),
                )
            else:
                doc = SkillDoc(
                    name=doc.name,
                    description=doc.description,
                    triggers=doc.triggers,
                    body=doc.body,
                    path=doc.path,
                    attachments=[],
                )
            docs.append(doc)
        return docs

    def get(self, name: str) -> SkillDoc:
        for doc in self.load_all():
            if doc.name == name:
                return doc
        raise FileNotFoundError(name)

    def match(self, request_text: str, *, limit: int = 3) -> list[SkillDoc]:
        text = request_text.lower()
        matches: list[tuple[int, SkillDoc]] = []
        for doc in self.load_all():
            score = sum(1 for trigger in doc.triggers if trigger.lower() in text)
            if score:
                matches.append((score, doc))
        matches.sort(key=lambda item: (-item[0], item[1].name))
        return [doc for _, doc in matches[:limit]]


def _skill_attachments(skill_dir: Path) -> list[str]:
    files = []
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file() or path.name == "SKILL.md":
            continue
        files.append(path.relative_to(skill_dir).as_posix())
    return files
