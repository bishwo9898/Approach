# Deploying a shareable demo

Vercel hosts the Next.js frontend. It cannot run FastAPI or PostgreSQL, so the
API and database go elsewhere — this guide uses Render, whose free tier is
enough for a demo.

Three things, in this order. The frontend needs the API's URL at build time, so
the API has to exist first.

---

## Before you start

**This is a demo deployment, not a production one.** Access is a shared passcode
per role: everyone holding it is the same user, and nothing is attributable to a
person. It exists so the link is not wide open. Clerk replaces it before this
holds data for athletes who did not agree to it being online.

Pick two passcodes now, at least 8 characters each. The API refuses to start in
production with anything shorter or with the development values.

---

## 1. API and database — Render

1. Push this repository to GitHub.
2. render.com → **New → Blueprint** → point it at the repository. It reads
   `render.yaml` and creates a `bsa-api` web service and a `bsa-postgres`
   database.
3. When prompted, set:
   - `BSA_COACH_PASSCODE`
   - `BSA_PLAYER_PASSCODE`
   - `BSA_CORS_ORIGINS` — leave blank for now, you will not have the Vercel URL
     until step 2.
4. Wait for the first deploy. It runs `alembic upgrade head` on start, so the
   schema is created for you.
5. Copy the service URL, e.g. `https://bsa-api.onrender.com`. Check it:

   ```bash
   curl https://bsa-api.onrender.com/health
   ```

   `database_target` tells you which database answered — useful whenever
   something looks wrong.

### Load an athlete into the hosted database

The database starts empty. Seed it from your machine using Render's **external**
connection string (Dashboard → the database → Connections):

```bash
cd apps/api
BSA_DATABASE_URL="postgresql+psycopg://...render external url..." \
  .venv/bin/python -m bsa.scripts.seed_athlete "../../CSV files/<athlete>/<export>.csv"
```

Re-run it with each new export; ingestion is idempotent.

---

## 2. Frontend — Vercel

1. vercel.com → **Add New → Project** → import the repository.
2. Set **Root Directory** to `apps/web`.

   > Every path in `apps/web/vercel.json` is resolved relative to this, which
   > is why it sets no `outputDirectory` — Next's default `.next` is already
   > correct. Setting it to `apps/web/.next` looks right and resolves to
   > `apps/web/apps/web/.next`, which fails *after* a successful build with
   > "The Next.js output directory was not found".
3. Add one environment variable:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_API_BASE_URL` | your Render API URL |

   This is baked into the browser bundle at build time. Changing it later needs
   a redeploy. It is only a URL — no secret is ever built into the frontend.
4. Deploy, and copy the resulting URL.

---

## 3. Close the loop

Back in Render, set `BSA_CORS_ORIGINS` to the Vercel URL (exactly, no trailing
slash) and let the API redeploy. Without this the browser blocks every request
and the app looks broken with nothing in the UI to explain why.

Then open the Vercel URL and sign in with a passcode.

---

## What to expect on a free tier

**The API sleeps after inactivity** and takes roughly a minute to wake. The
first load after a quiet period is slow. The app handles this deliberately: it
retries a request that could not reach the server for about a minute, and says
"the server may be starting up" rather than "wrong passcode", which is the
mistake that would otherwise send someone retyping a passcode that was correct.

Warm it up before a demo by opening the link a minute early.

**Raw imports are not retained.** `BSA_OBJECT_STORE_BACKEND=local` writes to a
disk that Render discards on restart, so archived source files do not survive.
Fine for a demo; the production answer is GCS, which the config already refuses
to run without in `BSA_ENV=production`.

---

## Before this holds data for athletes who have not agreed to it

- [ ] Replace the passcode gate with Clerk. Set `BSA_AUTH_PROVIDER=clerk`,
      `BSA_CLERK_JWKS_URL` and `BSA_CLERK_ISSUER`. `BSA_ENV=production` refuses
      to start with the dev provider, and refuses weak passcodes.
- [ ] Move the object store to GCS so the raw archive survives.
- [ ] Turn on database backups and restore one to prove it works.
- [ ] Agree a retention and consent position for minors' data.

See [SECURITY.md](SECURITY.md).
