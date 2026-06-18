Flask Migration to Fast

# Migration Verification Audit

Systematic comparison of old → new. Every function, route, schema, constant, and side-effect is accounted for.

---

## 1. Business Logic Functions (cal_new.py → calculator.py)

| # | Function | Old Location | New Location | Verdict |
|---|---|---|---|---|
| 1 | `convert_units_df()` | L35-46 | L44-58 as `_convert_units_df()` | ✅ Identical logic |
| 2 | `clean_nan_values()` | L50-58 | L78-86 | ✅ Identical |
| 3 | `nutritionix()` | L61-133 | L354-406 | ✅ Identical logic. Constants extracted to module level (`_NUTRIENT_MAP`, `_MG_IDS`, etc.) but same values and same conversion math |
| 4 | `smart_score()` | L135-143 | L97-104 | ✅ Identical |
| 5 | `match_recipe()` | L145-155 | L107-116 | ✅ Identical |
| 6 | `match_from_precalculated()` | L157-165 | L119-129 | ✅ Identical |
| 7 | `normalize()` | L168-172 | L89-91 | ✅ Identical |
| 8 | `find_ingredient()` | L174-200 | L151-180 | ✅ Identical (3-step: fuzzy → alt_name → "NA") |
| 9 | `get_matched_ingredient()` | L202-210 | L183-194 | ✅ Identical |
| 10 | `convert_unit()` | L212-226 | L200-220 | ✅ Identical |
| 11 | `add_to_nutrition()` | L228-233 | L412-419 as `_add_to_nutrition()` | ✅ Identical |
| 12 | `scale_values()` | L235-238 | L422-426 as `_scale_values()` | ✅ Identical |
| 13 | `calculate_nutrition()` | L240-305 | L429-503 | ⚠️ **See Gap #1 below** |
| 14 | `calculate_nutrition_for_dish()` | L307-323 | L509-531 | ✅ Identical |
| 15 | `fetch_nutrition_for_dish()` | L325-335 | L534-545 | ✅ Identical |
| 16 | `get_ingredients()` | L337-347 | L548-562 | ✅ Identical |
| 17 | `get_matching_dishes()` | L349-361 | L132-145 | ✅ Identical |
| 18 | `parse_for_unit_conversion()` | L363-415 | L236-294 | ✅ Identical |
| 19 | `convert_unit_to_grams()` | L417-420 | L223-230 | ✅ Identical |
| 20 | `save_nutrition_db()` | *(inline in routes)* | L565-567 | ✅ New wrapper — same `nutrition_df.to_excel(INGREDIENTS_PATH, index=False)` |

---

## 2. Gap Analysis

### Gap #1: `calculate_nutrition()` — missing `est_g` read

**Old code (L262):**
```python
est_g = ing_info['estimated_weight_in_grams']
```

**New code:** This line is **missing** from [calculator.py L454-456](file:///Users/manishyadav/Documents/work/KCDHA/food-computing/foodComputingNutrition/backend/app/services/calculator.py#L454-L456).

**Impact: NONE.** The old code reads `est_g` but then **never uses it** — the fallback path that would have used `est_g` (L276-278) is commented out in the original. The variable was dead code. Omitting it is correct.

### Gap #2: `calculate_nutrition()` — servings extraction

**Old code (L248-249):**
```python
servings = dish_row['servings']
if not isinstance(servings, int): servings = 1
```

**New code (L443-445):**
```python
servings = dish_row["servings"].values[0] if not dish_row.empty else 1
if not isinstance(servings, int):
    servings = 1
```

**Impact: IMPROVEMENT.** The old code assigned a pandas Series to `servings`, which would always fail `isinstance(servings, int)` and default to 1. The new code correctly extracts the scalar value with `.values[0]`, so dishes with actual serving counts > 1 are now handled properly.

### Gap #3: `nutritionix()` — missing `food_serving_weight` guard

**Old code:** No guard for `food_serving_weight` being `None` — would crash with `TypeError: unsupported operand type(s) for /: 'int' and 'NoneType'` on L127.

**New code (L384-385):**
```python
if not food_serving_weight:
    return None
```

**Impact: IMPROVEMENT.** Prevents a divide-by-zero crash.

---

## 3. Flask Routes → FastAPI Routes

| # | Old Flask Route | Old FastAPI Proxy | New Route | Input Schema | Output Schema | Behavior Match |
|---|---|---|---|---|---|---|
| 1 | `POST /nutrition` (L424-446) | `POST /api/nutrition` (L76-102) | `POST /api/v1/nutrition/nutrition` | `DishRequest` | `NutritionResponse` | ✅ |
| 2 | `POST /ingredients` (L449-470) | `POST /api/ingredients` (L104-125) | `POST /api/v1/nutrition/ingredients` | `DishRequest` | `IngredientsResponse` | ✅ |
| 3 | `POST /autocomplete` (L472-496) | `POST /api/autocomplete` (L127-148) | `POST /api/v1/nutrition/autocomplete` | `DishRequest` | `AutocompleteResponse` | ✅ |
| 4 | `POST /agg_nutrition` (L498-532) | `POST /api/agg_nutrition` (L150-176) | `POST /api/v1/nutrition/aggregate` | `DishListRequest` | `AggNutritionResponse` | ✅ |
| 5 | `POST /ingredient_search` (L534-543) | `POST /api/ingredient_search` (L178-200) | `POST /api/v1/nutrition/ingredient-search` | `IngredientSearchRequest` | `IngredientSearchResponse` | ✅ |
| 6 | `POST /fetch_nutrition` (L545-552) | `POST /api/fetch_nutrition` (L203-225) | `POST /api/v1/nutrition/fetch` | `FetchNutritionRequest` | `FetchNutritionResponse` | ✅ |
| 7 | `POST /convert_to_grams` (L554-574) | `POST /api/convert_to_grams` (L227-249) | `POST /api/v1/nutrition/convert-to-grams` | `ConvertToGramsRequest` | `ConvertToGramsResponse` | ✅ |
| 8 | *(N/A — new combined)* | *(N/A)* | `POST /api/v1/nutrition/dish` | `DishRequest` | `DishNutritionResponse` | ✅ New endpoint |
| 9 | *(N/A)* | `GET /health` (L252-268) | `GET /health` | — | — | ✅ (simplified: no Flask ping) |
| 10 | *(N/A)* | `GET /` (L270-288) | `GET /` | — | — | ✅ |

**All 7 original Flask routes are present. All 7 original FastAPI proxy routes are present. 0 missing.**

---

## 4. Route Behavior Comparison (Detail)

### `/nutrition` → `/api/v1/nutrition/nutrition`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `request.get_json()['dish_name']` | Pydantic `DishRequest` | ✅ (auto-validated) |
| Calculate | `calculate_nutrition_for_dish(dish_name)` | Same | ✅ |
| Save DB | `nutrition_df.to_excel(INGREDIENTS_PATH, index=False)` | `save_nutrition_db()` — same call | ✅ |
| 404 check | `if not nutrition_info` → 404 | Same | ✅ |
| Response | `{"matched_dish_name": ..., "nutrition_per_serving": clean_nan_values(...)}` | Same | ✅ |

### `/ingredients` → `/api/v1/nutrition/ingredients`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `request.get_json()['dish_name']` | Pydantic `DishRequest` | ✅ |
| Get ingredients | `get_ingredients(dish_name)` | Same | ✅ |
| 404 check | `if ingredients == {}` → 404 | `if not ingredients` → 404 | ✅ (equivalent) |
| Response | `{"matched_dish_name": ..., "ingredients": ...}` | Same | ✅ |

### `/autocomplete` → `/api/v1/nutrition/autocomplete`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `request.get_json()['dish_name']` | Pydantic `DishRequest` | ✅ |
| Match | `get_matching_dishes(dish_name, k=3, dishes_df=recipes_df)` | Same | ✅ |
| Response | `{"input_dish_name", "matched_dish_name", "match_score", "top_matches"}` | Same structure | ✅ |

### `/agg_nutrition` → `/api/v1/nutrition/aggregate`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `data['dishes']` | Pydantic `DishListRequest` | ✅ |
| Loop | Calculate per dish, accumulate | Same | ✅ |
| Save DB | Inside loop `nutrition_df.to_excel(...)` | `save_nutrition_db()` inside loop | ✅ |
| Skipped tracking | `skipped.append(dish)` | Same | ✅ |
| Response | `{"matched_dish_names", "nutrition_per_serving", "skipped_dishes"}` | Same structure | ✅ |

### `/ingredient_search` → `/api/v1/nutrition/ingredient-search`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `data['ingredients']` | Pydantic `IngredientSearchRequest` | ✅ |
| Match | `{ing: find_ingredient(ing) for ing in ings}` | Same | ✅ |
| Response | Raw dict | `IngredientSearchResponse(matched_ingredients=...)` | ✅ |

### `/fetch_nutrition` → `/api/v1/nutrition/fetch`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `data['dish']` | Pydantic `FetchNutritionRequest` | ✅ |
| Fetch | `fetch_nutrition_for_dish(dish)` | Same | ✅ |
| Response | Raw dict | `FetchNutritionResponse(nutrition_data=clean_nan_values(result))` | ✅ (added NaN cleaning — improvement) |

### `/convert_to_grams` → `/api/v1/nutrition/convert-to-grams`

| Step | Old | New | Match |
|---|---|---|---|
| Parse input | `data['string_to_convert']` | Pydantic `ConvertToGramsRequest` | ✅ |
| Parse | `parse_for_unit_conversion(string_to_convert)` | Same | ✅ |
| Convert | `convert_unit_to_grams(number, unit, ingredient)` | Same | ✅ |
| Response | `{"original", "parsed": {"quantity", "unit", "ingredient"}, "grams"}` | Same structure | ✅ |

---

## 5. Pydantic Schemas (fastapi_frontend.py → schemas.py)

| Old Schema (fastapi_frontend.py) | New Schema (schemas.py) | Match |
|---|---|---|
| `DishRequest` (L17-18) | `DishRequest` (L5-6) | ✅ |
| `DishListRequest` (L20-21) | `DishListRequest` (L9-10) | ✅ |
| `NutritionResponse` (L23-25) | `NutritionResponse` (L43-45) | ✅ (`matched_dish_name` now `Optional`) |
| `IngredientsResponse` (L27-29) | `IngredientsResponse` (L48-50) | ✅ (`matched_dish_name` now `Optional`) |
| `MatchInfo` (L31-33) | `MatchInfo` (L25-27) | ✅ |
| `AggNutritionResponse` (L35-38) | `AggNutritionResponse` (L60-63) | ✅ |
| `AutocompleteResponse` (L40-44) | `AutocompleteResponse` (L53-57) | ✅ |
| `ErrorResponse` (L46-47) | *(removed)* | ✅ Not needed — FastAPI uses `HTTPException` |
| `IngredientSearchRequest` (L49-50) | `IngredientSearchRequest` (L17-18) | ✅ |
| `IngredientSearchResponse` (L52-53) | `IngredientSearchResponse` (L66-67) | ✅ |
| `FetchNutritionRequest` (L55-56) | `FetchNutritionRequest` (L13-14) | ✅ |
| `FetchNutritionResponse` (L58-59) | `FetchNutritionResponse` (L70-71) | ✅ |
| `ConvertToGramsRequest` (L61-62) | `ConvertToGramsRequest` (L21-22) | ✅ |
| `ParsedData` (L64-67) | `ParsedData` (L30-33) | ✅ |
| `ConvertToGramsResponse` (L69-72) | `ConvertToGramsResponse` (L74-77) | ✅ |
| *(N/A)* | `DishNutritionResponse` (L36-40) | ✅ New — for combined `/dish` endpoint |

---

## 6. Constants & Data Loading

| Item | Old | New | Match |
|---|---|---|---|
| `BASE_DIR` / `DATA_DIR` | `os.path.dirname(os.path.abspath(__file__))` | `Path(__file__).resolve().parents[3]` | ✅ Both resolve to project root |
| `RECIPES_PATH` | `recipes.pkl` | Same | ✅ |
| `UNITS_PATH` | `units.xlsx` | Same | ✅ |
| `INGREDIENTS_PATH` | `fct.xlsx` | Same | ✅ |
| `PRECALCULATED_PATH` | `master_dishes_nutrition_per_100g.xlsx` | Same | ✅ |
| `recipes_df` | `pd.read_pickle(...)` | Same | ✅ |
| `nutrition_df` | `pd.read_excel(...)` | Same | ✅ |
| `precalculated_df` | `pd.read_excel(...)` | Same | ✅ |
| `units_df` | `pd.read_excel(...)` then `convert_units_df(...)` | Same | ✅ |
| `nutrient_map` (Nutritionix) | 34 entries inline | 34 entries as `_NUTRIENT_MAP` | ✅ Same keys, same values |
| `mg_ids` | `{307, 306, ...}` (17 IDs) | `_MG_IDS` (17 IDs) | ✅ Same set |
| `mcg_ids` | `{318, 417, 317, 338, 430}` | `_MCG_IDS` (same 5 IDs) | ✅ |
| `IU_ids` | `{318, 324}` | `_IU_IDS` (same 2 IDs) | ✅ |
| `IU_conversion` | `{318: 0.0000003, 324: 0.000000025}` | `_IU_CONVERSION` (same values) | ✅ |
| `drop_cols` | 7 columns inline in functions | `_DROP_COLS` (same 7 columns) | ✅ |

---

## 7. Side Effects

| Side Effect | Old | New | Match |
|---|---|---|---|
| `nutrition_df.to_excel(...)` on `/nutrition` | L438 | `save_nutrition_db()` called in `/nutrition` route (L77) | ✅ |
| `nutrition_df.to_excel(...)` on `/agg_nutrition` | L516 (inside loop) | `save_nutrition_db()` called inside loop (L144) | ✅ |
| Print statements | Throughout | Preserved throughout | ✅ |

---

## 8. Final Verdict

| Category | Items Checked | Issues Found |
|---|---|---|
| Business logic functions | 20 | 0 issues (2 improvements) |
| Flask routes | 7 | 0 missing |
| FastAPI proxy routes | 7 | 0 missing |
| Pydantic schemas | 15 | 0 missing (1 removed: `ErrorResponse` — not needed) |
| Constants & data loading | 14 | 0 issues |
| Side effects | 2 | 0 issues |
| **Total** | **65** | **✅ 0 gaps, 3 improvements** |

> [!TIP]
> **The 3 improvements over the old code:**
> 1. Servings extraction now correctly gets the scalar value instead of a pandas Series
> 2. Nutritionix `food_serving_weight` null guard prevents divide-by-zero
> 3. `/fetch` endpoint now applies `clean_nan_values()` to the response (old code didn't)
