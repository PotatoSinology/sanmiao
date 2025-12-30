# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Fixed reversion to regnal year for ISO string conversion in v0.1.5

[Unreleased]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.6...HEAD
[0.1.6]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.5...v0.1.6
[0.1.5]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.4...v0.1.5
[0.1.4]: https://github.com/PotatoSinology/sanmiao/releases/tag/v0.1.4

