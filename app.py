import os, time, logging
from uuid import uuid4
from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory, jsonify, abort
from huggingface_hub import InferenceClient
from docx import Document

# ─── Load .env ────────────────────────────────────────────────────────────────
load_dotenv()  # reads TEMPLATES_DIR, GENERATED_DIR, FLASK_ENV, HF_API_TOKEN

# ─── Flask Setup ─────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
GENERATED_DIR = os.getenv("GENERATED_DIR", "generated")
os.makedirs(GENERATED_DIR, exist_ok=True)

# ─── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Hugging Face Inference Client ────────────────────────────────────────────
HF_API_TOKEN = os.getenv("HF_API_TOKEN")
if not HF_API_TOKEN:
    logger.error("Missing HF_API_TOKEN in env!")
hf = InferenceClient(token=HF_API_TOKEN)

def call_llm(messages, max_tokens=500):
    """
    Calls the hosted HF Falcon-7B-Instruct (or any pipeline) over the Inference API.
    """
    prompt = messages[-1]["content"]
    logger.info("HF prompt: %s", prompt.replace("\n", " / "))
    # adjust model name if you want a different one:
    resp = hf.text_generation(
        model="tiiuae/falcon-7b-instruct",
        inputs=prompt,
        parameters={"max_new_tokens": max_tokens}
    )
    return resp.generated_text.strip()

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    return render_template("form.html")

@app.route("/generate", methods=["POST"])
def generate():
    storage = request.form.get("storage_type","").strip()
    volume  = request.form.get("volume","").strip()
    days    = request.form.get("days","").strip()
    wms     = request.form.get("wms","").strip()
    email   = request.form.get("email","").strip()
    if not (storage and volume and days and wms):
        abort(400, "Missing form fields")

    system_msg = {
        "role":"system",
        "content":(
            "You are an expert logistics quote generator for DSV. "
            "Based on the inputs, produce a clear, concise quotation including cost breakdown."
        )
    }
    user_msg = {
        "role":"user",
        "content":(
            f"Please draft a quotation for the following:\n"
            f"- Storage Type: {storage}\n"
            f"- Volume: {volume}\n"
            f"- Duration: {days} days\n"
            f"- Include WMS: {wms}\n"
            + (f"- Email: {email}\n" if email else "")
        )
    }
    quote_text = call_llm([system_msg, user_msg])

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
    doc.add_paragraph("")  # blank
    doc.add_paragraph("Quotation:", style="Heading 2")
    for line in quote_text.split("\n"):
        doc.add_paragraph(line)

    filename = f"quote_{int(time.time())}_{uuid4().hex[:8]}.docx"
    out_path = os.path.join(GENERATED_DIR, filename)
    doc.save(out_path)

    return send_from_directory(
        GENERATED_DIR, filename,
        as_attachment=True, download_name=filename
    )

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(force=True)
    user_text = (data.get("message") or "").strip()
    if not user_text:
        return jsonify({"reply":"Please type something first."})

    logger.info("Chat request: %s", user_text)
    sys_msg = {
        "role":"system",
        "content":"You are a helpful assistant for DSV Quotation Generator."
    }
    usr_msg = {"role":"user","content":user_text}

    try:
        reply = call_llm([sys_msg, usr_msg])
    except Exception as e:
        logger.error("HF error: %s", e, exc_info=True)
        reply = "Sorry, something went wrong."
    return jsonify({"reply":reply})

# ─── Entrypoint ────────────────────────────────────────────────────────────────
if __name__=="__main__":
    debug = os.getenv("FLASK_ENV","").lower()=="development"
    port  = int(os.getenv("PORT",5000))
    app.run(host="0.0.0.0", port=port, debug=debug)
