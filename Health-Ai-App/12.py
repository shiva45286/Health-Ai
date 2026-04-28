
from flask import send_from_directory

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)
    

from flask import Flask, request, jsonify, send_from_directory

from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch   # ✅ ADD THIS

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing


import matplotlib
matplotlib.use('Agg')   # 🔥 FIX: use non-GUI backend
import matplotlib.pyplot as plt
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

    # ================= HEADER =================
    logo_path = os.path.join("static", "logo.png")

    if os.path.exists(logo_path):
        content.append(Image(logo_path, width=1.2*inch, height=1.2*inch))

    content.append(Paragraph("🏥 HealthAI Medical Report", styles['Title']))
    content.append(Spacer(1, 12))

    # ================= PATIENT DATA =================
    table_data = [
        ["Parameter", "Value"],
        ["Age", data.get('age')],
        ["BMI", data.get('bmi')],
        ["Glucose", data.get('glucose')],
        ["HbA1c", data.get('hba1c')],
        ["Blood Pressure", data.get('bp')],
        ["Cholesterol", data.get('cholesterol')],
        ["Max HR", data.get('maxhr')],
    ]

    table = Table(table_data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR',(0,0),(-1,0),colors.white),
        ('GRID',(0,0),(-1,-1),1,colors.black),
    ]))

    content.append(table)
    content.append(Spacer(1, 20))

    # ================= RISK BADGES =================
    content.append(Paragraph("<b>Risk Analysis</b>", styles['Heading2']))
    content.append(Spacer(1, 10))

    def risk_color(text):
        text = str(text)
        if "High" in text:
            return colors.red
        elif "Normal" in text:
            return colors.green
        else:
            return colors.orange

    risks = [
        ("Diabetes", data.get('diabetes')),
        ("Heart", data.get('heart')),
        ("BP Score", data.get('bpRisk')),
        ("Health Score", data.get('healthScore'))
    ]

    for label, value in risks:
        style = ParagraphStyle(
            name='risk',
            backColor=risk_color(value),
            textColor=colors.white,
            leftPadding=6,
            rightPadding=6,
            topPadding=4,
            bottomPadding=4
        )
        content.append(Paragraph(f"{label}: {value}", style))
        content.append(Spacer(1, 6))

    content.append(Spacer(1, 15))

    # ================= CHART =================
    try:
        chart_path = os.path.join(UPLOAD_FOLDER, "chart.png")

        bp_digits = ''.join(filter(str.isdigit, str(data.get('bpRisk', 0))))
        bp_value = int(bp_digits) if bp_digits else 0

        values = [
            100 if "High" in str(data.get('diabetes')) else 0,
            100 if "High" in str(data.get('heart')) else 0,
            bp_value
        ]

        labels = ["Diabetes", "Heart", "BP"]

        plt.figure(figsize=(4,3))
        plt.bar(labels, values)
        plt.title("Health Risk Chart")
        plt.tight_layout()
        plt.savefig(chart_path)
        plt.close()

        content.append(Paragraph("<b>Health Chart</b>", styles['Heading2']))
        content.append(Spacer(1, 10))
        content.append(Image(chart_path, width=4*inch, height=3*inch))

    except Exception as e:
        print("Chart error:", e)

    content.append(Spacer(1, 20))

    # ================= AI EXPLANATION =================
    content.append(Paragraph("<b>AI Explanation</b>", styles['Heading2']))
    content.append(Spacer(1, 10))
    content.append(Paragraph(data.get("ai", "No explanation available"), styles['Normal']))

    content.append(Spacer(1, 20))

    # ================= QR CODE =================
    try:
        qr_data = f"http://127.0.0.1:5000/uploads/{filename}"
        qr_code = qr.QrCodeWidget(qr_data)

        bounds = qr_code.getBounds()
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]

        d = Drawing(100, 100, transform=[100./width,0,0,100./height,0,0])
        d.add(qr_code)

        content.append(Paragraph("<b>Scan QR to open report</b>", styles['Heading2']))
        content.append(d)

    except Exception as e:
        print("QR error:", e)

    # ================= BUILD =================
    doc.build(content)

    return jsonify({"file": f"/uploads/{filename}"})



if __name__ == "__main__":
    app.run(debug=True)

