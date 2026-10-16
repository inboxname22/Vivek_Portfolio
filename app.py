import os, json, base64, secrets, sqlite3, time, hmac
from pathlib import Path
from io import BytesIO
from functools import wraps
from collections import defaultdict, deque
from flask import Flask, request, session, jsonify, abort, render_template, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
BASE=Path(__file__).resolve().parent
secret=os.environ.get('SESSION_SECRET','')
if len(secret)<32: raise RuntimeError('SESSION_SECRET must contain at least 32 random characters.')
key=base64.b64decode(os.environ.get('DATA_KEY_B64',''),validate=True)
if len(key)!=32: raise RuntimeError('DATA_KEY_B64 must encode a random 32-byte AES key.')
aes=AESGCM(key)
db=Path(os.environ.get('DATABASE_PATH',str(BASE/'private'/'portfolio.db')))
db.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
app=Flask(__name__)
app.config.update(SECRET_KEY=secret,MAX_CONTENT_LENGTH=28*1024*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.environ.get('COOKIE_SECURE','1')=='1')
def con(): return sqlite3.connect(db,timeout=20)
def save(d):
    nonce=secrets.token_bytes(12); value=nonce+aes.encrypt(nonce,json.dumps(d).encode(),b'portfolio-v1')
    with con() as c: c.execute('INSERT INTO content(id,payload) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload',(value,))
def load():
    with con() as c: b=c.execute('SELECT payload FROM content WHERE id=1').fetchone()[0]
    return json.loads(aes.decrypt(b[:12],b[12:],b'portfolio-v1'))
with con() as c:
    c.executescript((BASE/'schema.sql').read_text())
    owner=c.execute('SELECT 1 FROM owner WHERE id=1').fetchone()
    exists=c.execute('SELECT 1 FROM content WHERE id=1').fetchone()
    if not owner:
        password=os.environ.get('ADMIN_PASSWORD','')
        if len(password)<14: raise RuntimeError('First startup requires ADMIN_PASSWORD with at least 14 characters.')
        c.execute('INSERT INTO owner VALUES(1,?)',(generate_password_hash(password,method='scrypt'),))
if not exists: save(json.loads((BASE/'seed.json').read_text()))
try: os.chmod(db,0o600)
except OSError: pass
attempts=defaultdict(deque)
def admin(f):
    @wraps(f)
    def inner(*a,**kw):
        now=time.time()
        if not session.get('owner') or now-session.get('last',0)>900 or now-session.get('issued',0)>28800:
            session.clear();abort(401)
        session['last']=now
        return f(*a,**kw)
    return inner
@app.before_request
def csrf():
    if request.method in ('POST','PUT','DELETE','PATCH'):
        t=session.get('csrf','')
        if not t or not hmac.compare_digest(t,request.headers.get('X-CSRF-Token','')): abort(403)
@app.after_request
def headers(resp):
    resp.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'self'"
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['X-Frame-Options']='SAMEORIGIN' if request.path=='/api/pdf' else 'DENY'
    resp.headers['Referrer-Policy']='same-origin'
    resp.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    if app.config['SESSION_COOKIE_SECURE']: resp.headers['Strict-Transport-Security']='max-age=31536000'
    if request.path.startswith('/api/'): resp.headers['Cache-Control']='no-store'
    return resp
@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(413)
@app.errorhandler(429)
def error(e):return jsonify(error=e.description),e.code
@app.get('/')
def index():return render_template('index.html')
@app.get('/health')
def health():return jsonify(ok=True)
@app.get('/api/session')
def info():
    if 'csrf' not in session:session['csrf']=secrets.token_urlsafe(32)
    return jsonify(csrf=session['csrf'])
@app.post('/api/login')
def login():
    ip=request.remote_addr or 'unknown';now=time.time()
    for k in ('global',ip):
        q=attempts[k]
        while q and q[0]<now-900:q.popleft()
        if len(q)>=(50 if k=='global' else 5):abort(429,'Wait 15 minutes before retrying.')
    x=request.get_json(silent=True) or {};p=x.get('password','')
    if not isinstance(p,str) or len(p)>1024:abort(400)
    with con() as c: hashed=c.execute('SELECT password_hash FROM owner WHERE id=1').fetchone()[0]
    if not check_password_hash(hashed,p):
        attempts[ip].append(now);attempts['global'].append(now);abort(401,'Incorrect password.')
    attempts[ip].clear();session.clear();session.update(owner=True,last=now,issued=now,csrf=secrets.token_urlsafe(32))
    return jsonify(csrf=session['csrf'])
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)
@app.get('/api/public')
def public():return jsonify({k:v for k,v in load().items() if k in ('name','title','summary','projects')})
@app.get('/api/admin')
@admin
def owner():return jsonify({k:v for k,v in load().items() if k not in ('pdf','word')})
@app.put('/api/admin')
@admin
def update():
    x=request.get_json(silent=True)
    if not isinstance(x,dict):abort(400)
    for k,n in [('name',200),('title',500),('summary',20000)]:
        if not isinstance(x.get(k),str) or len(x[k])>n:abort(400)
    projects=x.get('projects')
    if not isinstance(projects,list) or len(projects)>200:abort(400)
    for p in projects:
        if not isinstance(p,dict) or any(not isinstance(p.get(k),str) or len(p[k])>n for k,n in [('name',300),('description',20000)]):abort(400)
    d=load();d.update({k:x[k] for k in ('name','title','summary')});d['projects']=[{k:p[k] for k in ('name','description')} for p in projects];save(d);return jsonify(ok=True)
@app.post('/api/upload/<kind>')
@admin
def upload(kind):
    if kind not in ('pdf','word'):abort(404)
    f=request.files.get('file')
    if not f:abort(400)
    b=f.read(20*1024*1024+1);name=Path((f.filename or '').replace('\\','/')).name[:180]
    if len(b)>20*1024*1024:abort(413)
    if kind=='pdf' and (not name.lower().endswith('.pdf') or not b.startswith(b'%PDF-')):abort(400,'Invalid PDF.')
    if kind=='word' and not ((name.lower().endswith('.docx') and b.startswith(b'PK')) or (name.lower().endswith('.doc') and b.startswith(bytes.fromhex('D0CF11E0A1B11AE1')))):abort(400,'Invalid Word document.')
    d=load();d[kind]=base64.b64encode(b).decode();d[kind+'Name']=name;save(d);return jsonify(ok=True)
@app.get('/api/pdf')
def pdf():
    d=load()
    if not d.get('pdf'):abort(404)
    return send_file(BytesIO(base64.b64decode(d['pdf'])),mimetype='application/pdf',download_name='Vivek_Resume.pdf',as_attachment=request.args.get('download')=='1')
@app.get('/api/word')
@admin
def word():
    d=load()
    if not d.get('word'):abort(404)
    mime='application/vnd.openxmlformats-officedocument.wordprocessingml.document' if d['wordName'].lower().endswith('.docx') else 'application/msword'
    return send_file(BytesIO(base64.b64decode(d['word'])),mimetype=mime,download_name=d['wordName'],as_attachment=True)
