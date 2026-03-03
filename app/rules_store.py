from __future__ import annotations

import json
from pathlib import Path

from .config import settings
from .models import Rule, RuleCreate, RuleUpdate


def _path() -> Path:
    p = Path(settings.rules_file)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load() -> list[Rule]:
    p = _path()
    if not p.exists():
        return []
    return [Rule.model_validate(r) for r in json.loads(p.read_text())]


def _save(rules: list[Rule]) -> None:
    _path().write_text(
        json.dumps([r.model_dump(mode="json") for r in rules], indent=2)
    )


def list_rules() -> list[Rule]:
    return _load()


def get_rule(rule_id: str) -> Rule | None:
    return next((r for r in _load() if r.id == rule_id), None)


def add_rule(data: RuleCreate) -> Rule:
    rules = _load()
    rule = Rule(description=data.description, route=data.route)
    rules.append(rule)
    _save(rules)
    return rule


def update_rule(rule_id: str, data: RuleUpdate) -> Rule | None:
    rules = _load()
    for i, rule in enumerate(rules):
        if rule.id == rule_id:
            updated = rule.model_copy(
                update={k: v for k, v in data.model_dump(exclude_none=True).items()}
            )
            rules[i] = updated
            _save(rules)
            return updated
    return None


def delete_rule(rule_id: str) -> bool:
    rules = _load()
    filtered = [r for r in rules if r.id != rule_id]
    if len(filtered) == len(rules):
        return False
    _save(filtered)
    return True
