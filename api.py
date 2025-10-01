import os
import io
import tempfile
import subprocess

from flask import Flask, send_from_directory, send_file, request, jsonify
from PIL import Image

app = Flask(__name__)

def convert_office_to_pdf(input_file, output_dir):
    cmd = [
        "soffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        input_file
    ]
    subprocess.run(cmd, check=True)
    base = os.path.basename(input_file)
    name, _ = os.path.splitext(base)
    pdf_path = os.path.join(output_dir, f"{name}.pdf")
    return pdf_path

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/convert', methods=['POST'])
def convert():
    files = list(request.files.values())
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    quality = int(request.form.get("quality", 80))
    output_format = request.form.get("output_format", "pdf").lower()

    imgs = []
    pdfs = []

    office_exts = ["doc", "docx", "xls", "xlsx"]
    tiff_exts = ["tif", "tiff"]

    for file in files:
        ext = file.filename.split(".")[-1].lower()
        mime = file.mimetype
        fname = file.filename

        # Office files: Convert to PDF first
        if ext in office_exts:
            with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp_office:
                file.save(tmp_office.name)
                pdf_path = None
                try:
                    pdf_path = convert_office_to_pdf(tmp_office.name, os.path.dirname(tmp_office.name))
                    with open(pdf_path, "rb") as pfile:
                        pdf_stream = io.BytesIO(pfile.read())
                        pdfs.append(pdf_stream)
                except Exception as e:
                    os.remove(tmp_office.name)
                    if pdf_path and os.path.exists(pdf_path):
                        os.remove(pdf_path)
                    return jsonify({"error": f"Office to PDF error: {str(e)}"}), 500
                else:
                    os.remove(tmp_office.name)
                    if pdf_path and os.path.exists(pdf_path):
                        os.remove(pdf_path)
        # PDF files
        elif ext == "pdf" or mime == "application/pdf":
            pdfs.append(file)
        # TIFF images
        elif ext in tiff_exts:
            img = Image.open(file.stream)
            imgs.append(img)
        # HEIC/HEIF images
        elif ext in ["heif", "heic"]:
            try:
                import pillow_heif
                heif_file = pillow_heif.read_heif(file.read())
                img = Image.frombytes(
                    heif_file.mode, heif_file.size, heif_file.data, "raw"
                )
                imgs.append(img)
            except ImportError:
                return jsonify({"error": "pillow-heif not installed"}), 500
        # AVIF images
        elif ext == "avif":
            img = Image.open(file.stream).convert("RGB")
            imgs.append(img)
        # WebP
        elif ext == "webp":
            img = Image.open(file.stream)
            imgs.append(img)
        # SVG to PNG for PDF
        elif ext == "svg":
            try:
                from cairosvg import svg2png
                png_bytes = svg2png(bytestring=file.read())
                img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                imgs.append(img)
            except ImportError:
                return jsonify({"error": "cairosvg not installed"}), 500
        # Other images
        else:
            try:
                img = Image.open(file.stream)
                imgs.append(img)
            except Exception as e:
                return jsonify({"error": f"Image error: {str(e)}"}), 400

    # PDF compression with slider-based quality
    if pdfs and output_format == "pdf":
        if quality <= 30:
            pdf_setting = "/screen"
            resolution = 72
        elif quality <= 60:
            pdf_setting = "/ebook"
            resolution = 100
        elif quality <= 85:
            pdf_setting = "/printer"
            resolution = 150
        else:
            pdf_setting = "/prepress"
            resolution = 300

        with tempfile.NamedTemporaryFile(suffix=".pdf") as in_file, tempfile.NamedTemporaryFile(suffix=".pdf") as out_file:
            pdf_data = pdfs[0].read() if hasattr(pdfs[0], "read") else pdfs[0].getvalue()
            in_file.write(pdf_data)
            in_file.flush()
            gs_cmd = [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS={pdf_setting}",
                f"-dColorImageDownsampleType=/Bicubic",
                f"-dColorImageResolution={resolution}",
                f"-dGrayImageDownsampleType=/Bicubic",
                f"-dGrayImageResolution={resolution}",
                f"-dMonoImageDownsampleType=/Subsample",
                f"-dMonoImageResolution={resolution}",
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
            return send_file(out_file.name, mimetype="application/pdf", as_attachment=True, download_name="compressed.pdf")

    # Image(s) to PDF
    if imgs and output_format == "pdf":
        output = io.BytesIO()
        imgs[0].save(output, format="PDF", save_all=True, append_images=imgs[1:])
        output.seek(0)
        return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="converted.pdf")

    # Image(s) to image format
    if imgs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic", "tiff"]:
        output = io.BytesIO()
        save_kwargs = {}
        if output_format in ["jpeg", "webp", "avif", "heif", "heic"]:
            save_kwargs["quality"] = quality
        imgs[0].save(output, format=output_format.upper(), **save_kwargs)
        output.seek(0)
        mime = f"image/{output_format}"
        ext = output_format
        return send_file(output, mimetype=mime, as_attachment=True, download_name=f"converted.{ext}")

    # PDF to image conversion (first page only, speed)
    if pdfs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic", "tiff"]:
        try:
            import fitz
        except ImportError:
            return jsonify({"error": "PyMuPDF (fitz) not installed"}), 500
        pdf_data = pdfs[0].read() if hasattr(pdfs[0], "read") else pdfs[0].getvalue()
        pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
        page = pdf_doc.load_page(0)
        pix = page.get_pixmap()
        img_bytes = pix.tobytes(output="png")
        img = Image.open(io.BytesIO(img_bytes))
        output = io.BytesIO()
        save_kwargs = {}
        if output_format in ["jpeg", "webp", "avif", "heif", "heic"]:
            save_kwargs["quality"] = quality
        img.save(output, format=output_format.upper(), **save_kwargs)
        output.seek(0)
        mime = f"image/{output_format}"
        ext = output_format
        return send_file(output, mimetype=mime, as_attachment=True, download_name=f"converted.{ext}")

    return jsonify({"error": "Conversion operation not supported or no valid files"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)