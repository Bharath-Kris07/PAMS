import locale
import re
import io
import bson.binary
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_pymongo import PyMongo
from sqlalchemy.orm import joinedload

app = Flask(__name__)
# The exact DB URI required by the user
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/pams_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'haven_flow_secret' # Needed for flash messages

db = SQLAlchemy(app)

# MongoDB Configuration
app.config['MONGO_URI'] = 'mongodb://localhost:27017/pams_photos'
mongo = PyMongo(app)

@app.before_request
def require_login():
    allowed_routes = ['login', 'static']
    if request.endpoint and request.endpoint not in allowed_routes and 'staff_id' not in session:
        return redirect(url_for('login'))

@app.context_processor
def inject_staff():
    if 'staff_id' in session:
        staff = Staff.query.get(session['staff_id'])
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
# SQLALCHEMY ORM MODELS
# =======================

class Species(db.Model):
    __tablename__ = 'SPECIES'
    Species_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Species_Name = db.Column(db.String(50), nullable=False)
    breeds = db.relationship('Breed', backref='species', lazy=True)

class Role(db.Model):
    __tablename__ = 'ROLE'
    Role_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Role_Name = db.Column(db.String(50), nullable=False)
    staff = db.relationship('Staff', backref='role', lazy=True)

class Breed(db.Model):
    __tablename__ = 'BREED'
    Breed_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Breed_Name = db.Column(db.String(50), nullable=False)
    Species_ID = db.Column(db.Integer, db.ForeignKey('SPECIES.Species_ID'))
    animals = db.relationship('Animal', backref='breed', lazy=True)

class Staff(db.Model):
    __tablename__ = 'STAFF'
    Staff_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    F_Name = db.Column(db.String(50), nullable=False)
    L_Name = db.Column(db.String(50), nullable=False)
    Role_ID = db.Column(db.Integer, db.ForeignKey('ROLE.Role_ID'))

class Adopter(db.Model):
    __tablename__ = 'ADOPTER'
    Adopter_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    F_Name = db.Column(db.String(50), nullable=False)
    L_Name = db.Column(db.String(50), nullable=False)
    Email = db.Column(db.String(100), unique=True, nullable=False)
    Address = db.Column(db.String(255))
    phones = db.relationship('AdopterPhone', backref='adopter', lazy=True, cascade='all, delete-orphan')
    adoptions = db.relationship('Adoption', backref='adopter', lazy=True)

class AdopterPhone(db.Model):
    __tablename__ = 'ADOPTER_PHONE'
    Phone_Number = db.Column(db.String(15), primary_key=True)
    Adopter_ID = db.Column(db.Integer, db.ForeignKey('ADOPTER.Adopter_ID', ondelete='CASCADE'), primary_key=True)

class Animal(db.Model):
    __tablename__ = 'ANIMAL'
    Animal_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.String(50), nullable=False)
    Gender = db.Column(db.String(10))
    DateOfBirth = db.Column(db.Date)
    Adoption_Status = db.Column(db.String(20), default='Available')
    Breed_ID = db.Column(db.Integer, db.ForeignKey('BREED.Breed_ID'))
    medical_records = db.relationship('MedicalRecord', backref='animal', lazy=True)
    adoptions = db.relationship('Adoption', backref='animal', lazy=True)

class MedicalRecord(db.Model):
    __tablename__ = 'MEDICAL_RECORD'
    Record_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Treatment = db.Column(db.String(255), nullable=False)
    Treatment_Date = db.Column(db.Date)
    Notes = db.Column(db.Text)
    Animal_ID = db.Column(db.Integer, db.ForeignKey('ANIMAL.Animal_ID'))
    Staff_ID = db.Column(db.Integer, db.ForeignKey('STAFF.Staff_ID'))

class Adoption(db.Model):
    __tablename__ = 'ADOPTION'
    Adoption_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Adoption_Date = db.Column(db.Date, nullable=False)
    Fee = db.Column(db.Numeric(10, 2))
    Adopter_ID = db.Column(db.Integer, db.ForeignKey('ADOPTER.Adopter_ID'))
    Animal_ID = db.Column(db.Integer, db.ForeignKey('ANIMAL.Animal_ID'))
    Staff_ID = db.Column(db.Integer, db.ForeignKey('STAFF.Staff_ID'))
    payments = db.relationship('Payment', backref='adoption', lazy=True)
    returned = db.relationship('AdoptionReturn', backref='adoption', uselist=False, lazy=True)

class Payment(db.Model):
    __tablename__ = 'PAYMENT'
    Payment_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Amount = db.Column(db.Numeric(10, 2), nullable=False)
    Payment_Date = db.Column(db.Date, nullable=False)
    Adoption_ID = db.Column(db.Integer, db.ForeignKey('ADOPTION.Adoption_ID'))

class AdoptionReturn(db.Model):
    __tablename__ = 'ADOPTION_RETURN'
    Return_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Return_Date = db.Column(db.Date, nullable=False)
    Return_Reason = db.Column(db.Text)
    Adoption_ID = db.Column(db.Integer, db.ForeignKey('ADOPTION.Adoption_ID'), unique=True)


# =======================
# MONGODB IMAGE ROUTING
# =======================

@app.route('/upload_image', methods=['POST'])
def upload_image():
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
    """Main dashboard showing available animals"""
    try:
        # We perform a try block so it won't crash if DB isn't running in our sandbox
        available_animals = Animal.query.options(joinedload(Animal.breed).joinedload(Breed.species)).filter_by(Adoption_Status='Available').all()
    except Exception:
        available_animals = []
    return render_template('dashboard.html', animals=available_animals)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        staff_id = request.form.get('staff_id')
        try:
            staff_id = int(staff_id)
            staff = Staff.query.get(staff_id)
            if staff:
                session['staff_id'] = staff.Staff_ID
                flash(f"Welcome back, {staff.F_Name}!", "success")
                return redirect(url_for('dashboard'))
            else:
                flash("Invalid Staff ID.", "error")
        except (ValueError, TypeError):
            flash("Staff ID must be a number.", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('staff_id', None)
    flash("You have been logged out.", "success")
    return redirect(url_for('login'))

@app.route('/profile')
def profile():
    return render_template('staff_profile.html')

@app.route('/medical/dashboard')
def medical_dashboard():
    # Identify animals whose latest treatment is > 180 days ago, or who have no treatments.
    thresh_date = datetime.now().date() - timedelta(days=180)
    
    # Subquery for latest treatment date
    subq = db.session.query(
        MedicalRecord.Animal_ID,
        db.func.max(MedicalRecord.Treatment_Date).label('last_treatment')
    ).group_by(MedicalRecord.Animal_ID).subquery()
    
    animals_needing_followup = db.session.query(Animal).outerjoin(
        subq, Animal.Animal_ID == subq.c.Animal_ID
    ).filter(
        db.or_(
            subq.c.last_treatment == None,
            subq.c.last_treatment < thresh_date
        )
    ).all()
    
    return render_template('medical_dashboard.html', animals=animals_needing_followup)

@app.route('/medical/add', methods=['GET', 'POST'])
def add_medical_record():
    if request.method == 'POST':
        animal_id = request.form.get('animal_id')
        treatment = request.form.get('treatment')
        treatment_date = request.form.get('treatment_date')
        notes = request.form.get('notes')
        
        try:
            new_record = MedicalRecord(
                Animal_ID=int(animal_id),
                Treatment=treatment,
                Treatment_Date=datetime.strptime(treatment_date, '%Y-%m-%d').date() if treatment_date else None,
                Notes=notes,
                Staff_ID=session.get('staff_id')
            )
            db.session.add(new_record)
            db.session.commit()
            flash('Medical record added successfully.', 'success')
            return redirect(url_for('animal_profile', id=animal_id))
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding record: {str(e)}', 'error')
            
    animals = Animal.query.all()
    return render_template('add_medical_record.html', animals=animals)

@app.route('/analytics/revenue')
def revenue_dashboard():
    total_revenue = db.session.query(db.func.sum(Payment.Amount)).scalar() or 0
    
    # Pending Dues: Adoption Fee > sum of payments
    pending_dues = db.session.query(
        Adoption,
        db.func.coalesce(db.func.sum(Payment.Amount), 0).label('paid_amount')
    ).outerjoin(Payment, Adoption.Adoption_ID == Payment.Adoption_ID)\
     .group_by(Adoption.Adoption_ID)\
     .having(db.func.coalesce(db.func.sum(Payment.Amount), 0) < Adoption.Fee)\
     .all()

    recent_payments = Payment.query.order_by(Payment.Payment_Date.desc()).limit(10).all()
     
    return render_template('revenue_dashboard.html', 
                          total_revenue=total_revenue, 
                          pending_dues=pending_dues, 
                          recent_payments=recent_payments)

@app.route('/animal/add', methods=['GET', 'POST'])
def add_animal():
    if request.method == 'POST':
        name = request.form.get('name')
        gender = request.form.get('gender')
        dob = request.form.get('dob') # Ensure frontend sends YYYY-MM-DD
        breed_id = request.form.get('breed_id')
        
        try:
            new_animal = Animal(
                Name=name,
                Gender=gender,
                DateOfBirth=datetime.strptime(dob, '%Y-%m-%d').date() if dob else None,
                Breed_ID=int(breed_id) if breed_id else None,
                Adoption_Status='Available'
            )
            db.session.add(new_animal)
            db.session.commit()
            flash(f"Animal '{name}' successfully added!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error adding animal: {str(e)}", "error")
    
    # Query breeds for the dropdown
    breeds = []
    try:
        breeds = Breed.query.all()
    except:
        pass
    
    return render_template('add_animal.html', breeds=breeds)

@app.route('/adopter/register', methods=['GET', 'POST'])
def register_adopter():
    if request.method == 'POST':
        f_name = request.form.get('f_name')
        l_name = request.form.get('l_name')
        email = request.form.get('email')
        address = request.form.get('address')
        phone = request.form.get('phone') # Capture primary phone directly
        
        try:
            # Create adopter
            new_adopter = Adopter(
                F_Name=f_name, 
                L_Name=l_name, 
                Email=email, 
                Address=address
            )
            db.session.add(new_adopter)
            # Flush to get Adopter_ID
            db.session.flush()
            
            # Add phone number
            if phone:
                new_phone = AdopterPhone(Phone_Number=phone, Adopter_ID=new_adopter.Adopter_ID)
                db.session.add(new_phone)
                
            db.session.commit()
            flash("Adopter registered successfully!", "success")
            return redirect(url_for('adopter_profile', id=new_adopter.Adopter_ID))
        except Exception as e:
            db.session.rollback()
            flash(f"Error registering adopter: {str(e)}", "error")
            
    return render_template('register_adopter.html')

@app.route('/animal/<int:id>')
def animal_profile(id):
    animal = Animal.query.get_or_404(id)
    return render_template('animal_profile.html', animal=animal)

@app.route('/adopter/<int:id>')
def adopter_profile(id):
    adopter = Adopter.query.get_or_404(id)
    
    # Optional logic: total adoption fees the adopter paid across all adoptions
    total_fees = sum([float(a.Fee or 0) for a in adopter.adoptions])
    
    return render_template('adopter_profile.html', adopter=adopter, total_fees=total_fees)


if __name__ == '__main__':
    # Start local flask server on port 5000
    app.run(debug=True, port=5000)
