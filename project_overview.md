# Project Overview: Food Computing Nutrition Calculator

The **Food Computing Nutrition Calculator** is a nutrition analysis system that estimates the nutritional composition of cooked meals without requiring laboratory testing. It dynamically calculates macro- and micro-nutrients for custom recipes by identifying ingredients, converting household measurements into standard weights, and aggregating nutritional values per serving.

Designed for health apps, fitness platforms, dietary planning tools, and recipe websites, the system enables developers to retrieve detailed nutritional information simply by providing a dish name.

## Architecture

The application follows a two-service architecture:

* **FastAPI Gateway**: Handles request validation, API documentation, and client communication.
* **Flask Calculation Engine**: Performs recipe matching, quantity parsing, unit conversion, nutrient calculations, and database operations.

## Data Sources

The system primarily relies on local datasets:

* **recipes.pkl** – Recipe library and serving sizes
* **fct.xlsx** – Food Composition Table containing nutrient values
* **units.xlsx** – Ingredient-specific unit conversion data

When an ingredient is missing from the local database, the system automatically queries the **Nutritionix API**, stores the retrieved data locally, and reuses it for future calculations. This self-learning approach reduces external API dependency over time.

## Workflow

1. A nutrition request is sent through the FastAPI gateway.
2. The Flask engine uses fuzzy matching to find the closest recipe.
3. Ingredient quantities are extracted and converted from text-based measurements into numeric values.
4. Units are converted into grams using conversion tables.
5. Nutrient values are retrieved, scaled according to ingredient weight, aggregated, and divided by serving size.
6. A detailed per-serving nutritional profile is returned as JSON.

## Setup

1. Place `recipes.pkl` in the project root directory.
2. Install dependencies using `pip install -r requirements.txt`.
3. Start both services:

   * `python cal_new.py`
   * `python fastapi_frontend.py`
4. Access API documentation through Swagger UI at `http://localhost:8000/docs`.

## Key Highlights

* Dynamic per-serving nutritional analysis for cooked dishes.
* Supports natural-language ingredient quantities and kitchen measurements.
* Fuzzy recipe matching for handling spelling variations and incomplete dish names.
* Modular FastAPI + Flask architecture for scalability and maintainability.
* Self-expanding ingredient database through automatic Nutritionix integration.
* Cost-effective alternative to laboratory-based food analysis.
* Integration-ready with interactive Swagger documentation.
* Requires the external `recipes.pkl` dataset to operate.
