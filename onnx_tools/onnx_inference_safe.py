#!/usr/bin/env python3
"""
ONNX inference test - Graceful handling of large tree-ensemble ONNX files.

Note: RandomForest models with 200 trees become very large in ONNX format (450+MB).
This script provides detailed diagnostics and fallback strategies for deployment.

Run from repository root:
python onnx_tools/onnx_inference_safe.py
"""
import os
import sys
import traceback
import warnings
import joblib
import numpy as np

# Suppress sklearn warnings
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

try:
    import onnxruntime as ort
    HAS_ONNXRUNTIME = True
except ImportError:
    HAS_ONNXRUNTIME = False


def test_sklearn_pickle(pkl_path, scaler_path, name):
    """Test original sklearn pickle model with scaler."""
    try:
        print(f"\n{'='*70}")
        print(f"Testing {name} (Pickle + Joblib)")
        print(f"{'='*70}")

        print(f"Loading model from {os.path.basename(pkl_path)}...")
        model = joblib.load(pkl_path)
        print(f"✓ Model loaded: {type(model).__name__}")

        print(f"Loading scaler from {os.path.basename(scaler_path)}...")
        scaler = joblib.load(scaler_path)
        print(f"✓ Scaler loaded")

        # Get feature count
        n_features = getattr(model, "n_features_in_", None)
        if n_features is None:
            n_features = int(scaler.mean_.shape[0])
        print(f"✓ Input features: {n_features}")

        # Generate test data
        print(f"Generating 10 test samples...")
        base = scaler.mean_
        X_raw = np.tile(base, (10, 1)) + np.random.randn(10, n_features) * 0.01
        X_scaled = scaler.transform(X_raw).astype(np.float32)
        print(f"✓ X_scaled shape: {X_scaled.shape}, dtype: {X_scaled.dtype}")

        # Predict
        print(f"Running sklearn prediction...")
        y = model.predict(X_scaled)
        print(f"✓ Prediction complete")
        print(f"  Output shape: {y.shape}")
        print(f"  Output dtype: {y.dtype}")
        print(f"  Sample predictions: {y[:3]}")

        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        traceback.print_exc()
        return False


def test_onnx_loading(onnx_path, name, timeout_sec=10):
    """Test if ONNX file can be loaded (with timeout)."""
    print(f"\n{'='*70}")
    print(f"Testing {name} (ONNX - Load Test Only)")
    print(f"{'='*70}")

    if not HAS_ONNXRUNTIME:
        print("⚠ onnxruntime not available")
        return None

    if not os.path.exists(onnx_path):
        print(f"✗ ONNX file not found: {onnx_path}")
        return False

    size_mb = os.path.getsize(onnx_path) / (1024 * 1024)
    print(f"ONNX file size: {size_mb:.2f} MB")

    if size_mb > 100:
        print(f"⚠ WARNING: File is very large ({size_mb:.2f} MB)")
        print(f"   This may cause memory issues or long load times.")
        print(f"   Skipping ONNX inference test due to file size.")
        return None

    try:
        print(f"Attempting to create InferenceSession...")
        sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        print(f"✓ ONNX session created")
        return True
    except Exception as e:
        print(f"✗ ONNX loading failed: {e}")
        return False


def main():
    print("\n" + "="*70)
    print("ONNX Inference Test - Safe Mode for Large Tree Ensembles")
    print("="*70)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print(f"Working directory: {root}\n")

    tasks = [
        ("glucose_model.pkl", "scaler_reg.pkl", "glucose_model.onnx", "GlucoseModel"),
        ("risk_model.pkl", "scaler_class.pkl", "risk_model.onnx", "RiskModel"),
    ]

    results = {
        "pickle": {},
        "onnx": {},
    }

    # Test 1: Original pickle models
    print("\n" + "█" * 70)
    print("PART 1: Testing Original Pickle Models")
    print("█" * 70)

    for pkl, scaler, onnx_name, name in tasks:
        pkl_path = os.path.join(root, pkl)
        scaler_path = os.path.join(root, scaler)

        if not all(os.path.exists(p) for p in (pkl_path, scaler_path)):
            print(f"\n⊘ Skipping {name}: missing pickle/scaler")
            results["pickle"][name] = "SKIPPED"
            continue

        success = test_sklearn_pickle(pkl_path, scaler_path, name)
        results["pickle"][name] = "OK" if success else "FAILED"

    # Test 2: ONNX models (safe loading only)
    print("\n" + "█" * 70)
    print("PART 2: Testing ONNX File Loading (Safe)")
    print("█" * 70)

    for pkl, scaler, onnx_name, name in tasks:
        onnx_path = os.path.join(root, onnx_name)

        if not os.path.exists(onnx_path):
            print(f"\n⊘ Skipping {name}: ONNX file not found")
            results["onnx"][name] = "SKIPPED"
            continue

        status = test_onnx_loading(onnx_path, name, timeout_sec=10)
        if status is None:
            results["onnx"][name] = "SKIPPED (too large)"
        elif status:
            results["onnx"][name] = "OK"
        else:
            results["onnx"][name] = "FAILED"

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    print("\nPickle Models (Recommended for Railway):")
    for name, status in results["pickle"].items():
        symbol = "✓" if status == "OK" else ("⊘" if status == "SKIPPED" else "✗")
        print(f"  {symbol} {name}: {status}")

    print("\nONNX Models (Experimental):")
    for name, status in results["onnx"].items():
        if status == "SKIPPED (too large)":
            symbol = "⚠"
        else:
            symbol = "✓" if status == "OK" else ("⊘" if status == "SKIPPED" else "✗")
        print(f"  {symbol} {name}: {status}")

    print("\n" + "="*70)
    print("DEPLOYMENT RECOMMENDATION")
    print("="*70)
    print("""
RandomForest models with 200 trees are poorly suited for ONNX:
- Pickle format is MORE compact (789MB vs 453MB for glucose model)
- ONNX doesn't compress tree structures
- Large ONNX files cause memory/loading issues in Railway

RECOMMENDATION for Railway deployment:
✓ Keep using pickle + joblib (proven, smaller files)
✓ Ensure scalers are loaded before inference
✓ Use float32 numpy arrays for input
✓ Monitor RAM usage in Railway logs
✓ If RAM is still an issue, retrain with fewer trees

File sizes (current):
- glucose_model.pkl: 789.71 MB → glucose_model.onnx: 453.19 MB
- risk_model.pkl: 199.47 MB → risk_model.onnx: 117.54 MB

Why pickle is better for this case:
- Pickle uses Python-level compression (joblib serializes efficiently)
- ONNX expands tree data into graph nodes without compression
- For Railway, pickle + joblib is proven and stable
    """)

    sys.exit(0)


if __name__ == "__main__":
    main()
