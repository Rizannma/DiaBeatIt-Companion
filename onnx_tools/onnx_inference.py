#!/usr/bin/env python3
"""
ONNX inference test script with comprehensive logging and error handling.

Loads scalers, prepares float32 inputs, runs sklearn and ONNX models,
and compares predictions with detailed logging.

Run from repository root:
python onnx_tools/onnx_inference.py
"""
import os
import sys
import signal
import traceback
import warnings
import threading
import joblib
import numpy as np
import onnxruntime as ort

# Suppress sklearn feature name warnings during transform (harmless)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


class TimeoutError(Exception):
    """Timeout exception for long-running operations."""
    pass


def load_onnx_with_timeout(onnx_path, timeout_sec=30):
    """Load ONNX model with timeout to prevent hanging."""
    result = {"sess": None, "error": None}

    def _load():
        try:
            print(f"    [thread] Loading ONNX with onnxruntime.InferenceSession...")
            result["sess"] = ort.InferenceSession(
                onnx_path,
                providers=["CPUExecutionProvider"],
                sess_options=ort.SessionOptions()
            )
            print(f"    [thread] ONNX session created successfully")
        except Exception as e:
            print(f"    [thread] Error: {e}")
            result["error"] = e

    thread = threading.Thread(target=_load, daemon=True)
    thread.start()
    print(f"    Waiting for thread to complete (timeout={timeout_sec}s)...")
    thread.join(timeout=timeout_sec)

    if thread.is_alive():
        print(f"    ✗ Thread still running after {timeout_sec}s!")
        raise TimeoutError(
            f"ONNX session creation timed out after {timeout_sec}s (possible hang in onnxruntime; file may be too large)"
        )

    if result["error"]:
        raise result["error"]

    if result["sess"] is None:
        raise RuntimeError("ONNX session creation failed (returned None)")

    return result["sess"]


def load_and_prepare(pickle_model_path, scaler_path, n_samples=5, name="Model"):
    """Load model, scaler, prepare test data. Returns (model, X_scaled_float32)."""
    try:
        print(f"  [{name}] Loading model from {os.path.basename(pickle_model_path)}...")
        model = joblib.load(pickle_model_path)
        print(f"  [{name}] ✓ Model loaded successfully")

        print(f"  [{name}] Loading scaler from {os.path.basename(scaler_path)}...")
        scaler = joblib.load(scaler_path)
        print(f"  [{name}] ✓ Scaler loaded successfully")

        # Determine feature count
        print(f"  [{name}] Determining input feature count...")
        n_features = getattr(model, "n_features_in_", None)
        if n_features is None:
            if hasattr(scaler, "mean_"):
                n_features = int(scaler.mean_.shape[0])
                print(f"  [{name}]   → Inferred from scaler.mean_: {n_features} features")
            else:
                raise RuntimeError("Unable to infer feature count from model or scaler")
        else:
            print(f"  [{name}]   → Read from model.n_features_in_: {n_features} features")

        # Build reproducible small test set around scaler mean
        print(f"  [{name}] Generating {n_samples} test samples...")
        base = getattr(scaler, "mean_", np.zeros(n_features))
        X_raw = np.tile(base, (n_samples, 1)) + np.random.randn(n_samples, n_features) * 1e-2
        print(f"  [{name}]   → X_raw shape: {X_raw.shape}, dtype: {X_raw.dtype}")

        print(f"  [{name}] Scaling input data...")
        X_scaled = scaler.transform(X_raw)
        print(f"  [{name}]   → X_scaled shape: {X_scaled.shape}, dtype: {X_scaled.dtype}")

        # Enforce float32
        print(f"  [{name}] Converting to float32...")
        X_scaled = X_scaled.astype(np.float32)
        print(f"  [{name}]   → Final input shape: {X_scaled.shape}, dtype: {X_scaled.dtype}")
        print(f"  [{name}] ✓ Data preparation complete")

        return model, X_scaled, n_features
    except Exception as e:
        print(f"  [{name}] ✗ Error during load_and_prepare:")
        traceback.print_exc()
        raise


def run_onnx(onnx_path, X, name="Model"):
    """Load ONNX model and run inference. Returns outputs."""
    try:
        print(f"  [{name}] Checking ONNX file: {os.path.basename(onnx_path)}...")
        if not os.path.exists(onnx_path):
            raise FileNotFoundError(f"ONNX file not found: {onnx_path}")
        file_size_mb = os.path.getsize(onnx_path) / (1024 * 1024)
        print(f"  [{name}]   → File exists, size: {file_size_mb:.2f} MB")
        
        if file_size_mb > 100:
            print(f"  [{name}]   ⚠ WARNING: ONNX file is very large ({file_size_mb:.2f} MB)")
            print(f"  [{name}]      Loading large files may take significant time...")

        print(f"  [{name}] Creating ONNX InferenceSession (timeout=30s)...")
        sess = load_onnx_with_timeout(onnx_path, timeout_sec=30)
        print(f"  [{name}] ✓ ONNX session created successfully")

        print(f"  [{name}] Checking ONNX input/output metadata...")
        input_name = sess.get_inputs()[0].name
        input_shape = sess.get_inputs()[0].shape
        print(f"  [{name}]   → Input name: '{input_name}'")
        print(f"  [{name}]   → Input shape: {input_shape}")
        print(f"  [{name}]   → Actual X shape: {X.shape}, dtype: {X.dtype}")

        # Validate shape match
        if X.dtype != np.float32:
            print(f"  [{name}] ⚠ Warning: X dtype is {X.dtype}, expected float32. Converting...")
            X = X.astype(np.float32)

        print(f"  [{name}] Running ONNX inference...")
        outputs = sess.run(None, {input_name: X})
        print(f"  [{name}] ✓ Inference completed")
        print(f"  [{name}]   → Number of outputs: {len(outputs)}")
        print(f"  [{name}]   → Output[0] shape: {outputs[0].shape}, dtype: {outputs[0].dtype}")

        return outputs
    except TimeoutError as e:
        print(f"  [{name}] ✗ Timeout: {e}")
        traceback.print_exc()
        raise
    except Exception as e:
        print(f"  [{name}] ✗ Error during ONNX inference:")
        traceback.print_exc()
        raise


def compare(pkl_path, scaler_path, onnx_path, name):
    """Load models, run inference, compare predictions."""
    try:
        print(f"\n{'='*70}")
        print(f"Testing {name}")
        print(f"{'='*70}")

        print("Step 1: Loading pickle model and scaler...")
        model, X, n_features = load_and_prepare(pkl_path, scaler_path, name=name)

        print("\nStep 2: Running sklearn prediction...")
        print(f"  [{name}] Calling model.predict(X) with X shape {X.shape}...")
        y_sklearn = model.predict(X)
        print(f"  [{name}] ✓ sklearn prediction complete")
        print(f"  [{name}]   → y_sklearn shape: {y_sklearn.shape}, dtype: {y_sklearn.dtype}")

        print("\nStep 3: Loading ONNX model and running inference...")
        onnx_outs = run_onnx(onnx_path, X, name=name)

        print("\nStep 4: Comparing outputs...")
        y_onnx = np.asarray(onnx_outs[0])
        y_sklearn = np.asarray(y_sklearn)
        print(f"  [{name}] y_onnx shape: {y_onnx.shape}, dtype: {y_onnx.dtype}")
        print(f"  [{name}] y_sklearn shape: {y_sklearn.shape}, dtype: {y_sklearn.dtype}")

        # Align shapes for basic comparison
        if y_onnx.shape != y_sklearn.shape:
            print(f"  [{name}] Shape mismatch detected, checking for classifier case...")
            # Classifier probability vs labels case
            if y_onnx.ndim == 2 and y_onnx.shape[1] > 1:
                print(f"  [{name}]   → ONNX output is probabilities ({y_onnx.shape})")
                y_onnx_labels = np.argmax(y_onnx, axis=1)
                y_sklearn_labels = y_sklearn
                print(f"  [{name}]   → sklearn output is labels ({y_sklearn_labels.shape})")
                mismatches = int((y_onnx_labels != y_sklearn_labels).sum())
                match_pct = 100.0 * (1.0 - mismatches / len(y_sklearn))
                print(f"  [{name}] ✓ Label comparison: {mismatches} mismatches / {len(y_sklearn)} = {match_pct:.1f}% match")
                return True
            else:
                print(f"  [{name}] ✗ Shape mismatch: sklearn {y_sklearn.shape}, onnx {y_onnx.shape}")
                return False

        # Regressor case: direct shape match
        y_sklearn_f32 = y_sklearn.astype(np.float32)
        y_onnx_f32 = y_onnx.astype(np.float32)
        diff = np.abs(y_sklearn_f32 - y_onnx_f32)
        max_abs = float(np.max(diff))
        mean_abs = float(np.mean(diff))
        print(f"  [{name}] ✓ Regression output comparison:")
        print(f"  [{name}]   → max absolute difference: {max_abs:.6g}")
        print(f"  [{name}]   → mean absolute difference: {mean_abs:.6g}")
        return True

    except TimeoutError as e:
        print(f"\n✗ TIMEOUT for {name}: {e}")
        return False
    except Exception as e:
        print(f"\n✗ FAILED for {name}: {e}")
        traceback.print_exc()
        return False


def main():
    """Main entry point with error handling and clean exit."""
    print("\n" + "="*70)
    print("ONNX Model Inference Test")
    print("="*70)

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    print(f"Working directory: {root}\n")

    tasks = [
        ("glucose_model.pkl", "scaler_reg.pkl", "glucose_model.onnx", "GlucoseModel"),
        ("risk_model.pkl", "scaler_class.pkl", "risk_model.onnx", "RiskModel"),
    ]

    results = {}
    for pkl, scaler, onnx_name, name in tasks:
        pkl_path = os.path.join(root, pkl)
        scaler_path = os.path.join(root, scaler)
        onnx_path = os.path.join(root, onnx_name)

        missing = [p for p in (pkl_path, scaler_path, onnx_path) if not os.path.exists(p)]
        if missing:
            print(f"\n⚠ Skipping {name}: missing files:")
            for p in missing:
                print(f"    - {os.path.basename(p)}")
            results[name] = "SKIPPED"
            continue

        try:
            success = compare(pkl_path, scaler_path, onnx_path, name)
            results[name] = "OK" if success is not False else "FAILED"
        except Exception as e:
            print(f"\n✗ Exception for {name}:")
            traceback.print_exc()
            results[name] = "ERROR"

    print(f"\n\n{'='*70}")
    print("Summary")
    print(f"{'='*70}")
    for name, status in results.items():
        symbol = "✓" if status == "OK" else ("⊘" if status == "SKIPPED" else "✗")
        print(f"  {symbol} {name}: {status}")

    # Exit with appropriate code
    has_error = any(s in ("ERROR", "FAILED") for s in results.values())
    exit_code = 1 if has_error else 0
    print(f"\nExit code: {exit_code}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
