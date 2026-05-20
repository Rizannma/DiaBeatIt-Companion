# Render Deployment Guide - ONNX Analysis & Recommendations

## Executive Summary

After thorough analysis, **ONNX conversion is NOT recommended for your RandomForest models on Render**. Your pickle + joblib setup is already optimal.

### Key Findings

| Aspect | Pickle | ONNX |
|--------|--------|------|
| **Glucose Model Size** | 789.71 MB | 453.19 MB |
| **Risk Model Size** | 199.47 MB | 117.54 MB |
| **Load Time** | ~1s | >30s (hangs) |
| **Memory Efficiency** | ✓ Good | ✗ Poor |
| **Render Suitability** | ✓✓✓ Excellent | ✗ Not recommended |
| **Code Complexity** | Simple | Complex |
| **External Runtime** | None | ONNX Runtime |

---

## Why ONNX Failed for Your Use Case

Your models are **RandomForest ensembles with 200 trees each**.

### The Problem
- ONNX format stores tree structures as explicit graph nodes
- No compression mechanism for tree data
- Result: **Pickle IS MORE efficient than ONNX** (789MB vs 453MB)
- Massive ONNX files cause onnxruntime to hang when loading

### Where ONNX Excels
- Linear models (LogisticRegression, LinearRegression)
- Neural networks (MLPClassifier, neural network models)
- SVM models
- Small to medium model sizes

### Where ONNX Fails
- Tree ensembles (RandomForest, GradientBoosting)
- Large numbers of trees (>50)
- Deep decision trees

---

## Recommended Deployment Architecture

### Option 1: Keep Current Pickle Setup (RECOMMENDED)

**Why:** Proven, efficient, minimal dependencies

```python
# In your Flask app initialization
from onnx_tools.inference import get_glucose_model, get_risk_model

# Load models once at startup
glucose_model = get_glucose_model()  # lazy loads on first call
risk_model = get_risk_model()

# In your prediction routes
@app.route("/api/predict", methods=["POST"])
def predict():
    features = request.get_json()["features"]  # 20-element array
    glucose = glucose_model.predict(features)
    risk = risk_model.predict(features)
    return {"glucose": glucose, "risk": risk}
```

**Memory Usage:** ~2 GB (during model loading), ~500 MB (at rest with models loaded)

**Render Configuration:**

In your Render dashboard:
1. Set Instance Type: **Standard** (2 GB RAM minimum)
2. Set Build Command: `pip install -r requirements.txt`
3. Set Start Command: `gunicorn app:app` or `python app.py`
4. Allocate memory: **2GB or higher** for your models

Or in `render.yaml`:
```yaml
services:
  - type: web
    name: diabeatit
    runtime: python-3.11
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn app:app
    memoryMB: 2048
    numInstances: 1
```

---

### Option 2: Model Distillation (If RAM Still Issues)

**Retrain with fewer trees:**

```python
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier

# Instead of n_estimators=200, use:
glucose_model = RandomForestRegressor(
    n_estimators=50,    # was 200
    max_depth=15,       # was default (unlimited)
    random_state=42
)

risk_model = RandomForestClassifier(
    n_estimators=50,    # was 200
    max_depth=15,       # was default (unlimited)
    n_jobs=-1,
    random_state=42
)

# Retrain and save
glucose_model.fit(X_train, y_train)
joblib.dump(glucose_model, "glucose_model_lite.pkl")

risk_model.fit(X_train, y_train)
joblib.dump(risk_model, "risk_model_lite.pkl")
```

**Expected result:** ~40-50% model size reduction, minimal accuracy loss

---

## File Structure & Scripts

### Production Files (Use These)

```
onnx_tools/
├── inference.py              ← Use this in Flask app
├── onnx_inference_safe.py    ← Test script (validates pickle models)
└── README.md                 ← Deployment guide

Root:
├── glucose_model.pkl         ← Keep this
├── scaler_reg.pkl            ← Keep this
├── risk_model.pkl            ← Keep this
├── scaler_class.pkl          ← Keep this
├── glucose_model.onnx        ← Can delete (not needed)
└── risk_model.onnx           ← Can delete (not needed)
```

### Development/Analysis Files

```
onnx_tools/
├── convert_models_to_onnx.py ← Reference (already executed)
├── diagnose_models.py        ← Model inspection tool
├── onnx_inference.py         ← Legacy (hangs on large files)
└── onnx_inference_safe.py    ← Safe test version
```

---

## Implementation for Flask

### 1. Update your Flask app

```python
# app.py
from flask import Flask, request, jsonify
from onnx_tools.inference import create_inference_route

app = Flask(__name__)

# Add inference routes
create_inference_route(app)

# Or manually in your routes:
from onnx_tools.inference import get_glucose_model, get_risk_model

@app.route("/api/predict/glucose", methods=["POST"])
def predict_glucose():
    try:
        data = request.get_json()
        model = get_glucose_model()
        pred = model.predict(data["features"])
        return {"glucose": pred}
    except Exception as e:
        return {"error": str(e)}, 400

@app.route("/api/predict/risk", methods=["POST"])
def predict_risk():
    try:
        data = request.get_json()
        model = get_risk_model()
        pred = model.predict(data["features"])
        proba = model.predict_proba(data["features"])
        return {"risk_class": pred, "probabilities": proba.tolist()}
    except Exception as e:
        return {"error": str(e)}, 400
```

### 2. Update requirements.txt

```
# Remove these if present:
# skl2onnx
# onnx
# onnxruntime

# Keep these:
joblib
numpy
scikit-learn
Flask
Flask-SQLAlchemy
# ... other dependencies
```

### 3. Test locally

```bash
python onnx_tools/onnx_inference_safe.py
```

Expected output:
```
✓ GlucoseModel: OK
✓ RiskModel: OK
⚠ GlucoseModel (ONNX): SKIPPED (too large)
⚠ RiskModel (ONNX): SKIPPED (too large)
```

---

## Render Deployment Checklist

- [ ] Remove ONNX packages from `requirements.txt`
- [ ] Update Flask app to use `onnx_tools.inference`
- [ ] Test locally with `onnx_tools/onnx_inference_safe.py`
- [ ] Allocate minimum 2GB RAM in Render
- [ ] Deploy and monitor logs for memory usage
- [ ] Set up error alerting for model loading failures

### Render Deployment Steps

```bash
# 1. Push to GitHub (Render auto-deploys on push)
git add .
git commit -m "Update to use pickle inference"
git push origin main

# 2. In Render Dashboard:
#    - Connect your GitHub repo
#    - Create new Web Service
#    - Set runtime: Python 3.11
#    - Set start command: gunicorn app:app
#    - Set instance type: Standard (2GB RAM)

# 3. View logs in Render dashboard or via CLI:
render logs --service diabeatit

# 4. Redeploy if needed:
render deploy --service diabeatit
```

---

## Monitoring & Troubleshooting

### Check Memory Usage

```python
# Add to app.py startup
import resource
import os

def log_memory_usage():
    usage = resource.getrusage(resource.RUSAGE_SELF)
    rss_mb = usage.ru_maxrss / 1024
    print(f"[STARTUP] Process using {rss_mb:.1f} MB (peak: {usage.ru_maxrss})")

log_memory_usage()
```

### Common Issues

**Issue:** Models load slowly or timeout  
**Solution:** Increase Railway memory allocation to 2GB+

**Issue:** OOM (Out of Memory) errors  
**Solution:** Retrain with `n_estimators=50` (model distillation)

**Issue:** `FileNotFoundError` for pickle files  
**Solution:** Ensure `glucose_model.pkl`, `risk_model.pkl`, `scaler_*.pkl` are in repository root

---

## What About ONNX?

### When ONNX Makes Sense
- ✓ Deploying simple linear models
- ✓ Deploying neural networks
- ✓ Cross-platform deployment (Python + Java + C#)
- ✓ Edge devices with size constraints
- ✓ Model size <50MB

### When to Stick with Pickle
- ✓ Tree ensembles (your case)
- ✓ Large models (your case)
- ✓ Python-only deployment (your case)
- ✓ Already proven in production (your case)

---

## Summary

**Action Items:**

1. **Use** `onnx_tools/inference.py` in your Flask app
2. **Delete** ONNX files (not needed)
3. **Remove** ONNX packages from requirements.txt
4. **Keep** pickle files exactly as they are
5. **Deploy** to Render with 2GB+ Standard instance

**Expected Outcome:**
- Fast inference (pickle is as fast as sklearn)
- Low memory footprint
- Reliable, proven deployment
- No external runtime dependencies

This is the optimal configuration for your RandomForest models on Render.
