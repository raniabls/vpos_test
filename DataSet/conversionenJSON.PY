import pandas as pd
import json
import os

CSV_FOLDER = "DataSet/"
JSON_FOLDER = "DataSet_JSON/"

os.makedirs(JSON_FOLDER, exist_ok=True)

for filename in os.listdir(CSV_FOLDER):
    if filename.endswith(".csv"):
        path = os.path.join(CSV_FOLDER, filename)
        df = pd.read_csv(path)
        data = df.fillna("").to_dict(orient="records")
        json_path = os.path.join(JSON_FOLDER, filename.replace(".csv", ".json"))
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"{filename} -> {json_path} ✅")