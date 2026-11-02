"""
Keeping a person's AI key. It is encrypted, not hashed like AtomField's
own keys: those are only ever compared, while this one has to be sent to
the vendor again later.
"""

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

ENCODING = "utf-8"


class KeyUnreadableError(Exception):
    """
    A stored key can't be read: the server's secret has changed since.
    """


def fernet_key_from(secret: str) -> bytes:
    """
    Make the key Fernet wants from the secret in ``.env``, which is any
    long random text (``openssl rand -hex 32``), as the other secrets are.

    :param secret: ``AI_KEY_SECRET``.
    :type secret: str
    :return: 32 bytes, base64 encoded for a URL.
    :rtype: bytes
    """
    digest = hashlib.sha256(secret.encode(ENCODING)).digest()
    return base64.urlsafe_b64encode(digest)


class KeyVault:
    """
    Encrypts keys for the database, and reads them back to use them.
    """

    def __init__(self, secret: str) -> None:
        """
        :param secret: ``AI_KEY_SECRET``.
        :type secret: str
        """
        self.fernet = Fernet(fernet_key_from(secret))

    def seal(self, key: str) -> str:
        """
        Encrypt a key.

        :param key: The vendor's key.
        :type key: str
        :return: What is stored.
        :rtype: str
        """
        return self.fernet.encrypt(key.encode(ENCODING)).decode(ENCODING)

    def reveal(self, sealed: str) -> str:
        """
        Read a stored key back, to send it to its vendor.

        :param sealed: What ``seal`` returned.
        :type sealed: str
        :return: The vendor's key.
        :rtype: str
        :raises KeyUnreadableError: If this server's secret didn't seal it.
        """
        try:
            opened = self.fernet.decrypt(sealed.encode(ENCODING))
        except InvalidToken as error:
            raise KeyUnreadableError from error
        return opened.decode(ENCODING)
