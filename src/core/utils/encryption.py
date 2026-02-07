from cryptography.fernet import Fernet
from django.conf import settings
import base64

class EncryptionUtils:
    """
    Utility to Encrypt/Decrypt Sensitive Data (PII)
    Uses AES-128 via Fernet
    """
    
    @staticmethod
    def get_cipher():
        key = settings.ENCRYPTION_KEY
        # Ensure key is bytes
        if isinstance(key, str):
            key = key.encode()
        return Fernet(key)

    @staticmethod
    def encrypt(data: str) -> str:
        if not data:
            return ""
        cipher_suite = EncryptionUtils.get_cipher()
        encrypted_bytes = cipher_suite.encrypt(data.encode())
        return encrypted_bytes.decode()

    @staticmethod
    def decrypt(token: str) -> str:
        if not token:
            return ""
        try:
            cipher_suite = EncryptionUtils.get_cipher()
            decrypted_bytes = cipher_suite.decrypt(token.encode())
            return decrypted_bytes.decode()
        except Exception:
            # If decryption fails (e.g. invalid token, wrong key), return empty string or raw
            # Returning empty string is safer to avoid showing garbage
            return ""
