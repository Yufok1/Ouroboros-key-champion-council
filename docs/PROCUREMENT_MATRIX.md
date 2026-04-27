# Procurement Matrix

This matrix separates source-verified local inventory from verified external sources and unverified research leads for the broader historical-world program.

## Status Legend

- `IN_REPO`: verified from the current local manifests
- `VERIFIED_EXTERNAL`: verified with a specific source URL and readable usage terms
- `UNVERIFIED_CANDIDATE`: research lead only, not yet cleared for ingestion
- `STYLIZED_FALLBACK`: usable for placeholder or non-photoreal work only

## historical_maritime

### IN_REPO

- Poly Haven CC0 ships already local:
  - `Dutch Ship Large 01`
  - `Dutch Ship Large 02`
  - `Dutch Ship Medium`
  - `Ship Pinnace`
- Poly Haven CC0 maritime support already local:
  - `Cannon 01`
  - `Modular Wooden Pier`
  - `Lateral Sea Marker`
  - coastal cliffs, rocks, crates, barrels, lanterns, buckets, treasure props

### VERIFIED_EXTERNAL

| Source | URL | Terms | Native format | Availability | Intended pack | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Scottish Maritime Museum CC0 collection on Sketchfab | https://sketchfab.com/ScottishMaritimeMuseum/collections/scottish-maritime-museum-cc0-b367fa03fcea40279a5470eea7872709 | CC0 | Sketchfab downloadable models | 41-model CC0 collection | `sketchfab-scottish-maritime-cc0/` | Maritime heritage artifacts and vessel-adjacent scans; good verified maritime expansion lane |
| Sketchfab CC0 discovery tag | https://sketchfab.com/tags/cc0 | CC0-tagged discovery lane | varies by asset | rolling discovery source | `sketchfab-cc0-{collection}/` | Use only per-asset once the actual download page confirms the license and format |

### UNVERIFIED_CANDIDATE

- iMARECULTURE ship library: https://imareculture.eu/downloads/project-tools/3d-libraries-of-ships/
  - ancient ship library with three classical-era ships
  - described as an open source library, but redistribution/license wording still needs legal confirmation before ingestion
- Viking longships and knarrs via museum or cultural-heritage collections
- Chinese junks and dragon boats
- Arabic / Indian Ocean dhows and feluccas
- Polynesian voyaging canoes and outriggers
- Medieval European cogs and carracks

## historical_architecture

### IN_REPO

- No serious photoreal historical architecture lane exists locally
- Kenney arena, castle, and town kits remain stylized layout aids only

### VERIFIED_EXTERNAL

| Source | URL | Terms | Native format | Availability | Intended pack | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Smithsonian Open Access 3D | https://3d.si.edu/collections/openaccesshighlights | CC0 on marked models | Smithsonian web 3D downloads | thousands of open access objects | `smithsonian-open-access/` | Strong source for artifacts and some architectural/cultural objects, but not a complete building-kit source |

### UNVERIFIED_CANDIDATE

- Mediterranean classical structures: forum, temple, amphitheater, villa
- Egyptian monumental architecture: pyramid, tomb, temple
- Mesopotamian structures: ziggurat, palace
- East Asian structures: pagoda, torii, courtyard, palace
- Mesoamerican structures: pyramid, ball court
- Islamic structures: mosque, minaret, caravanserai
- Northern European structures: longhouse, mead hall, stave church
- Sub-Saharan African structures: Great Zimbabwe, compound architecture

## historical_people

### IN_REPO

- No photoreal humans are currently in repo
- Existing local NPC packs are stylized only

### VERIFIED_EXTERNAL

| Source | URL | Terms | Native format | Availability | Intended pack | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Renderpeople free posed sample | https://renderpeople.com/posed/ | free commercial use stated on page; FAQ forbids redistribution of downloadable 3D files as standalone assets | FBX, GLB, OBJ and DCC-specific formats | official free posed sample on page | `renderpeople-free-internal/` | Strong internal runtime lane, but likely not safe for redistributable pack publication without extra permission |
| Renderpeople FAQ | https://renderpeople.com/faq/ | confirms commercial rendering rights and blocks making source 3D files downloadable to third parties | n/a | policy reference | n/a | Use as the governing redistribution constraint when evaluating ingestion |

### UNVERIFIED_CANDIDATE

- ActorCore free campaign: https://actorcore.reallusion.com/campaigns/askNK/default.html
  - official page advertises 6 fully rigged scanned people plus the Spunky Moves pack
  - export pipeline is documented through AccuRIG to FBX/USD/iAvatar:
    https://actorcore.reallusion.com/static-page/auto-rig/pre_page/upload-export/upload-export.html
  - redistribution terms still need review before ingestion into a redistributable pack

### STYLIZED_FALLBACK

- Quaternius Universal Base Characters
  - https://quaternius.com/packs/universalbasecharacters.html
  - CC0
  - stylized fallback only, not part of the main photoreal pipeline

## historical_props

### IN_REPO

- Poly Haven already covers useful cross-cultural support props:
  - barrels
  - crates
  - lanterns
  - buckets
  - treasure chest
  - cannon

### VERIFIED_EXTERNAL

| Source | URL | Terms | Native format | Availability | Intended pack | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Smithsonian Open Access 3D | https://3d.si.edu/collections/openaccesshighlights | CC0 on marked models | Smithsonian web 3D downloads | thousands of objects | `smithsonian-open-access/` | Best verified lane for cultural artifacts, ritual objects, tools, and historical specimens |

### UNVERIFIED_CANDIDATE

- amphorae
- weapons and shields by culture
- ritual / religious objects
- carts, looms, kilns, anvils, agricultural tools
- scrolls, writing surfaces, coinage, trade goods

## historical_environments

### IN_REPO

- Coastal / island / reef-flavored environment pieces already exist in the local Poly Haven pack
- The current live validation scene `photoreal_smugglers_cove_v1_2026_03_17` proves the coastal lane is already usable

### VERIFIED_EXTERNAL

| Source | URL | Terms | Native format | Availability | Intended pack | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| Poly Haven | https://polyhaven.com/license | CC0 | glTF / HDRI / textures | public library | `polyhaven-{collection}/` | Best verified photoreal environment source already in use |
| Smithsonian Coral Collection with The Hydrous | https://sketchfab.com/Smithsonian/collections/coral-collection-916e2f4fe95f4bc995729415b0a07cfe | Smithsonian collection describes CC0 content in the account overview; verify each exported model page before pack publication | Sketchfab downloadable models | 100-model coral collection | `smithsonian-coral-collection/` | Strong reef lane candidate tied to cultural/scientific open-access work |

### UNVERIFIED_CANDIDATE

- The Hydrous coral models: https://thehydro.us/3d-models
  - official page says the models can be viewed, downloaded, and printed for projects
  - exact downstream redistribution/license language still needs confirmation per linked collection
- iMARECULTURE amphora and ship-adjacent historical environment assets
- night, storm, harbor, and other historical-scene HDRI sets beyond the current in-repo pair

## Notes

- `VERIFIED_EXTERNAL` means the source and broad usage terms are verified, not that every asset should be bulk-ingested immediately.
- `UNVERIFIED_CANDIDATE` means a real lead exists but legal/format review is still required.
- `STYLIZED_FALLBACK` assets should not be mixed into the main photoreal pipeline unless the user explicitly wants stylized placeholders.
