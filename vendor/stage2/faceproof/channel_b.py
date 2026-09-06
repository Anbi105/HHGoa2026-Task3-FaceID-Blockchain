def discover(*_, **__):
    """Network reverse search is deliberately opt-in; no full probe image is sent."""
    return {"accepted":False, "reason":"no_SERPAPI_KEY_or_ephemeral_host"}
