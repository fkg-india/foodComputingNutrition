from pydantic import BaseModel
from typing import Any, Optional


class DishRequest(BaseModel):
    dish_name: str


class DishListRequest(BaseModel):
    dishes: list[str]


class FetchNutritionRequest(BaseModel):
    dish: str


class IngredientSearchRequest(BaseModel):
    ingredients: list[str]


class ConvertToGramsRequest(BaseModel):
    string_to_convert: str


class MatchInfo(BaseModel):
    name: str
    score: float


class ParsedData(BaseModel):
    quantity: float
    unit: str
    ingredient: str


class DishNutritionResponse(BaseModel):
    """Combined response for /dish endpoint — ingredients + nutrition."""
    matched_dish_name: Optional[str] = None
    ingredients: dict[str, str]
    nutrition_per_serving: dict[str, float]


class NutritionResponse(BaseModel):
    matched_dish_name: Optional[str] = None
    nutrition_per_serving: dict[str, float]


class IngredientsResponse(BaseModel):
    matched_dish_name: Optional[str] = None
    ingredients: dict[str, str]


class AutocompleteResponse(BaseModel):
    input_dish_name: str
    matched_dish_name: str
    match_score: float
    top_matches: list[MatchInfo]


class AggNutritionResponse(BaseModel):
    matched_dish_names: dict[str, Optional[str]]
    nutrition_per_serving: dict[str, float]
    skipped_dishes: list[str]


class IngredientSearchResponse(BaseModel):
    matched_ingredients: dict[str, str]


class FetchNutritionResponse(BaseModel):
    nutrition_data: dict[str, Any]


class ConvertToGramsResponse(BaseModel):
    original: str
    parsed: ParsedData
    grams: float
