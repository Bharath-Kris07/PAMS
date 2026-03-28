# Haven Flow - Pet Adoption Management System

A local Python/Flask and MySQL/XAMPP application for managing pet adoptions, medical records, and shelter operations. 

## Features

- **Staff Authentication:** Secure login for shelter staff.
- **Animal Management:** Track species, breeds, availability status, and demographics.
- **Medical Records:** Maintain and track health histories, notes, and treatments.
- **Financial Analytics:** Monitor adoptions, adoption fees, ongoing dues, and recent payments.
- **Adopter Tracking:** Register adopters.

## Setup Instructions

Follow these steps to set up the project locally:

1. **Install Dependencies:**
   Make sure you have Python installed. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

2. **Start Database Server:**
   Start **XAMPP** and ensure both **Apache** and **MySQL** services are running.

3. **Initialize the Database:**
   - Open phpMyAdmin (or any MySQL client).
   - Create a new database named `pams_db`.
   - Import the provided SQL schema (`schema.txt` / dump) into the `pams_db` database to create the necessary tables.

4. **Run the Application:**
   Start the local Flask development server by running:
   ```bash
   python app.py
   ```
   The application will be accessible at `http://127.0.0.0:5000` (or `http://localhost:5000`).

## Architecture Highlights
- Uses **Flask** as the backend framework.
- Uses **SQLAlchemy** for Object Relational Mapping.
- Template rendering with **Jinja2**.
- Styled with modern **Tailwind CSS**. 
