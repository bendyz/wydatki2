import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

_VERIFICATION_PLAINTEXT = b"wydatki-majatek-v1"
_PBKDF2_ITERATIONS = 600_000


def _derive_key(password: str, salt_hex: str) -> Fernet:
    salt = bytes.fromhex(salt_hex)
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PBKDF2_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
    return Fernet(key)


def generate_setup(password: str) -> tuple[str, str]:
    """Return (salt_hex, verification_token) for a new key setup."""
    salt = os.urandom(16)
    salt_hex = salt.hex()
    fernet = _derive_key(password, salt_hex)
    verification_token = fernet.encrypt(_VERIFICATION_PLAINTEXT).decode()
    return salt_hex, verification_token


def verify_password(password: str, salt_hex: str, verification_token: str) -> bool:
    try:
        fernet = _derive_key(password, salt_hex)
        return fernet.decrypt(verification_token.encode()) == _VERIFICATION_PLAINTEXT
    except (InvalidToken, Exception):
        return False


def get_fernet(password: str, salt_hex: str) -> Fernet:
    return _derive_key(password, salt_hex)


def encrypt(fernet: Fernet, value: str) -> str:
    return fernet.encrypt(value.encode()).decode()


def decrypt(fernet: Fernet, token: str) -> str:
    return fernet.decrypt(token.encode()).decode()
