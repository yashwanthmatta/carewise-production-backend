import base64
import os
import secrets


def main() -> None:
    jwt_secret = secrets.token_urlsafe(64)
    field_encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")
    print("CAREWISE_JWT_SECRET=" + jwt_secret)
    print("CAREWISE_FIELD_ENCRYPTION_KEY=" + field_encryption_key)


if __name__ == "__main__":
    main()
