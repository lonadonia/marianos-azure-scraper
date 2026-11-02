"""Taxonomy IDs, listing URLs and the site menu (brief §4.3, §5.5).

IDs are hierarchical: 2 digits = department, 5 = category, 10 = subcategory; a child starts with its
parent's ID. Nodes are always keyed by ID, never by slug, because menu URLs are sometimes malformed
(``/pl/hard-cider08194``, ``…/05009?facets=true?pzn=relevance``, ``/pl/milk-plant-based-%20milk/02001``).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any
from urllib.parse import unquote, urlsplit

LEVEL_BY_LENGTH = {2: 2, 5: 5, 10: 10}
_VALID_ID = re.compile(r"^(\d{2}|\d{5}|\d{10})$")
_TRAILING_ID = re.compile(r"(\d{10}|\d{5}|\d{2})$")


@dataclass(frozen=True)
class ParsedTaxonomyUrl:
    taxonomy_id: str
    slug: str | None
    malformed: bool  # the ID had to be recovered from a broken URL


def is_taxonomy_id(value: str) -> bool:
    return bool(_VALID_ID.match(value))


def level(taxonomy_id: str) -> int:
    if not is_taxonomy_id(taxonomy_id):
        raise ValueError(f"not a taxonomy id: {taxonomy_id!r}")
    return len(taxonomy_id)


def parent_id(taxonomy_id: str) -> str | None:
    lvl = level(taxonomy_id)
    if lvl == 10:
        return taxonomy_id[:5]
    if lvl == 5:
        return taxonomy_id[:2]
    return None


def ancestors_or_self(taxonomy_id: str) -> list[str]:
    out = [taxonomy_id]
    p = parent_id(taxonomy_id)
    while p is not None:
        out.append(p)
        p = parent_id(p)
    return out


def is_within(node_id: str, root_id: str) -> bool:
    """``node_id`` is ``root_id`` or one of its descendants."""
    return level(node_id) >= level(root_id) and node_id.startswith(root_id)


def taxonomy_id_from_url(url: str) -> ParsedTaxonomyUrl | None:
    """Recover the taxonomy ID from a ``/pl/`` (or ``/pb/``) URL, tolerating known malformations."""
    path = unquote(urlsplit(url).path)
    # A second "?" inside the query never reaches the path, so only the path is inspected.
    segments = [s for s in path.split("/") if s]
    if not segments or segments[0] not in ("pl", "pb"):
        return None
    tail = segments[1:]
    if not tail:
        return None
    last = tail[-1]
    slug = tail[-2] if len(tail) >= 2 else None
    if is_taxonomy_id(last):
        malformed = segments[0] == "pl" and len(tail) != 2
        return ParsedTaxonomyUrl(last, slug, malformed or " " in (slug or ""))
    m = _TRAILING_ID.search(last)
    if m and len(tail) == 1:
        # "/pl/hard-cider08194": the slash between slug and ID is missing.
        return ParsedTaxonomyUrl(m.group(1), last[: m.start()].rstrip("-") or None, True)
    return None


class LinkKind(StrEnum):
    TAXONOMY = "taxonomy"  # /pl/<slug>/<id>
    DEPARTMENT_LANDING = "department_landing"  # /d/<slug>
    CURATED_SEARCH = "curated_search"  # /search?…searchType=mktg attribute
    BRAND_SEARCH = "brand_search"  # /search?brandName=…
    OTHER = "other"


@dataclass(frozen=True)
class MenuLink:
    titles: tuple[str, ...]  # title path from the menu root to this link
    url: str
    kind: LinkKind
    taxonomy_id: str | None = None
    landing_slug: str | None = None
    malformed_url: bool = False

    @property
    def title(self) -> str:
        return self.titles[-1]


@dataclass
class MenuNode:
    title: str
    type: str
    url: str | None
    children: list[MenuNode] = field(default_factory=list)

    def walk(self, path: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], MenuNode]]:
        here = (*path, self.title)
        yield here, self
        for child in self.children:
            yield from child.walk(here)

    def links(self, path: tuple[str, ...] = ()) -> list[MenuLink]:
        return [classify_link(p, n.url) for p, n in self.walk(path) if n.url]


def classify_link(titles: tuple[str, ...], url: str) -> MenuLink:
    parts = urlsplit(url)
    path = parts.path
    query = unquote(parts.query).lower()
    if path.startswith(("/pl/", "/pb/")):
        parsed = taxonomy_id_from_url(url)
        if parsed is not None:
            return MenuLink(titles, url, LinkKind.TAXONOMY, parsed.taxonomy_id, None, parsed.malformed)
    if path.startswith("/d/"):
        return MenuLink(titles, url, LinkKind.DEPARTMENT_LANDING, landing_slug=path[3:].strip("/"))
    if path.startswith("/search"):
        if "mktg" in query:
            return MenuLink(titles, url, LinkKind.CURATED_SEARCH)
        if "brandname=" in query:
            return MenuLink(titles, url, LinkKind.BRAND_SEARCH)
    return MenuLink(titles, url, LinkKind.OTHER)


def _to_node(raw: Mapping[str, Any]) -> MenuNode:
    return MenuNode(
        title=str(raw.get("title") or ""),
        type=str(raw.get("type") or ""),
        url=raw.get("url") or None,
        children=[_to_node(c) for c in (raw.get("children") or []) if isinstance(c, Mapping)],
    )


def site_menu_key(dynamicdata: Mapping[str, Any]) -> str | None:
    for key in dynamicdata:
        if key.startswith("navigation/") and "/site-menu-v2/" in key:
            return key
    return None


def parse_site_menu(state: Mapping[str, Any]) -> MenuNode:
    """The ``site-menu-v2`` tree from ``__INITIAL_STATE__.dynamicdata``."""
    dyn = state.get("dynamicdata") or {}
    key = site_menu_key(dyn)
    if key is None:
        raise KeyError("site-menu-v2 not present in dynamicdata")
    menu = dyn[key]["assetData"]["data"]["menu"]
    if isinstance(menu, Mapping):
        return _to_node(menu)
    return MenuNode("root", "link", None, [_to_node(m) for m in menu])


def _shop_all_landing(node: MenuNode) -> str | None:
    if node.url and node.title.strip().lower().startswith("shop all"):
        link = classify_link((node.title,), node.url)
        if link.kind is LinkKind.DEPARTMENT_LANDING:
            return link.landing_slug
    return None


@dataclass(frozen=True)
class MenuGroup:
    """The menu subtree that belongs to one CSV department row (secondary scope source, §5.5)."""

    landing_slug: str
    titles: tuple[str, ...]
    taxonomy_links: tuple[MenuLink, ...]
    curated_links: tuple[MenuLink, ...]
    sub_landings: tuple[str, ...]


def menu_groups(
    menu: MenuNode,
    csv_landing_slugs: Iterable[str],
    allowed_sub_landings: Mapping[str, Sequence[str]],
) -> dict[str, MenuGroup]:
    """Associate menu subtrees with CSV ``/d/`` rows.

    For each CSV slug S, find the "Shop All → /d/S" link and climb to the highest ancestor whose
    subtree holds no "Shop All" link to any other landing page, except the sub-landings configured
    for S (e.g. ``grocery → [snacks, international, …]``). This is deterministic, but it is only a
    seed: the landing page itself is the primary scope source and must be confirmed live.
    """
    shop = next((n for n in menu.children if n.title == "Shop"), menu)
    result: dict[str, MenuGroup] = {}
    for slug in csv_landing_slugs:
        allowed = {slug, *allowed_sub_landings.get(slug, ())}
        path: list[MenuNode] | None = None
        for p in _paths_to(shop, lambda n, s=slug: _shop_all_landing(n) == s):
            path = p
            break
        if path is None:
            continue
        group: MenuNode | None = None
        group_titles: tuple[str, ...] = ()
        for depth in range(1, len(path) - 1):  # skip the Shop dropdown itself and the link
            candidate = path[depth]
            others = {s for _, n in candidate.walk() if (s := _shop_all_landing(n)) is not None} - allowed
            if not others:
                group = candidate
                group_titles = tuple(n.title for n in path[1 : depth + 1])
                break
        if group is None:
            continue
        links = group.links(group_titles[:-1])
        by_id: dict[str, MenuLink] = {}
        for lk in links:  # the same node can be linked twice (e.g. 22011 with and without a query)
            if lk.kind is LinkKind.TAXONOMY and lk.taxonomy_id and lk.taxonomy_id not in by_id:
                by_id[lk.taxonomy_id] = lk
        result[slug] = MenuGroup(
            landing_slug=slug,
            titles=group_titles,
            taxonomy_links=tuple(by_id.values()),
            curated_links=tuple(lk for lk in links if lk.kind is LinkKind.CURATED_SEARCH),
            sub_landings=tuple(
                sorted(
                    {
                        lk.landing_slug
                        for lk in links
                        if lk.kind is LinkKind.DEPARTMENT_LANDING
                        and lk.landing_slug
                        and lk.landing_slug != slug
                    }
                )
            ),
        )
    return result


def _paths_to(root: MenuNode, pred: Any) -> Iterator[list[MenuNode]]:
    stack: list[tuple[MenuNode, list[MenuNode]]] = [(root, [root])]
    while stack:
        node, path = stack.pop()
        if pred(node):
            yield path
        for child in reversed(node.children):
            stack.append((child, [*path, child]))
