"""MCP server auto-configuration for IDEs."""

from __future__ import annotations

import json
from pathlib import Path


class MCPConfigError(Exception):
    """MCP configuration error."""

    pass


class CursorMCPInstaller:
    """Auto-configure Synapse MCP in Cursor settings.json."""

    @staticmethod
    def config_path() -> Path:
        """Return path to Cursor settings.json."""
        cursor_settings = Path.home() / ".cursor" / "settings" / "settings.json"
        if cursor_settings.exists():
            return cursor_settings

        # Alternative path for newer Cursor versions
        cursor_settings = Path.home() / "Library" / "Application Support" / "Cursor" / "User"
        if cursor_settings.exists():
            settings_file = cursor_settings / "settings.json"
            if settings_file.exists():
                return settings_file
            raise MCPConfigError(
                "Cursor settings.json not found. "
                "Please ensure Cursor is installed and configured."
            )

        raise MCPConfigError("Cursor configuration directory not found.")

    @staticmethod
    def install(synapse_mcp_command: str) -> tuple[str, bool]:
        """Install Synapse MCP in Cursor.

        Args:
            synapse_mcp_command: Full command to run synapse MCP server.

        Returns:
            (config_path, success) tuple.
        """
        config_path = CursorMCPInstaller.config_path()

        # Read existing config
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            config = {}

        # Backup original
        backup_path = config_path.with_suffix(".json.backup")
        if not backup_path.exists():
            backup_path.write_text(config_path.read_text() if config_path.exists() else "{}")

        # Add/update MCP server config
        if "mcp" not in config:
            config["mcp"] = {}
        if "mcpServers" not in config["mcp"]:
            config["mcp"]["mcpServers"] = {}

        config["mcp"]["mcpServers"]["synapse"] = {
            "command": synapse_mcp_command,
            "autoConnect": True,
        }

        # Write back
        config_path.write_text(json.dumps(config, indent=2))

        return str(config_path), True


class ClaudeMCPInstaller:
    """Auto-configure Synapse MCP in Claude Desktop."""

    @staticmethod
    def config_path() -> Path:
        """Return path to Claude config.json."""
        config_path = Path.home() / ".claude" / "config.json"
        if not config_path.exists():
            raise MCPConfigError(
                f"Claude Desktop config not found at {config_path}. "
                "Please ensure Claude Desktop is installed and configured."
            )
        return config_path

    @staticmethod
    def install(synapse_mcp_command: str) -> tuple[str, bool]:
        """Install Synapse MCP in Claude Desktop.

        Args:
            synapse_mcp_command: Full command to run synapse MCP server.

        Returns:
            (config_path, success) tuple.
        """
        config_path = ClaudeMCPInstaller.config_path()

        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            config = {}

        # Backup original
        backup_path = config_path.with_suffix(".json.backup")
        if not backup_path.exists():
            backup_path.write_text(config_path.read_text() if config_path.exists() else "{}")

        # Add/update MCP server config
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["synapse"] = {
            "command": synapse_mcp_command,
        }

        # Write back
        config_path.write_text(json.dumps(config, indent=2))

        return str(config_path), True


class RooMCPInstaller:
    """Auto-configure Synapse MCP in Roo."""

    @staticmethod
    def config_path() -> Path:
        """Return path to Roo config."""
        config_path = Path.home() / ".roo" / "config.json"
        if not config_path.exists():
            raise MCPConfigError(
                f"Roo config not found at {config_path}. "
                "Please ensure Roo is installed and configured."
            )
        return config_path

    @staticmethod
    def install(synapse_mcp_command: str) -> tuple[str, bool]:
        """Install Synapse MCP in Roo.

        Args:
            synapse_mcp_command: Full command to run synapse MCP server.

        Returns:
            (config_path, success) tuple.
        """
        config_path = RooMCPInstaller.config_path()

        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            config = {}

        # Backup original
        backup_path = config_path.with_suffix(".json.backup")
        if not backup_path.exists():
            backup_path.write_text(config_path.read_text() if config_path.exists() else "{}")

        # Add/update MCP server config
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["synapse"] = {
            "command": synapse_mcp_command,
        }

        # Write back
        config_path.write_text(json.dumps(config, indent=2))

        return str(config_path), True


class ClineMCPInstaller:
    """Auto-configure Synapse MCP in Cline."""

    @staticmethod
    def config_path() -> Path:
        """Return path to Cline config."""
        config_path = Path.home() / ".cline" / "config.json"
        if not config_path.exists():
            raise MCPConfigError(
                f"Cline config not found at {config_path}. "
                "Please ensure Cline extension is installed and configured."
            )
        return config_path

    @staticmethod
    def install(synapse_mcp_command: str) -> tuple[str, bool]:
        """Install Synapse MCP in Cline.

        Args:
            synapse_mcp_command: Full command to run synapse MCP server.

        Returns:
            (config_path, success) tuple.
        """
        config_path = ClineMCPInstaller.config_path()

        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            config = {}

        # Backup original
        backup_path = config_path.with_suffix(".json.backup")
        if not backup_path.exists():
            backup_path.write_text(config_path.read_text() if config_path.exists() else "{}")

        # Add/update MCP server config
        if "mcpServers" not in config:
            config["mcpServers"] = {}

        config["mcpServers"]["synapse"] = {
            "command": synapse_mcp_command,
        }

        # Write back
        config_path.write_text(json.dumps(config, indent=2))

        return str(config_path), True


def get_mcp_installers() -> dict[str, type]:
    """Return mapping of IDE name to installer class."""
    return {
        "cursor": CursorMCPInstaller,
        "claude": ClaudeMCPInstaller,
        "roo": RooMCPInstaller,
        "cline": ClineMCPInstaller,
    }
