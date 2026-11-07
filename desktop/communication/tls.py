"""Certificado autoassinado para HTTPS/WSS na rede local (D004).

Por que existe: o navegador do celular só libera a câmera (getUserMedia) em
contexto seguro, e o celular acessa o notebook por IP, não por localhost
(docs/architecture.md §2.1).

O certificado é reaproveitado entre execuções enquanto o IP for o mesmo e ele
não estiver perto de expirar, para o professor não precisar aceitar um aviso
novo a cada aula.
"""

from __future__ import annotations

import datetime as dt
import ipaddress
import os
import socket
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from desktop import config

CERT_FILENAME = "smartboard-cert.pem"
KEY_FILENAME = "smartboard-key.pem"
_LOOPBACK = "127.0.0.1"


@dataclass(frozen=True)
class CertificatePaths:
    cert: Path
    key: Path
    created: bool  # True se foi gerado agora; False se reaproveitado


def detect_local_ip() -> str:
    """IP IPv4 da interface usada para sair para a rede.

    Abre um socket UDP "conectado" a um endereço privado. Nenhum pacote é
    enviado; o sistema operacional só escolhe a interface de saída. Funciona
    igual no macOS e no Windows (R7). Sem rede, devolve 127.0.0.1.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        ip = probe.getsockname()[0]
    except OSError:
        ip = _LOOPBACK
    finally:
        probe.close()
    return ip


def _certificate_covers(cert_path: Path, ip: str, now: dt.datetime) -> bool:
    """True se o certificado existente inclui `ip` e não está perto de expirar."""
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    except (OSError, ValueError, x509.ExtensionNotFound):
        return False

    ips = {str(addr) for addr in san.value.get_values_for_type(x509.IPAddress)}
    renew_at = cert.not_valid_after_utc - dt.timedelta(days=config.CERT_RENEW_BEFORE_DAYS)
    return ip in ips and now < renew_at


def _generate(cert_path: Path, key_path: Path, ip: str, now: dt.datetime) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"SmartBoard Classroom {ip}")])

    alt_names: list[x509.GeneralName] = [
        x509.IPAddress(ipaddress.ip_address(ip)),
        x509.DNSName("localhost"),
    ]
    if ip != _LOOPBACK:
        alt_names.append(x509.IPAddress(ipaddress.ip_address(_LOOPBACK)))

    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=config.CERT_VALID_DAYS))
        .add_extension(x509.SubjectAlternativeName(alt_names), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .sign(key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    # Chave privada legível só pelo usuário (efeito pleno em macOS/Linux).
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(key_bytes)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def ensure_certificate(
    ip: str, cert_dir: Path = config.CERT_DIR, now: dt.datetime | None = None
) -> CertificatePaths:
    """Garante um certificado válido para `ip`, gerando um novo só se preciso."""
    now = now or dt.datetime.now(dt.timezone.utc)
    cert_path = cert_dir / CERT_FILENAME
    key_path = cert_dir / KEY_FILENAME

    if key_path.exists() and _certificate_covers(cert_path, ip, now):
        return CertificatePaths(cert_path, key_path, created=False)

    _generate(cert_path, key_path, ip, now)
    return CertificatePaths(cert_path, key_path, created=True)


def build_ssl_context(paths: CertificatePaths) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certfile=paths.cert, keyfile=paths.key)
    return context
