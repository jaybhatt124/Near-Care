-- ============================================================
-- Smart Health Navigator – MySQL Setup
-- Run this in MySQL Workbench
-- ============================================================

CREATE DATABASE IF NOT EXISTS smart_health_navigator
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE smart_health_navigator;

-- Hospitals table
CREATE TABLE IF NOT EXISTS hospitals (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    address     VARCHAR(500),
    city        VARCHAR(100),
    state       VARCHAR(100),
    lat         DOUBLE,
    lng         DOUBLE,
    specialties VARCHAR(500),
    phone       VARCHAR(50),
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Contact messages
CREATE TABLE IF NOT EXISTS contact_messages (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(100),
    email       VARCHAR(150),
    message     TEXT,
    received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_read     TINYINT DEFAULT 0
);

-- Custom diseases added by admin
CREATE TABLE IF NOT EXISTS custom_diseases (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(150),
    specialties VARCHAR(300),
    icon        VARCHAR(10) DEFAULT '💊',
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Sample hospitals (Ahmedabad) ──────────────────────────────
INSERT INTO hospitals (name, address, city, state, lat, lng, specialties, phone) VALUES
('Apollo Hospital International', 'Bhat, Gandhinagar-Ahmedabad Highway', 'Gandhinagar', 'Gujarat', 23.1427, 72.6396, 'cardiology, oncology, orthopedic, general', '+91 79 6670 1800'),
('Sterling Hospital', 'Gurukul Road, Memnagar', 'Ahmedabad', 'Gujarat', 23.0526, 72.5319, 'cardiology, oncology, neurology, general', '+91 79 4000 5000'),
('Shalby Hospital', 'Opp. Karnavati Club, SG Road', 'Ahmedabad', 'Gujarat', 23.0469, 72.5058, 'orthopedic, general, cardiology', '+91 79 4020 3000'),
('Zydus Hospital', 'Sola, Ahmedabad', 'Ahmedabad', 'Gujarat', 23.0785, 72.5244, 'cardiology, oncology, neurology, general', '+91 79 6619 0200'),
('Civil Hospital', 'Asarwa', 'Ahmedabad', 'Gujarat', 23.0524, 72.6104, 'general, orthopedic, neurology, cardiology', '+91 79 2268 1841'),
('VS Hospital', 'Ellisbridge', 'Ahmedabad', 'Gujarat', 23.0369, 72.5647, 'general, orthopedic, cardiology', '+91 79 2657 5861'),
('Safal Hospital', 'Navrangpura', 'Ahmedabad', 'Gujarat', 23.0398, 72.5614, 'orthopedic, physio, general', '+91 79 2646 3111'),
('Hope Hospital', 'Bopal-Ghuma Road, Bopal', 'Ahmedabad', 'Gujarat', 23.0324, 72.4638, 'cardiology, general, pulmonology', '+91 79 2687 0000');

-- ── Sample custom diseases ────────────────────────────────────
INSERT INTO custom_diseases (name, specialties, icon) VALUES
('Dengue Fever',    'general, nephrology',    '🦟'),
('Typhoid',         'general',                '🤒'),
('Malaria',         'general',                '🦠'),
('COVID-19',        'pulmonology, general',   '😷'),
('Chickenpox',      'dermatology, general',   '🔴');

SELECT 'Database setup complete!' AS status;
