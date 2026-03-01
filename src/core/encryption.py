"""
Encryption Service - AES Encryption for Sensitive Data
Nexira / Nexira v12 - Phase 4
Created by Xeeker & Claude - February 2026

Uses Fernet (AES-128-CBC + HMAC) from the cryptography library.
Key is generated once and stored in data/nexira.key
Encrypts: journal entries, config passwords
"""

import os
import base64
from pathlib import Path
from typing import Optional


KEY_FILENAME = 'nexira.key'


class EncryptionService:
    """
    Transparent encrypt/decrypt for sensitive data.
    Key is auto-generated on first run and stored locally.
    """

    def __init__(self, base_dir: str):
        self.key_path = os.path.join(base_dir, 'data', KEY_FILENAME)
        self._fernet = None
        self._available = False
        self._init_encryption()

    def _init_encryption(self):
        """Load or generate the encryption key."""
        try:
            from cryptography.fernet import Fernet
        except ImportError:
            print("⚠️  cryptography package not installed — encryption disabled")
            print("   Run: pip install cryptography --break-system-packages")
            return

        try:
            os.makedirs(os.path.dirname(self.key_path), exist_ok=True)

            if os.path.exists(self.key_path):
                with open(self.key_path, 'rb') as f:
                    key = f.read().strip()
            else:
                key = Fernet.generate_key()
                with open(self.key_path, 'wb') as f:
                    f.write(key)
                # Restrict permissions so only owner can read
                os.chmod(self.key_path, 0o600)
                print(f"✓ Encryption key generated: {self.key_path}")

            self._fernet = Fernet(key)
            self._available = True
            print("✓ Encryption service ready")

        except Exception as e:
            print(f"⚠️  Encryption init failed: {e}")

    @property
    def available(self) -> bool:
        return self._available

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string. Returns encrypted string prefixed with 'ENC:'
        so we can detect already-encrypted values.
        Falls back to plaintext if encryption not available.
        """
        if not self._available or not plaintext:
            return plaintext
        try:
            token = self._fernet.encrypt(plaintext.encode('utf-8'))
            return 'ENC:' + base64.urlsafe_b64encode(token).decode('utf-8')
        except Exception as e:
            print(f"⚠️  Encrypt error: {e}")
            return plaintext

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string. If not prefixed with 'ENC:', returns as-is
        (handles plaintext values stored before encryption was enabled).
        """
        if not self._available or not ciphertext:
            return ciphertext
        if not ciphertext.startswith('ENC:'):
            return ciphertext  # plaintext, not yet encrypted
        try:
            token = base64.urlsafe_b64decode(ciphertext[4:].encode('utf-8'))
            return self._fernet.decrypt(token).decode('utf-8')
        except Exception as e:
            print(f"⚠️  Decrypt error: {e}")
            return ciphertext

    def encrypt_journal_entry(self, content: str) -> str:
        return self.encrypt(content)

    def decrypt_journal_entry(self, content: str) -> str:
        return self.decrypt(content)

    def encrypt_password(self, password: str) -> str:
        return self.encrypt(password)

    def decrypt_password(self, password: str) -> str:
        return self.decrypt(password)
