import pytest
import docker
import docker.errors


@pytest.fixture(scope="module")
def docker_client():
    """Return a Docker client, skipping the module if the daemon is unreachable."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as exc:
        pytest.skip(f"Docker daemon not reachable - is the stack running? ({exc})")
