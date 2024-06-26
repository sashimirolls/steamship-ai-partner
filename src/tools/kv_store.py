"""A simple key-value store implemented atop Files and Tags."""

from typing import Any, Dict, List, Optional, Tuple

from steamship import Block, File, Steamship, Tag
from tools.tag_utils import get_tag, get_tag_value_key  # Assuming tag_utils is at the same level as kv_store

KV_STORE_MARKER = "__init__"


class KeyValueStore:
    """A simple key value store implemented in Steamship.

    Instances of the KeyValueStore are identified by its  `namespace`.
    This store_identifier corresponds to a File that will be created with a special tag identifying it.

    Entries of the KeyValueStore are saved as `Tag` objects with:
      * Kind = "KeyValueStore"
      * Name = the key of the (kv) pair
      * Value = a dict set to the value

    Note that the value is always saved as a dict object. To save a string or int, wrap it in a dict.

    WARNING:

    This is essentially a clever hack atop Steamship's tag system to provide mutable key-value storage. It is in the
    steamship.utils package because it's proven useful once or twice. But in general, if you find yourself heavily
    relying upon it, consider reaching out to us at hello@steamship.com to let us know, and we'll up-prioritize
    adding a proper key-value API.
    """

    client: Steamship
    store_identifier: str

    def __init__(self,
                 client: Steamship,
                 store_identifier: str = "KeyValueStore"):
        """Create a new KeyValueStore instance.

        Args:
            client (Steamship): The Steamship client.
            store_identifier (str): The store_identifier which identifies this KeyValueStore instance. You can have multiple, separate KeyValueStore instances in a workspace using this implementation.
        """
        self.client = client
        self.store_identifier = f"kv-store-{store_identifier}"
        self.cache = {}  # Initialize an empty cache

    def _get_file(self, or_create: bool = False) -> Optional[File]:
        status_files = File.query(
            self.client, f'filetag and kind "{self.store_identifier}"').files
        if len(status_files) == 0:
            if not or_create:
                return None
            return File.create(
                self.client,
                blocks=[Block(text="")],
                tags=[Tag(kind=self.store_identifier, name=KV_STORE_MARKER)],
            )
        else:
            return status_files[0]

    def get(self, key: str) -> Optional[Dict]:
        """Get the value represented by `key`."""
        if key in self.cache:
            return self.cache[key]
        file = self._get_file()
        if file is None:
            return None
        tag = get_tag(file.tags, kind=self.store_identifier, name=key)
        if tag:
            self.cache[key] = tag.value  # Update cache with newly retrieved value
            return tag.value
        return None  # Key not found

    def delete(self, key: str) -> bool:
        """Delete the entry represented by `key`"""
        file = self._get_file()
        if file is None:
            return False
        tag = get_tag(file.tags, kind=self.store_identifier, name=key)
        if tag:
            tag.delete()
            del self.cache[key]  # Invalidate cache for the deleted key
            return True
        return False

    def set(self, key: str, value: Dict[str, Any]):
        """Set the entry (key, value)."""
        # First delete it if it exists to avoid duplicate tags.
        self.delete(key)
        # Now get/create the file
        file = self._get_file(or_create=True)
        req = Tag(file_id=file.id,
                  kind=self.store_identifier,
                  name=key,
                  value=value)
        created_tag = self.client.post("tag/create", req, expect=Tag)
        self.cache[key] = value  # Update the cache with the new value
        return created_tag

    def items(
        self,
        filter_keys: Optional[List[str]] = None
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Return all key-value entries as a list of (key, value) tuples.

        If `filter_keys` is provided, only returns keys within that list."""

        file = self._get_file(or_create=True)
        return [(tag.name, tag.value) for tag in file.tags if (
                tag.kind == self.store_identifier and tag.name != KV_STORE_MARKER
                and (filter_keys is None or tag.name in filter_keys))]

    def reset(self):
        """Delete all key-values."""
        file = self._get_file()
        if file is not None:
            file.delete()
