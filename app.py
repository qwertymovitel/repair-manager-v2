import os
from flask import Flask, request, redirect, url_for, session, flash, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text, inspect, or_
from datetime import datetime

# --- INITIAL SETUP ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, static_folder='static')
app.secret_key = "maputo-repair-v4-warranty-fix"

instance_path = os.path.join(base_dir, 'instance')
if not os.path.exists(instance_path): os.makedirs(instance_path)

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
    ready_date = db.Column(db.DateTime, nullable=True)
    delivery_date = db.Column(db.DateTime, nullable=True)
    # NEW FIELDS FOR WARRANTY/COMPLAINTS
    is_warranty = db.Column(db.Boolean, default=False)
    client_complaint = db.Column(db.String(500), nullable=True)
    
    technician_id = db.Column(db.Integer, db.ForeignKey('technician.id'), nullable=True)
    technician = db.relationship('Technician', backref='repairs')
    quote_date = db.Column(db.DateTime, nullable=True)
    decision_date = db.Column(db.DateTime, nullable=True)
    last_updated = db.Column(db.DateTime, default=datetime.now)

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

# --- SHARED NAVIGATION ---
NAV_HTML = """
<div class="p-5 bg-slate-900 text-white flex justify-between items-center">
    <div class="flex items-center gap-4">
        <img src="{{ url_for('static', filename='favicon.png') }}" class="w-12 h-12">
        <div>
            <h1 class="text-2xl font-black italic tracking-tighter leading-none uppercase">Repair Manager</h1>
            <p class="text-[10px] text-slate-400 font-bold uppercase mt-1 tracking-widest">Maputo, Moçambique</p>
        </div>
    </div>
    <div class="flex items-center gap-3">
        <a href="/" class="text-[10px] border border-slate-700 px-3 py-1.5 rounded font-bold uppercase hover:bg-slate-800 transition">Painel Principal</a>
        <a href="/history" class="text-[10px] bg-slate-800 px-3 py-1.5 rounded font-bold uppercase hover:bg-slate-700 transition">Histórico</a>
        {% if session.get('logged_in') %}
            <a href="/logout" class="bg-rose-600 px-4 py-1.5 rounded text-[10px] font-black uppercase hover:bg-rose-700 transition">Sair</a>
        {% else %}
            <a href="/login" class="bg-blue-600 px-6 py-2 rounded text-xs font-black uppercase hover:bg-blue-700 transition">Login Admin</a>
        {% endif %}
    </div>
</div>
"""

# --- PAGE TEMPLATES ---
MAIN_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8"><title>Repair Manager - Maputo</title>
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon.png') }}">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>table {width:100%; border-collapse:collapse;} th,td {border:1px solid #cbd5e1; padding:15px; vertical-align:top; width:33.33%;} .bg-custom {background-color:#f8fafc;} .bg-warranty {background-color:#fff1f2; border-left: 4px solid #e11d48;}</style>
</head>
<body class="bg-slate-200 p-4 font-sans text-slate-900">
    <div class="max-w-7xl mx-auto bg-white shadow-2xl rounded-xl overflow-hidden border">
        """ + NAV_HTML + """

        <!-- SEARCH BAR -->
        <div class="p-4 bg-slate-100 border-b flex justify-between items-center">
            <form action="/" method="GET" class="flex max-w-md gap-2">
                <input type="text" name="s" value="{{ s }}" placeholder="🔍 Pesquisar equipamento ou técnico..." class="p-2 text-sm border-2 rounded-lg outline-none uppercase font-bold focus:border-blue-500 w-80">
                <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded-lg text-xs font-bold uppercase">Buscar</button>
                {% if s %}<a href="/" class="bg-slate-300 text-slate-700 px-4 py-2 rounded-lg text-xs font-bold flex items-center uppercase">Limpar</a>{% endif %}
            </form>
            {% if not session.get('logged_in') %}<div class="text-[9px] text-slate-400 font-bold uppercase italic animate-pulse">Auto-Update Ativo</div>{% endif %}
        </div>

        {% if session.get('logged_in') %}
        <div class="p-4 border-b bg-slate-50 flex justify-between items-center">
            <form action="/add" method="POST" class="flex gap-2 flex-1">
                <input type="text" name="desc" placeholder="NOVO EQUIPAMENTO..." class="flex-1 border-2 p-3 rounded-lg text-sm font-bold uppercase outline-none focus:border-blue-500" required>
                <select name="t_id" class="border-2 p-3 rounded-lg text-xs font-bold bg-white">
                    <option value="">Técnico (Opcional)</option>
                    {% for t in techs %}<option value="{{t.id}}">{{t.name}}</option>{% endfor %}
                </select>
                <button type="submit" class="bg-blue-600 text-white px-8 py-3 rounded-lg font-black uppercase text-xs">Registar</button>
            </form>
            <button onclick="document.getElementById('m').classList.toggle('hidden')" class="ml-4 text-[10px] bg-slate-200 p-2 rounded font-bold uppercase">Gerir Técnicos</button>
        </div>
        <div id="m" class="hidden p-4 bg-slate-100 border-b">
            <div class="flex flex-wrap gap-2 mb-4">
                {% for t in techs %}<span class="bg-white border-2 px-3 py-1 rounded-full text-[10px] font-bold">{{t.name}} <a href="/tech/delete/{{t.id}}" class="text-rose-500 ml-1">×</a></span>{% endfor %}
            </div>
            <form action="/tech/manage" method="POST" class="flex gap-2">
                <input type="text" name="n" placeholder="Novo nome..." class="border p-2 text-xs rounded-lg"><button type="submit" class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-[10px] font-bold uppercase">+ Add</button>
            </form>
        </div>
        {% endif %}

        <table class="w-full">
            <thead class="bg-slate-50 text-[11px] font-black text-slate-500 uppercase tracking-widest"><tr><th>1. ENTRADA</th><th>2. PENDENTE</th><th>3. FINALIZADO</th></tr></thead>
            <tbody>
                {% for r in repairs %}
                <tr class="{{ 'bg-warranty' if r.is_warranty else ('bg-custom' if loop.index is even) }} border-b border-slate-100">
                    <td>
                        {% if r.is_warranty %}<div class="text-[9px] bg-rose-600 text-white px-2 py-0.5 rounded inline-block font-black mb-2">REPARO EM GARANTIA</div>{% endif %}
                        <div class="font-black text-slate-800 text-lg leading-tight uppercase">{{ r.description }}</div>
                        
                        {% if r.client_complaint %}
                            <div class="text-[11px] bg-rose-100 text-rose-800 p-2 rounded mt-2 border border-rose-200">
                                <strong>QUEIXA:</strong> {{ r.client_complaint }}
                            </div>
                        {% endif %}

                        <div class="text-[9px] text-slate-400 mt-2 mb-2 font-bold uppercase tracking-tight italic border-b pb-1">Entrada {{ r.last_updated | format_dt }}</div>
                        
                        <div class="mb-4">
                            {% if not session.get('logged_in') %}
                                <a href="/toggle_ready/{{r.id}}" class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border-2 transition-all shadow-sm {{ 'bg-emerald-100 border-emerald-500 text-emerald-800' if r.is_ready else 'bg-slate-50 border-slate-300 text-slate-400' }}">
                                    <span class="text-[10px] font-black uppercase tracking-tighter">{{ '✓ PRONTO P/ ENTREGA' if r.is_ready else '☐ MARCAR PRONTO' }}</span>
                                </a>
                            {% else %}
                                <div class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border-2 {{ 'bg-emerald-50 border-emerald-200 text-emerald-600' if r.is_ready else 'bg-slate-50 border-slate-100 text-slate-300' }}">
                                    <span class="text-[10px] font-black uppercase tracking-tighter">{{ 'PRONTO' if r.is_ready else 'TRABALHANDO' }}</span>
                                </div>
                            {% endif %}
                            {% if r.is_ready and r.ready_date %}<div class="text-[9px] text-emerald-600 font-bold uppercase mt-1">Concluído {{ r.ready_date | format_dt }}</div>{% endif %}
                        </div>

                        {% if session.get('logged_in') %}
                            <form action="/reassign/{{r.id}}" method="POST" class="flex items-center gap-1">
                                <select name="t_id" class="border rounded px-2 py-1 text-[11px] font-bold bg-white">
                                    <option value="">(Sem Técnico)</option>
                                    {% for t in techs %}<option value="{{t.id}}" {{ 'selected' if r.technician_id == t.id }}>{{t.name}}</option>{% endfor %}
                                </select>
                                <button type="submit" class="text-emerald-600 font-black text-xl">✓</button>
                            </form>
                            <div class="mt-4 flex gap-4 items-center pt-2">
                                {% if r.status == 'NEW' %}<a href="/update/{{r.id}}/quote" class="bg-amber-500 text-white text-[10px] px-3 py-1.5 rounded font-black uppercase">Enviar Cotação</a>{% endif %}
                                <a href="/update/{{r.id}}/delete" class="text-[9px] text-slate-300 font-black hover:text-rose-600 uppercase" onclick="return confirm('Eliminar?')">Eliminar</a>
                            </div>
                        {% elif r.technician %}<div class="bg-slate-800 text-white text-[10px] px-3 py-1 rounded inline-block font-black uppercase tracking-widest">🔧 {{ r.technician.name }}</div>{% endif %}
                    </td>
                    <td>
                        {% if r.status != 'NEW' %}
                            <div class="text-[10px] font-black text-amber-600 uppercase italic">{% if r.status == 'PENDING' %}<span class="animate-pulse">●</span> Aguardando Decisão{% else %}Resposta Recebida{% endif %}</div>
                            <div class="text-[10px] text-slate-400 font-bold uppercase mt-1">{% if r.status == 'PENDING' %}Cotado {{ r.quote_date | time_ago }}{% else %}Cotado em {{ r.quote_date | format_dt }}{% endif %}</div>
                            {% if session.get('logged_in') and r.status == 'PENDING' %}
                                <div class="flex flex-col gap-2 mt-4"><a href="/update/{{r.id}}/approve" class="bg-emerald-600 text-white text-center text-[11px] p-2 rounded-lg font-black uppercase shadow-sm">Aprovar</a><a href="/update/{{r.id}}/return" class="bg-rose-600 text-white text-center text-[11px] p-2 rounded-lg font-black uppercase shadow-sm">Devolução</a></div>
                            {% endif %}
                        {% endif %}
                    </td>
                    <td>
                        {% if r.status == 'APPROVED' %}<div class="text-emerald-700 font-black text-2xl italic uppercase">✓ APROVADO</div>
                        {% elif r.status == 'RETURNED' %}<div class="text-rose-700 font-black text-2xl italic uppercase">✕ DEVOLUÇÃO</div>{% endif %}
                        
                        {% if r.decision_date %}
                            <div class="text-[10px] text-slate-400 font-bold uppercase mt-1 border-b pb-2 mb-4">Decidido em {{ r.decision_date | format_dt }}</div>
                            {% if session.get('logged_in') %}
                                <a href="/update/{{r.id}}/deliver" class="bg-slate-900 text-white block text-center text-[10px] p-3 rounded-lg font-black uppercase shadow-xl hover:bg-black">Confirmar Entrega</a>
                            {% endif %}
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

HISTORY_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt">
<head>
    <meta charset="UTF-8"><title>Histórico de Entregas</title>
    <link rel="icon" type="image/png" href="{{ url_for('static', filename='favicon.png') }}">
    <script src="https://cdn.tailwindcss.com"></script>
    <style>table {width:100%; border-collapse:collapse;} th,td {border:1px solid #cbd5e1; padding:12px; text-align:left;}</style>
</head>
<body class="bg-slate-200 p-4 font-sans text-slate-900">
    <div class="max-w-7xl mx-auto bg-white shadow-2xl rounded-xl overflow-hidden border">
        """ + NAV_HTML + """
        
        <div class="p-6 bg-slate-50 border-b flex justify-between items-center">
            <form action="/history" method="GET" class="flex max-w-md gap-2">
                <input type="text" name="s" value="{{ s }}" placeholder="🔍 Pesquisar no histórico..." class="p-2 text-sm border-2 rounded-lg outline-none uppercase font-bold w-64">
                <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded-lg text-xs font-bold uppercase">Ir</button>
                {% if s %}<a href="/history" class="bg-slate-300 text-slate-700 px-4 py-2 rounded-lg text-xs font-bold flex items-center uppercase">Limpar</a>{% endif %}
            </form>
            <div class="text-xs text-slate-400 font-bold uppercase tracking-widest">Total histórico: {{ repairs|length }}</div>
        </div>

        <table class="w-full">
            <thead class="bg-slate-100 text-[10px] font-black text-slate-500 uppercase tracking-widest"><tr><th>Equipamento</th><th>Técnico</th><th>Status Final</th><th>Entregue em</th><th>Ações Admin</th></tr></thead>
            <tbody>
                {% for r in repairs %}
                <tr class="hover:bg-slate-50 border-b">
                    <td class="font-bold uppercase text-sm p-4">{{ r.description }}</td>
                    <td class="text-xs uppercase">{{ r.technician.name if r.technician else '---' }}</td>
                    <td class="text-xs font-bold {{ 'text-emerald-600' if r.status == 'APPROVED' else 'text-rose-600' }} uppercase">{{ r.status }}</td>
                    <td class="text-xs">{{ r.delivery_date | format_dt }} <span class="text-slate-400 ml-1">{{ r.delivery_date | time_ago }}</span></td>
                    <td class="p-4">
                        {% if session.get('logged_in') %}
                            <div class="flex flex-wrap gap-3">
                                <a href="/update/{{r.id}}/undo" class="text-[9px] bg-slate-200 p-1.5 rounded font-black uppercase hover:bg-slate-300" title="Voltar ao painel principal sem mudar ordem">Desfazer Entrega</a>
                                <button onclick="let c=prompt('Motivo do retorno (Garantia):'); if(c) window.location.href='/warranty/{{r.id}}?c='+encodeURIComponent(c)" class="text-[9px] bg-rose-100 text-rose-700 p-1.5 rounded font-black uppercase hover:bg-rose-200">Garantia / Queixa</button>
                                <a href="/update/{{r.id}}/delete_hist" class="text-[9px] text-rose-500 font-bold uppercase hover:underline pt-1" onclick="return confirm('Eliminar permanentemente?')">Eliminar</a>
                            </div>
                        {% else %}<span class="text-[9px] text-slate-300 italic uppercase">Apenas Admin</span>{% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/')
def index():
    s = request.args.get('s', '').strip()
    query = Repair.query.filter(Repair.status != 'DELIVERED')
    if s: query = query.join(Technician, isouter=True).filter(or_(Repair.description.contains(s.upper()), Technician.name.contains(s)))
    repairs = query.order_by(Repair.last_updated.desc()).all()
    techs = Technician.query.order_by(Technician.name).all()
    return render_template_string(MAIN_TEMPLATE, repairs=repairs, techs=techs, s=s)

@app.route('/history')
def history():
    s = request.args.get('s', '').strip()
    query = Repair.query.filter_by(status='DELIVERED')
    if s: query = query.join(Technician, isouter=True).filter(or_(Repair.description.contains(s.upper()), Technician.name.contains(s)))
    repairs = query.order_by(Repair.delivery_date.desc()).all()
    return render_template_string(HISTORY_TEMPLATE, repairs=repairs, s=s)

@app.route('/toggle_ready/<int:id>')
def toggle_ready(id):
    if session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id); r.is_ready = not r.is_ready; r.ready_date = datetime.now() if r.is_ready else None; r.last_updated = datetime.now(); db.session.commit()
    return redirect(url_for('index'))

@app.route('/warranty/<int:id>')
def warranty(id):
    if not session.get('logged_in'): return redirect(url_for('login'))
    r = Repair.query.get(id)
    complaint = request.args.get('c', 'Cliente reclamou que não está a funcionar.')
    r.status = 'NEW'
    r.is_warranty = True
    r.client_complaint = complaint
    r.is_ready = False
    r.delivery_date = None
    r.last_updated = datetime.now() # Warranty hits the top
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['u'] == 'admin' and request.form['p'] == 'admin': session['logged_in'] = True; return redirect(url_for('index'))
    return render_template_string('''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Login</title><link rel="icon" type="image/png" href="/static/favicon.png"><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-slate-900 flex items-center justify-center h-screen"><div class="bg-white p-10 rounded-2xl shadow-2xl w-96 border-t-8 border-blue-600"><div class="flex justify-center mb-4"><img src="/static/favicon.png" class="w-12 h-12"></div><form method="POST"><input type="text" name="u" placeholder="Usuário" class="w-full border p-3 rounded mb-4 font-bold outline-none uppercase" required autofocus><input type="password" name="p" placeholder="Senha" class="w-full border p-3 rounded mb-6 font-bold outline-none" required><button type="submit" class="w-full bg-blue-600 text-white p-4 rounded font-black uppercase">Entrar</button></form></div></body></html>''')

@app.route('/update/<int:id>/<action>')
def update(id, action):
    if not session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id)
    
    if action == 'undo':
        # Restore to panel without changing the "last_updated" timestamp (don't move to top)
        r.status = 'APPROVED'
        r.delivery_date = None
    elif action == 'deliver':
        r.status = 'DELIVERED'; r.delivery_date = datetime.now(); r.last_updated = datetime.now()
    else:
        r.last_updated = datetime.now()
        if action == 'quote': r.status = 'PENDING'; r.quote_date = datetime.now()
        elif action == 'approve': r.status = 'APPROVED'; r.decision_date = datetime.now()
        elif action == 'return': r.status = 'RETURNED'; r.decision_date = datetime.now()
        elif action == 'delete' or action == 'delete_hist': db.session.delete(r)
        elif action == 'restore': r.status = 'APPROVED'; r.delivery_date = None

    db.session.commit()
    return redirect(url_for('history' if 'hist' in action else 'index'))

@app.route('/logout')
def logout(): session.clear(); return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add():
    if not session.get('logged_in'): return redirect(url_for('index'))
    desc = request.form.get('desc'); t_id = request.form.get('t_id')
    if desc: db.session.add(Repair(description=desc.upper(), technician_id=t_id if t_id else None, last_updated=datetime.now())); db.session.commit()
    return redirect(url_for('index'))

@app.route('/reassign/<int:id>', methods=['POST'])
def reassign(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id); r.technician_id = request.form.get('t_id') if request.form.get('t_id') else None; r.last_updated = datetime.now(); db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/manage', methods=['POST'])
def add_tech():
    if not session.get('logged_in'): return redirect(url_for('index'))
    n = request.form.get('n'); db.session.add(Technician(name=n)); db.session.commit(); return redirect(url_for('index'))

@app.route('/tech/delete/<int:id>')
def delete_tech(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    t = Technician.query.get(id); db.session.delete(t); db.session.commit(); return redirect(url_for('index'))

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
            with db.engine.connect() as conn:
                if 'delivery_date' not in cols: conn.execute(text('ALTER TABLE repair ADD COLUMN delivery_date DATETIME'))
                if 'client_complaint' not in cols: conn.execute(text('ALTER TABLE repair ADD COLUMN client_complaint TEXT'))
                if 'is_warranty' not in cols: conn.execute(text('ALTER TABLE repair ADD COLUMN is_warranty BOOLEAN DEFAULT 0'))
                conn.commit()
        except: pass
        if Technician.query.count() == 0:
            for n in ["Homo", "Willard", "Madeline", "Reginaldo", "Dinis"]: db.session.add(Technician(name=n))
            db.session.commit()
    app.run(host='0.0.0.0', port=5000)
