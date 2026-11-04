SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS service_logs;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    uid VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(20) DEFAULT '',
    created_at BIGINT NOT NULL
);

CREATE TABLE vehicles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    type VARCHAR(20) NOT NULL,
    brand VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL,
    reg_number VARCHAR(50),
    purchase_date DATE,
    user_role VARCHAR(50),
    setup_done TINYINT(1) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

SET FOREIGN_KEY_CHECKS = 1;

CREATE TABLE documents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT NOT NULL,
    doc_key VARCHAR(50) NOT NULL,
    doc_name VARCHAR(150) NOT NULL,
    file_data LONGTEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
);

CREATE TABLE service_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT NOT NULL UNIQUE,
    checked_data TEXT,
    timer_data TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
);
-- 3. Trips Table (Updated with proper foreign keys and coordinates)
CREATE TABLE IF NOT EXISTS trips (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    vehicle_id INT NOT NULL,
    start_location VARCHAR(255),
    start_latitude DECIMAL(10, 8),
    start_longitude DECIMAL(11, 8),
    destination VARCHAR(255),
    destination_latitude DECIMAL(10, 8),
    destination_longitude DECIMAL(11, 8),
    distance DECIMAL(10, 2),
    fuel_used DECIMAL(10, 2),
    fuel_cost DECIMAL(10, 2),
    trip_date DATE,
    trip_purpose VARCHAR(50),
    notes TEXT,
    total_cost DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE
);

-- 4. Trip Expenses Table (Handles individual itemized expenses for each trip)
CREATE TABLE IF NOT EXISTS trip_expenses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trip_id INT NOT NULL,
    expense_type VARCHAR(50),
    amount DECIMAL(10, 2),
    expense_date DATE,
    notes TEXT,
    FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
);
SET FOREIGN_KEY_CHECKS = 0;

-- Ensure vehicles table supports EV parameters and vehicle types
ALTER TABLE vehicles 
    MODIFY COLUMN type VARCHAR(30) NOT NULL,
    ADD COLUMN IF NOT EXISTS battery_capacity DECIMAL(8,2) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS battery_health INT DEFAULT 100,
    ADD COLUMN IF NOT EXISTS estimated_range INT DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS charging_type VARCHAR(50) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS connector_type VARCHAR(50) DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS charging_cost_per_kwh DECIMAL(6,2) DEFAULT 0.00,
    ADD COLUMN IF NOT EXISTS current_battery_pct INT DEFAULT 100,
    ADD COLUMN IF NOT EXISTS home_charging TINYINT(1) DEFAULT 1,
    ADD COLUMN IF NOT EXISTS fast_charging TINYINT(1) DEFAULT 0;

-- EV Charging Logs Table
CREATE TABLE IF NOT EXISTS charging_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT NOT NULL,
    user_id INT NOT NULL,
    charging_date DATE NOT NULL,
    start_battery INT NOT NULL,
    end_battery INT NOT NULL,
    energy_charged DECIMAL(8,2) NOT NULL, -- kWh
    charging_duration VARCHAR(50),
    charging_type VARCHAR(50), -- Home, AC, DC Fast, Public
    cost_per_kwh DECIMAL(6,2) NOT NULL,
    total_cost DECIMAL(10,2) NOT NULL,
    location VARCHAR(255),
    odometer INT DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- EV Charging Appointments / Reminders Table
CREATE TABLE IF NOT EXISTS charging_appointments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id INT NOT NULL,
    user_id INT NOT NULL,
    station_name VARCHAR(255) NOT NULL,
    appointment_date DATE NOT NULL,
    appointment_time VARCHAR(50) NOT NULL,
    charging_type VARCHAR(50),
    notes TEXT,
    status VARCHAR(30) DEFAULT 'Upcoming',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

SET FOREIGN_KEY_CHECKS = 1;