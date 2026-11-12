import hashlib, json
def content_hash8(line: str) -> str:
    return hashlib.sha256(line.replace("\r\n","\n").rstrip("\n").encode()).hexdigest()[:8]
def surface_hash(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
