from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import asyncio
from typing import List, Dict, Any, Optional

app = FastAPI(
    title="Nutrition APIs",
    description="FastAPI frontend for nutrition calculation endpoints",
    version="1.0.0"
)

FLASK_BACKEND_URL = "http://localhost:5000"


# CLASSES 

class DishRequest(BaseModel):
    dish_name: str

class DishListRequest(BaseModel):
    dishes: List[str]

class NutritionResponse(BaseModel):
    matched_dish_name: str
    nutrition_per_serving: Dict[str, float]

class IngredientsResponse(BaseModel):
    matched_dish_name: str
    ingredients: Dict[str, str]

class MatchInfo(BaseModel):
    name: str
    score: float

class AggNutritionResponse(BaseModel):
    matched_dish_names: Dict[str, Optional[str]]
    nutrition_per_serving: Dict[str, float]
    skipped_dishes: List[str]

class AutocompleteResponse(BaseModel):
    input_dish_name: str
    matched_dish_name: str
    match_score: float
    top_matches: List[MatchInfo]

class ErrorResponse(BaseModel):
    error: str


# ENDPOINTS
@app.post("/api/nutrition", response_model=NutritionResponse)
async def get_nutrition(request: DishRequest):
    """
    Get nutrition information for a dish
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{FLASK_BACKEND_URL}/nutrition",
                json={"dish_name": request.dish_name},
                timeout=30.0
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=response.json()["error"])
            elif response.status_code != 200:
                raise HTTPException(status_code=500, detail="Backend service error")
                
            return response.json()
            
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Backend service unavailable")

@app.post("/api/ingredients", response_model=IngredientsResponse)
async def get_ingredients(request: DishRequest):
    """
    Get ingredient mapping for a dish
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{FLASK_BACKEND_URL}/ingredients",
                json={"dish_name": request.dish_name},
                timeout=30.0
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=response.json()["error"])
            elif response.status_code != 200:
                raise HTTPException(status_code=500, detail="Backend service error")
                
            return response.json()
            
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Backend service unavailable")

@app.post("/api/autocomplete", response_model=AutocompleteResponse)
async def autocomplete_dish(request: DishRequest):
    """
    Get dish name suggestions and matching scores
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{FLASK_BACKEND_URL}/autocomplete",
                json={"dish_name": request.dish_name},
                timeout=30.0
            )
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=response.json()["error"])
            elif response.status_code != 200:
                raise HTTPException(status_code=500, detail="Backend service error")
                
            return response.json()
            
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Backend service unavailable")

@app.post("/api/agg_nutrition", response_model=AggNutritionResponse)
async def get_aggregated_nutrition(request: DishListRequest):
    """
    Get aggregated nutrition information for multiple dishes
    """
    async with httpx.AsyncClient() as client:
        try:
            print(f"Forwarding request to Flask: {FLASK_BACKEND_URL}/agg_nutrition")
            response = await client.post(
                f"{FLASK_BACKEND_URL}/agg_nutrition",
                json={"dishes": request.dishes},
                timeout=60.0  # or maybe even longer
            )
            
            print(f"Flask response status: {response.status_code}")
            print(f"Flask response: {response.text}")
            
            if response.status_code == 404:
                raise HTTPException(status_code=404, detail=response.json()["error"])
            elif response.status_code != 200:
                raise HTTPException(status_code=500, detail=f"Backend service error: {response.text}")
                
            return response.json()
            
        except httpx.RequestError as e:
            print(f"Connection error to Flask backend: {e}")
            raise HTTPException(status_code=503, detail="Backend service unavailable")


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{FLASK_BACKEND_URL}/", timeout=5.0)
            backend_status = "healthy" if response.status_code in [200, 404] else "unhealthy"
        except:
            backend_status = "unhealthy"
    
    return {
        "status": "healthy",
        "backend_status": backend_status,
        "service": "FastAPI Frontend"
    }

@app.get("/")
async def root():
    """
    Root endpoint with API information
    """
    return {
        "message": "Nutrition Calculator API",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": [
            "POST /api/nutrition",
            "POST /api/ingredients", 
            "POST /api/autocomplete"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)