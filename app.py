import os
import time
import logging
from uuid import uuid4

from dotenv import load_dotenv
from flask import (
    Flask, request, render_template,
    send_from_directory, jsonify, abort
)
import openai
from openai.error import RateLimitError
from docx import Document

# ─── Load .env ────────────────────────────────────────────────────────────────
load_dotenv()  # will populate OPENAI_API_KEY, TEMPLATES_DIR, GENERATED_DIR, FLASK_ENV

# ─── Flask & OpenAI Setup ─────────────────────────────────────────────────────
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

openai.api_key = os.getenv("OPENAI_API_KEY")
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
GENERATED_DIR = os.getenv("GENERATED_DIR", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── OpenAI Helper with Fallback ───────────────────────────────────────────────
def call_openai(messages, max_tokens=500):
    """
    Try GPT-4O-Mini first; on quota exhaustion, fall back to gpt-3.5-turbo.
    Returns the assistant reply string.
    """
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=max_tokens
        )
    except RateLimitError:
        logger.warning("GPT-4O quota exceeded; falling back to gpt-3.5-turbo")
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=max_tokens
        )
    return resp.choices[0].message.content.strip()


# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    """Show the quotation form."""
    return render_template("form.html")


@app.route("/generate", methods=["POST"])
def generate():
    """
    1) Read form fields
    2) Ask OpenAI for a quotation narrative
    3) Merge into the correct .docx template
    4) Return the generated .docx as download
    """
    # 1) Gather inputs
    storage = request.form.get("storage_type", "").strip()
    volume  = request.form.get("volume", "").strip()
    days    = request.form.get("days", "").strip()
    wms     = request.form.get("wms", "").strip()
    email   = request.form.get("email", "").strip()

    if not (storage and volume and days and wms):
        abort(400, "Missing form fields")

    # 2) Build prompt & call OpenAI
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
            f"{f'- Email: {email}' if email else ''}"
        )
    }
    quote_text = call_openai([system_msg, user_msg])

    # 3) Pick the right template file
    #    (Adjust these filenames to match exactly your .docx names)
    if "Chemical" in storage:
        tmpl_name = "Chemical VAS.docx"
    elif "Open Yard" in storage:
        tmpl_name = "Open Yard VAS.docx"
    else:
        tmpl_name = "Standard VAS.docx"

    template_path = os.path.join(TEMPLATES_DIR, tmpl_name)
    if not os.path.isfile(template_path):
        abort(500, f"Template not found: {tmpl_name}")

    # 4) Load, insert quote, save
    doc = Document(template_path)
    # Insert a heading and the AI text at the end:
    doc.add_paragraph("")  # blank line
    doc.add_paragraph("Quotation:", style="Heading 2")
    for line in quote_text.split("\n"):
        doc.add_paragraph(line)

    filename = f"quote_{int(time.time())}_{uuid4().hex[:8]}.docx"
    out_path = os.path.join(GENERATED_DIR, filename)
    doc.save(out_path)

    # 5) Send as attachment
    return send_from_directory(
        GENERATED_DIR,
        filename,
        as_attachment=True,
        download_name=filename
    )


@app.route("/chat", methods=["POST"])
def chat():
    """
    JSON { message: "..." } → { reply: "..." }
    """
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
        logger.error("OpenAI error: %s", e, exc_info=True)
        reply = "Sorry, something went wrong."

    return jsonify({"reply": reply})


# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_ENV", "").lower() == "development"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
