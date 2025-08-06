import os
import time
import logging
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory, jsonify, abort
from huggingface_hub import InferenceApi
from docx import Document

# ─── Load environment ─────────────────────────────────────────────────────────
load_dotenv()  # reads HF_API_TOKEN, HF_MODEL, TEMPLATES_DIR, GENERATED_DIR, FLASK_ENV

# ─── Flask setup ──────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Directories ───────────────────────────────────────────────────────────────
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
GENERATED_DIR = os.getenv("GENERATED_DIR", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# ─── Hugging Face Inference API ───────────────────────────────────────────────
HF_TOKEN = os.getenv("HF_API_TOKEN")
HF_MODEL = os.getenv("HF_MODEL", "gpt2")
hf = InferenceApi(repo_id=HF_MODEL, token=HF_TOKEN)

def call_ai(prompt: str, max_new_tokens: int = 200) -> str:
    """
    Send `prompt` to HF Inference, return the generated text.
    """
    logger.info("HF prompt: %s", prompt.replace("\n", " / "))
    # HF InferenceApi expects the inputs and a parameters dict
    response = hf(inputs=prompt, parameters={"max_new_tokens": max_new_tokens})
    # response is typically a list of dicts with 'generated_text'
    text = response[0].get("generated_text", "").strip()
    return text

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("form.html")


@app.route("/generate", methods=["POST"])
def generate():
    # 1) Gather inputs
    storage = request.form.get("storage_type", "").strip()
    volume  = request.form.get("volume", "").strip()
    days    = request.form.get("days", "").strip()
    wms     = request.form.get("wms", "").strip()
    email   = request.form.get("email", "").strip()

    if not (storage and volume and days and wms):
        abort(400, "Missing form fields")

    # 2) Build prompt & call the HF model
    prompt = (
        "You are an expert logistics quote generator for DSV. "
        "Based on the inputs, produce a clear, concise quotation including cost breakdown.\n\n"
        f"- Storage Type: {storage}\n"
        f"- Volume: {volume}\n"
        f"- Duration: {days} days\n"
        f"- Include WMS: {wms}\n"
        + (f"- Email: {email}\n" if email else "")
    )
    quote_text = call_ai(prompt, max_new_tokens=300)

    # 3) Pick the correct .docx template
    if "Chemical" in storage:
        tmpl_name = "Chemical VAS.docx"
    elif "Open Yard" in storage:
        tmpl_name = "Open Yard VAS.docx"
    else:
        tmpl_name = "Standard VAS.docx"

    template_path = os.path.join(TEMPLATES_DIR, tmpl_name)
    if not os.path.isfile(template_path):
        abort(500, f"Template not found: {tmpl_name}")

    # 4) Load, insert AI text, save
    doc = Document(template_path)
    doc.add_paragraph("")  # blank line
    doc.add_paragraph("Quotation:", style="Heading 2")
    for line in quote_text.split("\n"):
        doc.add_paragraph(line)

    filename = f"quote_{int(time.time())}_{uuid4().hex[:8]}.docx"
    out_path = os.path.join(GENERATED_DIR, filename)
    doc.save(out_path)

    # 5) Serve the file download
    return send_from_directory(
        GENERATED_DIR,
        filename,
        as_attachment=True,
        download_name=filename
    )


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_text = (data.get("message") or "").strip()
    if not user_text:
        return jsonify({"reply": "Please type something first."})

    logger.info("Chat request: %s", user_text)
    # We reuse the same HF pipeline for freeform chat
    reply = call_ai(user_text, max_new_tokens=150)
    return jsonify({"reply": reply})


# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "").lower() == "development"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
