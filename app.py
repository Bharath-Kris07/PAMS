import locale
import re
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# The exact DB URI required by the user
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+mysqlconnector://root:@localhost/pams_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'haven_flow_secret' # Needed for flash messages

db = SQLAlchemy(app)

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
# FLASK ROUTING LOGIC
# =======================

@app.route('/')
def dashboard():
    """Main dashboard showing available animals"""
    try:
        # We perform a try block so it won't crash if DB isn't running in our sandbox
        available_animals = Animal.query.filter_by(Adoption_Status='Available').all()
    except Exception:
        available_animals = []
    return render_template('dashboard.html', animals=available_animals)

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
