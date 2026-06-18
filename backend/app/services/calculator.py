"""
Nutrition calculator service.

Ported from cal_new.py (Flask). Contains all business logic:
- Dataset loading (recipes, FCT, units, precalculated)
- Fuzzy matching (dishes, ingredients)
- Unit conversions
- Nutritionix API fallback
- Nutrition calculation and aggregation
"""

import math
import os
import re
from pathlib import Path

import pandas as pd
import requests
from rapidfuzz import fuzz, process
from word2number import w2n

# ---------------------------------------------------------------------------
# Data file resolution
# Data files live in the project root (foodComputingNutrition/), two levels
# above this file (backend/app/services/calculator.py).
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parents[3]

RECIPES_PATH = DATA_DIR / "recipes.pkl"
UNITS_PATH = DATA_DIR / "units.xlsx"
INGREDIENTS_PATH = DATA_DIR / "fct.xlsx"
PRECALCULATED_PATH = DATA_DIR / "master_dishes_nutrition_per_100g.xlsx"

# ---------------------------------------------------------------------------
# Load datasets at module level (once on import / server startup)
# ---------------------------------------------------------------------------
recipes_df = pd.read_pickle(RECIPES_PATH)
nutrition_df = pd.read_excel(INGREDIENTS_PATH)
precalculated_df = pd.read_excel(PRECALCULATED_PATH)

_raw_units_df = pd.read_excel(UNITS_PATH)


def _convert_units_df(df: pd.DataFrame) -> pd.DataFrame:
    """Expand comma-separated unit/alt_names/associated_ingredient columns
    into Python lists, merge unit + alt_names, drop alt_names."""
    df = df.copy()
    text_to_list_cols = ["unit", "alt_names", "associated_ingredient"]
    for col in text_to_list_cols:
        if col in df.columns:
            df[col] = (
                df[col]
                .fillna("")
                .apply(lambda x: [item.strip() for item in x.split(",") if item.strip()])
            )
    df["unit"] = df["unit"] + df["alt_names"]
    df = df.drop(columns=["alt_names"])
    return df


units_df = _convert_units_df(_raw_units_df)

# Columns to exclude from nutrient dictionaries
_DROP_COLS = [
    "#",
    "Food Name; name",
    "Alternate Name; alt_name",
    "Local Name; lang",
    "food_code",
    "food_group_nin",
    "primarysource",
]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def clean_nan_values(obj: object) -> object:
    """Recursively replace NaN floats with 0.0 in dicts/lists."""
    if isinstance(obj, dict):
        return {key: clean_nan_values(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return 0.0
    return obj


def normalize(text: str) -> str:
    """Remove special characters, lowercase, collapse whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", str(text).lower())).strip()


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------
def smart_score(query: str, choice: str, **kwargs) -> float:  # noqa: ARG001
    """Best-of-four rapidfuzz scoring strategies."""
    return max(
        fuzz.ratio(query, choice),
        fuzz.token_sort_ratio(query, choice),
        fuzz.token_set_ratio(query, choice),
        fuzz.partial_ratio(query, choice),
    )


def match_recipe(dish_name: str, dishes_df: pd.DataFrame = recipes_df) -> str | None:
    """Fuzzy-match *dish_name* against the recipe database.
    Returns the best match name or None if score < 75."""
    recipe_names = list(dishes_df["name"])
    best_match, score, _ = process.extractOne(dish_name, recipe_names, scorer=smart_score)
    if score < 75:
        print(f"Found no matching dish for {dish_name} in database. Closest match is {best_match}")
        return None
    print(f"Found matching recipe: '{best_match}' with score {score}")
    return best_match


def match_from_precalculated(
    dish_name: str, df: pd.DataFrame = precalculated_df
) -> str | None:
    """Fuzzy-match *dish_name* against the precalculated nutrition table."""
    recipe_names = list(df["Food Name; name"])
    best_match, score, _ = process.extractOne(dish_name, recipe_names, scorer=smart_score)
    if score < 75:
        print(f"Found no matching dish for {dish_name} in database. Closest match is {best_match}")
        return None
    print(f"Found matching recipe: '{best_match}' with score {score}")
    return best_match


def get_matching_dishes(
    dish_name: str, k: int = 2, dishes_df: pd.DataFrame = recipes_df
) -> list[tuple[str, float]]:
    """Return up to *k* closest dish-name matches with score >= 75."""
    recipe_names = list(dishes_df["name"])
    matches = process.extract(dish_name, recipe_names, scorer=smart_score, limit=k)
    filtered = [(name, score) for name, score, _ in matches if score >= 75]
    if not filtered:
        print(
            f"No good match found for '{dish_name}'. "
            f"Closest was: {matches[0][0]} (score: {matches[0][1]})"
        )
        return []
    return filtered


# ---------------------------------------------------------------------------
# Ingredient matching
# ---------------------------------------------------------------------------
def find_ingredient(name: str, ndf: pd.DataFrame = nutrition_df) -> str:
    """Match a raw ingredient name to the FCT database.
    Returns the canonical Food Name or 'NA' if not found."""
    ndf["Alternate Name; alt_name"] = ndf["Alternate Name; alt_name"].fillna("").astype(str)

    original_clean = normalize(name)
    name_lookup = dict(
        zip(
            [normalize(n) for n in ndf["Food Name; name"]],
            ndf["Food Name; name"],
        )
    )

    # 1. Fuzzy match against normalized Food_Name
    match = process.extractOne(
        original_clean, list(name_lookup.keys()), scorer=fuzz.token_sort_ratio
    )
    if match and match[1] >= 80:
        return name_lookup[match[0]]

    # 2. Fallback: substring search in Alternate Name
    alt_match_row = ndf[
        ndf["Alternate Name; alt_name"]
        .str.lower()
        .str.contains(name.strip().lower(), regex=False)
    ]
    if not alt_match_row.empty:
        return alt_match_row.iloc[0]["Food Name; name"]

    return "NA"


def get_matched_ingredient(
    dish_name: str,
    dishes_df: pd.DataFrame,
    ndf: pd.DataFrame = nutrition_df,
) -> dict[str, str]:
    """Return {raw_ingredient: matched_fct_name} for all ingredients of a dish."""
    dish_row = dishes_df.loc[dishes_df["name"] == dish_name]
    ing_matched: dict[str, str] = {}
    for ingredient_list in dish_row["ingredients"]:
        for i in ingredient_list:
            ing_matched[i] = find_ingredient(i, ndf)
    return ing_matched


# ---------------------------------------------------------------------------
# Unit conversion
# ---------------------------------------------------------------------------
def convert_unit(
    unit: str, ingredient: str, udf: pd.DataFrame = units_df
) -> float | None:
    """Convert a unit to grams. Prefers ingredient-specific conversion,
    falls back to generic."""
    unit_rows = udf[udf["unit"].apply(lambda lst: unit in lst)]
    if unit_rows.empty:
        return None

    general_conversion = None
    for _, row in unit_rows.iterrows():
        if (
            ingredient
            and row["associated_ingredient"]
            and ingredient in row["associated_ingredient"]
        ):
            return row["value"]
        if not row["associated_ingredient"]:
            general_conversion = row["value"]

    return general_conversion


def convert_unit_to_grams(
    number: float, unit: str, ingredient: str
) -> float | None:
    """Multiply quantity by per-unit gram weight."""
    base = convert_unit(unit, ingredient)
    if base:
        return float(number) * base
    return None


# ---------------------------------------------------------------------------
# Natural-language quantity parsing
# ---------------------------------------------------------------------------
def parse_for_unit_conversion(line: str) -> tuple[float, str, str] | None:
    """Parse a string like '1.5 cups flour' into (quantity, unit, ingredient)."""
    original_line = line.strip()
    line = original_line

    fraction_patterns = [
        (r"^(one and a half|one and one half)", 1.5),
        (r"^(two and a half|two and one half)", 2.5),
        (r"^(three and a half|three and one half)", 3.5),
        (r"^(a half|half)", 0.5),
        (r"^(a quarter|quarter)", 0.25),
        (r"^(three quarters|three-quarters)", 0.75),
        (r"^(one third|a third)", 0.33),
        (r"^(two thirds)", 0.67),
    ]

    matched_fraction = False
    for pattern, value in fraction_patterns:
        match = re.match(pattern, line.lower())
        if match:
            original_match = re.match(pattern, original_line, re.IGNORECASE)
            if original_match:
                line = original_line.replace(original_match.group(1), str(value), 1)
                matched_fraction = True
                break

    if not matched_fraction:
        word_number_pattern = re.match(
            r"^([a-zA-Z]+(?:\s+[a-zA-Z]+)*?)\s+(?=\w+)", original_line
        )
        if word_number_pattern:
            word_number = word_number_pattern.group(1).strip()
            try:
                quantity = w2n.word_to_num(word_number)
                line = re.sub(
                    r"^" + re.escape(word_number), str(quantity), original_line, count=1
                )
            except ValueError:
                pass

    # Extract numeric quantity + unit + ingredient
    match = re.match(r"(?P<number>\d+(?:\.\d+)?)\s*(?P<unit>\w+)\s+(?P<ingredient>.+)", line)
    if match:
        def singularize(u: str) -> str:
            return u[:-1] if u.endswith("s") else u

        number = float(match.group("number"))
        unit = singularize(match.group("unit").lower())
        ingredient = match.group("ingredient").strip()
        return (number, unit, ingredient)

    # Fallback: number + ingredient (no unit → "count")
    match = re.match(r"(?P<number>\d+(?:\.\d+)?)\s+(?P<ingredient>.+)", line)
    if match:
        number = float(match.group("number"))
        ingredient = match.group("ingredient").strip()
        return (number, "count", ingredient)

    return None


# ---------------------------------------------------------------------------
# Nutritionix API fallback
# ---------------------------------------------------------------------------
_NUTRITIONIX_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"
_NUTRITIONIX_HEADERS = {
    "Content-Type": "application/json",
    "x-app-id": "d4440f54",
    "x-app-key": "03a9f800ce93eb67f07224633b953ee9",
}

_NUTRIENT_MAP = {
    208: "Energy; enerc",
    204: "Total Fat; fatce",
    606: "Saturated Fatty acids; fasat",
    307: "Sodium (Na); na",
    306: "Potassium (K); k",
    205: "Carbohydrate; choavldf",
    291: "Dietary Fiber; fibtg",
    269: "Free Sugars; fsugar",
    203: "Protein; protcnt",
    318: "Vitamin A; vita",
    401: "Ascorbic acids (C); vitc",
    301: "Calcium (Ca); ca",
    303: "Iron (Fe); fe",
    309: "Zinc (Zn); zn",
    324: "Vitamin D; vitd",
    404: "Thiamine (B1); thia",
    405: "Riboflavin (B2); ribf",
    406: "Niacin (B3); nia",
    417: "Folates (B9); folsum",
    601: "Cholesterol; cholc",
    305: "Phosphorus (P); p",
    304: "Magnesium (Mg); mg",
    317: "Selenium (Se); se",
    312: "Copper (Cu); cu",
    338: "Carotenoids; cartoid",
    410: "Pantothenic acid (B5); pantac",
    430: "Vitamin K; vitk",
    415: "Total B6; vitb6c",
    323: "Tocopherol equivalent (E); vite",
    605: "Trans Fatty acids; fatrn",
    618: "Essential Fatty acids; faess",
    645: "Monounsaturated Fatty acids; fams",
    646: "Polyunsaturated Fatty acids; fapu",
    255: "Moisture; water",
    315: "Manganese (Mn); mn",
}

_MG_IDS = {307, 306, 401, 301, 303, 309, 404, 405, 406, 415, 601, 305, 304, 312, 410, 323, 315}
_MCG_IDS = {318, 417, 317, 338, 430}
_IU_IDS = {318, 324}
_IU_CONVERSION = {
    318: 0.0000003,   # Vitamin A
    324: 0.000000025,  # Vitamin D
}


def nutritionix(ingredient: str) -> dict | None:
    """Fetch per-100g nutrient data from the Nutritionix API."""
    try:
        response = requests.post(
            _NUTRITIONIX_URL,
            headers=_NUTRITIONIX_HEADERS,
            json={"query": ingredient},
            timeout=15,
        )
        if response.status_code != 200:
            print(
                f"Nutritionix request failed for '{ingredient}' "
                f"with status {response.status_code}"
            )
            return None
        data = response.json()
        if not data.get("foods"):
            print(f"Nutritionix found no results for '{ingredient}'.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error calling Nutritionix for '{ingredient}': {e}")
        return None

    food_data = data["foods"][0]
    print(f"Made a nutritionix call for {ingredient}")

    food_matched_name = food_data.get("food_name")
    food_serving_weight = food_data.get("serving_weight_grams")
    food_nutrients = food_data.get("full_nutrients", [])

    if not food_serving_weight:
        return None

    result: dict = {
        "Food Name; name": food_matched_name,
        "Alternate Name; alt_name": ingredient if food_matched_name != ingredient else "",
        "primarysource": "nutritionix_FKG",
    }

    for item in food_nutrients:
        attr_id = item["attr_id"]
        if attr_id in _NUTRIENT_MAP:
            value = item.get("value", 0)
            value_per_100g = (value / food_serving_weight) * 100
            if attr_id in _MG_IDS:
                value_per_100g /= 1000
            if attr_id in _MCG_IDS:
                value_per_100g /= 1000000
            if attr_id in _IU_IDS:
                value_per_100g *= _IU_CONVERSION[attr_id]
            result[_NUTRIENT_MAP[attr_id]] = value_per_100g

    return result


# ---------------------------------------------------------------------------
# Nutrition calculation
# ---------------------------------------------------------------------------
def _add_to_nutrition(
    nutrition_dict: dict[str, float], add_dict: dict[str, float]
) -> dict[str, float]:
    """Accumulate nutrient values into *nutrition_dict* in-place."""
    for name, val in add_dict.items():
        if name in nutrition_dict:
            nutrition_dict[name] += float(val)
    return nutrition_dict


def _scale_values(scale: float, d: dict) -> dict:
    """Multiply every value in *d* by *scale* in-place and return it."""
    for key in d:
        d[key] *= scale
    return d


def calculate_nutrition(
    matched_dict: dict[str, str],
    dish_name: str,
    dishes_df: pd.DataFrame,
    ndf: pd.DataFrame = nutrition_df,
    udf: pd.DataFrame = units_df,
) -> dict[str, float]:
    """Calculate per-serving nutrition for a matched dish."""
    full_nutrient_list = list(ndf.columns)
    info: dict[str, float] = {
        key: 0.0 for key in full_nutrient_list if key not in _DROP_COLS
    }

    dish_row = dishes_df.loc[dishes_df["name"] == dish_name]
    servings = dish_row["servings"].values[0] if not dish_row.empty else 1
    if not isinstance(servings, int):
        servings = 1

    for i in dish_row["ingredient_description"].values[0]:
        for ing in i["items"]:
            ing_in_df = matched_dict.get(ing)
            if ing_in_df is None:
                ing_in_df = find_ingredient(ing, ndf)
                matched_dict[ing] = ing_in_df

            ing_info = i["items"][ing]
            qty = ing_info["quantity"]
            unit = ing_info["unit"]

            try:
                qty_val = float(qty)
            except (ValueError, TypeError):
                print(f"Skipping '{ing}' due to invalid or unspecified quantity: {qty}")
                continue

            g_equivalent = convert_unit(unit, ing, udf)
            if not g_equivalent:
                print(
                    f"No way to get weight (in grams) of {ing}, unit is {unit}. "
                    f"Skipping in nutrition calculation"
                )
                continue

            grams = float(g_equivalent) * qty_val
            scale = grams / 100

            if ing_in_df == "NA":
                nutritionix_response = nutritionix(ing)
                if isinstance(nutritionix_response, dict):
                    to_process = {
                        k: v
                        for k, v in nutritionix_response.items()
                        if k not in _DROP_COLS
                    }
                    info = _add_to_nutrition(info, _scale_values(scale, to_process))
                else:
                    print(
                        f"Failed nutritionix call for {ing}, "
                        f"proceeding with no nutritive data"
                    )
                    continue
            else:
                row = ndf[ndf["Food Name; name"] == ing_in_df]
                if len(row) == 0:
                    print(
                        f"For {ing}, no corresponding {ing_in_df} found in DB. "
                        f"Skipping in nutrition calculation"
                    )
                    continue
                row = row.drop(columns=_DROP_COLS, errors="ignore")
                matched_to = row.iloc[0].to_dict()
                info = _add_to_nutrition(info, _scale_values(scale, matched_to))

    info_per_serving = {key: value / servings for key, value in info.items()}
    return info_per_serving


# ---------------------------------------------------------------------------
# High-level orchestrators (called by route handlers)
# ---------------------------------------------------------------------------
def calculate_nutrition_for_dish(
    dish_name: str,
    dishes_df: pd.DataFrame = recipes_df,
    ndf: pd.DataFrame = nutrition_df,
    udf: pd.DataFrame = units_df,
) -> dict[str, float]:
    """Full pipeline: match dish → match ingredients → calculate nutrition."""
    matched_dish = match_recipe(dish_name, dishes_df)
    if not matched_dish:
        return {}

    try:
        matched_dict = get_matched_ingredient(matched_dish, dishes_df, ndf)
        print(matched_dict)
    except Exception:
        print(f"Error matching ingredient list for {matched_dish}")
        return {}

    try:
        return calculate_nutrition(matched_dict, matched_dish, dishes_df, ndf, udf)
    except Exception as e:
        print(f"Error calculating nutrition for {matched_dish}: {e}")
        return {}


def fetch_nutrition_for_dish(
    dish_name: str, df: pd.DataFrame = precalculated_df
) -> dict:
    """Fetch precalculated per-100g nutrition from the master sheet."""
    matched_dish = match_from_precalculated(dish_name, df)
    if not matched_dish:
        return {}

    drop_cols = ["Dish Weight (g)", "primarysource", "Food Name; name"]
    dish_row = df[df["Food Name; name"] == matched_dish]
    dish_row = dish_row.drop(columns=drop_cols, errors="ignore")
    return dish_row.iloc[0].to_dict()


def get_ingredients(
    dish_name: str,
    dishes_df: pd.DataFrame = recipes_df,
    ndf: pd.DataFrame = nutrition_df,
) -> dict[str, str]:
    """Get the {raw_ingredient: matched_fct_name} mapping for a dish."""
    matched_dish = match_recipe(dish_name, dishes_df)
    if not matched_dish:
        return {}

    try:
        return get_matched_ingredient(matched_dish, dishes_df, ndf)
    except Exception:
        print(f"Error matching ingredient list for {matched_dish}")
        return {}


def save_nutrition_db() -> None:
    """Persist the current in-memory nutrition_df back to fct.xlsx."""
    nutrition_df.to_excel(INGREDIENTS_PATH, index=False)
