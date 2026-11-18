"""G0 liveness only. Liveness is not evidence of inference or data readiness."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from sovereign_ops import __version__


class LivenessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["alive"] = "alive"
    stage: Literal["G0"] = "G0"
    mode: Literal["RESEARCH_ONLY"] = "RESEARCH_ONLY"
    inference: Literal["NOT_IMPLEMENTED"] = "NOT_IMPLEMENTED"


def create_app() -> FastAPI:
    application = FastAPI(
        title="ShockBridge Sovereign Ops",
        version=__version__,
        description=(
            "G0 foundation. No data ingestion, inference, or live infrastructure connection."
        ),
        docs_url=None,
        redoc_url=None,
    )

    @application.get("/health/live", response_model=LivenessResponse, tags=["health"])
    def liveness() -> LivenessResponse:
        return LivenessResponse()

    return application


app = create_app()
