from dataclasses import dataclass, replace
import os, json
from pathlib import Path
from dotenv import load_dotenv

@dataclass(frozen=True)
class Config:
    model_id: str = "insightface/buffalo_l@w600k_r50"
    pipeline_version: str = "faceproof/1.0.0"
    schema_id: str = "faceproof.evidence.v1"
    min_det_score: float = 0.62
    min_face_px: int = 90
    min_blur_var: float = 45.0
    max_secondary_face_ratio: float = 0.60
    accept_at: float = 1.01  # safe until a measured calibration is present
    review_at: float = 0.42
    min_margin: float = 0.06
    top_k: int = 10
    phash_max_hamming: int = 10
    chain: str = "anvil"
    rpc_url: str = "http://127.0.0.1:8545"
    registry_address: str = ""
    private_key: str = ""
    serpapi_key: str = ""

    def public(self):
        return {**self.__dict__, "private_key": "[redacted]", "serpapi_key": "[redacted]"}

def load_config() -> Config:
    load_dotenv()
    cfg=Config(chain=os.getenv("CHAIN", "anvil"), rpc_url=os.getenv("RPC_URL", "http://127.0.0.1:8545"), registry_address=os.getenv("REGISTRY_ADDRESS", ""), private_key=os.getenv("PRIVATE_KEY", ""), serpapi_key=os.getenv("SERPAPI_KEY", ""))
    calibration=Path("data/calibration.json")
    if calibration.exists(): cfg=replace(cfg, accept_at=float(json.loads(calibration.read_text(encoding="utf-8"))["suggested_accept_at"]))
    return cfg
