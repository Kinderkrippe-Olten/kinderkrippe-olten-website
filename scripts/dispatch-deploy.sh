#!/bin/sh
# Dispatch deploy-hugo.yaml for ONE named commit, and verify that is the commit the
# deploy actually picked up.
#
# Usage:  dispatch-deploy.sh <commit sha> [ref]
#
# Why this exists. GitHub suppresses workflow triggers for pushes made with
# GITHUB_TOKEN, so the syncers push and then dispatch the deploy explicitly. A
# workflow_dispatch resolves its ref SERVER-SIDE at dispatch time, and for a second or
# two after a push that resolution can still return the previous commit. On
# 2026-09-06 sync-geschichten.yaml pushed a944c998, dispatched one second later, and
# GitHub built 7603a93a: the deploy went green, the story was committed but never
# published, and nothing said so. The heal path in the sync workflows only notices on a
# LATER run that has nothing to commit -- up to a week.
#
# Two guards, because the first one alone is a race and the second one alone is slow:
#
#   1. Wait until the API's own view of the ref is the commit we pushed. This is the
#      actual cause, and waiting for it costs a few seconds.
#   2. Read back the run the dispatch created and compare its headSha. If it is not
#      ours, dispatch again. This is what makes the guarantee, rather than a hope
#      that the wait was long enough.
#
# Exit status:
#   0  a deploy for this commit is running -- or could not be verified either way
#   1  the deploy ran for a DIFFERENT commit and re-dispatching did not fix it
#
# The asymmetry is deliberate: "I could not see a run" is not the same claim as "I saw
# the wrong one". The first is left to the sync workflows' heal path, which exists for
# exactly that; the second is a fact worth a red run, because nothing else will catch
# it before the next sync.
set -eu

head="${1:?usage: dispatch-deploy.sh <commit sha> [ref]}"
ref="${2:-main}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"

workflow="${DEPLOY_WORKFLOW:-deploy-hugo.yaml}"
interval="${DISPATCH_POLL_INTERVAL:-3}"
ref_tries="${DISPATCH_REF_TRIES:-20}"      # x interval: how long the ref may lag
run_tries="${DISPATCH_RUN_TRIES:-20}"      # x interval: how long the run may take to appear
attempts="${DISPATCH_ATTEMPTS:-2}"         # dispatches before giving up

short="$(printf '%.8s' "$head")"

nap() {
  [ "$interval" = "0" ] || sleep "$interval"
}

# The ids of the deploy runs that exist right now, so the run OUR dispatch creates can
# be told apart from them. Ids rather than timestamps: the runner's clock and GitHub's
# need not agree, and a comparison that is wrong by a second is wrong in exactly the
# window this script exists for.
existing_runs() {
  gh run list --workflow="$workflow" --limit 20 --json databaseId \
    --jq '.[].databaseId' 2>/dev/null || true
}

# "<id> <sha>" per run, newest first.
runs_with_sha() {
  gh run list --workflow="$workflow" --limit 20 --json databaseId,headSha \
    --jq '.[] | "\(.databaseId) \(.headSha)"' 2>/dev/null || true
}

# --- Guard 1: let the API's view of the ref catch up to what we pushed -------------
i=1
while [ "$i" -le "$ref_tries" ]; do
  seen="$(gh api "repos/${GITHUB_REPOSITORY}/commits/${ref}" --jq '.sha' 2>/dev/null || true)"
  if [ "$seen" = "$head" ]; then
    break
  fi
  if [ "$i" -eq "$ref_tries" ]; then
    echo "::warning::GitHub still reports ${ref} at ${seen:-unknown}, not ${short}; dispatching anyway and checking what it builds"
    break
  fi
  nap
  i=$((i + 1))
done

# --- Guard 2: dispatch, then check which commit the run is actually building -------
attempt=1
while [ "$attempt" -le "$attempts" ]; do
  before="$(existing_runs)"
  gh workflow run "$workflow" --ref "$ref"
  echo "${workflow} dispatched on ${ref} for ${short} (attempt ${attempt}/${attempts})"

  found_id=""
  found_sha=""
  i=1
  while [ "$i" -le "$run_tries" ]; do
    nap
    # The newest run whose id was not there before the dispatch.
    while read -r id sha; do
      [ -n "$id" ] || continue
      if ! printf '%s\n' "$before" | grep -qx "$id"; then
        found_id="$id"
        found_sha="$sha"
        break
      fi
    done <<EOF
$(runs_with_sha)
EOF
    [ -n "$found_id" ] && break
    i=$((i + 1))
  done

  if [ -z "$found_id" ]; then
    echo "::warning::could not find the deploy run for ${short} within the timeout -- if it did not run, the next sync's heal check will dispatch it"
    exit 0
  fi

  if [ "$found_sha" = "$head" ]; then
    echo "deploy run ${found_id} is building ${short}"
    exit 0
  fi

  echo "::warning::deploy run ${found_id} picked up $(printf '%.8s' "$found_sha"), not ${short} -- GitHub's ref was still stale; dispatching again"
  attempt=$((attempt + 1))
done

echo "::error::${short} was pushed but every deploy dispatch built a different commit. The site is live at an OLDER commit and this run's changes are NOT published. Re-run deploy-hugo.yaml manually against ${ref} once GitHub reports it at ${short}."
exit 1
