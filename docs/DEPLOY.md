# Deploying a shareable demo

Vercel hosts the Next.js frontend. It cannot run FastAPI or PostgreSQL, so the
API and database go elsewhere — this guide uses Render, whose free tier is
enough for a demo.

Three things, in this order. The frontend needs the API's URL at build time, so
the API has to exist first.

---

## Before you start

**This is a demo deployment, not a production one.** It runs with
`BSA_ENV=staging`, because it does not meet what production enforces — a durable
object store, chiefly. What it *does* have is real per-person accounts: every
athlete has their own login and the server decides, on every request, which
athlete that person may read.

**One decision before you start: `BSA_SIGNUP_GATE`.**

Login addresses are `firstname.lastname@approach.com`, derived from the roster,
so anyone holding a team sheet can guess one. The gate decides whether guessing
an address is enough to claim that athlete's account:

| | |
|---|---|
| `code` | a matching address **and** the one-time activation code a coach hands out. `render.yaml` sets this. |
| `open` | a matching address alone. Only for a demo against data you would not mind a stranger reading. |

The API refuses to start in staging or production until this is set explicitly,
so nobody inherits the answer by accident.

---

## 1. API and database — Render

1. Push this repository to GitHub.
2. render.com → **New → Blueprint** → point it at the repository. It reads
   `render.yaml` and creates a `bsa-api` web service and a `bsa-postgres`
   database.
3. When prompted, set `BSA_CORS_ORIGINS` — leave it blank for now, you will not
   have the Vercel URL until step 2. `BSA_SIGNUP_GATE` comes from
   `render.yaml` as `code`; change it in the dashboard only if you decided on
   `open` above.
4. Wait for the first deploy. It runs `alembic upgrade head` on start, so the
   schema is created for you.
5. Copy the service URL, e.g. `https://bsa-api.onrender.com`. Check it:

   ```bash
   curl https://bsa-api.onrender.com/health
   ```

   `database_target` tells you which database answered — useful whenever
   something looks wrong.

### Load the roster and the data into the hosted database

The database starts empty. Both steps run from your machine, because the roster
export and the session exports are never committed — they are real athletes'
names, birth dates and sessions. Use Render's **external** connection string
(Dashboard → the database → Connections).

Accounts first:

```bash
cd apps/api
BSA_DATABASE_URL="postgresql+psycopg://...render external url..." \
BSA_ENV=staging BSA_SIGNUP_GATE=code \
  .venv/bin/python -m bsa.scripts.provision_roster "<roster export>.csv" \
    --emails birth-year --codes
```

That writes `var/activation-codes-*.csv`. **It is the only readable copy** — the
database stores only hashes — and it is what a coach reads out to each athlete.
Keep it off the repository; `var/` is gitignored.

Then the sessions:

```bash
BSA_DATABASE_URL="postgresql+psycopg://...render external url..." \
  .venv/bin/python -m bsa.scripts.ingest "../../CSV files/<athlete>/<export>.csv"
```

Re-run either with each new export; both are idempotent.

To give yourself a login for the demo itself, add `--demo-accounts
--demo-password "<something you chose>"` to the provisioning command. Outside
development the password is required rather than defaulted, so a deployed
database never ends up with a password that is written down in this repository.

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

Then open the Vercel URL and sign in. A first-time athlete uses **Set up your
account**: their email, their activation code if the gate requires one, then a
password of their own.

---

## What to expect on a free tier

**The API sleeps after inactivity** and takes roughly a minute to wake. The
first load after a quiet period is slow. The app handles this deliberately: it
retries a request that could not reach the server for about a minute, and says
"the server may be starting up" rather than "email or password is incorrect",
which is the mistake that would otherwise send someone retyping a password that
was correct all along.

Warm it up before a demo by opening the link a minute early.

**Raw imports are not retained.** `BSA_OBJECT_STORE_BACKEND=local` writes to a
disk that Render discards on restart, so archived source files do not survive.
Fine for a demo; the production answer is GCS, which the config already refuses
to run without in `BSA_ENV=production`.

---

## Before this holds data for athletes who have not agreed to it

- [ ] Replace the local accounts with Clerk, which brings password reset and
      email verification — neither of which exists here, because both need a
      mail channel. Set `BSA_AUTH_PROVIDER=clerk`,
      `BSA_CLERK_JWKS_URL` and `BSA_CLERK_ISSUER`. `BSA_ENV=production` refuses
      to start with the dev provider.
- [ ] Decide what happens when an athlete forgets their password. Today a coach
      has to clear it for them, because self-service reset without a mail
      channel reduces to "anyone who knows the address can take the account".
- [ ] Move the object store to GCS so the raw archive survives.
- [ ] Turn on database backups and restore one to prove it works.
- [ ] Agree a retention and consent position for minors' data.

See [SECURITY.md](SECURITY.md).
