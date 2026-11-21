"""Bound Redis connections and verify hostnames for TLS endpoints."""

from redis import Redis


def create_redis(url: str, *, worker: bool = False) -> Redis:
    tls = (
        {"ssl_cert_reqs": "required", "ssl_check_hostname": True}
        if url.startswith("rediss://")
        else {}
    )
    return Redis.from_url(
        url,
        socket_connect_timeout=2,
        socket_timeout=4 if worker else 2,
        max_connections=4 if worker else 16,
        **tls,
    )
