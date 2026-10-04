"""Self-signed certificate for the optional HTTPS mode."""

from __future__ import annotations

import datetime
import ipaddress
import os
from pathlib import Path

MDNS_HOSTNAME = "lanimals.local"
# Apple 平台拒绝有效期超过 825 天的服务器证书。
_VALID_DAYS = 825
_RENEW_BEFORE = datetime.timedelta(days=30)


def ensure_certificate(data_dir: Path, bind_host: str) -> tuple[Path, Path]:
    """Return a certificate covering bind_host, creating one only when needed.

    Reusing the same certificate matters: every new certificate makes each
    device show the browser warning again.
    """
    tls_dir = Path(data_dir) / "tls"
    cert_path = tls_dir / "cert.pem"
    key_path = tls_dir / "key.pem"
    if not _certificate_is_usable(cert_path, key_path, bind_host):
        _generate(tls_dir, cert_path, key_path, bind_host)
    return cert_path, key_path


def _certificate_is_usable(cert_path: Path, key_path: Path, bind_host: str) -> bool:
    from cryptography import x509

    if not key_path.is_file():
        return False
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    except (OSError, ValueError, x509.ExtensionNotFound):
        return False
    now = datetime.datetime.now(datetime.timezone.utc)
    if cert.not_valid_after_utc - now < _RENEW_BEFORE:
        return False
    covered = {str(address) for address in names.get_values_for_type(x509.IPAddress)}
    covered.update(names.get_values_for_type(x509.DNSName))
    return bind_host in covered


def _generate(tls_dir: Path, cert_path: Path, key_path: Path, bind_host: str) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    tls_dir.mkdir(parents=True, exist_ok=True)
    key = ec.generate_private_key(ec.SECP256R1())
    addresses = {ipaddress.ip_address("127.0.0.1")}
    dns_names = [MDNS_HOSTNAME, "localhost"]
    try:
        addresses.add(ipaddress.ip_address(bind_host))
    except ValueError:
        # 命令行配置里的 host 也可能是主机名。
        if bind_host not in dns_names:
            dns_names.append(bind_host)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, MDNS_HOSTNAME)])
    not_before = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_before + datetime.timedelta(days=_VALID_DAYS))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName(name) for name in dns_names]
                + [x509.IPAddress(address) for address in sorted(addresses, key=str)]
            ),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .sign(key, hashes.SHA256())
    )

    key_bytes = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    temporary_key = tls_dir / ".key.pem.tmp"
    temporary_cert = tls_dir / ".cert.pem.tmp"
    descriptor = os.open(temporary_key, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key_bytes)
    temporary_cert.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.replace(temporary_key, key_path)
    os.replace(temporary_cert, cert_path)
