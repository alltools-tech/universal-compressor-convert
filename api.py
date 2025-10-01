import os
import io
import tempfile
import subprocess

from flask import Flask, send_from_directory, send_file, request, jsonify
from PIL import Image

app = Flask(__name__)

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

    # Separate PDFs and images
    for file in files:
        ext = file.filename.split(".")[-1].lower()
        mime = file.mimetype
        if ext == "pdf" or mime == "application/pdf":
            pdfs.append(file)
        else:
            img = None
            if ext in ["heif", "heic"]:
                try:
                    import pillow_heif
                    heif_file = pillow_heif.read_heif(file.read())
                    img = Image.frombytes(
                        heif_file.mode, heif_file.size, heif_file.data, "raw"
                    )
                except ImportError:
                    return jsonify({"error": "pillow-heif not installed"}), 500
            elif ext == "avif":
                img = Image.open(file.stream).convert("RGB")
            elif ext == "webp":
                img = Image.open(file.stream)
            elif ext == "svg":
                try:
                    from cairosvg import svg2png
                    png_bytes = svg2png(bytestring=file.read())
                    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                except ImportError:
                    return jsonify({"error": "cairosvg not installed"}), 500
            else:
                img = Image.open(file.stream)
            if img:
                imgs.append(img)

    # PDF compression with slider-based quality
    if pdfs and output_format == "pdf":
        # Map slider value to Ghostscript advanced compression
        # Lower quality = lower resolution and higher downsampling
        # Higher quality = higher resolution, less downsampling
        # We'll dynamically set image resolution and downsampling
        # For advanced control, set -dColorImageResolution and -dDownsampleType
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
            pdfs[0].save(in_file.name)
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
    if imgs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic"]:
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
    if pdfs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic"]:
        try:
            import fitz
        except ImportError:
            return jsonify({"error": "PyMuPDF (fitz) not installed"}), 500
        pdf_stream = io.BytesIO(pdfs[0].read())
        pdf_doc = fitz.open(stream=pdf_stream.read(), filetype="pdf")
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