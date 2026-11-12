"""Deployment settings shared by the web process and local manager."""
import os
from pathlib import Path

DATA_DIR = Path(os.getenv('PANEL_DATA_DIR', '/var/lib/mihomo-panel'))
MANAGER_STATE = Path(os.getenv('MANAGER_STATE_DIR', '/var/lib/mihomo-panel-manager'))
MANAGER_SOCKET = os.getenv('MANAGER_SOCKET', '/run/mihomo-panel-manager/manager.sock')
MIHOMO_BIN = os.getenv('MIHOMO_BIN', '/opt/mihomo-panel/core/mihomo')
CONFIG_DIR = Path(os.getenv('MIHOMO_CONFIG_DIR', '/etc/mihomo'))
INSTANCE_DATA = Path(os.getenv('MIHOMO_DATA_DIR', '/var/lib'))
UNIT_DIR = Path(os.getenv('SYSTEMD_UNIT_DIR', '/etc/systemd/system'))
