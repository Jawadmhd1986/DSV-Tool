import os
import time
import logging
from uuid import uuid4

from dotenv import load_dotenv
from flask import (
    Flask, request, render_template,
    send_from_directory, jsonify, abort
)
from transformers import pipeline
from docx import Document

# ─── Load .env (for TEMPLATES_DIR, GENERATED_DIR, FLASK_ENV) ────────────────
load_dotenv()

# ─── Flask Setup ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
GENERATED_DIR = os.getenv("GENERATED_DIR", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# ─── Logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── HuggingFace LLM Pipeline ────────────────────────────────────────────────
hf_generator = pipeline(
    "text-generation",
    model="tiiuae/falcon-7b-instruct",  # or "gpt2" for smaller footprint
    device_map="auto",                  # omit on CPU-only
    torch_dtype="auto",
)

def call_openai(messages, max_tokens=500):
    """
    Free local inference: take the last user message as prompt,
    generate up to max_tokens additional tokens, return the text.
    """
    prompt = messages[-1]["content"]
    logger.info("HF prompt: %s", prompt.replace("\n", " / "))
    output = hf_generator(
        prompt,
        max_length=len(prompt.split()) + max_tokens,
        do_sample=False,
        num_return_sequences=1,
    )
    return output[0]["generated_text"].strip()

# ─── Routes ───────────────────────────────────────────────────────────────────
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

    # 2) Build prompt & call HF LLM
    system_msg = {
        "role": "system",
        "content": (
            "You are an expert logistics quote generator for DSV. "
            "Based on the inputs, produce a clear, concise quotation "
            "including cost breakdown."
        )
    }
    user_msg = {
        "role": "user",
        "content": (
            f"Please draft a quotation for the following:\n"
            f"- Storage Type: {storage}\n"
            f"- Volume: {volume}\n"
            f"- Duration: {days} days\n"
            f"- Include WMS: {wms}\n"
            + (f"- Email: {email}\n" if email else "")
        )
    }
    quote_text = call_openai([system_msg, user_msg])

    # 3) Pick the right .docx template
    if "Chemical" in storage:
        tmpl_name = "Chemical VAS.docx"
    elif "Open Yard" in storage:
        tmpl_name = "Open Yard VAS.docx"
    else:
        tmpl_name = "Standard VAS.docx"

    template_path = os.path.join(TEMPLATES_DIR, tmpl_name)
    if not os.path.isfile(template_path):
        abort(500, f"Template not found: {tmpl_name}")

    # 4) Load template, insert AI text, save
    doc = Document(template_path)
    doc.add_paragraph("")                     # blank line
    doc.add_paragraph("Quotation:", style="Heading 2")
    for line in quote_text.split("\n"):
        doc.add_paragraph(line)

    filename = f"quote_{int(time.time())}_{uuid4().hex[:8]}.docx"
    out_path = os.path.join(GENERATED_DIR, filename)
    doc.save(out_path)

    # 5) Return file
    return send_from_directory(
        GENERATED_DIR,
        filename,
        as_attachment=True,
        download_name=filename
    )


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(force=True)
    user_text = (payload.get("message") or "").strip()
    if not user_text:
        return jsonify({"reply": "Please type something first."})

    logger.info("Chat request: %s", user_text)
    sys_msg = {
        "role": "system",
        "content": "You are a helpful assistant for DSV Quotation Generator."
    }
    usr_msg = {"role": "user", "content": user_text}

    try:
        reply = call_openai([sys_msg, usr_msg])
    except Exception as e:
        logger.error("HF error: %s", e, exc_info=True)
        reply = "Sorry, something went wrong."
    return jsonify({"reply": reply})


# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_ENV", "").lower() == "development"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
