# Combined tournament ingestion

Play Limitless provides an additional population of events; it does not replace
the official-event pages at limitlessvgc.com. Both collectors now use
`ingestion.py` to populate the existing tables. PokeAPI remains the reference source.

## Normal pipeline

```sh
python start_app.py
```

This starts the database, checks/seeds references, builds both collectors, and runs
the official-event scraper followed by the API importer. The API service is also
part of a normal `docker compose up --build`; it waits for seeding before importing.
The launcher attempts both collectors and returns a failure code if either fails.

Before either collector, the seeder verifies every reference catalog using
`reference_seed_progress` and `reference_seed_stages`. PokeAPI timeouts are retried
(five total attempts, 45-second read timeout). Each complete resource and its
checkpoint commit together; a Pokémon and both types cannot be partially committed.
An exhausted retry stops startup with a nonzero status, and the next run resumes
the unfinished resource. Existing pre-checkpoint rows are verified once, preserving
their IDs. Catalogs are cached for 24 hours and details under `data/pokeapi/`.

For a forced refresh of reference data only:

```sh
docker compose -f Fetch_Data/compose.yaml run --rm --no-deps seed python seed_database.py --refresh
```

You can inspect reference progress without downloading anything:

```sql
SELECT stage, expected_count, completed_count, completed_at, last_error
FROM reference_seed_stages ORDER BY stage;
```

The API defaults to **all VGC formats returned by `/games`**, with **no event cap**.
The first run backfills matching history and can be long. Subsequent imports scan
the listings but skip older events already committed to PostgreSQL. Events started
within the last 14 days are fetched again to pick up results and delayed sheets.
Downloaded files alone never count as successful imports, so failed events are
retried on the next run. This is invoked on each pipeline run, not a scheduled job.

For a bounded first pipeline run, `python start_app.py --api-max-events 2` imports
at most two eligible events **per format**, while the scraper runs normally.

## Run an audit first

From the repository root, with the requirements installed:

```sh
python -m pip install -r Fetch_Data/requirements.txt
python -m Fetch_Data.limitless_api --max-events 2
```

This downloads public data and writes timestamped JSON snapshots under
`Fetch_Data/data/raw/play_limitless/` (gitignored). It does **not** connect to the
database or apply a migration. Each output line summarizes an event. Counts are
structural checks only: `placement_candidates` is not a count of fully verified
legal teams. Reference lookup happens during import.

Useful options:

- Omit `--regulation` (or use `--regulation all`) to collect all advertised formats.
- `--regulation I --regulation H`: select several formats; API codes also work.
- `--max-events 2`: optional per-format cap; omit for the full backfill/sync.
- `--refresh-days 0`: skip all previously imported events, including recent ones.
- `--refresh-all`: re-fetch selected old imports too, e.g. after fixing normalization.
- `--before 2026-05-01 --after 2025-05-01`: exclusive/inclusive UTC start-date bounds.
- `--min-players 16`: restrict discovery to larger events.
- `--event-id ID`: inspect a specific event; repeat for multiple events.
- `--without-pairings`: omit match collection; existing saved pairings remain intact.
- `--cache-dir PATH`: change the raw snapshot directory.
- `--report PATH`: save a run report at a specific location.

Successful old imports with missing or quarantined sheets are still considered
imported. Use `--refresh-all`, or explicit event IDs, to revisit them after the
14-day refresh window. If an earlier import omitted pairings, a later full import
does not skip it. Explicit event IDs always fetch, regardless of existing data.

Discovery is paginated and deduplicates event IDs. Today's and future start dates
are excluded by default. A past start date alone does not prove an event finished;
the documented API has no completion flag. Check outcomes before choosing a
training cohort. There is no API key requirement for these tournament endpoints.
Requests use timeouts, sequential pacing, rate-limit hints, and bounded retries
for connection failures, HTTP 429, and server errors.

## Import

```sh
python -m Fetch_Data.limitless_api --write --env-file Fetch_Data/.env
```

The PostgreSQL reference tables must already be seeded. The optional dotenv file
does not override existing environment variables. A host-side connection normally
uses `DB_HOST=127.0.0.1` and `DB_PORT=5433`; Docker uses `DB_HOST=db` and port 5432.

`--write` first applies `migrations/001_multi_source.sql` once, then imports each
event in its own transaction. This migration is additive, retains existing IDs,
and removes uniqueness from event names. **Do not rerun `01_schema.sql` to migrate
an existing database:** that bootstrap file drops tables. Back up your database
before any production migration.

For the existing Docker setup:

```sh
docker compose -f Fetch_Data/compose.yaml build api
# Audit two events per format; supplying arguments replaces the service's --write default.
docker compose -f Fetch_Data/compose.yaml run --rm --no-deps api --max-events 2
# Import all formats (service command defaults to --write).
docker compose -f Fetch_Data/compose.yaml run --rm api
```

The API service shares database settings and persists raw snapshots and reports on
the host. Standalone Python calls still default to audit mode; the pipeline/Docker
service explicitly enables writing. No deployment or scheduler is required.

## Existing scraper

The official scraper follows each event's `standings.limitlessvgc.com` link when
available. It reads the full embedded standings payload (including entrants hidden
by the site's top-256 display filter), then fetches each advertised public sheet.
Records, drop rounds, country, raw sheets and raw standings rows are retained.
Players without sheets remain in the database, excluded from sheet-based training.
This website adapter is separate from the documented Play Limitless API.

Existing official events without the adapter-version marker are automatically
revisited when discovered; recent events (within 14 days) are revisited as well.
Discovery still defaults to the first two 100-event pages; increase `--pages` for
older history. Events without a Standings link retain results-page coverage.
The report now separates `unreturned_players` from `missing` sheets among returned
players and identifies `coverage_scope` (`full_standings` or `results_page`).

For a specific official event, including an already imported one:

```bash
docker compose -f Fetch_Data/compose.yaml build scraper
docker compose -f Fetch_Data/compose.yaml run --rm --no-deps scraper python scraping_limitless.py --event-id 443
```

Team-sheet HTML is cached under `Fetch_Data/data/official_standings` and mounted
into the scraper container. Interrupted downloads resume from that cache; standings
are always fetched anew. `--refresh` bypasses sheet caches and detects changes.
Old `event_ID.json` files cannot bypass coverage upgrades. Network errors, unfinished
events, changed payload markup, and attendance mismatches still fail the event
without committing a partial replacement. Identity ambiguity is handled per participant. Successfully cached sheets
remain available for the retry. No reset or deletion of existing data is needed.

Existing player identities are adopted using unique normalized names, or shortened
names with matching placing and country. Stable event participant IDs are then used
for repeat imports. Changed builds remain conflicts for review rather than silently
overwriting existing sheets. Complete collection does not guarantee every sheet
resolves against the local Pokémon/item/move reference tables.


## Identity and repeat imports

- Events have an internal integer ID plus unique `(source, external_id)`. Existing
  events are backfilled as `limitless_vgc`. Newly imported events use a sequence.
- API players use stable source account IDs, not display names. A `player_sources`
  table maps these IDs to internal players. Cross-source identities are not guessed.
- Scraped display-name identities are scoped to an event. Existing player/team rows
  are adopted only when there is exactly one matching name in that same event.
  Ambiguous matches roll back the event for manual review.
- Repeated imports update results and missing sheets without duplicating entrants.
  Identical builds used by different entrants remain separate observations.
- Raw payload versions are retained in `ingestion_snapshots`. A changed existing
  build is flagged `conflict`; its normalized Pokémon rows are preserved and it is
  excluded from training pending review. Even filling a missing field in an already
  stored sheet currently requires review if it changes that sheet.
- Match responses are retained in `event_pairings` with source player IDs, phases,
  rounds, and winner values. Byes, automatic losses, ties, and double losses remain
  distinguishable. These are match outcomes, not individual game scores.
- Participant rows absent from a later response are not automatically deleted.

## Quality and training

Each entrant receives `sheet_status` and `quality_issues`. Missing sheets still
produce participant/result rows. Invalid sheets and unknown Pokémon/item/move/
ability references are retained in raw snapshots but are not inserted into feature
tables. One unresolved sheet does not discard the rest of its event.

Checks cover six members, duplicate held items, duplicate species (including shared
Pokédex numbers during import), move counts/duplicates, placement range, and explicit
custom rules. Missing ability/moves produces a partial-build warning; missing Tera
is checked for the Scarlet/Violet lettered regulations, not Series or M formats.
Series 12 maps to `S12`; all source format codes and names remain in event metadata.
An unrecognized format is retained but excluded from training pending mapping. A missing
held item is allowed. These checks **do not certify full regulation legality**:
restricted-species limits, move learnsets, organizer mislabeling, and historical
sheet accuracy still require review. EVs, IVs, and natures are not assumed available.
Some newer-format responses include natures: these remain in the raw snapshots,
but are not yet normalized into model features. `complete` refers to the fields
this pipeline models, not every possible build field or battle transformation.

Use `analysis/all_teams_reg_combined.sql` instead of `analysis/all_teams_reg.sql`
when training on mixed sources. The new query uses `training_team_entries`, which
excludes missing/conflicting/invalid sheets, requires six stored members, and
requires a valid placement and event size greater than one. Original notebooks
and their query have not been switched automatically. After importing API data,
switch to the combined query before retraining to avoid unlabeled entrants.

For a full-build model, additionally require `t.sheet_status = 'complete'`;
composition-only models can use `partial` rows. Legacy scraped sheets are marked
`legacy` until refreshed, so completeness is not asserted for them.

Keep `source`, platform, online status, and phase modes available for cohort
selection. Do not include placement, final record, drop round, or current-event
outcomes as predictor features. Preserve event-based temporal splits and compare
official-only versus combined training on the same held-out official events.
Null placements are never invented; those entrants remain available for a later
match-outcome model instead of entering placement regression.

Collecting all formats does not mean pooling incompatible formats in one training
set. Keep the query's `:regulation` parameter when building each model's dataset.

## Verify coverage and routine operation

Each API run saves `Fetch_Data/data/runs/TIMESTAMP.json` by default. It records
per-format discovered, skipped, processed, failed, and sheet-coverage counts. An
import also records database-wide coverage by source/regulation. `capped: true`
means the selected run was bounded and does not establish full historical coverage.
`status` distinguishes completion, completion with errors, and an aborted run.

1. Audit two events per format and inspect the report for missing formats/failures.
2. Run the isolated-schema tests below to verify normalization and database loading.
3. Import a bounded batch, then repeat with `--refresh-days 0`: previously imported
   IDs should be skipped; a capped run may continue to the next unseen events.
4. Use `--event-id ID --write` twice to explicitly prove a repeat import does not
   duplicate that event or its teams. Inspect quality flags and raw snapshots.
5. Check `analysis/ingestion_coverage.sql` for per-source, per-regulation usable
   training counts. Event totals alone do not demonstrate useful team coverage.

The test suite separately verifies launcher routing, format isolation, incremental
skipping, recent-event refresh, and nonzero failure propagation. A live API audit
tests public availability; it does not prove full historical completeness or
legality of organizer-submitted sheets.

## Tests

```sh
python -m unittest discover -s tests -v
VGC_TEST_DATABASE=1 python -m unittest discover -s tests -v
# Optional: repeat-import cached API events in an isolated schema using copies of
# your existing reference tables, and write Fetch_Data/data/pilot_report.json.
VGC_TEST_DATABASE=1 VGC_TEST_SNAPSHOTS=1 python -m unittest discover -s tests -v
```

The second command needs the local database settings and `python-dotenv`. It creates
uniquely named temporary schemas, excludes `public` from the search path, and removes
only its own schemas afterward. Tests cover repeat imports, migration preservation,
legacy backfill, source-ID collisions, conflict handling, unknown references,
rollback, missing labels, form mapping, pagination, and rate-limit retries.

API documentation: https://docs.limitlesstcg.com/developer/tournaments.html

### Official full-field validation

A live Frankfurt (event 443) audit retrieved all 1,129 reported entrants and
1,129 six-member sheets, compared with 163 entrants on the results page. Importing
that snapshot twice into an isolated schema produced 1,129 entrant records and
1,121 training-eligible sheets without duplicate insertion or changes to production
data. Eight sheets were quarantined against the current reference tables: six
contained the literal item value `Held Item:` and two used `Leek`, which did not
resolve. These source values remain raw for review; coverage is not equivalent to
training eligibility. Audit files are under the gitignored
`data/official_standings/frankfurt_*_audit.json` paths.


### Unresolved player identities

Migration `002_identity_reviews` adds `pending_identity_reviews`. Ambiguous or
unmatched result identities are saved with their candidate standings entries and
raw sheets; unaffected entrants import normally. Existing player/team/build rows
are preserved. The training view excludes any existing player IDs implicated in
an open review. Multiple claims to the same participant are all held for review;
no candidate wins because it appeared first.

Reports distinguish `unresolved` reference values from identity problems:
- `imported_entrants`: entrants processed into the main tables during this run
  (including existing entrants updated on repeat runs).
- `pending_identity_entrants`: collected entrants held out during this run.
- `identity_review_count` and `identity_review_names`: open review cases and names.
- `import_status`: `imported` or `imported_with_unresolved_identities`.

Pending official events are added to subsequent normal scraper runs even outside
the selected discovery pages and are never skipped as finished. Sheet caches are
reused. A later safe match adopts the existing identity, resolves the review, and
restores training eligibility subject to the normal quality checks. Reviews remain
pending if an entry merely disappears from the source. Resolved review records and
original ingestion snapshots remain available for audit; repeat retries do not
create duplicate review rows. This does not automatically guess a match that stays
ambiguous, and there is no manual-resolution UI yet.

Inspect open cases with:

```sql
SELECT e.external_id, e.event_name, r.review_key, r.payload, r.first_seen, r.last_seen
FROM pending_identity_reviews r JOIN events e USING(event_id)
WHERE r.resolved_at IS NULL
ORDER BY e.event_id, r.review_key;
```

### Shared Pokémon normalization

`normalization.py` is the single mapping implementation for the HTML scraper,
Standings sheets, Play Limitless API, and normalization of cached scraped records.
The HTML scraper now retains the `/pokemon/...` identifier as well as display
text. All collectors preserve original fields, normalization version, and issues.
The old public helper names remain compatibility wrappers around this module.

Limitless base identifiers use a consistent convention: `indeedee` becomes
`indeedee-male`, `maushold` becomes `maushold-family-of-four`, `landorus` becomes
`landorus-incarnate`, and `palafin` becomes `palafin-zero`. Explicit alternate forms
remain distinct. A specific display form can refine a generic ID. Conflicting
explicit IDs/names and ambiguous name-only form labels are flagged and excluded
from training. Unknown reference names still require review; normalization is not
complete legality validation.

Abilities such as Calyrex's `As One` use the resolved form. Blank `Held Item:`
labels become missing items, and move placeholders are removed consistently.
Source-specific display spellings, regional forms and form-name ordering share
one alias table. No collector has an independent set of species defaults anymore.

Existing stored builds are not silently rewritten. Reimporting a changed old build
can still produce a conflict: unifying future normalization cannot by itself prove
that every historical inferred form was correct. Original raw snapshots should be
used to review those conflicts. Already-skipped historical events require an
explicit `--event-id` (scraper) or `--refresh-all` (API) to revisit them. For official
Standings events, a targeted import reuses cached raw sheets and applies the new
normalizer without needing to download every sheet again.

### Console output

Live ingestion output is deliberately compact: `[OK]` marks a clean event,
`[WARN]` adds a second line containing only fields that need review, `[WAIT]`
explains API backoff, and `[ERROR]` identifies a failed event or discovery stage.
`new sheets` is the number inserted during that run, not the event's total sheet
count. Full event payloads, counters, errors, snapshots, and database coverage
remain in the timestamped JSON run report. The official scraper hides tracebacks
by default; pass `--verbose-errors` when debugging implementation failures.
