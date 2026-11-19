CREATE DATABASE traffic_db;
USE traffic_db;

CREATE TABLE admins (
    admin_id      INT AUTO_INCREMENT PRIMARY KEY,
    username      VARCHAR(50)  NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name     VARCHAR(100) NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE vehicles (
    vehicle_id     INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_number VARCHAR(20)  NOT NULL UNIQUE,
    vehicle_type   VARCHAR(30)  NOT NULL,
    owner_name     VARCHAR(100) NOT NULL,
    owner_phone    VARCHAR(15),
    owner_address  VARCHAR(255),
    registered_on  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE violation_types (
    type_id        INT AUTO_INCREMENT PRIMARY KEY,
    violation_name VARCHAR(100)  NOT NULL UNIQUE,
    fine_amount    DECIMAL(10,2) NOT NULL
);

CREATE TABLE violations (
    violation_id   INT AUTO_INCREMENT PRIMARY KEY,
    vehicle_id     INT NOT NULL,
    type_id        INT NOT NULL,
    admin_id       INT NOT NULL,
    location       VARCHAR(150) NOT NULL,
    violation_date DATE NOT NULL,
    fine_amount    DECIMAL(10,2) NOT NULL,
    payment_status ENUM('Unpaid','Paid') NOT NULL DEFAULT 'Unpaid',
    paid_on        DATE NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    FOREIGN KEY (type_id)    REFERENCES violation_types(type_id),
    FOREIGN KEY (admin_id)   REFERENCES admins(admin_id)
);

INSERT INTO violation_types (violation_name, fine_amount) VALUES
('No Helmet', 500.00),
('Overspeeding', 1000.00),
('Red Light Jumping', 1000.00),
('No Seat Belt', 500.00),
('Wrong Parking', 500.00),
('Triple Riding', 1000.00),
('Using Mobile While Driving', 1500.00),
('Driving Without Licence', 5000.00);