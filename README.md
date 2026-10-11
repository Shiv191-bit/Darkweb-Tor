# DarkTrace local research build

Run the local analyst console with `make run`, then open `http://localhost:4173/dashboard`.

## What runs now

`scripts/build_normalized_archive.py` produces `data/darktrace_normalized.db`
from a locally supplied Silk Road historical archive. It stores only observed seller
handles, source-linked handle identifiers, listings, archived onion-address
observations, source metadata and scan provenance. It does not convert listings
or page assets into actors, and it creates no fabricated attribution claims.

The dashboard exposes real actor search, actor detail, evidence-graph data,
source status, CSV/JSON/PDF exports and a hash-chained audit log. All output is
labelled as an investigative lead, not proof.

## Safety boundary

The included collector is offline and text-only. It removes scripts, style and
media content before admission. Live Tor collection, probing, authentication,
and real-world enrichment are not enabled. They require an approved source
registry, legal authorization, configured service credentials where applicable,
and separately verified plugins.

## Rebuild evidence data

```sh
PYTHONPATH=. ./.venv/bin/python scripts/build_normalized_archive.py \
  data/raw/gwern_dumps/silkroad1-20111103-delyankratunov/Silk-Rabbit-Hole \
  data/darktrace_normalized.db
```
