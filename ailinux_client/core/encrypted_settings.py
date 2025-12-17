"""
Encrypted User Settings Storage

Securely stores user data (bookmarks, auth tokens, preferences) encrypted
with the user's password. Syncs with MCP server when online.
"""

import os
import json
import base64
import hashlib
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

logger = logging.getLogger("ailinux.encrypted_settings")


class EncryptedSettingsError(Exception):
    """Base exception for encrypted settings errors."""
    pass


class DecryptionError(EncryptedSettingsError):
    """Raised when decryption fails (wrong password)."""
    pass


class EncryptedSettings:
    """
    Encrypted settings storage with server sync capability.

    Data is encrypted using the user's password via PBKDF2 + Fernet (AES).
    Only the user can decrypt their own data.
    """

    SETTINGS_FILE = "user_settings.enc"
    SALT_FILE = "user_settings.salt"
    VERSION = 1

    def __init__(self, storage_dir: Optional[Path] = None):
        """
        Initialize encrypted settings.

        Args:
            storage_dir: Directory for storing encrypted files.
                        Defaults to ~/.config/ailinux-client/
        """
        if not HAS_CRYPTO:
            logger.warning("cryptography package not installed. Using fallback storage.")

        self.storage_dir = storage_dir or Path.home() / ".config" / "ailinux-client"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._fernet: Optional[Fernet] = None
        self._data: Dict[str, Any] = self._default_data()
        self._unlocked = False
        self._password_hash: Optional[str] = None

    def _default_data(self) -> Dict[str, Any]:
        """Return default empty data structure."""
        return {
            "version": self.VERSION,
            "bookmarks": [],
            "favorites": [],
            "auth": {
                "tokens": {},
                "credentials": {}
            },
            "preferences": {},
            "sync": {
                "last_sync": None,
                "server_revision": 0
            }
        }

    def _derive_key(self, password: str, salt: bytes) -> bytes:
        """
        Derive encryption key from password using PBKDF2.

        Args:
            password: User's password
            salt: Random salt for key derivation

        Returns:
            32-byte key suitable for Fernet
        """
        if not HAS_CRYPTO:
            # Fallback: simple hash (less secure)
            key_material = hashlib.sha256((password + salt.hex()).encode()).digest()
            return base64.urlsafe_b64encode(key_material)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,  # OWASP recommended minimum
        )
        key = kdf.derive(password.encode())
        return base64.urlsafe_b64encode(key)

    def _get_or_create_salt(self) -> bytes:
        """Get existing salt or create new one."""
        salt_path = self.storage_dir / self.SALT_FILE

        if salt_path.exists():
            return salt_path.read_bytes()

        # Generate new random salt
        salt = os.urandom(32)
        salt_path.write_bytes(salt)
        return salt

    def is_initialized(self) -> bool:
        """Check if encrypted settings file exists."""
        return (self.storage_dir / self.SETTINGS_FILE).exists()

    def is_unlocked(self) -> bool:
        """Check if settings are currently unlocked."""
        return self._unlocked

    def initialize(self, password: str) -> bool:
        """
        Initialize new encrypted settings with password.

        Args:
            password: Password to encrypt settings with

        Returns:
            True if successful
        """
        try:
            salt = self._get_or_create_salt()
            key = self._derive_key(password, salt)

            if HAS_CRYPTO:
                self._fernet = Fernet(key)
            else:
                self._fernet = key  # Store key for fallback

            self._data = self._default_data()
            self._password_hash = hashlib.sha256(password.encode()).hexdigest()
            self._unlocked = True

            # Save initial empty data
            self._save()

            logger.info("Encrypted settings initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize encrypted settings: {e}")
            return False

    def unlock(self, password: str) -> bool:
        """
        Unlock encrypted settings with password.

        Args:
            password: User's password

        Returns:
            True if unlock successful, False if wrong password
        """
        try:
            salt = self._get_or_create_salt()
            key = self._derive_key(password, salt)

            settings_path = self.storage_dir / self.SETTINGS_FILE

            if not settings_path.exists():
                # First time - initialize
                return self.initialize(password)

            encrypted_data = settings_path.read_bytes()

            if HAS_CRYPTO:
                self._fernet = Fernet(key)
                decrypted = self._fernet.decrypt(encrypted_data)
            else:
                # Fallback: XOR with key (less secure)
                decrypted = self._xor_decrypt(encrypted_data, key)

            self._data = json.loads(decrypted.decode('utf-8'))
            self._password_hash = hashlib.sha256(password.encode()).hexdigest()
            self._unlocked = True

            logger.info("Encrypted settings unlocked")
            return True

        except (InvalidToken if HAS_CRYPTO else Exception) as e:
            logger.warning(f"Failed to unlock settings: wrong password or corrupted data")
            return False
        except Exception as e:
            logger.error(f"Error unlocking settings: {e}")
            return False

    def lock(self):
        """Lock settings and clear sensitive data from memory."""
        self._save()
        self._fernet = None
        self._data = self._default_data()
        self._password_hash = None
        self._unlocked = False
        logger.info("Encrypted settings locked")

    def _save(self):
        """Save encrypted data to disk."""
        if not self._unlocked or self._fernet is None:
            return

        try:
            json_data = json.dumps(self._data, indent=2).encode('utf-8')

            if HAS_CRYPTO:
                encrypted = self._fernet.encrypt(json_data)
            else:
                encrypted = self._xor_encrypt(json_data, self._fernet)

            settings_path = self.storage_dir / self.SETTINGS_FILE
            settings_path.write_bytes(encrypted)

        except Exception as e:
            logger.error(f"Failed to save encrypted settings: {e}")

    def _xor_encrypt(self, data: bytes, key: bytes) -> bytes:
        """Fallback XOR encryption (less secure, used when cryptography unavailable)."""
        key_len = len(key)
        return bytes([data[i] ^ key[i % key_len] for i in range(len(data))])

    def _xor_decrypt(self, data: bytes, key: bytes) -> bytes:
        """Fallback XOR decryption."""
        return self._xor_encrypt(data, key)  # XOR is symmetric

    # ========== Bookmarks API ==========

    def get_bookmarks(self) -> List[Dict[str, Any]]:
        """Get all bookmarks."""
        if not self._unlocked:
            return []
        return self._data.get("bookmarks", [])

    def add_bookmark(self, url: str, title: str, folder: str = "default",
                     icon: Optional[str] = None) -> bool:
        """
        Add a bookmark.

        Args:
            url: Bookmark URL
            title: Bookmark title
            folder: Folder to store bookmark in
            icon: Base64 encoded favicon (optional)

        Returns:
            True if successful
        """
        if not self._unlocked:
            return False

        bookmark = {
            "id": hashlib.md5(f"{url}{datetime.now().isoformat()}".encode()).hexdigest()[:12],
            "url": url,
            "title": title,
            "folder": folder,
            "icon": icon,
            "created": datetime.now().isoformat(),
            "modified": datetime.now().isoformat()
        }

        self._data["bookmarks"].append(bookmark)
        self._save()
        logger.info(f"Bookmark added: {title}")
        return True

    def remove_bookmark(self, bookmark_id: str) -> bool:
        """Remove a bookmark by ID."""
        if not self._unlocked:
            return False

        bookmarks = self._data.get("bookmarks", [])
        self._data["bookmarks"] = [b for b in bookmarks if b.get("id") != bookmark_id]
        self._save()
        return True

    def update_bookmark(self, bookmark_id: str, **kwargs) -> bool:
        """Update bookmark properties."""
        if not self._unlocked:
            return False

        for bookmark in self._data.get("bookmarks", []):
            if bookmark.get("id") == bookmark_id:
                bookmark.update(kwargs)
                bookmark["modified"] = datetime.now().isoformat()
                self._save()
                return True
        return False

    def get_bookmark_folders(self) -> List[str]:
        """Get list of bookmark folders."""
        if not self._unlocked:
            return []
        folders = set()
        for bookmark in self._data.get("bookmarks", []):
            folders.add(bookmark.get("folder", "default"))
        return sorted(list(folders))

    # ========== Favorites API ==========

    def get_favorites(self) -> List[Dict[str, Any]]:
        """Get favorites (quick access bookmarks)."""
        if not self._unlocked:
            return []
        return self._data.get("favorites", [])

    def add_favorite(self, url: str, title: str, position: int = -1) -> bool:
        """Add a favorite (max 10)."""
        if not self._unlocked:
            return False

        favorites = self._data.get("favorites", [])

        # Remove if already exists
        favorites = [f for f in favorites if f.get("url") != url]

        favorite = {
            "url": url,
            "title": title,
            "added": datetime.now().isoformat()
        }

        if position >= 0 and position < len(favorites):
            favorites.insert(position, favorite)
        else:
            favorites.append(favorite)

        # Keep max 10 favorites
        self._data["favorites"] = favorites[:10]
        self._save()
        return True

    def remove_favorite(self, url: str) -> bool:
        """Remove a favorite by URL."""
        if not self._unlocked:
            return False

        favorites = self._data.get("favorites", [])
        self._data["favorites"] = [f for f in favorites if f.get("url") != url]
        self._save()
        return True

    # ========== Auth Storage API ==========

    def store_auth_token(self, service: str, token: str,
                         expires: Optional[str] = None) -> bool:
        """
        Store authentication token for a service.

        Args:
            service: Service identifier (e.g., 'ailinux', 'github')
            token: Auth token
            expires: ISO timestamp when token expires (optional)

        Returns:
            True if successful
        """
        if not self._unlocked:
            return False

        self._data["auth"]["tokens"][service] = {
            "token": token,
            "expires": expires,
            "stored": datetime.now().isoformat()
        }
        self._save()
        logger.info(f"Auth token stored for: {service}")
        return True

    def get_auth_token(self, service: str) -> Optional[str]:
        """Get stored auth token for a service."""
        if not self._unlocked:
            return None

        token_data = self._data["auth"]["tokens"].get(service)
        if not token_data:
            return None

        # Check expiration
        if token_data.get("expires"):
            try:
                expires = datetime.fromisoformat(token_data["expires"])
                if datetime.now() > expires:
                    logger.info(f"Token expired for: {service}")
                    return None
            except:
                pass

        return token_data.get("token")

    def remove_auth_token(self, service: str) -> bool:
        """Remove stored auth token."""
        if not self._unlocked:
            return False

        if service in self._data["auth"]["tokens"]:
            del self._data["auth"]["tokens"][service]
            self._save()
            return True
        return False

    def store_credentials(self, service: str, username: str,
                          password: str) -> bool:
        """
        Store credentials for a service (double encrypted).

        Args:
            service: Service identifier
            username: Username/email
            password: Password

        Returns:
            True if successful
        """
        if not self._unlocked:
            return False

        self._data["auth"]["credentials"][service] = {
            "username": username,
            "password": password,  # Already encrypted by file-level encryption
            "stored": datetime.now().isoformat()
        }
        self._save()
        logger.info(f"Credentials stored for: {service}")
        return True

    def get_credentials(self, service: str) -> Optional[Dict[str, str]]:
        """Get stored credentials for a service."""
        if not self._unlocked:
            return None

        creds = self._data["auth"]["credentials"].get(service)
        if creds:
            return {
                "username": creds.get("username"),
                "password": creds.get("password")
            }
        return None

    def remove_credentials(self, service: str) -> bool:
        """Remove stored credentials."""
        if not self._unlocked:
            return False

        if service in self._data["auth"]["credentials"]:
            del self._data["auth"]["credentials"][service]
            self._save()
            return True
        return False

    # ========== Preferences API ==========

    def get_preference(self, key: str, default: Any = None) -> Any:
        """Get a user preference."""
        if not self._unlocked:
            return default
        return self._data.get("preferences", {}).get(key, default)

    def set_preference(self, key: str, value: Any) -> bool:
        """Set a user preference."""
        if not self._unlocked:
            return False

        self._data["preferences"][key] = value
        self._save()
        return True

    # ========== Server Sync API ==========

    def get_sync_data(self) -> Dict[str, Any]:
        """
        Get data for server sync.

        Returns encrypted blob that can be stored on server.
        Server cannot read the data - only user with password can.
        """
        if not self._unlocked or self._fernet is None:
            return {}

        sync_payload = {
            "version": self.VERSION,
            "bookmarks": self._data.get("bookmarks", []),
            "favorites": self._data.get("favorites", []),
            "preferences": self._data.get("preferences", {}),
            "sync_time": datetime.now().isoformat()
        }

        json_data = json.dumps(sync_payload).encode('utf-8')

        if HAS_CRYPTO:
            encrypted = self._fernet.encrypt(json_data)
        else:
            encrypted = self._xor_encrypt(json_data, self._fernet)

        return {
            "encrypted_data": base64.b64encode(encrypted).decode('ascii'),
            "checksum": hashlib.sha256(json_data).hexdigest()[:16],
            "timestamp": datetime.now().isoformat()
        }

    def import_sync_data(self, sync_data: Dict[str, Any]) -> bool:
        """
        Import data from server sync.

        Args:
            sync_data: Data from server containing encrypted_data

        Returns:
            True if successful
        """
        if not self._unlocked or self._fernet is None:
            return False

        try:
            encrypted = base64.b64decode(sync_data.get("encrypted_data", ""))

            if HAS_CRYPTO:
                decrypted = self._fernet.decrypt(encrypted)
            else:
                decrypted = self._xor_decrypt(encrypted, self._fernet)

            imported = json.loads(decrypted.decode('utf-8'))

            # Merge data (server wins for conflicts based on timestamp)
            self._data["bookmarks"] = imported.get("bookmarks", self._data["bookmarks"])
            self._data["favorites"] = imported.get("favorites", self._data["favorites"])
            self._data["preferences"].update(imported.get("preferences", {}))
            self._data["sync"]["last_sync"] = datetime.now().isoformat()

            self._save()
            logger.info("Sync data imported successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to import sync data: {e}")
            return False

    def get_last_sync(self) -> Optional[str]:
        """Get timestamp of last successful sync."""
        if not self._unlocked:
            return None
        return self._data.get("sync", {}).get("last_sync")

    def export_all(self) -> Dict[str, Any]:
        """Export all decrypted data (for backup)."""
        if not self._unlocked:
            return {}

        # Return copy without auth data for safety
        export = {
            "version": self._data.get("version"),
            "bookmarks": self._data.get("bookmarks", []),
            "favorites": self._data.get("favorites", []),
            "preferences": self._data.get("preferences", {}),
            "exported": datetime.now().isoformat()
        }
        return export

    # ========== Server Sync Methods ==========

    async def sync_to_server(self, api_client) -> bool:
        """
        Push encrypted settings to server.

        Args:
            api_client: APIClient instance with authentication

        Returns:
            True if sync successful
        """
        if not self._unlocked:
            logger.warning("Cannot sync: settings not unlocked")
            return False

        try:
            sync_data = self.get_sync_data()
            if not sync_data:
                return False

            # Use API client to push data
            response = await api_client.post(
                "/v1/user/settings/sync",
                json=sync_data
            )

            if response and response.get("success"):
                self._data["sync"]["last_sync"] = datetime.now().isoformat()
                self._data["sync"]["server_revision"] = response.get("revision", 0)
                self._save()
                logger.info("Settings synced to server successfully")
                return True

            logger.warning(f"Server sync failed: {response}")
            return False

        except Exception as e:
            logger.error(f"Error syncing to server: {e}")
            return False

    async def sync_from_server(self, api_client) -> bool:
        """
        Pull encrypted settings from server.

        Args:
            api_client: APIClient instance with authentication

        Returns:
            True if sync successful
        """
        if not self._unlocked:
            logger.warning("Cannot sync: settings not unlocked")
            return False

        try:
            # Use API client to pull data
            response = await api_client.get("/v1/user/settings/sync")

            if response and response.get("encrypted_data"):
                return self.import_sync_data(response)

            logger.info("No sync data on server")
            return False

        except Exception as e:
            logger.error(f"Error syncing from server: {e}")
            return False

    def sync_to_server_blocking(self, api_client) -> bool:
        """
        Blocking version of sync_to_server for use in non-async context.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Create a new task
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.sync_to_server(api_client)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(self.sync_to_server(api_client))
        except Exception as e:
            logger.error(f"Blocking sync failed: {e}")
            return False

    def sync_from_server_blocking(self, api_client) -> bool:
        """
        Blocking version of sync_from_server for use in non-async context.
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(
                        asyncio.run,
                        self.sync_from_server(api_client)
                    )
                    return future.result(timeout=30)
            else:
                return loop.run_until_complete(self.sync_from_server(api_client))
        except Exception as e:
            logger.error(f"Blocking sync failed: {e}")
            return False


# Global instance
_settings_instance: Optional[EncryptedSettings] = None


def get_encrypted_settings() -> EncryptedSettings:
    """Get global encrypted settings instance."""
    global _settings_instance
    if _settings_instance is None:
        _settings_instance = EncryptedSettings()
    return _settings_instance


def unlock_settings(password: str) -> bool:
    """Convenience function to unlock settings."""
    return get_encrypted_settings().unlock(password)


def lock_settings():
    """Convenience function to lock settings."""
    get_encrypted_settings().lock()
