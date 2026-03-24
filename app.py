import os
from flask import Flask, request, redirect, url_for, session, flash, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect
from datetime import datetime, timedelta

# --- INITIAL SETUP ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, static_folder='static')
app.secret_key = "maputo-repair-system-v2.5-readytime"

instance_path = os.path.join(base_dir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'repairs.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MODELS ---
class Technician(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Repair(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(500), nullable=False)
    status = db.Column(db.String(50), default='NEW') 
    is_ready = db.Column(db.Boolean, default=False)
    ready_date = db.Column(db.DateTime, nullable=True) # NEW: When it was marked ready
    technician_id = db.Column(db.Integer, db.ForeignKey('technician.id'), nullable=True)
    technician = db.relationship('Technician', backref='repairs')
    quote_date = db.Column(db.DateTime, nullable=True)
    decision_date = db.Column(db.DateTime, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.now)
    delay_until = db.Column(db.DateTime, nullable=True)

# --- JINJA FILTERS ---
@app.template_filter('format_dt')
def format_dt(value):
    if not value: return ""
    return value.strftime('%d/%m/%Y %H:%M')

@app.template_filter('time_ago')
def time_ago(dt):
    if not dt: return ""
    diff = datetime.now() - dt
    if diff.days > 0: return f"(Há {diff.days} dias)"
    if (diff.seconds // 60) < 60: return f"(Há {diff.seconds // 60} min)"
    return f"(Há {diff.seconds // 3600} horas)"

@app.context_processor
def utility_processor():
    def get_cleanup_info(repair):
        if repair.status not in ['APPROVED', 'RETURNED'] or not repair.decision_date:
            return None
        target_date = repair.decision_date + timedelta(days=90)
        if repair.delay_until and repair.delay_until > datetime.now():
            target_date = repair.delay_until
        remaining = target_date - datetime.now()
        return {"days_left": remaining.days, "is_expired": remaining.days <= 0}
    return dict(get_cleanup_info=get_cleanup_info)

# --- HTML TEMPLATE ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8">
    <title>Repair Manager - Maputo</title>
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon.png') }}">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>table {width:100%; border-collapse:collapse;} th,td {border:1px solid #cbd5e1; padding:15px; vertical-align:top; width:33.33%;} .bg-custom {background-color:#f8fafc;}</style>
</head>
<body class="bg-slate-200 p-4 font-sans text-slate-900">
    <div class="max-w-7xl mx-auto bg-white shadow-2xl rounded-xl overflow-hidden border">
        
        <!-- HEADER -->
        <div class="p-5 bg-slate-900 text-white flex justify-between items-center">
            <div class="flex items-center gap-4">
                <img src="{{ url_for('static', filename='favicon.png') }}" class="w-12 h-12">
                <div>
                    <h1 class="text-2xl font-black italic tracking-tighter leading-none uppercase">Repair Manager</h1>
                    <p class="text-[10px] text-slate-400 font-bold uppercase mt-1 tracking-widest">Maputo, Moçambique</p>
                </div>
            </div>
            <div class="flex items-center gap-3">
                {% if session.get('logged_in') %}
                    <button onclick="document.getElementById('m').classList.toggle('hidden')" class="text-[10px] bg-slate-700 px-3 py-1.5 rounded font-bold uppercase transition hover:bg-slate-600">Técnicos</button>
                    <span class="text-emerald-400 text-[10px] font-black border border-emerald-400 px-2 rounded uppercase tracking-wider">Admin</span>
                    <a href="/logout" class="bg-rose-600 px-4 py-1.5 rounded text-[10px] font-black uppercase hover:bg-rose-700 transition">Sair</a>
                {% else %}
                    <a href="/login" class="bg-blue-600 px-6 py-2 rounded text-xs font-black uppercase hover:bg-blue-700 transition">Login Admin</a>
                {% endif %}
            </div>
        </div>

        <!-- SEARCH BAR -->
        <div class="p-4 bg-slate-100 border-b flex justify-between items-center">
            <form action="/" method="GET" class="flex max-w-md gap-2">
                <input type="text" name="s" value="{{ s }}" placeholder="🔍 Pesquisar..." class="p-2 text-sm border-2 rounded-lg outline-none uppercase font-bold focus:border-blue-500 w-80">
                <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded-lg text-xs font-bold uppercase hover:bg-black transition">Buscar</button>
                {% if s %}<a href="/" class="bg-slate-300 text-slate-700 px-4 py-2 rounded-lg text-xs font-bold uppercase flex items-center">Limpar</a>{% endif %}
            </form>
            {% if not session.get('logged_in') %}<div class="text-[9px] text-slate-400 font-bold uppercase italic animate-pulse">Monitoramento Ativo</div>{% endif %}
        </div>

        <!-- ADMIN ADD PANEL -->
        {% if session.get('logged_in') %}
        <div class="p-4 border-b bg-slate-50">
            <form action="/add" method="POST" class="flex gap-2">
                <input type="text" name="desc" placeholder="EQUIPAMENTO..." class="flex-1 border-2 p-3 rounded-lg text-sm font-bold uppercase outline-none focus:border-blue-500" required>
                <select name="t_id" class="border-2 p-3 rounded-lg text-xs font-bold bg-white">
                    <option value="">Técnico (Opcional)</option>
                    {% for t in techs %}<option value="{{t.id}}">{{t.name}}</option>{% endfor %}
                </select>
                <button type="submit" class="bg-blue-600 text-white px-8 py-3 rounded-lg font-black uppercase text-xs hover:bg-blue-700 transition">Registar</button>
            </form>
        </div>
        <div id="m" class="hidden p-4 bg-slate-100 border-b">
            <div class="flex flex-wrap gap-2 mb-4">
                {% for t in techs %}<span class="bg-white border-2 px-3 py-1 rounded-full text-[10px] font-bold">{{t.name}} <a href="/tech/delete/{{t.id}}" class="text-rose-500 ml-1 font-black">×</a></span>{% endfor %}
            </div>
            <form action="/tech/manage" method="POST" class="flex gap-2">
                <input type="text" name="n" placeholder="Novo técnico..." class="border p-2 text-xs rounded-lg w-48"><button type="submit" class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-[10px] font-bold uppercase hover:bg-emerald-700 transition">+ Adicionar</button>
            </form>
        </div>
        {% endif %}

        <!-- MAIN TABLE -->
        <table class="w-full">
            <thead class="bg-slate-50 text-[11px] font-black text-slate-500 uppercase tracking-widest"><tr><th class="p-5 text-left">1. ENTRADA (NOVO)</th><th class="p-5 text-left">2. PENDENTE</th><th class="p-5 text-left">3. FINALIZADO</th></tr></thead>
            <tbody>
                {% for r in repairs %}
                <tr class="{{ 'bg-custom' if loop.index is even }} border-b border-slate-100">
                    <td>
                        <div class="font-black text-slate-800 text-lg leading-tight">{{ r.description }}</div>
                        <div class="text-[9px] text-slate-400 mt-1 mb-2 font-bold uppercase tracking-widest italic border-b pb-1">Entrada {{ r.last_updated | format_dt }}</div>
                        
                        <!-- PRONTO (READY) UI -->
                        <div class="mb-4">
                            {% if not session.get('logged_in') %}
                                <a href="/toggle_ready/{{r.id}}" class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border-2 transition-all shadow-sm {{ 'bg-emerald-100 border-emerald-500 text-emerald-800' if r.is_ready else 'bg-slate-50 border-slate-300 text-slate-400' }}">
                                    <span class="text-[10px] font-black uppercase tracking-tighter">{{ '✓ PRONTO' if r.is_ready else '☐ MARCAR PRONTO' }}</span>
                                </a>
                            {% else %}
                                <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border-2 {{ 'bg-emerald-50 border-emerald-200 text-emerald-600' if r.is_ready else 'bg-slate-50 border-slate-100 text-slate-300' }}">
                                    <span class="text-[10px] font-black uppercase tracking-tighter">{{ 'STATUS: PRONTO' if r.is_ready else 'STATUS: TRABALHANDO' }}</span>
                                </div>
                            {% endif %}
                            
                            <!-- THE NEW TIMESTAMP -->
                            {% if r.is_ready and r.ready_date %}
                                <div class="text-[9px] text-emerald-600 font-bold uppercase mt-1">Concluído em: {{ r.ready_date | format_dt }}</div>
                            {% endif %}
                        </div>

                        {% if session.get('logged_in') %}
                            <form action="/reassign/{{r.id}}" method="POST" class="flex items-center gap-1">
                                <select name="t_id" class="border-2 rounded px-2 py-1 text-[11px] font-bold bg-white">
                                    <option value="">(Sem Técnico)</option>
                                    {% for t in techs %}<option value="{{t.id}}" {{ 'selected' if r.technician_id == t.id }}>{{t.name}}</option>{% endfor %}
                                </select>
                                <button type="submit" class="text-emerald-600 font-black text-xl hover:scale-110 transition">✓</button>
                            </form>
                            <div class="mt-4 flex gap-4 items-center pt-2">
                                {% if r.status == 'NEW' %}<a href="/update/{{r.id}}/quote" class="bg-amber-500 text-white text-[10px] px-3 py-1.5 rounded font-black uppercase shadow-sm hover:bg-amber-600 transition">Enviar Cotação</a>{% endif %}
                                <a href="/update/{{r.id}}/delete" class="text-[9px] text-slate-300 font-black uppercase hover:text-rose-600 transition" onclick="return confirm('Eliminar?')">Eliminar</a>
                            </div>
                        {% elif r.technician %}<div class="bg-slate-800 text-white text-[10px] px-3 py-1 rounded inline-block font-black uppercase tracking-widest shadow-lg">🔧 {{ r.technician.name }}</div>{% endif %}
                    </td>
                    <td>
                        {% if r.status != 'NEW' %}
                            <div class="text-[10px] font-black text-amber-600 flex items-center gap-2 uppercase italic">
                                {% if r.status == 'PENDING' %}<span class="w-2 h-2 bg-amber-500 rounded-full animate-ping"></span> Aguardando Decisão{% else %}<span class="text-slate-400 not-italic font-bold">Resposta Recebida</span>{% endif %}
                            </div>
                            <div class="text-[10px] text-slate-400 mt-1 mb-4 font-bold uppercase">
                                {% if r.status == 'PENDING' %}Cotado {{ r.quote_date | time_ago }}{% else %}Cotado em {{ r.quote_date | format_dt }}{% endif %}
                            </div>
                            {% if session.get('logged_in') and r.status == 'PENDING' %}
                                <div class="flex flex-col gap-2 mt-4">
                                    <a href="/update/{{r.id}}/approve" class="bg-emerald-600 text-white text-center text-[11px] p-2.5 rounded-lg font-black uppercase shadow-md hover:bg-emerald-700 transition">Aprovar</a>
                                    <a href="/update/{{r.id}}/return" class="bg-rose-600 text-white text-center text-[11px] p-2.5 rounded-lg font-black uppercase shadow-md hover:bg-rose-700 transition">Devolução</a>
                                </div>
                            {% endif %}
                        {% endif %}
                    </td>
                    <td>
                        {% if r.status == 'APPROVED' %}<div class="text-emerald-700 font-black text-2xl italic uppercase leading-none">✓ APROVADO</div>
                        {% elif r.status == 'RETURNED' %}<div class="text-rose-700 font-black text-2xl italic uppercase leading-none">✕ DEVOLUÇÃO</div>{% endif %}
                        
                        {% set cln = get_cleanup_info(r) %}
                        {% if cln %}
                            <div class="text-[10px] text-slate-400 font-bold uppercase mt-1 italic tracking-widest">Decisão em {{ r.decision_date | format_dt }}</div>
                            <div class="mt-3 inline-flex items-center gap-1 px-3 py-1 rounded text-[10px] font-black uppercase {{ 'bg-red-100 text-red-700' if cln.is_expired else 'bg-blue-50 text-blue-600 shadow-inner' }}">
                                {% if cln.is_expired %} EXPIROU {% else %} Expira em: {{ cln.days_left }} dias {% endif %}
                            </div>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <script>const isAdmin={{'true' if session.get('logged_in') else 'false'}}, isS={{'true' if s else 'false'}}; if(!isAdmin && !isS){ let lastT = null; setInterval(async()=>{ try{ const r=await fetch('/api/last_update'); const d=await r.json(); if(lastT !== null && d.timestamp > lastT) location.reload(); lastT=d.timestamp; }catch(e){} }, 5000); }</script>
</body>
</html>
"""

# --- ROUTES ---
@app.route('/')
def index():
    s = request.args.get('s', '').strip()
    query = Repair.query
    if s: query = query.join(Technician, isouter=True).filter(db.or_(Repair.description.contains(s.upper()), Technician.name.contains(s)))
    repairs = query.order_by(Repair.last_updated.desc()).all()
    techs = Technician.query.order_by(Technician.name).all()
    return render_template_string(HTML_TEMPLATE, repairs=repairs, techs=techs, s=s)

@app.route('/toggle_ready/<int:id>')
def toggle_ready(id):
    if session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id)
    r.is_ready = not r.is_ready
    # Set the timestamp only when turning it ON
    r.ready_date = datetime.now() if r.is_ready else None
    r.last_updated = datetime.now()
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['u'] == 'admin' and request.form['p'] == 'admin':
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template_string('''<!DOCTYPE html><html lang="pt"><head><meta charset="UTF-8"><title>Login</title><link rel="icon" type="image/png" href="/static/favicon.png"><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-900 flex items-center justify-center h-screen"><div class="bg-white p-10 rounded-2xl shadow-2xl w-96 border-t-8 border-blue-600"><div class="flex justify-center mb-4"><img src="/static/favicon.png" class="w-12 h-12"></div><form method="POST"><input type="text" name="u" placeholder="Usuário" class="w-full border p-3 rounded mb-4 font-bold outline-none" required autofocus><input type="password" name="p" placeholder="Senha" class="w-full border p-3 rounded mb-6 font-bold outline-none" required><button type="submit" class="w-full bg-blue-600 text-white p-4 rounded font-black uppercase">Entrar</button></form><div class="mt-6 text-center"><a href="/" class="text-xs text-slate-400 uppercase underline">Sair</a></div></div></body></html>''')

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add():
    if not session.get('logged_in'): return redirect(url_for('index'))
    desc = request.form.get('desc')
    t_id = request.form.get('t_id')
    if desc: db.session.add(Repair(description=desc.upper(), technician_id=t_id if t_id else None, last_updated=datetime.now())); db.session.commit()
    return redirect(url_for('index'))

@app.route('/reassign/<int:id>', methods=['POST'])
def reassign(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id)
    r.technician_id = request.form.get('t_id') if request.form.get('t_id') else None
    r.last_updated = datetime.now(); db.session.commit()
    return redirect(url_for('index'))

@app.route('/update/<int:id>/<action>')
def update(id, action):
    if not session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id)
    r.last_updated = datetime.now()
    if action == 'quote': r.status = 'PENDING'; r.quote_date = datetime.now()
    elif action == 'approve': r.status = 'APPROVED'; r.decision_date = datetime.now()
    elif action == 'return': r.status = 'RETURNED'; r.decision_date = datetime.now()
    elif action == 'delete': db.session.delete(r)
    elif action == 'deny_removal': r.delay_until = datetime.now() + timedelta(days=30)
    db.session.commit(); return redirect(url_for('index'))

@app.route('/tech/manage', methods=['POST'])
def add_tech():
    if not session.get('logged_in'): return redirect(url_for('index'))
    n = request.form.get('n')
    if n: db.session.add(Technician(name=n)); db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/delete/<int:id>')
def delete_tech(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    t = Technician.query.get(id); db.session.delete(t); db.session.commit()
    return redirect(url_for('index'))

@app.route('/api/last_update')
def last_update():
    latest = Repair.query.order_by(Repair.last_updated.desc()).first()
    return jsonify({"timestamp": latest.last_updated.timestamp() if latest else 0})

# --- AUTO-FIX DATABASE ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        try:
            inspector = inspect(db.engine)
            cols = [c['name'] for c in inspector.get_columns('repair')]
            if 'is_ready' not in cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE repair ADD COLUMN is_ready BOOLEAN DEFAULT 0'))
                    conn.commit()
            if 'ready_date' not in cols:
                with db.engine.connect() as conn:
                    conn.execute(text('ALTER TABLE repair ADD COLUMN ready_date DATETIME'))
                    conn.commit()
        except Exception as e: print("Migration Check:", e)

        if Technician.query.count() == 0:
            for n in ["Homo", "Willard", "Madeline", "Reginaldo", "Dinis"]: db.session.add(Technician(name=n))
            db.session.commit()
    app.run(host='0.0.0.0', port=5000)
