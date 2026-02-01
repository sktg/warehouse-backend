# Data handling
import pandas as pd

# Machine learning
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

# Visualization
import matplotlib.pyplot as plt
import joblib

# ---------------- LOAD DATA ----------------
df = pd.read_excel("wms_queue_output_20260201_075839_FINAL.xlsx")

# Clean column names
df.columns = df.columns.str.strip()

print("Columns in dataset:\n", df.columns.tolist())

# ---------------- FILTER COMPLETED TASKS ----------------
df = df[df["Task Status"] == "Completed"].copy()

# ---------------- TIME FEATURES ----------------
df["Task Completion DateTime"] = pd.to_datetime(df["Task Completion DateTime"])

df["hour"] = df["Task Completion DateTime"].dt.hour
df["day_of_week"] = df["Task Completion DateTime"].dt.dayofweek
df["is_afternoon"] = (df["hour"] >= 13).astype(int)

# ---------------- FEATURES & TARGET ----------------
features = [
    "Warehouse Task",
    "Task Type",
    "Resource Allocated",
    "hour",
    "day_of_week",
    "is_afternoon"
]

target = "Task Time taken (mins)"

X = df[features]
y = df[target]

# Convert text columns to numbers
X = pd.get_dummies(X, drop_first=True)

# ---------------- TRAIN TEST SPLIT ----------------
X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42
)

# ---------------- MODEL ----------------
model = GradientBoostingRegressor(
    n_estimators=200,
    learning_rate=0.05,
    max_depth=3,
    random_state=42
)

model.fit(X_train, y_train)

# ---------------- EVALUATION ----------------
predictions = model.predict(X_test)

print("MAE:", mean_absolute_error(y_test, predictions))
print("R² :", r2_score(y_test, predictions))

# ---------------- FEATURE IMPORTANCE ----------------
importances = pd.Series(
    model.feature_importances_,
    index=X.columns
).sort_values(ascending=False)

importances.head(10).plot(kind="bar")
plt.title("Top Feature Importance")
plt.show()

# ---------------- SAVE MODEL ----------------
joblib.dump(model, "task_time_model.pkl")
print("Model saved as task_time_model.pkl")

joblib.dump(X.columns.tolist(), "model_columns.pkl")
print("Model columns saved as model_columns.pkl")

# ---------------- EXAMPLE PREDICTION ----------------
example = pd.DataFrame([{
    "Warehouse Task": "WT01",
    "Task Type": "Picking",
    "Resource Allocated": "RSG02",
    "hour": 15,
    "day_of_week": 1,
    "is_afternoon": 1
}])

example = pd.get_dummies(example)
example = example.reindex(columns=X.columns, fill_value=0)

print("Predicted time (mins):", model.predict(example))
