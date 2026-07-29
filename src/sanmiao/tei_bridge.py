"""
TEI / LJB integration: tag + solve on plain text or XML fragments, JSON proposals.

Runs the same pipeline as cjk_date_interpreter but returns structured output
for external apply (e.g. Le Jean-Baptiste). Plain-text and <root> fragments
need no TEI namespace; use extract_date_fragment() to read existing <date> nodes.
"""

from __future__ import annotations

import inspect
import json
import sys
import time
from typing import Any, Callable, Optional

import lxml.etree as et
import pandas as pd

from .config import DEFAULT_GREGORIAN_START, DEFAULT_TAQ, DEFAULT_TPQ, normalize_defaults
from .converters import jdn_to_iso
from .loaders import load_normalisation_map, normalise_for_search, prepare_tables
from .reporting import generate_report_from_dataframe
from .date_authority import list_date_authority
from .tagging import consolidate_date, index_date_nodes, tag_date_elements
from .xml_utils import remove_lone_tags, strip_text
from .bulk_processing import extract_date_table_bulk, add_can_names_bulk
from .ns import is_tag, strip_namespaces, xpath_dates
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


def _collect_parse_inner_by_index(xml_root: et._Element) -> dict[int, str]:
    """Inner XML (sanmiao children) for each indexed <date>, keyed by date_index."""
    out: dict[int, str] = {}
    for node in xpath_dates(xml_root):
        raw = node.attrib.get("index")
        if raw is None:
            continue
        try:
            idx = int(raw)
        except (TypeError, ValueError):
            continue
        out[idx] = _inner_xml(node)
    return out


def _plain_markup_text(markup: str) -> str:
    """Text content of a markup fragment, spaces stripped (matches date_string normalization)."""
    import re

    return re.sub(r"<[^>]+>", "", markup).replace(" ", "").strip()


def restore_original_markup(inner_xml: str, norm_surface: str, orig_surface: str) -> str:
    """
    Rewrite text nodes in sanmiao markup from normalized to original script.

    Tagging runs on normalized text; inner XML reflects simplified forms. When
    normalization is character-wise with preserved length, map text chars in order.
    """
    norm_surface = str(norm_surface).replace(" ", "")
    orig_surface = str(orig_surface).replace(" ", "")
    if not inner_xml or norm_surface == orig_surface or len(norm_surface) != len(orig_surface):
        return inner_xml

    out: list[str] = []
    norm_i = 0
    i = 0
    while i < len(inner_xml):
        if inner_xml[i] == "<":
            close = inner_xml.find(">", i)
            if close == -1:
                out.append(inner_xml[i:])
                break
            out.append(inner_xml[i : close + 1])
            i = close + 1
        else:
            if norm_i < len(norm_surface):
                out.append(orig_surface[norm_i])
                norm_i += 1
            else:
                out.append(inner_xml[i])
            i += 1
    return "".join(out)


def _inner_xml(date_el: et._Element) -> str:
    parts = []
    if date_el.text:
        parts.append(date_el.text)
    for child in date_el:
        parts.append(et.tostring(child, encoding="unicode", method="xml", with_tail=False))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts).strip()


def _candidate_from_row(row: pd.Series, phrase_dic: dict, pg: bool, gs: list) -> dict[str, Any]:
    line_df = pd.DataFrame([row])
    try:
        report = generate_report_from_dataframe(line_df, phrase_dic, jd_out=False)
        lines = [ln.strip() for ln in report.splitlines() if ln.strip()]
        display = lines[-1] if lines else str(row.get("date_string", ""))
    except Exception:
        display = str(row.get("date_string", ""))
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
    original_text: str | None = None,
    normalized_text: str | None = None,
    implied=None,
) -> tuple[list[dict[str, Any]], dict | None]:
    """Tag + solve on an lxml root (plain <root> or TEI subtree).

    Returns (proposals, implied). Pass implied from a prior chunk to preserve
    sequential context across paragraph boundaries.
    """
    gs, civ = normalize_defaults(gs, civ)
    phrase_dic = get_phrase_dic(lang or "en")

    xml_root = index_date_nodes(xml_root)
    parse_inner = _collect_parse_inner_by_index(xml_root)
    norm_surface_by_index = {idx: _plain_markup_text(inner) for idx, inner in parse_inner.items()}
    xml_string, output_df, implied, _ = extract_date_table_bulk(
        xml_root,
        implied=implied,
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
        original_text=original_text,
        normalized_text=normalized_text,
    )

    if tables is None:
        tables = prepare_tables(civ=civ)
    era_df, dyn_df, _, _, _, _, ruler_can_names = tables
    if not output_df.empty:
        output_df = add_can_names_bulk(output_df, ruler_can_names, dyn_df, era_df)

    if output_df.empty or "date_index" not in output_df.columns:
        return [], implied

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
        orig_ds = proposal["date_string"]
        norm_ds = norm_surface_by_index.get(int(date_index), orig_ds)
        inner = parse_inner.get(int(date_index))
        if inner:
            proposal["parseInnerXml"] = restore_original_markup(inner, norm_ds, orig_ds)
        proposals.append(proposal)

    return proposals, implied


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
    return propose_dates_batch([text], civ=civ, sequential=sequential, proliferate=proliferate,
                               fuzzy=fuzzy, tpq=tpq, taq=taq, pg=pg, gs=gs, lang=lang)[0]


def propose_dates_batch(
    chunks: list[str],
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
    on_chunk: Optional[Callable[[dict[str, Any]], None]] = None,
) -> list[list[dict[str, Any]]]:
    """
    Tag + solve multiple text fragments in one call (loads lookup tables once).

    Sequential implied state carries from each chunk to the next when sequential=True.
    Optional on_chunk(event) fires after each paragraph with timing stats.
    """
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    if civ is None:
        civ = ["c", "j", "k"]

    t_tables = time.perf_counter()
    tables = prepare_tables(civ=civ)
    tables_ms = round((time.perf_counter() - t_tables) * 1000)
    char_map = load_normalisation_map() if fuzzy else None
    results: list[list[dict[str, Any]]] = []
    implied = None
    total = len(chunks)

    if on_chunk:
        on_chunk({
            "type": "init",
            "total": total,
            "tablesMs": tables_ms,
        })

    for index, text in enumerate(chunks):
        t0 = time.perf_counter()
        chars = len(text or "")

        if not text or not str(text).strip():
            results.append([])
            if on_chunk:
                on_chunk({
                    "type": "chunk",
                    "index": index,
                    "done": index + 1,
                    "total": total,
                    "ms": round((time.perf_counter() - t0) * 1000),
                    "chars": chars,
                    "proposals": 0,
                    "skipped": True,
                })
            continue

        original = str(text).replace(" ", "")
        work = original
        if fuzzy and char_map is not None:
            work = normalise_for_search(work, char_map)

        xml_string = tag_date_elements(work, civ=civ, fuzzy=fuzzy)
        xml_string = consolidate_date(xml_string)
        xml_root = remove_lone_tags(xml_string)
        xml_root = strip_text(xml_root)

        proposals, implied = propose_dates_from_xml_root(
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
            original_text=original if fuzzy else None,
            normalized_text=work if fuzzy else None,
            implied=implied if sequential else None,
        )
        results.append(proposals)

        if on_chunk:
            on_chunk({
                "type": "chunk",
                "index": index,
                "done": index + 1,
                "total": total,
                "ms": round((time.perf_counter() - t0) * 1000),
                "chars": chars,
                "proposals": len(proposals),
                "skipped": False,
            })

    return results


def _tag_proposals_from_root(
    xml_root: et._Element,
    *,
    original_text: str | None = None,
    normalized_text: str | None = None,
    fuzzy: bool = False,
) -> list[dict[str, Any]]:
    """Collect tag-only proposals (parse children, no calendar solve)."""
    xml_root = index_date_nodes(xml_root)
    parse_inner = _collect_parse_inner_by_index(xml_root)
    norm_surface_by_index = {idx: _plain_markup_text(inner) for idx, inner in parse_inner.items()}

    proposals: list[dict[str, Any]] = []
    for date_index in sorted(parse_inner.keys()):
        inner = parse_inner[date_index]
        norm_ds = norm_surface_by_index.get(date_index, "")
        orig_ds = norm_ds
        if fuzzy and original_text and normalized_text:
            orig_ds = _original_surface_for_index(
                int(date_index),
                norm_ds,
                original_text.replace(" ", ""),
                normalized_text.replace(" ", ""),
            )
        proposals.append({
            "date_index": int(date_index),
            "date_string": orig_ds or norm_ds,
            "status": "tagged",
            "candidates": [],
            "parseInnerXml": restore_original_markup(inner, norm_ds, orig_ds),
        })
    return proposals


def _original_surface_for_index(
    date_index: int,
    norm_surface: str,
    original: str,
    normalized: str,
) -> str:
    """Best-effort map from normalized tag surface back to original script."""
    if not norm_surface or norm_surface == original or len(original) != len(normalized):
        return norm_surface
    pos = 0
    seen = 0
    while pos <= len(normalized) - len(norm_surface):
        if normalized[pos : pos + len(norm_surface)] == norm_surface:
            if seen == date_index:
                return original[pos : pos + len(norm_surface)]
            seen += 1
            pos += len(norm_surface)
        else:
            pos += 1
    return norm_surface


def tag_dates_batch(
    chunks: list[str],
    *,
    civ=None,
    fuzzy: bool = True,
    lang: str = "en",
    on_chunk: Optional[Callable[[dict[str, Any]], None]] = None,
) -> list[list[dict[str, Any]]]:
    """
    Tag-only pass: find date spans and parse structure, no calendar solve.

    Returns proposals with status ``tagged``, parseInnerXml set, empty candidates.
    """
    if civ is None:
        civ = ["c", "j", "k"]

    char_map = load_normalisation_map() if fuzzy else None
    results: list[list[dict[str, Any]]] = []
    total = len(chunks)

    if on_chunk:
        on_chunk({"type": "init", "total": total, "tablesMs": 0})

    for index, text in enumerate(chunks):
        t0 = time.perf_counter()
        chars = len(text or "")

        if not text or not str(text).strip():
            results.append([])
            if on_chunk:
                on_chunk({
                    "type": "chunk",
                    "index": index,
                    "done": index + 1,
                    "total": total,
                    "ms": round((time.perf_counter() - t0) * 1000),
                    "chars": chars,
                    "proposals": 0,
                    "skipped": True,
                })
            continue

        original = str(text).replace(" ", "")
        work = original
        if fuzzy and char_map is not None:
            work = normalise_for_search(work, char_map)

        xml_string = tag_date_elements(work, civ=civ, fuzzy=fuzzy)
        xml_string = consolidate_date(xml_string)
        xml_root = remove_lone_tags(xml_string)
        xml_root = strip_text(xml_root)

        proposals = _tag_proposals_from_root(
            xml_root,
            original_text=original if fuzzy else None,
            normalized_text=work if fuzzy else None,
            fuzzy=fuzzy,
        )
        results.append(proposals)

        if on_chunk:
            on_chunk({
                "type": "chunk",
                "index": index,
                "done": index + 1,
                "total": total,
                "ms": round((time.perf_counter() - t0) * 1000),
                "chars": chars,
                "proposals": len(proposals),
                "skipped": False,
            })

    return results


def resolve_dates_batch(
    date_elements: list[str],
    *,
    civ=None,
    sequential: bool = True,
    proliferate: bool = False,
    fuzzy: bool = False,
    tpq: int = DEFAULT_TPQ,
    taq: int = DEFAULT_TAQ,
    pg: bool = False,
    gs: list | None = None,
    lang: str = "en",
    on_progress: Optional[Callable[[dict[str, Any]], None]] = None,
) -> list[dict[str, Any] | None]:
    """
    Resolve existing ``<date>`` XML strings in document order.

    Returns one proposal dict per input element (or ``None`` when unsolved).
    Sequential implied state carries forward when ``sequential=True``.
    """
    if gs is None:
        gs = DEFAULT_GREGORIAN_START
    if civ is None:
        civ = ["c", "j", "k"]

    t_tables = time.perf_counter()
    tables = prepare_tables(civ=civ)
    tables_ms = round((time.perf_counter() - t_tables) * 1000)
    implied = None
    total = len(date_elements)
    results: list[dict[str, Any] | None] = []

    if on_progress:
        on_progress({"type": "init", "total": total, "tablesMs": tables_ms})

    for index, date_xml in enumerate(date_elements):
        t0 = time.perf_counter()
        if not date_xml or not str(date_xml).strip():
            results.append(None)
            if on_progress:
                on_progress({
                    "type": "chunk",
                    "index": index,
                    "done": index + 1,
                    "total": total,
                    "ms": round((time.perf_counter() - t0) * 1000),
                    "chars": 0,
                    "proposals": 0,
                    "skipped": True,
                })
            continue

        frag = extract_date_fragment(date_xml)
        proposals, implied = propose_dates_from_xml_root(
            frag,
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
            implied=implied if sequential else None,
        )
        results.append(proposals[0] if proposals else None)

        if on_progress:
            on_progress({
                "type": "chunk",
                "index": index,
                "done": index + 1,
                "total": total,
                "ms": round((time.perf_counter() - t0) * 1000),
                "chars": len(str(date_xml)),
                "proposals": 1 if proposals else 0,
                "skipped": False,
            })

    return results


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
    proposals, _implied = propose_dates_from_xml_root(frag, **kwargs)
    return proposals


def propose_dates_json(text: str, **kwargs) -> str:
    return json.dumps(propose_dates(text, **kwargs), ensure_ascii=False, indent=2)


def _kwargs_for(fn, opts: dict[str, Any]) -> dict[str, Any]:
    """Drop CLI options that the target function does not accept."""
    allowed = set(inspect.signature(fn).parameters)
    return {k: v for k, v in opts.items() if k in allowed}


def cli_main() -> None:
    """
    Read JSON from stdin, write proposals JSON to stdout.

    Request shape::
        {"text": "...", "civ": ["c","j","k"], ...}
        {"chunks": ["para1", "para2", ...], "civ": ["c"], ...}
        {"mode": "tag", "chunks": [...], ...}  — tag-only (parse, no solve)
        {"mode": "resolve", "dates": ["<date>...</date>", ...], ...}
        {"mode": "authority", "civ": ["c","j","k"], ...}  — lookup lists for UI pickers
        {"chunks": [...], "stream": true, ...}  — NDJSON progress lines, then result
    """
    req = json.load(sys.stdin)
    opts = {k: v for k, v in req.items() if k not in ("text", "chunks", "dates", "stream", "mode")}
    mode = req.get("mode", "propose")

    if mode == "authority":
        json.dump(list_date_authority(civ=opts.get("civ")), sys.stdout, ensure_ascii=False)
        return
    chunks = req.get("chunks")
    stream = bool(req.get("stream"))

    if mode == "tag" and chunks is not None:
        tag_opts = _kwargs_for(tag_dates_batch, opts)
        if stream:
            def emit(event: dict[str, Any]) -> None:
                print(json.dumps(event, ensure_ascii=False), flush=True)

            results = tag_dates_batch(chunks, on_chunk=emit, **tag_opts)
            print(json.dumps({"type": "result", "results": results}, ensure_ascii=False), flush=True)
            return
        json.dump(tag_dates_batch(chunks, **tag_opts), sys.stdout, ensure_ascii=False)
        return

    if mode == "resolve":
        dates = req.get("dates") or []
        resolve_opts = _kwargs_for(resolve_dates_batch, opts)
        if stream:
            def emit_resolve(event: dict[str, Any]) -> None:
                print(json.dumps(event, ensure_ascii=False), flush=True)

            results = resolve_dates_batch(dates, on_progress=emit_resolve, **resolve_opts)
            print(json.dumps({"type": "result", "results": results}, ensure_ascii=False), flush=True)
            return
        json.dump(resolve_dates_batch(dates, **resolve_opts), sys.stdout, ensure_ascii=False)
        return

    if chunks is not None:
        propose_opts = _kwargs_for(propose_dates_batch, opts)
        if stream:
            def emit(event: dict[str, Any]) -> None:
                print(json.dumps(event, ensure_ascii=False), flush=True)

            results = propose_dates_batch(chunks, on_chunk=emit, **propose_opts)
            print(json.dumps({"type": "result", "results": results}, ensure_ascii=False), flush=True)
            return
        json.dump(propose_dates_batch(chunks, **propose_opts), sys.stdout, ensure_ascii=False)
        return
    text = req.get("text", "")
    proposals = propose_dates(text, **_kwargs_for(propose_dates, opts))
    json.dump(proposals, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    cli_main()
