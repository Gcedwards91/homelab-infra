import time

import docker
import docker.errors
import pytest

# Recorded when pytest imports this conftest, before any test runs. Log checks
# use it as a cutoff so they only judge what the stack logged on its own, not
# log lines provoked by the suite's own traffic (e.g. Loki logging a cancelled
# query after test_observability_stack queries it).
SESSION_START = time.time()


@pytest.fixture(scope="module")
def docker_client():
    """Return a Docker client, skipping the module if the daemon is unreachable."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:
        pytest.skip(f"Docker daemon not reachable - is the stack running? ({exc})")


@pytest.fixture(scope="session")
def session_start():
    """Unix timestamp taken before the first test ran."""
    return SESSION_START
