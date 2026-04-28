from flask import Flask, render_template, request, jsonify, session, redirect
import pickle
import sqlite3
import bcrypt
import os
import pandas as pd
import json
import logging
import pickle

from google import genai




# OCR
from PIL import Image
import pytesseract
from pdf2image import convert_from_bytes



# ---------------- CONFIG ----------------

app = Flask(__name__)
app.secret_key = "super_secret_key"

logging.basicConfig(level=logging.INFO)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"



UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

last_report_data = {}

# ---------------- DATABASE ----------------

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    c.execute('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT
    )
    ''')

    conn.commit()
    conn.close()

init_db()


# ---------------- ROUTES ----------------

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/login')
def login():
    return render_template('login.html')

@app.route('/signup')
def signup():
    return render_template('signup.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')
    return render_template('dashboard.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# ---------------- SIGNUP ----------------

@app.route('/signup-user', methods=['POST'])
def signup_user():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE email=?", (email,))
        if c.fetchone():
            return jsonify({"success": False, "message": "User exists"})

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        c.execute("INSERT INTO users VALUES (NULL, ?, ?)", (email, hashed))
        conn.commit()
        conn.close()

    
        return jsonify({"success": True})

    except Exception as e:
        print("SIGNUP ERROR:", e)
        return jsonify({"success": False})

# ---------------- LOGIN ----------------

@app.route('/login-user', methods=['POST'])
def login_user():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        conn = sqlite3.connect('users.db')
        c = conn.cursor()

        c.execute("SELECT password FROM users WHERE email=?", (email,))
        user = c.fetchone()
        conn.close()

        if not user:
            return jsonify({"success": False, "message": "User not found"})

        if bcrypt.checkpw(password.encode(), user[0].encode()):
            session['user'] = email
            return jsonify({"success": True})

        return jsonify({"success": False, "message": "Wrong password"})

    except Exception as e:
        print("LOGIN ERROR:", e)
        return jsonify({"success": False})



# ---------------- GOOGLE LOGIN ----------------

@app.route('/google-login', methods=['POST'])
def google_login():
    email = request.json.get("email")

    conn = sqlite3.connect('users.db')
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE email=?", (email,))
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (NULL, ?, ?)", (email, "google"))

    conn.commit()
    conn.close()

    session['user'] = email
    return jsonify({"success": True})



diabetes_model = pickle.load(open("model/diabetes.pkl","rb"))
heart_model = pickle.load(open("model/heart.pkl","rb"))
# BP LOGIC (GLOBAL)
def bp_risk_score(bp, age, bmi):
    score = 0

    # Blood Pressure contribution
    if bp < 120:
        score += 0
    elif bp < 130:
        score += 10
    elif bp < 140:
        score += 25
    else:
        score += 40

    # Age contribution
    if age > 45:
        score += 10
    if age > 60:
        score += 10

    # BMI contribution
    if bmi > 25:
        score += 10
    if bmi > 30:
        score += 10

    return min(score, 100)

def health_score(diabetes, heart, bp_score):
    score = 100

    if diabetes == 1:
        score -= 30

    if heart == 1:
        score -= 30

    # BP contribution (scaled)
    score -= int(bp_score * 0.3)

    return max(score, 0)


# dashboard route
@app.route('/multi-predict', methods=['POST'])
def multi_predict():

    data = request.json

    import pandas as pd

    # DIABETES
    d_input = pd.DataFrame([{
    "age": data.get('age', 0),
    "hypertension": data.get('hypertension', 0),
    "bmi": data.get('bmi', 0),

    # 🔥 MATCH TRAINING NAMES EXACTLY
    "HbA1c_level": data.get('hba1c', 0),
    "blood_glucose_level": data.get('glucose', 0)
}])

    diabetes = diabetes_model.predict(d_input)[0]

    # HEART
    h_input = pd.DataFrame([{
    "Age": data.get('age', 0),
    "RestingBP": data.get('bp', 0),
    "Cholesterol": data.get('cholesterol', 0),
    "MaxHR": data.get('maxhr', 0)
}])

    heart = heart_model.predict(h_input)[0]

    # BP SCORE
    bp_score = bp_risk_score(
        data.get('bp', 0),
        data.get('age', 0),
        data.get('bmi', 0)
    )

    # FINAL HEALTH SCORE
    final_score = health_score(diabetes, heart, bp_score)

    return jsonify({
        "diabetes": int(diabetes),
        "heart": int(heart),
        "bp_score": int(bp_score),
        "health_score": int(final_score)
    })



@app.route('/upload-report', methods=['POST'])
def upload_report():

    file = request.files['file']
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(filepath)

    extracted = {}
    records = []

    # ---------- CSV ----------
    if file.filename.endswith('.csv'):
        df = pd.read_csv(filepath)

        # 🔥 normalize column names
        df.columns = df.columns.str.lower().str.replace(" ", "").str.replace("_", "")

        def find_value(row, keywords):
            for col in row.keys():
                for key in keywords:
                    if key in col:
                        try:
                            return float(row[col])
                        except:
                            return 0
            return 0

        # 🔥 extract first row (for auto-fill UI)
        row = df.iloc[0]

        extracted = {
            "age": find_value(row, ["age"]),
            "bmi": find_value(row, ["bmi"]),
            "glucose": find_value(row, ["glucose"]),
            "hba1c": find_value(row, ["hba1c", "hb"]),
            "bp": find_value(row, ["bp", "pressure"]),
            "cholesterol": find_value(row, ["cholesterol"]),
            "maxhr": find_value(row, ["maxhr", "heartrate"]),
            "hypertension": find_value(row, ["hypertension"])
        }

        # 🔥 STEP 1: convert full dataset
        records = df.to_dict(orient="records")

    return jsonify({
        "first": extracted,   # for input autofill
        "data": records       # 🔥 for chart
    })
    return data




import time

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        user_msg = data.get("message")

        time.sleep(2)  # avoid rate spam

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_msg
        )

        return jsonify({"reply": response.text})

    except Exception as e:
        print("Chat Error:", e)
        return jsonify({"reply": "AI busy, try again in few seconds"})
    



from flask import send_from_directory

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
    

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import os
from datetime import datetime

@app.route('/download-report', methods=['POST'])
def download_report():

    data = request.json

    filename = f"health_report_{datetime.now().strftime('%H%M%S')}.pdf"
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    doc = SimpleDocTemplate(file_path)
    styles = getSampleStyleSheet()

    content = []

    # ===== TITLE =====
    content.append(Paragraph("HealthAI Medical Report", styles['Title']))
    content.append(Spacer(1, 15))

    # ===== BASIC DATA TABLE =====
    table_data = [
        ["Parameter", "Value"],
        ["Age", data['age']],
        ["BMI", data['bmi']],
        ["Glucose", data['glucose']],
        ["HbA1c", data['hba1c']],
        ["Blood Pressure", data['bp']],
        ["Cholesterol", data['cholesterol']],
        ["Max HR", data['maxhr']],
    ]

    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID',(0,0),(-1,-1),1,colors.black),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold')
    ]))

    content.append(table)
    content.append(Spacer(1, 20))

    # ===== RISKS =====
    content.append(Paragraph("<b>Risk Analysis</b>", styles['Heading2']))
    content.append(Spacer(1, 10))

    content.append(Paragraph(f"Diabetes: {data['diabetes']}", styles['Normal']))
    content.append(Paragraph(f"Heart Risk: {data['heart']}", styles['Normal']))
    content.append(Paragraph(f"BP Score: {data['bpRisk']}", styles['Normal']))
    content.append(Paragraph(f"Health Score: {data['healthScore']}", styles['Normal']))

    content.append(Spacer(1, 20))

    # ===== AI EXPLANATION =====
    content.append(Paragraph("<b>AI Explanation</b>", styles['Heading2']))
    content.append(Spacer(1, 10))
    content.append(Paragraph(data.get("ai", "No explanation available"), styles['Normal']))

    content.append(Spacer(1, 20))

    # ===== RECOMMENDATIONS =====
    content.append(Paragraph("<b>Recommendations</b>", styles['Heading2']))
    content.append(Spacer(1, 10))
    content.append(Paragraph(data.get("diet", "No recommendations"), styles['Normal']))

    doc.build(content)

    return jsonify({"file": f"/uploads/{filename}"})



if __name__ == "__main__":
    app.run(debug=True)

