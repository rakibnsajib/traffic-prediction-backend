from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router


app = FastAPI(
    title="AI Traffic Prediction and Optimal Route API",
    version="1.0.0",
    description="Backend API for AI-based traffic prediction and route optimization.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
def health_check() -> dict:
    return {"status": "ok", "service": "traffic-prediction-backend"}

