# Quality profiles

## What a profile is

A profile is a named, versioned bundle of rule overrides. It does not add
new rules. It changes the enabled state, severity or parameters of rules
that already exist in `app/engines/validation/definitions.py`.

That constraint is deliberate. Any behaviour a profile can produce is
behaviour a review can read in the profile file, and any rule a profile
touches is a rule that BIMGuard already tested.

## Format

Profiles are YAML files. A JSON Schema is bundled at
`apps/api/data/profiles/schema.json`.

    schema_version: 1        # schema version of the profile format itself
    id: jp-bimcim-v1         # slug, unique across profiles
    name: ...                # human-readable name
    description: ...         # optional, shown in the UI
    illustrative: true       # default; true means "not a standard"
    rules:
      STALE_DEPENDENCY:
        enabled: true
        severity: CRITICAL
        params: { ... }       # only if the rule accepts parameters

Every field in a `rules` entry is optional. Anything omitted keeps its
current value: the database override if one exists, otherwise the factory
default.

## Loading

`app/engines/profiles/loader.py` parses the file, validates it against the
Pydantic model in `types.py`, and runs each rule override through the
engine's own `validate_configuration`. Any failure raises
`ProfileLoadError` with a user-facing message. No partial profile is ever
returned.

Invalid files are skipped during directory scanning and logged; the detail
endpoint surfaces the error.

## Activation

Activation is per project. A single row in `profile_activations` records
which profile is active for a project. When a project has no active profile
the effective configuration is: factory defaults, overlaid by the
per-rule database overrides from the rules page.

Precedence, highest last:

1. Factory defaults
2. Per-rule database overrides
3. Active profile

## Where it takes effect

`app/services/validation.py:rule_configs(db, project_id)` merges the three
layers. `run_validation` calls it with the project id. `refresh_run` does
not: it reuses the `rules_snapshot` recorded on the run, so historical runs
keep the configuration they were created with even if the profile is later
changed or removed.

## The bundled sample

`apps/api/data/profiles/jp-bimcim-v1.yaml` configures the existing rules
for a Japanese workflow: 2-3 letter document prefixes, tighter metadata
requirements, approval-required before issue, and stale dependencies
escalated to CRITICAL.

**It is illustrative.** It does not claim compliance with any official
MLIT BIM/CIM guideline. Each rule id belongs to BIMGuard, not to MLIT.
Claiming verified compliance would require mapping each check to a specific
MLIT guideline version and clause, and shipping evidence for that mapping.
That has not been done. Do not describe this profile as MLIT-compliant.

## Adding a new profile

1. Write a YAML file. Copy the sample and change the `id`.
2. Drop it in `apps/api/data/profiles/`.
3. Restart the API (or set `BIMGUARD_PROFILES_DIR` to point at another
   directory).

No database migration is needed. The file is the source of truth.

## What profiles do NOT do (yet)

- They do not add new rule types. New checks are new code in the engine.
- They do not change how a rule interprets its input.
- They do not apply across projects. Activation is per project.
- They do not carry their own version of the engine. A profile written for
  `schema_version: 1` is expected to load on any later engine that still
  accepts `schema_version: 1`.

## Testing

- `tests/test_profiles.py` - loader behaviour: valid, invalid, unknown
  rule, bad severity, bad params, bad YAML, bundled sample still loads.
- `tests/test_profiles_api.py` - endpoints, permission checks, and the
  round-trip that proves activation changes the effective config.