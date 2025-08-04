import docker

try:
    client = docker.DockerClient(base_url="npipe:////./pipe/docker_engine")
    version = client.version()
    print("Docker version info:", version)
except Exception as e:
    print("Error:", e)
