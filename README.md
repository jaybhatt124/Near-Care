# 🏥 NearCares

**Find the right specialist hospital near you — instantly.**

NearCares is a GPS-powered web app that helps users find nearby specialist hospitals by clicking on a body map or selecting a condition. Built with Flask and powered by live location data from Google Maps (with Mappls as fallback).

---

## ✨ Features

- 🫀 **Interactive Body Map** — Click any body part to find relevant specialist hospitals
- 💊 **Disease Search** — Select from 20+ common conditions or search by name
- 📍 **GPS Location** — Auto-detects your location with high accuracy; manual entry fallback
- 🏥 **Live Hospital Search** — Fetches real hospitals near you via Google Maps Places API (Mappls fallback)
- ⭐ **Smart Grouping** — Results grouped by specialty (Cardiology, Orthopedic, Neurology, etc.)
- 🔐 **Admin Panel** — Manage hospitals, view contact messages, add custom diseases
- ✉️ **Reply to Users** — Admin can reply to contact messages directly via Gmail
- 💾 **Dual Storage** — MySQL database with JSON file fallback (works without MySQL)

---

## 🖥️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3, Flask |
| Database | MongoDB (JSON file fallback) |
| Location API | Google Maps (primary), Mappls (fallback) |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Auth | Flask Sessions |
| Config | python-dotenv |

---

## 🚀 Quick Start

### 1. Clone / Download the project

```bash
# If using Git
git clone <your-repo-url>
cd shn
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

```bash
# Copy the example file
cp .env.example .env   # Mac/Linux
copy .env.example .env  # Windows
```

Open `.env` and fill in your values:

```env
SECRET_KEY=your-random-secret-key
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=smart_health_navigator
ADMIN_USER=admin
ADMIN_PASS=your_admin_password
GOOGLE_MAPS_KEY=your_google_maps_api_key
MAPPLS_API_KEY=your_mappls_api_key
```

> ⚠️ **Never share or commit your `.env` file!** It is listed in `.gitignore`.

### 4. Set up MySQL database

Open **MySQL Workbench** (or any MySQL client) and run:

```sql
source db_setup.sql
```

This creates the database, tables, and loads sample hospitals in Ahmedabad.

> 💡 If MySQL is not available, the app automatically falls back to JSON file storage in the `data/` folder — no setup needed.

### 5. Run the app

```bash
python app.py
```

### 6. Open in browser

| URL | Description |
|-----|-------------|
| `http://localhost:5000` | Main website |
| `http://localhost:5000/admin` | Admin panel |

---

## 🔑 Getting API Keys

**Google Maps (primary)**
1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Create a project and enable **Places API** + **Geocoding API**
3. Create an API key and paste it into `.env` as `GOOGLE_MAPS_KEY`

**Mappls / MapmyIndia (fallback)**
1. Go to [https://www.mappls.com/api/](https://www.mappls.com/api/)
2. Sign up and create a REST API key
3. Copy the key and paste it into `.env` as `MAPPLS_API_KEY`

---

## 📁 Project Structure

```
shn/
├── app.py                  # Main Flask application
├── .env                    # Your secrets (never commit!)
├── .env.example            # Template for .env
├── .gitignore              # Protects .env from Git
├── requirements.txt        # Python dependencies
├── db_setup.sql            # MySQL schema + sample data
├── README.md               # This file
│
├── templates/
│   ├── base.html           # Shared layout (header, footer)
│   ├── index.html          # Home page with body map
│   ├── hospitals.html      # Hospital search results page
│   ├── contact.html        # Contact form
│   ├── about.html          # About page
│   ├── tips.html           # Health tips page
│   └── admin/
│       ├── login.html      # Admin login
│       └── dashboard.html  # Admin dashboard
│
├── static/
│   ├── css/
│   │   └── style.css       # All styles
│   └── js/
│       ├── home.js         # Body map + home page logic
│       ├── hospitals.js    # Hospital search + location
│       └── contact.js      # Contact form submission
│
└── data/                   # Auto-created JSON fallback storage
    ├── contacts.json
    ├── hospitals.json
    └── diseases.json
```

---

## 🔐 Admin Panel

Access the admin panel at `/admin` (link hidden from public nav).

| Feature | Description |
|---------|-------------|
| 🏥 Hospitals | Add / delete verified hospitals |
| ✉️ Messages | View contact form submissions |
| ✉️ Reply | Opens Gmail compose with user's email pre-filled |
| 💊 Diseases | Add custom diseases beyond the built-in list |

Default credentials (change in `.env`):
- **Username:** `admin`
- **Password:** `admin123`

---

## 🌐 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/search-hospitals` | POST | Search hospitals by location + condition |
| `/api/geocode` | POST | Convert address to coordinates |
| `/api/reverse-geocode` | POST | Convert coordinates to address |
| `/api/contact` | POST | Submit contact form |
| `/api/diseases` | GET | Get all diseases (built-in + custom) |
| `/api/contact/check` | GET | Debug: check contact storage status |

---

## 🛡️ Security Notes

- All secrets stored in `.env` — never hardcoded
- Admin panel protected by session-based authentication
- Admin link hidden from public navigation
- `.env` excluded from Git via `.gitignore`
- Change default `ADMIN_PASS` before deploying

---

## 📄 License

© 2026 NearCares. All rights reserved.

> This app is for educational and navigational purposes only.  
> Always consult a qualified medical professional for diagnosis and treatment.
