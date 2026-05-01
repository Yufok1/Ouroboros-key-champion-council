# middle-passage

> "The ocean kept receipts. We are learning to read them."

Open-source forensic data toolkit for the Middle Passage Forensic Recovery Project.

This package is a protection-first research scaffold for integrating voyage records,
oceanographic assumptions, bathymetry, and memorial GIS outputs. It models
**survey-priority zones**, not certainties, and every output is designed to carry
uncertainty, source references, and non-disturbance language.

**License:** Creative Commons CC BY 4.0  
**Purpose:** Humanitarian. Scientific. Memorial.  
**Status:** Phase 0 scaffold with synthetic-safe defaults.

## Principles

- People, not cargo.
- Ancestors, not artifacts.
- Probability zones, not treasure maps.
- Public methods, careful precision.
- Protection before spectacle.

## Install

After the first PyPI release:

```bash
pip install middle-passage
```

Until then, install from this GitHub subdirectory:

```bash
pip install "middle-passage @ git+https://github.com/Yufok1/Ouroboros-key-champion-council.git@main#subdirectory=middle-passage"
```

For local development:

```bash
pip install -e .
```

## CLI

Generate a synthetic-safe sample GeoJSON:

```bash
middle-passage sample --output sample.geojson
```

Model survey-priority zones from a voyage CSV:

```bash
middle-passage model-deposits --voyages voyages.csv --output zones.geojson
```

If no voyage file is provided, the CLI uses a clearly marked synthetic sample
for development only.

## Data Sensitivity

The package supports data sensitivity labels:

- `public`: safe public metadata or generalized zones
- `generalized`: public map data with reduced precision
- `restricted`: high-precision working data for qualified review
- `do_not_publish`: sensitive records or coordinates that should not be released

Precise burial-site candidates should not be published casually. Release policy
must be governed by descendant/community review, legal review, and protection risk.

## Current Scope

This first package cut includes:

- flexible CSV voyage loading
- simple voyage filtering
- current-vector drift estimation
- conservative descent/scatter model
- survey-priority zone creation
- GeoJSON FeatureCollection export
- CLI and tests

It does not claim to identify remains. It creates reproducible, inspectable
research objects for future expert validation.

## Release

This package should be published from GitHub with PyPI Trusted Publishing.
See `docs/PYPI_RELEASE.md` for the release checklist.
