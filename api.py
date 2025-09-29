import os
import tempfile
import subprocess

from flask import Flask, send_from_directory
import os

app = Flask(__name__)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))  # Default to 5000 if not specified
    app.run(host='0.0.0.0', port=port)


@app.route("/compress-pdf", methods=["POST"])
def compress_pdf():
    pdf = request.files.get("pdf")
    if not pdf:
        return jsonify({"error": "No PDF uploaded"}), 400
    with tempfile.NamedTemporaryFile(suffix=".pdf") as in_file, tempfile.NamedTemporaryFile(suffix=".pdf") as out_file:
        pdf.save(in_file.name)
        gs_cmd = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            "-dPDFSETTINGS=/ebook",  # options: /screen, /ebook, /printer, /prepress
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={out_file.name}",
            in_file.name
        ]
        try:
            subprocess.run(gs_cmd, check=True)
        except Exception as e:
            return jsonify({"error": f"Ghostscript error: {str(e)}"}), 500
        return send_file(out_file.name, mimetype="application/pdf")

@app.route("/images-to-pdf", methods=["POST"])
def images_to_pdf():
    images = []
    for key in request.files:
        img_file = request.files[key]
        ext = img_file.filename.split(".")[-1].lower()
        # SVG to PNG for PDF
        if ext == "svg":
            try:
                from cairosvg import svg2png
            except ImportError:
                return jsonify({"error": "cairosvg not installed"}), 500
            png_bytes = svg2png(bytestring=img_file.read())
            img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        # AVIF to PNG/JPEG for PDF (Pillow >=10.0.0)
        elif ext == "avif":
            img = Image.open(img_file.stream).convert("RGB")
        # BMP, PNG, JPEG, WebP
        else:
            img = Image.open(img_file.stream)
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
        images.append(img)
    if not images:
        return jsonify({"error": "No images uploaded"}), 400
    with tempfile.NamedTemporaryFile(suffix=".pdf") as pdf_file:
        images[0].save(pdf_file.name, save_all=True, append_images=images[1:], format="PDF")
        return send_file(pdf_file.name, mimetype="application/pdf")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)