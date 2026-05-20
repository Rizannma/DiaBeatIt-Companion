#!/usr/bin/env python3
"""
Production-ready inference module with lazy Hugging Face Hub loading.

Assets are downloaded only on first inference call, cached by
huggingface_hub on disk and cached in memory in this process.
"""
import os
import warnings
from threading import Lock
from typing import Dict, Union

import joblib
import numpy as np
import onnxruntime as ort
from huggingface_hub import hf_hub_download


warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

HF_REPO_ID = os.getenv("HF_MODEL_REPO_ID", "stella001228/diabeatit-models")
HF_REVISION = os.getenv("HF_MODEL_REVISION", "main")


class ONNXInferenceBase:
    """Base class with lazy loading + in-memory cache for ONNX session and scaler."""

    def __init__(self, model_filename: str, scaler_filename: str, name: str):
        self.name = name
        self.model_filename = model_filename
        self.scaler_filename = scaler_filename
        self.model = None
        self.scaler = None
        self.input_name = None
        self.expected_features = None
        self._lock = Lock()

    def load_model(self):
        """Lazy load model/scaler only when first prediction is requested."""
        if self.model is not None and self.scaler is not None:
            return

        with self._lock:
            if self.model is not None and self.scaler is not None:
                return

            model_path = hf_hub_download(
                repo_id=HF_REPO_ID,
                filename=self.model_filename,
                revision=HF_REVISION,
            )
            scaler_path = hf_hub_download(
                repo_id=HF_REPO_ID,
                filename=self.scaler_filename,
                revision=HF_REVISION,
            )

            self.scaler = joblib.load(scaler_path)
            self.model = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
            self.input_name = self.model.get_inputs()[0].name

            raw_shape = self.model.get_inputs()[0].shape
            if len(raw_shape) >= 2 and isinstance(raw_shape[1], int):
                self.expected_features = raw_shape[1]
            elif hasattr(self.scaler, "n_features_in_"):
                self.expected_features = int(self.scaler.n_features_in_)

            print(f"[{self.name}] Model and scaler loaded from Hugging Face Hub")

    def _prepare_input(self, features: Union[Dict, np.ndarray]) -> np.ndarray:
        """Convert features to scaled float32 numpy array and validate feature count."""
        if isinstance(features, dict):
            features = np.array([list(features.values())], dtype=np.float32)
        elif not isinstance(features, np.ndarray):
            features = np.array(features, dtype=np.float32)

        if features.ndim == 1:
            features = features.reshape(1, -1)

        if self.expected_features is not None and features.shape[1] != self.expected_features:
            raise ValueError(
                f"[{self.name}] Expected {self.expected_features} features, got {features.shape[1]}"
            )

        scaled = self.scaler.transform(features).astype(np.float32)
        return scaled


class GlucoseInference(ONNXInferenceBase):
    """Glucose prediction model with lazy HF download."""

    def __init__(self):
        super().__init__(
            model_filename="glucose_model.onnx",
            scaler_filename="scaler_reg.pkl",
            name="GlucoseModel",
        )

    def predict(self, features: Union[Dict, np.ndarray]) -> float:
        self.load_model()
        X = self._prepare_input(features)
        pred = self.model.run(None, {self.input_name: X})[0]
        return float(np.asarray(pred).reshape(-1)[0])


class RiskInference(ONNXInferenceBase):
    """Risk prediction model with lazy HF download."""

    def __init__(self):
        super().__init__(
            model_filename="risk_model.onnx",
            scaler_filename="scaler_class.pkl",
            name="RiskModel",
        )

    def predict(self, features: Union[Dict, np.ndarray]) -> int:
        self.load_model()
        X = self._prepare_input(features)
        outputs = self.model.run(None, {self.input_name: X})
        labels = np.asarray(outputs[0]).reshape(-1)
        return int(labels[0])

    def predict_proba(self, features: Union[Dict, np.ndarray]) -> np.ndarray:
        self.load_model()
        X = self._prepare_input(features)
        outputs = self.model.run(None, {self.input_name: X})

        if len(outputs) < 2:
            return np.array([], dtype=np.float32)

        proba_output = outputs[1]

        if isinstance(proba_output, list) and proba_output and isinstance(proba_output[0], dict):
            row = proba_output[0]
            ordered = [v for _, v in sorted(row.items(), key=lambda kv: kv[0])]
            return np.asarray(ordered, dtype=np.float32)

        proba = np.asarray(proba_output)
        return proba[0].astype(np.float32)


_glucose_model = None
_risk_model = None


def get_glucose_model() -> GlucoseInference:
    """Get or create glucose singleton (no preload)."""
    global _glucose_model
    if _glucose_model is None:
        _glucose_model = GlucoseInference()
    return _glucose_model


def get_risk_model() -> RiskInference:
    """Get or create risk singleton (no preload)."""
    global _risk_model
    if _risk_model is None:
        _risk_model = RiskInference()
    return _risk_model


# Example Flask integration
def create_inference_route(app):
    """
    Add inference routes to Flask app.
    
    Usage:
        from flask import Flask
        from onnx_tools.inference import create_inference_route
        
        app = Flask(__name__)
        create_inference_route(app)
    """
    @app.route("/api/predict/glucose", methods=["POST"])
    def predict_glucose():
        """Predict glucose level."""
        from flask import request, jsonify
        
        try:
            data = request.get_json()
            features = np.array(data["features"], dtype=np.float32)
            
            model = get_glucose_model()
            prediction = model.predict(features)
            
            return jsonify({
                "success": True,
                "prediction": prediction,
                "model": "GlucoseModel"
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400
    
    @app.route("/api/predict/risk", methods=["POST"])
    def predict_risk():
        """Predict risk class."""
        from flask import request, jsonify
        
        try:
            data = request.get_json()
            features = np.array(data["features"], dtype=np.float32)
            
            model = get_risk_model()
            prediction = model.predict(features)
            proba = model.predict_proba(features) if hasattr(model, "predict_proba") else None
            
            return jsonify({
                "success": True,
                "prediction": int(prediction),
                "probabilities": proba.tolist() if proba is not None else None,
                "model": "RiskModel"
            })
        except Exception as e:
            return jsonify({"success": False, "error": str(e)}), 400


if __name__ == "__main__":
    print("Testing lazy Hugging Face ONNX inference...")

    glucose = GlucoseInference()
    test_features_glucose = np.random.randn(1, 20).astype(np.float32)
    pred_glucose = glucose.predict(test_features_glucose)
    print(f"✓ Glucose prediction: {pred_glucose:.2f}")

    risk = RiskInference()
    test_features_risk = np.random.randn(1, 18).astype(np.float32)
    pred_risk = risk.predict(test_features_risk)
    proba_risk = risk.predict_proba(test_features_risk)
    print(f"✓ Risk prediction: {pred_risk} (class)")
    print(f"✓ Risk probabilities: {proba_risk}")
