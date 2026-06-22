# Fuzzy Search: Cross-Script Date Tagging

## Status

**Implemented.** Fuzzy mode is wired end-to-end in the current codebase. Target release: **0.3.0**.

Users can submit date strings in **traditional Chinese**, **simplified Chinese**, or **Japanese character forms** and have sanmiao tag, resolve, and report them correctly. Matching is **exact after script normalization** — not Levenshtein-style fuzzy distance.

`fuzzy=True` is the default in `cjk_date_interpreter()`. Set `fuzzy=False` to restore pre-0.3.0 behaviour (traditional tag columns only, no input normalization).

See also `IMPLEMENTATION_PLAN.md` for unrelated dynasty/ruler/era validation work.

---

## Problem (original)

Sanmiao matches dynasty, era, and ruler names by building **exact regex alternations** from CSV tag lists in `tagging.py`. The tables are overwhelmingly in **traditional Chinese** (`東漢`, `寶應`, `眞`, etc.). Input in simplified or Japanese script forms did not match.

---

## Architecture (as built)

### Canonical search form: simplified Chinese

Use **simplified Chinese** as the internal “search normal form” for all cross-script matching. The character map is **precomputed at data-prep time** and bundled as `src/sanmiao/data/sanmiao_fuzzy_chars.csv` (Variant → Norm pairs, filtered from the master fuzzy table in the `normalization_compile_table` repo).

```
User input (any script)
        │
        ▼
  normalise_for_search()          loaders.py
   (char map lookup)              sanmiao_fuzzy_chars.csv
        │
        ▼
  normalized text ──► tag_date_elements(fuzzy=True)
        │                  regex lists from *_simp columns
        ▼
  XML with tagged dates ──► extract_date_table_bulk(fuzzy=True)
        │                  bulk_resolve_* on *_simp columns
        │                  filter_dynasty_mismatch_era_compatible(fuzzy=True)
        ▼
  solving (IDs / numbers only — unchanged)
        │
        ▼
  add_can_names_bulk() ──► report (traditional dyn_name, era_name, ruler_name)
```

### Two column sets in the data

| Column | Role |
|--------|------|
| `string`, `era_name` | Traditional forms — canonical output, `fuzzy=False` matching |
| `string_simp`, `era_name_simp` | Simplified search forms — `fuzzy=True` tagging and ID resolution |

Simplified columns exist only where string matching happens (`dynasty_tags.csv`, `ruler_tags.csv`, `era_table.csv`). Main dynasty/ruler tables are unchanged; resolution by ID uses traditional names for reporting.

### Why not fuzzy string distance?

Matching is exact after normalization. That fits the existing regex architecture and avoids false positives (e.g. 梁 matching the wrong dynasty).

---

## Data pipeline

Simplified tag columns are generated when calendar tables are rebuilt, in `sql_date_table_download.py`:

1. Load `fuzzy_normalisation_table.csv` (repo root)
2. Apply `add_simplified_column()` to dynasty tags, ruler tags, and era names
3. Export updated CSVs to `src/sanmiao/data/`

The runtime character map (`sanmiao_fuzzy_chars.csv`) is built separately by `normalization_compile_table/table_fuzzy/filter_fuzzy_for_sanmiao.py`, which keeps only Variant→Norm rows reachable from characters in the tag corpora.

| File | Simplified column | Source column |
|------|-------------------|---------------|
| `dynasty_tags.csv` | `string_simp` | `string` |
| `ruler_tags.csv` | `string_simp` | `string` |
| `era_table.csv` | `era_name_simp` | `era_name` |

Re-run the data-prep scripts whenever tag tables or the fuzzy character map changes.

---

## Code changes (implemented)

### 1. `loaders.py` — normalization

- `load_normalisation_map()` — reads `sanmiao_fuzzy_chars.csv`
- `normalise_for_search(text, char_map)` — per-character lookup; unmapped characters pass through

No separate `normalize.py` module; logic lives in `loaders.py`.

### 2. `sanmiao.py` — entry point

```python
def cjk_date_interpreter(..., fuzzy=True):
```

When `fuzzy=True`:

- Load character map
- Normalize each Chinese date string before `tag_date_elements()`
- Pass `fuzzy=True` through to tagging and `extract_date_table_bulk()`

When `fuzzy=False`: no input normalization; traditional tag and resolution columns throughout.

### 3. `tagging.py` — tag list source

```python
def tag_date_elements(text, civ=None, fuzzy=False):
```

When `fuzzy=True`: build dynasty/era/ruler regex lists from `string_simp` / `era_name_simp`.

Sexagenary, month, day, and relational regexes are unchanged. `normalise_date_fields()` also accepts simplified month forms (e.g. `腊月`).

### 4. `bulk_processing.py` — string-to-ID resolution

Originally the plan assumed only tagging needed fuzzy support. In practice, tagged XML carries **simplified** text in `<dyn>`, `<era>`, and `<ruler>`, so bulk resolution must match on simplified columns too:

| Function | `fuzzy=True` lookup column |
|----------|---------------------------|
| `bulk_resolve_dynasty_ids` | `string_simp` |
| `bulk_resolve_ruler_ids` | `string_simp` |
| `bulk_resolve_era_ids` | `era_name_simp` |
| `filter_dynasty_mismatch_era_compatible` | `era_name_simp`, `string_simp` |

`extract_date_table_bulk(..., fuzzy=False)` threads the flag through initial resolution, mismatch filtering, and mismatch retry re-resolution.

`solving.py` is unchanged — it works on IDs and numeric constraints.

### 5. Output

`add_can_names_bulk()` joins traditional `dyn_name`, `era_name`, and `ruler_name` from canonical tables by ID. Resolved match lines are in traditional Chinese.

The report **header** (`USER INPUT:` / `date_string`) currently reflects **normalized** text, not what the user typed. See [Preserve original user input](#preserve-original-user-input) below.

---

## Preserve original user input

### Problem

When `fuzzy=True`, `cjk_date_interpreter()` normalizes each item **before** tagging:

```python
# sanmiao.py (current)
if fuzzy:
    item = normalise_for_search(item, char_map)   # overwrites item
xml_string = tag_date_elements(item, ...)
```

The report header is built from `date_string`, which is extracted from the tagged XML:

```python
# bulk_processing.py → dates_xml_to_df()
"date_string": node.xpath("normalize-space(string())", ...)
```

```python
# reporting.py → generate_report_from_dataframe()
header = f'{phrase_dic["ui"]}: {meta["date_string"]}\n...'
```

So if the user types `東漢建安十八年`, the header shows `东汉建安十八年` (normalized). Match lines correctly use traditional canonical names; only the echo of user input is wrong.

Internal processing should stay normalized. Only the **display string** needs to reflect the original input.

### Recommended approach: preserve at the entry point (implemented)

Save the original string before normalization and restore per-date `date_string` spans after bulk processing via `restore_original_date_strings()` in `bulk_processing.py`.

```python
# sanmiao.py
user_input = item
if fuzzy:
    item = normalise_for_search(item, char_map)

extract_date_table_bulk(
    xml_root, ...,
    original_text=user_input,
    normalized_text=item,   # full line that was tagged
)
```

`restore_original_date_strings()` walks `date_index` in order, finds each normalized per-date `date_string` in `normalized_text`, and copies the same character span from `original_text`. Works for **one or multiple dates per line** when normalization preserves string length (true for the bundled char map).

**XML / direct callers:** pass `original_text` and `normalized_text` to `extract_date_table_bulk()`, or call `restore_original_date_strings(df, original, normalized)` on any dataframe with `date_index` and `date_string`. Also exported from `sanmiao` package.

**Fallback:** if lengths differ or a span is not found, that date keeps its normalized `date_string`.

| | Entry-point slice (implemented) | Whole-line override | Map spans in XML |
|--|-------------------------------|---------------------|------------------|
| Complexity | Low | Trivial but wrong for multi-date | High |
| Multi-date per line | Yes | No | Yes |
| XML pipeline | `original_text` + `normalized_text` params | — | Fragile |

### Implementation checklist

- [x] `restore_original_date_strings()` in `bulk_processing.py`
- [x] `original_text` / `normalized_text` on `extract_date_table_bulk()`
- [x] `user_input` preserved in `sanmiao.py` before normalization
- [x] Export from `sanmiao` package
- [ ] Integration test asserting header preserves original script under `fuzzy=True`

---

## Deviations from the original plan

| Original plan | As built |
|---------------|----------|
| `src/sanmiao/normalize.py` | `loaders.py` (`load_normalisation_map`, `normalise_for_search`) |
| `kanji_to_hanzi.tsv` + OpenCC at runtime | Precomputed `sanmiao_fuzzy_chars.csv` (TC/SC/JP variants in one table) |
| `scripts/generate_simp_columns.py` | `sql_date_table_download.py` + `filter_fuzzy_for_sanmiao.py` |
| `fuzzy=False` default | `fuzzy=True` default |
| OpenCC required when `fuzzy=True` | Char map bundled; `[fuzzy]` extra in `pyproject.toml` reserved for future runtime OpenCC if needed |
| Tagging only | Tagging **and** `bulk_processing` resolution |

---

## Testing

Manual smoke tests pass (e.g. `东汉建安十八年`, `汉永平元年` → traditional output).

Formal test files from the original plan are **not yet written**:

- `tests/test_normalize.py` — character normalization
- `tests/test_fuzzy_tagging.py` — integration (traditional / simplified / Japanese → same IDs)

Regression requirement: `fuzzy=False` must match pre-0.3.0 behaviour.

---

## Implementation phases

### Phase 0 — Prerequisites

- [x] Write planning document
- [ ] Confirm PyPI release with attestations works (see CHANGELOG)

### Phase 1 — Normalization infrastructure

- [x] Character map bundled (`sanmiao_fuzzy_chars.csv`)
- [x] `load_normalisation_map()` / `normalise_for_search()` in `loaders.py`
- [x] `[fuzzy]` optional dependency declared in `pyproject.toml`
- [ ] Unit tests for normalization

### Phase 2 — Data columns

- [x] Simplified columns in tag CSVs (`sql_date_table_download.py`)
- [x] Corpus-filtered char map build (`filter_fuzzy_for_sanmiao.py` in `normalization_compile_table`)
- [ ] Document data-prep in README

### Phase 3 — Pipeline integration

- [x] `fuzzy` in `tag_date_elements()` and `cjk_date_interpreter()`
- [x] `fuzzy` in `bulk_resolve_*`, `filter_dynasty_mismatch_era_compatible`, `extract_date_table_bulk()`
- [x] Traditional canonical names in output via `add_can_names_bulk()`
- [ ] Integration tests
- [ ] CHANGELOG entry for 0.3.0

### Phase 4 — Polish

- [x] **Preserve original user input in report header** (slice logic in `restore_original_date_strings`)
- [ ] Korean hanja (`civ='k'`) — audit real-world failures; machinery should already apply
- [ ] Expand character map from real-world failures
- [ ] `detect_script_hint()` API (extend `utils.guess_variant()`)
- [ ] Per-span script restoration in XML (only if multi-date-per-line with mixed scripts becomes a real requirement)

---

## Open questions

1. **Japanese table strings** — Spot-check `civ='j'` entries against the char map; expand map as failures appear.
2. **Default for web app** — CLI/library default is now `fuzzy=True`; confirm Huma-Num web app follows suit.
3. **Version numbering** — Ship as **0.3.0** (new feature).
4. **Kanji2Hanzi licensing** — Confirm if further expansion of the master fuzzy table needs explicit attribution.

---

## References

- [OpenCC](https://github.com/BYVoid/OpenCC) (used in master fuzzy table compilation)
- [Kanji2Hanzi rule.txt](https://github.com/NoHeartPen/Kanji2Hanzi/blob/master/mdx/rule.txt)
- Sanmiao tagging: `src/sanmiao/tagging.py`
- Sanmiao entry point: `src/sanmiao/sanmiao.py`
- Bulk resolution: `src/sanmiao/bulk_processing.py`
- Data rebuild: `sql_date_table_download.py`
- Fuzzy char filter: `normalization_compile_table/table_fuzzy/filter_fuzzy_for_sanmiao.py`
