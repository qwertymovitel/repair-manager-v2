import os
from flask import Flask, render_template_string, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta

# --- SETUP ---
base_dir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__, static_folder='static')
app.secret_key = "maputo-repair-system-2024"

# Database path
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
    if (diff.seconds // 60) < 1: return "(agora mesmo)"
    if (diff.seconds // 60) < 60: return f"(Há {diff.seconds // 60} min)"
    return f"(Há {diff.seconds // 3600} horas)"

@app.context_processor
def utility_processor():
    def needs_cleanup(repair):
        if repair.status not in ['APPROVED', 'RETURNED'] or not repair.decision_date: return False
        over_90 = datetime.now() > (repair.decision_date + timedelta(days=90))
        not_delayed = repair.delay_until is None or datetime.now() > repair.delay_until
        return over_90 and not_delayed
    return dict(needs_cleanup=needs_cleanup)

# --- HTML TEMPLATE (Embedded) ---
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
<body class="bg-slate-200 p-4 font-sans">
    <div class="max-w-7xl mx-auto bg-white shadow-2xl rounded-xl overflow-hidden border">
        <!-- HEADER -->
        <div class="p-5 bg-slate-900 text-white flex justify-between items-center">
            <div class="flex items-center gap-4">
                <img src="{{ url_for('static', filename='favicon.png') }}" class="w-12 h-12">
                <div>
                    <h1 class="text-2xl font-black italic tracking-tighter">REPAIR MANAGER</h1>
                    <p class="text-[10px] text-slate-400 font-bold uppercase">Maputo, Moçambique</p>
                </div>
            </div>
            <div>
                {% if session.get('logged_in') %}
                    <button onclick="document.getElementById('m').classList.toggle('hidden')" class="text-[10px] bg-slate-700 px-3 py-1.5 rounded font-bold uppercase">Técnicos</button>
                    <a href="/logout" class="bg-rose-600 px-4 py-1.5 rounded text-[10px] font-black uppercase ml-2">Sair</a>
                {% else %}<a href="/login" class="bg-blue-600 px-6 py-2 rounded text-xs font-black uppercase">Login Admin</a>{% endif %}
            </div>
        </div>

        <!-- SEARCH -->
        <div class="p-4 bg-slate-100 border-b flex justify-between items-center">
            <form action="/" method="GET" class="flex max-w-md gap-2">
                <input type="text" name="s" value="{{ s }}" placeholder="🔍 Pesquisar..." class="p-2 text-sm border-2 rounded-lg outline-none uppercase font-bold focus:border-blue-500 w-64">
                <button type="submit" class="bg-slate-800 text-white px-4 py-2 rounded-lg text-xs font-bold uppercase">Buscar</button>
                {% if s %}<a href="/" class="bg-slate-300 text-slate-700 px-4 py-2 rounded-lg text-xs font-bold uppercase flex items-center">Limpar</a>{% endif %}
            </form>
            {% if not session.get('logged_in') %}<div class="text-[9px] text-slate-400 font-bold uppercase italic animate-pulse tracking-widest">Auto-Refresh Ativo</div>{% endif %}
        </div>

        <!-- ADMIN PANEL -->
        {% if session.get('logged_in') %}
        <div class="p-4 border-b bg-slate-50">
            <form action="/add" method="POST" class="flex gap-2">
                <input type="text" name="desc" placeholder="EQUIPAMENTO..." class="flex-1 border-2 p-3 rounded-lg text-sm font-bold uppercase outline-none focus:border-blue-500" required>
                <select name="t_id" class="border-2 p-3 rounded-lg text-xs font-bold bg-white">
                    <option value="">Técnico (Opcional)</option>
                    {% for t in techs %}<option value="{{t.id}}">{{t.name}}</option>{% endfor %}
                </select>
                <button type="submit" class="bg-blue-600 text-white px-8 py-3 rounded-lg font-black uppercase text-xs">Registar</button>
            </form>
        </div>
        <div id="m" class="hidden p-4 bg-slate-100 border-b">
            <div class="flex flex-wrap gap-2 mb-4">
                {% for t in techs %}<span class="bg-white border-2 px-3 py-1 rounded-full text-[10px] font-bold">{{t.name}} <a href="/tech/delete/{{t.id}}" class="text-rose-500 ml-1">×</a></span>{% endfor %}
            </div>
            <form action="/tech/manage" method="POST" class="flex gap-2">
                <input type="text" name="n" placeholder="Novo técnico..." class="border p-2 text-xs rounded-lg">
                <button type="submit" class="bg-emerald-600 text-white px-4 py-2 rounded-lg text-[10px] font-bold uppercase">+ Adicionar Técnico</button>
            </form>
        </div>
        {% endif %}

        <!-- TABLE -->
        <table class="w-full">
            <thead class="bg-slate-50 text-[11px] font-black text-slate-500 uppercase"><tr><th class="p-5 text-left">1. NOVO</th><th class="p-5 text-left">2. PENDENTE</th><th class="p-5 text-left">3. FINALIZADO</th></tr></thead>
            <tbody>
                {% for r in repairs %}
                <tr class="{{ 'bg-custom' if loop.index is even }}">
                    <td>
                        <div class="font-black text-slate-800 text-lg leading-tight">{{ r.description }}</div>
                        <div class="text-[9px] text-slate-400 mt-1 mb-4 font-bold uppercase tracking-widest italic border-b pb-1">Registado em {{ r.last_updated | format_dt }}</div>
                        {% if session.get('logged_in') %}
                            <form action="/reassign/{{r.id}}" method="POST" class="flex items-center gap-1">
                                <select name="t_id" class="border rounded px-2 py-1 text-[11px] font-bold bg-white">
                                    <option value="">(Sem Técnico)</option>
                                    {% for t in techs %}<option value="{{t.id}}" {{ 'selected' if r.technician_id == t.id }}>{{t.name}}</option>{% endfor %}
                                </select>
                                <button type="submit" class="text-emerald-600 font-black text-xl">✓</button>
                            </form>
                            <div class="mt-4 flex gap-4 items-center">
                                {% if r.status == 'NEW' %}<a href="/update/{{r.id}}/quote" class="bg-amber-500 text-white text-[10px] px-3 py-1.5 rounded font-black uppercase">Enviar p/ Cotação</a>{% endif %}
                                <a href="/update/{{r.id}}/delete" class="text-[9px] text-slate-300 font-black uppercase hover:text-rose-600" onclick="return confirm('Eliminar?')">Eliminar</a>
                            </div>
                        {% elif r.technician %}<div class="bg-slate-800 text-white text-[10px] px-3 py-1 rounded inline-block font-black uppercase tracking-widest shadow-lg">🔧 {{ r.technician.name }}</div>{% endif %}
                    </td>
                    <td>
                        {% if r.status != 'NEW' %}
                            <div class="text-[10px] font-black text-amber-600 uppercase italic">{% if r.status == 'PENDING' %}<span class="animate-pulse">●</span> Aguardando Decisão{% else %}Resposta Recebida{% endif %}</div>
                            <div class="text-[10px] text-slate-400 font-bold uppercase mt-1">{% if r.status == 'PENDING' %}Cotado {{ r.quote_date | time_ago }}{% else %}Decidido em {{ r.decision_date | format_dt }}{% endif %}</div>
                            {% if session.get('logged_in') and r.status == 'PENDING' %}
                                <div class="flex flex-col gap-2 mt-4"><a href="/update/{{r.id}}/approve" class="bg-emerald-600 text-white text-center text-[11px] p-2 rounded-lg font-black uppercase">Aprovar</a><a href="/update/{{r.id}}/return" class="bg-rose-600 text-white text-center text-[11px] p-2 rounded-lg font-black uppercase">Devolução</a></div>
                            {% endif %}
                        {% endif %}
                    </td>
                    <td>
                        {% if r.status == 'APPROVED' %}<div class="text-emerald-700 font-black text-2xl italic uppercase">✓ APROVADO</div><div class="text-[10px] text-slate-400 font-bold uppercase">Em {{ r.decision_date | format_dt }}</div>
                        {% elif r.status == 'RETURNED' %}<div class="text-rose-700 font-black text-2xl italic uppercase">✕ DEVOLUÇÃO</div><div class="text-[10px] text-slate-400 font-bold uppercase">Em {{ r.decision_date | format_dt }}</div>{% endif %}
                        {% if needs_cleanup(r) and session.get('logged_in') %}<div class="mt-4 p-2 bg-amber-50 border-2 border-amber-200 rounded text-[9px] font-black text-amber-900 uppercase italic tracking-tighter shadow-sm">⚠️ ALERTA +90 DIAS<br><div class="mt-2 flex gap-2"><a href="/update/{{r.id}}/delete" class="bg-emerald-700 text-white px-2 py-0.5 rounded">Remover</a> <a href="/update/{{r.id}}/deny_removal" class="bg-slate-500 text-white px-2 py-0.5 rounded">Manter +30d</a></div></div>{% endif %}
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

# --- ROUTES CONT. ---
@app.route('/')
def index():
    s = request.args.get('s', '').strip()
    query = Repair.query
    if s:
        query = query.join(Technician, isouter=True).filter(
            db.or_(Repair.description.contains(s.upper()), Technician.name.contains(s))
        )
    repairs = query.order_by(Repair.last_updated.desc()).all()
    techs = Technician.query.order_by(Technician.name).all()
    return render_template_string(HTML_TEMPLATE, repairs=repairs, techs=techs, s=s)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['u'] == 'admin' and request.form['p'] == 'admin':
            session['logged_in'] = True
            return redirect(url_for('index'))
    return render_template_string('''
    <!DOCTYPE html><html lang="pt"><head><meta charset="UTF-8"><title>Login - Repair Manager</title>
    <link rel="icon" type="image/png" href="/static/favicon.png"><script src="https://cdn.tailwindcss.com"></script></head>
    <body class="bg-slate-900 flex items-center justify-center h-screen"><div class="bg-white p-10 rounded-2xl shadow-2xl w-96 border-t-8 border-blue-600">
    <div class="flex justify-center mb-4"><img src="/static/favicon.png" class="w-12 h-12"></div>
    <h2 class="text-2xl font-black text-slate-800 text-center mb-6 uppercase tracking-tighter italic">Admin Access</h2>
    <form method="POST"><div class="mb-4"><label class="block text-[10px] font-black uppercase text-slate-400 mb-1">Usuário</label><input type="text" name="u" class="w-full border-2 p-3 rounded-lg outline-none focus:border-blue-500 font-bold" required autofocus></div>
    <div class="mb-6"><label class="block text-[10px] font-black uppercase text-slate-400 mb-1">Senha</label><input type="password" name="p" class="w-full border-2 p-3 rounded-lg outline-none focus:border-blue-500 font-bold" required></div>
    <button type="submit" class="w-full bg-blue-600 text-white p-4 rounded-xl font-black uppercase text-sm hover:bg-blue-700 shadow-lg">Entrar</button></form>
    <div class="mt-6 text-center"><a href="/" class="text-[10px] font-bold text-slate-400 uppercase hover:text-slate-600 underline">Voltar</a></div></div></body></html>
    ''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/add', methods=['POST'])
def add():
    if not session.get('logged_in'): return redirect(url_for('index'))
    desc = request.form.get('desc')
    t_id = request.form.get('t_id')
    if desc:
        db.session.add(Repair(description=desc.upper(), technician_id=t_id if t_id else None, last_updated=datetime.now()))
        db.session.commit()
    return redirect(url_for('index'))

@app.route('/reassign/<int:id>', methods=['POST'])
def reassign(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    r = Repair.query.get(id)
    r.technician_id = request.form.get('t_id') if request.form.get('t_id') else None
    r.last_updated = datetime.now()
    db.session.commit()
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
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/manage', methods=['POST'])
def add_tech():
    if not session.get('logged_in'): return redirect(url_for('index'))
    n = request.form.get('n')
    if n: db.session.add(Technician(name=n)); db.session.commit()
    return redirect(url_for('index'))

@app.route('/tech/delete/<int:id>')
def delete_tech(id):
    if not session.get('logged_in'): return redirect(url_for('index'))
    t = Technician.query.get(id)
    db.session.delete(t); db.session.commit()
    return redirect(url_for('index'))

@app.route('/api/last_update')
def last_update():
    latest = Repair.query.order_by(Repair.last_updated.desc()).first()
    return jsonify({"timestamp": latest.last_updated.timestamp() if latest else 0})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if Technician.query.count() == 0:
            for n in ["Homo", "Willard", "Madeline", "Reginaldo", "Dinis"]:
                db.session.add(Technician(name=n))
            db.session.commit()
    app.run(host='0.0.0.0', port=5000)
