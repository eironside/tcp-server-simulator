import pytest

from tcp_sim.transport.tcp_client import TcpClientConfig, create_client_ssl_context
from tcp_sim.transport.tcp_server import TcpServerConfig, create_server_ssl_context


@pytest.mark.unit
def test_server_tls_context_disabled_returns_none() -> None:
    config = TcpServerConfig(use_tls=False)
    assert create_server_ssl_context(config) is None


@pytest.mark.unit
def test_server_tls_context_requires_cert_and_key() -> None:
    config = TcpServerConfig(use_tls=True, tls_certfile=None, tls_keyfile=None)
    with pytest.raises(ValueError):
        create_server_ssl_context(config)


@pytest.mark.unit
def test_client_tls_context_disabled_returns_none() -> None:
    config = TcpClientConfig(host="127.0.0.1", port=5565, use_tls=False)
    assert create_client_ssl_context(config) is None


@pytest.mark.unit
def test_client_tls_context_rejects_disabled_verification() -> None:
    config = TcpClientConfig(
        host="127.0.0.1",
        port=5565,
        use_tls=True,
        tls_verify=False,
    )
    with pytest.raises(ValueError):
        create_client_ssl_context(config)
