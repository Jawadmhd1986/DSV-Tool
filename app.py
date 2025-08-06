import os
import re
import logging
from datetime import datetime
from flask import Flask, render_template, request, send_file, jsonify
from docx import Document
import openai

# Initialize Flask app
app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
TEMPLATES_DIR = os.getenv('TEMPLATES_DIR', 'templates')
GENERATED_DIR = os.getenv('GENERATED_DIR', 'generated')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY

# Storage rate configuration
STORAGE_RATES = {
    'standard':   {'AC': 2.5, 'Non-AC': 2.0, 'Open Shed': 1.8},
    'chemical':   {'AC': 3.5, 'Non-AC': 2.7},
    'open_yard':  {'KIZAD': 125/365, 'Mussafah': 160/365},
}
WMS_MONTHLY_FEE = 1500

def normalize_text(text: str) -> str:
    """Clean and normalize incoming chat messages."""
    mapping = {
        r"\bu\b": "you", r"\bur\b": "your", r"\br\b": "are",
        r"\bpls\b": "please", r"\bthx\b": "thanks",
        # …add any other shorthand here…
    }
    text = text.lower().strip()
    for pat, rep in mapping.items():
        text = re.sub(pat, rep, text)
    # strip unwanted characters
    return re.sub(r"[^a-z0-9\s\.\-@]", "", text)

def generate_document(storage_type: str, volume: float, days: int,
                      include_wms: bool, email: str) -> str:
    """Generate a DOCX quotation and return its file path."""
    # pick template
    key = (
        'open_yard' if 'open yard' in storage_type.lower() else
        'chemical' if 'chemical' in storage_type.lower() else
        'standard'
    )
    tpl_file = {
        'standard':   "Standard VAS.docx",
        'chemical':   "Chemical VAS.docx",
        'open_yard':  "Open Yard VAS.docx",
    }[key]
    doc = Document(os.path.join(TEMPLATES_DIR, tpl_file))

    # rate & unit
    unit       = 'SQM' if key == 'open_yard' else 'CBM'
    rate_group = STORAGE_RATES[key]
    rate_key   = next((k for k in rate_group if k.lower() in storage_type.lower()), None)
    rate       = rate_group.get(rate_key, 0)
    rate_unit  = f"{unit} / {'YEAR' if key=='open_yard' else 'DAY'}"

    # fees
    storage_fee = volume * days * rate
    months      = max(1, days // 30)
    wms_fee     = 0 if key=='open_yard' or not include_wms else WMS_MONTHLY_FEE * months
    total_fee   = round(storage_fee + wms_fee, 2)

    # placeholders
    ph = {
        '{{STORAGE_TYPE}}': storage_type,
        '{{DAYS}}':          str(days),
        '{{VOLUME}}':        f"{volume:.2f}",
        '{{UNIT}}':          unit,
        '{{UNIT_RATE}}':     f"{rate:.2f} AED/{rate_unit}",
        '{{STORAGE_FEE}}':   f"{storage_fee:,.2f} AED",
        '{{WMS_FEE}}':       f"{wms_fee:,.2f} AED",
        '{{TOTAL_FEE}}':     f"{total_fee:,.2f} AED",
        '{{TODAY_DATE}}':    datetime.utcnow().strftime('%d %b %Y'),
    }

    # replace in paragraphs & tables
    for p in doc.paragraphs:
        for k, v in ph.items():
            if k in p.text:
                p.text = p.text.replace(k, v)
    for tbl in doc.tables:
        for row in tbl.rows:
            for cell in row.cells:
                for k, v in ph.items():
                    if k in cell.text:
                        cell.text = cell.text.replace(k, v)

    # strip unused sections
    def strip(s, e):
        inside = False
        rem = []
        for i, p in enumerate(doc.paragraphs):
            if s in p.text: inside = True
            if inside:    rem.append(i)
            if e in p.text: inside = False
        for i in reversed(rem):
            elm = doc.paragraphs[i]._element
            elm.getparent().remove(elm)

    if key == 'standard':
        strip('[VAS_CHEMICAL]', '[/VAS_CHEMICAL]')
        strip('[VAS_OPENYARD]', '[/VAS_OPENYARD]')
    elif key == 'chemical':
        strip('[VAS_STANDARD]', '[/VAS_STANDARD]')
        strip('[VAS_OPENYARD]', '[/VAS_OPENYARD]')
    else:
        strip('[VAS_STANDARD]', '[/VAS_STANDARD]')
        strip('[VAS_CHEMICAL]', '[/VAS_CHEMICAL]')

    # save
    os.makedirs(GENERATED_DIR, exist_ok=True)
    fn = f"Quotation_{email.split('@')[0] if email else 'client'}.docx"
    out = os.path.join(GENERATED_DIR, fn)
    doc.save(out)
    return out

def call_openai(messages: list) -> str:
    """Fallback to OpenAI for unmatched chat queries."""
    resp = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=500
    )
    return resp.choices[0].message.content.strip()

# ——— Flask endpoints ——————————————————————

@app.route('/')
def index():
    return render_template('form.html')

@app.route('/generate', methods=['POST'])
def generate():
    try:
        st  = request.form.get('storage_type', '')
        vol = float(request.form.get('volume', 0))
        dd  = int(request.form.get('days', 0))
        wms = request.form.get('wms', 'No') == 'Yes'
        em  = request.form.get('email', '')
        path = generate_document(st, vol, dd, wms, em)
        return send_file(path, as_attachment=True)
    except Exception:
        logger.exception("Doc generation failed")
        return jsonify({'error': 'Could not generate quotation.'}), 500

@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json() or {}
    raw  = data.get('message', '')
    txt  = normalize_text(raw)

    # example: built-in rule
    if re.search(r"\bstorage rate\b", txt):
        return jsonify({'reply': 'Which storage type? Standard, Chemical, or Open Yard?'})

    # …add more regex handlers here…

    # fallback to AI
    logger.info("AI fallback for: %s", raw)
    sys = {
        'role': 'system',
        'content': (
            'You are a professional logistics assistant at DSV Abu Dhabi. '
            'Answer concisely, using company rates and services as reference.'
        )
    }
    user_msg = {'role': 'user', 'content': raw}
    reply = call_openai([sys, user_msg])
    return jsonify({'reply': reply})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
