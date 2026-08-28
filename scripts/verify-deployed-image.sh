#!/usr/bin/env bash
# verify-deployed-image.sh -- assert a container is RUNNING the intended image.
#
# WP-IVGS-07 Task 5. THE INCIDENT THIS EXISTS TO PREVENT, twice in one session
# (WP-IVGS-06 §6.1):
#
#   1. `docker compose up -d --no-deps scheduler` -- the service is named
#      `ivgs-scheduler`. Compose matched nothing, printed nothing, EXITED 0.
#   2. An `ssh root@node bash -s` block without `cd /opt/ivgs`. Its `sed` failed,
#      the tag was never bumped, compose recreated the OLD image, EXITED 0.
#
# Both were reported as successful deploys by every check that trusted the
# command. Only opening the running container found them. A third shape exists
# and bit this package too: a service under `profiles:` is silently skipped
# unless `--profile` is passed (`coqui-tts` on node-04).
#
# Same family as the `docker exec` heredoc trap in dev/CLAUDE.md §7: a green
# result from a command that never ran.
#
# Usage:
#   scripts/verify-deployed-image.sh <container> <expected-tag-substring> [ssh-host]
# Exits 0 only if the container exists AND its image matches. Never exits 0 on
# "container not found" -- that is the failure mode being guarded, not a pass.
set -uo pipefail

CNT="${1:?usage: verify-deployed-image.sh <container> <expected-tag> [ssh-host]}"
WANT="${2:?expected tag substring required}"
HOST="${3:-}"

if [ -n "$HOST" ]; then
  RUNNING=$(ssh -o BatchMode=yes "root@$HOST" \
    "docker inspect '$CNT' --format '{{.Config.Image}}' 2>/dev/null" 2>/dev/null)
else
  RUNNING=$(docker inspect "$CNT" --format '{{.Config.Image}}' 2>/dev/null)
fi

WHERE="${HOST:-local}"
if [ -z "$RUNNING" ]; then
  echo "DEPLOY FAILED [$WHERE]: container '$CNT' is not running at all"
  exit 1
fi
case "$RUNNING" in
  *"$WANT"*) echo "DEPLOY VERIFIED [$WHERE]: $CNT -> $RUNNING"; exit 0 ;;
  *) echo "DEPLOY FAILED [$WHERE]: $CNT is on '$RUNNING', wanted '*$WANT*'"; exit 1 ;;
esac
