"""SSRF koruması: yalnızca genel internete çözülen http(s) adreslerine izin verilir."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from urllib.parse import urlsplit, urlunsplit

from .errors import UnsafeUrl

Resolver = Callable[[str, int], list[str]]
MAX_URL_LENGTH = 2048
ALLOWED_PORTS = {None, 80, 443}
_BLOCKED_SUFFIXES = (".local", ".internal", ".localhost", ".lan", ".home", ".corp")


def _default_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrl("Adres çözümlenemedi") from exc
    return [str(info[4][0]) for info in infos]


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_public_url(url: str, resolver: Resolver | None = None) -> str:
    """Güvenliyse normalize edilmiş URL'yi döndürür, değilse UnsafeUrl fırlatır.

    Yönlendirme sonrası her yeni adres için tekrar çağrılmalıdır.
    """
    text = url.strip()
    if not text or len(text) > MAX_URL_LENGTH:
        raise UnsafeUrl("Geçersiz bağlantı uzunluğu")
    parts = urlsplit(text)
    if parts.scheme.lower() not in ("http", "https"):
        raise UnsafeUrl("Yalnızca http/https bağlantıları kabul edilir")
    if parts.username is not None or parts.password is not None:
        raise UnsafeUrl("Kullanıcı bilgisi içeren bağlantı kabul edilmez")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeUrl("Bağlantıda alan adı yok")
    try:
        port = parts.port
    except ValueError as exc:
        raise UnsafeUrl("Geçersiz bağlantı portu") from exc
    if port not in ALLOWED_PORTS:
        raise UnsafeUrl("Bu bağlantı portu kabul edilmez")
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        raise UnsafeUrl("Yerel alan adları kabul edilmez")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        addresses = (resolver or _default_resolver)(host, port or 443)
    else:
        addresses = [str(literal)]
    if not addresses:
        raise UnsafeUrl("Adres çözümlenemedi")
    for address in addresses:
        if not _is_public(address):
            raise UnsafeUrl("Özel/yerel ağ adresleri kabul edilmez")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", parts.query, ""))
