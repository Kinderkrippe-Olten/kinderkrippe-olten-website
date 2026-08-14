# Trigger the Stellen sync on change instead of on a schedule

Date: 2026-08-11. Revised 2026-08-14 twice: first with the verified deployment facts
(this OpenCloud instance runs in Kubernetes, which turns the detector from a systemd
unit into a Deployment), then with the event contract captured live from the running
instance. The verification checklist that occupied the original draft is now complete;
what replaced it is measured fact, and the listener can be written against it.

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

### Where it runs

This instance is a **Kubernetes deployment, not a host**: cluster `talos-volki-01`,
namespace `cust-kko-opencloud-posix`, chart `charts/opencloud-posix`, release
`kko-opencloud-posix` — all in the `oep-k8s` repository.
`customers/kko/services/opencloud-posix/values.yaml` sets no `nats:` block, so
`opencloud.nats.external.enabled` keeps its default `false`: NATS runs **embedded
inside the opencloud pod**, and the chart's `{{- else }}` branch applies.

Verified 2026-08-14, paths relative to `oep-k8s`:

| | Value | Source |
|---|---|---|
| Endpoint | `opencloud-kko-posix-opencloud.cust-kko-opencloud-posix.svc.cluster.local:9233` | `charts/opencloud-posix/templates/opencloud/service.yaml:16` + `fullnameOverride` |
| Bind address | `0.0.0.0:9233` | `charts/opencloud-posix/templates/opencloud/deployment.yaml:394` |
| Cluster name | `opencloud-cluster` | `charts/opencloud-posix/templates/collaboration/deployment.yaml:113` |
| TLS | none — the `OC_EVENTS_*TLS*` vars are set only in the external-NATS branch | `charts/opencloud-posix/templates/opencloud/deployment.yaml:382` |
| Credentials | none — nothing sets `OC_EVENTS_AUTH_*`, and an anonymous connection succeeds | confirmed by connecting |
| JetStream | yes; one stream, `main-queue` | `nats stream ls` |

Two consequences worth stating plainly.

**The detector is a Deployment, not a systemd unit.** It needs no host access, no SSH
and no ingress — the endpoint is an ordinary ClusterIP service. It belongs in
`oep-k8s` as a new service entry in `customers/kko/customer.yaml`, deployed by the
existing ApplicationSet into `cust-kko-opencloud-posix`, next to the instance it
watches. It must *not* go into `charts/opencloud-posix`: that chart is shared with
stv-olten and oep-demo, while this detector exists only for kko's website.

**Connecting from another pod is an established path, not an improvisation.** The
collaboration service already does exactly this
(`charts/opencloud-posix/templates/collaboration/deployment.yaml:111`), with a comment
recording the 7.3.0 crash-loop that made it necessary. The chart sets
`NATS_NATS_HOST=0.0.0.0` and publishes port 9233 on the service specifically so
off-pod clients work.

### Verification: done

The endpoint, the absence of TLS and credentials, and JetStream with its stream name
come from the table above. The event contract was captured live on 2026-08-14 and is
recorded under "The event contract" below.

One question is answered as far as it can be without asking upstream: whether an
external ConsumerGroup is a *supported* interface or merely an attachable one. The
stream carries twelve durable consumers, one per OpenCloud service — `activitylog`,
`clientlog`, `dcfs`, `evhistory`, `frontend`, `graph`, `jsoncs3sharemanager`,
`storage-users`, `userlog`, and pull consumers for postprocessing and search. An
external consumer would be a thirteenth of exactly the same kind. That is good
evidence, not proof.

### Subscribe as a durable consumer, not a core subscription

The listener must register a **durable JetStream pull consumer** — name it
`stellen-dispatcher` — and ack only after a successful dispatch. This is not an
implementation detail, and the distinction is easy to get wrong in the lossy direction:

- A **core** subscription sees only what is published while it is connected. Everything
  arriving during a restart is gone for good.
- A **durable** consumer resumes from its ack floor and replays what it missed, bounded
  by the stream's 7-day retention.

Restarts will not be rare. This cluster runs `argocd-image-updater`, so image bumps
restart pods unprompted; add chart changes, node drains and OOM kills. Under a core
subscription every one of those is a window in which an uploaded ad produces no
dispatch at all, and it surfaces up to 24 hours later via the heartbeat — in a system
this document describes as reacting in seconds. Nobody would connect the delay to a pod
restart.

Note that the capture command in "The event contract" is a *core* subscription
(`nats sub main-queue`), because it was used to observe live traffic. Do not take it as
a model for the listener.

**Debounce the replay on startup.** A durable consumer that was down for an hour
delivers every missed event at once, and each would otherwise fire its own dispatch —
which now queue rather than cancel, since `cancel-in-progress` stays false. Collapse
whatever arrives in the first few seconds after connecting into a single dispatch. The
debounce exists *because* of durability; the two belong together.

### A pre-existing exposure, noted in passing

That NATS port is unauthenticated, unencrypted, and — with no NetworkPolicy in the
chart or the namespace — reachable from any pod in the cluster, including other
tenants' namespaces. Anything able to run a pod there can read every file event in
kko's OpenCloud.

This is not caused by the present design and fixing it is out of scope. It is
recorded here because the detector would be the first thing to *depend* on that
reachability, so a later decision to lock the port down with a NetworkPolicy must
remember to admit the detector.

### Not the postprocessing hook

Do **not** implement this as a `POSTPROCESSING_STEPS` custom step, despite it being
the more obvious "official" extension point. It is an *upload* pipeline: deletions
never reach it, and deleting a PDF is half of the workflow. It also blocks upload
finalisation until the custom step replies, so an outage in the listener wedges
uploads for ordinary users. A passive consumer has neither problem.

### Filtering

Everything in the deployment arrives on the single subject `main-queue`, so filtering
cannot happen at subscribe time — every event must be decoded and then judged. Getting
this wrong is cheap in one direction and not the other: an over-broad filter causes
harmless `no changes` runs, an over-narrow one silently misses publications. So the
rule throughout is **fail open** — when the listener cannot tell, it dispatches.

Concretely, dispatch when all of:

1. `Metadata.eventtype` is in the mutating allowlist: `events.UploadReady`,
   `events.ItemMoved`, `events.ItemTrashed`, `events.TrashbinPurged`,
   `events.ContainerCreated`, and defensively `events.ContainerDeleted` and
   `events.ItemPurged`. Not `events.FileUploaded` — see below. Never
   `events.UserSignedIn`, `events.FileDownloaded`, `events.SendSSE`,
   `events.FileLocked`/`Unlocked`, which are the bulk of the traffic.
2. The space is the job-ad space, `faf2a73a-2916-4fe7-95a9-9f62023f812c`. **The field
   path differs per event type** — see the table below — and if the space cannot be
   determined at all, dispatch anyway.
3. The path test below passes, **or the event carries no path at all**, in which case
   dispatch anyway.

Where the space lives, per event type:

| Event | Field |
|---|---|
| `UploadReady` | `FileRef.resource_id.space_id` |
| `ItemMoved` | `Ref.resource_id.space_id` *and* `OldReference.resource_id.space_id` |
| `ItemTrashed` | `Ref.resource_id.space_id` (also `ID.space_id`) |
| `ContainerCreated`, `TrashbinPurged` | `Ref.resource_id.space_id` |

`UploadReady` is the odd one out, nesting under `FileRef` where everything else uses
`Ref` — and it is the event that signals a new job ad, so a single hardcoded accessor
written from a one-line description fails on precisely the case the feature exists for.

Both halves of rule 2 matter, in opposite directions. Without the table, a naive
accessor returns nothing for `UploadReady`; failing *closed* on that would mean uploads
never dispatch while renames and deletes work perfectly — a feature that looks alive and
is missing its main case. Failing *open* without the table is worse in the other
direction: 6 allowlisted events were observed in 32 minutes, most of them in unrelated
spaces, which extrapolates to roughly 270 dispatches a day against the 1,100 runs a
*month* this design exists to eliminate. The table is what keeps the fail-open branch
rare enough to afford.

The path test has two subtleties, both found by measurement rather than reasoning:

**Test both paths on `ItemMoved`.** A file moved *out* of the job-ad folder matches
only `OldReference.path`; moved *in*, only `Ref.path`. Checking one direction silently
misses half of all moves.

**Treat an ancestor as a match too.** A container operation reports only the
container's own path, so dragging `Stellenanzeigen` itself somewhere else yields
`/Stellenanzeigen` → `/Archiv/Stellenanzeigen`, and a plain
`startswith("Stellenanzeigen/")` fails on both. Dispatch if either path is under the
watched prefix **or** the watched prefix is under it. Today `Stellenanzeigen` sits at
the space root so only the space itself is above it, but the check costs one line and
closes the case permanently.

Normalise the leading `./` or `/` before comparing — which one appears depends on the
event type.

### Fallback: WebDAV poll

Both original reasons for keeping this escape hatch have now been examined.
Connectivity is settled — subscribing from another pod demonstrably works. The event
contract is the mixed verdict recorded above: usable, but visibly internal. The
decision was to proceed with NATS because fail-open makes a broken contract cost
latency rather than correctness.

So this stays as the documented fallback rather than the plan. What would trigger it
is an OpenCloud upgrade that breaks the events badly enough to be worth abandoning
them, at which point the same trigger can be driven without touching OpenCloud
internals at all:

```
every minute:
    listing = rclone lsl OC:Stellenanzeigen        # names, sizes, mtimes
    hash    = sha256(listing)
    if hash != contents of state file:
        dispatch; store hash
```

About twenty lines, no OpenCloud internals, and one HTTP request a minute. It reacts
in about a minute rather than seconds. As a CronJob it needs no NATS access at all —
WebDAV is reachable from anywhere, so it would not even have to run in the cluster.
Worth keeping in mind as the escape hatch, because it eliminates the wasted VMs just
as completely, that being the actual goal.

Note the asymmetry in credentials, which the earlier draft of this document got wrong
by claiming the detector needs the OpenCloud App Token "either way":

- **NATS consumer:** no OpenCloud credential whatsoever. The endpoint is
  unauthenticated, so the listener holds only the GitHub App key.
- **WebDAV poll:** needs the App Token, which is now **Can view** only and therefore
  grants nothing beyond reading four PDFs already published on the open web.

So the NATS path is the one that touches fewer secrets, which is a point in its favour
that was not visible before the endpoint was inspected.

## The event contract

Captured live on 2026-08-14 by subscribing to `main-queue` while performing each action
in the OpenCloud web UI, in a scratch folder at the space root — outside
`Stellenanzeigen/`, so the sync never saw the test files. Reproduce with:

```
kubectl -n cust-kko-opencloud-posix exec natsbox -- \
  nats --server nats://opencloud-kko-posix-opencloud:9233 sub main-queue
```

Subscribe to `main-queue`, not `>`: the latter adds roughly 100 lines a second of
JetStream API and advisory chatter that buries everything. The `nats` CLI is not
packaged for Ubuntu — run it in the cluster as above (nats-box needs no privileges and
starts fine under the namespace's `pod-security: baseline`), or pin the binary
(natscli v0.4.0, sha256
`8dbd437c826b953dbd7432cf890ef22ba3c33dccc3dce5e71b3e8d055427849c`) and reach the
service with `kubectl port-forward`.

### Envelope

Every event has the same shape, with the interesting part base64-encoded:

```json
{"Timestamp":"2026-08-14T09:37:56Z",
 "Metadata":{"eventid":"…","eventtype":"events.UploadReady","initiatorid":"","traceparent":"…"},
 "ID":"…","Topic":"main-queue","Payload":"<base64 JSON>"}
```

The type is `Metadata.eventtype`; space and path live in the decoded `Payload`.

### What each action emits

| Action | Events, in order | Path |
|---|---|---|
| Upload a file | `BytesReceived`, `FileUploaded`, `PostprocessingFinished`, **`UploadReady`** | `UploadReady.FileRef.path` = `./nats-test/Zitronen-Muffins.pdf` |
| Rename a file | **`ItemMoved`** | `Ref.path` *and* `OldReference.path` |
| Delete a file | **`ItemTrashed`** | `Ref.path` |
| Empty the trash | **`TrashbinPurged`** | none — space reference only |
| Create a folder | **`ContainerCreated`** | `Ref.path` = `./nats-test` |
| Rename a folder | **one** `ItemMoved` | `/nats-test` → `/nats-test-renamed` |
| Delete a folder containing a file | **one** `ItemTrashed` | `./nats-test-renamed` |

### The five findings that shape the listener

**Rename is a single `ItemMoved` carrying both paths**, not a delete plus a create. It
fires on the move itself regardless of the new name, so a rename *to* an invalid
filename still triggers a sync and the run reports the problem — an explicit open
question in the original draft, now answered yes.

**`ItemTrashed` is the delete signal, not `TrashbinPurged`.** Trashing removes the file
from the folder listing, which is exactly when the mirror changes. The earlier worry
that a delete "may only become final" at purge time was wrong. Fortunate, because
`TrashbinPurged` carries no path or item identity at all — only the space — so it could
never have been filtered precisely. It stays in the allowlist and dispatches
unconditionally under the fail-open rule.

**Use `UploadReady`, not `FileUploaded`.** In two of three uploads observed in this
space, `FileUploaded.Ref` held a resource_id and *no path field whatsoever*, while an
upload in a different space did carry one. `UploadReady` consistently carries
`FileRef.path` plus `ParentID`, and fires after postprocessing — when the file is
actually readable, which is what the sync needs.

**Container operations emit one event, not one per contained file.** Deleting a site
folder full of job ads produces a single `ItemTrashed`. Bursts are therefore much rarer
than assumed, and `cancel-in-progress` has little work to do.

**Path prefixes are inconsistent**: `./` from `UploadReady`, `ItemTrashed` and
`ContainerCreated`, but `/` from `ItemMoved`. Normalise before comparing.

### Volume

127 events in 32 minutes across the entire deployment, 89 of them `UserSignedIn`. A
four-action test produced 7. Noise is not a concern, and the allowlist removes most of
what remains.

### The stability judgement

Mixed, and worth stating plainly rather than rounding up.

**For:** the consumer mechanism is a real extension point — twelve services use it. The
type names (`FileUploaded`, `ItemTrashed`, `ItemMoved`) are long-standing in oCIS and
OpenCloud.

**Against:** the payloads are Go structs serialised straight to JSON — `Executant`,
`OldReference`, `ImpersonatingUser`, `SpaceOwner`. The inconsistencies above are the
signature of an internal interface rather than a designed contract: a path field
present or absent depending on code path, two path prefixes, `Timestamp` sometimes
null. No schema, no versioning.

**Verdict: proceed, because fail-open makes the failure mode cheap.** A renamed or
dropped event costs latency, not correctness, as long as the daily heartbeat and weekly
cron remain. See the failure mode about silent event renames for what to monitor.

One gap, stated honestly: `ContainerDeleted` and `ItemPurged` are in the allowlist on
reasoning, not measurement. Neither was observed, because no test produced them.

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

Be clear about the limit: the App's private key is still permanent access, because it
can always mint fresh tokens. The App shortens the *token's* life, not the *key's*. It
is better lifecycle management, not a different trust model.

Setup:

1. Create a GitHub App in the `Kinderkrippe-Olten` organisation.
2. Repository permissions: **Actions: read and write**. Metadata: read is added
   automatically. Grant nothing else — in particular not Contents and not Workflows.
3. Install it on `kinderkrippe-olten-website` only.
4. Generate a private key and store it as a Kubernetes Secret in
   `cust-kko-opencloud-posix`, mounted into the detector pod. This is the only real
   credential in the design; handle it the way the OpenCloud token is handled — never
   in a shell command line, never in a transcript.
5. The detector signs a short JWT with the key, exchanges it for an installation
   token, and uses that for the dispatch call.

A fine-grained PAT with the same single permission is an acceptable shortcut, with a
calendar reminder before its expiry.

## Changes to sync-stellen.yaml

One, and it is small:

**Demote the cron to weekly.** Do not remove it, but do not rely on it either — see
"Where the backstop lives" below.

```yaml
schedule:
  - cron: '17 5 * * 1'   # weekly third net; see "Where the backstop lives"
```

The off-round minute avoids the top-of-hour congestion GitHub documents for
scheduled workflows.

### Leave `cancel-in-progress` at false

An earlier draft of this document recommended flipping it to `true` to collapse
bursts, on the reasoning that "a cancelled run either has not committed yet or has
already finished committing". **That reasoning is wrong, and the change must not be
made.** There is a third state.

`sync-stellen.yaml` pushes and then dispatches the deploy as two separate commands:

```
git push
gh workflow run deploy-hugo.yaml --ref "${GITHUB_REF_NAME}"
```

A cancellation between them leaves the PDF committed on `main` with no deploy
triggered — and the push was made with `GITHUB_TOKEN`, which does not trigger
workflows, which is the entire reason the explicit dispatch exists.

It does not self-heal. The next run hits
`if [ -z "$(git status --porcelain content/docs/stellen)" ]`, prints `no changes to
commit` and exits **before** reaching the dispatch. Neither the heartbeat nor the
weekly cron recovers it. The ad sits in the repository, absent from the live site,
until some unrelated ad change happens to produce a fresh commit. Silent, and
effectively permanent.

The justification for the change has evaporated anyway: "The event contract" records
that container operations emit a single event, so the bursts it was meant to collapse
barely occur. Queued runs are cheap, and a redundant second run exits at `no changes`.

If a future change does introduce real bursts, fix them by debouncing **in the
listener** — where no commit is at stake — not by cancelling a run that may be
halfway between pushing and publishing.

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
relevant event, and additionally once a day regardless. A CronJob in your own cluster
is not subject to GitHub's inactivity rule.

Three nets, in order:

| Net | Covers | Fails when |
|---|---|---|
| Event dispatch (Deployment) | Normal publishing, seconds | Listener or NATS broken |
| Daily heartbeat (CronJob, same namespace) | Missed or dropped events | Namespace broken, or cluster down |
| Weekly GitHub cron | Detector broken while the cluster is up | Auto-disabled after 60 quiet days |

**A cluster outage is covered by nothing, and that is fine.** An earlier draft claimed
the weekly cron was "the only net that survives the cluster going down". It is not: the
sync fetches from `cloud.kinderkrippe-olten.ch`, which
`clusters/talos-volki-01/cluster_config/gateway-api/gateway.d/94-cloud-kinderkrippe-olten-ch.yaml`
binds to the same cluster the detector runs in. An outage takes out the detector and
the data source together, and the cron run fails at `rclone copy`.

The gap is benign, because during an outage OpenCloud is down and **nobody can upload a
job ad in the first place**. The only exposure is an ad uploaded shortly before the
outage that had not yet synced, and it publishes on recovery.

What the weekly cron does cover is the likelier case: the cluster is fine but the
detector specifically is broken — namespace misconfigured, CronJob suspended, listener
crash-looping past its restart budget, App key revoked. It also has a property the
heartbeat lacks: **its failure is visible**, as a red run in the Actions tab, with no
monitoring to build. That, rather than surviving a cluster outage, is the argument for
keeping it — and it must still not be the net anything depends on.

**This makes the detector's own health the thing to monitor.** With the heartbeat as
primary backstop, a dead detector means job ads stop publishing and only the weekly
cron catches it. In-cluster this is cheaper than it would be on a host: the
kube-prometheus-stack already running on `talos-volki-01` exposes
`kube_job_status_failed` and `kube_cronjob_status_last_successful_time`, so alerting on
a failed heartbeat or a crash-looping listener needs no new tooling. That alerting is
part of the deliverable, not an afterthought.

## Failure modes

| Failure | Consequence | Caught by |
|---|---|---|
| Listener pod crash-looping or unscheduled | Ads wait for the daily heartbeat; events during the gap replay on restart | Pod restart alert; heartbeat; durable consumer |
| Namespace broken, cluster up | Ads publish up to a week late | Weekly cron run; CronJob failure alert |
| Cluster down | Nothing to publish — uploads are impossible too | Not covered by design; see "Where the backstop lives" |
| GitHub credential expired or revoked | Ads publish up to a week late | Dispatch call logs an error; weekly cron |
| OpenCloud token expired | Sync cannot fetch | Weekly cron run fails visibly |
| Detector fires spuriously | A run reports `no changes` | Harmless |
| Duplicate dispatches | Queued, second exits at `no changes` | Listener debounce; `cancel-in-progress` stays false deliberately |
| Repository inactive 60 days | Weekly cron auto-disabled | Heartbeat is unaffected — it does not run on GitHub |
| OpenCloud upgrade renames or drops an event | Silent regression to heartbeat latency | Nothing automatic; see below |

Two of those deserve more than a table row.

**The 60-day rule.** GitHub disables scheduled workflows in public repositories after
60 days without repository activity. With the cron demoted to weekly and normal
publishing driven by the detector, the repository could go quiet for a long stretch,
and then the third net disappears silently. Re-enabling is one click and GitHub
notifies the owner, but it is worth knowing that the safety net has its own off switch.

**Event renames on upgrade.** This is the cost of depending on an interface whose
stability is exactly what "Verification: mostly done" cannot yet confirm. If an
OpenCloud upgrade renames or stops emitting the events the listener matches, nothing
breaks loudly: the daily heartbeat keeps publishing, so ads still appear, just up to a
day late instead of within seconds. That is a mild enough failure to go unnoticed for
months. Mitigation is to alert on the *absence* of event-driven dispatches over a
window rather than only on errors — worth doing if the captured event names turn out to
look internal, and reason enough to prefer the WebDAV fallback if they do.

## Build order

1. ~~Find the NATS endpoint; confirm JetStream.~~ **Done 2026-08-14** — see the table
   under "Where it runs".
2. ~~Capture the event names.~~ **Done 2026-08-14** — see "The event contract".
3. Create the App, install it on the one repository, store the private key as a Secret.
   This is now the only thing blocking everything below it.
4. Build and test the dispatch step on its own: signing, token exchange, and a
   `workflow_dispatch` with `dry_run` ticked.
5. Build the listener against the contract above, as a chart plus a service entry in
   `customers/kko/customer.yaml`. Add the daily heartbeat CronJob in the same chart —
   it is the primary backstop, not an extra.
6. Add monitoring on the listener Deployment and the heartbeat CronJob.
7. **Only then** demote the GitHub cron to weekly. Keeping `*/15` until the detector is
   proven means a detector fault shows up as wasted runs rather than as job ads silently
   not publishing.

## Out of scope

- Changing the sync itself. `apply-stellen-sync.py`,
  `validate-stellen-filenames.py` and the fetch step are untouched.
- Reacting to changes anywhere other than the job-ad folder.
- Notifying the author in OpenCloud or Mattermost when a filename is rejected. The
  failed Actions run remains the notification.
- Any change to `charts/opencloud-posix`. It is shared with other tenants; the detector
  is a separate chart that happens to run in the same namespace.
- Closing the unauthenticated-NATS exposure described above. Pre-existing, cluster-wide,
  and a decision for `oep-k8s` rather than this design.

## A note on repository boundaries

This spec lives in the website repository because that is where the sync it triggers
lives. The detector itself will live in `oep-k8s`, since that is where the cluster is
described. Whoever implements step 5 should leave a pointer back to this file from the
new chart, or the reasoning behind an oddly specific little Deployment in a customer
namespace will be unfindable a year from now.
