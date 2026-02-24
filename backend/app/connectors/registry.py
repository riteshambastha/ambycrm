"""
Auto-discovering connector registry.

On startup, the registry scans all connector sub-packages and registers
any class that subclasses BaseConnector and has a `metadata` attribute.
To add a new connector, simply drop a new sub-package — no edits here.
"""

import importlib
import pkgutil
from pathlib import Path

from app.connectors.base import BaseConnector


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, type[BaseConnector]] = {}

    def register(self, connector_cls: type[BaseConnector]) -> None:
        key = connector_cls.metadata.key
        self._connectors[key] = connector_cls

    def get(self, key: str) -> type[BaseConnector] | None:
        return self._connectors.get(key)

    def get_instance(self, key: str) -> BaseConnector | None:
        cls = self.get(key)
        return cls() if cls else None

    def all_keys(self) -> list[str]:
        return list(self._connectors.keys())

    def all_connectors(self) -> list[type[BaseConnector]]:
        return list(self._connectors.values())

    def discover(self) -> None:
        """
        Walk the connectors package tree and import every module.
        Any BaseConnector subclass with a `metadata` attribute is auto-registered.
        """
        connectors_pkg_path = Path(__file__).parent
        self._walk_and_import("app.connectors", connectors_pkg_path)

    def _walk_and_import(self, pkg_name: str, pkg_path: Path) -> None:
        for finder, module_name, is_pkg in pkgutil.iter_modules([str(pkg_path)]):
            full_name = f"{pkg_name}.{module_name}"
            try:
                module = importlib.import_module(full_name)
            except ImportError:
                continue

            for attr_name in dir(module):
                obj = getattr(module, attr_name)
                if (
                    isinstance(obj, type)
                    and issubclass(obj, BaseConnector)
                    and obj is not BaseConnector
                    and hasattr(obj, "metadata")
                ):
                    self.register(obj)

            if is_pkg:
                sub_path = pkg_path / module_name
                self._walk_and_import(full_name, sub_path)


registry = ConnectorRegistry()
