def fuse(channel_a, channel_b):
    a=channel_a.get("accepted", False); b=channel_b.get("accepted", False)
    if a and b and (channel_a.get("image_sha256") == channel_b.get("image_sha256") or channel_a.get("post_uri") == channel_b.get("post_uri")):
        return {"outcome":"CORROBORATED", "a":channel_a, "b":channel_b}
    if a: return {"outcome":"SINGLE_CHANNEL_A", "a":channel_a}
    if b: return {"outcome":"SINGLE_CHANNEL_B", "b":channel_b}
    return {"outcome":"ABSTAIN"}
