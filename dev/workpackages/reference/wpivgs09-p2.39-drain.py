"""P2.39 drain — §3.3's disposition table, on the operator's GO of 2026-08-28.

Runs INSIDE ivgs-scheduler and uses the scheduler's OWN PriorityQueueManager,
so `remove_job` does what production does rather than what this script thinks
production does. The two direct-Redis operations are the two the operator
approved by name, because `remove_job` provably cannot perform them:

  * rows 19/20 sit in `pq:queue:normal` with `effective_priority=urgent` in
    their hash, so `remove_job` would `zrem` from `urgent` (a miss) and
    decrement `urgent` for a job that never joined it;
  * the two hash-expired urgent entries have no hash at all, and `remove_job`
    is a no-op without one (`priority_queue.py:284`, `if job_data:`).
"""
import asyncio, json, sys
import redis.asyncio as aioredis
from priority_queue import PriorityQueueManager

SYNTHETIC = ["probe", "wpivgs06-probe", "wpivgs07-dbl",
             "d04f0000-0000-4000-8000-0000000000d1",
             "d06f0000-0000-4000-8000-0000000000d1",
             "d07f0000-0000-4000-8000-0000000000d1"]
TERMINAL_NO_HASH = ["b3df6eb6-2056-4ec0-8950-01a0c2afacb6",
                    "1e65b11d-edec-48cf-afaf-9ddf4e448d0b"]
TERMINAL = ["610b35d8-a530-4dbe-af44-94b83905b9c3",
            "439b2779-9e3e-48aa-8aad-6a0f1ffc3756"]
DELETED_PROJECT = ["89383cdd-7798-4b6e-97a6-f395de0b1e33",
                   "1aa7b507-825c-4f1d-bbf7-0421f19572e3",
                   "98b32541-b81b-4de7-a536-a7d44e7b51b0",
                   "8b881252-880f-409b-9d57-bd607a3f16fb",
                   "d4b41765-c8ff-4763-bb9a-4e35a4ad2dfd",
                   "02d2c773-a7bb-4433-8620-c4f3530bfbc6",
                   "bd07f416-908a-4be5-b688-8872e04c37b9",
                   "aae4f8cc-2bc6-4125-b96f-86742dbc2d41",
                   "3f489575-7522-440a-8228-f2490a2d3383",
                   "8cdb79b6-7e88-4d9c-8db2-9b872e3dcf9e"]
IN_NORMAL_ZSET = ["de838c11-b268-45ac-aec0-e03c74ceac1e",
                  "47be634d-10e6-4516-8c2b-2a4f376eb287"]


async def main():
    r = aioredis.from_url("redis://redis:6379/1", decode_responses=True)
    pq = PriorityQueueManager(redis=r)

    async def zcards():
        return {q: await r.zcard(f"pq:queue:{q}") for q in ("urgent", "normal", "batch")}

    async def depths_raw():
        return await r.hgetall("pq:depths")

    print("BEFORE  zcards =", await zcards(), " depths(raw) =", await depths_raw())
    print()

    for label, ids in (("synthetic probe", SYNTHETIC),
                       ("terminal job", TERMINAL),
                       ("deleted project", DELETED_PROJECT)):
        for jid in ids:
            had = bool(await r.hgetall(f"pq:job:{jid}"))
            await pq.remove_job(jid)
            gone = not await r.hgetall(f"pq:job:{jid}")
            still = await r.zscore("pq:queue:urgent", jid)
            print(f"remove_job   {jid:40s} {label:16s} hash_was={had} hash_gone={gone} "
                  f"urgent_zset={'CLEARED' if still is None else 'STILL PRESENT'}")

    print()
    for jid in TERMINAL_NO_HASH:
        n = await r.zrem("pq:queue:urgent", jid)
        print(f"zrem urgent  {jid:40s} terminal, hash expired >72h; remove_job is a "
              f"no-op without a hash -> removed={n}")

    print()
    for jid in IN_NORMAL_ZSET:
        n = await r.zrem("pq:queue:normal", jid)
        d = await r.delete(f"pq:job:{jid}")
        print(f"zrem normal  {jid:40s} hash said urgent, entry was in normal -> "
              f"zrem={n} hash_del={d}")

    print()
    zc = await zcards()
    print("AFTER drain  zcards =", zc, " depths(raw) =", await depths_raw())

    # The counter reset the operator approved: pq:depths becomes the measured
    # ZCARD of each sorted set. This is the ONLY place the two are reconciled;
    # nothing in the scheduler does it.
    for q, n in zc.items():
        await r.hset("pq:depths", q, n)
    print("AFTER reset  zcards =", await zcards(), " depths(raw) =", await depths_raw())
    print()
    print("residual pq:* keys:", sorted([k async for k in r.scan_iter(match="pq:*")]))
    await r.aclose()

asyncio.run(main())

# ---------------------------------------------------------------------------
# BANKED AS EVIDENCE, 2026-08-28. Run once, on the operator's GO, inside
# `ivgs-scheduler` with PYTHONPATH=/app. It is kept because P2.47 will need to
# know exactly what was removed and by which method, and because the reset at
# the end is the only reconciliation of `pq:depths` against the sorted sets that
# has ever happened.
#
# ⛔ NOT A TOOL. Do not re-run it: the id lists are the census of one moment,
# and re-running would `remove_job` ids that may since belong to real work.
# The lasting fix is P2.47, not this file.
#
# Observed output is in WP-IVGS-09-RENDERER-report_2026-08-28.md §3.3-3.4.
# ---------------------------------------------------------------------------
