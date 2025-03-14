from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
from routes.batch_routes import batch_routes
from routes.patient_routes import patient_bp
from routes.json_process_routes import json_process_bp
import pandas as pd
import gridfs
import io
import os
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# ✅ Register Blueprints
app.register_blueprint(batch_routes)
app.register_blueprint(patient_bp)
app.register_blueprint(json_process_bp)

# ✅ Connect to MongoDB
client = MongoClient("mongodb+srv://pavanshankar9000:pavan%409000@project1.gfku5.mongodb.net/?retryWrites=true&w=majority")
db = client["Finish_db"]
fs = gridfs.GridFS(db)  # ✅ Initialize GridFS for file storage

# ✅ Define base folder for saving Excel files locally
BASE_REPORTS_FOLDER = "reports"
os.makedirs(BASE_REPORTS_FOLDER, exist_ok=True)  # Ensure base folder exists

@app.route("/upload-pdf", methods=["POST"])
def upload_pdf():
    """
    Uploads PDF files for a patient inside a batch and stores them in MongoDB GridFS.
    """
    try:
        batch_name = request.args.get("batch_name", "").strip()
        patient_id = request.args.get("patient_id", "").strip()

        if "pdfs" not in request.files:
            return jsonify({"error": "No PDF file uploaded"}), 400

        uploaded_files = request.files.getlist("pdfs")  # Multiple PDFs

        file_ids = []
        for file in uploaded_files:
            file_id = fs.put(file, filename=file.filename, patient_id=patient_id, batch=batch_name)
            file_ids.append(str(file_id))

        return jsonify({"message": "PDFs uploaded successfully", "file_ids": file_ids}), 200

    except Exception as e:
        return jsonify({"error": f"Failed to upload PDFs: {str(e)}"}), 500


@app.route("/download-pdf/<batch_name>/<patient_id>/<file_name>", methods=["GET"])
def download_pdf(batch_name, patient_id, file_name):
    """
    Retrieves a PDF file from MongoDB GridFS for a specific batch and patient.
    """
    try:
        # ✅ Search for the PDF in GridFS
        file_doc = db.fs.files.find_one({"batch": batch_name, "patient_id": patient_id, "filename": file_name})

        if not file_doc:
            return jsonify({"error": "No PDF found for this patient"}), 404

        file_id = file_doc["_id"]
        file_data = fs.get(file_id)

        return send_file(
            io.BytesIO(file_data.read()),
            as_attachment=True,
            download_name=file_doc["filename"],
            mimetype="application/pdf"
        )

    except Exception as e:
        return jsonify({"error": f"Error fetching PDF file: {str(e)}"}), 500


@app.route("/excel-download", methods=["POST"])
def generate_excel():
    """
    Generates an Excel file from received data, stores it inside batch folders,
    and uploads it to MongoDB GridFS.
    """
    try:
        # ✅ Get JSON data from frontend
        json_data = request.get_json()
        headers = json_data.get("headers", [])
        data = json_data.get("data", [])
        selected_patient = json_data.get("selectedPatient", "").strip()
        selected_batch = json_data.get("selectedBatch", "BATCH1").strip()

        if not headers or not data or not selected_patient:
            return jsonify({"error": "Invalid data received"}), 400

        # ✅ Convert JSON to DataFrame
        df = pd.DataFrame(data, columns=[
            "condition", "low", "lowToMild", "mild", "mildToModerate", "moderate", "moderateToHigh", "high",
            "concern", "noMutation", "aiScore", "reason"
        ])
        df.columns = headers  # ✅ Rename columns based on headers

        # ✅ Create batch folder if not exists
        batch_folder = os.path.join(BASE_REPORTS_FOLDER, selected_batch)
        os.makedirs(batch_folder, exist_ok=True)  

        # ✅ Save Excel file inside batch folder
        file_name = f"{selected_patient}_Scoring_chart.xlsx"
        file_path = os.path.join(batch_folder, file_name)

        with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False)

        # ✅ Save file in MongoDB GridFS
        with open(file_path, "rb") as file:
            file_id = fs.put(file, filename=file_name, patient_id=selected_patient, batch=selected_batch)

        return jsonify({
            "message": "Excel file stored successfully",
            "file_id": str(file_id),
            "file_path": file_path
        }), 200

    except Exception as e:
        return jsonify({"error": f"Failed to generate Excel: {str(e)}"}), 500


@app.route("/download-excel/<batch_name>/<patient_id>", methods=["GET"])
def download_excel(batch_name, patient_id):
    """
    Fetches the latest Excel file for a patient inside the batch folder or from MongoDB GridFS.
    """
    try:
        # ✅ First, check if the file exists locally
        file_name = f"{patient_id}_Scoring_chart.xlsx"
        batch_folder = os.path.join(BASE_REPORTS_FOLDER, batch_name)
        local_file_path = os.path.join(batch_folder, file_name)

        if os.path.exists(local_file_path):
            return send_file(
                local_file_path,
                as_attachment=True,
                download_name=file_name,
                mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # ✅ If not found locally, check in MongoDB GridFS
        file_doc = db.fs.files.find_one({"patient_id": patient_id, "batch": batch_name}, sort=[("uploadDate", -1)])
        if not file_doc:
            return jsonify({"error": "No Excel file found for this patient"}), 404

        # ✅ Fetch file from GridFS
        file_id = file_doc["_id"]
        file_data = fs.get(file_id)

        return send_file(
            io.BytesIO(file_data.read()),
            as_attachment=True,
            download_name=file_doc["filename"],
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:
        return jsonify({"error": f"Error fetching Excel file: {str(e)}"}), 500


if __name__ == '__main__':
    app.run(debug=True)
