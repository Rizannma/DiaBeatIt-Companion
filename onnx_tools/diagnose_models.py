#!/usr/bin/env python3
"""
Diagnostic script to inspect pickle models and ONNX files.

Run from repository root:
python onnx_tools/diagnose_models.py
"""
import os
import sys
import joblib
import numpy as np

try:
    import onnx
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False


def diagnose_pickle(pkl_path, name):
    """Load and inspect a pickle model."""
    print(f"\n{'='*70}")
    print(f"Inspecting {name} ({os.path.basename(pkl_path)})")
    print(f"{'='*70}")
    
    if not os.path.exists(pkl_path):
        print(f"✗ File not found: {pkl_path}")
        return
    
    size_mb = os.path.getsize(pkl_path) / (1024 * 1024)
    print(f"File size: {size_mb:.2f} MB")
    
    try:
        model = joblib.load(pkl_path)
        print(f"Model type: {type(model).__name__}")
        print(f"Model module: {type(model).__module__}")
        
        # Print key attributes
        if hasattr(model, "n_features_in_"):
            print(f"  n_features_in_: {model.n_features_in_}")
        if hasattr(model, "n_classes_"):
            print(f"  n_classes_: {model.n_classes_}")
        if hasattr(model, "n_estimators"):
            print(f"  n_estimators: {model.n_estimators} (tree ensemble!)")
        if hasattr(model, "classes_"):
            print(f"  classes_: {model.classes_}")
        if hasattr(model, "coef_"):
            coef = model.coef_
            print(f"  coef_ shape: {coef.shape}")
        if hasattr(model, "intercept_"):
            print(f"  intercept_: {model.intercept_}")
        
        # For tree ensembles
        if hasattr(model, "estimators_"):
            print(f"  estimators_ shape: {np.asarray(model.estimators_).shape}")
            print(f"  Total estimators: {len(model.estimators_) if hasattr(model.estimators_, '__len__') else 'unknown'}")
            
    except Exception as e:
        print(f"✗ Error loading model: {e}")
        import traceback
        traceback.print_exc()


def diagnose_onnx(onnx_path, name):
    """Load and inspect an ONNX model."""
    print(f"\nONNX File Analysis:")
    print(f"-" * 70)
    
    if not os.path.exists(onnx_path):
        print(f"✗ File not found: {onnx_path}")
        return
    
    size_mb = os.path.getsize(onnx_path) / (1024 * 1024)
    print(f"File size: {size_mb:.2f} MB")
    
    if not HAS_ONNX:
        print("⚠ onnx package not installed, skipping detailed analysis")
        return
    
    try:
        model_proto = onnx.load(onnx_path)
        print(f"ONNX opset version: {model_proto.opset_import[0].version if model_proto.opset_import else 'unknown'}")
        print(f"ONNX IR version: {model_proto.ir_version}")
        
        # Graph info
        graph = model_proto.graph
        print(f"\nGraph inputs: {len(graph.input)}")
        for inp in graph.input:
            print(f"  - {inp.name}")
        
        print(f"\nGraph outputs: {len(graph.output)}")
        for out in graph.output:
            print(f"  - {out.name}")
        
        print(f"\nGraph nodes: {len(graph.node)}")
        
        # Count node types
        node_types = {}
        for node in graph.node:
            op = node.op_type
            node_types[op] = node_types.get(op, 0) + 1
        
        print("\nNode type distribution:")
        for op, count in sorted(node_types.items(), key=lambda x: -x[1]):
            print(f"  {op}: {count}")
        
    except Exception as e:
        print(f"✗ Error loading ONNX: {e}")
        import traceback
        traceback.print_exc()


def main():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    tasks = [
        ("glucose_model.pkl", "glucose_model.onnx", "GlucoseModel (Regression)"),
        ("risk_model.pkl", "risk_model.onnx", "RiskModel (Classification)"),
    ]
    
    for pkl, onnx_name, name in tasks:
        pkl_path = os.path.join(root, pkl)
        onnx_path = os.path.join(root, onnx_name)
        
        diagnose_pickle(pkl_path, name)
        diagnose_onnx(onnx_path, name)
    
    print(f"\n{'='*70}")
    print("Diagnosis Summary")
    print(f"{'='*70}")
    print("""
If ONNX files are much larger than pickle files, likely causes:
1. Tree-based ensembles (RandomForest, GradientBoosting) expand dramatically in ONNX
   - Each tree is expanded into sequential operations
   - No compression in ONNX format
   
2. Large coefficient matrices that aren't efficiently encoded

3. skl2onnx may not be optimizing for deployment

Solutions:
- Use simpler models (linear, SVM) if possible
- Use model distillation to reduce complexity
- Consider keeping pickle + joblib for now if ONNX is too large
- Reduce tree depth or ensemble size in training
    """)


if __name__ == "__main__":
    main()
