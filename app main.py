"""
NearCares - Migrated Version
  - MongoDB  (replaces MySQL)
  - Google Maps API  (replaces Mappls)
  - Google Maps deep link  (no JS map SDK needed)
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import requests, math, os, json, time
from datetime import datetime
from functools import wraps
from concurrent.futures import ThreadPoolExecutor, as_completed
from bson import ObjectId

# ── Load .env ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env loaded")
except ImportError:
    print("⚠️  Install python-dotenv: pip install python-dotenv")

# ── MongoDB ────────────────────────────────────────────────────────────────
try:
    from pymongo import MongoClient, DESCENDING
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://localhost:27017')
    try:
        import certifi
        _tls_kwargs = {'tls': True, 'tlsCAFile': certifi.where()}
    except ImportError:
        print("⚠️  certifi not installed (pip install certifi) — TLS handshake may fail on Windows")
        _tls_kwargs = {'tls': True}
    try:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=10000, socketTimeoutMS=10000, **_tls_kwargs)
        _client.server_info()
    except Exception:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=10000, socketTimeoutMS=10000, tls=True)
        _client.server_info()
    _db       = _client[os.environ.get('MONGO_DB', 'nearcares')]
    hospitals_col  = _db['hospitals']
    contacts_col   = _db['contacts']
    diseases_col   = _db['diseases']
    MONGO_OK = True
    print("✅ MongoDB connected")
except Exception as e:
    MONGO_OK = False
    print(f"⚠️  MongoDB not available: {e} — using JSON fallback")

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'nearcares-secret-2026')

ADMIN_USERNAME = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASS', 'admin123')

# ── Google Maps key ────────────────────────────────────────────────────────
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_KEY', '')
if not GOOGLE_MAPS_KEY:
    print("⚠️  GOOGLE_MAPS_KEY not set — hospital search will not work")

# ══════════════════════════════════════════════════════════════════════════
# JSON FALLBACK (when MongoDB is not available)
# ══════════════════════════════════════════════════════════════════════════

DATA_DIR       = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
CONTACTS_FILE  = os.path.join(DATA_DIR, 'contacts.json')
HOSPITALS_FILE = os.path.join(DATA_DIR, 'hospitals.json')
DISEASES_FILE  = os.path.join(DATA_DIR, 'diseases.json')
os.makedirs(DATA_DIR, exist_ok=True)

def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️  JSON load error {path}: {e}")
    return []

def _save_json(path, data):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"⚠️  JSON save error {path}: {e}")

# ══════════════════════════════════════════════════════════════════════════
# DATABASE HELPERS  (MongoDB first, JSON fallback)
# ══════════════════════════════════════════════════════════════════════════

def _serialize(doc):
    """Convert MongoDB _id ObjectId → string 'id' field."""
    if doc and '_id' in doc:
        doc = dict(doc)
        doc['id'] = str(doc.pop('_id'))
    return doc

# ── Hospitals ──────────────────────────────────────────────────────────────
def db_add_hospital(name, address, city, state, lat, lng, specialties, phone=''):
    record = {
        'name': name, 'address': address, 'city': city, 'state': state,
        'lat': lat, 'lng': lng, 'specialties': specialties, 'phone': phone,
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    if MONGO_OK:
        hospitals_col.insert_one(record)
        return
    hospitals = _load_json(HOSPITALS_FILE)
    record['id'] = max((h.get('id', 0) for h in hospitals), default=0) + 1
    hospitals.append(record)
    _save_json(HOSPITALS_FILE, hospitals)

def db_get_hospitals():
    if MONGO_OK:
        return [_serialize(h) for h in hospitals_col.find().sort('added_at', DESCENDING)]
    return list(reversed(_load_json(HOSPITALS_FILE)))

def db_delete_hospital(hid):
    if MONGO_OK:
        try:
            hospitals_col.delete_one({'_id': ObjectId(hid)})
        except Exception:
            hospitals_col.delete_one({'id': int(hid)})
        return
    data = [h for h in _load_json(HOSPITALS_FILE) if str(h.get('id')) != str(hid)]
    _save_json(HOSPITALS_FILE, data)

# ── Contacts ───────────────────────────────────────────────────────────────
def db_save_contact(name, email, message):
    record = {
        'name': name, 'email': email, 'message': message,
        'received_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'is_read': False
    }
    if MONGO_OK:
        contacts_col.insert_one(record)
        return
    contacts = _load_json(CONTACTS_FILE)
    record['id'] = max((c.get('id', 0) for c in contacts), default=0) + 1
    contacts.append(record)
    _save_json(CONTACTS_FILE, contacts)

def db_get_contacts():
    if MONGO_OK:
        return [_serialize(c) for c in contacts_col.find().sort('received_at', DESCENDING)]
    return list(reversed(_load_json(CONTACTS_FILE)))

def db_mark_read(cid):
    if MONGO_OK:
        try:
            contacts_col.update_one({'_id': ObjectId(cid)}, {'$set': {'is_read': True}})
        except Exception:
            contacts_col.update_one({'id': int(cid)}, {'$set': {'is_read': True}})
        return
    contacts = _load_json(CONTACTS_FILE)
    for c in contacts:
        if str(c.get('id')) == str(cid):
            c['is_read'] = True
    _save_json(CONTACTS_FILE, contacts)

def db_delete_contact(cid):
    if MONGO_OK:
        try:
            contacts_col.delete_one({'_id': ObjectId(cid)})
        except Exception:
            contacts_col.delete_one({'id': int(cid)})
        return
    data = [c for c in _load_json(CONTACTS_FILE) if str(c.get('id')) != str(cid)]
    _save_json(CONTACTS_FILE, data)

# ── Diseases ───────────────────────────────────────────────────────────────
def db_add_disease(name, specialties, icon='💊'):
    record = {'name': name, 'specialties': specialties, 'icon': icon}
    if MONGO_OK:
        diseases_col.insert_one(record)
        return
    diseases = _load_json(DISEASES_FILE)
    record['id'] = max((d.get('id', 0) for d in diseases), default=0) + 1
    diseases.append(record)
    _save_json(DISEASES_FILE, diseases)

def db_get_diseases():
    if MONGO_OK:
        return [_serialize(d) for d in diseases_col.find()]
    return _load_json(DISEASES_FILE)

def db_delete_disease(did):
    if MONGO_OK:
        try:
            diseases_col.delete_one({'_id': ObjectId(did)})
        except Exception:
            diseases_col.delete_one({'id': int(did)})
        return
    data = [d for d in _load_json(DISEASES_FILE) if str(d.get('id')) != str(did)]
    _save_json(DISEASES_FILE, data)

# ══════════════════════════════════════════════════════════════════════════
# GOOGLE MAPS API
# ══════════════════════════════════════════════════════════════════════════

# Google place `types` that mean "this is actually a healthcare place"
_ALLOWED_HEALTH_TYPES = {
    'hospital', 'doctor', 'health', 'physiotherapist',
    'dentist', 'pharmacy', 'medical_lab', 'clinic',
    'point_of_interest', 'establishment',
}
# Google place `types` that mean "this is NOT healthcare, drop it even if the
# text query matched" — Text Search does loose full-text matching, so a
# furniture shop named 'City Hospital Furniture Mart' or a salon calling
# itself 'Skin Clinic' can otherwise slip through.
_BLOCKED_TYPES = {
    'furniture_store', 'home_goods_store', 'store', 'shopping_mall',
    'hair_care', 'beauty_salon', 'spa', 'clothing_store', 'restaurant',
    'cafe', 'food', 'lodging', 'real_estate_agency', 'car_dealer',
    'electronics_store', 'shoe_store', 'jewelry_store', 'parking',
    'gym', 'moving_company', 'storage', 'insurance_agency',
}


def _is_real_healthcare_place(types, name=''):
    types = set(types or [])
    if types & _BLOCKED_TYPES:
        return False
    if types & _ALLOWED_HEALTH_TYPES:
        return True
    name_lower = (name or '').lower()
    healthcare_words = ['hospital', 'clinic', 'medical', 'health', 'nursing',
                        'dental', 'eye', 'heart', 'surgery', 'diagnostic',
                        'pathology', 'pharmacy', 'pharma', 'care']
    return any(w in name_lower for w in healthcare_words)


def _classify_place_type(types, keyword):
    """Decide Hospital vs Clinic from Google's place types + the search keyword."""
    types = types or []
    if 'hospital' in types:
        return 'Hospital'
    if 'doctor' in types or 'health' in types or 'physiotherapist' in types:
        return 'Clinic'
    if 'clinic' in keyword.lower():
        return 'Clinic'
    return 'Hospital'


def _parse_places_response(data, lat, lng, radius, keyword):
    """Parse Google Places API response into hospital dicts."""
    results = []
    skipped = 0
    for place in data.get('results', []):
        loc = place.get('geometry', {}).get('location', {})
        if 'lat' not in loc or 'lng' not in loc:
            continue
        place_types = place.get('types', [])
        place_name = place.get('name', '')
        if not _is_real_healthcare_place(place_types, place_name):
            skipped += 1
            continue
        dist_km = haversine(lat, lng, loc['lat'], loc['lng'])
        if dist_km > (radius / 1000):
            skipped += 1
            continue
        ptype = _classify_place_type(place_types, keyword)
        results.append({
            'name':           place.get('name', 'Healthcare Facility'),
            'address':        place.get('formatted_address', place.get('vicinity', '')),
            'lat':            float(loc['lat']),
            'lng':            float(loc['lng']),
            'distance':       round(dist_km, 2),
            'type':           ptype,
            'place_id':       place.get('place_id', ''),
            'phone':          place.get('international_phone_number', place.get('formatted_phone_number', '')),
            'source':         'google',
            'priority_rank':  0,
            'popularity':     float(place.get('user_ratings_total', 0) or 0),
            'display_rating': float(place.get('rating', 0) or 0),
        })
    if skipped:
        print(f"[Google Places] Filtered out {skipped} irrelevant/out-of-radius result(s) for '{keyword}'")
    return results


def google_nearby_places(lat, lng, radius=5000, keyword='hospital', max_pages=3):
    """Google Places Text Search with pagination."""
    if not GOOGLE_MAPS_KEY:
        return []
    radius = min(int(radius), 50000)
    all_results = []
    try:
        params = {
            'query':    keyword,
            'location': f'{lat},{lng}',
            'radius':   radius,
            'key':      GOOGLE_MAPS_KEY,
        }
        for page in range(max_pages):
            resp = requests.get(
                'https://maps.googleapis.com/maps/api/place/textsearch/json',
                params=params, timeout=10
            )
            data = resp.json()
            status = data.get('status')
            print(f"[Google TextSearch] status={status} keyword={keyword} page={page+1}")
            if status not in ('OK', 'ZERO_RESULTS'):
                break
            all_results.extend(_parse_places_response(data, lat, lng, radius, keyword))
            next_token = data.get('next_page_token')
            if not next_token or page == max_pages - 1:
                break
            time.sleep(2)
            params = {'pagetoken': next_token, 'key': GOOGLE_MAPS_KEY}
        return all_results
    except Exception as e:
        print(f"[Google TextSearch] Exception: {e}")
        return all_results


def google_nearby_search(lat, lng, radius=5000, keyword='hospital', max_pages=3):
    """Google Places Nearby Search — different algorithm than Text Search."""
    if not GOOGLE_MAPS_KEY:
        return []
    radius = min(int(radius), 50000)
    all_results = []
    try:
        params = {
            'location': f'{lat},{lng}',
            'radius':   radius,
            'type':     'hospital',
            'key':      GOOGLE_MAPS_KEY,
        }
        if keyword and keyword.lower() not in ('hospital', 'clinic'):
            params['keyword'] = keyword
        for page in range(max_pages):
            resp = requests.get(
                'https://maps.googleapis.com/maps/api/place/nearbysearch/json',
                params=params, timeout=10
            )
            data = resp.json()
            status = data.get('status')
            print(f"[Google NearbySearch] status={status} keyword={keyword} page={page+1}")
            if status not in ('OK', 'ZERO_RESULTS'):
                break
            all_results.extend(_parse_places_response(data, lat, lng, radius, keyword))
            next_token = data.get('next_page_token')
            if not next_token or page == max_pages - 1:
                break
            time.sleep(2)
            params = {'pagetoken': next_token, 'key': GOOGLE_MAPS_KEY}
        return all_results
    except Exception as e:
        print(f"[Google NearbySearch] Exception: {e}")
        return all_results



def google_geocode(address):
    """Convert address string → lat/lng using Google Geocoding API."""
    if not GOOGLE_MAPS_KEY:
        return None
    try:
        resp = requests.get(
            'https://maps.googleapis.com/maps/api/geocode/json',
            params={'address': address, 'components': 'country:IN', 'key': GOOGLE_MAPS_KEY},
            timeout=10
        )
        data = resp.json()
        if data.get('status') == 'OK' and data.get('results'):
            r   = data['results'][0]
            loc = r['geometry']['location']
            return {
                'lat': float(loc['lat']),
                'lng': float(loc['lng']),
                'formatted_address': r.get('formatted_address', address)
            }
    except Exception as e:
        print(f"[Google Geocode] {e}")
    return None


def google_reverse_geocode(lat, lng):
    """Convert lat/lng → address using Google Reverse Geocoding API."""
    if not GOOGLE_MAPS_KEY:
        return None
    try:
        resp = requests.get(
            'https://maps.googleapis.com/maps/api/geocode/json',
            params={'latlng': f'{lat},{lng}', 'key': GOOGLE_MAPS_KEY},
            timeout=10
        )
        data = resp.json()
        if data.get('status') == 'OK' and data.get('results'):
            r = data['results'][0]
            city = state = ''
            for comp in r.get('address_components', []):
                if 'locality' in comp.get('types', []):
                    city = comp.get('long_name', '')
                if 'administrative_area_level_1' in comp.get('types', []):
                    state = comp.get('long_name', '')
            return {
                'formatted_address': r.get('formatted_address', f'{lat},{lng}'),
                'city':  city,
                'state': state,
            }
    except Exception as e:
        print(f"[Google Reverse Geocode] {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════
# DOMAIN DATA  (same as original)
# ══════════════════════════════════════════════════════════════════════════

MULTISPECIALTY_WORDS = [
    'apollo','shalby','zydus','sterling','fortis','max','medanta',
    'narayana','manipal','kokilaben','medistar','safal','hope','kiran',
    'vedanta','multispecialt','multi specialt','super specialt',
]

SPECIALTIES = {
    'orthopedic':    {'label': '🦴 Orthopedic & Bone',       'icon': '🦴', 'keywords': ['ortho','orthopedic','bone','joint','fracture','spine','arthroplasty','arthritis']},
    'neurology':     {'label': '🧠 Neurology & Brain',        'icon': '🧠', 'keywords': ['neuro','neurology','brain','stroke','epilepsy']},
    'ent':           {'label': '👂 ENT',                      'icon': '👂', 'keywords': ['ent','ear','nose','throat','sinus','audiolog']},
    'ophthalmology': {'label': '👁️ Eye Hospital',             'icon': '👁️', 'keywords': ['eye','ophthalm','vision','retina','cataract','netralaya']},
    'cardiology':    {'label': '❤️ Cardiology & Heart',       'icon': '❤️', 'keywords': ['cardio','cardiac','heart','cardiovascular','angioplasty']},
    'pulmonology':   {'label': '🫁 Pulmonology & Chest',      'icon': '🫁', 'keywords': ['pulmo','pulmonary','lung','chest','respiratory','asthma']},
    'gastro':        {'label': '🫃 Gastroenterology',         'icon': '🫃', 'keywords': ['gastro','digestive','intestine','bowel','colonoscopy']},
    'oncology':      {'label': '🎗️ Cancer & Oncology',        'icon': '🎗️', 'keywords': ['onco','oncology','cancer','tumour','tumor','radiotherapy']},
    'nephrology':    {'label': '🫘 Kidney & Nephrology',      'icon': '🫘', 'keywords': ['nephro','kidney','renal','dialysis','urology']},
    'endocrinology': {'label': '💊 Diabetes & Endocrinology', 'icon': '💊', 'keywords': ['endocrin','diabetes','diabetology','hormone','bariatric']},
    'dermatology':   {'label': '🧴 Skin & Dermatology',       'icon': '🧴', 'keywords': ['derma','skin clinic','cosmet','trichology']},
    'psychiatry':    {'label': '🧘 Psychiatry & Mental Health','icon': '🧘', 'keywords': ['psychiatr','psychology','mental health','addiction','counselling']},
    'gynecology':    {'label': '🤰 Gynecology & Obstetrics',  'icon': '🤰', 'keywords': ['gynecol','obstetric','maternity','women','ladies','womens health','fetal','pregnancy','delivery','infertility','ivf']},
    'dental':        {'label': '🦷 Dental & Oral',            'icon': '🦷', 'keywords': ['dental','dentist','tooth','teeth','orthodont','oral','periodontic']},
    'pediatrics':    {'label': '👶 Pediatrics & Child',       'icon': '👶', 'keywords': ['pediatr','child','children','baby','neonat','paediatr']},
    'fertility':     {'label': '🧬 Fertility & IVF',          'icon': '🧬', 'keywords': ['fertil','ivf','test tube','infertility','reproductive']},
    'urology':       {'label': '🔬 Urology',                  'icon': '🔬', 'keywords': ['urolog','prostate','bladder','urinary tract']},
    'general':       {'label': '🏥 General Medicine',         'icon': '🏥', 'keywords': ['general medicine','family medicine','polyclinic','nursing home']},
}

BODY_PART_SPECIALTIES = {
    # Head region
    'head':       ['neurology', 'ent', 'ophthalmology', 'psychiatry'],
    'brain':      ['neurology', 'psychiatry'],
    'eyes':       ['ophthalmology'],
    'ear':        ['ent'],
    'nose':       ['ent'],
    'throat':     ['ent'],
    'mouth':      ['ent'],
    'face':       ['ent', 'dermatology'],
    # Neck & upper
    'neck':       ['ent', 'neurology', 'orthopedic'],
    'shoulders':  ['orthopedic'],
    'shoulder':   ['orthopedic'],
    # Chest & core
    'chest':      ['cardiology', 'pulmonology'],
    'heart':      ['cardiology'],
    'lungs':      ['pulmonology'],
    'stomach':    ['gastro'],
    'abdomen':    ['gastro', 'nephrology'],
    'liver':      ['gastro'],
    'kidney':     ['nephrology'],
    # Upper limbs
    'arms':       ['orthopedic'],
    'arm':        ['orthopedic'],
    'wrist':      ['orthopedic'],
    'hand':       ['orthopedic'],
    'elbow':      ['orthopedic'],
    # Spine & back
    'back':       ['orthopedic', 'neurology'],
    'spine':      ['orthopedic', 'neurology'],
    'lower_back': ['orthopedic', 'neurology'],
    # Lower limbs
    'hips':       ['orthopedic'],
    'hip':        ['orthopedic'],
    'knees':      ['orthopedic'],
    'knee':       ['orthopedic'],
    'legs':       ['orthopedic'],
    'leg':        ['orthopedic'],
    'ankle':      ['orthopedic'],
    'feet':       ['orthopedic'],
    'foot':       ['orthopedic'],
    # Skin
    'skin':       ['dermatology'],
}

ILLNESS_SPECIALTIES = {
    'fever':         ['general'],
    'cough':         ['pulmonology', 'ent'],
    'cold':          ['ent', 'general'],
    'flu':           ['general', 'pulmonology'],
    'diarrhea':      ['gastro'],
    'vomiting':      ['gastro', 'general'],
    'fatigue':       ['general', 'endocrinology'],
    'heart_disease': ['cardiology'],
    'bp':            ['cardiology', 'general'],
    'hypertension':  ['cardiology', 'general'],
    'chest_pain':    ['cardiology', 'pulmonology'],
    'asthma':        ['pulmonology'],
    'breathing':     ['pulmonology', 'cardiology'],
    'liver':         ['gastro'],
    'gastric':       ['gastro'],
    'acidity':       ['gastro'],
    'constipation':  ['gastro'],
    'kidney':        ['nephrology'],
    'urinary':       ['nephrology', 'urology'],
    'arthritis':     ['orthopedic'],
    'back_pain':     ['orthopedic', 'neurology'],
    'fracture':      ['orthopedic'],
    'joint_pain':    ['orthopedic'],
    'bone':          ['orthopedic'],
    'headache':      ['neurology', 'general'],
    'migraine':      ['neurology'],
    'stroke':        ['neurology'],
    'epilepsy':      ['neurology'],
    'paralysis':     ['neurology'],
    'eye':           ['ophthalmology'],
    'vision':        ['ophthalmology'],
    'cataract':      ['ophthalmology'],
    'thyroid':       ['endocrinology'],
    'ear_pain':      ['ent'],
    'sinus':         ['ent'],
    'tonsil':        ['ent'],
    'skin':          ['dermatology'],
    'allergy':       ['dermatology', 'pulmonology'],
    'rash':          ['dermatology'],
    'acne':          ['dermatology'],
    'depression':    ['psychiatry'],
    'anxiety':       ['psychiatry'],
    'stress':        ['psychiatry'],
    'insomnia':      ['psychiatry'],
    'diabetes':      ['endocrinology'],
    'obesity':       ['endocrinology'],
    'hormone':       ['endocrinology'],
    'cancer':        ['oncology'],
    'tumor':         ['oncology'],
    'gynecologist':  ['gynecology'],
    'gynecology':    ['gynecology'],
    'pregnancy':     ['gynecology'],
    'maternity':     ['gynecology'],
    'delivery':      ['gynecology'],
    'period':        ['gynecology'],
    'menstrual':     ['gynecology'],
    'infertility':   ['fertility', 'gynecology'],
    'ivf':           ['fertility'],
    'dental':        ['dental'],
    'toothache':     ['dental'],
    'teeth':         ['dental'],
    'child':         ['pediatrics'],
    'baby':          ['pediatrics'],
    'pediatric':     ['pediatrics'],
    'prostate':      ['urology'],
    'bladder':       ['urology', 'nephrology'],
    'stones':        ['nephrology', 'urology'],
    'appendix':      ['gastro', 'general'],
    'hernia':        ['gastro', 'general'],
    'piles':         ['gastro'],
    'fistula':       ['gastro'],
    'varicose':      ['orthopedic', 'general'],
}

# Keywords to use when calling Google Places Text Search per specialty
# These are plain text search queries — Google matches against place names/types
SPECIALTY_SEARCH_KEYWORDS = {
    'orthopedic':    ['orthopedic hospital', 'bone hospital', 'ortho clinic', 'joint clinic', 'joint replacement', 'spine hospital', 'fracture clinic', 'arthritis hospital'],
    'neurology':     ['neurology hospital', 'neuro clinic', 'brain hospital', 'stroke hospital', 'epilepsy clinic', 'spine specialist', 'neuro surgery'],
    'ent':           ['ent hospital', 'ear nose throat', 'ent clinic', 'sinus clinic', 'hearing clinic', 'throat specialist'],
    'ophthalmology': ['eye hospital', 'eye clinic', 'netralaya', 'vision centre', 'retina clinic', 'lasik clinic', 'cataract surgery'],
    'cardiology':    ['heart hospital', 'cardiac hospital', 'cardiology clinic', 'heart surgery', 'angioplasty', 'cardiac care', 'bypass surgery'],
    'pulmonology':   ['chest hospital', 'lung clinic', 'pulmonology', 'respiratory clinic', 'asthma clinic', 'tb hospital', 'breathing specialist'],
    'gastro':        ['gastroenterology', 'gastro clinic', 'digestive clinic', 'liver hospital', 'colonoscopy', 'endoscopy', 'hepatology'],
    'oncology':      ['cancer hospital', 'oncology centre', 'cancer clinic', 'tumor hospital', 'chemotherapy', 'radiation therapy', 'cancer surgery'],
    'nephrology':    ['kidney hospital', 'nephrology clinic', 'dialysis centre', 'kidney transplant', 'renal clinic', 'urology hospital'],
    'endocrinology': ['diabetes clinic', 'endocrinology', 'diabetology', 'thyroid clinic', 'hormone clinic', 'metabolism clinic'],
    'dermatology':   ['skin clinic', 'dermatology clinic', 'skin hospital', 'hair clinic', 'allergy clinic', 'cosmetic clinic'],
    'psychiatry':    ['psychiatry', 'mental health clinic', 'psychology clinic', 'depression clinic', 'anxiety clinic', 'rehabilitation centre'],
    'gynecology':    ['gynecology', 'maternity hospital', 'women hospital', 'obstetrics', 'ivf centre', 'pregnancy care', 'delivery hospital'],
    'dental':        ['dental hospital', 'dental clinic', 'dental care', 'ortho dental', 'root canal', 'implant clinic', 'smile clinic'],
    'pediatrics':    ['children hospital', 'pediatric hospital', 'child clinic', 'kids hospital', 'neonatal', 'child specialist'],
    'fertility':     ['ivf centre', 'fertility clinic', 'test tube baby', 'infertility clinic', 'iui clinic', 'embryo transfer'],
    'urology':       ['urology hospital', 'urology clinic', 'prostate clinic', 'kidney stone', 'bladder clinic', 'urinary specialist'],
    'general':       ['hospital', 'clinic', 'medical centre', 'nursing home'],
}

DISEASE_DIRECT_SEARCHES = {
    'fever':         ['general physician', 'fever clinic', 'general practitioner'],
    'cough':         ['cough specialist', 'chest doctor', 'respiratory clinic', 'pulmonologist'],
    'cold':          ['ent specialist', 'cold flu clinic', 'throat doctor'],
    'flu':           ['general physician', 'flu treatment', 'fever doctor'],
    'diarrhea':      ['gastroenterologist', 'stomach doctor', 'gastro clinic'],
    'vomiting':      ['gastroenterologist', 'stomach specialist', 'nausea treatment'],
    'fatigue':       ['general physician', 'health checkup', 'thyroid specialist'],
    'heart_disease': ['heart hospital', 'cardiac surgeon', 'angioplasty', 'cardiac care', 'heart specialist'],
    'bp':            ['bp specialist', 'heart clinic', 'hypertension doctor', 'cardiologist'],
    'hypertension':  ['cardiologist', 'bp doctor', 'heart clinic', 'hypertension specialist'],
    'chest_pain':    ['emergency hospital', 'cardiac care', 'heart emergency', 'chest specialist'],
    'asthma':        ['asthma clinic', 'pulmonologist', 'respiratory specialist', 'breathing treatment'],
    'breathing':     ['pulmonologist', 'respiratory clinic', 'lung specialist', 'breathing problem doctor'],
    'liver':         ['liver specialist', 'hepatologist', 'gastroenterologist', 'liver hospital'],
    'gastric':       ['gastric treatment', 'stomach specialist', 'gastro clinic', 'acid reflux doctor'],
    'acidity':       ['acidity treatment', 'stomach doctor', 'gastro clinic', 'acid reflux specialist'],
    'constipation':  ['gastroenterologist', 'digestive specialist', 'stomach doctor'],
    'kidney':        ['kidney specialist', 'nephrologist', 'kidney hospital', 'renal clinic'],
    'urinary':       ['urologist', 'urinary specialist', 'kidney stone doctor', 'bladder specialist'],
    'arthritis':     ['arthritis specialist', 'rheumatologist', 'joint pain doctor', 'orthopedic surgeon'],
    'back_pain':     ['spine specialist', 'back pain clinic', 'orthopedic surgeon', 'pain management'],
    'fracture':      ['fracture clinic', 'orthopedic surgeon', 'bone hospital', 'trauma center'],
    'joint_pain':    ['joint specialist', 'joint replacement', 'orthopedic surgeon', 'knee specialist'],
    'bone':          ['bone specialist', 'orthopedic surgeon', 'bone hospital'],
    'headache':      ['neurologist', 'migraine clinic', 'headache specialist', 'pain clinic'],
    'migraine':      ['migraine specialist', 'neurologist', 'headache clinic', 'migraine treatment'],
    'stroke':        ['stroke center', 'neurologist', 'emergency hospital', 'stroke specialist'],
    'epilepsy':      ['epilepsy clinic', 'neurologist', 'seizure specialist'],
    'paralysis':     ['neurologist', 'rehabilitation center', 'physiotherapy', 'paralysis treatment'],
    'eye':           ['eye specialist', 'ophthalmologist', 'eye hospital', 'vision clinic'],
    'vision':        ['eye specialist', 'vision clinic', 'optometrist', 'lasik clinic'],
    'cataract':      ['cataract surgery', 'eye hospital', 'cataract specialist', 'phaco surgery'],
    'thyroid':       ['thyroid specialist', 'endocrinologist', 'thyroid clinic', 'hormone specialist'],
    'ear_pain':      ['ent specialist', 'ear doctor', 'hearing clinic', 'ent hospital'],
    'sinus':         ['sinus specialist', 'ent doctor', 'sinus clinic', 'nose specialist'],
    'tonsil':        ['ent specialist', 'throat doctor', 'tonsil removal', 'ent hospital'],
    'skin':          ['skin specialist', 'dermatologist', 'skin clinic', 'skin hospital'],
    'allergy':       ['allergy clinic', 'allergy specialist', 'immunologist', 'skin allergy doctor'],
    'rash':          ['skin specialist', 'dermatologist', 'rash treatment', 'skin clinic'],
    'acne':          ['acne treatment', 'dermatologist', 'skin specialist', 'cosmetic clinic'],
    'depression':    ['psychiatrist', 'depression treatment', 'mental health clinic', 'counseling center'],
    'anxiety':       ['psychiatrist', 'anxiety treatment', 'mental health clinic', 'counseling center'],
    'stress':        ['mental health clinic', 'stress management', 'psychiatrist', 'counseling'],
    'insomnia':      ['sleep specialist', 'psychiatrist', 'sleep clinic', 'insomnia treatment'],
    'diabetes':      ['diabetologist', 'diabetes clinic', 'diabetes hospital', 'sugar doctor'],
    'obesity':       ['weight loss clinic', 'bariatric surgeon', 'obesity specialist', 'dietitian'],
    'hormone':       ['endocrinologist', 'hormone specialist', 'thyroid clinic', 'hormone therapy'],
    'cancer':        ['cancer hospital', 'oncologist', 'chemotherapy', 'tumor specialist'],
    'tumor':         ['oncologist', 'cancer hospital', 'tumor surgeon', 'cancer specialist'],
    'gynecologist':  ['gynecologist', 'women specialist', 'lady doctor', 'gynecology clinic'],
    'gynecology':    ['gynecologist', 'women hospital', 'maternity hospital', 'gynecology clinic'],
    'pregnancy':     ['maternity hospital', 'pregnancy care', 'obstetrician', 'delivery hospital'],
    'maternity':     ['maternity hospital', 'pregnancy care', 'delivery hospital'],
    'delivery':      ['maternity hospital', 'delivery hospital', 'obstetrician'],
    'period':        ['gynecologist', 'women specialist', 'period problems', 'menstrual clinic'],
    'menstrual':     ['gynecologist', 'menstrual disorder clinic', 'women specialist'],
    'infertility':   ['ivf centre', 'fertility clinic', 'infertility specialist', 'reproductive medicine'],
    'ivf':           ['ivf centre', 'fertility clinic', 'test tube baby', 'ivf specialist'],
    'dental':        ['dental hospital', 'dentist', 'dental clinic', 'tooth doctor'],
    'toothache':     ['dentist', 'dental clinic', 'tooth extraction', 'dental hospital'],
    'teeth':         ['dentist', 'dental clinic', 'orthodontist', 'dental hospital'],
    'child':         ['pediatrician', 'children hospital', 'child specialist', 'kids doctor'],
    'baby':          ['pediatrician', 'child specialist', 'baby doctor', 'children hospital'],
    'pediatric':     ['pediatrician', 'children hospital', 'child specialist'],
    'prostate':      ['urologist', 'prostate specialist', 'prostate clinic'],
    'bladder':       ['urologist', 'bladder specialist', 'urinary clinic'],
    'stones':        ['kidney stone specialist', 'urolithiasis', 'stone clinic', 'lithotripsy'],
    'appendix':      ['emergency hospital', 'general surgeon', 'appendix removal'],
    'hernia':        ['hernia specialist', 'general surgeon', 'hernia repair', 'hernia clinic'],
    'piles':         ['piles clinic', 'proctologist', 'fissure treatment', 'anal specialist'],
    'fistula':       ['fistula specialist', 'proctologist', 'anal fistula treatment'],
    'varicose':      ['vascular surgeon', 'varicose vein clinic', 'leg vein specialist'],
}

COMMON_ILLNESSES = {
    'fever':         {'icon': '🌡️', 'label': 'Fever'},
    'cough':         {'icon': '😷', 'label': 'Cough'},
    'cold':          {'icon': '🤧', 'label': 'Cold & Flu'},
    'diarrhea':      {'icon': '🚽', 'label': 'Diarrhea'},
    'cancer':        {'icon': '🎗️', 'label': 'Cancer'},
    'heart_disease': {'icon': '❤️',  'label': 'Heart Disease'},
    'bp':            {'icon': '💉', 'label': 'High BP'},
    'diabetes':      {'icon': '💊', 'label': 'Diabetes'},
    'asthma':        {'icon': '🫁', 'label': 'Asthma'},
    'kidney':        {'icon': '🫘', 'label': 'Kidney Issues'},
    'skin':          {'icon': '🧴', 'label': 'Skin Problems'},
    'eye':           {'icon': '👁️', 'label': 'Eye Problems'},
    'headache':      {'icon': '🤕', 'label': 'Headache'},
    'migraine':      {'icon': '😖', 'label': 'Migraine'},
    'liver':         {'icon': '🫀', 'label': 'Liver Issues'},
    'depression':    {'icon': '😔', 'label': 'Depression'},
    'anxiety':       {'icon': '😰', 'label': 'Anxiety'},
    'thyroid':       {'icon': '🦋', 'label': 'Thyroid'},
    'arthritis':     {'icon': '🦴', 'label': 'Arthritis'},
    'back_pain':     {'icon': '🔙', 'label': 'Back Pain'},
    'gynecologist':  {'icon': '🤰', 'label': 'Gynecologist'},
    'pregnancy':     {'icon': '🤰', 'label': 'Pregnancy'},
    'dental':        {'icon': '🦷', 'label': 'Dental Problems'},
    'child':         {'icon': '👶', 'label': 'Child Health'},
    'infertility':   {'icon': '🧬', 'label': 'Infertility / IVF'},
    'prostate':      {'icon': '🔬', 'label': 'Prostate Issues'},
    'stones':        {'icon': '💎', 'label': 'Kidney Stones'},
    'hernia':        {'icon': '🩹', 'label': 'Hernia'},
    'piles':         {'icon': '💊', 'label': 'Piles / Fissure'},
}

# ══════════════════════════════════════════════════════════════════════════
# UTILS
# ══════════════════════════════════════════════════════════════════════════

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)), 2)

def is_multispecialty(name, address=''):
    text = (name + ' ' + address).lower()
    return any(w in text for w in MULTISPECIALTY_WORDS)

def spec_score(name, address, sid):
    text = (name + ' ' + address).lower()
    return sum(1 for kw in SPECIALTIES[sid]['keywords'] if kw in text)

def classify(h, needed):
    """Classify hospital into specialties. Score >= 1 means at least one
    keyword matched (e.g. 'heart' in 'Heart Hospital')."""
    matched = [(s, spec_score(h['name'], h.get('address',''), s)) for s in needed]
    return [m[0] for m in sorted(matched, key=lambda x: -x[1]) if m[1] >= 1]

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated

# ══════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    all_illnesses = dict(COMMON_ILLNESSES)
    for d in db_get_diseases():
        key = d['name'].lower().replace(' ', '_')
        all_illnesses[key] = {'icon': d.get('icon','💊'), 'label': d['name']}
    return render_template('index.html', illnesses=all_illnesses)

@app.route('/hospitals')
def hospitals():
    return render_template('hospitals.html')

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/tips')
def tips():
    return render_template('tips.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

# ══════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.route('/admin/login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if (request.form.get('username') == ADMIN_USERNAME and
                request.form.get('password') == ADMIN_PASSWORD):
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Invalid credentials', 'error')
    return render_template('admin/login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

@app.route('/admin')
@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    hospitals_list  = db_get_hospitals()
    contacts_list   = db_get_contacts()
    unread_count    = sum(1 for c in contacts_list if not c.get('is_read'))
    custom_diseases = db_get_diseases()
    return render_template('admin/dashboard.html',
        hospitals=hospitals_list, contacts=contacts_list,
        unread_count=unread_count, custom_diseases=custom_diseases,
        db_ok=MONGO_OK, all_specialties=list(SPECIALTIES.keys()))

@app.route('/admin/hospitals/add', methods=['POST'])
@admin_required
def admin_add_hospital():
    name = request.form.get('name','').strip()
    if not name:
        flash('Name is required', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        lat = float(request.form.get('lat') or 0)
        lng = float(request.form.get('lng') or 0)
    except ValueError:
        lat = lng = 0.0
    db_add_hospital(name,
        request.form.get('address','').strip(),
        request.form.get('city','').strip(),
        request.form.get('state','').strip(),
        lat, lng,
        request.form.get('specialties','').strip(),
        request.form.get('phone','').strip())
    flash(f'✅ Hospital "{name}" added!', 'success')
    return redirect(url_for('admin_dashboard') + '#hospitals')

@app.route('/admin/hospitals/delete/<hid>', methods=['POST'])
@admin_required
def admin_delete_hospital(hid):
    db_delete_hospital(hid)
    flash('Hospital deleted', 'success')
    return redirect(url_for('admin_dashboard') + '#hospitals')

@app.route('/admin/contacts/read/<cid>', methods=['POST'])
@admin_required
def admin_mark_read(cid):
    db_mark_read(cid)
    return redirect(url_for('admin_dashboard') + '#contacts')

@app.route('/admin/contacts/delete/<cid>', methods=['POST'])
@admin_required
def admin_delete_contact(cid):
    db_delete_contact(cid)
    flash('Message deleted', 'success')
    return redirect(url_for('admin_dashboard') + '#contacts')

@app.route('/admin/contacts/view/<cid>')
@admin_required
def admin_view_contact(cid):
    contacts = db_get_contacts()
    c = next((x for x in contacts if str(x.get('id', '')) == str(cid)), None)
    if not c:
        return jsonify({'error': 'Not found'}), 404
    db_mark_read(cid)
    return jsonify({
        'id':          c.get('id'),
        'name':        c.get('name', ''),
        'email':       c.get('email', ''),
        'message':     c.get('message', ''),
        'received_at': str(c.get('received_at', '')),
    })

@app.route('/admin/diseases/add', methods=['POST'])
@admin_required
def admin_add_disease():
    name = request.form.get('name','').strip()
    if name:
        db_add_disease(name,
            request.form.get('specialties','').strip(),
            request.form.get('icon','💊').strip() or '💊')
        flash(f'Disease "{name}" added', 'success')
    return redirect(url_for('admin_dashboard') + '#diseases')

@app.route('/admin/diseases/delete/<did>', methods=['POST'])
@admin_required
def admin_delete_disease(did):
    db_delete_disease(did)
    flash('Disease removed', 'success')
    return redirect(url_for('admin_dashboard') + '#diseases')

# ══════════════════════════════════════════════════════════════════════════
# API ROUTES
# ══════════════════════════════════════════════════════════════════════════

@app.route('/api/search-hospitals', methods=['POST'])
def api_search_hospitals():
    try:
        data         = request.get_json()
        body_part    = data.get('body_part','').lower().strip()
        illness_type = data.get('illness_type','').lower().strip()
        user_lat     = float(data.get('lat', 0))
        user_lng     = float(data.get('lng', 0))
        radius       = int(data.get('radius', 5000))
        limit        = int(data.get('limit', 50))
        custom_query = data.get('custom_query','').lower().strip()

        if not user_lat or not user_lng:
            return jsonify({'error': 'Missing location'}), 400

        # Determine what symptoms/condition the user searched for
        disease_key = ''
        if custom_query:
            custom_diseases = db_get_diseases()
            m = next((d for d in custom_diseases if custom_query in d['name'].lower()), None)
            if m:
                needed = [s.strip() for s in m['specialties'].split(',') if s.strip()]
                label  = m['name']
                disease_key = custom_query
            else:
                best = next((k for k in ILLNESS_SPECIALTIES if custom_query in k.replace('_',' ')), None)
                if best:
                    needed = ILLNESS_SPECIALTIES[best]
                    disease_key = best
                else:
                    matched_specs = []
                    for sid, spec in SPECIALTIES.items():
                        if sid == 'general':
                            continue
                        if any(kw in custom_query for kw in spec['keywords']):
                            matched_specs.append(sid)
                    needed = matched_specs if matched_specs else ['general']
                label = custom_query.title()
        elif illness_type and illness_type in ILLNESS_SPECIALTIES:
            needed = ILLNESS_SPECIALTIES[illness_type]
            label  = COMMON_ILLNESSES.get(illness_type, {}).get('label', illness_type.title())
            disease_key = illness_type
        elif body_part and body_part in BODY_PART_SPECIALTIES:
            needed = BODY_PART_SPECIALTIES[body_part]
            label  = body_part.title()
        else:
            needed = ['general']
            label  = 'General'

        raw = []

        # 1. Admin-added hospitals from DB (highest priority)
        for h in db_get_hospitals():
            if not (h.get('lat') and h.get('lng')):
                continue
            dist = haversine(user_lat, user_lng, float(h['lat']), float(h['lng']))
            if dist <= radius / 1000:
                raw.append({
                    'name':           h['name'],
                    'address':        ' '.join(filter(None, [h.get('address'), h.get('city'), h.get('state')])),
                    'lat':            float(h['lat']),
                    'lng':            float(h['lng']),
                    'distance':       dist,
                    'type':           'Hospital',
                    'place_id':       f"db:{h.get('id','')}",
                    'popularity':     10.0,
                    'display_rating': 4.8,
                    'priority_rank':  3,
                    'source':         'database',
                    'phone':          h.get('phone','')
                })

        # 2. Google — ALL API calls run in PARALLEL for speed
        #    Google treats radius as bias, not strict — so we send 1.5x
        #    to get more results, haversine filter keeps actual radius only.
        google_radius = int(radius * 1.5)
        tasks = {}
        for kw in ['hospital', 'clinic', 'medical centre', 'nursing home']:
            tasks[f'text_{kw}'] = (google_nearby_places, user_lat, user_lng, google_radius, kw, 3)
        for kw in ['hospital', 'clinic', 'doctor']:
            tasks[f'nearby_{kw}'] = (google_nearby_search, user_lat, user_lng, google_radius, kw, 2)
        specialty_kws = []
        for sid in needed:
            for kw in SPECIALTY_SEARCH_KEYWORDS.get(sid, []):
                specialty_kws.append(kw)
        for i, kw in enumerate(specialty_kws[:5]):
            tasks[f'spec_{i}'] = (google_nearby_places, user_lat, user_lng, google_radius, kw, 2)

        # Disease-specific direct searches
        disease_kws = DISEASE_DIRECT_SEARCHES.get(disease_key, [])
        if not disease_kws and custom_query:
            disease_kws = [f'{custom_query} hospital', f'{custom_query} specialist', f'{custom_query} clinic']
        for i, kw in enumerate(disease_kws[:3]):
            tasks[f'disease_{i}'] = (google_nearby_places, user_lat, user_lng, google_radius, kw, 2)
        with ThreadPoolExecutor(max_workers=12) as executor:
            futures = {}
            for name, (fn, *args) in tasks.items():
                futures[executor.submit(fn, *args)] = name
            for future in as_completed(futures):
                try:
                    task_name = futures[future]
                    results = future.result()
                    # Tag disease-specific and specialty-specific results as relevant
                    if task_name.startswith('disease_') or task_name.startswith('spec_'):
                        for r in results:
                            r['relevant'] = True
                            r['priority_rank'] = max(r.get('priority_rank', 0), 1)
                    raw.extend(results)
                except Exception as e:
                    print(f"[Parallel] Task {futures[future]} failed: {e}")

        # 4. Deduplicate map results
        seen_ids = set()
        seen_names = set()
        deduped = []
        max_dist_km = radius / 1000
        for h in sorted(raw, key=lambda x: (-x.get('priority_rank', 0), x['distance'])):
            if h.get('distance', 999) > max_dist_km:
                continue
            pid = h.get('place_id', '')
            name_key = h['name'].strip().lower()[:40]
            loc_key = f"{h.get('lat',0):.5f},{h.get('lng',0):.5f}"
            if pid and pid in seen_ids:
                continue
            combined_key = f"{name_key}|{loc_key}"
            if combined_key in seen_names:
                continue
            if pid:
                seen_ids.add(pid)
            seen_names.add(combined_key)
            deduped.append(h)

        # 5. Tag each hospital with relevance to the user's search
        for h in deduped:
            # Don't overwrite relevant=True already set by disease/specialty searches
            if h.get('relevant'):
                matched = classify(h, needed)
                if matched:
                    h['specialty_label'] = SPECIALTIES.get(matched[0],{}).get('label', matched[0])
                else:
                    h['specialty_label'] = SPECIALTIES.get(needed[0],{}).get('label', needed[0]) if needed else ''
            else:
                matched = classify(h, needed)
                if matched:
                    h['relevant'] = True
                    h['specialty_label'] = SPECIALTIES.get(matched[0],{}).get('label', matched[0])
                else:
                    h['relevant'] = False
                    h['specialty_label'] = ''

        # 5. Sort — hospitals first, then clinics
        hospitals = [h for h in deduped if h.get('type') == 'Hospital']
        clinics   = [h for h in deduped if h.get('type') != 'Hospital']

        def hospital_sort(h):
            return (-h.get('priority_rank', 0),
                    -h.get('display_rating', 0),
                    -1 if h.get('relevant') else 0,
                    h['distance'])
        def clinic_sort(h):
            return (-h.get('priority_rank', 0),
                    -h.get('display_rating', 0),
                    -1 if h.get('relevant') else 0,
                    h['distance'])

        hospitals.sort(key=hospital_sort)
        clinics.sort(key=clinic_sort)

        # 6. Build groups — ONLY relevant + multispecialty hospitals
        groups = []

        # Relevant hospitals matching the search
        relevant_hospitals = [h for h in hospitals if h.get('relevant')]
        if relevant_hospitals:
            sp = SPECIALTIES.get(needed[0], {}) if needed else {}
            groups.append({
                'id': 'relevant_hospitals',
                'label': f'🏥 {label} — Matching Hospitals',
                'icon': sp.get('icon', '🏥'),
                'hospitals': relevant_hospitals
            })

        # Multispecialty hospitals (Apollo, Zydus etc.) — can handle any condition
        multi_hospitals = [h for h in hospitals if not h.get('relevant') and is_multispecialty(h['name'], h.get('address',''))]
        if multi_hospitals:
            groups.append({
                'id': 'multispecialty',
                'label': '⭐ Multispecialty Hospitals',
                'icon': '⭐',
                'hospitals': multi_hospitals
            })

        # Only show relevant clinics
        relevant_clinics = [c for c in clinics if c.get('relevant')]
        if relevant_clinics:
            groups.append({
                'id': 'relevant_clinics',
                'label': '🩺 Matching Clinics',
                'icon': '🩺',
                'hospitals': relevant_clinics
            })

        if not groups and deduped:
            groups.append({
                'id': 'general',
                'label': '🏥 Hospitals & Clinics near you',
                'icon': '🏥',
                'hospitals': deduped
            })

        trimmed = []
        for g in groups:
            hs = g['hospitals'][:limit]
            if hs:
                trimmed.append({**g, 'hospitals': hs})

        return jsonify({'success': True, 'groups': trimmed,
            'total': sum(len(g['hospitals']) for g in trimmed),
            'search_label': label, 'radius_km': radius/1000,
            'sort_by': 'rating'})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/geocode', methods=['POST'])
def api_geocode():
    try:
        address = request.get_json().get('address','')
        if not address:
            return jsonify({'error': 'Address required'}), 400
        result = google_geocode(address)
        if result:
            return jsonify({'success': True, **result})
        return jsonify({'error': 'Address not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/reverse-geocode', methods=['POST'])
def api_reverse_geocode():
    try:
        data = request.get_json() or {}
        lat  = float(data.get('lat', 0))
        lng  = float(data.get('lng', 0))
        if not lat or not lng:
            return jsonify({'error': 'lat/lng required'}), 400
        result = google_reverse_geocode(lat, lng)
        if result:
            return jsonify({'success': True, **result})
        return jsonify({'error': 'Location not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/contact', methods=['POST'])
def api_contact():
    try:
        data    = request.get_json(force=True, silent=True) or {}
        name    = str(data.get('name','')).strip()
        email   = str(data.get('email','')).strip()
        message = str(data.get('message','')).strip()
        if not name or not email or not message:
            return jsonify({'error': 'All fields required'}), 400
        db_save_contact(name, email, message)
        return jsonify({'success': True, 'message': 'Thank you! We will get back to you soon.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/diseases')
def api_diseases():
    combined = [{'key':k,'label':v['label'],'icon':v['icon'],'source':'builtin'}
                for k,v in COMMON_ILLNESSES.items()]
    for d in db_get_diseases():
        combined.append({'key':d['name'].lower().replace(' ','_'),
                         'label':d['name'],'icon':d.get('icon','💊'),'source':'custom'})
    return jsonify(combined)


@app.route('/api/status')
def api_status():
    return jsonify({
        'mongo':                MONGO_OK,
        'google_maps_key_set':  bool(GOOGLE_MAPS_KEY),
    })


@app.route('/api/suggest', methods=['POST'])
def api_suggest():
    """Return hospital/clinic name suggestions as user types.
    Combines disease list with Google Places for hospital names."""
    try:
        data    = request.get_json() or {}
        q       = data.get('q', '').strip().lower()
        lat     = float(data.get('lat', 0) or 0)
        lng     = float(data.get('lng', 0) or 0)
        radius  = int(data.get('radius', 10000))
        if not q or len(q) < 2:
            return jsonify({'suggestions': []})

        suggestions = []

        # 1. Disease/condition matches
        all_diseases = [{'key': k, 'label': v['label'], 'icon': v['icon'], 'type': 'condition'}
                        for k, v in COMMON_ILLNESSES.items()]
        for d in db_get_diseases():
            all_diseases.append({'key': d['name'].lower().replace(' ','_'),
                                 'label': d['name'], 'icon': d.get('icon','💊'), 'type': 'condition'})

        def _rank(label):
            ll = label.lower()
            if ll.startswith(q):         return 0
            words = ll.split()
            if any(w.startswith(q) for w in words): return 1
            if q in ll:                  return 2
            return 3

        disease_matches = sorted(
            [d for d in all_diseases if _rank(d['label']) < 3],
            key=lambda d: _rank(d['label'])
        )[:5]
        for d in disease_matches:
            suggestions.append({
                'text':  d['label'],
                'icon':  d['icon'],
                'type':  'condition',
                'key':   d['key'],
            })

        # 2. Google Places for hospital names near location
        if lat and lng and GOOGLE_MAPS_KEY:
            try:
                resp = requests.get(
                    'https://maps.googleapis.com/maps/api/place/textsearch/json',
                    params={
                        'query':    f'{q} hospital clinic',
                        'location': f'{lat},{lng}',
                        'radius':   min(radius, 50000),
                        'key':      GOOGLE_MAPS_KEY,
                    },
                    timeout=8
                )
                pdata = resp.json()
                if pdata.get('status') == 'OK':
                    for place in pdata.get('results', [])[:8]:
                        name = place.get('name', '')
                        addr = place.get('formatted_address', place.get('vicinity', ''))
                        loc  = place.get('geometry', {}).get('location', {})
                        dist = haversine(lat, lng, loc.get('lat',0), loc.get('lng',0)) if lat and lng else 0
                        rating = float(place.get('rating', 0) or 0)
                        place_types = set(place.get('types', []))
                        if place_types & _BLOCKED_TYPES:
                            continue
                        suggestions.append({
                            'text':     name,
                            'subtext':  addr,
                            'icon':     '🏥',
                            'type':     'hospital',
                            'rating':   rating,
                            'distance': round(dist, 1),
                            'lat':      loc.get('lat', 0),
                            'lng':      loc.get('lng', 0),
                        })
            except Exception as e:
                print(f"[Suggest] Google error: {e}")

        return jsonify({'suggestions': suggestions[:12]})
    except Exception as e:
        return jsonify({'suggestions': [], 'error': str(e)})


# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 55)
    print("🏥  NearCares  (MongoDB + Google Maps)")
    print(f"🗄️   MongoDB: {'✅ Connected' if MONGO_OK else '⚠️  Fallback to JSON'}")
    print("🌐  http://localhost:5000")
    print("🔐  http://localhost:5000/admin  (admin / admin123)")
    print("=" * 55)
    # use_reloader=False fixes WinError 10038 on Windows (Flask socket reloader bug)
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
