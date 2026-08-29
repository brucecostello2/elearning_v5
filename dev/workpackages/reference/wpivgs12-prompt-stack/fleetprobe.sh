#!/usr/bin/env bash
# WP-IVGS-12 Task 0(c) — fleet reachability probe, run from node-01.
# Records exactly what was measured on 2026-08-29 05:51-05:58 UTC.
for h in 90 91 92 93 94 95 96 7 51 1; do
  printf '192.168.1.%-3s ' "$h"
  if timeout 2 ping -c1 -W1 "192.168.1.$h" >/dev/null 2>&1; then printf 'icmp=UP  '; else printf 'icmp=--  '; fi
  for p in 22 8000; do
    if timeout 3 bash -c "echo > /dev/tcp/192.168.1.$h/$p" 2>/dev/null; then printf '%s=OPEN ' "$p"; else printf '%s=---- ' "$p"; fi
  done
  ip neigh | awk -v a="192.168.1.$h" '$1==a {printf "arp=%s", $NF}'
  echo
done
