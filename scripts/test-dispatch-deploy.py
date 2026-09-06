#!/usr/bin/env python3
"""Tests for dispatch-deploy.sh, run with a stub `gh` on PATH.

Run with:  python3 scripts/test-dispatch-deploy.py

The bug this guards against, observed 2026-09-06: sync-geschichten.yaml pushed
a944c998 and dispatched deploy-hugo.yaml one second later; GitHub resolved 'main' to
the PREVIOUS commit and built that instead. The step reported success, the story sat
committed but unpublished, and the heal path would not have noticed until the next run
with nothing to commit -- a week later.

The stub `gh` lets the lag be reproduced deterministically. It emulates the CONTRACT of
the three calls the script makes -- a sha, a list of run ids, a list of "id sha" lines
-- rather than gh's JSON, because that is exactly the surface the script depends on.
"""

import os
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "dispatch-deploy.sh")
HEAD = "a944c998aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
OLD = "7603a93abbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

failures = []

STUB = r"""#!/bin/sh
# Stub `gh`. Scenario comes from files in $STUB_DIR; every call is logged.
echo "$*" >> "$STUB_DIR/calls"
case "$1" in
  api)
    n=$(cat "$STUB_DIR/ref_n" 2>/dev/null || echo 1)
    total=$(wc -l < "$STUB_DIR/ref_shas")
    [ "$n" -gt "$total" ] && n="$total"
    sed -n "${n}p" "$STUB_DIR/ref_shas"
    echo $((n + 1)) > "$STUB_DIR/ref_n"
    ;;
  workflow)
    k=$(cat "$STUB_DIR/disp_n" 2>/dev/null || echo 0)
    echo $((k + 1)) > "$STUB_DIR/disp_n"
    ;;
  run)
    # Runs created by the dispatches so far, newest first, then the pre-existing one.
    k=$(cat "$STUB_DIR/disp_n" 2>/dev/null || echo 0)
    i="$k"
    while [ "$i" -ge 1 ]; do
      sha=$(sed -n "${i}p" "$STUB_DIR/run_shas")
      if [ -n "$sha" ]; then
        case "$*" in
          *headSha*) echo "$((100 + i)) $sha" ;;
          *)         echo "$((100 + i))" ;;
        esac
      fi
      i=$((i - 1))
    done
    case "$*" in
      *headSha*) echo "100 0000000000000000000000000000000000000000" ;;
      *)         echo "100" ;;
    esac
    ;;
esac
"""


def check(name, cond, detail=""):
    if cond:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


def run(tmp, ref_shas, run_shas, head=HEAD, **env):
    """Run the script against a scenario. Returns (rc, output, calls)."""
    stub_dir = tempfile.mkdtemp(dir=tmp)
    bin_dir = os.path.join(stub_dir, "bin")
    os.makedirs(bin_dir)
    gh = os.path.join(bin_dir, "gh")
    with open(gh, "w") as fh:
        fh.write(STUB)
    os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    for name, lines in (("ref_shas", ref_shas), ("run_shas", run_shas)):
        with open(os.path.join(stub_dir, name), "w") as fh:
            fh.write("".join(l + "\n" for l in lines))

    e = dict(os.environ)
    e.update({
        "PATH": bin_dir + os.pathsep + e["PATH"],
        "STUB_DIR": stub_dir,
        "GITHUB_REPOSITORY": "Kinderkrippe-Olten/kinderkrippe-olten-website",
        # No waiting in tests: the timings are the thing under test, not the clock.
        "DISPATCH_POLL_INTERVAL": "0",
        "DISPATCH_REF_TRIES": "4",
        "DISPATCH_RUN_TRIES": "3",
        "DISPATCH_ATTEMPTS": "2",
    })
    e.update(env)
    p = subprocess.run([SCRIPT, head, "main"], capture_output=True, text=True, env=e)
    calls = []
    path = os.path.join(stub_dir, "calls")
    if os.path.isfile(path):
        calls = [l.rstrip("\n") for l in open(path)]
    return p.returncode, p.stdout + p.stderr, calls


def dispatches(calls):
    return [c for c in calls if c.startswith("workflow run")]


def main():
    tmp = tempfile.mkdtemp(prefix="dispatch-test-")

    # --- the ref is already current: dispatch once, verify, done ---
    rc, out, calls = run(tmp, ref_shas=[HEAD], run_shas=[HEAD])
    check("happy: rc 0", rc == 0, out)
    check("happy: dispatched exactly once", len(dispatches(calls)) == 1, calls)
    check("happy: says which commit is being deployed", HEAD[:8] in out, out)

    # --- THE BUG: the API's view of main lags the push ---
    rc, out, calls = run(tmp, ref_shas=[OLD, OLD, HEAD], run_shas=[HEAD])
    check("lag: rc 0", rc == 0, out)
    check("lag: dispatched exactly once", len(dispatches(calls)) == 1, calls)
    # The dispatch must come AFTER the ref caught up -- dispatching into the lag is
    # the whole bug, and a script that polled but dispatched anyway would still fail.
    first_dispatch = next(i for i, c in enumerate(calls) if c.startswith("workflow run"))
    ref_calls_before = sum(1 for c in calls[:first_dispatch] if c.startswith("api "))
    check("lag: waited for the ref before dispatching", ref_calls_before == 3,
          calls[:first_dispatch + 1])

    # --- dispatched anyway, but GitHub still built the wrong commit ---
    rc, out, calls = run(tmp, ref_shas=[HEAD], run_shas=[OLD, HEAD])
    check("stale run: rc 0 after the retry", rc == 0, out)
    check("stale run: dispatched twice", len(dispatches(calls)) == 2, calls)
    check("stale run: warns about the run it rejected", "::warning::" in out and OLD[:8] in out,
          out)

    # --- every attempt builds the wrong commit: red run, not a silent success ---
    rc, out, calls = run(tmp, ref_shas=[HEAD], run_shas=[OLD, OLD])
    check("never right: rc 1", rc == 1, out)
    check("never right: stops after DISPATCH_ATTEMPTS", len(dispatches(calls)) == 2, calls)
    check("never right: the error names the undeployed commit",
          "::error::" in out and HEAD[:8] in out, out)

    # --- the ref never catches up: dispatch anyway, the verification is the guard ---
    rc, out, calls = run(tmp, ref_shas=[OLD], run_shas=[HEAD])
    check("ref never catches up: dispatches anyway", len(dispatches(calls)) >= 1, calls)
    check("ref never catches up: rc 0 once the run is right", rc == 0, out)
    check("ref never catches up: says so", "::warning::" in out, out)

    # --- no run appears at all: unknown is not the same claim as known-wrong ---
    # The next sync run's heal path covers this, so it is a warning, not a red run.
    rc, out, calls = run(tmp, ref_shas=[HEAD], run_shas=[""])
    check("no run found: rc 0", rc == 0, out)
    check("no run found: warns rather than failing",
          "::warning::" in out and "::error::" not in out, out)

    if failures:
        print(f"\n{len(failures)} failure(s): " + ", ".join(failures))
        sys.exit(1)
    print("\nall checks passed")


if __name__ == "__main__":
    main()
