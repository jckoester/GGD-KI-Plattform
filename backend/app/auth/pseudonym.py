import hashlib
import hmac


def pseudonymize(external_id: str, school_secret: str) -> str:
    return hmac.new(
        school_secret.encode(), external_id.encode(), hashlib.sha256
    ).hexdigest()
