"""Write the OpenAPI document to a file.

Run without a server, so CI can regenerate the frontend's types from the same
source of truth the API actually serves:

    python -m bsa.scripts.dump_openapi

The committed document is what `pnpm gen:api` reads, which means a backend
schema change that nobody regenerates types for shows up as a CI diff rather
than as a runtime surprise in the browser.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from bsa.api.app import create_app
from bsa.scripts.paths import shared_dir


def main() -> int:
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else shared_dir() / "openapi.json"
    output.parent.mkdir(parents=True, exist_ok=True)

    spec = create_app().openapi()
    # Sorted and newline-terminated so the file diffs cleanly.
    output.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")

    paths = len(spec.get("paths", {}))
    schemas = len(spec.get("components", {}).get("schemas", {}))
    print(f"wrote {output} ({paths} paths, {schemas} schemas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
