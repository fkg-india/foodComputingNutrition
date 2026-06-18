"""
FastAPI application entrypoint.

Replaces the old two-service architecture (Flask + FastAPI proxy)
with a single unified FastAPI service.
"""

from fastapi import FastAPI

from backend.app.routers.nutrition import router as nutrition_router

app = FastAPI(
    title="Food Computing Nutrition API",
    description=(
        "Unified FastAPI service for dish nutrition calculation. "
        "Matches recipes via fuzzy search, converts units, scales nutrients, "
        "and falls back to the Nutritionix API for unknown ingredients."
    ),
    version="2.0.0",
)

app.include_router(nutrition_router)


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Food Computing Nutrition API",
        "version": "2.0.0",
    }


@app.get("/")
def root():
    """Root endpoint with API information."""
    return {
        "message": "Food Computing Nutrition API",
        "version": "2.0.0",
        "docs": "/docs",
        "endpoints": [
            "POST /api/v1/nutrition/dish",
            "POST /api/v1/nutrition/nutrition",
            "POST /api/v1/nutrition/ingredients",
            "POST /api/v1/nutrition/autocomplete",
            "POST /api/v1/nutrition/aggregate",
            "POST /api/v1/nutrition/ingredient-search",
            "POST /api/v1/nutrition/fetch",
            "POST /api/v1/nutrition/convert-to-grams",
            "GET /health",
        ],
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
