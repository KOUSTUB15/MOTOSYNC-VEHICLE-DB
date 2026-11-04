#!/usr/bin/env python3
"""
MotoSync Fuel / EV Charging Meter OCR scanner.
Uses the same OpenCV + Tesseract approach as the existing document_scanner.py.
It extracts only values actually visible in the image; it does not invent values.
"""
import argparse, json, os, re, sys, base64
from pathlib import Path

try:
    import cv2
    import numpy as np
    import pytesseract
except ImportError as exc:
    print(f"Missing scanner dependency: {exc}. Install opencv-python, numpy, pytesseract.", file=sys.stderr)
    sys.exit(2)

if os.getenv("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.getenv("TESSERACT_CMD")

NUMBER = r"(?:\d{1,3}(?:[,.]\d{3})*|\d+)(?:[.,]\d+)?"

def num(s):
    if not s: return None
    s = s.replace('₹','').replace('Rs.','').replace('Rs','').replace('INR','').replace(' ','')
    # Indian/comma formatting: 1,234.56 -> 1234.56; decimal comma -> decimal point
    if ',' in s and '.' in s:
        s = s.replace(',','')
    elif ',' in s:
        parts=s.split(',')
        s = ''.join(parts[:-1])+'.'+parts[-1] if len(parts[-1]) <= 2 else ''.join(parts)
    s = re.sub(r'[^0-9.]','',s)
    try: return float(s)
    except: return None

def preprocess(img):
    h,w=img.shape[:2]
    if w < 1400:
        scale=min(2.5,1400/max(w,1))
        img=cv2.resize(img,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    gray=cv2.createCLAHE(clipLimit=2.5,tileGridSize=(8,8)).apply(gray)
    blur=cv2.GaussianBlur(gray,(3,3),0)
    otsu=cv2.threshold(blur,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
    adaptive=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,11)
    return img,[img,gray,otsu,adaptive]

def ocr_best(variants):
    best={'text':'','confidence':0.0,'score':-1}
    for im in variants:
        for psm in (6,11,12,13):
            cfg=f'--oem 3 --psm {psm}'
            data=pytesseract.image_to_data(im,lang=os.getenv('TESSERACT_LANG','eng'),config=cfg,output_type=pytesseract.Output.DICT)
            texts=[]; conf=[]
            for t,c in zip(data.get('text',[]),data.get('conf',[])):
                t=t.strip()
                if t:
                    texts.append(t)
                    try:
                        c=float(c)
                        if c>=0: conf.append(c)
                    except: pass
            text=' '.join(texts).strip()
            avg=sum(conf)/len(conf) if conf else 0
            # Prefer text containing meter keywords and numeric characters.
            keyword=sum(1 for k in ('total','amount','volume','litre','liter','liters','litres','fuel','price','rate','kwh','energy','unit','charge','charging','cost','₹','rs') if k in text.lower())
            digits=len(re.findall(r'\d',text))
            score=digits + keyword*18 + avg*.25
            if score>best['score']:
                best={'text':text,'confidence':round(avg,2),'score':score}
    return best

def nearby_number(text, patterns):
    for p in patterns:
        m=re.search(p,text,re.I)
        if m:
            v=num(m.group(1))
            if v is not None: return v
    return None

def extract_fuel(text):
    # Work line-by-line first because station displays often put label and number on separate lines.
    lines=[x.strip() for x in re.split(r'[\n|]+',text) if x.strip()]
    joined=' '.join(lines)
    liters=nearby_number(joined,[rf'(?:volume|quantity|qty|litres?|liters?|fuel)\s*[:=]?\s*(?:rs\.?\s*)?({NUMBER})\s*(?:l|ltr|litre|liter|litres|liters)?'])
    cost=nearby_number(joined,[rf'(?:total|amount|sale|payable|cost)\s*[:=]?\s*(?:₹|rs\.?|inr)?\s*({NUMBER})',rf'(?:₹|rs\.?|inr)\s*({NUMBER})'])
    rate=nearby_number(joined,[rf'(?:price|rate|unit\s*price|price\s*/\s*l|rate\s*/\s*l)\s*[:=]?\s*(?:₹|rs\.?)?\s*({NUMBER})'])
    # Fallback: line based labels
    for i,line in enumerate(lines):
        low=line.lower()
        target=' '.join(lines[i:i+2])
        if liters is None and any(k in low for k in ('litre','liter','volume','quantity','qty')):
            m=re.search(NUMBER+r'\s*(?:l|ltr|litre|liter)?',target,re.I)
            if m: liters=num(m.group(0))
        if cost is None and any(k in low for k in ('total','amount','payable','cost')):
            m=re.search(r'(?:₹|rs\.?|inr)?\s*('+NUMBER+r')',target,re.I)
            if m: cost=num(m.group(1))
        if rate is None and any(k in low for k in ('price','rate')):
            m=re.search(r'(?:₹|rs\.?|inr)?\s*('+NUMBER+r')',target,re.I)
            if m: rate=num(m.group(1))
    if cost is None and liters is not None and rate is not None: cost=round(liters*rate,2)
    if rate is None and cost is not None and liters and liters>0: rate=round(cost/liters,2)
    return {'expense_type':'fuel','liters':liters,'cost':cost,'rate_per_liter':rate}

def extract_charging(text):
    joined=' '.join(x.strip() for x in re.split(r'[\n|]+',text) if x.strip())
    energy=nearby_number(joined,[rf'(?:energy|units?|consumption|charged)\s*[:=]?\s*({NUMBER})\s*(?:kwh|kw\s*h|units?)?',rf'({NUMBER})\s*(?:kwh|kw\s*h)'])
    cost=nearby_number(joined,[rf'(?:total|amount|payable|cost|charging\s*cost)\s*[:=]?\s*(?:₹|rs\.?|inr)?\s*({NUMBER})',rf'(?:₹|rs\.?|inr)\s*({NUMBER})'])
    rate=nearby_number(joined,[rf'(?:price|rate|tariff|unit\s*price|price\s*/\s*kwh|rate\s*/\s*kwh)\s*[:=]?\s*(?:₹|rs\.?)?\s*({NUMBER})'])
    if cost is None and energy is not None and rate is not None: cost=round(energy*rate,2)
    if rate is None and cost is not None and energy and energy>0: rate=round(cost/energy,2)
    return {'expense_type':'charging','energy_kwh':energy,'cost':cost,'rate_per_kwh':rate}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--input',required=True)
    ap.add_argument('--output',required=True)
    ap.add_argument('--meter-type',choices=['fuel','charging'],required=True)
    ap.add_argument('--filename',default='meter.jpg')
    args=ap.parse_args()
    result={'success':False,'meter_type':args.meter_type,'filename':args.filename,'raw_text':'','confidence':0,'fields':{},'readable':False,'message':''}
    try:
        raw=Path(args.input).read_bytes()
        img=cv2.imdecode(np.frombuffer(raw,dtype=np.uint8),cv2.IMREAD_COLOR)
        if img is None: raise RuntimeError('OpenCV could not decode the meter image')
        original,variants=preprocess(img)
        ocr=ocr_best(variants)
        fields=extract_fuel(ocr['text']) if args.meter_type=='fuel' else extract_charging(ocr['text'])
        result.update({'success':True,'raw_text':ocr['text'],'confidence':ocr['confidence'],'fields':fields,'readable':bool(ocr['text'].strip()),'message':'Meter OCR completed' if ocr['text'].strip() else 'No readable meter values found'})
        # Return the exact uploaded image so the UI can keep a receipt/meter proof image.
        mime='image/jpeg'
        if args.filename.lower().endswith('.png'): mime='image/png'
        result['image_data']='data:'+mime+';base64,'+base64.b64encode(raw).decode('ascii')
    except Exception as exc:
        result['message']=str(exc)
        with open(args.output,'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)
        return 1
    with open(args.output,'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False)
    return 0

if __name__=='__main__': sys.exit(main())
