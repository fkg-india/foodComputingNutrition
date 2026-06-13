import os
import json
import ast
import pandas as pd

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    jsonl_path = os.path.join(base_dir, "recipes.jsonl")
    pkl_path = os.path.join(base_dir, "recipes.pkl")

    print(f"Reading {jsonl_path}...")
    data_list = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line)
            # Evaluate fields that are string representations of Python lists/dicts
            for field in ["ingredient_description", "instructions"]:
                val = data.get(field)
                if isinstance(val, str):
                    try:
                        data[field] = ast.literal_eval(val)
                    except Exception as e:
                        print(f"Error parsing field {field}: {e}")
            data_list.append(data)

    df = pd.DataFrame(data_list)
    print(f"Writing {pkl_path}...")
    df.to_pickle(pkl_path)
    print("Done! recipes.pkl successfully created.")

if __name__ == "__main__":
    main()
