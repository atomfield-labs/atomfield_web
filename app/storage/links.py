"""
Signed links: URLs that carry their own permission.

A link allows one action (download or upload) on one key until an
expiry; an upload link also caps the size. Its signature is an HMAC of
exactly those fields with the server's secret: change any of them and
the signature no longer matches. Any API process can check a link
without a database lookup, and nothing needs cleaning up afterwards.
"""

import hashlib
import hmac
from dataclasses import dataclass

DOWNLOAD = "GET"
UPLOAD = "PUT"


@dataclass(frozen=True, slots=True)
class LinkGrant:
    """
    What one signed link allows.

    :param method: ``DOWNLOAD`` or ``UPLOAD``; signed, never sent, so a
        download link cannot be replayed as an upload.
    :type method: str
    :param key: The one file the link opens.
    :type key: str
    :param expires: Unix time after which the link is refused.
    :type expires: int
    :param max_bytes: Largest upload accepted (uploads only).
    :type max_bytes: int
    :param filename: Name the browser saves a download as.
    :type filename: str
    """

    method: str
    key: str
    expires: int
    max_bytes: int = 0
    filename: str = ""

    def message(self) -> bytes:
        """
        The exact bytes that are signed. Fields cannot contain a
        newline (keys and filenames are checked), so the joined form
        is unambiguous.

        :return: Canonical encoding of the grant.
        :rtype: bytes
        """
        fields = (
            self.method,
            self.key,
            str(self.expires),
            str(self.max_bytes),
            self.filename,
        )
        return "\n".join(fields).encode()


class LinkSigner:
    """
    Signs and checks link grants with the server's secret.
    """

    def __init__(self, secret: str) -> None:
        """
        :param secret: Shared by every API process; never leaves them.
        :type secret: str
        """
        self.secret = secret.encode()

    def sign(self, grant: LinkGrant) -> str:
        """
        Compute a grant's signature.

        :param grant: What the link allows.
        :type grant: LinkGrant
        :return: HMAC-SHA256 as hex.
        :rtype: str
        """
        return hmac.new(
            self.secret, grant.message(), hashlib.sha256
        ).hexdigest()

    def verify(self, grant: LinkGrant, signature: str, now: float) -> bool:
        """
        Check a link: unexpired, and signed for exactly this grant.

        ``compare_digest`` takes the same time however many leading
        characters match; ``==`` stops at the first difference, which
        lets an attacker guess a signature one character at a time.

        :param grant: What the request asks to do.
        :type grant: LinkGrant
        :param signature: Signature carried by the link.
        :type signature: str
        :param now: Current Unix time.
        :type now: float
        :return: True if the link allows the request.
        :rtype: bool
        """
        if grant.expires < now:
            return False
        return hmac.compare_digest(self.sign(grant), signature)
