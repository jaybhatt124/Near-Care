"""
NearCares
Full-stack Flask app with:
  - MySQL database (hospitals + contact messages)
  - Admin panel (add/delete hospitals, view contact messages)
  - Live hospital search via Google Maps (primary), Mappls (fallback)
  - Custom disease search
  - Light theme across all pages
  - Footer: © 2026 NearCares. All rights reserved.
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
import requests, math, os
from datetime import datetime
from functools import wraps

# ─── Load .env file automatically ────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ .env loaded")
except ImportError:
    print("⚠️  python-dotenv not installed — install with: pip install python-dotenv")

# ─── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# ─── Maps / Places API keys ──────────────────────────────────────────────────
# Priority: Google Maps (primary) → Mappls / MapmyIndia (fallback)
GOOGLE_MAPS_KEY = os.environ.get('GOOGLE_MAPS_KEY', '')
MAPPLS_API_KEY  = os.environ.get('MAPPLS_API_KEY', '')

if not GOOGLE_MAPS_KEY:
    print("⚠️  GOOGLE_MAPS_KEY not set in .env — will try Mappls fallback")
if not MAPPLS_API_KEY:
    print("⚠️  MAPPLS_API_KEY not set in .env — no fallback available")
if not GOOGLE_MAPS_KEY and not MAPPLS_API_KEY:
    print("⚠️  No maps API key configured — hospital search will not work")

# ─── MongoDB Atlas ───────────────────────────────────────────────────────────
try:
    from pymongo import MongoClient
    from bson import ObjectId
    MONGO_AVAILABLE = True
except ImportError:
    MONGO_AVAILABLE = False
    print("⚠️  pymongo not installed — run: pip install 'pymongo[srv]'")

_mongo_client = None
_mongo_db     = None
_db_ok        = False

_APP_DIR = os.path.abspath(os.path.dirname(__file__))
import json, tempfile

# On Vercel / AWS Lambda-style serverless, everything except /tmp is read-only.
_IS_SERVERLESS = bool(os.environ.get('VERCEL') or os.environ.get('VERCEL_ENV')
                      or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'))
DATA_DIR = os.path.join(tempfile.gettempdir(), 'nearcares_data') if _IS_SERVERLESS \
    else os.path.join(_APP_DIR, 'data')

def _ensure_data_dir():
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception as e:
        print(f"⚠️  Could not create data dir ({DATA_DIR}): {e}")

def _load_json(path):
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️  JSON load error: {e}")
    return []

def _save_json(path, data):
    try:
        _ensure_data_dir()
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"⚠️  JSON save error: {e}")

CONTACTS_FILE  = os.path.join(DATA_DIR, 'contacts.json')
HOSPITALS_FILE = os.path.join(DATA_DIR, 'hospitals.json')
DISEASES_FILE  = os.path.join(DATA_DIR, 'diseases.json')
_ensure_data_dir()
if _IS_SERVERLESS:
    print(f"⚠️  Running on serverless — JSON fallback data in {DATA_DIR} will NOT persist between invocations. Fix MONGO_URI to use MongoDB instead.")



def get_mongo_db():
    global _mongo_client, _mongo_db, _db_ok
    if _mongo_db is not None:
        return _mongo_db
    if not MONGO_AVAILABLE:
        return None
    uri = os.environ.get('MONGO_URI', '')
    if not uri:
        print("⚠️  MONGO_URI not set in .env — using JSON file fallback")
        return None
    try:
        _mongo_client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        _mongo_client.admin.command('ping')
        _mongo_db = _mongo_client['nearcares']
        _db_ok = True
        print("✅  MongoDB Atlas connected")
        return _mongo_db
    except Exception as e:
        print(f"⚠️  MongoDB connection failed: {e} — using JSON fallback")
        _db_ok = False
        return None


def _doc_to_dict(doc):
    """Convert MongoDB document to plain dict with string id."""
    if doc is None:
        return None
    d = dict(doc)
    if '_id' in d:
        d['id'] = str(d.pop('_id'))
    return d


def init_db():
    db = get_mongo_db()
    if db is not None:
        # Ensure indexes
        try:
            db.hospitals.create_index('added_at')
            db.contact_messages.create_index('received_at')
            print("✅  MongoDB indexes ready")
        except Exception as e:
            print(f"⚠️  Index creation: {e}")
    else:
        print("⚠️  Using JSON file storage (set MONGO_URI in .env for MongoDB)")


# ── Hospitals ────────────────────────────────────────────────────────────────
def db_add_hospital(name, address, city, state, lat, lng, specialties, phone=''):
    db = get_mongo_db()
    doc = {
        'name': name, 'address': address, 'city': city, 'state': state,
        'lat': lat, 'lng': lng, 'specialties': specialties, 'phone': phone,
        'added_at': datetime.now().strftime('%Y-%m-%d %H:%M')
    }
    if db is not None:
        try:
            db.hospitals.insert_one(doc)
            return
        except Exception as e:
            print(f"[DB] Hospital insert error: {e}")
    hospitals = _load_json(HOSPITALS_FILE)
    doc['id'] = max((h.get('id', 0) for h in hospitals), default=0) + 1
    hospitals.append(doc)
    _save_json(HOSPITALS_FILE, hospitals)


def db_get_hospitals():
    db = get_mongo_db()
    if db is not None:
        try:
            docs = list(db.hospitals.find().sort('added_at', -1))
            return [_doc_to_dict(d) for d in docs]
        except Exception as e:
            print(f"[DB] Get hospitals error: {e}")
    return list(reversed(_load_json(HOSPITALS_FILE)))


def db_delete_hospital(hid):
    db = get_mongo_db()
    if db is not None:
        try:
            db.hospitals.delete_one({'_id': ObjectId(hid)})
            return
        except Exception:
            # Try numeric id fallback
            try:
                db.hospitals.delete_one({'id': int(hid)})
                return
            except Exception as e:
                print(f"[DB] Delete hospital error: {e}")
    hospitals = _load_json(HOSPITALS_FILE)
    hospitals = [h for h in hospitals if str(h.get('id')) != str(hid)]
    _save_json(HOSPITALS_FILE, hospitals)


# ── Contact messages ─────────────────────────────────────────────────────────
def db_save_contact(name, email, message):
    """Save contact message to MongoDB or JSON fallback."""
    doc = {
        'name': name, 'email': email, 'message': message,
        'received_at': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'is_read': 0
    }
    db = get_mongo_db()
    if db is not None:
        try:
            db.contact_messages.insert_one(doc)
            print(f"[CONTACT] Saved to MongoDB: {name}")
            return True
        except Exception as e:
            print(f"[CONTACT] MongoDB insert failed: {e}")
    # JSON fallback
    contacts = _load_json(CONTACTS_FILE)
    doc['id'] = max((c.get('id', 0) for c in contacts), default=0) + 1
    contacts.append(doc)
    _save_json(CONTACTS_FILE, contacts)
    print(f"[CONTACT] Saved to JSON: {name}")
    return True


def db_get_contacts():
    db = get_mongo_db()
    if db is not None:
        try:
            docs = list(db.contact_messages.find().sort('received_at', -1))
            return [_doc_to_dict(d) for d in docs]
        except Exception as e:
            print(f"[CONTACT] Get contacts error: {e}")
    return list(reversed(_load_json(CONTACTS_FILE)))


def db_mark_read(cid):
    db = get_mongo_db()
    if db is not None:
        try:
            db.contact_messages.update_one({'_id': ObjectId(cid)}, {'$set': {'is_read': 1}})
            return
        except Exception:
            try:
                db.contact_messages.update_one({'id': int(cid)}, {'$set': {'is_read': 1}})
                return
            except Exception as e:
                print(f"[DB] Mark read error: {e}")
    contacts = _load_json(CONTACTS_FILE)
    for c in contacts:
        if str(c.get('id')) == str(cid):
            c['is_read'] = 1
    _save_json(CONTACTS_FILE, contacts)


def db_delete_contact(cid):
    db = get_mongo_db()
    if db is not None:
        try:
            db.contact_messages.delete_one({'_id': ObjectId(cid)})
            return
        except Exception:
            try:
                db.contact_messages.delete_one({'id': int(cid)})
                return
            except Exception as e:
                print(f"[DB] Delete contact error: {e}")
    contacts = _load_json(CONTACTS_FILE)
    contacts = [c for c in contacts if str(c.get('id')) != str(cid)]
    _save_json(CONTACTS_FILE, contacts)


# ── Custom diseases ──────────────────────────────────────────────────────────
def db_add_disease(name, specialties, icon='💊'):
    db = get_mongo_db()
    doc = {'name': name, 'specialties': specialties, 'icon': icon}
    if db is not None:
        try:
            db.custom_diseases.insert_one(doc)
            return
        except Exception as e:
            print(f"[DB] Add disease error: {e}")
    diseases = _load_json(DISEASES_FILE)
    doc['id'] = max((d.get('id', 0) for d in diseases), default=0) + 1
    diseases.append(doc)
    _save_json(DISEASES_FILE, diseases)


def db_get_diseases():
    db = get_mongo_db()
    if db is not None:
        try:
            docs = list(db.custom_diseases.find().sort('_id', -1))
            return [_doc_to_dict(d) for d in docs]
        except Exception as e:
            print(f"[DB] Get diseases error: {e}")
    return list(reversed(_load_json(DISEASES_FILE)))


def db_delete_disease(did):
    db = get_mongo_db()
    if db is not None:
        try:
            db.custom_diseases.delete_one({'_id': ObjectId(did)})
            return
        except Exception:
            try:
                db.custom_diseases.delete_one({'id': int(did)})
                return
            except Exception as e:
                print(f"[DB] Delete disease error: {e}")
    diseases = _load_json(DISEASES_FILE)
    diseases = [d for d in diseases if str(d.get('id')) != str(did)]
    _save_json(DISEASES_FILE, diseases)


# ═══════════════════════════════════════════════════════════════════════════
# DOMAIN DATA
# ═══════════════════════════════════════════════════════════════════════════

MULTISPECIALTY_WORDS = [
    'safal','hope','medistar','sterling','apollo','shalby','zydus','kiran','nirma',
    'vedanta','narayana','manipal','kokilaben','fortis','max','medanta','medicity',
    'multispecialt','multi specialt','super specialt','superspecialt','multi-specialt',
    'general hospital','civil hospital','district hospital','government hospital',
    'govt hospital','municipal hospital','medical college','medical center',
    'medical centre','institute of medical','hospital and research',
    'hospital & research','comprehensive',
]

SPECIALTIES = {
    'orthopedic':    {'label': '🦴 Orthopedic & Bone', 'icon': '🦴',
        'keywords': ['ortho','orthopedic','orthopaedic','bone','joint','fracture','spine','spinal','disc','lumbar','cervical','arthroplasty','arthritis','ligament','tendon','musculo','skeletal','trauma center','sports medicine','sports injury','hand surgery','knee surgery','shoulder surgery','hip replacement']},
    'physio':        {'label': '💪 Physiotherapy', 'icon': '💪',
        'keywords': ['physio','physiotherapy','physiotherapist','rehab','rehabilitation','chiro','chiropractic','occupational therapy']},
    'neurology':     {'label': '🧠 Neurology & Brain', 'icon': '🧠',
        'keywords': ['neuro','neurology','neurological','neurologist','neurosurg','brain','stroke','epilepsy','parkinson','alzheimer']},
    'ent':           {'label': '👂 ENT', 'icon': '👂',
        'keywords': ['ent','ear','nose','throat','sinus','tonsil','otolaryngology','audiolog','hearing','rhinology','laryngology','thyroid']},
    'ophthalmology': {'label': '👁️ Eye Hospital', 'icon': '👁️',
        'keywords': ['eye','ophthalm','vision','retina','cataract','lasik','glaucoma','netralaya','drishti','ocular']},
    'cardiology':    {'label': '❤️ Cardiology & Heart', 'icon': '❤️',
        'keywords': ['cardio','cardiac','cardiology','cardiologist','heart','cardiovascular','angioplasty','bypass','pacemaker','coronary']},
    'pulmonology':   {'label': '🫁 Pulmonology & Chest', 'icon': '🫁',
        'keywords': ['pulmo','pulmonary','pulmonologist','lung','lungs','chest hospital','respiratory','asthma clinic','tb hospital','tuberculosis','broncho','thoracic']},
    'gastro':        {'label': '🫃 Gastroenterology', 'icon': '🫃',
        'keywords': ['gastro','gastroenterology','gastroenterologist','digestive','intestine','bowel','colon','colonoscopy','endoscopy','abdominal','gastric']},
    'liver':         {'label': '🫀 Liver & Hepatology', 'icon': '🫀',
        'keywords': ['liver','hepato','hepatology','hepatologist','pancrea','bile','jaundice','cirrhosis','liver transplant']},
    'oncology':      {'label': '🎗️ Cancer & Oncology', 'icon': '🎗️',
        'keywords': ['onco','oncology','oncologist','cancer','tumour','tumor','radiotherapy','chemotherapy','radiation','haematology']},
    'nephrology':    {'label': '🫘 Kidney & Nephrology', 'icon': '🫘',
        'keywords': ['nephro','nephrology','nephrologist','kidney','renal','dialysis','urology','urologist','urinary']},
    'endocrinology': {'label': '💊 Diabetes & Endocrinology', 'icon': '💊',
        'keywords': ['endocrin','endocrinology','diabetes','diabetology','diabetologist','hormone','insulin','bariatric']},
    'dermatology':   {'label': '🧴 Skin & Dermatology', 'icon': '🧴',
        'keywords': ['derma','dermatology','dermatologist','skin clinic','cosmet','cosmetic','hair clinic','trichology']},
    'psychiatry':    {'label': '🧘 Psychiatry & Mental Health', 'icon': '🧘',
        'keywords': ['psychiatr','psychology','mental health','mental hospital','de-addiction','addiction','counselling','counseling']},
    'general':       {'label': '🏥 General Medicine', 'icon': '🏥',
        'keywords': ['general medicine','general physician','family medicine','primary care','polyclinic','nursing home']},
}

BODY_PART_SPECIALTIES = {
    'head': ['neurology','ent','ophthalmology','psychiatry'],
    'neck': ['ent','neurology','orthopedic'],
    'chest': ['cardiology','pulmonology'],
    'stomach': ['gastro','liver'],
    'shoulders': ['orthopedic','physio'],
    'arms': ['orthopedic','physio'],
    'back': ['orthopedic','neurology','physio'],
    'knees': ['orthopedic','physio'],
    'legs': ['orthopedic','physio'],
    'feet': ['orthopedic','physio'],
}

ILLNESS_SPECIALTIES = {
    'fever':         ['general'],
    'cough':         ['pulmonology','ent'],
    'cold':          ['ent','general'],
    'diarrhea':      ['gastro'],
    'cancer':        ['oncology'],
    'heart_disease': ['cardiology'],
    'bp':            ['cardiology','general'],
    'diabetes':      ['endocrinology'],
    'asthma':        ['pulmonology'],
    'kidney':        ['nephrology'],
    'skin':          ['dermatology'],
    'eye':           ['ophthalmology'],
    'headache':      ['neurology','general'],
    'migraine':      ['neurology'],
    'liver':         ['liver','gastro'],
    'depression':    ['psychiatry'],
    'anxiety':       ['psychiatry'],
    'thyroid':       ['ent','endocrinology'],
    'arthritis':     ['orthopedic','physio'],
    'back_pain':     ['orthopedic','physio','neurology'],
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

# ═══════════════════════════════════════════════════════════════════════════
# UTILS
# ═══════════════════════════════════════════════════════════════════════════

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlng/2)**2)
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a)), 2)


def _google_nearby_hospitals(lat, lng, radius):
    """Google Places Nearby Search — primary source."""
    if not GOOGLE_MAPS_KEY:
        return None
    try:
        resp = requests.get('https://maps.googleapis.com/maps/api/place/nearbysearch/json', params={
            'location': f'{lat},{lng}', 'radius': min(radius, 50000),
            'type': 'hospital', 'keyword': 'hospital clinic',
            'key': GOOGLE_MAPS_KEY}, timeout=15)
        data = resp.json()
        if data.get('status') not in ('OK', 'ZERO_RESULTS'):
            print(f"⚠️  Google Places error: {data.get('status')} — {data.get('error_message','')}")
            return None
        out = []
        for place in data.get('results', []):
            loc = place.get('geometry', {}).get('location', {})
            if 'lat' not in loc or 'lng' not in loc:
                continue
            types = place.get('types', [])
            ptype = 'Hospital' if 'hospital' in types else 'Clinic' if 'doctor' in types else 'Healthcare'
            out.append({'name': place.get('name', 'Healthcare Facility'),
                'address': place.get('vicinity', ''),
                'lat': loc['lat'], 'lng': loc['lng'],
                'distance': haversine(lat, lng, loc['lat'], loc['lng']),
                'type': ptype, 'place_id': place.get('place_id', ''),
                'popularity': float(place.get('user_ratings_total', 0) or 0),
                'display_rating': float(place.get('rating', 0) or 0),
                'priority_rank': 0, 'source': 'live'})
        return out
    except Exception as e:
        print(f"⚠️  Google Places request failed: {e}")
        return None


def _mappls_nearby_hospitals(lat, lng, radius):
    """Mappls (MapmyIndia) Nearby Places — fallback source."""
    if not MAPPLS_API_KEY:
        return None
    try:
        resp = requests.get(f'https://apis.mappls.com/advancedmaps/v1/{MAPPLS_API_KEY}/near_me/hospital', params={
            'refLocation': f'{lat},{lng}', 'radius': radius}, timeout=15)
        data = resp.json()
        out = []
        for place in data.get('suggestedLocations', []):
            plat, plng = place.get('latitude'), place.get('longitude')
            if plat is None or plng is None:
                continue
            plat, plng = float(plat), float(plng)
            out.append({'name': place.get('placeName', 'Healthcare Facility'),
                'address': place.get('placeAddress', ''),
                'lat': plat, 'lng': plng,
                'distance': haversine(lat, lng, plat, plng),
                'type': 'Hospital', 'place_id': place.get('eLoc', ''),
                'popularity': 0, 'display_rating': 0,
                'priority_rank': 0, 'source': 'live'})
        return out
    except Exception as e:
        print(f"⚠️  Mappls request failed: {e}")
        return None


def search_live_hospitals(lat, lng, radius):
    """Try Google Maps first; fall back to Mappls if unavailable/fails."""
    result = _google_nearby_hospitals(lat, lng, radius)
    if result is not None:
        return result
    result = _mappls_nearby_hospitals(lat, lng, radius)
    if result is not None:
        return result
    return []


def geocode_address(address):
    """Google Geocoding API first; Mappls geo_code as fallback."""
    if GOOGLE_MAPS_KEY:
        try:
            resp = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params={
                'address': address, 'components': 'country:IN', 'key': GOOGLE_MAPS_KEY}, timeout=10)
            data = resp.json()
            if data.get('status') == 'OK' and data.get('results'):
                r = data['results'][0]
                loc = r['geometry']['location']
                return {'lat': loc['lat'], 'lng': loc['lng'], 'formatted_address': r.get('formatted_address', address)}
        except Exception as e:
            print(f"⚠️  Google geocode failed: {e}")
    if MAPPLS_API_KEY:
        try:
            resp = requests.get(f'https://apis.mappls.com/advancedmaps/v1/{MAPPLS_API_KEY}/geo_code',
                params={'addr': address}, timeout=10)
            data = resp.json()
            results = data.get('copResults') or data.get('results') or []
            if results:
                r = results[0]
                return {'lat': float(r.get('latitude')), 'lng': float(r.get('longitude')),
                    'formatted_address': r.get('formattedAddress', address)}
        except Exception as e:
            print(f"⚠️  Mappls geocode failed: {e}")
    return None


def reverse_geocode_latlng(lat, lng):
    """Google reverse geocoding first; Mappls rev_geocode as fallback."""
    if GOOGLE_MAPS_KEY:
        try:
            resp = requests.get('https://maps.googleapis.com/maps/api/geocode/json', params={
                'latlng': f'{lat},{lng}', 'key': GOOGLE_MAPS_KEY}, timeout=10)
            data = resp.json()
            if data.get('status') == 'OK' and data.get('results'):
                r = data['results'][0]
                city = state = ''
                for comp in r.get('address_components', []):
                    if 'locality' in comp.get('types', []):
                        city = comp.get('long_name', '')
                    if 'administrative_area_level_1' in comp.get('types', []):
                        state = comp.get('long_name', '')
                return {'formatted_address': r.get('formatted_address', f'{lat},{lng}'),
                    'city': city, 'state': state, 'country': 'India'}
        except Exception as e:
            print(f"⚠️  Google reverse geocode failed: {e}")
    if MAPPLS_API_KEY:
        try:
            resp = requests.get(f'https://apis.mappls.com/advancedmaps/v1/{MAPPLS_API_KEY}/rev_geocode',
                params={'lat': lat, 'lng': lng}, timeout=10)
            data = resp.json()
            results = data.get('results', [])
            if results:
                r = results[0]
                return {'formatted_address': r.get('formatted_address') or f'{lat},{lng}',
                    'city': r.get('city', ''), 'state': r.get('state', ''), 'country': r.get('country', 'India')}
        except Exception as e:
            print(f"⚠️  Mappls reverse geocode failed: {e}")
    return None


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


# ═══════════════════════════════════════════════════════════════════════════
# PUBLIC ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    all_illnesses = dict(COMMON_ILLNESSES)
    for d in db_get_diseases():
        key = d['name'].lower().replace(' ', '_')
        all_illnesses[key] = {'icon': d.get('icon','💊'), 'label': d['name']}
    return render_template('index.html', illnesses=all_illnesses, google_maps_key=GOOGLE_MAPS_KEY)


@app.route('/results')
def results():
    """Hospital results page — shown after user selects disease/body part."""
    return render_template('results.html', google_maps_key=GOOGLE_MAPS_KEY)


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/tips')
def tips():
    return render_template('tips.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


# ═══════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route('/admin/login', methods=['GET', 'POST'])
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
        hospitals=hospitals_list,
        contacts=contacts_list,
        unread_count=unread_count,
        custom_diseases=custom_diseases,
        db_ok=_db_ok,
        all_specialties=list(SPECIALTIES.keys()))


@app.route('/admin/hospitals/add', methods=['POST'])
@admin_required
def admin_add_hospital():
    name  = request.form.get('name','').strip()
    if not name:
        flash('Name is required', 'error')
        return redirect(url_for('admin_dashboard'))
    try:
        lat = float(request.form.get('lat') or 0)
        lng = float(request.form.get('lng') or 0)
    except ValueError:
        lat = lng = 0.0
    db_add_hospital(
        name        = name,
        address     = request.form.get('address','').strip(),
        city        = request.form.get('city','').strip(),
        state       = request.form.get('state','').strip(),
        lat         = lat,
        lng         = lng,
        specialties = request.form.get('specialties','').strip(),
        phone       = request.form.get('phone','').strip(),
    )
    flash(f'✅ Hospital "{name}" added!', 'success')
    return redirect(url_for('admin_dashboard') + '#hospitals')


@app.route('/admin/hospitals/delete/<int:hid>', methods=['POST'])
@admin_required
def admin_delete_hospital(hid):
    db_delete_hospital(hid)
    flash('Hospital deleted', 'success')
    return redirect(url_for('admin_dashboard') + '#hospitals')


@app.route('/admin/contacts/read/<int:cid>', methods=['POST'])
@admin_required
def admin_mark_read(cid):
    db_mark_read(cid)
    return redirect(url_for('admin_dashboard') + '#contacts')


@app.route('/admin/contacts/delete/<int:cid>', methods=['POST'])
@admin_required
def admin_delete_contact(cid):
    db_delete_contact(cid)
    flash('Message deleted', 'success')
    return redirect(url_for('admin_dashboard') + '#contacts')


@app.route('/admin/contacts/reply/<int:cid>')
@admin_required
def admin_reply(cid):
    """Return JSON with the pre-built mailto URL — JS opens it client-side."""
    import urllib.parse
    contacts = db_get_contacts()
    c = next((x for x in contacts if x.get('id') == cid), None)
    if not c:
        return jsonify({'error': 'Contact not found'}), 404

    to      = str(c.get('email', '')).strip()
    name    = str(c.get('name',  '')).strip()
    orig    = str(c.get('message', ''))
    subject = 'Re: Your message to NearCares'
    body    = (
        f"Dear {name},\n\n"
        f"Thank you for reaching out to NearCares.\n\n"
        f"--- Your original message ---\n"
        f"{orig}\n\n"
        f"Best regards,\nNearCares Team"
    )
    mailto = (
        f"mailto:{to}"
        f"?subject={urllib.parse.quote(subject)}"
        f"&body={urllib.parse.quote(body)}"
    )
    return jsonify({
        'email':  to,
        'name':   name,
        'mailto': mailto
    })


@app.route('/admin/contacts/view/<int:cid>')
@admin_required
def admin_view_contact(cid):
    """Return contact data as JSON for the modal."""
    contacts = db_get_contacts()
    c = next((x for x in contacts if x.get('id') == cid), None)
    if not c:
        return jsonify({'error': 'Not found'}), 404
    # Mark as read
    db_mark_read(cid)
    return jsonify({
        'id':          c.get('id'),
        'name':        c.get('name', ''),
        'email':       c.get('email', ''),
        'message':     c.get('message', ''),
        'received_at': str(c.get('received_at', '')),
        'reply_url':   url_for('admin_reply', cid=cid)
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


@app.route('/admin/diseases/delete/<int:did>', methods=['POST'])
@admin_required
def admin_delete_disease(did):
    db_delete_disease(did)
    flash('Disease removed', 'success')
    return redirect(url_for('admin_dashboard') + '#diseases')


# ═══════════════════════════════════════════════════════════════════════════
# API ROUTES
# ═══════════════════════════════════════════════════════════════════════════

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

        # Determine specialties
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

        # DB hospitals
        for h in db_get_hospitals():
            if not (h.get('lat') and h.get('lng')):
                continue
            dist = haversine(user_lat, user_lng, float(h['lat']), float(h['lng']))
            if dist <= radius / 1000:
                raw.append({'name': h['name'],
                    'address': ' '.join(filter(None, [h.get('address'), h.get('city'), h.get('state')])),
                    'lat': float(h['lat']), 'lng': float(h['lng']),
                    'distance': dist, 'type': 'Hospital',
                    'place_id': f"db:{h['id']}", 'popularity': 10.0,
                    'display_rating': 4.8, 'priority_rank': 3, 'source': 'database',
                    'phone': h.get('phone','')})

        # Live places: Google Maps first, Mappls as fallback
        live_hospitals = search_live_hospitals(user_lat, user_lng, radius)
        raw.extend(live_hospitals)

        # Group
        multi_bucket = []
        spec_buckets = {s: [] for s in needed}
        unmatched    = []
        seen         = set()

        for h in sorted(raw, key=lambda x: (-x.get('priority_rank',0), -x.get('popularity',0), x['distance'])):
            uid = f"{h['name'].strip().lower()}|{h.get('address','').strip().lower()}"
            if uid in seen:
                continue
            seen.add(uid)
            if is_multispecialty(h['name'], h.get('address','')):
                h['specialty_label'] = '⭐ Multispecialty'
                multi_bucket.append(h)
            else:
                matched = classify(h, needed)
                if matched:
                    h['specialty_label'] = SPECIALTIES.get(matched[0],{}).get('label', matched[0])
                    spec_buckets[matched[0]].append(h)
                else:
                    h['specialty_label'] = '🏥 General'
                    unmatched.append(h)

        groups = []
        if multi_bucket:
            groups.append({'id':'multispecialty','label':'⭐ Multispecialty Hospitals','icon':'⭐','hospitals':multi_bucket})
        for sid in needed:
            if spec_buckets.get(sid):
                sp = SPECIALTIES.get(sid, {})
                groups.append({'id':sid,'label':sp.get('label',sid.title()),'icon':sp.get('icon','🏥'),'hospitals':spec_buckets[sid]})
        if not groups and unmatched:
            groups.append({'id':'general','label':'🏥 Hospitals Nearby','icon':'🏥','hospitals':unmatched[:15]})

        remaining = limit
        trimmed   = []
        for g in groups:
            if remaining <= 0: break
            hs = g['hospitals'][:remaining]
            if hs:
                trimmed.append({**g,'hospitals':hs})
                remaining -= len(hs)

        return jsonify({'success':True,'groups':trimmed,
            'total':sum(len(g['hospitals']) for g in trimmed),
            'search_label':label,'radius_km':radius/1000,
            'maps_key':GOOGLE_MAPS_KEY})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/geocode', methods=['POST'])
def api_geocode():
    try:
        address = request.get_json().get('address','')
        if not address:
            return jsonify({'error': 'Address required'}), 400
        result = geocode_address(address)
        if result:
            return jsonify({'success':True, **result})
        return jsonify({'error':'Address not found'}), 404
    except Exception as e:
        return jsonify({'error':str(e)}), 500


@app.route('/api/reverse-geocode', methods=['POST'])
def api_reverse_geocode():
    try:
        data = request.get_json() or {}
        lat  = float(data.get('lat', 0))
        lng  = float(data.get('lng', 0))
        if not lat or not lng:
            return jsonify({'error':'Lat/lng required'}), 400
        result = reverse_geocode_latlng(lat, lng)
        if result:
            return jsonify({'success':True, **result})
        return jsonify({'error':'Location not found'}), 404
    except Exception as e:
        return jsonify({'error':str(e)}), 500


@app.route('/api/contact', methods=['POST'])
def api_contact():
    try:
        data = request.get_json(force=True, silent=True) or {}
        name    = str(data.get('name','')).strip()
        email   = str(data.get('email','')).strip()
        message = str(data.get('message','')).strip()
        print(f"📩 Contact form: name={name!r}, email={email!r}, msg_len={len(message)}")
        if not name or not email or not message:
            return jsonify({'error': 'All fields required'}), 400
        db_save_contact(name, email, message)
        # Verify it was actually saved
        saved = db_get_contacts()
        print(f"✅ Contact saved. Total contacts now: {len(saved)}")
        return jsonify({'success': True, 'message': 'Thank you! We will get back to you soon.'})
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/api/contact/check')
def api_contact_check():
    """Debug: see how many contacts are stored and where"""
    contacts = db_get_contacts()
    result = {
        'count': len(contacts),
        'data_dir': DATA_DIR,
        'contacts_file': CONTACTS_FILE,
        'file_exists': os.path.exists(CONTACTS_FILE),
        'db_ok': _db_ok,
        'latest': contacts[:3] if contacts else []
    }
    # Also test direct MySQL query
    if _db_ok:
        conn = get_db()
        if conn:
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("SELECT COUNT(*) as cnt FROM contact_messages")
                row = cur.fetchone()
                cur.execute("SHOW TABLES LIKE 'contact_messages'")
                table_exists = cur.fetchone() is not None
                conn.close()
                result['mysql_count'] = row['cnt'] if row else 0
                result['mysql_table_exists'] = table_exists
            except Exception as e:
                result['mysql_error'] = str(e)
    return jsonify(result)


@app.route('/api/diseases')
def api_diseases():
    combined = [{'key':k,'label':v['label'],'icon':v['icon'],'source':'builtin'}
                for k,v in COMMON_ILLNESSES.items()]
    for d in db_get_diseases():
        combined.append({'key':d['name'].lower().replace(' ','_'),
                         'label':d['name'],'icon':d.get('icon','💊'),'source':'custom'})
    return jsonify(combined)


# ═══════════════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    init_db()
    print("="*55)
    print("🏥  NearCares")
    print("🌐  http://localhost:5000")
    print("🔐  http://localhost:5000/admin  (admin / admin123)")
    print("="*55)
    app.run(debug=True, host='0.0.0.0', port=5000)
else:
    init_db()