# imports

Drop real TrackMan exports here.

This folder is mounted into the API container at `/data/imports`, so you can
inspect a file without copying it anywhere:

```bash
docker compose exec api python -m bsa.scripts.inspect_csv /data/imports/your-export.csv
```

**Everything in this folder except this README is gitignored, deliberately.**
Real exports contain real athlete data and must never be committed. The
synthetic fixtures under `samples/trackman/` are the ones that belong in the
repository.
