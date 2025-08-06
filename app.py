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
from openai.error import RateLimitError, OpenAIError
from docx import Document

# ─── Load .env ────────────────────────────────────────────────────────────────
load_dotenv()  # populates OPENAI_API_KEY, TEMPLATES_DIR, GENERATED_DIR, FLASK_ENV

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

# ─── OpenAI Helper with Double-Fallback ─────────────────────────────────────────
def call_openai(messages, max_tokens=500):
    """
    Try GPT-4O-Mini → GPT-3.5-Turbo → return an error sentence if both fail.
    """
    for model in ("gpt-4o-mini", "gpt-3.5-turbo"):
        try:
            logger.info(f"Calling OpenAI with model {model}")
            resp = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens
            )
            return resp.choices[0].message.content.strip()
        except RateLimitError:
            logger.warning(f"{model} quota/rate-limit hit; trying next model")
        except OpenAIError as e:
            logger.error(f"{model} API error: {e}")
        except Exception:
            logger.exception(f"{model} unexpected error")
    # both models failed
    return (
        "Sorry, our AI service is unavailable right now. "
        "Please try again in a few minutes."
    )

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    """Render the quotation form."""
    return render_template("form.html")


@app.route("/generate", methods=["POST"])
def generate():
    """
    1) Read form fields
    2) Ask OpenAI for a quotation narrative
    3) Merge into the correct .docx template
    4) Return the generated .docx as a download
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
    JSON { message: "..." } → JSON { reply: "..." }
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

    reply = call_openai([sys_msg, usr_msg])
    return jsonify({"reply": reply})


# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_ENV", "").lower() == "development"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug_mode)
            f"Draft a quotation with:\n"
            f"- Storage: {storage}\n"
            f"- Volume: {volume}\n"
            f"- Duration: {days} days\n"
            f"- Include WMS: {wms}\n"
            f"{'- Email: ' + email if email else ''}"
        )
    }
    quote_text = call_openai([sys_msg, usr_msg])

    # pick template
    if "Chemical" in storage:
        tmpl = "Chemical VAS.docx"
    elif "Open Yard" in storage:
        tmpl = "Open Yard VAS.docx"
    else:
        tmpl = "Standard VAS.docx"

    tpl_path = os.path.join(TEMPLATES_DIR, tmpl)
    if not os.path.isfile(tpl_path):
        abort(500, f"Template not found: {tmpl}")

    doc = Document(tpl_path)
    doc.add_paragraph("")
    doc.add_paragraph("Quotation:", style="Heading 2")
    for line in quote_text.split("\n"):
        doc.add_paragraph(line)

    fname = f"quote_{int(time.time())}_{uuid4().hex[:8]}.docx"
    out_path = os.path.join(GENERATED_DIR, fname)
    doc.save(out_path)

    return send_from_directory(
        GENERATED_DIR,
        fname,
        as_attachment=True,
        download_name=fname
    )


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    text = (data.get("message") or "").strip()
    if not text:
        return jsonify({"reply": "Please type something first."})

    sys_msg = {
        "role": "system",
        "content": "You are a helpful assistant for the DSV quote generator."
    }
    usr_msg = {"role": "user", "content": text}
    reply = call_openai([sys_msg, usr_msg])
    return jsonify({"reply": reply})


# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    debug = os.getenv("FLASK_ENV", "").lower() == "development"
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
