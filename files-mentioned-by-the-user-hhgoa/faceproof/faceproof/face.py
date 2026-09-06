from dataclasses import dataclass
import numpy as np

@dataclass
class ProbeResult:
    embedding: np.ndarray
    det_score: float
    bbox: list[float]
    blur_var: float

class FaceError(ValueError): pass

def _app():
    try:
        from insightface.app import FaceAnalysis
        app=FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640,640)); return app
    except ImportError as e: raise RuntimeError("InsightFace is required; run pip install -r requirements.txt") from e

def probe_image(image_path, config, app=None):
    import cv2
    image=cv2.imread(str(image_path))
    if image is None: raise FaceError("unreadable_image")
    faces=(app or _app()).get(image)
    if not faces: raise FaceError("no_face_detected")
    faces.sort(key=lambda f: (f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]), reverse=True)
    face=faces[0]; x1,y1,x2,y2=map(int, face.bbox); side=min(x2-x1,y2-y1)
    if float(face.det_score) < config.min_det_score: raise FaceError(f"low_detection_confidence:{face.det_score:.3f}")
    if side < config.min_face_px: raise FaceError(f"face_too_small:{side}px<{config.min_face_px}px")
    area=max(1,(x2-x1)*(y2-y1))
    if len(faces)>1:
        other=faces[1]; b=other.bbox; ratio=((b[2]-b[0])*(b[3]-b[1]))/area
        if ratio > config.max_secondary_face_ratio: raise FaceError(f"ambiguous_subject:{len(faces)}_faces_ratio_{ratio:.2f}")
    crop=image[max(0,y1):min(image.shape[0],y2), max(0,x1):min(image.shape[1],x2)]
    blur=float(cv2.Laplacian(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
    if blur < config.min_blur_var: raise FaceError(f"image_too_blurry:{blur:.1f}<{config.min_blur_var:.1f}")
    emb=np.asarray(face.embedding, dtype=np.float32); emb/=np.linalg.norm(emb)
    if emb.shape != (512,) or not np.isclose(np.linalg.norm(emb), 1, atol=1e-4): raise FaceError("invalid_arcface_embedding")
    return ProbeResult(emb, float(face.det_score), list(map(float,face.bbox)), blur)
