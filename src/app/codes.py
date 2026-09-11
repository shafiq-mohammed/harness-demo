"""Short code generation."""

import secrets
import string

CODE_ALPHABET = string.ascii_letters + string.digits
CODE_LENGTH = 8


def generate_code(length: int = CODE_LENGTH) -> str:
    """Return a random code of `length` characters from CODE_ALPHABET."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(length))
