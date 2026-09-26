#!/usr/bin/env python3
"""Standalone adapter for the shared one-shot MQTT CLI."""

import sys

from shared_modules.mqtt import _publish_once, cli_main as main, publish_message


if __name__ == "__main__":
    sys.exit(main())
