"""Content-addressed, immutable artifact store (spec 5.4, 11.2).

Identity is SHA-256 of the bytes. Objects live under
``<root>/sha256/<hex[0:2]>/<hex>`` and are written atomically (temp file +
rename) then made read-only. Re-putting identical bytes is a no-op; existing
objects are never overwritten. Reads re-verify the hash.

URIs have the form ``artifact://sha256/<hex>`` so references stay valid when the
root moves (e.g. local filesystem in development, blob storage later).
"""

from __future__ import annotations

import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path

from research_engine.contracts.common import HASH_PREFIX, sha256_bytes

URI_PREFIX = "artifact://sha256/"


class ArtifactIntegrityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactRef:
    uri: str
    content_hash: str
    size: int


def uri_for_hash(content_hash: str) -> str:
    return URI_PREFIX + content_hash.removeprefix(HASH_PREFIX)


class ArtifactStore:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        (self.root / "sha256").mkdir(parents=True, exist_ok=True)

    def _path(self, hex_digest: str) -> Path:
        return self.root / "sha256" / hex_digest[:2] / hex_digest

    @staticmethod
    def _hex(ref: str) -> str:
        if ref.startswith(URI_PREFIX):
            return ref[len(URI_PREFIX) :]
        if ref.startswith(HASH_PREFIX):
            return ref[len(HASH_PREFIX) :]
        raise ValueError(f"not an artifact reference: {ref!r}")

    def put(self, data: bytes) -> ArtifactRef:
        digest = sha256_bytes(data)
        hex_digest = digest.removeprefix(HASH_PREFIX)
        path = self._path(hex_digest)
        if path.exists():
            if sha256_bytes(path.read_bytes()) != digest:
                raise ArtifactIntegrityError(f"stored object {hex_digest} is corrupt")
            return ArtifactRef(uri_for_hash(digest), digest, len(data))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.chmod(tmp, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return ArtifactRef(uri_for_hash(digest), digest, len(data))

    def put_text(self, text: str) -> ArtifactRef:
        return self.put(text.encode("utf-8"))

    def exists(self, ref: str) -> bool:
        return self._path(self._hex(ref)).exists()

    def get(self, ref: str) -> bytes:
        hex_digest = self._hex(ref)
        path = self._path(hex_digest)
        data = path.read_bytes()
        if sha256_bytes(data) != HASH_PREFIX + hex_digest:
            raise ArtifactIntegrityError(f"artifact {hex_digest} failed verification")
        return data

    def get_text(self, ref: str) -> str:
        return self.get(ref).decode("utf-8")
