"""Testes do certificado autoassinado (etapa 1.2, D004)."""

import datetime as dt
import ipaddress
import ssl
import sys

import pytest
from cryptography import x509

from desktop import config
from desktop.communication.tls import (
    build_ssl_context,
    detect_local_ip,
    ensure_certificate,
)

IP = "192.168.1.74"


def san_ips(cert_path) -> set[str]:
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    return {str(a) for a in san.get_values_for_type(x509.IPAddress)}


def test_generates_certificate_with_ip_in_san(tmp_path):
    paths = ensure_certificate(IP, cert_dir=tmp_path)
    assert paths.created is True
    assert paths.cert.exists() and paths.key.exists()
    assert IP in san_ips(paths.cert)
    assert "127.0.0.1" in san_ips(paths.cert)


def test_reuses_certificate_for_same_ip(tmp_path):
    first = ensure_certificate(IP, cert_dir=tmp_path)
    content = first.cert.read_bytes()
    second = ensure_certificate(IP, cert_dir=tmp_path)
    assert second.created is False
    assert second.cert.read_bytes() == content


def test_regenerates_when_ip_changes(tmp_path):
    ensure_certificate(IP, cert_dir=tmp_path)
    other = ensure_certificate("10.0.0.5", cert_dir=tmp_path)
    assert other.created is True
    assert "10.0.0.5" in san_ips(other.cert)


def test_regenerates_when_close_to_expiry(tmp_path):
    now = dt.datetime.now(dt.timezone.utc)
    ensure_certificate(IP, cert_dir=tmp_path, now=now)
    later = now + dt.timedelta(days=config.CERT_VALID_DAYS - config.CERT_RENEW_BEFORE_DAYS + 1)
    assert ensure_certificate(IP, cert_dir=tmp_path, now=later).created is True


def test_regenerates_when_certificate_is_corrupted(tmp_path):
    paths = ensure_certificate(IP, cert_dir=tmp_path)
    paths.cert.write_text("lixo", encoding="utf-8")
    assert ensure_certificate(IP, cert_dir=tmp_path).created is True


@pytest.mark.skipif(sys.platform == "win32", reason="permissões POSIX")
def test_private_key_is_owner_only(tmp_path):
    paths = ensure_certificate(IP, cert_dir=tmp_path)
    assert paths.key.stat().st_mode & 0o077 == 0


def test_ssl_context_loads(tmp_path):
    context = build_ssl_context(ensure_certificate(IP, cert_dir=tmp_path))
    assert isinstance(context, ssl.SSLContext)
    assert context.minimum_version >= ssl.TLSVersion.TLSv1_2


def test_detect_local_ip_returns_ipv4():
    ip = ipaddress.ip_address(detect_local_ip())
    assert ip.version == 4
