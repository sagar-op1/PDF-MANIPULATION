from flask import Flask, render_template, request, send_file, flash, send_from_directory, redirect, url_for
from PyPDF2 import PdfFileMerger as PdfMerger, PdfFileReader as PdfReader, PdfFileWriter as PdfWriter
from io import BytesIO
import os
from datetime import datetime
from docx import Document
import tempfile
import fitz
from pdf2docx import Converter
import shutil
import zipfile
from PIL import Image
import io
from reportlab.pdfgen import canvas
from werkzeug.datastructures import FileStorage

app = Flask(__name__)
app.secret_key = 'your_secret_key'

UPLOAD_FOLDER = 'uploads'
CONVERTED_FOLDER = 'converted'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CONVERTED_FOLDER'] = CONVERTED_FOLDER
app.config['LOAD_FOLDER'] = 'static/input_pdfs'

# Ensure the upload folder exists
os.makedirs(app.config['LOAD_FOLDER'], exist_ok=True)


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


@app.route('/', methods=['GET', 'POST'])
def index():
    return render_template('index.html')


# noinspection PyTypeChecker
@app.route('/merge', methods=['GET', 'POST'])
def merge():
    if request.method == "POST":
        pdf_files = request.files.getlist("pdf_files")

        if len(pdf_files) <= 1:
            flash("Error: Please upload multiple PDF files for merging.", "error")
            return render_template('merge.html')

        for pdf in pdf_files:
            if not pdf or not allowed_file(pdf.filename):
                flash("Error: Please upload valid PDF files only.", "error")
                return render_template('merge.html')

        merger = PdfMerger()
        pdf: FileStorage
        for pdf in pdf_files:
            merger.append(pdf)

        buffer = BytesIO()
        merger.write(buffer)
        buffer.seek(0)

        # Save the merged PDF temporarily
        merged_filename = os.path.join(tempfile.mkdtemp(), "merged.pdf")
        with open(merged_filename, "wb") as f:
            f.write(buffer.read())

        # Redirect to a new endpoint to initiate the download
        return redirect(url_for('download_merged', filename="merged.pdf"))

    return render_template('merge.html')


@app.route('/download_merged/<filename>')
def download_merged(filename):
    # Serve the merged PDF for download
    return send_from_directory(tempfile.gettempdir(), filename, as_attachment=True)


# UPLOAD_FOLDER = 'uploads'
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/split')
def split():
    return render_template('split.html')


@app.route('/split', methods=['POST'])
def split_pdf():
    # Check if the post request has the file part
    if 'pdf_files' not in request.files:
        return render_template('split.html', error='No file part')

    pdf_files = request.files.getlist('pdf_files')
    split_results = []

    # Check if the user selected at least one file
    if not pdf_files or pdf_files[0].filename == '':
        return render_template('split.html', error='No selected file')

    # Create the uploads folder if it doesn't exist
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    # Process each uploaded PDF file
    for pdf_file in pdf_files:
        filename = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
        pdf_file.save(filename)

        # Split the PDF into two parts and get file paths made by
        part1_file_path, part2_file_path = split_pdf_file(filename)

        # Add the split results to the list
        split_results.append({'part1': part1_file_path, 'part2': part2_file_path})

    return render_template('split.html', success='PDF files split successfully', split_results=split_results)


def split_pdf_file(file_path):
    with open(file_path, 'rb') as file:
        input_pdf = PdfReader(file)
        output_pdf1 = PdfWriter()
        output_pdf2 = PdfWriter()

        total_pages = len(input_pdf.pages)
        mid_point = total_pages // 2

        # Add pages to the first PDF
        for page_num in range(mid_point):
            output_pdf1.add_page(input_pdf.pages[page_num])

        # Add pages to the second PDF
        for page_num in range(mid_point, total_pages):
            output_pdf2.add_page(input_pdf.pages[page_num])

        # Create file paths for the split PDFs
        part1_file_path = file_path.replace('.pdf', '_part1.pdf')
        part2_file_path = file_path.replace('.pdf', '_part2.pdf')

        # Write the two split PDFs to new files sunny god
        with open(part1_file_path, 'wb') as part1_file:
            output_pdf1.write(part1_file)

        with open(part2_file_path, 'wb') as part2_file:
            output_pdf2.write(part2_file)

        # Return file paths
        return part1_file_path, part2_file_path


@app.route('/download_part/<filename>')
def download_part(filename):
    # Serve the split PDF part for download
    return send_file(filename, as_attachment=True)


@app.route('/menu')
def menu():
    return render_template('menu.html')


@app.route('/compress')
def compress():
    return render_template('compress.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return render_template('compress.html', message='No file part')

    file = request.files['file']

    if file.filename == '':
        return render_template('compress.html', message='No selected file')

    if file and allowed_file(file.filename):
        # Save the uploaded file to a temporary directory
        temp_dir = tempfile.mkdtemp()
        filename = os.path.join(temp_dir, file.filename)
        file.save(filename)

        # Compress the PDF before further processing
        compressed_filename = compress_pdf(filename)

        return send_file(compressed_filename, as_attachment=True)

    return render_template('compress.html', message='Invalid file type')


def compress_pdf(input_file):
    output_file = os.path.join(os.path.dirname(input_file), f"compressed_{os.path.basename(input_file)}")

    with open(input_file, 'rb') as input_pdf:
        pdf_reader = PdfReader(input_pdf)
        pdf_writer = PdfWriter()

        for page_num in range(len(pdf_reader.pages)):
            pdf_writer.addPage(pdf_reader.pages[page_num])

        with open(output_file, 'wb') as output_pdf:
            pdf_writer.write(output_pdf)

    return output_file


def add_page_numbers(input_path, output_path):
    input_pdf = PdfReader(input_path)
    output_pdf = PdfWriter()

    for page_number in range(len(input_pdf.pages)):
        page = input_pdf.pages[page_number]
        media_box = page.mediabox
        width, height = media_box.width, media_box.height

        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(width, height))
        text = f"Page {page_number + 1}"

        # Adjust x-coordinate to move the text to the right side of the page
        x_coordinate = width - 50

        can.drawString(x_coordinate, 50, text)
        can.save()

        packet.seek(0)
        new_pdf = PdfReader(packet)
        page.merge_page(new_pdf.pages[0])
        output_pdf.add_page(page)

    with open(output_path, 'wb') as output_file:
        output_pdf.write(output_file)


@app.route('/Pagenumber', methods=['GET', 'POST'])
def Pagenumber():
    if request.method == 'POST':
        if 'pdf_file' not in request.files:
            return render_template('Pagenumber.html', error='No file part')

        pdf_file = request.files['pdf_file']

        if pdf_file.filename == '':
            return render_template('Pagenumber.html', error='No selected file')

        if pdf_file:
            input_path = os.path.join(app.config['UPLOAD_FOLDER'], pdf_file.filename)
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], 'PageNumber.pdf')

            pdf_file.save(input_path)
            add_page_numbers(input_path, output_path)

            return send_file(output_path, as_attachment=True)

    return render_template('Pagenumber.html')


@app.route('/pdf_docx')
def pdf_docx():
    return render_template('pdf_docx.html')


@app.route('/convert', methods=['POST'])
def convert():
    if 'file' not in request.files:
        return render_template('pdf_docx.html', error='No file part')

    file = request.files['file']

    if file.filename == '':
        return render_template('pdf_docx.html', error='No selected file')

    if file and allowed_file(file.filename):
        # Save the uploaded file to a temporary directory
        temp_dir = tempfile.mkdtemp()
        pdf_path = os.path.join(temp_dir, file.filename)
        file.save(pdf_path)

        # Compress the PDF before conversion
        compressed_pdf_path = compress_pdf(pdf_path)

        # Convert compressed PDF to DOCX
        docx_filename = file.filename.rsplit('.', 1)[0] + '.docx'
        pdf_to_docx(compressed_pdf_path, docx_filename)

        # Provide the converted file for download
        response = send_file(docx_filename, as_attachment=True,
                             mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document')

        # Remove the temporary files
        os.remove(pdf_path)
        os.remove(compressed_pdf_path)

        return response

    return render_template('pdf_docx.html', error='Invalid file type')


def pdf_to_docx(pdf_path, docx_filename):

    cv = Converter(pdf_path)
    cv.convert(docx_filename, start=0, end=None)
    cv.close()


# def allowed_file(filename):
#     return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def convert_pdf_to_images(pdf_path, output_folder):
    pdf_document = fitz.open(pdf_path)

    image_paths = []

    for page_number in range(pdf_document.page_count):
        page = pdf_document[page_number]
        pixmap = page.get_pixmap()

        # Convert Pixmap to Pillow Image
        img = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

        image_path = os.path.join(output_folder, f"page_{page_number + 1}.png")
        image_paths.append(image_path)

        # Save the Pillow Image to a PNG file
        img.save(image_path)

    pdf_document.close()

    return image_paths


@app.route('/Pdf_jpg')
def Pdf_jpg():
    return render_template('Pdf_jpg.html')


@app.route('/uploads', methods=['POST'])
def uploads_file():
    if 'file' not in request.files:
        return "No file part"

    file = request.files['file']

    if file.filename == '':
        return "No selected file"

    # Create the upload folder if it doesn't exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # Save the uploaded PDF file
    pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], 'input.pdf')
    file.save(pdf_path)

    # Create the converted images folder if it doesn't exist
    converted_images_folder = os.path.join(app.config['CONVERTED_FOLDER'], 'images')
    os.makedirs(converted_images_folder, exist_ok=True)

    # Convert PDF to images
    image_paths = convert_pdf_to_images(pdf_path, converted_images_folder)

    # Create a zip file
    zip_filename = os.path.join(app.config['CONVERTED_FOLDER'], 'output.zip')
    with zipfile.ZipFile(zip_filename, 'w') as zipf:
        for image_path in image_paths:
            zipf.write(image_path, os.path.basename(image_path))

    # Clean up: Remove the uploaded PDF and images
    os.remove(pdf_path)
    shutil.rmtree(converted_images_folder)

    return send_file(zip_filename, as_attachment=True, download_name='Image.zip')


if __name__ == '_main_':
    app.run(debug=True)
    