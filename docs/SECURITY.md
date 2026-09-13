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

Delegated to a proven provider. We do not implement password storage, hashing,
reset flows or session management — there is no version of us doing that which
beats Clerk doing it.

| Provider | Use |
|---|---|
| `dev` | Local development and tests. Static seeded tokens, not secret. |
| `clerk` | Intended production provider. Verifies the JWT against Clerk's published JWKS, checking issuer, audience and expiry. |

`Settings` **refuses to boot** with `BSA_AUTH_PROVIDER=dev` when
`BSA_ENV=production`. The dev provider cannot reach production by
misconfiguration; the process will not start.

Clerk verification deliberately reads **no** role or organization claim. A token
failure returns "token verification failed" without saying why — telling a caller
precisely which check failed helps them forge the next one.

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
| `ADMIN` | All organization data, integrations, player mappings, metric configuration |
| `COACH` | Organization players and their analytics |
| `PLAYER` | Only the athlete their own user row points at |

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

- [ ] Replace the `dev` auth provider with Clerk; verify production refuses to
      boot with `dev`.
- [ ] Move all secrets to Secret Manager.
- [ ] Switch the object store to GCS with a retention policy.
- [ ] Enable Cloud SQL automated backups and confirm a restore.
- [ ] Add Sentry or equivalent error tracking.
- [ ] Confirm the facility's consent and retention policy for minors' data, and
      implement deletion on request.
- [ ] Review who holds `ADMIN` — it can remap athlete identities.
- [ ] Penetration-test the authorization boundary with a real player account.
