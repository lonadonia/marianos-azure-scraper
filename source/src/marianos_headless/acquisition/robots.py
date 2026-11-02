"""robots.txt parsing and allow checks (RFC 9309: ``*`` and ``$`` wildcards, longest match wins,
Allow wins ties). The ``*`` group applies: the browser does not present its own product token."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from urllib.parse import unquote, urlsplit


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str

    def regex(self) -> re.Pattern[str]:
        out = []
        for ch in self.pattern:
            if ch == "*":
                out.append(".*")
            elif ch == "$":
                out.append("$")
            else:
                out.append(re.escape(ch))
        return re.compile("".join(out))

    def matches(self, path: str) -> bool:
        return self.regex().match(path) is not None

    @property
    def specificity(self) -> int:
        return len(self.pattern.replace("*", "").replace("$", ""))


@dataclass
class RobotsPolicy:
    rules: list[Rule] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    sha256: str = ""

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        path = unquote(parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        best: Rule | None = None
        for rule in self.rules:
            if not rule.pattern:
                continue  # an empty Disallow allows everything
            if rule.matches(path) and (
                best is None
                or rule.specificity > best.specificity
                or (rule.specificity == best.specificity and rule.allow and not best.allow)
            ):
                best = rule
        return best is None or best.allow

    def disallowed_patterns(self) -> list[str]:
        return [r.pattern for r in self.rules if not r.allow and r.pattern]


def parse_robots(text: str, user_agent: str = "*") -> RobotsPolicy:
    groups: list[tuple[set[str], list[Rule]]] = []
    sitemaps: list[str] = []
    agents: set[str] = set()
    rules: list[Rule] = []
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if not last_was_agent and (agents or rules):
                groups.append((agents, rules))
                agents, rules = set(), []
            agents.add(value.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if key in ("allow", "disallow"):
            rules.append(Rule(key == "allow", value))
        elif key == "sitemap":
            sitemaps.append(value)
    if agents or rules:
        groups.append((agents, rules))
    ua = user_agent.lower()
    chosen = [r for a, rs in groups if ua in a for r in rs]
    if not chosen:
        chosen = [r for a, rs in groups if "*" in a for r in rs]
    return RobotsPolicy(chosen, sitemaps, hashlib.sha256(text.encode("utf-8")).hexdigest())
