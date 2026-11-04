#!/usr/bin/env python3
"""
OpenCV document scanner and Tesseract OCR adapter for VehicleManager.

The script is intentionally a small command-line service so the existing PHP
API can call it from XAMPP without changing the rest of the application.
It never invents document values: field candidates are taken from OCR output
and the complete OCR text is returned for user verification.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise RuntimeError(message)


try:
    import cv2
    import numpy as np
    import pytesseract
except ImportError as exc:
    fail(
        "Missing scanner dependency: {}. Run `python -m pip install -r requirements.txt`."
        .format(exc.name or str(exc))
    )

if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")


FIELD_LABELS = {
    "rc": [
        ("registration_number", "Registration Number", ["registration no", "registration number", "reg no", "reg. no"]),
        ("owner_name", "Owner Name", ["owner name", "name of owner", "registered owner"]),
        ("vehicle_model", "Vehicle Model", ["model", "vehicle model", "model name"]),
        ("manufacturer", "Manufacturer", ["maker", "manufacturer", "maker name"]),
        ("fuel_type", "Fuel Type", ["fuel", "fuel type"]),
        ("registration_date", "Registration Date", ["registration date", "date of registration", "reg date"]),
        ("chassis_number", "Chassis Number", ["chassis no", "chassis number", "chassis"]),
        ("engine_number", "Engine Number", ["engine no", "engine number", "engine"]),
    ],
    "ins": [
        ("policy_number", "Policy Number", ["policy no", "policy number", "policy no."]),
        ("registration_number", "Registration Number", ["registration no", "registration number", "reg no", "vehicle no"]),
        ("insured_name", "Insured Name", ["insured name", "policy holder", "proposer name", "name of insured"]),
        ("insurance_company", "Insurance Company", ["insurance company", "insurer", "company name"]),
        ("policy_start_date", "Policy Start Date", ["policy start date", "policy start", "start date", "effective from", "valid from"]),
        ("policy_expiry_date", "Policy Expiry Date", ["policy expiry date", "policy expiry", "expiry date", "valid till", "valid until"]),
    ],
    "puc": [
        ("registration_number", "Registration Number", ["registration no", "registration number", "reg no", "vehicle number"]),
        ("certificate_number", "Certificate Number", ["certificate no", "certificate number", "puc no", "certificate"]),
        ("owner_name", "Owner Name", ["owner name", "name of owner"]),
        ("issue_date", "Issue Date", ["issue date", "date of issue", "test date"]),
        ("expiry_date", "Expiry Date", ["expiry date", "valid till", "valid until"]),
        ("emission_reading", "Emission Reading", ["emission", "co", "hc"]),
    ],
    "lic": [
        ("license_number", "License Number", ["driving licence no", "driving license no", "license no", "licence no"]),
        ("holder_name", "Holder Name", ["name", "holder name", "name of holder"]),
        ("date_of_birth", "Date of Birth", ["date of birth", "dob", "d.o.b"]),
        ("issue_date", "Issue Date", ["issue date", "date of issue"]),
        ("expiry_date", "Expiry Date", ["expiry date", "valid till", "valid until"]),
        ("address", "Address", ["address", "permanent address"]),
    ],
    "other": [
        ("document_number", "Document Number", ["document no", "document number", "certificate no", "number"]),
        ("holder_name", "Holder Name", ["holder name", "name", "owner name"]),
        ("issue_date", "Issue Date", ["issue date", "date of issue"]),
        ("expiry_date", "Expiry Date", ["expiry date", "valid till", "valid until"]),
        ("address", "Address", ["address"]),
    ],
}


def order_points(points):
    points = np.asarray(points, dtype=np.float32)
    result = np.zeros((4, 2), dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    result[0] = points[np.argmin(sums)]       # top-left
    result[2] = points[np.argmax(sums)]       # bottom-right
    result[1] = points[np.argmin(diffs)]      # top-right
    result[3] = points[np.argmax(diffs)]      # bottom-left
    return result


def four_point_transform(image, points):
    rect = order_points(points)
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_width = max(int(width_a), int(width_b), 1)
    max_height = max(int(height_a), int(height_b), 1)
    destination = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1],
    ], dtype=np.float32)
    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def decode_document(path):
    raw = Path(path).read_bytes()
    if raw[:4] == b"%PDF" or str(path).lower().endswith(".pdf"):
        try:
            import pymupdf as fitz
        except ImportError:
            try:
                import fitz
            except ImportError:
                fail("PDF scanning requires PyMuPDF. Install the requirements file.")
        pdf = fitz.open(stream=raw, filetype="pdf")
        if pdf.page_count == 0:
            fail("The PDF does not contain a page.")
        images = []
        for page_number in range(min(pdf.page_count, 20)):
            page = pdf.load_page(page_number)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2.2, 2.2), alpha=False)
            image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
                pixmap.height, pixmap.width, pixmap.n
            )
            images.append(cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        pdf.close()
        return images

    image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        fail("OpenCV could not decode the document image.")
    return [image]


def scan_document(image):
    height, width = image.shape[:2]
    if width < 1000:
        scale = min(2.0, 1000.0 / max(width, 1))
        image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    image_area = image.shape[0] * image.shape[1]
    candidate = None
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:30]:
        area = cv2.contourArea(contour)
        if area < image_area * 0.20:
            continue
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            candidate = polygon.reshape(4, 2)
            break

    if candidate is not None:
        corrected = four_point_transform(image, candidate)
    else:
        corrected = image

    corrected_gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
    corrected_gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(corrected_gray)
    threshold = cv2.adaptiveThreshold(
        corrected_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 31, 11
    )
    return corrected, [corrected, corrected_gray, threshold], candidate is not None


def run_ocr(variants):
    languages = os.getenv("TESSERACT_LANG", "eng")
    configs = ("--oem 3 --psm 6", "--oem 3 --psm 11")
    best = {"text": "", "confidence": 0.0, "score": -1}

    for variant in variants:
        for config in configs:
            data = pytesseract.image_to_data(
                variant, lang=languages, config=config,
                output_type=pytesseract.Output.DICT
            )
            words = []
            confidences = []
            for text, confidence in zip(data.get("text", []), data.get("conf", [])):
                text = text.strip()
                if not text:
                    continue
                words.append(text)
                try:
                    numeric_confidence = float(confidence)
                    if numeric_confidence >= 0:
                        confidences.append(numeric_confidence)
                except (TypeError, ValueError):
                    pass
            text = pytesseract.image_to_string(variant, lang=languages, config=config).strip()
            alphanumeric_count = len(re.findall(r"[A-Za-z0-9]", text))
            average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            score = alphanumeric_count + (average_confidence * 0.35)
            if score > best["score"]:
                best = {
                    "text": text,
                    "confidence": average_confidence,
                    "score": score,
                }
    return best["text"], best["confidence"]


def normalized(line):
    return re.sub(r"[^a-z0-9]+", " ", line.lower()).strip()


def value_after_label(lines, labels):
    for index, original_line in enumerate(lines):
        line = normalized(original_line)
        for label in sorted(labels, key=len, reverse=True):
            label_pattern = re.escape(label.strip()).replace(r"\ ", r"[\s._:-]+")
            if not label_pattern:
                continue
            match = re.search(r"(?<![a-z0-9])" + label_pattern + r"(?=\s|:|-|$)", original_line, flags=re.IGNORECASE)
            if not match:
                continue
            remainder = original_line[match.end():].strip(" :-\t")
            if remainder and len(remainder) > 1:
                return remainder
            if index + 1 < len(lines):
                next_line = lines[index + 1].strip(" :-\t")
                if next_line:
                    return next_line
    return ""


def first_regex(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(0).strip()
    return ""


def extract_fields(text, doc_type):
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    specs = FIELD_LABELS.get(doc_type, FIELD_LABELS["other"])
    extracted = {}
    fields = []

    for key, label, labels in specs:
        value = value_after_label(lines, labels)
        if not value and key == "registration_number":
            value = first_regex(text, [
                r"\b[A-Z]{2}\s?\d{1,2}\s?[A-Z]{1,3}\s?\d{3,4}\b",
                r"\b[A-Z]{2}[- ]?\d{2}[- ]?[A-Z]{1,3}[- ]?\d{3,4}\b",
            ])
        if value:
            extracted[key] = value
            fields.append({"key": key, "label": label, "value": value})

    return extracted, fields


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--doc-type", default="other")
    parser.add_argument("--filename", default="document")
    parser.add_argument("--tesseract", default="")
    args = parser.parse_args()

    if args.tesseract:
        pytesseract.pytesseract.tesseract_cmd = args.tesseract

    result = {
        "success": False,
        "filename": args.filename,
        "doc_type": args.doc_type,
        "raw_text": "",
        "extracted_fields": {},
        "fields": [],
        "confidence": 0.0,
        "document_detected": False,
    }

    try:
        images = decode_document(args.input)
        page_texts = []
        page_confidences = []
        detected = False
        for image in images:
            _, variants, page_detected = scan_document(image)
            page_text, page_confidence = run_ocr(variants)
            if page_text.strip():
                page_texts.append(page_text.strip())
            page_confidences.append(page_confidence)
            detected = detected or page_detected
        raw_text = "\n\n".join(page_texts)
        confidence = (
            sum(page_confidences) / len(page_confidences)
            if page_confidences else 0.0
        )
        extracted, fields = extract_fields(raw_text, args.doc_type)
        result.update({
            "success": True,
            "raw_text": raw_text,
            "extracted_fields": extracted,
            "fields": fields,
            "confidence": round(confidence, 2),
            "document_detected": detected,
            "readable": bool(raw_text.strip()),
            "message": "OCR completed" if raw_text.strip() else "No readable text found",
        })
    except Exception as exc:
        result["message"] = str(exc)
        with open(args.output, "w", encoding="utf-8") as output:
            json.dump(result, output, ensure_ascii=False)
        return 1

    with open(args.output, "w", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())