import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# --- INITIAL SETUP ---
base_dir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(base_dir, 'templates')

app = Flask(__name__, template_folder=template_dir)
app.secret_key = "super-secret-key-maputo-2024"

# Ensure database directory exists
instance_path = os.path.join(base_dir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'repairs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- DATABASE MODELS ---

class Technician(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Repair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='NEW') # NEW, PENDING, APPROVED, RETURNED
    technician_id = db.Column(db.Integer, db.ForeignKey('technician.id'), nullable=True)
    technician = db.relationship('Technician', backref='repairs')
    quote_date = db.Column(db.DateTime, nullable=True)
    decision_date = db.Column(db.DateTime, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.now)
    delay_until = db.Column(db.DateTime, nullable=True)

# --- JINJA FILTERS (UI HELPERS) ---

@app.template_filter('format_dt')
def format_dt(value):
    if not value: return ""
    return value.strftime('%d/%m/%Y %H:%M')

@app.template_filter('time_ago')
def time_ago(dt):
    if not dt: return ""
    diff = datetime.now() - dt
    if diff.days > 0: return f"(Há {diff.days} dias)"
    minutes = diff.seconds // 60
    if minutes < 1: return "(agora mesmo)"
    if minutes < 60: return f"(Há {minutes} min)"
    return f"(Há {diff.seconds // 3600} horas)"

@app.context_processor
def utility_processor():
    def needs_cleanup(repair):
        if repair.status not in ['APPROVED', 'RETURNED'] or not repair.decision_date: return False
        # Check if 90 days passed
        over_90 = datetime.now() > (repair.decision_date + timedelta(days=90))
        # Check if 30-day snooze is active
        not_delayed = repair.delay_until is None or datetime.now() > repair.delay_until
        return over_90 and not_delayed
    return dict(needs_cleanup=needs_cleanup)

# --- ROUTES ---

@app.route('/')
def index():
    search_query = request.args.get('s', '').strip()
    query = Repair.query
    
    if search_query:
        # Search in Equipment Description OR Technician Name
        query = query.join(Technician, isouter=True).filter(
            db.or_(
                Repair.description.contains(search_query.upper()),
                Technician.name.contains(search_query)
            )
        )
    
    repairs = query.order_by(Repair.last_updated.desc()).all()
    techs = Technician.query.order_by(Technician.name).all()
    return render_template('index.html', repairs=repairs, techs=techs, search_query=search_query)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == 'admin':
            session['logged_in'] = True
            return redirect(url_for('index'))
        flash('Credenciais Inválidas')
    
    # OPTION 1: Inline HTML to prevent "Internal Server Error"
    return '''
    <!DOCTYPE html>
    <html lang="pt">
    <head>
        <meta charset="UTF-8"><title>Login - Repair Manager</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-slate-900 flex items-center justify-center h-screen font-sans">
        <div class="bg-white p-10 rounded-2xl shadow-2xl w-96 border-t-8 border-blue-600">
            <h2 class="text-2xl font-black text-slate-800 text-center mb-6 uppercase tracking-tighter italic">Admin Access</h2>
            <form method="POST">
                <div class="mb-4">
                    <label class="block text-[10px] font-black uppercase text-slate-400 mb-1">Usuário</label>
                    <input type="text" name="username" class="w-full border-2 border-slate-200 p-3 rounded-lg outline-none focus:border-blue-500 font-bold" required autofocus>
                </div>
                <div class="mb-6">
                    <label class="block text-[10px] font-black uppercase text-slate-400 mb-1">Senha</label>
                    <input type="password" name="password" class="w-full border-2 border-slate-200 p-3 rounded-lg outline-none focus:border-blue-500 font-bold" required>
                </div>
                <button type="submit" class="w-full bg-blue-600 text-white p-4 rounded-xl font-black uppercase text-sm hover:bg-blue-700 transition shadow-lg">Entrar</button>
            </form>
            <div class="mt-6 text-center"><a href="/" class="text-[10px] font-bold text-slate-400 uppercase hover:text-slate-600 underline">Sair</a></div>
        </div>
    </body>
    </html>
    '''

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add():
    if not session.get('logged_in'): return redirect(url_for('index'))
    desc = request.form.get('description')
    tech_id = request.form.get('tech_id')
    if desc:
        new_repair = Repair(
            description=desc.upper(), 
            technician_id=tech_id if tech_id != "" else None,
            last_updated=datetime.now()
        )
        db.session.add(new_repair)
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/reassign/<int:id>', methods=['POST'])
def reassign(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    repair = Repair.query.get(id)
    tech_id = request.form.get('tech_id')
    repair.technician_id = tech_id if tech_id != "" else None
    repair.last_updated = datetime.now()
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/update/<int:id>/<action>')
def update(id, action):
    if not session.get('logged_in'): return redirect(url_for('index'))
    repair = Repair.query.get(id)
    repair.last_updated = datetime.now()
    
    if action == 'quote':
        repair.status = 'PENDING'
        repair.quote_date = datetime.now()
    elif action == 'approve':
        repair.status = 'APPROVED'
        repair.decision_date = datetime.now()
    elif action == 'return':
        repair.status = 'RETURNED'
        repair.decision_date = datetime.now()
    elif action == 'delete':
        db.session.delete(repair)
    elif action == 'deny_removal':
        repair.delay_until = datetime.now() + timedelta(days=30)
        
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/manage', methods=['POST'])
def add_tech():
    if not session.get('logged_in'): return redirect(url_for('index'))
    name = request.form.get('tech_name')
    if name:
        db.session.add(Technician(name=name))
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/delete/<int:id>')
def delete_tech(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    tech = Technician.query.get(id)
    db.session.delete(tech)
    db.session.commit()
    return redirect(url_for('index'))

# API for auto-refresh
@app.route('/api/last_update')
def last_update():
    latest = Repair.query.order_by(Repair.last_updated.desc()).first()
    return jsonify({"timestamp": latest.last_updated.timestamp() if latest else 0})

# --- START APP ---

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Seed initial technician list
        if Technician.query.count() == 0:
            for n in ["Homo", "Willard", "Madeline", "Reginaldo", "Dinis"]:
                db.session.add(Technician(name=n))
            db.session.commit()
    app.run(host='0.0.0.0', port=5000)
