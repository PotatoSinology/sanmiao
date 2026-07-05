"""
TEI / LJB integration: tag + solve on plain text or XML fragments, JSON proposals.

Runs the same pipeline as cjk_date_interpreter but returns structured output
for external apply (e.g. Le Jean-Baptiste). Plain-text and <root> fragments
need no TEI namespace; use extract_date_fragment() to read existing <date> nodes.
"""

from __future__ import annotations

import json
from typing import Any

import lxml.etree as et
import pandas as pd

from .config import DEFAULT_GREGORIAN_START, DEFAULT_TAQ, DEFAULT_TPQ, normalize_defaults
from .converters import jdn_to_iso
from .loaders import load_normalisation_map, normalise_for_search, prepare_tables
from .reporting import generate_report_from_dataframe
from .tagging import consolidate_date, index_date_nodes, tag_date_elements
from .xml_utils import remove_lone_tags, strip_text
from .bulk_processing import extract_date_table_bulk, add_can_names_bulk
from .ns import is_tag, strip_namespaces
from .config import get_phrase_dic


def row_to_tei_attrs(
    row: pd.Series | dict,
    *,
    pg: bool = False,
    gs: list | None = None,
) -> dict[str, str]:
    """
    Map a resolved sanmiao dataframe row to TEI-oriented attribute strings.
    JDN is canonical; when/notBefore/notAfter are derived for display.
    """
    gs, _ = normalize_defaults(gs, None)
    if isinstance(row, pd.Series):
        row = row.to_dict()

    out: dict[str, str] = {}
    for key in (
        "era_id", "dyn_id", "ruler_id", "cal_stream",
        "year", "month", "intercalary", "day", "gz", "nmd_gz", "lp",
        "ind_year", "sex_year",
    ):
        val = row.get(key)
        if val is not None and not (isinstance(val, float) and pd.isna(val)):
            out[key] = str(int(val)) if isinstance(val, (int, float)) and float(val).is_integer() else str(val)

    dila = row.get("dila_id")
    if dila is not None and not (isinstance(dila, float) and pd.isna(dila)):
        out["key"] = str(dila)

    jdn = row.get("jdn")
    jdn_end = row.get("hui_jdn") or row.get("jdn_end")
    if jdn is not None and not (isinstance(jdn, float) and pd.isna(jdn)):
        out["jdn"] = str(jdn)
        iso = row.get("ISO_Date")
        if iso is not None and not (isinstance(iso, float) and pd.isna(iso)):
            out["when"] = str(iso)
        else:
            try:
                out["when"] = jdn_to_iso(float(jdn), pg, gs)
            except (TypeError, ValueError):
                pass
    if jdn_end is not None and not (isinstance(jdn_end, float) and pd.isna(jdn_end)):
        if "jdn" in out:
            out["jdnEnd"] = str(jdn_end)
        try:
            out["notAfter"] = jdn_to_iso(float(jdn_end), pg, gs)
        except (TypeError, ValueError):
            pass
    nmd = row.get("nmd_jdn")
    if nmd is not None and not (isinstance(nmd, float) and pd.isna(nmd)) and "notBefore" not in out:
        try:
            out["notBefore"] = jdn_to_iso(float(nmd), pg, gs)
        except (TypeError, ValueError):
            pass

    return out


def _inner_xml(date_el: et._Element) -> str:
    parts = []
    if date_el.text:
        parts.append(date_el.text)
    for child in date_el:
        parts.append(et.tostring(child, encoding="unicode", method="xml"))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _candidate_from_row(row: pd.Series, phrase_dic: dict, pg: bool, gs: list) -> dict[str, Any]:
    line_df = pd.DataFrame([row])
    report = generate_report_from_dataframe(line_df, phrase_dic, jd_out=False)
    lines = [ln.strip() for ln in report.splitlines() if ln.strip()]
    display = lines[-1] if lines else str(row.get("date_string", ""))
    return {
        "displayLine": display,
        "attrs": row_to_tei_attrs(row, pg=pg, gs=gs),
        "era_id": None if pd.isna(row.get("era_id")) else int(row["era_id"]),
        "dyn_id": None if pd.isna(row.get("dyn_id")) else int(row["dyn_id"]),
        "error_str": None if pd.isna(row.get("error_str")) else str(row["error_str"]),
    }


def _status_for_group(group: pd.DataFrame) -> str:
    if group.empty:
        return "unresolved"
    if "error_str" in group.columns:
        errs = group["error_str"].fillna("").astype(str).str.strip()
        ok = group[errs == ""]
    else:
        ok = group
    if len(ok) == 0:
        return "unresolved"
    if len(ok) == 1:
        return "unique"
    return "ambiguous"


def propose_dates_from_xml_root(
    xml_root: et._Element,
    *,
    civ=None,
    sequential: bool = True,
    proliferate: bool = False,
    fuzzy: bool = False,
    attributes: bool = True,
    tpq: int = DEFAULT_TPQ,
    taq: int = DEFAULT_TAQ,
    pg: bool = False,
    gs: list | None = None,
    lang: str = "en",
    tables=None,
) -> list[dict[str, Any]]:
    """Tag + solve on an lxml root (plain <root> or TEI subtree)."""
    gs, civ = normalize_defaults(gs, civ)
    phrase_dic = get_phrase_dic(lang or "en")

    xml_root = index_date_nodes(xml_root)
    xml_string, output_df, _, _ = extract_date_table_bulk(
        xml_root,
        implied=None,
        pg=pg,
        gs=gs,
        lang=lang,
        tpq=tpq,
        taq=taq,
        civ=civ,
        tables=tables,
        sequential=sequential,
        proliferate=proliferate,
        fuzzy=fuzzy,
        attributes=attributes,
    )

    if tables is None:
        tables = prepare_tables(civ=civ)
    era_df, dyn_df, _, _, _, _, ruler_can_names = tables
    if not output_df.empty:
        output_df = add_can_names_bulk(output_df, ruler_can_names, dyn_df, era_df)

    if output_df.empty or "date_index" not in output_df.columns:
        return []

    proposals = []
    for date_index, group in output_df.groupby("date_index", sort=True):
        status = _status_for_group(group)
        first = group.iloc[0]
        proposal: dict[str, Any] = {
            "date_index": int(date_index),
            "date_string": str(first.get("date_string", "")),
            "status": status,
            "candidates": [_candidate_from_row(r, phrase_dic, pg, gs) for _, r in group.iterrows()],
        }
        if status == "unique" and proposal["candidates"]:
            proposal["attrs"] = proposal["candidates"][0]["attrs"]
        proposals.append(proposal)

    return proposals


def propose_dates(
    text: str,
    *,
    civ=None,
    sequential: bool = True,
    proliferate: bool = False,
    fuzzy: bool = True,
    tpq: int = DEFAULT_TPQ,
    taq: int = DEFAULT_TAQ,
    pg: bool = False,
    gs: list | None = None,
    lang: str = "en",
) -> list[dict[str, Any]]:
    """
    Tag + solve a Chinese (or mixed) date string. Returns one proposal per date span.

    Uses the same steps as cjk_date_interpreter for a single CCS input line.
    """
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    if civ is None:
        civ = ["c", "j", "k"]

    original = text.replace(" ", "")
    work = original
    char_map = load_normalisation_map() if fuzzy else None
    if fuzzy:
        work = normalise_for_search(work, char_map)

    xml_string = tag_date_elements(work, civ=civ, fuzzy=fuzzy)
    xml_string = consolidate_date(xml_string)
    xml_root = remove_lone_tags(xml_string)
    xml_root = strip_text(xml_root)

    tables = prepare_tables(civ=civ)
    return propose_dates_from_xml_root(
        xml_root,
        civ=civ,
        sequential=sequential,
        proliferate=proliferate,
        fuzzy=fuzzy,
        tpq=tpq,
        taq=taq,
        pg=pg,
        gs=gs,
        lang=lang,
        tables=tables,
    )


def extract_date_fragment(date_element: et._Element | str) -> et._Element:
    """
    Wrap a TEI (or sanmiao) <date> element in <root> for re-resolution.
    Strips namespaces so internal sanmiao paths match legacy behaviour.
    """
    if isinstance(date_element, str):
        date_element = et.fromstring(date_element.encode("utf-8"))
    if not is_tag(date_element, "date"):
        raise ValueError("expected a <date> element")
    frag = et.Element("root")
    inner = strip_namespaces(date_element)
    frag.append(inner)
    return frag


def resolve_date_element(
    date_element: et._Element | str,
    **kwargs,
) -> list[dict[str, Any]]:
    """Re-solve an existing <date> subtree (parse children and/or attrs)."""
    frag = extract_date_fragment(date_element)
    index_date_nodes(frag)
    kwargs.setdefault("attributes", True)
    return propose_dates_from_xml_root(frag, **kwargs)


def propose_dates_json(text: str, **kwargs) -> str:
    return json.dumps(propose_dates(text, **kwargs), ensure_ascii=False, indent=2)
