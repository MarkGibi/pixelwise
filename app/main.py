import os

import numpy as np
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.classifier import classify_batch
from app.models import Prediction, SessionLocal

load_dotenv()

SECRET_API_KEY = os.getenv("SECRET_API_KEY")
CLASSIFY_RATE_LIMIT = os.getenv("CLASSIFY_RATE_LIMIT", "1000/minute")
BATCH_RATE_LIMIT = os.getenv("BATCH_RATE_LIMIT", "1000/minute")


class ClassifyRequest(BaseModel):
    pixels: list[list[int]]


class BatchClassifyRequest(BaseModel):
    images: list[list[list[int]]]


class ClassifyResponse(BaseModel):
    prediction: str
    confidence: float
    scores: dict[str, float]


class BatchClassifyResponse(BaseModel):
    results: list[ClassifyResponse]
    count: int


def require_api_key(x_api_key: str | None = Header(default=None)):
    if not SECRET_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key != SECRET_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def save_predictions(results: list[dict]):
    db = SessionLocal()
    try:
        db.add_all(
            [
                Prediction(
                    prediction=result["prediction"],
                    confidence=result["confidence"],
                    model_version="v1",
                )
                for result in results
            ]
        )
        db.commit()
    finally:
        db.close()


def to_image_array(pixels: list[list[int]]) -> np.ndarray:
    arr = np.array(pixels, dtype=np.uint8)
    if arr.shape != (28, 28):
        raise HTTPException(
            status_code=400,
            detail=f"Expected image shape 28x28, got {arr.shape}",
        )
    return arr


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="PixelWise API")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.get("/health")
def health():
    return {"status": "ok", "model_version": "v1"}


@app.get("/results")
def results():
    db = SessionLocal()
    try:
        rows = (
            db.query(Prediction)
            .order_by(Prediction.created_at.desc())
            .limit(20)
            .all()
        )

        return {
            "results": [
                {
                    "id": r.id,
                    "prediction": r.prediction,
                    "confidence": r.confidence,
                    "model_version": r.model_version,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@app.post(
    "/classify",
    response_model=ClassifyResponse,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(CLASSIFY_RATE_LIMIT)
def classify(request: Request, req: ClassifyRequest):
    image = to_image_array(req.pixels)
    result = classify_batch(image[np.newaxis])[0]

    save_predictions([result])

    return result


@app.post(
    "/classify/batch",
    response_model=BatchClassifyResponse,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit(BATCH_RATE_LIMIT)
def classify_batch_endpoint(request: Request, req: BatchClassifyRequest):
    if not req.images:
        raise HTTPException(status_code=400, detail="No images provided")

    images = np.stack([to_image_array(image) for image in req.images])
    results = classify_batch(images)

    save_predictions(results)

    return {"results": results, "count": len(results)}
