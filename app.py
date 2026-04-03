import locale
import re
import io
import bson.binary
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_pymongo import PyMongo
from sqlalchemy import text  
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/pams_db'
app.config['SQLALCHEMY_ECHO'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'haven_flow_secret' 

db = SQLAlchemy(app)

app.config['MONGO_URI'] = 'mongodb://localhost:27017/pams_photos'
mongo = PyMongo(app)

# MongoDB interactions handled separately from SQL
@app.before_request
def require_login():
    allowed_routes = ['login', 'static', 'seed_passwords']
    if request.endpoint and request.endpoint not in allowed_routes and 'staff_id' not in session:
        return redirect(url_for('login'))

@app.context_processor
def inject_staff():
    if 'staff_id' in session:
        query = text("SELECT * FROM STAFF WHERE Staff_ID = :id")
        staff = db.session.execute(query, {'id': session['staff_id']}).fetchone()
        return dict(current_staff=staff)
    return dict(current_staff=None)

@app.template_filter('in_rupees')
def in_rupees(value):
    """Formats a number as Indian Rupees (e.g. 20000 -> ₹20,000)"""
    try:
        value = float(value)
    except (ValueError, TypeError):
        return "₹0"
    
    # Custom Indian numbering format logic
    s, *d = str(int(value)).partition(".")
    r = ",".join([s[x-2:x] for x in range(-3, -len(s), -2)][::-1] + [s[-3:]])
    return f"₹{r}"

@app.template_filter('in_mobile')
def in_mobile(value):
    """Formats a 10-digit number as an Indian mobile number (+91 XXXX XXXXX)"""
    val = str(value).replace(" ", "").replace("+91", "")
    if len(val) == 10:
        return f"+91 {val[:5]} {val[5:]}"
    return value


@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') not in ['Admin', 'Staff']: return 'Unauthorized', 403
    entity_type = request.form.get('entity_type')
    entity_id_str = request.form.get('entity_id')
    
    if not entity_type or not entity_id_str:
        flash("Missing entity information.", "error")
        return redirect(request.referrer)
        
    try:
        entity_id = int(entity_id_str)
    except ValueError:
        flash("Invalid entity ID.", "error")
        return redirect(request.referrer)

    if 'photo' not in request.files:
        flash("No photo file selected.", "error")
        return redirect(request.referrer)
    
    file = request.files['photo']
    if file.filename == '':
        flash("No file selected.", "error")
        return redirect(request.referrer)

    try:
        image_data = bson.binary.Binary(file.read())
        
        mongo.db.photos.update_one(
            {'MySQL_ID': entity_id, 'type': entity_type},
            {
                '$set': {
                    'image_data': image_data,
                    'filename': file.filename,
                    'mimetype': file.mimetype
                }
            },
            upsert=True
        )
        flash("Photo uploaded successfully!", "success")
    except Exception as e:
        flash(f"Error uploading photo: {str(e)}", "error")
        
    return redirect(request.referrer)

@app.route('/image/<entity_type>/<int:entity_id>')
def serve_image(entity_type, entity_id):
    try:
        photo = mongo.db.photos.find_one({'MySQL_ID': entity_id, 'type': entity_type})
        if photo and 'image_data' in photo:
            return send_file(
                io.BytesIO(photo['image_data']),
                mimetype=photo.get('mimetype', 'image/jpeg')
            )
    except Exception:
        pass
        
    return redirect('https://placehold.co/400x400/eeeeee/a0aec0?text=No+Photo')

@app.route('/reports/medical/<int:animal_id>')
def report_medical(animal_id):
    query = """
SELECT m.Treatment, m.Treatment_Date, m.Notes, a.Name as Animal_Name
FROM MEDICAL_RECORD m
JOIN ANIMAL a ON m.Animal_ID = a.Animal_ID
WHERE a.Animal_ID = :animal_id
ORDER BY m.Treatment_Date DESC
"""
    result = db.session.execute(db.text(query), {'animal_id': animal_id}).fetchall()
    return render_template('reports.html', report_type='medical', data=result, query_text=query.strip(), animal_id=animal_id)

@app.route('/reports/revenue')
def report_revenue():
    query = "SELECT SUM(Amount) as Total_Revenue FROM PAYMENT"
    result = db.session.execute(db.text(query)).fetchone()
    total_revenue = result.Total_Revenue if result and result.Total_Revenue else 0
    return render_template('reports.html', report_type='revenue', data={'Total_Revenue': total_revenue}, query_text=query.strip())

@app.route('/reports/species')
def report_species():
    query = """
SELECT s.Species_Name, COUNT(a.Animal_ID) as Available_Count
FROM SPECIES s
JOIN BREED b ON s.Species_ID = b.Species_ID
JOIN ANIMAL a ON b.Breed_ID = a.Breed_ID
WHERE a.Animal_ID NOT IN (
    SELECT ad.Animal_ID 
    FROM ADOPTION ad 
    LEFT JOIN AdoptionReturn ar ON ad.Adoption_ID = ar.Adoption_ID 
    WHERE ar.Return_Date IS NULL
)
GROUP BY s.Species_Name
ORDER BY Available_Count DESC
"""
    result = db.session.execute(db.text(query)).fetchall()
    return render_template('reports.html', report_type='species', data=result, query_text=query.strip())


@app.route('/')
def dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    role_name = session.get('role_name')
    if role_name == 'Admin':
        return redirect(url_for('admin_dashboard'))
    elif role_name == 'Staff':
        return redirect(url_for('staff_dashboard'))
        
    try:
        query = text("""
            SELECT a.*, b.Breed_Name, s.Species_Name, 'Available' as adoption_status
            FROM ANIMAL a
            LEFT JOIN BREED b ON a.Breed_ID = b.Breed_ID
            LEFT JOIN SPECIES s ON b.Species_ID = s.Species_ID
            WHERE a.Animal_ID NOT IN (
                SELECT ad.Animal_ID 
                FROM ADOPTION ad 
                LEFT JOIN AdoptionReturn ar ON ad.Adoption_ID = ar.Adoption_ID 
                WHERE ar.Return_Date IS NULL
            )
        """)
        available_animals = db.session.execute(query).fetchall()
    except Exception as e:
        available_animals = []
    return render_template('dashboard.html', animals=available_animals)

@app.route('/admin/dashboard')
@app.route('/admin/dashboard')
def admin_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
        
    search_term = request.args.get('q')
    
    # 1. Querying the View instead of raw tables!
    query_str = """
        SELECT Animal_ID, Name, Gender, Adoption_Status, Species_Name AS Species 
        FROM view_staff_pets
    """
    
    params = {}
    
    # 2. Applying the search filter directly to the View
    if search_term:
        query_str += " WHERE (Name LIKE :term OR Breed_Name LIKE :term OR Species_Name LIKE :term"
        params['term'] = f"%{search_term}%"
        if search_term.isdigit():
            query_str += " OR Animal_ID = :exact_id"
            params['exact_id'] = int(search_term)
        query_str += ")"

    pets_result = db.session.execute(text(query_str), params)
    pets = [dict(zip([k.lower() for k in pets_result.keys()], row)) for row in pets_result.fetchall()]

    staff_result = db.session.execute(text("""
        SELECT s.Staff_ID, s.F_Name, s.L_Name, r.Role_Name as Role 
        FROM STAFF s 
        LEFT JOIN ROLE r ON s.Role_ID = r.Role_ID
    """))
    staff_members = [dict(zip([k.lower() for k in staff_result.keys()], row)) for row in staff_result.fetchall()]
        
    return render_template('admin_dashboard.html', pets=pets, staff_members=staff_members)
@app.route('/admin/staff/<int:id>/update_role', methods=['POST'])
def update_staff_role(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    new_role = request.form.get('role')
    
    try:
        # Added extra safeguards in the WHERE clause: Staff cannot update themselves or other Admins
        db.session.execute(text("""
            UPDATE STAFF 
            SET Role_ID = (SELECT Role_ID FROM ROLE WHERE Role_Name = :role) 
            WHERE Staff_ID = :id 
            AND Staff_ID != :current_id
            AND Role_ID NOT IN (SELECT Role_ID FROM ROLE WHERE Role_Name = 'Admin')
        """), {
            'role': new_role, 
            'id': id, 
            'current_id': session.get('staff_id')
        })
        db.session.commit()
        flash(f"Staff role updated successfully to {new_role}!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Database error updating role: {str(e)}", "error")
        
    return redirect(url_for('admin_dashboard'))

@app.route('/staff/dashboard')
def staff_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Staff': return "Unauthorized", 403
    
    query = text("""
        SELECT a.Animal_ID, a.Name, a.Gender, 
               'Available' AS Adoption_Status, 
               s.Species_Name AS Species 
        FROM ANIMAL a 
        LEFT JOIN BREED b ON a.Breed_ID = b.Breed_ID 
        LEFT JOIN SPECIES s ON b.Species_ID = s.Species_ID
        WHERE a.Animal_ID NOT IN (
            SELECT ad.Animal_ID 
            FROM ADOPTION ad 
            LEFT JOIN AdoptionReturn ar ON ad.Adoption_ID = ar.Adoption_ID 
            WHERE ar.Return_Date IS NULL
        )
    """)
    pets_result = db.session.execute(query)
    pets = [dict(zip([k.lower() for k in pets_result.keys()], row)) for row in pets_result.fetchall()]
    return render_template('staff_dashboard.html', pets=pets)
@app.route('/animals/all')
def all_animals():
    if 'staff_id' not in session: return redirect(url_for('login'))

    query = text("SELECT * FROM view_all_animals")

    result = db.session.execute(query)
    columns = result.keys()

    animals = [dict(zip([k.lower() for k in columns], row)) for row in result.fetchall()]

    return render_template('all_animals.html', animals=animals)
@app.route('/admin/animal/<int:id>/delete', methods=['POST'])
def delete_animal(id):

    if 'staff_id' not in session or session.get('role_name') != 'Admin':
        flash("Unauthorized access.", "error")
        return redirect(url_for('login'))
        
    try:
    
        db.session.execute(text("""
            DELETE FROM PAYMENT 
            WHERE Adoption_ID IN (SELECT Adoption_ID FROM ADOPTION WHERE Animal_ID = :id)
        """), {'id': id})

        db.session.execute(text("""
            DELETE FROM AdoptionReturn 
            WHERE Adoption_ID IN (SELECT Adoption_ID FROM ADOPTION WHERE Animal_ID = :id)
        """), {'id': id})

        db.session.execute(text("DELETE FROM ADOPTION WHERE Animal_ID = :id"), {'id': id})
        
        db.session.execute(text("DELETE FROM MEDICAL_RECORD WHERE Animal_ID = :id"), {'id': id})
        
        db.session.execute(text("DELETE FROM ANIMAL WHERE Animal_ID = :id"), {'id': id})
        
        db.session.commit()
        flash("Animal and all associated records deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Database error deleting animal: {str(e)}", "error")
        print(f"Delete animal failed: {str(e)}")
        
    # Redirect to the main directory
    return redirect(url_for('all_animals'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
        password = request.form.get('password')
        
        if not staff_id or not password:
            flash("Please enter both ID and password.", "error")
            return render_template('login.html')
            
        try:
            staff_id = int(staff_id)
            query = text("""
                SELECT s.*, r.Role_Name 
                FROM STAFF s 
                LEFT JOIN ROLE r ON s.Role_ID = r.Role_ID 
                WHERE s.Staff_ID = :id
            """)
            staff = db.session.execute(query, {'id': staff_id}).fetchone()
            
            if staff:
                auth_doc = mongo.db.credentials.find_one({'staff_id': staff_id})
                
                if auth_doc and check_password_hash(auth_doc['password_hash'], password):
                    session['staff_id'] = staff_id 
                    session['role_name'] = getattr(staff, 'Role_Name', None)
                    
                    flash(f"Welcome back, {staff.F_Name}!", "success")
                    
                    if session['role_name'] == 'Admin':
                        return redirect(url_for('admin_dashboard'))
                    elif session['role_name'] == 'Staff':
                        return redirect(url_for('staff_dashboard'))
                    else:
                        return redirect(url_for('dashboard'))
                else:
                    flash("Invalid ID or Password.", "error")
            else:
                flash("Invalid ID or Password.", "error")
        except (ValueError, TypeError):
            flash("Staff ID must be numeric.", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear() 
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    staff_id = session['staff_id']
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if not all([current_password, new_password, confirm_password]):
            flash("All password fields are required.", "error")
            return redirect(url_for('profile'))
            
        if new_password != confirm_password:
            flash("New passwords do not match.", "error")
            return redirect(url_for('profile'))
            
        try:
            auth_doc = mongo.db.credentials.find_one({'staff_id': staff_id})
            if auth_doc and check_password_hash(auth_doc['password_hash'], current_password):
                hashed_pw = generate_password_hash(new_password)
                mongo.db.credentials.update_one(
                    {'staff_id': staff_id},
                    {'$set': {'password_hash': hashed_pw}}
                )
                flash("Password updated successfully!", "success")
            else:
                flash("Incorrect current password.", "error")
        except Exception as e:
            flash(f"Error updating password: {e}", "error")
            
        return redirect(url_for('profile'))
        
    query = text("""
        SELECT s.*, r.Role_Name 
        FROM STAFF s 
        LEFT JOIN ROLE r ON s.Role_ID = r.Role_ID 
        WHERE s.Staff_ID = :id
    """)
    staff = db.session.execute(query, {'id': staff_id}).fetchone()
    return render_template('profile.html', staff=staff)

@app.route('/medical/dashboard')
def medical_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    query = text("""
        SELECT a.*, m.Treatment as last_treatment_name, m.Treatment_Date as last_treatment_date
        FROM ANIMAL a
        LEFT JOIN (
            SELECT Animal_ID, MAX(Treatment_Date) as max_date
            FROM MEDICAL_RECORD
            GROUP BY Animal_ID
        ) last_date ON a.Animal_ID = last_date.Animal_ID
        LEFT JOIN MEDICAL_RECORD m ON a.Animal_ID = m.Animal_ID AND m.Treatment_Date = last_date.max_date
        ORDER BY last_date.max_date DESC
    """)
    medical_result = db.session.execute(query)
    all_medical_animals = [dict(zip([k.lower() for k in medical_result.keys()], row)) for row in medical_result.fetchall()]
    return render_template('medical_dashboard.html', animals=all_medical_animals)

@app.route('/medical/add', methods=['GET', 'POST'])
def add_medical_record():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        animal_id = request.form.get('animal_id')
        treatment = request.form.get('treatment')
        treatment_date = request.form.get('treatment_date')
        notes = request.form.get('notes')
        
        try:
            insert_q = text("""
                INSERT INTO MEDICAL_RECORD (Treatment, Treatment_Date, Notes, Animal_ID, Staff_ID)
                VALUES (:treatment, :t_date, :notes, :a_id, :s_id)
            """)
            db.session.execute(insert_q, {
                'treatment': treatment,
                't_date': datetime.strptime(treatment_date, '%Y-%m-%d').date() if treatment_date else None,
                'notes': notes,
                'a_id': int(animal_id),
                's_id': session.get('staff_id')
            })
            db.session.commit()
            
            
            flash('Medical record added successfully.', 'success')
            return redirect(url_for('animal_profile', id=animal_id))
        except Exception as e:
            db.session.rollback()
            clean_error = str(e).split('[SQL:')[0].strip()
            flash(clean_error, 'error')
            
    animal_res = db.session.execute(text("SELECT Animal_ID, Name FROM ANIMAL"))
    animals = [dict(zip([k.lower() for k in animal_res.keys()], row)) for row in animal_res.fetchall()]
    return render_template('add_medical_record.html', animals=animals)

@app.route('/analytics/revenue')
def revenue_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    try:
        total_revenue = db.session.execute(text("SELECT SUM(Amount) as total FROM PAYMENT")).scalar() or 0
        
        pending_query = text("""
            SELECT a.Adoption_ID, a.Fee, ad.F_Name, ad.L_Name, an.Name as Animal_Name,
                   COALESCE(SUM(p.Amount), 0) as paid_amount
            FROM ADOPTION a
            JOIN ADOPTER ad ON a.Adopter_ID = ad.Adopter_ID
            JOIN ANIMAL an ON a.Animal_ID = an.Animal_ID
            LEFT JOIN PAYMENT p ON a.Adoption_ID = p.Adoption_ID
            GROUP BY a.Adoption_ID, a.Fee, ad.F_Name, ad.L_Name, an.Name
            HAVING COALESCE(SUM(p.Amount), 0) < a.Fee
        """)
        pending_dues = db.session.execute(pending_query).fetchall()
        
        recent_payments_query = text("""
            SELECT p.*, ad.F_Name, ad.L_Name 
            FROM PAYMENT p
            JOIN ADOPTION a ON p.Adoption_ID = a.Adoption_ID
            JOIN ADOPTER ad ON a.Adopter_ID = ad.Adopter_ID
            ORDER BY p.Payment_Date DESC LIMIT 10
        """)
        recent_payments = db.session.execute(recent_payments_query).fetchall()
    except:
        total_revenue = 0
        pending_dues = []
        recent_payments = []
         
    return render_template('revenue_dashboard.html', 
                          total_revenue=total_revenue, 
                          pending_dues=pending_dues, 
                          recent_payments=recent_payments)

@app.route('/animal/add', methods=['GET', 'POST'])
def add_animal():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form.get('name')
        gender = request.form.get('gender')
        dob_str = request.form.get('dob')
        species_name = request.form.get('species_name')
        breed_name = request.form.get('breed_name')
        
        try:
            species_q = text("SELECT Species_ID FROM SPECIES WHERE Species_Name = :sn")
            species_res = db.session.execute(species_q, {'sn': species_name}).fetchone()
            
            if species_res:
                species_id = species_res.Species_ID
            else:
                db.session.execute(text("INSERT INTO SPECIES (Species_Name) VALUES (:sn)"), {'sn': species_name})
                species_id = db.session.execute(text("SELECT LAST_INSERT_ID()")).scalar()
            
            breed_q = text("SELECT Breed_ID FROM BREED WHERE Breed_Name = :bn AND Species_ID = :sid")
            breed_res = db.session.execute(breed_q, {'bn': breed_name, 'sid': species_id}).fetchone()
            
            if breed_res:
                breed_id = breed_res.Breed_ID
            else:
                db.session.execute(text("INSERT INTO BREED (Breed_Name, Species_ID) VALUES (:bn, :sid)"), 
                                   {'bn': breed_name, 'sid': species_id})
                breed_id = db.session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

            # Insert Animal (Status is derived, so we omit Adoption_Status column)
            dob = datetime.strptime(dob_str, '%Y-%m-%d').date() if dob_str else None
            insert_animal_q = text("""
                INSERT INTO ANIMAL (Name, Gender, DateOfBirth, Breed_ID)
                VALUES (:name, :gender, :dob, :bid)
            """)
            db.session.execute(insert_animal_q, {
                'name': name,
                'gender': gender,
                'dob': dob,
                'bid': breed_id
            })
            animal_id = db.session.execute(text("SELECT LAST_INSERT_ID()")).scalar()

            # Handle Optional Photo (MongoDB)
            if 'photo' in request.files:
                file = request.files['photo']
                if file.filename != '':
                    image_data = bson.binary.Binary(file.read())
                    mongo.db.photos.update_one(
                        {'MySQL_ID': int(animal_id), 'type': 'animal'},
                        {
                            '$set': {
                                'image_data': image_data,
                                'filename': file.filename,
                                'mimetype': file.mimetype
                            }
                        },
                        upsert=True
                    )
            
            db.session.commit()
            flash(f"Animal '{name}' successfully added!", "success")
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding animal: {str(e)}", "error")
    
    return render_template('add_animal.html')

@app.route('/adopter/register', methods=['GET', 'POST'])
def register_adopter():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        f_name = request.form.get('f_name')
        l_name = request.form.get('l_name')
        email = request.form.get('email')
        address = request.form.get('address')
        phone = request.form.get('phone') 
        
        try:
            insert_q = text("""
                INSERT INTO ADOPTER (F_Name, L_Name, Email, Address)
                VALUES (:fn, :ln, :em, :addr)
            """)
            db.session.execute(insert_q, {'fn': f_name, 'ln': l_name, 'em': email, 'addr': address})
            
            adopter_id_q = text("SELECT Adopter_ID FROM ADOPTER WHERE Email = :em ORDER BY Adopter_ID DESC LIMIT 1")
            new_id_res = db.session.execute(adopter_id_q, {'em': email}).fetchone()
            adopter_id = new_id_res.Adopter_ID if new_id_res else None
            
            if phone and adopter_id:
                db.session.execute(text("INSERT INTO ADOPTER_PHONE (Phone_Number, Adopter_ID) VALUES (:ph, :aid)"), 
                                   {'ph': phone, 'aid': adopter_id})
                
            db.session.commit()
            
            
            flash("Adopter registered successfully!", "success")
            if adopter_id:
                return redirect(url_for('adopter_profile', id=adopter_id))
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error registering adopter: {str(e)}", "error")
            
    return render_template('register_adopter.html')

@app.route('/adopters')
def view_adopters():
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    try:
        search_term = request.args.get('q')
        # LEFT JOIN with subquery to pick the primary/first phone number recorded
        base_query = """
            SELECT a.*, ap.Phone_Number 
            FROM ADOPTER a 
            LEFT JOIN (
                SELECT Adopter_ID, MIN(Phone_Number) as Phone_Number 
                FROM ADOPTER_PHONE 
                GROUP BY Adopter_ID
            ) ap ON a.Adopter_ID = ap.Adopter_ID
        """
        params = {}
        
        if search_term:
            base_query += " WHERE a.F_Name LIKE :term OR a.L_Name LIKE :term OR a.Email LIKE :term"
            params['term'] = f"%{search_term}%"
            if search_term.isdigit():
                base_query += " OR a.Adopter_ID = :id"
                params['id'] = int(search_term)
        
        base_query += " LIMIT 50"
        adopters = db.session.execute(text(base_query), params).fetchall()
    except Exception as e:
        adopters = []
        
    return render_template('adopters_list.html', adopters=adopters)

@app.route('/animal/<int:id>')
def animal_profile(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    animal_res = db.session.execute(text("""
        SELECT a.*, b.Breed_Name, s.Species_Name,
               CASE 
                   WHEN a.Animal_ID IN (
                       SELECT ad.Animal_ID 
                       FROM ADOPTION ad 
                       LEFT JOIN AdoptionReturn ar ON ad.Adoption_ID = ar.Adoption_ID 
                       WHERE ar.Return_Date IS NULL
                   ) THEN 'Adopted' 
                   ELSE 'Available' 
               END AS Adoption_Status
        FROM ANIMAL a
        LEFT JOIN BREED b ON a.Breed_ID = b.Breed_ID
        LEFT JOIN SPECIES s ON b.Species_ID = s.Species_ID
        WHERE a.Animal_ID = :id
    """), {'id': id})
    animal_list = [dict(zip([k.lower() for k in animal_res.keys()], row)) for row in animal_res.fetchall()]
    animal = animal_list[0] if animal_list else None
    
    if not animal:
        flash("Animal not found.", "error")
        return redirect(url_for('dashboard'))
        
    medical_res = db.session.execute(text("""
        SELECT * FROM MEDICAL_RECORD 
        WHERE Animal_ID = :id 
        ORDER BY Treatment_Date DESC
    """), {'id': id})
    medical_records = [dict(zip([k.lower() for k in medical_res.keys()], row)) for row in medical_res.fetchall()]
    
    adopt_res = db.session.execute(text("""
        SELECT ad.Adoption_ID, ad.Adoption_Date, 
               CASE WHEN ar.Return_Date IS NOT NULL THEN 'Returned' 
                    WHEN ad.Staff_ID IS NULL THEN 'Pending' 
                    ELSE 'Approved' END AS status, 
               a.Adopter_ID, a.F_Name, a.L_Name, ar.Return_Date, ar.Return_Reason 
        FROM ADOPTION ad 
        JOIN ADOPTER a ON ad.Adopter_ID = a.Adopter_ID 
        LEFT JOIN AdoptionReturn ar ON ad.Adoption_ID = ar.Adoption_ID 
        WHERE ad.Animal_ID = :id 
        ORDER BY ad.Adoption_Date DESC
    """), {'id': id})
    adoptions = [dict(zip([k.lower() for k in adopt_res.keys()], row)) for row in adopt_res.fetchall()]

    # Fetch all adopters for the adoption modal datalist
    adopter_res = db.session.execute(text("SELECT Adopter_ID, F_Name, L_Name FROM ADOPTER ORDER BY F_Name, L_Name"))
    adopters = [dict(zip([k.lower() for k in adopter_res.keys()], row)) for row in adopter_res.fetchall()]

    return render_template('animal_profile.html', animal=animal, medical_records=medical_records, adoptions=adoptions, adopters=adopters)

@app.route('/animal/<int:id>/adopt', methods=['POST'])
def adopt_animal(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    adopter_id = request.form.get('adopter_id')
    raw_fee = request.form.get('fee', '0')
    staff_id = session.get('staff_id')
    
    # Safe float conversion ensures the trigger gets a valid number
    try:
        fee = float(raw_fee) if raw_fee and raw_fee.strip() != '' else 0.0
    except ValueError:
        fee = 0.0
    
    try:
        # We ONLY insert into ADOPTION. 
        # The MySQL trigger 'after_adoption_insert' will automatically catch this and log the PAYMENT.
        db.session.execute(text("""
            INSERT INTO ADOPTION (Animal_ID, Adopter_ID, Staff_ID, Adoption_Date, Fee) 
            VALUES (:an_id, :ad_id, :st_id, CURRENT_DATE, :fee)
        """), {'an_id': id, 'ad_id': adopter_id, 'st_id': staff_id, 'fee': fee})
            
        db.session.commit()
        flash("Adoption logged successfully! Payment handled via database trigger.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Database error: {str(e)}", "error")
        print(f"Adoption failed: {str(e)}") 
        
    return redirect(url_for('animal_profile', id=id))

@app.route('/adopter/<int:id>')
def adopter_profile(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    adopter = db.session.execute(text("SELECT * FROM ADOPTER WHERE Adopter_ID = :id"), {'id': id}).fetchone()
    
    if not adopter:
        flash("Adopter not found.", "error")
        return redirect(url_for('dashboard'))
        
    phones = db.session.execute(text("SELECT Phone_Number FROM ADOPTER_PHONE WHERE Adopter_ID = :id"), {'id': id}).fetchall()
    
    adoptions = db.session.execute(text("""
        SELECT a.Adoption_ID, a.Adoption_Date, an.Animal_ID, an.Name AS Animal_Name, a.Fee, r.Return_Date 
        FROM ADOPTION a 
        JOIN ANIMAL an ON a.Animal_ID = an.Animal_ID 
        LEFT JOIN AdoptionReturn r ON a.Adoption_ID = r.Adoption_ID 
        WHERE a.Adopter_ID = :id 
        ORDER BY a.Adoption_Date DESC
    """), {'id': id}).fetchall()
    
    total_contributions = db.session.execute(text("""
        SELECT COALESCE(SUM(p.Amount), 0) 
        FROM PAYMENT p 
        JOIN ADOPTION a ON p.Adoption_ID = a.Adoption_ID 
        WHERE a.Adopter_ID = :id
    """), {'id': id}).scalar()
    
    active_adoptions = db.session.execute(text("""
        SELECT ad.Adoption_ID, an.Name AS Pet_Name, ad.Fee 
        FROM ADOPTION ad 
        JOIN ANIMAL an ON ad.Animal_ID = an.Animal_ID 
        WHERE ad.Adopter_ID = :id 
        AND ad.Adoption_ID NOT IN (SELECT Adoption_ID FROM AdoptionReturn)
    """), {'id': id}).fetchall()
    
    return render_template('adopter_profile.html', adopter=adopter, phones=phones, adoptions=adoptions, total_fees=total_contributions, active_adoptions=active_adoptions)

@app.route('/admin/adopter/<int:id>/return_adoption', methods=['POST'])
def return_adoption_from_profile(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    adoption_id = request.form.get('adoption_id')
    return_reason = request.form.get('return_reason')
    
    try:
        # Note: Refund is handled by a database trigger, so we only insert the return record.
        db.session.execute(text("""
            INSERT INTO AdoptionReturn (Adoption_ID, Return_Date, Return_Reason) 
            VALUES (:ad_id, CURRENT_DATE, :reason)
        """), {'ad_id': adoption_id, 'reason': return_reason})
        db.session.commit()
        flash("Adoption return processed successfully! Refund issued via trigger.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error processing return: {e}", "error")
        
    return redirect(url_for('adopter_profile', id=id))

@app.route('/animal/<int:id>/medical', methods=['GET', 'POST'])
def view_medical_records(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        treatment_name = request.form.get('treatment_name')
        treatment_date = request.form.get('treatment_date')
        notes = request.form.get('notes')
        staff_id = session.get('staff_id')
        
        try:
            db.session.execute(text("""
                INSERT INTO MEDICAL_RECORD (Animal_ID, Staff_ID, Treatment, Treatment_Date, Notes)
                VALUES (:a_id, :s_id, :name, :date, :notes)
            """), {
                'a_id': id,
                's_id': staff_id,
                'name': treatment_name,
                'date': treatment_date,
                'notes': notes
            })
            db.session.commit()
            flash("Medical record logged successfully.", "success")
        except Exception as e:
            db.session.rollback()
            clean_error = str(e).split('[SQL:')[0].strip()
            flash(clean_error, 'error')
        return redirect(url_for('view_medical_records', id=id))
        
    animal_res = db.session.execute(text("SELECT * FROM ANIMAL WHERE Animal_ID = :id"), {'id': id})
    animal = [dict(zip([k.lower() for k in animal_res.keys()], row)) for row in animal_res.fetchall()]
    animal = animal[0] if animal else None

    record_res = db.session.execute(text("""
        SELECT m.*, s.F_Name, s.L_Name 
        FROM MEDICAL_RECORD m 
        LEFT JOIN STAFF s ON m.Staff_ID = s.Staff_ID 
        WHERE m.Animal_ID = :id 
        ORDER BY m.Treatment_Date DESC
    """), {'id': id})
    medical_records = [dict(zip([k.lower() for k in record_res.keys()], row)) for row in record_res.fetchall()]
    
    return render_template('medical_records.html', animal=animal, medical_records=medical_records)

@app.route('/admin/medical/<int:id>/delete', methods=['POST'])
def delete_medical_record(id):
    if session.get('role_name') != 'Admin':
        flash("Unauthorized: Admin access required.", "error")
        return redirect(url_for('login'))
        
    try:
        # Fetch Animal_ID for redirection before deletion
        query = text("SELECT Animal_ID FROM MEDICAL_RECORD WHERE Record_ID = :id")
        record = db.session.execute(query, {'id': id}).fetchone()
        
        if not record:
            flash("Medical record not found.", "error")
            return redirect(url_for('dashboard'))
            
        animal_id = record.Animal_ID
        
        db.session.execute(text("DELETE FROM MEDICAL_RECORD WHERE Record_ID = :id"), {'id': id})
        db.session.commit()
        flash("Medical record deleted successfully.", "success")
        return redirect(url_for('view_medical_records', id=animal_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting record: {str(e)}", "error")
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/admin/medical/<int:id>/edit', methods=['POST'])
def edit_medical_record(id):
    if session.get('role_name') != 'Admin':
        flash("Unauthorized: Admin access required.", "error")
        return redirect(url_for('login'))
        
    treatment = request.form.get('treatment')
    treatment_date = request.form.get('treatment_date')
    notes = request.form.get('notes')
    
    try:
        # Fetch Animal_ID for redirection
        query = text("SELECT Animal_ID FROM MEDICAL_RECORD WHERE Record_ID = :id")
        record = db.session.execute(query, {'id': id}).fetchone()
        
        if not record:
            flash("Medical record not found.", "error")
            return redirect(url_for('dashboard'))
            
        animal_id = record.Animal_ID
        
        db.session.execute(text("""
            UPDATE MEDICAL_RECORD 
            SET Treatment = :treatment, Treatment_Date = :date, Notes = :notes 
            WHERE Record_ID = :id
        """), {
            'treatment': treatment,
            'date': treatment_date,
            'notes': notes,
            'id': id
        })
        db.session.commit()
        flash("Medical record updated successfully.", "success")
        return redirect(url_for('view_medical_records', id=animal_id))
    except Exception as e:
        db.session.rollback()
        flash(f"Error updating record: {str(e)}", "error")
        return redirect(request.referrer or url_for('dashboard'))

@app.route('/api/adopters/search')
def search_adopters_api():
    if 'staff_id' not in session: return jsonify([]), 401
    q = request.args.get('q', '')
    if not q: return jsonify([])
    
    term = f"%{q}%"
    res = db.session.execute(text("""
        SELECT Adopter_ID, F_Name, L_Name 
        FROM ADOPTER 
        WHERE F_Name LIKE :term OR L_Name LIKE :term 
        LIMIT 10
    """), {'term': term})
    
    adopters = [dict(zip([k.lower() for k in res.keys()], row)) for row in res.fetchall()]
    return jsonify(adopters)

@app.route('/admin/financials')
def financial_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    rev_res = db.session.execute(text("SELECT SUM(Amount) as total FROM PAYMENT")).fetchone()
    total_revenue = float(rev_res[0]) if rev_res and rev_res[0] else 0.0
    
    pay_res = db.session.execute(text("""
        SELECT p.Payment_ID, p.Amount, p.Payment_Date, ad.F_Name, ad.L_Name, ani.Name as pet_name 
        FROM PAYMENT p 
        JOIN ADOPTION a ON p.Adoption_ID = a.Adoption_ID 
        JOIN ADOPTER ad ON a.Adopter_ID = ad.Adopter_ID 
        JOIN ANIMAL ani ON a.Animal_ID = ani.Animal_ID 
        ORDER BY p.Payment_Date DESC
    """))
    payments = [dict(zip([k.lower() for k in pay_res.keys()], row)) for row in pay_res.fetchall()]
    
    return render_template('financials.html', payments=payments, total_revenue=total_revenue)

@app.route('/admin/adoption/<int:id>/pay', methods=['POST'])
def log_payment(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') not in ['Admin', 'Staff']: return "Unauthorized", 403
    
    amount = request.form.get('amount')
    date = request.form.get('payment_date')
    
    try:
        db.session.execute(text("""
            INSERT INTO PAYMENT (Adoption_ID, Payment_Date, Amount) 
            VALUES (:id, :date, :amount)
        """), {'id': id, 'date': date, 'amount': amount})
        db.session.commit()
        flash("Payment logged successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error logging payment: {e}", "error")
    return redirect(request.referrer)

@app.route('/admin/adoption/<int:id>/return', methods=['POST'])
def return_adoption(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    reason = request.form.get('return_reason')
    date = request.form.get('return_date')
    
    try:
        # Simplified: Single INSERT. Trigger handles Animal/Adoption status updates.
        db.session.execute(text("""
            INSERT INTO AdoptionReturn (Adoption_ID, Return_Date, Return_Reason) 
            VALUES (:id, :date, :reason)
        """), {'id': id, 'date': date, 'reason': reason})
        
        db.session.commit()
        flash("Adoption return processed. Pet availability updated via database trigger.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error processing return: {e}", "error")
    return redirect(request.referrer)

@app.route('/admin/adopter/<int:id>/edit', methods=['GET', 'POST'])
def edit_adopter(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    if request.method == 'POST':
        f_name = request.form.get('f_name')
        l_name = request.form.get('l_name')
        email = request.form.get('email')
        address = request.form.get('address')
        
        try:
            db.session.execute(text("""
                UPDATE ADOPTER 
                SET F_Name = :f, L_Name = :l, Email = :e, Address = :a 
                WHERE Adopter_ID = :id
            """), {'f': f_name, 'l': l_name, 'e': email, 'a': address, 'id': id})
            db.session.commit()
            flash("Adopter profile updated!", "success")
            return redirect(url_for('adopter_profile', id=id))
        except Exception as e:
            db.session.rollback()
            flash(f"Error updating profile: {e}", "error")
            
    adopter = db.session.execute(text("SELECT * FROM ADOPTER WHERE Adopter_ID = :id"), {'id': id}).fetchone()
    return render_template('edit_adopter.html', adopter=adopter)

@app.route('/admin/adopter/<int:id>/add_phone', methods=['POST'])
def add_adopter_phone(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    
    new_phone = request.form.get('phone_number')
    if not new_phone:
        flash("Phone number cannot be empty.", "error")
        return redirect(url_for('adopter_profile', id=id))
        
    try:
        db.session.execute(text("""
            INSERT INTO ADOPTER_PHONE (Adopter_ID, Phone_Number) 
            VALUES (:id, :phone)
        """), {'id': id, 'phone': new_phone.strip()})
        db.session.commit()
        flash("Contact method added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash("Error: Could not add number. It might already exist.", "error")
        
    return redirect(url_for('adopter_profile', id=id))

@app.route('/admin/adopter/<int:id>/remove_photo', methods=['POST'])
def remove_adopter_photo(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    try:
        # Adopter photos are stored in MongoDB, not as a SQL column
        mongo.db.photos.delete_one({'MySQL_ID': id, 'type': 'adopter'})
        flash("Adopter photo removed.", "success")
    except Exception as e:
        flash(f"Error removing photo: {e}", "error")
    return redirect(url_for('adopter_profile', id=id))

@app.route('/admin/adopter/<int:id>/delete', methods=['POST'])
def delete_adopter(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    try:
        # Cascade Delete: Payments -> Returns -> Adoptions -> Adopter
        db.session.execute(text("DELETE FROM PAYMENT WHERE Adoption_ID IN (SELECT Adoption_ID FROM ADOPTION WHERE Adopter_ID = :id)"), {'id': id})
        db.session.execute(text("DELETE FROM AdoptionReturn WHERE Adoption_ID IN (SELECT Adoption_ID FROM ADOPTION WHERE Adopter_ID = :id)"), {'id': id})
        db.session.execute(text("DELETE FROM ADOPTION WHERE Adopter_ID = :id"), {'id': id})
        db.session.execute(text("DELETE FROM ADOPTER_PHONE WHERE Adopter_ID = :id"), {'id': id})
        db.session.execute(text("DELETE FROM ADOPTER WHERE Adopter_ID = :id"), {'id': id})
        
        db.session.commit()
        flash("Adopter and all associated records deleted successfully. Pets reverted to Available.", "success")
        return redirect(url_for('view_adopters'))
    except Exception as e:
        db.session.rollback()
        flash(f"Constraint Error: {e}", "error")
        return redirect(url_for('adopter_profile', id=id))

@app.route('/admin/adopter/<int:id>/delete_phone/<path:phone>', methods=['POST'])
def delete_phone(id, phone):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    
    try:
        db.session.execute(text("DELETE FROM ADOPTER_PHONE WHERE Adopter_ID = :id AND Phone_Number = :phone"), 
                         {'id': id, 'phone': phone})
        db.session.commit()
        flash("Contact method removed.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting phone: {e}", "error")
        
    return redirect(url_for('adopter_profile', id=id))

@app.route('/admin/logs')
def admin_logs():
    return "This section is under maintenance.", 501



@app.route('/delete_image/<entity_type>/<int:entity_id>', methods=['POST'])
def delete_image(entity_type, entity_id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    try:
        # mongo.db.photos.delete_one({'entity_type': entity_type, 'entity_id': entity_id})
        mongo.db.photos.delete_one({'MySQL_ID': entity_id, 'type': entity_type})
        flash("Image deleted.", "success")
    except Exception as e:
        flash(f"Error deleting image: {e}", "error")
    return redirect(request.referrer)


@app.route('/seed_passwords')
def seed_passwords():
    from werkzeug.security import generate_password_hash
    try:
        staff_records = db.session.execute(text("SELECT Staff_ID FROM STAFF")).fetchall()
        
        for staff in staff_records:
            hashed_pw = generate_password_hash('password123')
            mongo.db.credentials.update_one(
                {'staff_id': int(staff.Staff_ID)},
                {'$set': {'password_hash': hashed_pw}},
                upsert=True
            )
            
        return '✅ All passwords safely seeded into MongoDB!'
    except Exception as e:
        return f'❌ Error seeding passwords: {str(e)}'

if __name__ == '__main__':
    app.run(debug=True, port=5000)
