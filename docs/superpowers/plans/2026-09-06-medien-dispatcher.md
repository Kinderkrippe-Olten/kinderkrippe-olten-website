# Medien Dispatcher Implementation Plan (`oep-k8s`)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dispatch `sync-medienmitteilungen.yaml` within seconds of a change under `Medienmitteilungen/` in kko's OpenCloud space, instead of waiting for the weekly cron.

**Architecture:** A **second Helm release of the existing `stellen-dispatcher` chart**, not a change to it. `watch.path`, `github.workflow`, `nats.durable` and `heartbeat.schedule` are already values, and the ApplicationSet resolves `customers/<customer>/services/<name>/values.yaml` by convention. The only edit to the shared chart is one log string.

**Tech Stack:** Helm, ArgoCD ApplicationSet, NATS JetStream, Prometheus Operator.

**Repository:** `~/checkouts/oep/oep-k8s` (`git@opgit:OP/oep-k8s.git`) — **not** the website repo.

**Spec:** `docs/superpowers/specs/2026-09-06-opencloud-medienmitteilungen-sync-design.md` (in the website repo, section "Dispatcher (`oep-k8s`)")

**Prerequisite:** `sync-medienmitteilungen.yaml` must be merged and present on `main` in the website repo first. GitHub answers `workflow_dispatch` for a missing workflow with a `404`, which `dispatch.sh` reports but cannot distinguish from a wrong repo.

## Global Constraints

- Do **not** rename the existing `stellen-dispatcher` durable consumer. A rename resets its ack floor and replays up to seven days of retained events.
- `nats.durable` **must** differ between the two releases. Two releases sharing one durable consumer do not each see the stream — JetStream *splits* it, delivering each message to exactly one pod, so press-release events would land at random in the job-ad dispatcher and be dropped.
- Both releases mount the same `stellen-dispatcher-github` sealed Secret. It is sealed `--scope strict` to name and namespace, both unchanged, and the PAT already carries `Actions: write` on the repository holding both workflows. **Nothing to reseal.**
- Namespace `cust-kko-opencloud-posix`, cluster `talos-volki-01`, space id `faf2a73a-2916-4fe7-95a9-9f62023f812c`.
- This repository has no CI for charts. Verification is `helm template` locally plus the ArgoCD diff.

## File Structure

| File | Responsibility |
|---|---|
| `bases/services/stellen-dispatcher/files/listen.sh` | **Modified**: one log string made watch-agnostic |
| `customers/kko/services/medien-dispatcher/values.yaml` | The new release's instance facts |
| `customers/kko/customer.yaml` | **Modified**: the service entry |
| `clusters/talos-volki-01/cluster_config/monitoring/medien-dispatcher-alerts.yaml` | Alerts for the new deployment and CronJob |

---

### Task 1: Make the shared chart's dispatch reason watch-agnostic

**Files:**
- Modify: `bases/services/stellen-dispatcher/files/listen.sh` (the `dispatch.sh` call)

**Interfaces:**
- Consumes: nothing.
- Produces: nothing. Cosmetic, but it lands first so the new release's logs read correctly from its first dispatch.

- [ ] **Step 1: Confirm the current string and that nothing asserts on it**

```bash
cd ~/checkouts/oep/oep-k8s
grep -rn 'job-ad change under' bases/services/stellen-dispatcher/
grep -rn 'job-ad' bases/services/stellen-dispatcher/test-filter.sh || echo "test-filter.sh does not depend on it"
```
Expected: one hit, in `files/listen.sh`; `test-filter.sh` clean.

- [ ] **Step 2: Make the edit**

In `bases/services/stellen-dispatcher/files/listen.sh`, replace:

```sh
  if sh "$SCRIPT_DIR/dispatch.sh" "job-ad change under $WATCH_PATH"; then
```

with:

```sh
  # Watch-agnostic: this chart now backs two releases, one watching
  # Stellenanzeigen/ and one Medienmitteilungen/. WATCH_PATH already says which.
  if sh "$SCRIPT_DIR/dispatch.sh" "change under $WATCH_PATH"; then
```

- [ ] **Step 3: Verify the chart still renders for the existing release**

```bash
helm template kko-stellen-dispatcher bases/services/stellen-dispatcher \
  -f bases/services/stellen-dispatcher/values.yaml \
  -f customers/kko/services/stellen-dispatcher/values.yaml \
  | grep -c 'change under'
```
Expected: at least `1`, and no template error.

- [ ] **Step 4: Commit**

```bash
git add bases/services/stellen-dispatcher/files/listen.sh
git commit -m "stellen-dispatcher: the dispatch reason no longer says 'job-ad'"
```

---

### Task 2: The medien-dispatcher release

**Files:**
- Create: `customers/kko/services/medien-dispatcher/values.yaml`
- Modify: `customers/kko/customer.yaml`

**Interfaces:**
- Consumes: the chart at `bases/services/stellen-dispatcher`.
- Produces: Helm release `kko-medien-dispatcher` in `cust-kko-opencloud-posix` — deployment `kko-medien-dispatcher`, CronJob `kko-medien-dispatcher-heartbeat`. Task 3's alert expressions use exactly those names.

- [ ] **Step 1: Write the values file**

```bash
mkdir -p customers/kko/services/medien-dispatcher
cat > customers/kko/services/medien-dispatcher/values.yaml <<'YAML'
# kko medien-dispatcher — watches this instance's OpenCloud event stream and asks the
# website repo to re-sync the press releases when something changes under
# Medienmitteilungen/.
#
# A SECOND RELEASE of the stellen-dispatcher chart, not a change to it: watch.path,
# github.workflow, nats.durable and heartbeat.schedule are all values, so the two
# instances differ only in this file. Design:
# docs/superpowers/specs/2026-09-06-opencloud-medienmitteilungen-sync-design.md in the
# website repo.

nats:
  # The embedded NATS inside the opencloud pod -- same endpoint as
  # stellen-dispatcher, which is the point: one stream, two independent consumers.
  url: "nats://opencloud-kko-posix-opencloud.cust-kko-opencloud-posix.svc.cluster.local:9233"

  # MUST differ from stellen-dispatcher's. A durable consumer is a queue group: two
  # releases sharing one name do not each receive the stream, JetStream SPLITS it
  # between them and delivers each message to exactly one pod. Press-release events
  # would then land at random in the job-ad dispatcher and be dropped -- intermittently,
  # in proportion to how many pods are up, which is the hardest possible failure to
  # reproduce. Separate durables give each release its own view of main-queue.
  durable: medien-dispatcher

watch:
  # Same space as the job ads; the id after the '$' in the OPENCLOUD_WEBDAV_URL secret.
  spaceId: "faf2a73a-2916-4fe7-95a9-9f62023f812c"
  path: "Medienmitteilungen"

github:
  repo: "Kinderkrippe-Olten/kinderkrippe-olten-website"
  workflow: "sync-medienmitteilungen.yaml"
  ref: "main"
  # The same sealed Secret as stellen-dispatcher. It is sealed --scope strict to name
  # and namespace, both unchanged here, and the PAT already carries Actions: write on
  # the repository that holds both workflows. Nothing to reseal.
  existingSecret: "stellen-dispatcher-github"
  secretKey: "GITHUB_TOKEN"

heartbeat:
  # Staggered away from stellen-dispatcher's "23 4 * * *". Inheriting it would fire
  # both dispatchers in the same second every night; the two sync workflows share one
  # concurrency group so that is safe rather than destructive, but two syncs queueing
  # behind each other daily makes the Actions log harder to read than it needs to be.
  schedule: "53 4 * * *"
YAML
```

- [ ] **Step 2: Add the service entry**

In `customers/kko/customer.yaml`, immediately after the `stellen-dispatcher` entry (the block ending `releaseName: kko-stellen-dispatcher`), insert:

```yaml
  # Second release of the same chart, watching Medienmitteilungen/ and dispatching
  # sync-medienmitteilungen.yaml. Separate durable consumer -- see the values file.
  # Design: docs/superpowers/specs/2026-09-06-opencloud-medienmitteilungen-sync-design.md
  # in the website repo.
  - name: medien-dispatcher
    chart: stellen-dispatcher
    chartPath: bases/services/stellen-dispatcher
    namespace: cust-kko-opencloud-posix
    cluster: talos-volki-01
    enabled: true
    releaseName: kko-medien-dispatcher
```

Also update the file's header comment, which currently reads `OpenCloud (posixfs + external SSO), Outline and the stellen-dispatcher.` — make it `… Outline and the two OpenCloud dispatchers.`

- [ ] **Step 3: Render the new release and check the four values that matter**

```bash
cd ~/checkouts/oep/oep-k8s
helm template kko-medien-dispatcher bases/services/stellen-dispatcher \
  -f bases/services/stellen-dispatcher/values.yaml \
  -f customers/kko/services/medien-dispatcher/values.yaml > /scratch/zaucker/claude-tmp/medien.yaml

grep -E 'NATS_DURABLE|WATCH_PATH|GITHUB_WORKFLOW' -A1 /scratch/zaucker/claude-tmp/medien.yaml
grep -E 'schedule:|name: kko-medien-dispatcher' /scratch/zaucker/claude-tmp/medien.yaml
```

Expected: `NATS_DURABLE: "medien-dispatcher"`, `WATCH_PATH: "Medienmitteilungen"`, `GITHUB_WORKFLOW: "sync-medienmitteilungen.yaml"`, `schedule: "53 4 * * *"`, deployment named `kko-medien-dispatcher`.

- [ ] **Step 4: Prove the two releases do not collide**

```bash
helm template kko-stellen-dispatcher bases/services/stellen-dispatcher \
  -f bases/services/stellen-dispatcher/values.yaml \
  -f customers/kko/services/stellen-dispatcher/values.yaml > /scratch/zaucker/claude-tmp/stellen.yaml

# Every named resource must differ between the two renders.
diff <(grep -E '^  name: ' /scratch/zaucker/claude-tmp/stellen.yaml | sort -u) \
     <(grep -E '^  name: ' /scratch/zaucker/claude-tmp/medien.yaml  | sort -u)

# The durables must differ. This is the one that silently breaks both if it is wrong.
grep -h -A1 NATS_DURABLE /scratch/zaucker/claude-tmp/stellen.yaml /scratch/zaucker/claude-tmp/medien.yaml
```
Expected: every resource name differs; the two durables are `stellen-dispatcher` and `medien-dispatcher`. **If any resource name is shared, stop** — the two releases would fight over it in the namespace.

- [ ] **Step 5: Commit**

```bash
git add customers/kko/services/medien-dispatcher/values.yaml customers/kko/customer.yaml
git commit -m "kko: a second dispatcher for the Medienmitteilungen sync"
```

---

### Task 3: Alerts for the new release

**Files:**
- Create: `clusters/talos-volki-01/cluster_config/monitoring/medien-dispatcher-alerts.yaml`

**Interfaces:**
- Consumes: the deployment and CronJob names produced by Task 2.
- Produces: PrometheusRule `medien-dispatcher-alerts` in `platform-monitoring`.

The failure mode is quiet: if the listener dies, the daily heartbeat keeps publishing and the only symptom is that press releases appear the next day instead of within seconds. That is exactly why it has to be alerted rather than noticed.

- [ ] **Step 1: Write the rules**

```bash
cat > clusters/talos-volki-01/cluster_config/monitoring/medien-dispatcher-alerts.yaml <<'YAML'
---
# Alerts for kko's medien-dispatcher (cust-kko-opencloud-posix).
#
# The sibling of stellen-dispatcher-alerts.yaml -- same chart, same shape, same quiet
# failure mode: if the listener dies the daily heartbeat keeps dispatching, so press
# releases still publish, just up to a day late. Nobody connects "the website is slow
# to update" to a pod, and it can sit like that for months.
#
# Kept as a separate file rather than folded into the stellen rules so that the two
# releases can be silenced, edited and reasoned about independently.
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: medien-dispatcher-alerts
  namespace: platform-monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:

    - name: medien-dispatcher
      rules:

        - alert: MedienDispatcherDown
          expr: kube_deployment_status_replicas_available{namespace="cust-kko-opencloud-posix",deployment="kko-medien-dispatcher"} < 1
          for: 15m
          labels:
            severity: warning
          annotations:
            summary: "medien-dispatcher has no available replica (kko press-release trigger)"
            description: |
              The listener that turns OpenCloud press-release changes into a GitHub
              sync is not running. Press releases still publish via the daily
              heartbeat CronJob, so this is not urgent -- but latency has silently
              gone from seconds to up to 24 hours, and nothing else will report it.

              15m rather than 5m: a node drain or an image-updater bump legitimately
              takes the pod down for a few minutes.

                kubectl -n cust-kko-opencloud-posix get pods -l app.kubernetes.io/instance=kko-medien-dispatcher
                kubectl -n cust-kko-opencloud-posix logs deploy/kko-medien-dispatcher --tail=100

              Causes, in the order they have actually happened on the sibling release:
                - NATS unreachable because the opencloud pod is restarting
                - the GitHub PAT expired (look for "dispatch: FAILED http=401")
                - the durable consumer was deleted from the stream

              NOTE: this release shares the PAT and the NATS endpoint with
              stellen-dispatcher. If BOTH dispatchers are down, the cause is almost
              certainly one of those two shared things, not the chart.

        - alert: MedienDispatcherHeartbeatStale
          # 90000s = 25h: daily schedule plus an hour of slack.
          expr: time() - kube_cronjob_status_last_schedule_time{namespace="cust-kko-opencloud-posix",cronjob="kko-medien-dispatcher-heartbeat"} > 90000
          for: 10m
          labels:
            severity: warning
          annotations:
            summary: "medien-dispatcher heartbeat has not fired in >25h"
            description: |
              The daily fallback dispatch has not run. On its own this changes nothing
              while the listener is healthy -- but it is the net under the listener, so
              firing together with MedienDispatcherDown means press releases have
              stopped publishing entirely until someone acts.

                kubectl -n cust-kko-opencloud-posix get cronjob kko-medien-dispatcher-heartbeat

              A suspended CronJob still reports its last schedule time, so check
              `.spec.suspend` before blaming the scheduler.

        - alert: MedienDispatcherHeartbeatFailed
          expr: kube_job_failed{namespace="cust-kko-opencloud-posix",job_name=~"kko-medien-dispatcher-heartbeat-.*",condition="true"} > 0
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "medien-dispatcher heartbeat Job {{ $labels.job_name }} failed"
            description: |
              backoffLimit is 0, so one failure is one alert. Read the log before
              assuming a breakage -- one of the two causes is deliberate:

                kubectl -n cust-kko-opencloud-posix logs job/{{ $labels.job_name }}

              1. "expiry check: the GitHub PAT expires in Nd" -- NOTHING IS BROKEN.
                 heartbeat.sh fails the Job on purpose inside
                 heartbeat.tokenExpiryWarnDays (30) so a PAT expiry arrives a month
                 early. The SAME secret backs stellen-dispatcher, so its heartbeat
                 will be failing for the same reason; reseal once and both clear.

              2. "dispatch: FAILED http=..." -- the real failure. 401 expired or
                 revoked token, 403 missing "Actions: write", 404 wrong repo or
                 sync-medienmitteilungen.yaml missing on the target ref, 422
                 workflow_dispatch not declared. A 404 here with stellen-dispatcher
                 healthy means the workflow file is not on main yet.
YAML
```

- [ ] **Step 2: Validate the manifest**

```bash
cd ~/checkouts/oep/oep-k8s
python3 -c "
import yaml
d = list(yaml.safe_load_all(open('clusters/talos-volki-01/cluster_config/monitoring/medien-dispatcher-alerts.yaml')))
r = [x for x in d if x][0]
names = [a['alert'] for g in r['spec']['groups'] for a in g['rules']]
print(r['metadata']['name'], names)
assert len(names) == 3
"
```
Expected: `medien-dispatcher-alerts ['MedienDispatcherDown', 'MedienDispatcherHeartbeatStale', 'MedienDispatcherHeartbeatFailed']`

- [ ] **Step 3: Commit**

```bash
git add clusters/talos-volki-01/cluster_config/monitoring/medien-dispatcher-alerts.yaml
git commit -m "monitoring: alerts for kko's medien-dispatcher"
```

---

## Done when

- ArgoCD shows `kko-medien-dispatcher` Synced/Healthy in `cust-kko-opencloud-posix`.
- `kubectl -n cust-kko-opencloud-posix logs deploy/kko-medien-dispatcher | head` ends with
  `listening: stream=main-queue durable=medien-dispatcher space=faf2a73a-… path=Medienmitteilungen …`
- Both durables exist and are distinct:
  `kubectl -n cust-kko-opencloud-posix exec deploy/kko-medien-dispatcher -- nats --server "$NATS_URL" consumer ls main-queue | grep dispatcher`
- Touching a file under `Medienmitteilungen/` in OpenCloud produces `dispatch: ok (change under Medienmitteilungen)` in the log within ~15s, and a `sync-medienmitteilungen.yaml` run in the website repo.
- Touching a file under `Stellenanzeigen/` still dispatches **only** `sync-stellen.yaml` — the check that proves the two durables are not splitting one stream.
