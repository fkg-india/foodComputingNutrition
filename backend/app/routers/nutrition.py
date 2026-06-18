"""
Nutrition API router.

All 7 original endpoints ported from cal_new.py + fastapi_frontend.py,
mapped to /api/v1/nutrition/* paths.
"""

from fastapi import APIRouter, HTTPException

from backend.app.schemas import (
    AggNutritionResponse,
    AutocompleteResponse,
    ConvertToGramsRequest,
    ConvertToGramsResponse,
    DishListRequest,
    DishNutritionResponse,
    DishRequest,
    FetchNutritionRequest,
    FetchNutritionResponse,
    IngredientSearchRequest,
    IngredientSearchResponse,
    IngredientsResponse,
    NutritionResponse,
    ParsedData,
)
from backend.app.services.calculator import (
    calculate_nutrition_for_dish,
    clean_nan_values,
    convert_unit_to_grams,
    fetch_nutrition_for_dish,
    find_ingredient,
    get_ingredients,
    get_matching_dishes,
    match_recipe,
    parse_for_unit_conversion,
    recipes_df,
    save_nutrition_db,
)

router = APIRouter(prefix="/api/v1/nutrition", tags=["nutrition"])


@router.post("/dish", response_model=DishNutritionResponse)
def get_dish_nutrition(request: DishRequest):
    """Combined endpoint: fuzzy-match a dish, return its ingredients AND
    per-serving nutrition in one payload.

    Replaces the old /nutrition + /ingredients Flask endpoints.
    """
    dish_name = request.dish_name

    nutrition_info = calculate_nutrition_for_dish(dish_name)
    save_nutrition_db()

    if not nutrition_info:
        raise HTTPException(
            status_code=404,
            detail=f"No nutrition data found for dish: '{dish_name}'",
        )

    matched_name = match_recipe(dish_name, recipes_df)
    ingredients = get_ingredients(dish_name)

    return DishNutritionResponse(
        matched_dish_name=matched_name,
        ingredients=clean_nan_values(ingredients),
        nutrition_per_serving=clean_nan_values(nutrition_info),
    )


@router.post("/nutrition", response_model=NutritionResponse)
def get_nutrition_only(request: DishRequest):
    """Calculate per-serving nutrition for a dish (original /nutrition endpoint)."""
    dish_name = request.dish_name

    nutrition_info = calculate_nutrition_for_dish(dish_name)
    save_nutrition_db()

    if not nutrition_info:
        raise HTTPException(
            status_code=404,
            detail=f"No nutrition data found for dish: '{dish_name}'",
        )

    matched_name = match_recipe(dish_name, recipes_df)

    return NutritionResponse(
        matched_dish_name=matched_name,
        nutrition_per_serving=clean_nan_values(nutrition_info),
    )


@router.post("/ingredients", response_model=IngredientsResponse)
def get_dish_ingredients(request: DishRequest):
    """Get matched ingredient list for a dish (original /ingredients endpoint)."""
    dish_name = request.dish_name
    ingredients = get_ingredients(dish_name)

    if not ingredients:
        raise HTTPException(
            status_code=404,
            detail=f"No ingredient data found for dish: '{dish_name}'",
        )

    matched_name = match_recipe(dish_name, recipes_df)

    return IngredientsResponse(
        matched_dish_name=matched_name,
        ingredients=ingredients,
    )


@router.post("/autocomplete", response_model=AutocompleteResponse)
def autocomplete(request: DishRequest):
    """Return top 3 fuzzy-matched dish names with scores."""
    dish_name = request.dish_name
    matches = get_matching_dishes(dish_name, k=3, dishes_df=recipes_df)

    if not matches:
        raise HTTPException(
            status_code=404,
            detail=f"No close match found for dish: '{dish_name}'",
        )

    best_match = matches[0][0]

    return AutocompleteResponse(
        input_dish_name=dish_name,
        matched_dish_name=best_match,
        match_score=matches[0][1],
        top_matches=[{"name": name, "score": score} for name, score in matches],
    )


@router.post("/aggregate", response_model=AggNutritionResponse)
def aggregate_nutrition(request: DishListRequest):
    """Aggregate per-serving nutrition across multiple dishes."""
    dishes = request.dishes
    total_nutrition: dict[str, float] = {}
    skipped: list[str] = []

    for dish in dishes:
        nutrition_info = calculate_nutrition_for_dish(dish)
        save_nutrition_db()

        if not nutrition_info:
            skipped.append(dish)
        else:
            for key, val in nutrition_info.items():
                if key in total_nutrition:
                    total_nutrition[key] += val
                else:
                    total_nutrition[key] = val

    matched_dish_names = {dish: match_recipe(dish, recipes_df) for dish in dishes}

    return AggNutritionResponse(
        matched_dish_names=clean_nan_values(matched_dish_names),
        nutrition_per_serving=clean_nan_values(total_nutrition),
        skipped_dishes=skipped,
    )


@router.post("/ingredient-search", response_model=IngredientSearchResponse)
def search_ingredients(request: IngredientSearchRequest):
    """Match a list of raw ingredient names to the FCT database."""
    matched = {ing: find_ingredient(ing) for ing in request.ingredients}
    return IngredientSearchResponse(matched_ingredients=matched)


@router.post("/fetch", response_model=FetchNutritionResponse)
def fetch_nutrition(request: FetchNutritionRequest):
    """Fetch precalculated per-100g nutrition from master sheet."""
    result = fetch_nutrition_for_dish(request.dish)

    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No precalculated nutrition found for dish: '{request.dish}'",
        )

    return FetchNutritionResponse(nutrition_data=clean_nan_values(result))


@router.post("/convert-to-grams", response_model=ConvertToGramsResponse)
def convert_to_grams(request: ConvertToGramsRequest):
    """Parse a natural-language quantity string and convert to grams."""
    parsed = parse_for_unit_conversion(request.string_to_convert)
    if not parsed:
        raise HTTPException(status_code=400, detail="Parsing failed")

    number, unit, ingredient = parsed
    conversion = convert_unit_to_grams(number, unit, ingredient)

    if not conversion:
        raise HTTPException(
            status_code=400,
            detail=f"Conversion failed, no '{unit}' in DB",
        )

    return ConvertToGramsResponse(
        original=request.string_to_convert,
        parsed=ParsedData(quantity=number, unit=unit, ingredient=ingredient),
        grams=conversion,
    )
