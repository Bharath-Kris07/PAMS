# Pet Adoption Management System (PAMS)

A comprehensive, full-stack local web application designed to manage pet adoptions, medical records, and shelter operations. Built with strict adherence to Entity-Relationship (ER) modeling, utilizing a dual-database architecture (MySQL + MongoDB).

## 🌟 Key Features

- **Role-Based Access Control (RBAC):** Distinct dashboards and permissions for 'Admin' and 'Staff' users.
- **Strict ER-Compliance:** Built entirely using raw SQL queries to ensure perfect alignment with the logical ER diagram (no ORM abstraction).
- **Animal & Medical Management:** Track species, breeds, availability status, and detailed medical history logs.
- **Adoption Pipeline:** Process adoptions, track pending requests, and handle adoption returns using automated MySQL Triggers.
- **Financial Analytics:** Monitor revenue, track nominal recovery fees for adoptions, and view recent payments.
- **Dual-Database Architecture:** 
  - **MySQL/MariaDB:** Handles structured, relational data (entities, relationships, and transactions).
  - **MongoDB:** Handles unstructured data (BSON image uploads for pet profiles) and secure password hashing.

## 🛠️ Technology Stack

- **Backend:** Python, Flask
- **Relational Database:** MySQL / MariaDB (via XAMPP)
- **NoSQL Database:** MongoDB (PyMongo)
- **Frontend:** HTML5, Tailwind CSS, Jinja2 Templating
- **Security:** Werkzeug Password Hashing

## 🚀 Setup Instructions

Follow these steps to run the project locally:

### 1. Install Dependencies
Ensure you have Python installed. Clone the repository and install the required packages:
`pip install -r requirements.txt`

### 2. Start Database Servers
- **MySQL:** Open XAMPP and start both the **Apache** and **MySQL** services.
- **MongoDB:** Ensure your local MongoDB server is running on the default port (`localhost:27017`).

### 3. Initialize the MySQL Database
- Open phpMyAdmin (or your preferred MySQL client).
- Create a new database named `pams_db`.
- Import the provided SQL schema (`schema.txt`) into `pams_db` to generate the tables and triggers.

### 4. Seed MongoDB Credentials
Because staff IDs are stored in MySQL but passwords are in MongoDB, you must seed the initial passwords before logging in:
1. Start the Flask application (see step 5).
2. Open your browser and navigate to `http://127.0.0.1:5000/seed_passwords`.
3. This script will automatically securely hash and store default passwords (`password123`) for all staff members found in your MySQL database.

### 5. Run the Application
Start the local Flask development server:
`python app.py`

Access the application at `http://127.0.0.1:5000`.

## 🏗️ Architecture Highlights

- **Dynamic Status Derivation:** Instead of relying on hardcoded status columns that violate normalization, adoption statuses (Pending, Approved, Returned) are derived on-the-fly using complex `JOIN` and `CASE` SQL statements.
- **Database Integrity:** Utilizes MySQL `FOREIGN KEY` constraints, `CASCADE` rules, and `AFTER INSERT` triggers to maintain flawless data consistency.
