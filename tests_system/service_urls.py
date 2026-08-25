"""
One place where `tests_system` learns which host the services are on.

WP-52. Ten call sites across this tree hardcoded `localhost` against services
that node-01 publishes on its LAN address only -- `docker ps` shows
`192.168.1.90:8001->8001/tcp`, not `0.0.0.0`, so `http://localhost:8001` is
refused, not merely slow. The `e2e` modules already did the right thing shape --
`os.getenv("E2E_BASE_URL", ...)` -- but with a default that was wrong in the
same way. This module is that shape, once, with a default that resolves.

Conventions
-----------
`IVGS_TEST_HOST`            host publishing the stack        default 192.168.1.90
`IVGS_TEST_API_URL`         full API base, overrides host    default http://$HOST:8001/api/v1
`IVGS_TEST_SCHEDULER_URL`   full scheduler base              default http://$HOST:8002

The two ports are DIFFERENT services and stay separate: 8001 is `ivgs-fastapi`,
8002 is `ivgs-scheduler` (whose container listens on 8001 internally and is
published on 8002). Collapsing them would point the scheduler tests at the API.

`E2E_BASE_URL` is still honoured as an alias for `IVGS_TEST_API_URL` so existing
invocations and runbooks keep working; it is checked first for that reason.

The default host is a literal rather than a read of the node registry on
purpose: this module has to work in a bare checkout with no `.env`, and
192.168.1.0/24 is what spec 2.3 mandates. See
`spec_compliance/test_no_hardcoded_ips.py` for the guard that matters -- the
obsolete scheme -- which this does not trip.
"""
import os

#: Host publishing the node-01 service ports. Override for a remote stack.
TEST_HOST = os.getenv("IVGS_TEST_HOST", "192.168.1.90")

#: ivgs-fastapi. Published 8001 -> 8001.
API_BASE_URL = (
    os.getenv("E2E_BASE_URL")
    or os.getenv("IVGS_TEST_API_URL")
    or f"http://{TEST_HOST}:8001/api/v1"
)

#: ivgs-scheduler. Published 8002 -> 8001. Not the same service as above.
SCHEDULER_URL = os.getenv("IVGS_TEST_SCHEDULER_URL") or f"http://{TEST_HOST}:8002"

#: Redis and SeaweedFS, for the environment block in `conftest.py`.
#: Redis logical database 15 is the test scratch db and is deliberate.
REDIS_URL = os.getenv("IVGS_TEST_REDIS_URL") or f"redis://{TEST_HOST}:6379/15"
SEAWEEDFS_MASTER_URL = (
    os.getenv("IVGS_TEST_SEAWEEDFS_MASTER_URL") or f"http://{TEST_HOST}:9333"
)
SEAWEEDFS_FILER_URL = (
    os.getenv("IVGS_TEST_SEAWEEDFS_FILER_URL") or f"http://{TEST_HOST}:8888"
)

__all__ = [
    "TEST_HOST",
    "API_BASE_URL",
    "SCHEDULER_URL",
    "REDIS_URL",
    "SEAWEEDFS_MASTER_URL",
    "SEAWEEDFS_FILER_URL",
]
