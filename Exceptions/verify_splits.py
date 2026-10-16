import json

with open("data/processed/preprocessed.json", encoding="utf-8") as f:
    records = json.load(f)

train = [r for r in records if r["split"] == "train"]
val   = [r for r in records if r["split"] == "val"]
test  = [r for r in records if r["split"] == "test"]

print(f"Train: {len(train)}")
print(f"Val:   {len(val)}")
print(f"Test:  {len(test)}")

# ID overlap between splits
train_ids = set(r["id"] for r in train)
val_ids   = set(r["id"] for r in val)
test_ids  = set(r["id"] for r in test)

print()
print(f"Train and Test overlap: {len(train_ids & test_ids)}")
print(f"Train and Val  overlap: {len(train_ids & val_ids)}")
print(f"Val   and Test overlap: {len(val_ids & test_ids)}")

# Sample test records
print()
print("First 5 test records:")
for r in test[:5]:
    print(f"  {r['id']}  split={r['split']}  category={r['defect_category']}  label={r['label']}")

# Now simulate what training actually uses
HOLDOUT = [
    "swallows_declared_exception",
    "corrupted_state_on_exception",
    "inconsistent_with_precheck",
    "empty_catch",
]

train_seen = [
    r for r in records
    if r["split"] == "train" and r["defect_category"] not in HOLDOUT
]

print()
print(f"Records actually used for training: {len(train_seen)}")

train_used_ids = set(r["id"] for r in train_seen)
print(f"Train(used) and Test overlap: {len(train_used_ids & test_ids)}")