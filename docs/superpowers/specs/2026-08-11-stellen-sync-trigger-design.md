# Trigger the Stellen sync on change instead of on a schedule

Date: 2026-08-11

Follow-up to [2026-08-10-opencloud-stellen-sync-design.md](2026-08-10-opencloud-stellen-sync-design.md),
which built the sync itself. That design is unchanged by this one.

## Problem

The sync runs on `*/15 6-18 * * 1-5`: roughly **1,100 workflow runs a month**, each
spinning up a fresh VM, to catch job-ad changes that happen **two to four times a
month**. Over 99% of those runs find nothing to do and report `no changes`.

Actions minutes are free on this public repository, so this is not about cost. It is
about not starting eleven hundred virtual machines to answer a question whose answer
is almost always "no".

Goal: GitHub does work only when something actually changed.

## The shape of the fix

Something outside GitHub notices a change and asks GitHub to run the existing sync.

```
OpenCloud folder ──▶ change detector ──▶ workflow_dispatch ──▶ sync-stellen.yaml (unchanged)
```

The detector carries no information about *what* changed. The sync is already an
idempotent full mirror, so "something moved, go look" is sufficient. This keeps the
entire tested pipeline — validation, canonicalisation, the wipeout guard, all 62
tests — exactly as it is.

It also means a missed signal costs latency, not correctness, provided the cron
survives as a backstop. That is what makes the detector an optimisation rather than
critical infrastructure, and it is the property worth protecting in every decision
below.

## Trigger: `workflow_dispatch`, not `repository_dispatch`

This is the security-relevant choice, and the two endpoints differ sharply:

| Endpoint | Fine-grained permission | What a leaked credential permits |
|---|---|---|
| `repository_dispatch` | **Contents: write** | Push arbitrary commits — publish anything to the live site |
| `workflow_dispatch` | **Actions: write** | Run existing workflows; cancel and re-run jobs |

`Actions: write` cannot modify repository contents, cannot modify workflow
definitions, and cannot read secrets. The worst a stolen credential achieves is
nuisance — cancelling builds, deleting run history — rather than publishing
fabricated content on a childcare organisation's website.

`sync-stellen.yaml` already exposes `workflow_dispatch`, so **the workflow needs no
change to support this**.

## Detector: NATS consumer

OpenCloud runs NATS as its event broker. Services publish events there and consume
them through ConsumerGroups, and an external consumer can register its own. The
detector subscribes, and on any create or delete beneath the job-ad folder calls
`workflow_dispatch`.

It must run on the OpenCloud host, or at least inside its network: NATS is internal
and not exposed the way WebDAV is.

### Verification comes first

Two things are not settled by the public documentation and must be confirmed on the
running instance before any code is written:

1. The event type names for file creation and deletion.
2. Whether an external ConsumerGroup is a supported, stable interface, or an
   internal one that merely happens to be attachable.

Until both are known the listener cannot be finished, and its long-term maintenance
cost cannot be judged. The verification is a subscription on the host while adding
and deleting a file in the folder — see "Verification on the host" below.

Also to be established there: whether the NATS endpoint requires credentials, and
whether it is JetStream-backed. The documentation's description of events persisted
to disk and delivered to ConsumerGroups implies JetStream, which determines the
client library and the consumer configuration.

### Not the postprocessing hook

Do **not** implement this as a `POSTPROCESSING_STEPS` custom step, despite it being
the more obvious "official" extension point. It is an *upload* pipeline: deletions
never reach it, and deleting a PDF is half of the workflow. It also blocks upload
finalisation until the custom step replies, so an outage in the listener wedges
uploads for ordinary users. A passive consumer has neither problem.

### Filtering

Events will cover the whole deployment, not just the job-ad space. The listener must
filter to the relevant space and path prefix, and ignore everything else. Getting
this wrong is cheap in one direction and not the other: an over-broad filter causes
harmless `no changes` runs, while an over-narrow one silently misses publications.
When in doubt, filter loosely.

### Fallback: local WebDAV poll

If external ConsumerGroups turn out to be unsupported, or the event contract looks
too unstable to depend on, the same trigger can be driven without touching OpenCloud
internals at all:

```
every minute:
    listing = rclone lsl OC:Stellenanzeigen        # names, sizes, mtimes
    hash    = sha256(listing)
    if hash != contents of state file:
        dispatch; store hash
```

About twenty lines, no OpenCloud internals, runs anywhere since WebDAV is reachable,
and costs one local HTTP request per minute. It reacts in about a minute rather than
seconds. Worth keeping in mind as the escape hatch, because it eliminates the wasted
VMs just as completely — that being the actual goal.

Either way the detector needs the OpenCloud App Token, which is now **Can view**
only and therefore grants nothing beyond reading four PDFs already published on the
open web.

## Verification on the host

Run before writing the listener. Everything below happens on the OpenCloud host;
nothing here changes state.

**1. Find the NATS endpoint and whether it needs credentials.** Inspect the
OpenCloud configuration for the events settings — `OC_EVENTS_ENDPOINT`, and the
`NATS_NATS_HOST` / `NATS_NATS_PORT` pair. Record host, port, and any TLS or
authentication requirement.

**2. Confirm whether it is JetStream-backed.** With the `nats` CLI
(github.com/nats-io/natscli):

```
nats --server nats://<host>:<port> server check jetstream
nats --server nats://<host>:<port> stream ls
```

A stream listing means JetStream, which decides the client library and the consumer
configuration. Record the stream name carrying file events.

**3. Capture the event names.** Subscribe broadly, then act on a file:

```
nats --server nats://<host>:<port> sub ">"
```

With that running, in the OpenCloud web UI:

- upload a small PDF into `Stellenanzeigen/Hagmatt/`
- rename it
- delete it
- empty the trash

Record, for each: the **subject**, the **event type name**, and enough of the
payload to see how the space and path are identified. The rename matters — it may
appear as a move rather than a create plus delete, and a rename to a bad filename
must still trigger a sync so the run reports the problem. Emptying the trash matters
because a delete may only become final at that point.

**4. Judge the interface.** Does subscribing from outside work without special
configuration? Are the subjects and type names stable-looking, or clearly internal?
This is the judgement call that decides between the NATS consumer and the WebDAV
fallback — it is worth making deliberately rather than by default.

Bring back the answers to 1–4 and the listener can be written against facts rather
than assumptions.

## Credential: GitHub App, scoped to Actions: write

Either a fine-grained PAT or a GitHub App can hold exactly `Actions: write`, so
**blast radius is identical**. The App wins on lifecycle:

| | Fine-grained PAT | GitHub App |
|---|---|---|
| Expiry | Expires; the trigger then dies silently | Private key does not expire; mints 1-hour tokens |
| Ownership | Belongs to one person's account | Owned by the organisation |
| Audit | Attributed to a person | Attributed to the app |
| Setup | Create and copy | Create, install, JWT sign → token exchange |

Expiry is the deciding factor. This project has already produced two confusing
credential failures — an empty secret and a placeholder value — and a PAT quietly
expiring in a year is the same class of fault: job ads stop updating with no
obvious cause.

Be clear about the limit: the App's private key on disk is still permanent access,
because it can always mint fresh tokens. The App shortens the *token's* life, not
the *key's*. It is better lifecycle management, not a different trust model.

Setup:

1. Create a GitHub App in the `Kinderkrippe-Olten` organisation.
2. Repository permissions: **Actions: read and write**. Metadata: read is added
   automatically. Grant nothing else — in particular not Contents and not Workflows.
3. Install it on `kinderkrippe-olten-website` only.
4. Generate a private key; place it on the detector host, readable only by the
   detector's user.
5. The detector signs a short JWT with the key, exchanges it for an installation
   token, and uses that for the dispatch call.

A fine-grained PAT with the same single permission is an acceptable shortcut, with a
calendar reminder before its expiry.

## Changes to sync-stellen.yaml

Two, both small:

**Demote the cron to weekly.** Do not remove it, but do not rely on it either — see
"Where the backstop lives" below.

```yaml
schedule:
  - cron: '17 5 * * 1'   # weekly third net; see "Where the backstop lives"
```

The off-round minute avoids the top-of-hour congestion GitHub documents for
scheduled workflows.

**Collapse bursts.** Uploading five PDFs fires five dispatches. Since every run is a
full mirror, only the last matters:

```yaml
concurrency:
  group: sync-stellen
  cancel-in-progress: true    # currently false
```

Cancelling mid-run is safe here: the sync is idempotent, and a cancelled run either
has not committed yet or has already finished committing.

## Where the backstop lives

The obvious backstop — a daily GitHub cron — cannot be trusted, because of the rule
that scheduled workflows in public repositories are disabled after 60 days without
repository activity.

Whether commits made by the workflow itself reset that clock is undocumented.
Keepalive actions in the wild work by committing with `GITHUB_TOKEN`, which suggests
they do, but it is not stated anywhere official.

That question turns out to be moot. The sync only commits **when an ad actually
changes**, so commits occur exactly when the repository is already active, and cease
during precisely the quiet stretch when a backstop matters. Sixty days without a job
ad is entirely plausible. The GitHub cron is therefore guaranteed to be absent in
the one scenario it exists for.

**So the real backstop is a heartbeat from the detector.** The detector already has
to run somewhere and already holds the dispatch credential; it dispatches on every
relevant event, and additionally once a day regardless. A timer on a host under your
own control is not subject to GitHub's inactivity rule.

Three nets, in order:

| Net | Covers | Fails when |
|---|---|---|
| Event dispatch | Normal publishing, seconds | Listener or NATS broken |
| Daily heartbeat dispatch from the same host | Missed or dropped events | Detector host down |
| Weekly GitHub cron | Detector host down entirely | Auto-disabled after 60 quiet days |

Each covers the one above it. The weekly cron is worth keeping — four or five runs a
month is nothing, and it is the only net that survives the detector host dying — but
it must not be the net anything depends on.

**This makes the detector's own health the thing to monitor.** With the heartbeat as
primary backstop, a dead detector means job ads stop publishing and only the weekly
cron catches it. A failed systemd timer is straightforward to alert on with existing
monitoring, and that alerting is part of the deliverable, not an afterthought.

## Failure modes

| Failure | Consequence | Caught by |
|---|---|---|
| Detector host down | Ads publish up to a week late | Weekly cron; monitoring on the timer |
| GitHub credential expired or revoked | Same | Dispatch call logs an error; weekly cron |
| OpenCloud token expired | Sync cannot fetch | Weekly cron run fails visibly |
| Detector fires spuriously | A run reports `no changes` | Harmless |
| Duplicate dispatches | Collapsed | `cancel-in-progress` |
| Repository inactive 60 days | Weekly cron auto-disabled | Heartbeat is unaffected — it does not run on GitHub |

The last one deserves attention. GitHub disables scheduled workflows in public
repositories after 60 days without repository activity. With the cron demoted to
daily and normal publishing driven by the detector, the repository could go quiet
for a long stretch, and then the backstop disappears silently. Re-enabling is one
click, and GitHub notifies the owner, but it is worth knowing that the safety net
has its own off switch.

## Build order

1. **Verify on the host** — the NATS checklist above. Nothing else can be designed
   honestly until the event names and the interface's status are known.
2. Create the App, install it on the one repository, place the private key.
3. Build and test the dispatch step on its own: signing, token exchange, and a
   `workflow_dispatch` with `dry_run` ticked. This is independent of NATS and can be
   done in parallel with step 1.
4. Build the listener against the verified event names. Add the daily heartbeat in
   the same unit — it is the primary backstop, not an extra.
5. Add monitoring on the detector's timer.
6. **Only then** demote the GitHub cron to weekly. Keeping `*/15` until the detector
   is proven means a detector fault shows up as wasted runs rather than as job ads
   silently not publishing.

## Out of scope

- Changing the sync itself. `apply-stellen-sync.py`,
  `validate-stellen-filenames.py` and the fetch step are untouched.
- Reacting to changes anywhere other than the job-ad folder.
- Notifying the author in OpenCloud or Mattermost when a filename is rejected. The
  failed Actions run remains the notification.
