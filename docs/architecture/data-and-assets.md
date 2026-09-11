# Release data architecture

Status: implemented and release-validated (2026-09-12).

## Goals

The catalog must support these flows without encoding UI behavior in file names:

1. Add a desktop character: **unit → character → character default outfit → load**.
2. Change the selected character's outfit: **outfit name → normal/performance option**, showing
   only options backed by an available asset variant.
3. Keep standard and chibi rendering independent from clothing selection.
4. Keep public metadata, local asset locations, and redistribution approval independent.

## Normalized model

```text
Catalog
├─ units[]
│  └─ member_character_ids[]
├─ characters[]
│  ├─ unit_ids[]
│  ├─ default_outfit_id
│  ├─ ui_asset_refs
│  └─ outfits[]
│     └─ variants[]
│        ├─ presentation: standard | chibi
│        ├─ costume_mode: normal | performance
│        └─ model_asset_ref
└─ asset_packs[] (references only)
```

Stable ASCII IDs are used for joins and saved settings. User-facing names live in locale files and
are addressed by `name_key`. Source IDs may be retained in `source_ref` for local import tooling,
but are never used as the application's primary identity.

### Why variants have two axes

The source folders represent four combinations:

| Source type | `presentation` | `costume_mode` |
|---|---|---|
| `stand` | `standard` | `normal` |
| `stand_costume` | `standard` | `performance` |
| `cb` | `chibi` | `normal` |
| `cb_costume` | `chibi` | `performance` |

This prevents `stand` and `cb` from appearing as different outfits. It also makes the required UI
rule mechanical: after the user selects an outfit name, list the distinct `costume_mode` values
whose variants exist for the active `presentation`.

## Selection rules

### Add character

1. List enabled units in `sort_order`.
2. List enabled members of the selected unit.
3. Resolve `character.default_outfit_id`.
4. Select the variant matching the current presentation and `default_costume_mode`.
5. If that exact variant is unavailable, prefer the same presentation with `normal`, then the same
   presentation's first available variant. Do not silently switch between standard and chibi.
6. If no compatible variant exists, keep the character disabled and show a localized diagnostic.

### Change outfit

1. Scope the action to one desktop character instance, not the global character definition.
2. Show outfit names that have at least one variant for the instance's active presentation.
3. After an outfit is chosen, show `normal` and/or `performance` only when matching variants exist.
4. If only one mode exists, it may be applied directly; the UI must not manufacture the other mode.
5. Persist `{character_id, outfit_id, presentation, costume_mode}`. Never persist a display name or
   absolute file path.

## Asset references

Catalog records use `asset://<pack-id>/<relative-path>`. An asset pack manifest declares every file,
its SHA-256 digest, media role, provenance, and publication decision. Absolute developer paths and
implicit directory scanning are not part of the public runtime contract.

The requested UI assets map as follows:

| Development source | Catalog role | Owner |
|---|---|---|
| `cb_icon_stand` | `character.portrait` | character |
| `chain_profile_bg` | `character.profile_background` | character |
| `chain_talk_bg` | `character.chat_background` or unit chat background | character/unit |
| `ChainChrIcon` | `character.chat_icon` or unit chat icon | character/unit |
| `unit_icons` | `unit.icon` | unit |

The importer must create the mapping explicitly. Numeric filename position is not accepted as a
join key because the five collections have different counts and numbering conventions.

## Proposed repository layout

```text
ShinyColorsPet/
├─ data/
│  ├─ catalog.json                 # reviewed, non-binary public metadata
│  └─ locales/<locale>.json        # public display text by stable key
├─ schemas/
│  ├─ catalog-v1.schema.json
│  └─ asset-pack-v1.schema.json
├─ asset-packs/                    # only owner-approved distributable packs
│  └─ <pack-id>/asset-pack.json
├─ packaging/
│  └─ release-assets.json          # deny-by-default package allowlist
├─ docs/                         # architecture, integrations, release, and provenance
└─ shiny_pet/                      # migrated application code after review
```

Local or separately supplied assets are imported by the user-facing model manager. Importing never
copies them into the GPL-covered repository; it copies each selected Spine set into the user's
LocalAppData directory and generates its runtime manifest there.

### Local-only model location

Spine models are explicitly prohibited from the public repository and public installer. The user
selects an extracted download containing `dresses.json`; complete Spine 3.6 sets are copied to
`%LOCALAPPDATA%/ShinyColorsPet/models/<character>/<outfit>/<variant>/`. Generated manifests are
centralized under `%LOCALAPPDATA%/ShinyColorsPet/manifests/` and embed the small catalog record used
by the character and outfit selectors.

An individual model can also be added by supplying its character, unit, outfit, presentation, and
costume fields and selecting one directory containing `data.json`, `data.atlas`, and its texture
pages. Updates use a staging directory before replacing an installed set. Runtime paths are always
resolved against the copied LocalAppData directory, so the original download is not a dependency.

The older `asset-pack.json` discovery remains supported for development and migration, but users no
longer need a pre-generated pack or manifest to install models through the UI.

## Boundaries

- Catalog schema is application data, not proof of redistribution rights.
- A file is packageable only if both its pack review state is `approved` and its pack ID is in
  `packaging/release-assets.json`.
- Missing review information is a hard deny.
- Credentials, chat databases, memories, user settings, source story scripts, unreviewed voice
  references outside the public `audio_reference/` directory, test screenshots, model fixtures,
  and complete renderer runtime checkouts never enter the default package. All files under
  `souls/` and `audio_reference/` are public runtime character context and are packaged as
  directories declared in `packaging/release-character-context.json`.
- `local-assets/` is ignored as a whole; public build tooling must also reject it if copied into a
  staging directory by an external process.
- The application must work with an empty asset allowlist and explain how to register a local pack.
