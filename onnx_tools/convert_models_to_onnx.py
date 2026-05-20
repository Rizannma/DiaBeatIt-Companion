#!/usr/bin/env python3
"""
Convert sklearn pickle models to ONNX using skl2onnx.

Run from repository root:
python onnx_tools/convert_models_to_onnx.py

It will look for the pickles in the project root and write .onnx files there.
"""
import os
import joblib
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType


MODEL_FILES = {
    "glucose_model.pkl": ("glucose_model.onnx", "scaler_reg.pkl"),
    "risk_model.pkl": ("risk_model.onnx", "scaler_class.pkl"),
}


def get_n_features(model, scaler_path=None):
    # Try standard sklearn attribute
    n = getattr(model, "n_features_in_", None)
    if n is not None:
        return int(n)

    # Try common coefficient shapes
    if hasattr(model, "coef_"):
        coef = getattr(model, "coef_")
        try:
            return int(coef.shape[-1])
        except Exception:
            pass

    # Fall back to scaler if provided
    if scaler_path and os.path.exists(scaler_path):
        scaler = joblib.load(scaler_path)
        if hasattr(scaler, "mean_"):
            return int(scaler.mean_.shape[0])

    raise RuntimeError("Cannot determine number of input features for model; please inspect the model or provide a scaler.")


def convert(pkl_path, onnx_path, scaler_hint=None):
    model = joblib.load(pkl_path)
    n_features = get_n_features(model, scaler_hint)
    initial_type = [("input", FloatTensorType([None, n_features]))]
    onx = convert_sklearn(model, initial_types=initial_type, target_opset=12)
    with open(onnx_path, "wb") as f:
        f.write(onx.SerializeToString())
    print(f"Saved {onnx_path} with input features={n_features}")


def main():
    here = os.path.dirname(__file__) or "."
    root = os.path.abspath(os.path.join(here, ".."))
    for pkl, (onnx_name, scaler) in MODEL_FILES.items():
        pkl_path = os.path.join(root, pkl)
        onnx_path = os.path.join(root, onnx_name)
        scaler_path = os.path.join(root, scaler)
        if not os.path.exists(pkl_path):
            print(f"Skipping {pkl_path}: not found")
            continue
        convert(pkl_path, onnx_path, scaler_hint=scaler_path)


if __name__ == "__main__":
    main()
