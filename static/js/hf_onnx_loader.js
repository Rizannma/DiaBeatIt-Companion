const HF_BASE = "https://huggingface.co/stella001228/diabeatit-models/resolve/main";

let ortModule = null;
let glucoseSession = null;
let riskSession = null;
let scalerRegBytes = null;
let scalerClassBytes = null;

async function getOrtWeb() {
  if (!ortModule) {
    ortModule = await import("https://cdn.jsdelivr.net/npm/onnxruntime-web/dist/ort.min.js");
  }
  return ortModule;
}

async function fetchBytes(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to fetch asset: ${url}`);
  }
  return new Uint8Array(await res.arrayBuffer());
}

export async function initGlucoseAssets() {
  if (glucoseSession && scalerRegBytes) {
    return { session: glucoseSession, scalerBytes: scalerRegBytes };
  }

  const ort = await getOrtWeb();

  if (!glucoseSession) {
    const modelBytes = await fetchBytes(`${HF_BASE}/glucose_model.onnx`);
    glucoseSession = await ort.InferenceSession.create(modelBytes.buffer);
  }

  if (!scalerRegBytes) {
    scalerRegBytes = await fetchBytes(`${HF_BASE}/scaler_reg.pkl`);
  }

  return { session: glucoseSession, scalerBytes: scalerRegBytes };
}

export async function initRiskAssets() {
  if (riskSession && scalerClassBytes) {
    return { session: riskSession, scalerBytes: scalerClassBytes };
  }

  const ort = await getOrtWeb();

  if (!riskSession) {
    const modelBytes = await fetchBytes(`${HF_BASE}/risk_model.onnx`);
    riskSession = await ort.InferenceSession.create(modelBytes.buffer);
  }

  if (!scalerClassBytes) {
    scalerClassBytes = await fetchBytes(`${HF_BASE}/scaler_class.pkl`);
  }

  return { session: riskSession, scalerBytes: scalerClassBytes };
}

export async function inferGlucose(inputName, inputTensor) {
  const { session } = await initGlucoseAssets();
  const feeds = {};
  feeds[inputName] = inputTensor;
  return session.run(feeds);
}

export async function inferRisk(inputName, inputTensor) {
  const { session } = await initRiskAssets();
  const feeds = {};
  feeds[inputName] = inputTensor;
  return session.run(feeds);
}
