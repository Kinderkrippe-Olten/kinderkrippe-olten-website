# Trigger the Stellen sync on change instead of on a schedule

Date: 2026-08-11. Revised 2026-08-14 with the verified deployment facts: this
OpenCloud instance runs in Kubernetes, which answers most of the original
verification checklist and turns the detector from a systemd unit into a Deployment.

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

### Verification: mostly done

Settled by the table above: the endpoint, the absence of TLS and credentials, and
JetStream with its stream name.

Still open, and not answerable by reading:

- **The event type names** for creation, deletion and rename — see "Capturing the
  event names" below.
- **Whether the contract is stable enough to depend on.** Half-answered: subscribing
  from outside the OpenCloud pod is supported and already in production use. What
  remains unknown is whether the *subjects and type names* look like a public
  interface or an internal one, and that cannot be judged until they have been seen.

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

Events cover the whole deployment, not just the job-ad space — confirmed, `main-queue`
is one stream for everything. The listener must filter to the relevant space and path
prefix and ignore the rest. Getting this wrong is cheap in one direction and not the
other: an over-broad filter causes harmless `no changes` runs, while an over-narrow one
silently misses publications. When in doubt, filter loosely.

### Fallback: WebDAV poll

Connectivity is no longer the risk it was when this was written — subscribing from
another pod demonstrably works. What could still send us here is the event contract
looking too internal to depend on. In that case the same trigger can be driven without
touching OpenCloud internals at all:

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

## Capturing the event names

The one verification step left. It changes no cluster state, but it does add and
remove a throwaway file in the live job-ad folder.

The `nats` CLI is not packaged for Ubuntu. Either run it inside the cluster and
install nothing:

```
kubectl -n cust-kko-opencloud-posix run natsbox --rm -it --image=natsio/nats-box -- sh
nats --server nats://opencloud-kko-posix-opencloud:9233 sub ">"
```

The namespace enforces `pod-security: baseline` with `warn: restricted`, so expect a
warning about `runAsNonRoot`; nats-box needs no privileges and starts regardless.

Or pin the binary locally — same style as the rclone install in `sync-stellen.yaml` —
and reach the service through a port-forward, which buys shell history and scrollback:

```
curl -fsSLO https://github.com/nats-io/natscli/releases/download/v0.4.0/nats-0.4.0-linux-amd64.zip
echo "8dbd437c826b953dbd7432cf890ef22ba3c33dccc3dce5e71b3e8d055427849c  nats-0.4.0-linux-amd64.zip" | sha256sum -c -
kubectl -n cust-kko-opencloud-posix port-forward svc/opencloud-kko-posix-opencloud 9233:9233
```

With a broad subscription running, in the OpenCloud web UI:

- upload a small PDF into `Stellenanzeigen/Hagmatt/`
- rename it
- delete it
- empty the trash

Record for each: the **subject**, the **event type name**, and enough of the payload
to see how the space and path are identified. The rename matters — it may appear as a
move rather than a create plus delete, and a rename to a bad filename must still
trigger a sync so the run reports the problem. Emptying the trash matters because a
delete may only become final at that point.

`main-queue` carries every event in the deployment: 14,425 messages at the time of
checking, with one arriving 240 ms earlier. Expect the interesting events to be buried
in unrelated traffic — subscribe broadly to learn the subjects, then narrow.

**Give the throwaway PDF a name the validator will reject**, or do this outside the
`*/15 6-18 * * 1-5` window. Otherwise the existing schedule may publish it to the live
site before you delete it. A rejected file is reported and not published, which makes
it the safer of the two.

With those answers the listener can be written against facts rather than assumptions.

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
relevant event, and additionally once a day regardless. A CronJob in your own cluster
is not subject to GitHub's inactivity rule.

Three nets, in order:

| Net | Covers | Fails when |
|---|---|---|
| Event dispatch (Deployment) | Normal publishing, seconds | Listener or NATS broken |
| Daily heartbeat (CronJob, same namespace) | Missed or dropped events | Cluster or namespace down |
| Weekly GitHub cron | The cluster being down entirely | Auto-disabled after 60 quiet days |

Each covers the one above it. The weekly cron is worth keeping — four or five runs a
month is nothing, and it is the only net that survives the cluster going down — but it
must not be the net anything depends on.

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
| Listener pod crash-looping or unscheduled | Ads wait for the daily heartbeat | Pod restart alert; heartbeat |
| Cluster or namespace down | Ads publish up to a week late | Weekly cron; CronJob failure alert |
| GitHub credential expired or revoked | Same | Dispatch call logs an error; weekly cron |
| OpenCloud token expired | Sync cannot fetch | Weekly cron run fails visibly |
| Detector fires spuriously | A run reports `no changes` | Harmless |
| Duplicate dispatches | Collapsed | `cancel-in-progress` |
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
2. **Capture the event names** — the section above. The listener cannot be finished
   honestly until they are known, and the judgement about the interface's stability
   depends on seeing them.
3. Create the App, install it on the one repository, store the private key as a Secret.
4. Build and test the dispatch step on its own: signing, token exchange, and a
   `workflow_dispatch` with `dry_run` ticked. Independent of NATS, so it can be done in
   parallel with step 2.
5. Build the listener against the verified event names, as a chart plus a service entry
   in `customers/kko/customer.yaml`. Add the daily heartbeat CronJob in the same chart —
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
