# VehicleManager OpenCV document scanning

The previous scan flow returned hard-coded demo values after a timeout. It
now sends the selected image, camera frame, or PDF to `document_scanner.py`.
The scanner:

1. loads the document with OpenCV (and renders PDF pages with PyMuPDF);
2. detects a large four-corner document contour;
3. corrects perspective, enhances contrast, and creates an adaptive threshold;
4. runs Tesseract OCR on multiple preprocessing modes;
5. returns document-specific field candidates **and the complete OCR text**.

No name, registration number, policy number, or other field is fabricated by
the application. OCR values are still editable because image quality,
lighting, handwriting, and document fonts can cause OCR errors. The complete
raw OCR result is shown and saved with the document so that no detected text
is silently discarded.

## Installation on XAMPP

Copy these files into the same folder as `api.php`:

- `api.php`
- `document_scanner.py`
- `index.html`

Install Python packages from a terminal:

```bash
python -m pip install -r requirements.txt
```

Install the Tesseract executable separately and make sure it is available on
the system `PATH`. If Apache cannot see the system `PATH`, set the
`TESSERACT_CMD` environment variable to the full path of the executable.

- Windows: install Tesseract, then set `DOCUMENT_SCANNER_PYTHON` to the full
  path of `python.exe` if `python3` is not the command used by XAMPP.
- Linux/macOS: install the system Tesseract package and use
  `DOCUMENT_SCANNER_PYTHON` if `python3` is not on PHP's `PATH`.

For example, on Windows Apache you may set the environment variable to:

```text
DOCUMENT_SCANNER_PYTHON=C:\Users\YOUR_USER\AppData\Local\Programs\Python\Python312\python.exe
```

Do not put that setting inside the browser code. It belongs to the Apache/PHP
environment so the Python path is not exposed to users.

## File limits

The existing normal document upload behaviour remains limited to 50KB. OCR
scans accept image/PDF input up to 10MB because a camera photo that is useful
for OCR is normally larger than 50KB. The existing localStorage vehicle
storage behaviour is unchanged.

## Quick test

From the folder containing `document_scanner.py`:

```bash
python document_scanner.py --input sample-rc.jpg --output result.json --doc-type rc
```

The output JSON contains `raw_text`, `fields`, `extracted_fields`,
`confidence`, and `document_detected`. Open the web app through Apache (not
`file://`) so the browser can call the existing PHP API.