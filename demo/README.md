# Demo snapshot

`snapshot/` holds the frozen copy of the real store that demo mode serves (`docker compose up`, or
`python -m ci.api --demo demo/snapshot`). It is built by `python -m ci.demo build --out demo/snapshot` from a real
daily run: no LLM call, no simulated data. Items keep only the D34 allowlist (title, URL, dates, source, competitor,
category, score, status, reason, our summary and a 280-character excerpt); full article text is never included.
`snapshot/snapshot.json` names the snapshot's date, its runs and the commit it was built from.

The API never writes `snapshot/`. In the default writable demo (D111) each start copies `ci.sqlite` and
`changes.sqlite` to a new temporary folder (`ci.demo.prepare`) and actions write only there; a startup guard proves
that opening the copy changed 0 rows, or the demo serves `snapshot/` read-only instead (also with
`CI_DEMO_READ_ONLY=1`).
