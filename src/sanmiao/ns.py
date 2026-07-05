"""
Namespace helpers for TEI and mixed-namespace XML.

Sanmiao parse children (`year`, `era`, `dyn`, …) are typically unprefixed even inside
TEI documents. Outer `<date>` wrappers may use the document default namespace (TEI);
when created via lxml inside a namespaced `<date>`, children inherit that namespace
(local-name still matches). XPath uses local-name() throughout.
"""

from __future__ import annotations

import lxml.etree as et

TEI_NS = "http://www.tei-c.org/ns/1.0"

# Wrapper <date> may inherit namespace from these ancestor local names.
_WRAPPER_NS_ANCESTORS = frozenset(
    {"TEI", "teiCorpus", "text", "body", "div", "p", "ab", "l", "head", "date"}
)


def local_name(tag: str) -> str:
    if not tag or not isinstance(tag, str):
        return tag or ""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def is_tag(el: et._Element, name: str) -> bool:
    return local_name(el.tag) == name


def tag_in(el: et._Element, names: set[str] | frozenset) -> bool:
    return local_name(el.tag) in names


def make_element(name: str, ns: str | None = None, text: str | None = None) -> et._Element:
    tag = f"{{{ns}}}{name}" if ns else name
    el = et.Element(tag)
    if text is not None:
        el.text = text
    return el


def find_child(parent: et._Element, name: str) -> et._Element | None:
    for child in parent:
        if is_tag(child, name):
            return child
    return None


def child_local_names(node: et._Element) -> list[str]:
    return [local_name(c.tag) for c in node]


def xpath_all(
    root: et._Element,
    local: str,
    *,
    require_attr: str | None = None,
    extra_predicate: str = "",
) -> list:
    pred = f'local-name()="{local}"'
    if require_attr:
        pred += f" and @{require_attr}"
    if extra_predicate:
        pred += f" and ({extra_predicate})"
    return root.xpath(f".//*[{pred}]")


def xpath_dates(root: et._Element, *, indexed_only: bool = False, with_gz: bool = False) -> list:
    pred = 'local-name()="date"'
    if indexed_only:
        pred += " and @index"
    if with_gz:
        pred += ' and .//*[local-name()="gz"]'
    return root.xpath(f".//*[{pred}]")


def child_text(node: et._Element, local: str) -> str | None:
    xp = f'normalize-space(string(.//*[local-name()="{local}"][1]))'
    result = node.xpath(xp)
    if isinstance(result, str) and result.strip():
        return result
    return None


def child_attr(node: et._Element, local: str, attr: str) -> str | None:
    xp = f'normalize-space(string(.//*[local-name()="{local}"][1]/@{attr}))'
    result = node.xpath(xp)
    if isinstance(result, str) and result.strip():
        return result
    return None


def has_child(node: et._Element, local: str) -> bool:
    return bool(node.xpath(f'boolean(.//*[local-name()="{local}"])'))


def has_ancestor_date(el: et._Element) -> bool:
    return bool(el.xpath('boolean(ancestor::*[local-name()="date"])'))


def detect_wrapper_namespace(root: et._Element) -> str | None:
    """
    Namespace URI for new <date> wrappers when tagging inside a namespaced document.
    Parse children (year, era, …) remain unprefixed.
    """
    if root.tag.startswith("{"):
        if local_name(root.tag) in _WRAPPER_NS_ANCESTORS:
            return root.tag.split("}", 1)[0][1:]
    for el in root.iter():
        if el.tag.startswith("{") and local_name(el.tag) in _WRAPPER_NS_ANCESTORS:
            return el.tag.split("}", 1)[0][1:]
    return None


def strip_namespaces(root: et._Element) -> et._Element:
    """Return a deep copy with Clark notation removed (for sanmiao-only fragments)."""
    root = et.fromstring(et.tostring(root))
    for el in root.iter():
        if isinstance(el.tag, str) and el.tag.startswith("{"):
            el.tag = local_name(el.tag)
    return root
