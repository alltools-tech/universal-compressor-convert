import os
import io
import tempfile

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
    dpi = int(request.form.get("dpi", 72))
    grayscale = request.form.get("grayscale", "false").lower() == "true"

    imgs = []
    pdfs = []

    tiff_exts = ["tif", "tiff"]
    bmp_exts = ["bmp"]
    svg_exts = ["svg"]

    for file in files:
        ext = file.filename.split(".")[-1].lower()
        mime = file.mimetype
        fname = file.filename

        # PDF files
        if ext == "pdf" or mime == "application/pdf":
            pdfs.append(file)
        # TIFF images
        elif ext in tiff_exts:
            img = Image.open(file.stream)
            imgs.append(img)
        # BMP images
        elif ext in bmp_exts:
            img = Image.open(file.stream)
            imgs.append(img)
        # SVG images
        elif ext in svg_exts:
            try:
                from cairosvg import svg2png
                png_bytes = svg2png(bytestring=file.read(), dpi=dpi)
                img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
                imgs.append(img)
            except ImportError:
                return jsonify({"error": "cairosvg not installed"}), 500
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
        # Other images
        else:
            try:
                img = Image.open(file.stream)
                imgs.append(img)
            except Exception as e:
                import traceback
                print("DEBUG ERROR:", str(e))
                print(traceback.format_exc())
                return jsonify({"error": f"Image error: {str(e)}"}), 400

    # Apply grayscale if selected
    if grayscale:
        imgs = [img.convert("L").convert("RGB") for img in imgs]

    # PDF compression with slider-based quality (only for single PDF file)
    if pdfs and output_format == "pdf":
        # Directly return the first PDF (no compression)
        pdf_data = pdfs[0].read() if hasattr(pdfs[0], "read") else pdfs[0].getvalue()
        output = io.BytesIO(pdf_data)
        output.seek(0)
        return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="converted.pdf")

    # Image(s) to PDF
    if imgs and output_format == "pdf":
        output = io.BytesIO()
        imgs[0].save(output, format="PDF", save_all=True, append_images=imgs[1:], resolution=dpi)
        output.seek(0)
        return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="converted.pdf")

    # Image(s) to image format
    if imgs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic", "tiff", "bmp"]:
        output = io.BytesIO()
        save_kwargs = {}
        if output_format in ["jpeg", "webp", "avif", "heif", "heic"]:
            save_kwargs["quality"] = quality
        save_kwargs["dpi"] = (dpi, dpi)
        imgs[0].save(output, format=output_format.upper(), **save_kwargs)
        output.seek(0)
        mime = f"image/{output_format}"
        ext = output_format
        return send_file(output, mimetype=mime, as_attachment=True, download_name=f"converted.{ext}")

    # PDF to image conversion (first page only, fast)
    if pdfs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic", "tiff", "bmp"]:
        try:
            import fitz
        except ImportError:
            return jsonify({"error": "PyMuPDF (fitz) not installed"}), 500
        pdf_data = pdfs[0].read() if hasattr(pdfs[0], "read") else pdfs[0].getvalue()
        pdf_doc = fitz.open(stream=pdf_data, filetype="pdf")
        page = pdf_doc.load_page(0)
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes(output="png")
        img = Image.open(io.BytesIO(img_bytes))
        # Apply grayscale if selected
        if grayscale:
            img = img.convert("L").convert("RGB")
        output = io.BytesIO()
        save_kwargs = {}
        if output_format in ["jpeg", "webp", "avif", "heif", "heic"]:
            save_kwargs["quality"] = quality
        save_kwargs["dpi"] = (dpi, dpi)
        img.save(output, format=output_format.upper(), **save_kwargs)
        output.seek(0)
        mime = f"image/{output_format}"
        ext = output_format
        return send_file(output, mimetype=mime, as_attachment=True, download_name=f"converted.{ext}")

    return jsonify({"error": "Conversion operation not supported or no valid files"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)