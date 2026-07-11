"""
NearCares - Migrated Version
  - MongoDB  (replaces MySQL)
  - Google Maps API  (replaces Mappls)
  - Google Maps deep link  (no JS map SDK needed)

VERCEL FIXES vs original:
  1. DATA_DIR → /tmp  (Vercel root fs is read-only; only /tmp is writable)
  2. MONGO_URI default is '' not 'mongodb://localhost:27017'  (localhost doesn't exist on Vercel)
  3. MongoDB block won't crash startup if MONGO_URI is missing
  4. app.run() only called locally — Vercel uses api/index.py as WSGI handler
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import requests, math, os, json
from datetime import datetime
from functools import wraps
from bson import ObjectId

# ── Load .env ──────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env loaded")
except ImportError:
    print("⚠️  Install python-dotenv: pip install python-dotenv")

# ── MongoDB ────────────────────────────────────────────────────────────────
# FIX 1: default is '' so missing MONGO_URI won't try to connect to localhost
MONGO_OK       = False
hospitals_col  = None
contacts_col   = None
diseases_col   = None

try:
    from pymongo import MongoClient, DESCENDING
    MONGO_URI = os.environ.get('MONGO_URI', '')
    if not MONGO_URI:
        raise ValueError("MONGO_URI env var not set — falling back to JSON")
    try:
        import certifi
        _tls_kwargs = {'tls': True, 'tlsCAFile': certifi.where()}
    except ImportError:
        print("⚠️  certifi not installed (pip install certifi) — TLS handshake may fail on Windows")
        _tls_kwargs = {}
    _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, **_tls_kwargs)
    _client.server_info()           # will raise if unreachable
    _db            = _client[os.environ.get('MONGO_DB', 'nearcares')]
    hospitals_col  = _db['hospitals']
    contacts_col   = _db['contacts']
    diseases_col   = _db['diseases']
    MONGO_OK       = True
    print("✅ MongoDB connected")
except Exception as e:
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
# JSON FALLBACK — FIX 2: /tmp is the only writable dir on Vercel
# ══════════════════════════════════════════════════════════════════════════

DATA_DIR       = os.path.join('/tmp', 'nearcares_data')
CONTACTS_FILE  = os.path.join(DATA_DIR, 'contacts.json')
HOSPITALS_FILE = os.path.join(DATA_DIR, 'hospitals.json')
DISEASES_FILE  = os.path.join(DATA_DIR, 'diseases.json')

try:
    os.makedirs(DATA_DIR, exist_ok=True)
except Exception as e:
    print(f"⚠️  Could not create DATA_DIR ({DATA_DIR}): {e}")

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
    'dentist', 'pharmacy', 'medical_lab',
}
# Google place `types` that mean "this is NOT healthcare, drop it even if the
# text query matched" — Text Search does loose full-text matching, so a
# furniture shop named 'City Hospital Furniture Mart' or a salon calling
# itself 'Skin Clinic' can otherwise slip through.
_BLOCKED_TYPES = {
    'furniture_store', 'home_goods_store', 'store', 'shopping_mall',
    'hair_care', 'beauty_salon', 'spa', 'clothing_store', 'restaurant',
    'cafe', 'food', 'lodging', 'real_estate_agency', 'car_dealer',
    'electronics_store', 'shoe_store', 'jewelry_store',
}


def _is_real_healthcare_place(types):
    types = set(types or [])
    if types & _BLOCKED_TYPES:
        return False
    return bool(types & _ALLOWED_HEALTH_TYPES)


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


def google_nearby_places(lat, lng, radius=5000, keyword='hospital'):
    """Google Places Text Search — returns list of hospital/clinic dicts.
    Text Search (not Nearby Search) is used because it accepts free-text
    keywords like 'orthopedic clinic', not just fixed place types.
    Results are filtered by Google's `types` field so non-healthcare
    businesses that merely match the search text (furniture shops, salons,
    etc.) don't get included."""
    if not GOOGLE_MAPS_KEY:
        return []
    radius = min(int(radius), 50000)
    try:
        resp = requests.get(
            'https://maps.googleapis.com/maps/api/place/textsearch/json',
            params={
                'query':    keyword,
                'location': f'{lat},{lng}',
                'radius':   radius,
                'key':      GOOGLE_MAPS_KEY,
            },
            timeout=15
        )
        data = resp.json()
        status = data.get('status')
        print(f"[Google Places] status={status} keyword={keyword}")
        if status not in ('OK', 'ZERO_RESULTS'):
            print(f"[Google Places] Error: {data.get('error_message','')}")
            return []
        results = []
        skipped = 0
        for place in data.get('results', []):
            loc = place.get('geometry', {}).get('location', {})
            if 'lat' not in loc or 'lng' not in loc:
                continue
            place_types = place.get('types', [])
            if not _is_real_healthcare_place(place_types):
                skipped += 1
                continue
            dist_km = haversine(lat, lng, loc['lat'], loc['lng'])
            if dist_km > (radius / 1000):
                # Google's Text Search `radius` is only a soft bias, not a hard
                # cutoff — it can still return places far outside it (this is
                # what caused 60km+/entire-country results to show up).
                skipped += 1
                continue
            ptype = _classify_place_type(place_types, keyword)
            results.append({
                'name':           place.get('name', 'Healthcare Facility'),
                'address':        place.get('formatted_address', ''),
                'lat':            float(loc['lat']),
                'lng':            float(loc['lng']),
                'distance':       round(dist_km, 2),
                'type':           ptype,
                'place_id':       place.get('place_id', ''),
                'phone':          '',
                'source':         'google',
                'priority_rank':  0,
                'popularity':     float(place.get('user_ratings_total', 0) or 0),
                'display_rating': float(place.get('rating', 0) or 0),
            })
        if skipped:
            print(f"[Google Places] Filtered out {skipped} irrelevant/out-of-radius result(s) for '{keyword}'")
        return results
    except Exception as e:
        print(f"[Google Places] Exception: {e}")
        return []


def google_geocode(address):
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
# DOMAIN DATA
# ══════════════════════════════════════════════════════════════════════════

MULTISPECIALTY_WORDS = [
    'safal','hope','medistar','sterling','apollo','shalby','zydus','kiran',
    'vedanta','narayana','manipal','kokilaben','fortis','max','medanta',
    'multispecialt','multi specialt','super specialt','general hospital',
    'civil hospital','district hospital','government hospital','govt hospital',
    'medical college','medical center','medical centre','comprehensive',
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
    'general':       {'label': '🏥 General Medicine',         'icon': '🏥', 'keywords': ['general medicine','family medicine','polyclinic','nursing home']},
}

BODY_PART_SPECIALTIES = {
    'head':       ['neurology', 'ent', 'ophthalmology', 'psychiatry'],
    'brain':      ['neurology', 'psychiatry'],
    'eyes':       ['ophthalmology'],
    'ear':        ['ent'],
    'nose':       ['ent'],
    'throat':     ['ent'],
    'mouth':      ['ent'],
    'face':       ['ent', 'dermatology'],
    'neck':       ['ent', 'neurology', 'orthopedic'],
    'shoulders':  ['orthopedic'],
    'shoulder':   ['orthopedic'],
    'chest':      ['cardiology', 'pulmonology'],
    'heart':      ['cardiology'],
    'lungs':      ['pulmonology'],
    'stomach':    ['gastro'],
    'abdomen':    ['gastro', 'nephrology'],
    'liver':      ['gastro'],
    'kidney':     ['nephrology'],
    'arms':       ['orthopedic'],
    'arm':        ['orthopedic'],
    'wrist':      ['orthopedic'],
    'hand':       ['orthopedic'],
    'elbow':      ['orthopedic'],
    'back':       ['orthopedic', 'neurology'],
    'spine':      ['orthopedic', 'neurology'],
    'lower_back': ['orthopedic', 'neurology'],
    'hips':       ['orthopedic'],
    'hip':        ['orthopedic'],
    'knees':      ['orthopedic'],
    'knee':       ['orthopedic'],
    'legs':       ['orthopedic'],
    'leg':        ['orthopedic'],
    'ankle':      ['orthopedic'],
    'feet':       ['orthopedic'],
    'foot':       ['orthopedic'],
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
    'urinary':       ['nephrology'],
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
    'thyroid':       ['ent', 'endocrinology'],
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
}

SPECIALTY_SEARCH_KEYWORDS = {
    'orthopedic':    ['orthopedic hospital', 'bone hospital', 'ortho clinic', 'joint clinic'],
    'neurology':     ['neurology hospital', 'neuro clinic', 'brain hospital'],
    'ent':           ['ent hospital', 'ear nose throat', 'ent clinic'],
    'ophthalmology': ['eye hospital', 'eye clinic', 'netralaya', 'vision centre'],
    'cardiology':    ['heart hospital', 'cardiac hospital', 'cardiology clinic'],
    'pulmonology':   ['chest hospital', 'lung clinic', 'pulmonology', 'respiratory clinic'],
    'gastro':        ['gastroenterology', 'gastro clinic', 'digestive clinic'],
    'oncology':      ['cancer hospital', 'oncology centre', 'cancer clinic'],
    'nephrology':    ['kidney hospital', 'nephrology clinic', 'dialysis centre'],
    'endocrinology': ['diabetes clinic', 'endocrinology', 'diabetology'],
    'dermatology':   ['skin clinic', 'dermatology clinic', 'skin hospital'],
    'psychiatry':    ['psychiatry', 'mental health clinic', 'psychology clinic'],
    'general':       ['hospital', 'clinic', 'medical centre', 'nursing home'],
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
    matched = [(s, spec_score(h['name'], h.get('address',''), s)) for s in needed]
    return [m[0] for m in sorted(matched, key=lambda x: -x[1]) if m[1] > 0]

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
    c = next((x for x in contacts if x.get('id') == cid), None)
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
        limit        = int(data.get('limit', 30))
        custom_query = data.get('custom_query','').lower().strip()

        if not user_lat or not user_lng:
            return jsonify({'error': 'Missing location'}), 400

        # Determine specialties needed
        if custom_query:
            custom_diseases = db_get_diseases()
            m = next((d for d in custom_diseases if custom_query in d['name'].lower()), None)
            if m:
                needed = [s.strip() for s in m['specialties'].split(',') if s.strip()]
                label  = m['name']
            else:
                best   = next((k for k in ILLNESS_SPECIALTIES if custom_query in k.replace('_',' ')), None)
                needed = ILLNESS_SPECIALTIES.get(best, ['general'])
                label  = custom_query.title()
        elif illness_type and illness_type in ILLNESS_SPECIALTIES:
            needed = ILLNESS_SPECIALTIES[illness_type]
            label  = COMMON_ILLNESSES.get(illness_type, {}).get('label', illness_type.title())
        elif body_part and body_part in BODY_PART_SPECIALTIES:
            needed = BODY_PART_SPECIALTIES[body_part]
            label  = body_part.title()
        else:
            needed = ['general']
            label  = 'General'

        raw = []

        # 1. Admin-added hospitals from DB
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

        # 2. Google Maps Places (Text Search) — hospitals AND clinics
        search_keywords = set()
        for sid in needed:
            for kw in SPECIALTY_SEARCH_KEYWORDS.get(sid, ['hospital']):
                search_keywords.add(kw)
        search_keywords.update(['hospital', 'clinic'])

        for keyword in search_keywords:
            places = google_nearby_places(user_lat, user_lng, radius=radius, keyword=keyword)
            raw.extend(places)

        # 3. Deduplicate
        seen, deduped = set(), []
        for h in sorted(raw, key=lambda x: (-x.get('priority_rank', 0), x['distance'])):
            uid = h['name'].strip().lower()[:35]
            if uid not in seen:
                seen.add(uid)
                deduped.append(h)

        # 4. Sort — DB entries first, then multispecialty hospitals,
        #    then clinics (so clinics aren't buried behind every hospital), then distance
        def sort_key(h):
            is_multi  = 1 if is_multispecialty(h['name'], h.get('address','')) else 0
            is_clinic = 1 if h.get('type') == 'Clinic' else 0
            return (-h.get('priority_rank', 0), -is_multi, -is_clinic, h['distance'])
        deduped.sort(key=sort_key)

        # 5. Classify
        spec_buckets = {s: [] for s in needed}
        multi_bucket, unmatched = [], []

        for h in deduped:
            matched = classify(h, needed)
            if matched:
                h['specialty_label'] = SPECIALTIES.get(matched[0],{}).get('label', matched[0])
                spec_buckets[matched[0]].append(h)
            elif is_multispecialty(h['name'], h.get('address','')):
                h['specialty_label'] = '⭐ Multispecialty'
                multi_bucket.append(h)
            else:
                h['specialty_label'] = '🏥 General'
                unmatched.append(h)

        # 6. Build groups
        groups = []
        for sid in needed:
            if spec_buckets.get(sid):
                sp = SPECIALTIES.get(sid, {})
                groups.append({'id': sid, 'label': sp.get('label', sid.title()),
                               'icon': sp.get('icon', '🏥'), 'hospitals': spec_buckets[sid]})
        if multi_bucket:
            groups.append({'id': 'multispecialty', 'label': '⭐ Multispecialty Hospitals',
                           'icon': '⭐', 'hospitals': multi_bucket})
        if unmatched and groups:
            groups.append({'id': 'nearby', 'label': '🏥 Other Hospitals & Clinics Nearby',
                           'icon': '🏥', 'hospitals': unmatched[:15]})
        if not groups and deduped:
            groups.append({'id': 'general', 'label': '🏥 Hospitals & Clinics near you',
                           'icon': '🏥', 'hospitals': deduped[:30]})

        trimmed = [({**g, 'hospitals': g['hospitals'][:limit]})
                   for g in groups if g['hospitals'][:limit]]

        return jsonify({'success': True, 'groups': trimmed,
                        'total': sum(len(g['hospitals']) for g in trimmed),
                        'search_label': label, 'radius_km': radius/1000, 'sort_by': 'distance'})

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
    combined = [{'key': k, 'label': v['label'], 'icon': v['icon'], 'source': 'builtin'}
                for k, v in COMMON_ILLNESSES.items()]
    for d in db_get_diseases():
        combined.append({'key': d['name'].lower().replace(' ','_'),
                         'label': d['name'], 'icon': d.get('icon','💊'), 'source': 'custom'})
    return jsonify(combined)


@app.route('/api/status')
def api_status():
    return jsonify({
        'mongo':                MONGO_OK,
        'google_maps_key_set':  bool(GOOGLE_MAPS_KEY),
    })


# ══════════════════════════════════════════════════════════════════════════
# FIX 3: app.run() only for local dev — Vercel uses api/index.py instead
# ══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print("=" * 55)
    print("🏥  NearCares  (MongoDB + Google Maps)")
    print(f"🗄️   MongoDB: {'✅ Connected' if MONGO_OK else '⚠️  Fallback to JSON'}")
    print("🌐  http://localhost:5000")
    print("🔐  http://localhost:5000/admin  (admin / admin123)")
    print("=" * 55)
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=False)
