# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Dynasty-mismatch validation and XML correction.** When dynasty-restricted resolution finds no valid era_id or ruler_id for a date (e.g. false pair 清+太上), the pipeline now:
  - Detects such date_indices (`detect_dynasty_mismatch_indices`) and fixes the XML via `fix_dynasty_mismatch_xml`: moves `<dyn>` content out of the `<date>` element, then runs `remove_lone_tags` so dates left with only era/ruler are stripped.
  - Drops from the extracted table only date_indices that were actually removed from the XML (`date_indices_in_xml_string`); for dates that remain (e.g. era+year), clears `dyn_id` and re-resolves era/ruler without dynasty restriction so they are solved (e.g. 太康二年 → Jin and Liao candidates).
- New helper `date_indices_in_xml_string()` in `xml_utils` to report which date indices still exist in an XML string after correction.

### Changed
- Era and ruler resolution already restricted by dynasty (`bulk_resolve_era_ids` by `dyn_id`, `bulk_resolve_ruler_ids` by `ruler_df`); pipeline now applies dynasty-mismatch detection and XML/table correction after resolution so bad dynasty+era/ruler pairs are fixed and remaining dates are solved.
- **Dynasty-mismatch era compatibility:** Before ejecting a dynasty, we check whether the era belongs to a dynasty whose tag (or whose parent’s tag via `part_of`) exactly equals `dyn_str`. Uses `filter_dynasty_mismatch_era_compatible` with `era_df`, `dyn_tag_df`, and `dyn_df` (for `part_of`). Avoids falsely ejecting 漢永平 (永平 under 東漢 46, 46 part_of 42, tag 漢 = 42) and 魏永平 (永平 under 北魏 89, tag 魏 = 89); compatibility is exact tag match only.
- **Dynasty + suffix only:** In `bulk_resolve_dynasty_ids`, we no longer expand to child dynasties (part_of) when the date has only dynasty + suffix (no era_str, no ruler_str). So 晉時 resolves to 晉 (51) only, not 西晉/東晉 (52, 53). Expansion to children still happens when the date has era or ruler context.

## [0.2.4] - 2025-02-10
- Additional debugging of date resolution for XML tagging purposes

## [0.2.3] - 2025-01-30

### Fixed
- Massive bug with long sequential tables, dropping duplicates on table rather than on date index bloc.
- Massive bug recognising new moon eves, comparing integers to strings.

## [0.2.2] - 2025-01-28

### Changed
- Added cache-control meta tags and a version-aware sessionStorage reloading check so browsers always fetch the freshest frontend bundle.
- Added relative date tagging and basic interpretation.
- Tag 改元 and relational prefixes as protected XML nodes.
- Add suffix-aware era selection (early/late/single-era) and interpret era 初 as year=1.
- Add tpq/taq filtering to reporting when candidates exceed limit (15)
- Implement two-pass era tagging to prioritize eras before date elements
- Add era_prefix_only ruler tags for abbreviated posthumous names

## [0.2.1] - 2025-01-19

### Changed
- Developped and tested XML markup functions
- Further debugging
- Several confusing era start and end dates fixed
- Added Chinese, Japanese, and German output language support.

## [0.2.0] - 2025-01-08

### Changed
- Fixed `make_leapmonth_from_group1(m)` to take an argument. Oops

## [0.1.8] - 2025-01-08

### Changed
- Rewrote codebase to increase speed
- Solved problem of duplicate entries in reports
- Tested functions for independant use in XML tagging
- Added sequential vs non sequential modes to determine whether to intelligently forward fill date elements
- Added proliferate mode to disable enormous match sets on ambiguous strings in XML tagging

### Documentation
- Added comprehensive docstrings to all functions that were missing them

## [0.1.7] - 2025-12-30

### Changed
- Add lru_cache to CSV loading
- Remove mutable defaults and global warning suppression
- Move ganshi mappings to module scope

## [0.1.6] - 2025-12-30

### Fixed
- Fixed era selection logic in `jdn_to_ccs` to properly handle both integer and float types for `era_start_year`
- Fixed issue where precise Western dates (ISO format) were incorrectly defaulting to emperor start year instead of using valid eras (including blank eras where `era_name == ''`)
- Changed type checking from `isinstance(row['era_start_year'], float)` to `pd.notna(row['era_start_year'])` to correctly identify valid eras regardless of numeric type

## [0.1.5] - 2025-01-02

### Removed
- Removed all debug logging code that was added during development

## [0.1.4] - 2025-12-29

### Added
- Added lunation tables for Sun-Wu, Liu-Shu, Liao, Jin, and Korea extracted from the [Chinese Time Authority](https://authority.dila.edu.tw/time/).
- Civilization filtering (`civ` parameter) to filter dynasties, rulers, eras, and lunation tables by `cal_stream`
  - Supports `'c'` (China, cal_stream 1-3), `'j'` (Japan), `'k'` (Korea)
  - Can accept a single string or list of strings (e.g., `['c', 'j', 'k']`)
  - Automatically filters out all entries with null `cal_stream` values

### Fixed
- Moved web app back end off of Huma-Num webcluster to PLMshift for stability.

[Unreleased]: https://github.com/PotatoSinology/sanmiao/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/PotatoSinology/sanmiao/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/PotatoSinology/sanmiao/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/PotatoSinology/sanmiao/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/PotatoSinology/sanmiao/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.8...v0.2.0
[0.1.8]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.7...v0.1.8
[0.1.7]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.6...v0.1.7
[0.1.6]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/PotatoSinology/sanmiao/releases/tag/v0.1.4

