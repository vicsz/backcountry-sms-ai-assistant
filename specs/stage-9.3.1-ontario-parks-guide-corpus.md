# Stage 9.3.1 — One-time Ontario provincial parks guide corpus

Status: Complete for the MVP; one-time corpus generated locally; rerunnable generator deferred

## Objective

Create one compact, source-linked Markdown file covering Ontario provincial parks for use as the
initial RAG corpus. The file is a generated one-time input, not a continuously refreshed dataset.
A future refresh stage may add a rerunnable extraction/normalization process. The MVP does not
require retaining that generator or maintaining a separate manifest.

## Output

Create exactly one canonical corpus file at:

`data/rag/ontario-provincial-parks-guide.md`

The file should contain a short introduction followed by one clearly delimited section per
provincial park. Each park section should include, where the official page provides the information:

- official park name and source URL;
- park classification and general location;
- available activities;
- facilities and rentals;
- camping types, including car, walk-in, group, winter, or backcountry where applicable;
- stable practical planning notes;
- a source and retrieval/review date.

The corpus may include a small “how to use this guide” section, but it is not a general camping
manual and should not contain extensive narrative copied from the source pages.

## Source and extraction boundary

Use Ontario Parks’ Park Locator and individual official park pages as the primary sources. The
extraction process may use the Park Locator catalogue, recurring page fields, activity/facility
labels, and selected stable camping/planning sections.

Exclude or clearly mark as non-RAG content:

- current fire bans, closures, alerts, advisories, weather, operating dates, fees, reservations,
  availability, and route conditions;
- legal-status conclusions or advice inferred from the source pages;
- unsupported descriptions for parks with sparse official information;
- personal data, contact details not needed for practical park identification, credentials, or
  secrets.

The corpus must preserve source URLs and distinguish an official source fact from a generated
summary. Facts that can change must carry a review/retrieval date and a “verify current details”
boundary rather than being presented as permanently current.

## MVP preparation requirements

- Discover the official park list from the Park Locator rather than maintaining a hardcoded park
  catalogue.
- Resolve each park to its official page and record missing, redirected, duplicate, or sparse pages.
- Normalize repeated fields into consistent Markdown headings and compact bullet lists.
- Preserve source wording for names and classifications; summaries must not invent amenities or
  suitability ratings.
- A rerunnable generator, input/output hashes, and an external manifest are deferred to a future
  ingestion or refresh stage.

## MVP quality checks

The generation check must verify:

- every discovered park is either represented once or explicitly listed as an omission;
- every park section has a source URL and park name;
- no excluded current-status terms or sections are included unintentionally;
- duplicate park sections and malformed Markdown are rejected;
- source links and retrieval metadata are present;
- the checked-in file is the intended single corpus object and has no accidental generated artifacts.

## Acceptance criteria and non-goals

- The single Markdown corpus is generated and reviewed for representative operating, non-operating,
  waterway, car-camping, and backcountry parks.
- The corpus includes all parks discoverable from the selected official catalogue or explicitly
  documents exclusions and missing source pages.
- A rerunnable generator and external manifest are not required for this MVP.
- No scheduled ingestion, automatic refresh, live status lookup, vector-store setup, handler change,
  deployment, or SMS send is part of this stage.
