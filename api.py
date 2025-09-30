import os
import io
import tempfile
import subprocess

from flask import Flask, send_from_directory, send_file, request, jsonify
from PIL import Image, ImageOps

app = Flask(__name__)

@app.route('/')
def serve_index():
    return send_from_directory('.', 'index.html')

@app.route('/convert', methods=['POST'])
def convert():
    # Get files and options
    files = list(request.files.values())
    if not files:
        return jsonify({"error": "No files uploaded"}), 400

    quality = int(request.form.get("quality", 80))
    resize_width = request.form.get("resize_width")
    resize_height = request.form.get("resize_height")
    output_format = request.form.get("output_format", "pdf").lower()
    dpi = int(request.form.get("dpi", 150))
    grayscale = request.form.get("grayscale", "0") == "1"

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
            # HEIF/HEIC support
            if ext in ["heif", "heic"]:
                try:
                    import pillow_heif
                    heif_file = pillow_heif.read_heif(file.read())
                    img = Image.frombytes(
                        heif_file.mode, heif_file.size, heif_file.data, "raw"
                    )
                except ImportError:
                    return jsonify({"error": "pillow-heif not installed"}), 500
            # AVIF support
            elif ext == "avif":
                img = Image.open(file.stream).convert("RGB")
            # SVG to PNG for PDF
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
                # Resize if needed
                if resize_width and resize_height:
                    img = img.resize((int(resize_width), int(resize_height)))
                # Grayscale if needed
                if grayscale:
                    img = ImageOps.grayscale(img)
                imgs.append(img)

    # If PDF(s) uploaded and asked for conversion to images
    if pdfs and output_format in ["jpeg", "png", "webp", "svg", "avif", "heif", "heic"]:
        try:
            import fitz
        except ImportError:
            return jsonify({"error": "PyMuPDF (fitz) not installed"}), 500
        images_from_pdf = []
        for pdf in pdfs:
            pdf_stream = io.BytesIO(pdf.read())
            pdf_doc = fitz.open(stream=pdf_stream.read(), filetype="pdf")
            for page_num in range(pdf_doc.page_count):
                page = pdf_doc.load_page(page_num)
                pix = page.get_pixmap(dpi=dpi)
                img_bytes = pix.tobytes(output="png")
                img = Image.open(io.BytesIO(img_bytes))
                # Resize/grayscale if needed
                if resize_width and resize_height:
                    img = img.resize((int(resize_width), int(resize_height)))
                if grayscale:
                    img = ImageOps.grayscale(img)
                images_from_pdf.append(img)
        # Save all images to archive or single if one page
        output = io.BytesIO()
        if len(images_from_pdf) == 1:
            images_from_pdf[0].save(output, format=output_format.upper(), quality=quality)
        else:
            # Save as zip
            import zipfile
            with zipfile.ZipFile(output, 'w') as zipf:
                for i, img in enumerate(images_from_pdf):
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format=output_format.upper(), quality=quality)
                    img_bytes.seek(0)
                    zipf.writestr(f"page_{i+1}.{output_format}", img_bytes.read())
            output.seek(0)
            return send_file(
                output,
                mimetype="application/zip",
                as_attachment=True,
                download_name="converted_images.zip"
            )
        output.seek(0)
        mime = f"image/{output_format}"
        ext = output_format
        return send_file(output, mimetype=mime, as_attachment=True, download_name=f"converted.{ext}")

    # If images uploaded, output as PDF
    if imgs and output_format == "pdf":
        output = io.BytesIO()
        imgs[0].save(output, format="PDF", save_all=True, append_images=imgs[1:], resolution=dpi)
        output.seek(0)
        return send_file(output, mimetype="application/pdf", as_attachment=True, download_name="converted.pdf")

    # If images uploaded, output as image format
    if imgs and output_format in ["jpeg", "png", "webp", "avif", "heif", "heic"]:
        output = io.BytesIO()
        imgs[0].save(output, format=output_format.upper(), quality=quality)
        output.seek(0)
        mime = f"image/{output_format}"
        ext = output_format
        return send_file(output, mimetype=mime, as_attachment=True, download_name=f"converted.{ext}")

    # If PDF uploaded and output format is PDF (compression)
    if pdfs and output_format == "pdf":
        # Compress PDF using Ghostscript
        with tempfile.NamedTemporaryFile(suffix=".pdf") as in_file, tempfile.NamedTemporaryFile(suffix=".pdf") as out_file:
            pdfs[0].save(in_file.name)
            gs_cmd = [
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS=/ebook",
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

    return jsonify({"error": "Conversion operation not supported or no valid files"}), 400

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)