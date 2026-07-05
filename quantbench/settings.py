from __future__ import annotations

import json
import warnings
from copy import deepcopy
from pathlib import Path
from typing import Any

from quantbench.config import PROJECT_SETTINGS_FILE, SETTINGS_FILES, USER_SETTINGS_FILE


def load_settings(files: list[Path] | tuple[Path, ...] | None = None) -> dict[str, Any]:
    """Load user + project settings, with later files overriding earlier files."""

    merged: dict[str, Any] = {}
    for path in files or SETTINGS_FILES:
        path = Path(path)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - config should be skipped with context
            warnings.warn(f"Skipping settings file {path}: {type(exc).__name__}: {exc}", stacklevel=2)
            continue
        if not isinstance(payload, dict):
            warnings.warn(f"Skipping settings file {path}: root must be an object.", stacklevel=2)
            continue
        merged = _deep_merge(merged, payload)
    return merged


def is_server_enabled(name: str, settings: dict[str, Any] | None = None) -> bool:
    disabled = ((settings or load_settings()).get("mcp") or {}).get("disabledServers") or []
    return name not in set(disabled if isinstance(disabled, list) else [])


def is_skill_enabled(name: str, settings: dict[str, Any] | None = None) -> bool:
    disabled = ((settings or load_settings()).get("skills") or {}).get("disabledSkills") or []
    return name not in set(disabled if isinstance(disabled, list) else [])


def set_server_enabled(name: str, enabled: bool, *, scope: str = "user") -> None:
    _set_enabled(("mcp", "disabledServers"), name, enabled, scope)


def set_skill_enabled(name: str, enabled: bool, *, scope: str = "user") -> None:
    _set_enabled(("skills", "disabledSkills"), name, enabled, scope)


def _set_enabled(keys: tuple[str, str], name: str, enabled: bool, scope: str) -> None:
    if enabled:
        # Enabling clears the name from EVERY scope's disable list, so an explicit "on" always
        # wins - including for a project-shipped default-disabled example server that a user turns
        # on from the Customize panel (which writes user scope). Without this, the project-scope
        # disable would keep overriding the user-scope enable and the toggle would appear broken.
        for path in SETTINGS_FILES:
            _set_disabled_item(path, keys, name, True, create_missing=False)
    else:
        _set_disabled_item(_settings_file_for_scope(scope), keys, name, False)


def _settings_file_for_scope(scope: str) -> Path:
    if scope == "user":
        return USER_SETTINGS_FILE
    if scope == "project":
        return PROJECT_SETTINGS_FILE
    raise ValueError("scope must be user or project")


def _set_disabled_item(
    path: Path, keys: tuple[str, str], name: str, enabled: bool, *, create_missing: bool = True
) -> None:
    # When enabling (removing from the disable list), skip files that don't exist or don't list the
    # name - there is nothing to clear, and we must not write spurious empty settings files.
    if enabled and not create_missing and not path.exists():
        return
    payload = _read_json_object(path)
    section = payload.setdefault(keys[0], {})
    if not isinstance(section, dict):
        section = {}
        payload[keys[0]] = section
    values = section.get(keys[1], [])
    if not isinstance(values, list):
        values = []
    disabled = {str(item) for item in values}
    if enabled:
        if not create_missing and name not in disabled:
            return
        disabled.discard(name)
    else:
        disabled.add(name)
    section[keys[1]] = sorted(disabled)
    _write_json(path, payload)


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} root must be an object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        elif isinstance(value, list) and isinstance(result.get(key), list):
            # Lists in settings are the disable lists (mcp.disabledServers, skills.disabledSkills).
            # Union them across scopes rather than replacing: a server/skill is disabled if disabled
            # at ANY scope, so a project-shipped default-disable and a user-scope disable both take
            # effect. Enabling clears the name from every scope (see _set_enabled).
            merged_list = list(result[key])
            for item in value:
                if item not in merged_list:
                    merged_list.append(item)
            result[key] = merged_list
        else:
            result[key] = deepcopy(value)
    return result
