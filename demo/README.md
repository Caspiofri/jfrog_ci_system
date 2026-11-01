# Demo snapshot

`snapshot/` holds the frozen copy of the real store that demo mode serves (`docker compose up`, or
`python -m ci.api --demo demo/snapshot`). It is built by `python -m ci.demo build --out demo/snapshot` from a real
daily run: no LLM call, no simulated data. Items keep only the D34 allowlist (title, URL, dates, source, competitor,
category, score, status, reason, our summary and a 280-character excerpt); full article text is never included.
`snapshot/snapshot.json` names the snapshot's date, its runs and the commit it was built from.
