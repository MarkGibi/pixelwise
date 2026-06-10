import os

import numpy as np
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from slowapi import Limiter
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.classifier import classify_batch

load_dotenv()

SECRET_API_KEY = os.getenv("SECRET_API_KEY")


class ClassifyRequest(BaseModel):
    pixels: list[list[int]]


class ClassifyResponse(BaseModel):
    prediction: str
    confidence: float
    scores: dict[str, float]


def require_api_key(x_api_key: str | None = Header(default=None)):
    if not SECRET_API_KEY:
        raise HTTPException(status_code=500, detail="API key not configured")
    if x_api_key != SECRET_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


limiter = Limiter(key_func=get_remote_address)

app = FastAPI(title="PixelWise API")
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.get("/health")
def health():
    return {"status": "ok", "model_version": "v1"}


@app.get("/results")
def results():
    return {"results": [], "note": "persistence not yet implemented"}


@app.post(
    "/classify",
    response_model=ClassifyResponse,
    dependencies=[Depends(require_api_key)],
)
@limiter.limit("10/minute")
def classify(request: Request, req: ClassifyRequest):
    arr = np.array(req.pixels, dtype=np.uint8)[np.newaxis]
    return classify_batch(arr)[0]
