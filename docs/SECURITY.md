# Security

This system holds performance data about minors. That shapes every decision
below, and it is the reason several otherwise-convenient options were rejected.

## Threat model

The realistic risks, in the order they are likely to actually happen:

1. **An athlete reads another athlete's data** by changing an id in a URL.
2. **Data is attributed to the wrong athlete** by a name-matching shortcut in
   ingestion — invisible, and corrupts two histories at once.
3. **A vendor credential leaks** into the browser bundle, a log line, or the repo.
4. **Unnecessary PII accumulates** because a column was added "just in case".
5. **A coach acts on stale data** because a broken import was hidden rather than
   surfaced.

Nation-state adversaries are not the threat model. A curious teenager with a
browser devtools console is.

## Authentication

| Provider | Use |
|---|---|
| `local` | Current. Per-person accounts the facility provisions from a TrackMan roster export. Argon2id password hashes, opaque database-backed sessions. |
| `passcode` | One shared passcode per role. A demo gate, superseded. |
| `dev` | Local development and tests. Static seeded tokens, not secret. |
| `clerk` | Intended destination. Verifies the JWT against Clerk's published JWKS, checking issuer, audience and expiry. |

`Settings` **refuses to boot** with `BSA_AUTH_PROVIDER=dev` when
`BSA_ENV=production`. The dev provider cannot reach production by
misconfiguration; the process will not start.

Clerk verification deliberately reads **no** role or organization claim. A token
failure returns "token verification failed" without saying why — telling a caller
precisely which check failed helps them forge the next one.

### Why we hold passwords at all

The stated intent was to delegate this: there is no version of us doing password
storage that beats Clerk doing it, and `clerk.py` is still where this is going.
What changed is that the athletes are minors added from a roster export. They
have no corporate identity to federate, no work email, and in many cases no
email at all. A shared passcode per role cannot tell two of them apart, which
means nothing is attributable and every athlete sees the same thing.

So `local` is the honest interim, and it is deliberately narrow:

| | |
|---|---|
| Hashing | Argon2id, 19 MiB / t=2 / 1 lane — OWASP's recommended minimum. Never a fast hash. |
| Storage | `user_credentials`, a separate table. Every authenticated request loads a `User`; none of them carries a password hash into memory or a log line. |
| Sessions | Rows in `user_sessions`, not signed tokens — a row can be revoked on sign-out, and a signed token cannot. Only the SHA-256 of the token is stored; a reader of that table cannot sign in as anyone. |
| Lockout | Counted in Postgres, not in process memory, so a restart or a second instance does not hand an attacker a fresh budget. |
| Rate limit | A per-client sliding window on the unauthenticated endpoints. In-process, and therefore defence in depth only — the lockout is the control that has to hold. |

**What it does not do:** password reset, email verification, or multi-factor.
All three need a mail channel this system does not have. A forgotten password is
cleared by a coach. Self-service reset without a mail channel would reduce to
"anyone who knows the address can take the account", which is strictly worse
than the inconvenience.

### Claiming an account

Accounts are provisioned with no password; an athlete claims one.

```
provisioned --prove the address--> choose a password --> sign in
```

Two properties that are easy to get wrong and are tested:

1. **Step two re-proves step one.** Setting a password repeats every check
   itself, because the lookup hands back nothing that could serve as proof it
   succeeded.
2. **Only one caller can claim an account.** The password is written with a
   conditional `UPDATE` that matches only while no password is set, so two
   simultaneous setups cannot both succeed.

### The one deliberate disclosure

Account setup answers "is this address on the roster?" — a plain 404 with
"Email does not match." Sign-in never does: a wrong address and a wrong password
return the same message after the same amount of work (an unknown address still
pays for a dummy Argon2 verification, so timing does not leak either).

The asymmetry is intentional. Somebody given their address verbally cannot fix a
typo if the only feedback is "something was wrong", and the roster this reveals
is the facility's own class list, which every athlete in it already knows.

What it costs: addresses are `firstname.lastname@<domain>`, so they are
guessable from a team sheet. **`BSA_SIGNUP_GATE` is what closes that**, and it is
the single most important setting in a deployment:

| | |
|---|---|
| `open` | A matching address is enough. Whoever types it first owns the account. Development and demos against data nobody minds a stranger reading. |
| `code` | A matching address **and** the account's one-time activation code, which the coach distributes. The code is stored as an Argon2 hash and shown exactly once, at provisioning. |

A staging or production API **refuses to start** until it is set explicitly. An
unset gate is not defaulted to the safe value — it is refused, so the choice is
always on the record as somebody's.

A missing code costs no lockout attempt; only a wrong one does. The setup form
learns a code is needed from the reply, and charging for that would lock people
out for following the form as designed.

## Authorization

**Authorization is ours, in our database, on every protected request.**

```
credential → AuthProvider.verify() → subject id
                                        │
                     users(auth_provider, auth_subject)   ← our row, our truth
                                        │
                       organization_id + role + player_id
```

Nothing a token asserts about permissions is honoured. A compromised or
misconfigured auth provider cannot grant itself access to an athlete.

### Roles

| Role | May access |
|---|---|
| `ADMIN` | Everything a coach can reach, plus room for operations a facility may later want to withhold from coaching staff |
| `COACH` | Every athlete in the organization and their analytics; adding an athlete, mapping a vendor identity, attaching a session video |
| `PLAYER` | Only the athlete their own user row points at |

The facility runs on two roles, coach and player. `ADMIN` is therefore vacant,
and anything gated on it is unreachable — which is how a "Map athlete" control
ended up on the coach's own Data Health page under the label *Admin mapping
required*. Staff actions are gated on `require_staff` (admin **or** coach) for
that reason, not because the distinction stopped mattering: the role still
exists, and a third role can take operations back off coaches without a schema
change.

What never widens is the athlete boundary. `PLAYER` is checked separately and
against the athlete their own row points at, so none of the above touches it.

`PARENT` is future scope and is not implemented.

### Defence in depth

1. **Every repository function takes `organization_id` and filters on it.**
   Cross-tenant access is impossible at the data layer, independent of what the
   API checked.
2. **`authorize_player` is the single choke point** for athlete access. Player
   endpoints under `/api/v1/me/*` never accept an athlete id at all — there is
   nothing to tamper with.
3. **A foreign athlete returns 404, not 403.** The difference would confirm which
   athletes are enrolled at the facility.
4. **The frontend `AuthGate` is navigation, not a control.** Deleting it makes
   the app confusing, not insecure.

Covered by tests in `tests/integration/test_api_authorization.py`: anonymous
access, malformed credentials, valid-but-unknown credentials, player reaching
another athlete across six endpoints, player reaching coach endpoints, coach
attempting an admin-only action, and cross-organization access in both directions.

### Merging two vendor rows into one athlete

The roster export lists vendor accounts, not people, and TrackMan entered some
athletes twice. Those rows are merged into one athlete on an exact rule the
facility set: **identical first name, last name and date of birth.**

This is the one place the system collapses two identities, so the limits are
deliberate:

- A shared name alone is never enough. Neither is a shared birth *year*.
- A row with no readable birth date is never merged — the evidence is missing.
- A merge that rests on a date the export repeats dozens of times (a bulk-upload
  default rather than a birthday) is flagged separately in the report, because
  there the name is carrying the whole claim.
- Merging two athletes who already exist separately will not retire a record
  that carries imported data or a claimed login. Moving sessions between
  athletes, and taking away a login in use, are decisions a provisioning script
  must not make by itself; it reports them instead.

Retired records are deactivated, never deleted, so the history stays readable
and the address stays taken rather than becoming re-issuable to somebody else.

## Identity integrity

An athlete is resolved **only** by an explicit `(provider, external_id)` row.
Name matching resolves nothing and maps nothing — this is enforced in code and
asserted by a test that creates a same-named player and confirms nothing attaches
to them.

Unknown vendor athletes are queued for a human; their events are held, not
attached. Mapping is an `ADMIN` action and is audited. Uniqueness on
`(organization, provider, external_id)` makes it impossible for one vendor
identity to point at two athletes.

## Secrets

**Never in source control.** `.gitignore` excludes `.env*` (except
`.env.example`), `*.pem`, `*.key` and `service-account*.json`.

| Environment | Source |
|---|---|
| Development | `.env`, gitignored |
| Production | Google Secret Manager, injected as environment variables |

**Vendor credentials never reach the browser.** TrackMan and Futures credentials
are read server-side only. `NEXT_PUBLIC_*` carries exactly one value — the API
base URL. There is no integration configuration in the frontend at all, so there
is nothing to leak.

**Nothing credential-shaped is logged.** Audit metadata is scrubbed of any key
containing `password`, `token`, `secret`, `authorization`, `api_key` or
`credential` before it is written — audit rows are the most widely-read table
during an incident. Covered by a test.

## Data minimization

A field is added when a feature requires it, not when it might one day.

- `date_of_birth` is nullable, exists only for future age-band grouping, and
  nothing in Phase 1 reads it.
- No medical data. No contact details beyond a login email.
- No home address, phone number, school, or guardian information.
- `external_display_name` is stored for operator recognition only and is never
  used for matching.

## Analytics restraint

This system makes **no** medical, injury or risk claims, and must not begin to.

A velocity drop is reported as a change in velocity. If unusual changes are ever
surfaced, the language is "recent performance change" — never "injury risk". A
frontend test asserts that a negative change renders without injury or risk
wording, so the constraint is enforced rather than merely intended.

Injury prediction and ML are explicitly out of scope (see the phase plan). With
minors involved, an unvalidated model producing a scary number is a real harm,
not a feature.

## Transport and deployment

- HTTPS everywhere (terminated by Cloud Run).
- CORS restricted to configured origins; `Authorization` and `Content-Type` only.
- OpenAPI docs are disabled in production.
- Upload size capped at 32 MB.
- Object store keys are content-addressed and validated against directory
  traversal.
- `Settings` refuses to boot in production with a local object store — Cloud Run
  disks are ephemeral and the raw archive would be silently lost.
- Cloud SQL and GCS reachable only by the service account, least privilege.

## Audit

Narrow by design — administrative actions that override or reshape athlete-facing
data, not a request log:

`PLAYER_MAPPING_CREATED · PLAYER_MAPPING_CHANGED · METRIC_CREATED ·
METRIC_CHANGED · PR_OVERRIDDEN · FUTURES_SYNC_MANUALLY_CONFIRMED ·
IMPORT_REPROCESSED`

Each entry records actor, organization, action, target, timestamp and scrubbed
metadata. `actor_label` is denormalized so the log stays readable after a user is
deactivated or renamed.

## Operational honesty

Broken automation is shown, not hidden. The coach dashboard surfaces last
successful import, failed imports, sessions awaiting verification, unresolved
athletes and pending Futures updates.

A coach who does not know an import failed will read a stale dashboard as if it
were current, and make training decisions on it. That is a safety property, not a
UX preference.

## Before real athlete data is loaded

- [ ] Replace the `local` provider with Clerk, which brings password reset and
      email verification; verify production refuses to
      boot with `dev`.
- [ ] Move all secrets to Secret Manager.
- [ ] Switch the object store to GCS with a retention policy.
- [ ] Enable Cloud SQL automated backups and confirm a restore.
- [ ] Add Sentry or equivalent error tracking.
- [ ] Confirm the facility's consent and retention policy for minors' data, and
      implement deletion on request.
- [ ] Review who holds `ADMIN` — it can remap athlete identities.
- [ ] Penetration-test the authorization boundary with a real player account.
