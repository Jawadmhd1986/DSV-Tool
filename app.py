import os
import logging

from dotenv import load_dotenv
from flask import Flask, request, render_template, send_from_directory, jsonify
import openai
from openai.error import RateLimitError

# ─── Load .env ────────────────────────────────────────────────────────────────
load_dotenv()  # pulls in OPENAI_API_KEY, TEMPLATES_DIR, GENERATED_DIR, FLASK_ENV

# ─── Flask & OpenAI Setup ─────────────────────────────────────────────────────
app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # optional, see changes to templates

openai.api_key = os.getenv("OPENAI_API_KEY")
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "templates")
GENERATED_DIR = os.getenv("GENERATED_DIR", "generated")

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
    except RateLimitError as e:
        logger.warning("GPT-4O quota exceeded; falling back to gpt-3.5-turbo")
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=max_tokens
        )
    return resp.choices[0].message.content

# ─── Routes ────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET"])
def index():
    # Renders your form.html in templates/
    return render_template("form.html")


@app.route("/generate", methods=["POST"])
def generate():
    # Your existing quotation-generation logic goes here.
    # For example:
    #
    # storage = request.form["storage_type"]
    # volume  = request.form["volume"]
    # days    = request.form["days"]
    # wms     = request.form["wms"]
    # email   = request.form.get("email")
    #
    # sys_msg = {"role": "system", "content": "..."}
    # user_msg = {"role": "user", "content": f"..."}
    # reply = call_openai([sys_msg, user_msg])
    #
    # # fill in a .docx template under TEMPLATES_DIR
    # # save to GENERATED_DIR, then:
    # return send_from_directory(GENERATED_DIR, filename, as_attachment=True)
    #
    # (Keep your existing Generate code here.)
    raise NotImplementedError("Your /generate logic goes here")


@app.route("/chat", methods=["POST"])
def chat():
    payload = request.get_json(force=True)
    user_text = payload.get("message", "").strip()
    if not user_text:
        return jsonify({"reply": "Please send a message."})

    logger.info("Chat request: %s", user_text)

    system_msg = {
        "role": "system",
        "content": "You are a helpful assistant for DSV product quotations."
    }
    user_msg = {
        "role": "user",
        "content": user_text
    }

    try:
        reply_text = call_openai([system_msg, user_msg])
    except Exception as e:
        logger.error("OpenAI error: %s", e, exc_info=True)
        reply_text = "Sorry, something went wrong."

    return jsonify({"reply": reply_text})


# ─── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # When running with `python app.py`
    debug_mode = os.getenv("FLASK_ENV", "").lower() == "development"
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=debug_mode)
