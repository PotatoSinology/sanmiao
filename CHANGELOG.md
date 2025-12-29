# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.4] - 2025-12-29

### Added
- Added lunation tables for Sun-Wu, Liu-Shu, and Korea extracted from the [Chinese Time Authority](https://authority.dila.edu.tw/time/).
- Civilization filtering (`civ` parameter) to filter dynasties, rulers, eras, and lunation tables by `cal_stream`
  - Supports `'c'` (China, cal_stream 1-3), `'j'` (Japan), `'k'` (Korea)
  - Can accept a single string or list of strings (e.g., `['c', 'j', 'k']`)
  - Automatically filters out all entries with null `cal_stream` values

### Fixed
- Moved web app back end off of Huma-Num webcluster to PLMshift for stability.

[Unreleased]: https://github.com/PotatoSinology/sanmiao/compare/v0.1.4...HEAD
[0.1.4]: https://github.com/PotatoSinology/sanmiao/releases/tag/v0.1.4

