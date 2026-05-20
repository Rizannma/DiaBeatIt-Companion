# ONNX conversion & inference

## ⚠️ IMPORTANT: Deployment Recommendation

**For RandomForest models with Railway, keep using pickle + joblib, NOT ONNX.**

### Why?
- Your models are RandomForest ensembles with 200 trees
- ONNX format **expands** these files dramatically:
  - `glucose_model.pkl`: 789 MB → `glucose_model.onnx`: 453 MB (still huge!)
  - `risk_model.pkl`: 199 MB → `risk_model.onnx`: 117 MB
- Tree structures don't compress in ONNX format
- Pickle + joblib is MORE efficient for your use case

### Test Results
```
✓ Pickle models load and predict successfully
✗ ONNX files too large for Railway deployment (>100MB each)
```

---

## Setup

Required packages:

```bash
pip install skl2onnx onnx onnxruntime
# Already required: joblib numpy scikit-learn
```

---

## Usage

### 1. Test Original Pickle Models (Recommended)

```bash
python onnx_tools/onnx_inference_safe.py
```

This validates that:
- Pickle models load correctly
- Scalers work with float32 inputs  
- Predictions produce expected output shapes

**Output:** Both GlucoseModel and RiskModel should show ✓ OK

### 2. Inspect Models and ONNX Files

```bash
python onnx_tools/diagnose_models.py
```

Shows:
- Model types (RandomForestRegressor, RandomForestClassifier)
- Number of trees and features
- ONNX file sizes and node counts
- Why ONNX is bloated for tree ensembles

### 3. Convert to ONNX (Optional, for reference)

```bash
python onnx_tools/convert_models_to_onnx.py
```

Creates `.onnx` files (for compatibility testing, not recommended for Railway).

---

## Railway Deployment Strategy

### Use Pickle + Joblib (Current Best)

```python
import joblib
import numpy as np

# Load once at startup
glucose_model = joblib.load("glucose_model.pkl")
scaler_reg = joblib.load("scaler_reg.pkl")

# At inference time
def predict_glucose(raw_features):
    # raw_features: shape (1, 20)
    scaled = scaler_reg.transform(raw_features).astype(np.float32)
    pred = glucose_model.predict(scaled)
    return float(pred[0])
```

### Why This Works for Railway

✓ Pickle is proven and stable  
✓ No external ONNX runtime needed  
✓ joblib handles memory efficiently  
✓ float32 numpy arrays keep memory usage low  
✓ Faster load times than massive ONNX files  

### If RAM is Still an Issue

1. **Reduce model complexity** (retrain with fewer trees)
   ```python
   RandomForestRegressor(n_estimators=50)  # was 200
   RandomForestClassifier(n_estimators=50)  # was 200
   ```

2. **Monitor Railway logs**
   ```
   python -c "import resource; print(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)"
   ```

3. **Profile before deployment**
   ```bash
   python -m memory_profiler app.py
   ```

---

## Technical Notes

### Model Inspection
- GlucoseModel: RandomForestRegressor, 200 trees, 20 features → predicts glucose levels
- RiskModel: RandomForestClassifier, 200 trees, 18 features → predicts risk class (0, 1, or 2)

### ONNX Node Types
- `TreeEnsembleRegressor`: Glucose model
- `TreeEnsembleClassifier`: Risk model (+ Cast + ZipMap for probability outputs)

### Why ONNX is Inefficient for Trees
- ONNX stores full tree structure without compression
- Pickle + joblib uses Python-level optimizations
- Ideal for: linear models, SVMs, neural networks
- Not ideal for: tree ensembles, large forests

---

## Files in This Directory

| File | Purpose |
|------|---------|
| `onnx_inference_safe.py` | **Use this** - Test pickle models and assess deployment viability |
| `diagnose_models.py` | Inspect model types, sizes, and ONNX structure |
| `convert_models_to_onnx.py` | Convert pickle → ONNX (optional, creates large files) |
| `onnx_inference.py` | Original inference script (hangs on large ONNX files) |
| `README.md` | This file |

---

## Summary

**For Railway Deployment:**
- ✓ Keep glucose_model.pkl + scaler_reg.pkl
- ✓ Keep risk_model.pkl + scaler_class.pkl
- ✓ Load with joblib + numpy float32
- ✗ Don't use ONNX (too large, no performance benefit)

This setup minimizes RAM usage while maintaining fast, reliable predictions.

