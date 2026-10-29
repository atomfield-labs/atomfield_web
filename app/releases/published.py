"""
What releases and data packs share: a name and version is published
once and never changes.

Publishing the same file again changes nothing, so a publish can always
be retried. Other contents under a published name and version are
refused: the change needs a version of its own.
"""

CONFLICT_MESSAGE = (
    "{label} was already published with other contents; give the "
    "change a new version"
)


class PublishConflictError(ValueError):
    """
    This name and version were already published with other contents.
    """


def already_published(
    published_sha256: str | None, sha256: str, label: str
) -> bool:
    """
    Whether this exact file is already published under its name and
    version, so publishing it again changes nothing.

    :param published_sha256: Fingerprint published under that name and
        version, or None if nothing was.
    :type published_sha256: str | None
    :param sha256: Fingerprint of the file being published.
    :type sha256: str
    :param label: Its name and version, for the message.
    :type label: str
    :return: True if it is there already.
    :rtype: bool
    :raises PublishConflictError: If other contents were published
        under that name and version.
    """
    if published_sha256 is None:
        return False
    if published_sha256 != sha256:
        raise PublishConflictError(CONFLICT_MESSAGE.format(label=label))
    return True
