import locale
import re
import io
import bson.binary
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_pymongo import PyMongo
from sqlalchemy import text  

app = Flask(__name__)
# The exact DB URI required by the user
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/pams_db'
app.config['SQLALCHEMY_ECHO'] = True
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'haven_flow_secret' # Needed for flash messages

db = SQLAlchemy(app)

# MongoDB Configuration
app.config['MONGO_URI'] = 'mongodb://localhost:27017/pams_photos'
mongo = PyMongo(app)

# =======================
# MONGODB HELPERS
# =======================
def create_notification(notif_type, message):
    try:
        mongo.db.notifications.insert_one({
            'type': notif_type,
            'message': message,
            'created_at': datetime.now()
        })
    except Exception as e:
        print(f"Error creating notification: {e}")

def log_audit(staff_id, action, entity, details=""):
    try:
        mongo.db.audit_logs.insert_one({
            'staff_id': staff_id,
            'action': action,
            'entity': entity,
            'details': details,
            'created_at': datetime.now()
        })
    except Exception as e:
        print(f"Error logging audit: {e}")


@app.before_request
def require_login():
    allowed_routes = ['login', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'staff_id' not in session:
        return redirect(url_for('login'))

@app.context_processor
def inject_staff():
    if 'staff_id' in session:
        query = text("SELECT * FROM STAFF WHERE Staff_ID = :id")
        staff = db.session.execute(query, {'id': session['staff_id']}).fetchone()
        return dict(current_staff=staff)
    return dict(current_staff=None)

# =======================
# JINJA2 CUSTOM FILTERS
# =======================

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


# =======================
# MONGODB IMAGE ROUTING
# =======================

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return 'Unauthorized', 403
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
        # Convert to BSON Binary
        image_data = bson.binary.Binary(file.read())
        
        # Upsert the image
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

# =======================
# RAW SQL REPORTING ROUTES
# =======================

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
WHERE a.Adoption_Status = 'Available'
GROUP BY s.Species_Name
ORDER BY Available_Count DESC
"""
    result = db.session.execute(db.text(query)).fetchall()
    return render_template('reports.html', report_type='species', data=result, query_text=query.strip())


# =======================
# FLASK ROUTING LOGIC
# =======================

@app.route('/')
def dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    """Main dashboard showing available animals"""
    # Redirect to corresponding dashboard if user is authenticated
    role_name = session.get('role_name')
    if role_name == 'Admin':
        return redirect(url_for('admin_dashboard'))
    elif role_name == 'Staff':
        return redirect(url_for('staff_dashboard'))
        
    try:
        query = text("""
            SELECT a.*, b.Breed_Name, s.Species_Name 
            FROM ANIMAL a
            LEFT JOIN BREED b ON a.Breed_ID = b.Breed_ID
            LEFT JOIN SPECIES s ON b.Species_ID = s.Species_ID
            WHERE a.Adoption_Status = 'Available'
        """)
        available_animals = db.session.execute(query).fetchall()
    except Exception as e:
        available_animals = []
    return render_template('dashboard.html', animals=available_animals)

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    # Hard check for 'Admin' role
    if session.get('role_name') != 'Admin':
        return "Unauthorized", 403
        
    try:
        pets_q = text("""
            SELECT a.*, b.Breed_Name, s.Species_Name 
            FROM ANIMAL a
            LEFT JOIN BREED b ON a.Breed_ID = b.Breed_ID
            LEFT JOIN SPECIES s ON b.Species_ID = s.Species_ID
            LIMIT 50
        """)
        pets = db.session.execute(pets_q).fetchall()
        
        # Admin view integration for adoption requests
        adoptions_q = text("SELECT * FROM view_admin_adoptions LIMIT 50")
        adoptions = db.session.execute(adoptions_q).fetchall()
        
        staff_q = text("""
            SELECT s.*, r.Role_Name 
            FROM STAFF s
            LEFT JOIN ROLE r ON s.Role_ID = r.Role_ID
            LIMIT 50
        """)
        staff_list = db.session.execute(staff_q).fetchall()
    except Exception as e:
        pets, adoptions, staff_list = [], [], []
        
    return render_template('admin_dashboard.html', pets=pets, adoptions=adoptions, staff_list=staff_list)

@app.route('/staff/dashboard')
def staff_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    # Hard check for 'Staff' role
    if session.get('role_name') != 'Staff':
        return "Unauthorized", 403
        
    try:
        # Staff view integration for operational pet listing
        pets_q = text("SELECT * FROM view_staff_pets LIMIT 50")
        pets = db.session.execute(pets_q).fetchall()
    except Exception as e:
        pets = []
        
    return render_template('staff_dashboard.html', pets=pets)

@app.route('/animal/delete/<int:id>', methods=['POST'])
def delete_animal(id):
    # Action route security check - Placed directly at the top
    if session.get('role_name') != 'Admin':
        return "Unauthorized", 403
    
    try:
        db.session.execute(text("DELETE FROM ANIMAL WHERE Animal_ID = :id"), {'id': id})
        db.session.commit()
        log_audit(session.get('staff_id'), 'delete_animal', 'animal', f"Deleted animal ID {id}")
        create_notification('system', f"Animal ID {id} was permanently deleted by admin.")
        flash("Animal deleted successfully.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting animal: {str(e)}", "error")
    return redirect(url_for('admin_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
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
                session['staff_id'] = getattr(staff, 'Staff_ID', staff_id) 
                # Store the role name securely into the session payload
                session['role_name'] = getattr(staff, 'Role_Name', None)
                
                flash(f"Welcome back, {staff.F_Name}!", "success")
                log_audit(staff_id, 'login', 'staff', f"Staff logged in as {session['role_name']}")
                
                # Role-Based Routing Core Switchboard Logic
                if session['role_name'] == 'Admin':
                    return redirect(url_for('admin_dashboard'))
                elif session['role_name'] == 'Staff':
                    return redirect(url_for('staff_dashboard'))
                else:
                    return redirect(url_for('dashboard')) # Fallback
            else:
                flash("Invalid Staff ID.", "error")
        except (ValueError, TypeError):
            flash("Staff ID must be a number.", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    staff_id = session.get('staff_id')
    if staff_id:
        log_audit(staff_id, 'logout', 'staff', 'Staff logged out')
    session.pop('staff_id', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/profile')
def profile():
    if 'staff_id' not in session: return redirect(url_for('login'))
    return render_template('staff_profile.html')

@app.route('/medical/dashboard')
def medical_dashboard():
    if 'staff_id' not in session: return redirect(url_for('login'))
    thresh_date = datetime.now().date() - timedelta(days=180)
    query = text("""
        SELECT a.*, m.Treatment as last_treatment_name, m.Treatment_Date as last_treatment_date
        FROM ANIMAL a
        LEFT JOIN (
            SELECT Animal_ID, MAX(Treatment_Date) as max_date
            FROM MEDICAL_RECORD
            GROUP BY Animal_ID
        ) last_date ON a.Animal_ID = last_date.Animal_ID
        LEFT JOIN MEDICAL_RECORD m ON a.Animal_ID = m.Animal_ID AND m.Treatment_Date = last_date.max_date
        WHERE last_date.max_date IS NULL OR last_date.max_date < :thresh_date
    """)
    animals_needing_followup = db.session.execute(query, {'thresh_date': thresh_date}).fetchall()
    return render_template('medical_dashboard.html', animals=animals_needing_followup)

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
            
            log_audit(session.get('staff_id'), 'add_medical_record', 'medical_record', f'Added treatment for Animal {animal_id}')
            create_notification('medical', f'New medical record added for Animal ID {animal_id}')
            
            flash('Medical record added successfully.', 'success')
            return redirect(url_for('animal_profile', id=animal_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding record: {str(e)}', 'error')
            
    try:
        animals = db.session.execute(text("SELECT * FROM ANIMAL")).fetchall()
    except:
        animals = []
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
        dob = request.form.get('dob')
        breed_id = request.form.get('breed_id')
        
        try:
            insert_query = text("""
                INSERT INTO ANIMAL (Name, Gender, DateOfBirth, Adoption_Status, Breed_ID)
                VALUES (:name, :gender, :dob, 'Available', :breed_id)
            """)
            db.session.execute(insert_query, {
                'name': name,
                'gender': gender,
                'dob': datetime.strptime(dob, '%Y-%m-%d').date() if dob else None,
                'breed_id': int(breed_id) if breed_id else None
            })
            db.session.commit()
            
            log_audit(session.get('staff_id'), 'add_animal', 'animal', f"Added animal '{name}'")
            create_notification('system', f"New animal added to shelter: {name}")
            
            flash(f"Animal '{name}' successfully added!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding animal: {str(e)}", "error")
    
    breeds = []
    try:
        breeds = db.session.execute(text("SELECT * FROM BREED")).fetchall()
    except:
        pass
    
    return render_template('add_animal.html', breeds=breeds)

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
            
            log_audit(session.get('staff_id'), 'register_adopter', 'adopter', f"Registered {f_name} {l_name}")
            create_notification('adoption', f"New adopter registered: {f_name} {l_name}")
            
            flash("Adopter registered successfully!", "success")
            if adopter_id:
                return redirect(url_for('adopter_profile', id=adopter_id))
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error registering adopter: {str(e)}", "error")
            
    return render_template('register_adopter.html')

@app.route('/animal/<int:id>')
def animal_profile(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    animal = db.session.execute(text("""
        SELECT a.*, b.Breed_Name, s.Species_Name
        FROM ANIMAL a
        LEFT JOIN BREED b ON a.Breed_ID = b.Breed_ID
        LEFT JOIN SPECIES s ON b.Species_ID = s.Species_ID
        WHERE a.Animal_ID = :id
    """), {'id': id}).fetchone()
    
    if not animal:
        flash("Animal not found.", "error")
        return redirect(url_for('dashboard'))
        
    medical_records = db.session.execute(text("SELECT * FROM MEDICAL_RECORD WHERE Animal_ID = :id ORDER BY Treatment_Date DESC"), {'id': id}).fetchall()
    
    adoptions = db.session.execute(text("""
        SELECT ad.*, a.F_Name, a.L_Name 
        FROM ADOPTION ad
        JOIN ADOPTER a ON ad.Adopter_ID = a.Adopter_ID
        WHERE ad.Animal_ID = :id
    """), {'id': id}).fetchall()

    return render_template('animal_profile.html', animal=animal, medical_records=medical_records, adoptions=adoptions)

@app.route('/adopter/<int:id>')
def adopter_profile(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    adopter = db.session.execute(text("SELECT * FROM ADOPTER WHERE Adopter_ID = :id"), {'id': id}).fetchone()
    
    if not adopter:
        flash("Adopter not found.", "error")
        return redirect(url_for('dashboard'))
        
    phones_data = db.session.execute(text("SELECT Phone_Number FROM ADOPTER_PHONE WHERE Adopter_ID = :id"), {'id': id}).fetchall()
    phones = [p.Phone_Number for p in phones_data]
    
    adoptions = db.session.execute(text("""
        SELECT ad.*, a.Name as Animal_Name 
        FROM ADOPTION ad
        JOIN ANIMAL a ON ad.Animal_ID = a.Animal_ID
        WHERE ad.Adopter_ID = :id
    """), {'id': id}).fetchall()
    
    total_fees = sum([float(a.Fee or 0) for a in adoptions])
    
    return render_template('adopter_profile.html', adopter=adopter, phones=phones, adoptions=adoptions, total_fees=total_fees)

@app.route('/notifications')
def notifications():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return 'Unauthorized', 403
    try:
        notifs = list(mongo.db.notifications.find().sort("created_at", -1).limit(50))
    except Exception:
        notifs = []
    return render_template('notifications.html', notifications=notifs)

@app.route('/audit-logs')
def audit_logs():
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return 'Unauthorized', 403
    try:
        logs = list(mongo.db.audit_logs.find().sort("created_at", -1).limit(50))
    except Exception:
        logs = []
        
    enriched_logs = []
    for log in logs:
        staff_name = "Unknown"
        s_id = log.get('staff_id')
        if s_id:
            try:
                staff = db.session.execute(text("SELECT F_Name, L_Name FROM STAFF WHERE Staff_ID = :id"), {'id': s_id}).fetchone()
                if staff:
                    staff_name = f"{staff.F_Name} {staff.L_Name}"
            except Exception:
                pass
        
        enriched_logs.append({
            'created_at': log.get('created_at'),
            'action': log.get('action'),
            'entity': log.get('entity'),
            'details': log.get('details'),
            'staff_name': staff_name
        })
        
    return render_template('audit_logs.html', logs=enriched_logs)


@app.route('/delete_image/<entity_type>/<int:entity_id>', methods=['POST'])
def delete_image(entity_type, entity_id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') != 'Admin': return "Unauthorized", 403
    try:
        # User requested specific schema: entity_type and entity_id
        mongo.db.photos.delete_one({'entity_type': entity_type, 'entity_id': entity_id})
        # Note: Also keeping the previous MySQL_ID/type check just in case of schema legacy
        mongo.db.photos.delete_one({'MySQL_ID': entity_id, 'type': entity_type})
        
        flash("Image deleted.", "success")
        log_audit(session.get('staff_id'), 'delete_image', entity_type, f"Deleted image for {entity_type} {entity_id}")
    except Exception as e:
        flash(f"Error deleting image: {e}", "error")
    return redirect(request.referrer)

@app.route('/adoption/accept/<int:id>', methods=['POST'])
def accept_adoption(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') not in ['Admin', 'Staff']: return "Unauthorized", 403
    try:
        db.session.execute(text("UPDATE ANIMAL SET Adoption_Status = 'Processing' WHERE Animal_ID = (SELECT Animal_ID FROM ADOPTION WHERE Adoption_ID = :id)"), {'id': id})
        db.session.commit()
        flash("Adoption accepted and pet status set to Processing.", "success")
        log_audit(session.get('staff_id'), 'accept_adoption', 'adoption', f"Accepted adoption ID {id}")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(request.referrer)

@app.route('/adoption/reject/<int:id>', methods=['POST'])
def reject_adoption(id):
    if 'staff_id' not in session: return redirect(url_for('login'))
    if session.get('role_name') not in ['Admin', 'Staff']: return "Unauthorized", 403
    try:
        # User requested update instead of delete. Use status markers.
        db.session.execute(text("UPDATE ADOPTION SET Status = 'Rejected' WHERE Adoption_ID = :id"), {'id': id})
        db.session.execute(text("UPDATE ANIMAL SET Adoption_Status = 'Available' WHERE Animal_ID = (SELECT Animal_ID FROM ADOPTION WHERE Adoption_ID = :id)"), {'id': id})
        db.session.commit()
        flash("Adoption request rejected and pet set back to available.", "success")
        log_audit(session.get('staff_id'), 'reject_adoption', 'adoption', f"Rejected adoption ID {id}")
    except Exception as e:
        db.session.rollback()
        flash(f"Error: {e}", "error")
    return redirect(request.referrer)

if __name__ == '__main__':
    # Start local flask server on port 5000
    app.run(debug=True, port=5000)
