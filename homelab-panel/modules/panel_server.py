"""Validate the panel's small, explicit Waitress configuration before startup."""


def server_options(config=None):
    """Merge Pi-friendly defaults and reject typos/invalid values before workers run."""
    options = {
        "host": "0.0.0.0",
        "port": 5000,
        "threads": 2,
        "connection_limit": 32,
        "backlog": 64,
        "channel_timeout": 30,
        "cleanup_interval": 5,
    }
    if config is None:
        config = {}
    if not isinstance(config, dict):
        raise ValueError("WEB_SERVER_CONFIG must be a dictionary")
    unknown = config.keys() - options.keys()
    if unknown:
        raise ValueError("Unknown WEB_SERVER_CONFIG option(s): " + ", ".join(sorted(map(str, unknown))))
    options.update(config)
    if not isinstance(options["host"], str) or not options["host"].strip():
        raise ValueError("WEB_SERVER_CONFIG.host must be a nonempty address or hostname")
    options["host"] = options["host"].strip()
    for key in options.keys() - {"host"}:
        if type(options[key]) is not int or options[key] < 1:
            raise ValueError(f"WEB_SERVER_CONFIG.{key} must be a positive integer")
    if options["port"] > 65535:
        raise ValueError("WEB_SERVER_CONFIG.port must be between 1 and 65535")
    return options
