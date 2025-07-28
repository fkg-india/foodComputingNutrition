'''
1. take as input a string (dish name)
2. try and match it to some dish in the DB (recipes.jsonl)
3. calculate nutrition (via the master database of nutrients + nutritionix)
4. send back the nutrition info json 
5. write any new ingredients looked up to the master db
'''

from rapidfuzz import process, fuzz
from flask import jsonify
import re
import requests
import pandas as pd
from flask import Flask, request, jsonify
import math

app = Flask(__name__)

RECIPES_PATH = r"C:\Users\Anurav\Research\FoodComputing\foodComputingNutrition-main\foodComputingNutrition-main\recipes.pkl" # PATH TO PKL (see misc to get pkl from jsonl)
UNITS_PATH = r"C:\Users\Anurav\Research\FoodComputing\foodComputingNutrition-main\foodComputingNutrition-main\units.xlsx" 
INGREDIENTS_PATH = r"C:\Users\Anurav\Research\FoodComputing\foodComputingNutrition-main\foodComputingNutrition-main\fct.xlsx"

recipes_df = pd.read_pickle(RECIPES_PATH)
units_df = pd.read_excel(UNITS_PATH)
nutrition_df = pd.read_excel(INGREDIENTS_PATH)

def clean_nan_values(obj):
    if isinstance(obj, dict):
        return {key: clean_nan_values(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan_values(item) for item in obj]
    elif isinstance(obj, float) and math.isnan(obj):
        return 0.0  
    else:
        return obj


def nutritionix(ingredient):
    url = 'https://trackapi.nutritionix.com/v2/natural/nutrients'
    headers = {
        'Content-Type': 'application/json',
        'x-app-id': 'd4440f54',
        'x-app-key': '03a9f800ce93eb67f07224633b953ee9'
    }
    body = {"query": ingredient}
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code != 200:
            print(f"Nutritionix request failed for '{ingredient}' with status {response.status_code}")
            return None
        data = response.json()
        if not data.get('foods'):
            print(f"Nutritionix found no results for '{ingredient}'.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error calling Nutritionix for '{ingredient}': {e}")
        return None

    # --- Process the successful response ---
    food_data = data['foods'][0]
    print(food_data)

    nutrient_map = {
        208: 'Energy; enerc', 204: 'Total Fat; fatce', 606: 'Saturated Fatty acids; fasat',
        307: 'Sodium (Na); na', 306: 'Potassium (K); k', 205: 'Carbohydrate; choavldf',
        291: 'Dietary Fiber; fibtg', 269: 'Free Sugars; fsugar', 203: 'Protein; protcnt',
        318: 'Vitamin A; vita', 401: 'Ascorbic acids (C); vitc', 301: 'Calcium (Ca); ca',
        303: 'Iron (Fe); fe', 309: 'Zinc (Zn); zn', 324: 'Vitamin D; vitd',
        404: 'Thiamine (B1); thia', 405: 'Riboflavin (B2); ribf', 406: 'Niacin (B3); nia',
        417: 'Folates (B9); folsum', 601: 'Cholesterol; cholc', 305: 'Phosphorus (P); p',
        304: 'Magnesium (Mg); mg', 317: 'Selenium (Se); se', 312: 'Copper (Cu); cu',
        338: 'Carotenoids; cartoid', 410: 'Pantothenic acid (B5); pantac',  430: 'Vitamin K; vitk', 
        415: 'Total B6; vitb6c', 323: 'Tocopherol equivalent (E); vite', 605: 'Trans Fatty acids; fatrn', 
        618: 'Essential Fatty acids; faess', 645: 'Monounsaturated Fatty acids; fams', 646: 'Polyunsaturated Fatty acids; fapu',
        255: 'Moisture; water', 315: 'Manganese (Mn); mn'
    }
    
    # Units that need conversion to grams
    mg_ids = {307, 306, 401, 301, 303, 309, 404, 405, 406, 415, 601, 305, 304, 312, 410, 323, 315}
    mcg_ids = {318, 417, 317, 338, 430}

    IU_ids = {318, 324} 
    IU_conversion = {
    318: 0.0000003,     # Vitamin A
    324: 0.000000025    # Vitamin D
    }

    
    food_matched_name = food_data.get("food_name", None)
    food_serving_weight = food_data.get("serving_weight_grams", None)
    food_nutrients = food_data.get('full_nutrients', [])

    result = dict()

    result['Food Name; name'] = food_matched_name
    result['Alternate Name; alt_name'] = ingredient if food_matched_name != ingredient else ""
    result['primarysource'] = "nutritionix_FKG"

    for item in food_nutrients:
        attr_id = item['attr_id']
        if attr_id in nutrient_map:
            value = item.get('value', 0)
            # Normalize to per 100g
            value_per_100g = (value / food_serving_weight) * 100
            if attr_id in mg_ids: value_per_100g /= 1000
            if attr_id in mcg_ids: value_per_100g /= 1000000
            if attr_id in IU_ids: value_per_100g *= IU_conversion[attr_id]  
            result[nutrient_map[attr_id]] = value_per_100g
            
    return result

def smart_score(query, choice, **kwargs): 
    scores = [
        fuzz.ratio(query, choice),
        fuzz.token_sort_ratio(query, choice),
        fuzz.token_set_ratio(query, choice),
        fuzz.partial_ratio(query, choice)
    ]

    return max(scores)

def match_recipe(dish_name, dishes_df):
    recipe_names = list(dishes_df['name'])
    
    best_match, score, _ = process.extractOne(
        dish_name, recipe_names, scorer=smart_score
    )
    
    # print(best_match, score, _)

    if score < 75:
        print(f'Found no matching dish for {dish_name} in database. Closest match is {best_match}')
        return None
    else:
        print(f"Found matching recipe: '{best_match}' with score {score}")
        return best_match

def normalize(text):
    """
    Removes special characters, converts to lowercase, and standardizes whitespace
    """
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', '', str(text).lower())).strip()

def find_ingredient(name, nutrition_df=nutrition_df):
    """
    Tries to match ingredient to an eisting ingredient in nutrition_df, returns name of ingredient if found 
    """
    nutrition_df['Alternate Name; alt_name'] = nutrition_df['Alternate Name; alt_name'].fillna('').astype(str)

    original_clean = normalize(name)
    food_names = nutrition_df['Food Name; name'].tolist()

    # 1. Fuzzy match against normalized Food_Name using token_sort_ratio
    match = process.extractOne(original_clean, food_names, scorer=fuzz.token_sort_ratio)
    # print(match)

    if match and match[1] >= 80:  
        return match[0]

    # 2. Fallback: check if the original name is a substring in Alternate_Name (case-insensitive)
    alt_match_row = nutrition_df[nutrition_df['Alternate Name; alt_name'].str.lower().str.contains(name.strip().lower(), regex=False)]

    if not alt_match_row.empty:
        matched_name = alt_match_row.iloc[0]['Food Name; name']
        return matched_name

    # 3. If no match is found after both steps
    # print(f"No confident match found for: '{name}'. Closest match is {match[0]}")
    return "NA"

def nutritionix(ingredient):
    url = 'https://trackapi.nutritionix.com/v2/natural/nutrients'
    headers = {
        'Content-Type': 'application/json',
        'x-app-id': 'd4440f54',
        'x-app-key': '03a9f800ce93eb67f07224633b953ee9'
    }
    body = {"query": ingredient}
    try:
        response = requests.post(url, headers=headers, json=body)
        if response.status_code != 200:
            print(f"Nutritionix request failed for '{ingredient}' with status {response.status_code}")
            return None
        data = response.json()
        if not data.get('foods'):
            print(f"Nutritionix found no results for '{ingredient}'.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Network error calling Nutritionix for '{ingredient}': {e}")
        return None

    # --- Process the successful response ---
    food_data = data['foods'][0]
    # print(food_data)

    nutrient_map = {
        208: 'Energy; enerc', 204: 'Total Fat; fatce', 606: 'Saturated Fatty acids; fasat',
        307: 'Sodium (Na); na', 306: 'Potassium (K); k', 205: 'Carbohydrate; choavldf',
        291: 'Dietary Fiber; fibtg', 269: 'Free Sugars; fsugar', 203: 'Protein; protcnt',
        318: 'Vitamin A; vita', 401: 'Ascorbic acids (C); vitc', 301: 'Calcium (Ca); ca',
        303: 'Iron (Fe); fe', 309: 'Zinc (Zn); zn', 324: 'Vitamin D; vitd',
        404: 'Thiamine (B1); thia', 405: 'Riboflavin (B2); ribf', 406: 'Niacin (B3); nia',
        417: 'Folates (B9); folsum', 601: 'Cholesterol; cholc', 305: 'Phosphorus (P); p',
        304: 'Magnesium (Mg); mg', 317: 'Selenium (Se); se', 312: 'Copper (Cu); cu',
        338: 'Carotenoids; cartoid', 410: 'Pantothenic acid (B5); pantac',  430: 'Vitamin K; vitk', 
        415: 'Total B6; vitb6c', 323: 'Tocopherol equivalent (E); vite', 605: 'Trans Fatty acids; fatrn', 
        618: 'Essential Fatty acids; faess', 645: 'Monounsaturated Fatty acids; fams', 646: 'Polyunsaturated Fatty acids; fapu',
        255: 'Moisture; water', 315: 'Manganese (Mn); mn'
    }
    
    # Units that need conversion to grams
    mg_ids = {307, 306, 401, 301, 303, 309, 404, 405, 406, 415, 601, 305, 304, 312, 410, 323, 315}
    mcg_ids = {318, 417, 317, 338, 430}
    IU_ids = {318, 324}
    
    food_matched_name = food_data.get("food_name", None)
    food_serving_weight = food_data.get("serving_weight_grams", None)
    food_nutrients = food_data.get('full_nutrients', [])

    result = dict()

    result['Food Name; name'] = food_matched_name
    result['Alternate Name; alt_name'] = ingredient if food_matched_name != ingredient else ""
    result['primarysource'] = "nutritonix"

    for item in food_nutrients:
        attr_id = item['attr_id']
        if attr_id in nutrient_map:
            value = item.get('value', 0)
            # Normalize to per 100g
            value_per_100g = (value / food_serving_weight) * 100
            if attr_id in mg_ids: value_per_100g /= 1000
            if attr_id in mcg_ids: value_per_100g /= 1000000
            result[nutrient_map[attr_id]] = value_per_100g
            
    return result

def get_matched_ingredient(dish_name, dishes_df, nutrition_df=nutrition_df):
    """Return a dictionary of matched ingredients for dish_name"""
    dish_row = dishes_df.loc[dishes_df['name'] == dish_name]
    ing_matched = {}
    for l in dish_row['ingredients']:
        # print(l)
        for i in l:
            ing_matched[i] = find_ingredient(i)
    return ing_matched

def add_to_nutrition(nutrition_dict, add_dict):
    for i in add_dict.items():
        name, val = i[0], float(i[1])
        if name not in nutrition_dict: continue 
        else: nutrition_dict[name] += val
    return nutrition_dict

def scale_values(scale, dict_to_scale):
    for i in dict_to_scale:
        dict_to_scale[i] *= scale
    return dict_to_scale

def calculate_nutrition(matched_dict, dish_name, dishes_df, nutrition_df=nutrition_df, units_df=units_df):
    """
    Calculates the nutrition composition for a dish, return a JSON 
    """
    full_nutrient_list = list(nutrition_df.columns)
    drop_cols = ['#', 'Food Name; name', 'Alternate Name; alt_name', 'Local Name; lang', 'food_code', 'food_group_nin', 'primarysource']
    info = {key: 0 for key in full_nutrient_list if key not in drop_cols}
    dish_row = dishes_df.loc[dishes_df['name'] == dish_name]
    servings = dish_row['servings']
    if not isinstance(servings, int): servings = 1 # set to 1 if NA 
    
    
    for i in dish_row['ingredient_description'].values[0]:
        for ing in i['items']:
            ing_in_df = matched_dict[ing]
            ing_info = i['items'][ing]
            qty = ing_info['quantity']
            unit = ing_info['unit']
            est_g = ing_info['estimated_weight_in_grams']

            if unit not in units_df['unit']: 
                if est_g == 'NA':
                    print(f'No way to get weight (in grams) of {ing}, unit is {unit}. Skipping in nutrition claculation')
                    continue 
                else: 
                    est_g = float(est_g)
                    scale = est_g / 100
            else:
                g_equivalent = units_df[units_df['unit'] == unit]['value']
                grams = float(g_equivalent) * float(qty)
                scale = grams / 100

            if ing_in_df == 'NA':
                # print('In nutritionix')
                nutritionix_response = nutritionix(ing)
                if isinstance(nutritionix_response, dict): 
                    to_process_dict = {i:nutritionix_response[i] for i in nutritionix_response if i not in drop_cols}
                    info = add_to_nutrition(info, scale_values(scale, to_process_dict))
                else:
                    print(f'Failed nutritionix call for {ing}, proceeding with no nutritive data')
                    continue

            else: # matched ingredient to something in nutrition_df
                # print('In DB')
                row = nutrition_df[nutrition_df['Food Name; name'] == ing_in_df]
                if len(row) == 0:
                    print(f'For {ing}, no corresponding {ing_in_df} found in DB. Skipping in nutrition calculation')
                    continue 
                row = row.drop(columns=drop_cols, errors='ignore')
                matched_to = row.iloc[0].to_dict()
                info = add_to_nutrition(info, scale_values(scale, matched_to))
    
    info_per_serving = {key: value / servings for key, value in info.items()}
    return info_per_serving
    
def calculate_nutrition_for_dish(dish_name, dishes_df=recipes_df, nutrition_df=nutrition_df, units_df=units_df):
    """ Input a dish name, and get nutrition dicitionary """
    matched_dish = match_recipe(dish_name, dishes_df)
    if not matched_dish: return {}

    try: matched_dict = get_matched_ingredient(matched_dish, dishes_df, nutrition_df)
    except: 
        print(f'Error matching ingredient list for {matched_dish}')
        return {}
    try: nutrition_info = calculate_nutrition(matched_dict, matched_dish, dishes_df, nutrition_df, units_df)
    except Exception as e: 
        print(f'Error calculating nutrition for {matched_dish}: {e}')
        return {}
    
    return nutrition_info

def get_ingredients(dish_name, dishes_df=recipes_df, nutrition_df=nutrition_df, units_df=units_df):
    """ Get an ingredient list for the input dish_name """
    matched_dish = match_recipe(dish_name, dishes_df)
    if not matched_dish: return {}

    try: 
        matched_dict = get_matched_ingredient(matched_dish, dishes_df, nutrition_df)
        return matched_dict
    except: 
        print(f'Error matching ingredient list for {matched_dish}')
        return {}

def get_matching_dishes(dish_name, k=2, dishes_df=recipes_df):
    """ Get k closest dish_name matches """
    recipe_names = list(dishes_df['name'])
    min_score = 75

    matches = process.extract(dish_name, recipe_names, scorer=smart_score, limit=k)

    filtered_matches = [(name, score) for name, score, _ in matches if score >= min_score]

    if not filtered_matches:
        print(f"No good match found for '{dish_name}'. Closest was: {matches[0][0]} (score: {matches[0][1]})")
        return []
    else: return filtered_matches


# --- API Endpoints ---

@app.route('/nutrition', methods=['POST'])
def get_dish_nutrition():
    """
    API endpoint to get nutrition for a dish.
    Expects a JSON body with {"dish_name": "some dish"}
    """
    data = request.get_json()
    if not data or 'dish_name' not in data:
        return jsonify({"error": "Invalid request. 'dish_name' not found in JSON body."}), 400

    dish_name = data['dish_name']
    print(f"Received request for dish: '{dish_name}'")

    nutrition_info = calculate_nutrition_for_dish(dish_name)
    nutrition_df.to_excel(INGREDIENTS_PATH, index=False)
    
    if not nutrition_info:
        return jsonify({"error": f"No nutrition data found for dish: '{dish_name}'"}), 404

    return jsonify({
        "matched_dish_name": match_recipe(dish_name, recipes_df),
        "nutrition_per_serving": clean_nan_values(nutrition_info)
    })


@app.route('/ingredients', methods=['POST'])
def get_dish_ingredients():
    """
    API endpoint to get matched ingredient list for a dish.
    Expects a JSON body with {"dish_name": "some dish"}
    Returns dict where keys are raw ingredient names (as listed) and values are matched ingredient names
    """
    data = request.get_json()
    if not data or 'dish_name' not in data:
        return jsonify({"error": "Invalid request. 'dish_name' not found in JSON body."}), 400

    dish_name = data['dish_name']
    print(f"Received request for ingredients of dish: '{dish_name}'")

    ingredients = get_ingredients(dish_name)
    if ingredients == {}:
        return jsonify({"error": f"No ingredient data found for dish: '{dish_name}'"}), 404

    return jsonify({
        "matched_dish_name": match_recipe(dish_name, recipes_df),
        "ingredients": ingredients
    })

@app.route('/autocomplete', methods=['POST'])
def autocomplete():
    """
    API endpoint to get matched dish-name list for a dish.
    Expects a JSON body with {"dish_name": "some dish"}
    """
    data = request.get_json()
    if not data or 'dish_name' not in data:
        return jsonify({"error": "Invalid request. 'dish_name' not found in JSON body."}), 400

    dish_name = data['dish_name']
    print(f"Received request for ingredients of dish: '{dish_name}'")

    matches = get_matching_dishes(dish_name, k=3, dishes_df=recipes_df)

    if not matches: return jsonify({"error": f"No close match found for dish: '{dish_name}'"}), 404

    best_match = matches[0][0]

    return jsonify({
        "input_dish_name": dish_name,
        "matched_dish_name": best_match,
        "match_score": matches[0][1],
        "top_matches": [{"name": name, "score": score} for name, score in matches],
    })

@app.route('/agg_nutrition', methods=['POST'])
def agg_nutrition():
    """
    API endpoint to get nutrition information for a list of dishes
    Expects a JSON body with {"dishes": ["dish1", "dish2", ...]}
    """
    data = request.get_json()
    if not data or 'dishes' not in data:
        return jsonify({"error": "Invalid request. 'dishes' not found in JSON body"}), 400
    
    dishes = [dish for dish in data['dishes']]
    print(f"Received request for dishes: '{dishes}'")

    total_nutrition_info = {}
    skipped = []

    for dish in dishes: 
        nutrition_info = calculate_nutrition_for_dish(dish)
        nutrition_df.to_excel(INGREDIENTS_PATH, index=False)

        if not nutrition_info: skipped.append(dish)
        else: 
            for i in nutrition_info: 
                if i in total_nutrition_info: total_nutrition_info[i] += nutrition_info[i]
                else: total_nutrition_info[i] = nutrition_info[i]

    matched_dish_names = {dish:match_recipe(dish, recipes_df) for dish in dishes}

    response_data = {
        "matched_dish_names": clean_nan_values(matched_dish_names),
        "nutrition_per_serving": clean_nan_values(total_nutrition_info),
        "skipped_dishes": skipped
    }

    return response_data


# --- Main Execution ---
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
# visit http://localhost:8000/docs#/
