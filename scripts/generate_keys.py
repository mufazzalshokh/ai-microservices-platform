"""Generate local RSA signing material without overwriting either key."""

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def generate(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    private_path = directory / "jwt-private.pem"
    public_path = directory / "jwt-public.pem"
    if private_path.exists() or public_path.exists():
        raise FileExistsError("Refusing to overwrite existing key material")
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    # O_EXCL also prevents a concurrent invocation from replacing a key.
    with os.fdopen(
        os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb"
    ) as file:
        file.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
    with public_path.open("xb") as file:
        file.write(
            key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("keys"))
    generate(parser.parse_args().directory)
