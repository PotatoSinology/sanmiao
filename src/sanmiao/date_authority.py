"""
Compact dynasty / ruler / era lookup for LJB date attribute pickers.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from .loaders import prepare_tables


def _optional_int(value) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_float(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick_ruler_label(
    person_id,
    ruler_tag_df: pd.DataFrame,
    ruler_can_names: pd.DataFrame,
) -> str:
    tags = ruler_tag_df.loc[ruler_tag_df["person_id"] == person_id, "string"].dropna()
    if not tags.empty:
        return str(min(tags, key=lambda s: len(str(s))))
    can = ruler_can_names.loc[ruler_can_names["person_id"] == person_id, "string"].dropna()
    if not can.empty:
        return str(can.iloc[0])
    return str(person_id)


def list_date_authority(civ=None) -> dict[str, list[dict[str, Any]]]:
    """
    Join sanmiao tables into three searchable lists for UI pickers.

    Returns JSON-serializable dict with keys ``dynasties``, ``rulers``, ``eras``.
    """
    era_df, dyn_df, ruler_df, _lunar, _dyn_tags, ruler_tag_df, ruler_can_names = prepare_tables(
        civ=civ,
    )

    dyn_name_by_id = {
        int(row["dyn_id"]): str(row["dyn_name"])
        for _, row in dyn_df.iterrows()
        if pd.notna(row.get("dyn_id")) and pd.notna(row.get("dyn_name"))
    }

    ruler_labels: dict[int, str] = {}
    for person_id in ruler_df["person_id"].dropna().unique():
        ruler_labels[int(person_id)] = _pick_ruler_label(
            person_id, ruler_tag_df, ruler_can_names
        )

    dynasties: list[dict[str, Any]] = []
    if not dyn_df.empty:
        sort_cols = [c for c in ["cal_stream", "dyn_start_year", "dyn_id"] if c in dyn_df.columns]
        for _, row in dyn_df.sort_values(sort_cols).iterrows():
            dyn_id = _optional_int(row.get("dyn_id"))
            if dyn_id is None:
                continue
            dynasties.append(
                {
                    "dynId": dyn_id,
                    "label": str(row["dyn_name"]),
                    "startYear": _optional_int(row.get("dyn_start_year")),
                    "endYear": _optional_int(row.get("dyn_end_year")),
                    "calStream": _optional_float(row.get("cal_stream")),
                }
            )

    rulers: list[dict[str, Any]] = []
    if not ruler_df.empty:
        sort_cols = [c for c in ["dyn_id", "emp_start_year", "person_id"] if c in ruler_df.columns]
        for _, row in ruler_df.sort_values(sort_cols).iterrows():
            dyn_id = _optional_int(row.get("dyn_id"))
            ruler_id = _optional_int(row.get("person_id"))
            if dyn_id is None or ruler_id is None:
                continue
            rulers.append(
                {
                    "rulerId": ruler_id,
                    "dynId": dyn_id,
                    "label": ruler_labels.get(ruler_id, str(ruler_id)),
                    "dynLabel": dyn_name_by_id.get(dyn_id, ""),
                    "startYear": _optional_int(row.get("emp_start_year")),
                    "endYear": _optional_int(row.get("emp_end_year")),
                }
            )

    eras: list[dict[str, Any]] = []
    if not era_df.empty:
        sort_col = "era_start_jdn" if "era_start_jdn" in era_df.columns else "era_start_year"
        for _, row in era_df.sort_values(sort_col).iterrows():
            era_id = _optional_int(row.get("era_id"))
            dyn_id = _optional_int(row.get("dyn_id"))
            if era_id is None or dyn_id is None:
                continue
            ruler_id = _optional_int(row.get("ruler_id"))
            eras.append(
                {
                    "eraId": era_id,
                    "dynId": dyn_id,
                    "rulerId": ruler_id,
                    "label": str(row["era_name"]),
                    "labelSimp": (
                        str(row["era_name_simp"])
                        if pd.notna(row.get("era_name_simp"))
                        else None
                    ),
                    "dynLabel": dyn_name_by_id.get(dyn_id, ""),
                    "rulerLabel": ruler_labels.get(ruler_id, "") if ruler_id is not None else "",
                    "startYear": _optional_int(row.get("era_start_year")),
                    "endYear": _optional_int(row.get("era_end_year")),
                }
            )

    return {"dynasties": dynasties, "rulers": rulers, "eras": eras}
