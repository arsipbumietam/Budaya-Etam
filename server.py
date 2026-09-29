"""Portal Balai Pelestarian Kebudayaan Kaltim.
Run: python server.py  |  Production: uvicorn server:app --host 0.0.0.0
SQLite data and uploads stay outside the public static directory.
"""
from __future__ import annotations
import csv, hashlib, hmac, io, json, os, re, secrets, sqlite3, time, zipfile
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from seed import SETTINGS, SERVICES, POSTS

ROOT = Path(__file__).resolve().parent
if (ROOT/'static/assets/logo-kementerian.png').exists():
    SETTINGS['logo_url']='/static/assets/logo-kementerian.png'
DATA = Path(os.environ.get('BPK_DATA_DIR', ROOT / 'data')).resolve()
DATA.mkdir(parents=True, exist_ok=True)
UPLOADS = DATA / 'uploads'; UPLOADS.mkdir(exist_ok=True)
DB = DATA / 'portal.sqlite3'
PRODUCTION = os.environ.get('BPK_ENV', 'local') == 'production'
COOKIE = 'bpk_session'
MAX_BODY = 12 * 1024 * 1024
MAX_FILE = 8 * 1024 * 1024
KINDS = {'berita','pengumuman','agenda','entitas','cinebudaya','publikasi','ppid','sakip','peraturan','galeri'}
ROLES = {'superadmin','admin','editor','operator'}
STATES = {'Diterima','Diverifikasi','Perlu Perbaikan','Diproses','Selesai','Ditolak'}
Image.MAX_IMAGE_PIXELS = 20_000_000

def now(): return datetime.now(timezone.utc).isoformat(timespec='seconds')
def digest(s): return hashlib.sha256(s.encode()).hexdigest()
def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return 'scrypt$'+salt.hex()+'$'+value.hex()
def password_ok(password, stored):
    try:
        _, salt, val = stored.split('$')
        return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1,dklen=32).hex(),val)
    except (ValueError, TypeError): return False

def validate_password(p):
    if not isinstance(p,str) or not 10 <= len(p) <= 128:
        raise HTTPException(400,'Kata sandi baru harus 10–128 karakter.')
    if not (re.search('[a-zA-Z]',p) and re.search('[0-9]',p) and re.search(r'[^a-zA-Z0-9]',p)):
        raise HTTPException(400,'Gunakan kombinasi huruf, angka, dan simbol.')

@contextmanager
def db():
    c = sqlite3.connect(DB, timeout=20)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()

def initialize():
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''
        CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT UNIQUE COLLATE NOCASE,
        display_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL, active INTEGER DEFAULT 1,
        force_change INTEGER DEFAULT 0, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (sid TEXT PRIMARY KEY, csrf TEXT NOT NULL, user_id INTEGER REFERENCES users(id) ON DELETE CASCADE, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS posts (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY, original_name TEXT, filename TEXT UNIQUE, mime TEXT,
        size INTEGER, is_private INTEGER, created_at TEXT);
        CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY, code TEXT UNIQUE, access_hash TEXT,
        service_id INTEGER, service_name TEXT, name TEXT, email TEXT, phone TEXT, institution TEXT,
        message TEXT, status TEXT, public_reply TEXT DEFAULT '', internal_note TEXT DEFAULT '',
        assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL, attachments TEXT DEFAULT '[]',
        history TEXT DEFAULT '[]', created_at TEXT, updated_at TEXT, is_demo INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, actor TEXT, action TEXT, entity TEXT, created_at TEXT);
        CREATE TABLE IF NOT EXISTS limits (key TEXT, at REAL);
        CREATE INDEX IF NOT EXISTS idx_limits ON limits(key,at);
        CREATE INDEX IF NOT EXISTS idx_session_expiry ON sessions(expires);
        ''')
        if not c.execute('SELECT 1 FROM settings').fetchone():
            c.execute('INSERT INTO settings VALUES (1,?)',(json.dumps(SETTINGS,ensure_ascii=False),))
            for p in POSTS: c.execute('INSERT INTO posts VALUES (?,?)',(p['id'],json.dumps(p,ensure_ascii=False)))
            for s in SERVICES: c.execute('INSERT INTO services VALUES (?,?)',(s['id'],json.dumps(s,ensure_ascii=False)))
        if not c.execute('SELECT 1 FROM users').fetchone():
            initial = os.environ.get('BPK_INITIAL_PASSWORD','@dmin123')
            if PRODUCTION and initial == '@dmin123':
                raise RuntimeError('Produksi pertama memerlukan BPK_INITIAL_PASSWORD baru, bukan kata sandi bawaan.')
            if PRODUCTION: validate_password(initial)
            c.execute('INSERT INTO users(username,display_name,password_hash,role,force_change,created_at) VALUES(?,?,?,?,?,?)',
              ('Febryanto','Febryanto',password_hash(initial),'superadmin', int(initial == '@dmin123'),now()))
        c.execute('DELETE FROM sessions WHERE expires < ?',(time.time(),))
        c.execute('DELETE FROM limits WHERE at < ?',(time.time()-86400,))
initialize()

app = FastAPI(title='Balai Pelestarian Kebudayaan Kaltim',docs_url=None,redoc_url=None,openapi_url=None)

class BodyLimitMiddleware:
    def __init__(self, app): self.app=app
    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http': return await self.app(scope,receive,send)
        # API writes are bounded before parsers allocate data, including chunked requests.
        if scope['method'] in {'POST','PUT','PATCH','DELETE'}:
            chunks=[]; size=0
            while True:
                msg=await receive()
                if msg['type']=='http.disconnect': return
                size+=len(msg.get('body',b''))
                if size>MAX_BODY:
                    r=JSONResponse({'detail':'Ukuran permintaan melebihi 12 MB.'},status_code=413)
                    return await r(scope,receive,send)
                chunks.append(msg)
                if not msg.get('more_body'): break
            async def replay():
                if chunks:return chunks.pop(0)
                return await receive()
            return await self.app(scope,replay,send)
        return await self.app(scope,receive,send)
app.add_middleware(BodyLimitMiddleware)

@app.middleware('http')
async def security_headers(request: Request, call_next):
    if request.method in {'POST','PUT','PATCH','DELETE'} and request.url.path.startswith('/api/'):
        origin=request.headers.get('origin')
        allowed={str(request.base_url).rstrip('/')}
        allowed.update(x.strip().rstrip('/') for x in os.environ.get('BPK_ALLOWED_ORIGINS','').split(',') if x.strip())
        if origin and origin not in allowed:
            return JSONResponse({'detail':'Asal permintaan tidak diizinkan.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    response.headers.setdefault('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; font-src 'self'; connect-src 'self'; frame-src https://www.youtube-nocookie.com https://player.vimeo.com; media-src 'self' blob: https:; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    if request.url.path.startswith('/api/') or request.url.path.startswith('/files/'):
        response.headers['Cache-Control']='no-store'
    if PRODUCTION: response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.exception_handler(HTTPException)
async def http_error(request, exc): return JSONResponse({'detail':exc.detail},status_code=exc.status_code)

def settings():
    with db() as c: return json.loads(c.execute('SELECT data FROM settings WHERE id=1').fetchone()[0])
def audit(user,action,entity):
    with db() as c: c.execute('INSERT INTO audit(actor,action,entity,created_at) VALUES (?,?,?,?)',
      ((user or {}).get('username','publik'),action,str(entity)[:250],now()))
def safe_user(row):
    return {k:row[k] for k in ['id','username','display_name','role','active','force_change','created_at']}

def session(request):
    sid=request.cookies.get(COOKIE,'')
    if not sid:return None
    with db() as c:
        r=c.execute('SELECT * FROM sessions WHERE sid=? AND expires>?',(digest(sid),time.time())).fetchone()
        return dict(r) if r else None

def guard(request,roles=None,write=False):
    s=session(request)
    if not s or not s['user_id']:raise HTTPException(401,'Silakan login terlebih dahulu.')
    with db() as c:
        row=c.execute('SELECT * FROM users WHERE id=? AND active=1',(s['user_id'],)).fetchone()
    if not row:raise HTTPException(401,'Akun tidak aktif atau sesi telah berakhir.')
    u=safe_user(row)
    if roles and u['role'] not in roles:raise HTTPException(403,'Akun ini tidak memiliki izin untuk tindakan tersebut.')
    if write:csrf_guard(request,s)
    if write and (PRODUCTION or not settings()['review_mode']) and u['force_change'] and request.url.path!='/api/password':
        raise HTTPException(403,'Ganti kata sandi awal melalui menu Akun Saya sebelum mengelola situs produksi.')
    return u

def csrf_guard(request,s=None):
    s=s or session(request)
    if not s or not hmac.compare_digest(request.headers.get('x-csrf-token',''),s['csrf']):
        raise HTTPException(403,'Sesi keamanan kedaluwarsa. Muat ulang halaman lalu coba lagi.')

def new_session(user_id=None):
    raw=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    with db() as c:
        c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
        c.execute('INSERT INTO sessions VALUES (?,?,?,?)',(digest(raw),csrf,user_id,time.time()+8*3600))
    return raw,csrf

def put_cookie(response,raw):
    response.set_cookie(COOKIE,raw,max_age=8*3600,httponly=True,secure=PRODUCTION,samesite='strict',path='/')
    return response

def rate(request,kind,max_count,seconds,extra=''):
    ip=request.client.host if request.client else 'local'
    key=digest(kind+'|'+ip+'|'+extra.casefold())
    with db() as c:
        c.execute('DELETE FROM limits WHERE at < ?',(time.time()-86400,))
        n=c.execute('SELECT COUNT(*) FROM limits WHERE key=? AND at>?',(key,time.time()-seconds)).fetchone()[0]
        if n>=max_count:raise HTTPException(429,'Terlalu banyak percobaan. Silakan tunggu dan coba kembali.')
        c.execute('INSERT INTO limits VALUES(?,?)',(key,time.time()))

def text(value,max_len=500,required=False):
    if not isinstance(value,str):raise HTTPException(400,'Isian harus berupa teks.')
    v=value.strip()
    if len(v)>max_len or (required and not v):raise HTTPException(400,f'Isian wajib terisi dan maksimal {max_len} karakter.' if required else f'Isian maksimal {max_len} karakter.')
    return v

def safe_url(value,local=True):
    v=text(value,2000)
    if not v:return ''
    if local and re.fullmatch(r'/(?:files|static/assets)/[a-zA-Z0-9_./-]+',v) and '..' not in v:return v
    u=urlparse(v)
    if u.scheme not in {'https','http'} or not u.netloc or u.username or u.password:raise HTTPException(400,'Tautan harus berupa alamat http/https yang sah.')
    return v

async def payload(request):
    try:d=await request.json()
    except Exception:raise HTTPException(400,'Data JSON tidak sah.')
    if not isinstance(d,dict):raise HTTPException(400,'Data harus berupa objek.')
    return d

@app.get('/api/session')
def get_session(request:Request):
    s=session(request); u=None
    if s and s['user_id']:
        with db() as c:
            row=c.execute('SELECT * FROM users WHERE id=? AND active=1',(s['user_id'],)).fetchone()
            if row:u=safe_user(row)
            else:s=None
    if s:return {'user':u,'csrf':s['csrf']}
    raw,csrf=new_session()
    return put_cookie(JSONResponse({'user':None,'csrf':csrf}),raw)

@app.post('/api/login')
async def login(request:Request):
    csrf_guard(request);d=await payload(request)
    name=text(d.get('username',''),64,True); pw=d.get('password','')
    if not isinstance(pw,str) or not 1<=len(pw)<=128:raise HTTPException(400,'Kata sandi harus terisi dan maksimal 128 karakter.')
    rate(request,'login-global',30,900);rate(request,'login-user',8,900,name)
    with db() as c:row=c.execute('SELECT * FROM users WHERE username=? AND active=1',(name,)).fetchone()
    # Constant-work fallback avoids making unknown accounts much faster.
    fallback='scrypt$'+'00'*16+'$'+'00'*32
    ok=await run_in_threadpool(password_ok,pw,row['password_hash'] if row else fallback)
    if not row or not ok:raise HTTPException(401,'Username atau kata sandi tidak sesuai.')
    old=session(request)
    if old:
        with db() as c:c.execute('DELETE FROM sessions WHERE sid=?',(old['sid'],))
    raw,csrf=new_session(row['id']);u=safe_user(row);audit(u,'login','sesi pengelola')
    return put_cookie(JSONResponse({'user':u,'csrf':csrf}),raw)

@app.post('/api/logout')
async def logout(request:Request):
    csrf_guard(request); s=session(request)
    with db() as c:c.execute('DELETE FROM sessions WHERE sid=?',(s['sid'],))
    raw,csrf=new_session()
    return put_cookie(JSONResponse({'ok':True,'csrf':csrf,'user':None}),raw)

@app.post('/api/password')
async def change_password(request:Request):
    u=guard(request,write=True);d=await payload(request)
    old=d.get('old_password','');new=d.get('new_password','')
    if not isinstance(old,str) or not 1<=len(old)<=128:raise HTTPException(400,'Kata sandi lama tidak sah.')
    rate(request,'password',8,900);validate_password(new)
    with db() as c:stored=c.execute('SELECT password_hash FROM users WHERE id=?',(u['id'],)).fetchone()[0]
    if not await run_in_threadpool(password_ok,old,stored):raise HTTPException(400,'Kata sandi lama tidak sesuai.')
    if old==new:raise HTTPException(400,'Kata sandi baru harus berbeda.')
    hashed=await run_in_threadpool(password_hash,new)
    with db() as c:
        c.execute('UPDATE users SET password_hash=?,force_change=0 WHERE id=?',(hashed,u['id']))
        c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
    raw,csrf=new_session(u['id']);u['force_change']=0;audit(u,'ganti kata sandi','akun sendiri')
    return put_cookie(JSONResponse({'ok':True,'user':u,'csrf':csrf}),raw)

@app.get('/api/public')
def public_data():
    with db() as c:
        posts=[dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM posts ORDER BY id DESC')]
        svcs=[dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM services')]
    return {'settings':settings(),'posts':[p for p in posts if p['status']=='published'],
      'services':sorted([s for s in svcs if s['active']],key=lambda x:x['sort_order'])}

@app.get('/api/admin/overview')
def overview(request:Request):
    u=guard(request)
    with db() as c:
        ps=[json.loads(r[0]) for r in c.execute('SELECT data FROM posts')]
        req=[]
        if u['role']!='editor':
            req=[dict(r) for r in c.execute('SELECT id,code,service_name,name,status,created_at FROM requests ORDER BY id DESC LIMIT 6')]
        return {'published':sum(p['status']=='published' for p in ps),'draft':sum(p['status']=='draft' for p in ps),
         'media':c.execute('SELECT COUNT(*) FROM media WHERE is_private=0').fetchone()[0],
         'requests':c.execute('SELECT COUNT(*) FROM requests').fetchone()[0] if u['role']!='editor' else None,
         'pending':c.execute("SELECT COUNT(*) FROM requests WHERE status NOT IN ('Selesai','Ditolak')").fetchone()[0] if u['role']!='editor' else None,
         'recent_requests':req}

@app.get('/api/admin/posts')
def all_posts(request:Request):
    guard(request,{'superadmin','admin','editor'})
    with db() as c:return [dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM posts ORDER BY id DESC')]

def clean_post(d,old=None):
    p={};p['kind']=text(d.get('kind',''),25,True)
    if p['kind'] not in KINDS:raise HTTPException(400,'Jenis konten tidak dikenali.')
    for k,limit,required in [('title',200,True),('category',100,False),('excerpt',500,False),('body',100000,False),('duration',30,False),('location',200,False),('credit',500,False)]:
        p[k]=text(d.get(k,''),limit,required)
    for k in ['image','attachment','source','video_url']:p[k]=safe_url(d.get(k,''))
    if p['image'].startswith('/files/') or p['attachment'].startswith('/files/'):
        with db() as c:
            for key in ['image','attachment']:
                if p[key].startswith('/files/'):
                    m=c.execute('SELECT * FROM media WHERE id=?',(p[key].split('/')[-1],)).fetchone()
                    if not m or m['is_private']:raise HTTPException(400,'Konten publik hanya boleh memakai berkas publik.')
                    if key=='image' and not m['mime'].startswith('image/'):raise HTTPException(400,'Sampul harus berupa gambar.')
    p['status']=d.get('status','draft')
    if p['status'] not in {'draft','published'}:raise HTTPException(400,'Status konten tidak sah.')
    p['is_demo']=bool(d.get('is_demo',False));p['event_date']=text(d.get('event_date',''),32)
    if p['event_date']:
        try:datetime.fromisoformat(p['event_date'])
        except ValueError:raise HTTPException(400,'Tanggal agenda tidak sah.')
    p['created_at']=old.get('created_at',now()) if old else now();p['updated_at']=now()
    return p

@app.post('/api/admin/posts')
async def create_post(request:Request):
    u=guard(request,{'superadmin','admin','editor'},True);p=clean_post(await payload(request))
    with db() as c:
        cur=c.execute('INSERT INTO posts(data) VALUES (?)',(json.dumps(p,ensure_ascii=False),));p['id']=cur.lastrowid
    audit(u,'tambah konten',p['title']);return p

@app.put('/api/admin/posts/{pid}')
async def edit_post(pid:int,request:Request):
    u=guard(request,{'superadmin','admin','editor'},True)
    with db() as c:r=c.execute('SELECT data FROM posts WHERE id=?',(pid,)).fetchone()
    if not r:raise HTTPException(404,'Konten tidak ditemukan.')
    p=clean_post(await payload(request),json.loads(r[0]));p['id']=pid
    with db() as c:c.execute('UPDATE posts SET data=? WHERE id=?',(json.dumps(p,ensure_ascii=False),pid))
    audit(u,'sunting konten',p['title']);return p

@app.delete('/api/admin/posts/{pid}')
def delete_post(pid:int,request:Request):
    u=guard(request,{'superadmin','admin','editor'},True)
    with db() as c:
        if not c.execute('SELECT 1 FROM posts WHERE id=?',(pid,)).fetchone():raise HTTPException(404,'Konten tidak ditemukan.')
        c.execute('DELETE FROM posts WHERE id=?',(pid,))
    audit(u,'hapus konten',pid);return {'ok':True}

@app.get('/api/admin/services')
def all_services(request:Request):
    guard(request,{'superadmin','admin'})
    with db() as c:return [dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM services ORDER BY id')]

def clean_service(d):
    s={}
    for k,limit in [('title',200),('description',1500),('requirements',5000),('procedure',5000),('time_note',1000),('fee_note',1000),('standard_note',2000),('icon',30)]:s[k]=text(d.get(k,''),limit,k=='title')
    s['source']=safe_url(d.get('source',''));s['active']=bool(d.get('active',True))
    try:s['sort_order']=int(d.get('sort_order',99))
    except (ValueError,TypeError):raise HTTPException(400,'Urutan harus berupa angka.')
    return s

@app.post('/api/admin/services')
async def add_service(request:Request):
    u=guard(request,{'superadmin','admin'},True);s=clean_service(await payload(request))
    with db() as c:cur=c.execute('INSERT INTO services(data) VALUES (?)',(json.dumps(s,ensure_ascii=False),));s['id']=cur.lastrowid
    audit(u,'tambah layanan',s['title']);return s

@app.put('/api/admin/services/{sid}')
async def update_service(sid:int,request:Request):
    u=guard(request,{'superadmin','admin'},True);s=clean_service(await payload(request));s['id']=sid
    with db() as c:
        if not c.execute('SELECT 1 FROM services WHERE id=?',(sid,)).fetchone():raise HTTPException(404,'Layanan tidak ditemukan.')
        c.execute('UPDATE services SET data=? WHERE id=?',(json.dumps(s,ensure_ascii=False),sid))
    audit(u,'sunting layanan',s['title']);return s

@app.delete('/api/admin/services/{sid}')
def delete_service(sid:int,request:Request):
    u=guard(request,{'superadmin','admin'},True)
    with db() as c:
        if c.execute('SELECT 1 FROM requests WHERE service_id=?',(sid,)).fetchone():raise HTTPException(409,'Layanan memiliki riwayat permohonan. Nonaktifkan layanan, jangan menghapusnya.')
        if not c.execute('SELECT 1 FROM services WHERE id=?',(sid,)).fetchone():raise HTTPException(404,'Layanan tidak ditemukan.')
        c.execute('DELETE FROM services WHERE id=?',(sid,))
    audit(u,'hapus layanan',sid);return {'ok':True}

@app.put('/api/admin/settings')
async def update_settings(request:Request):
    u=guard(request,{'superadmin','admin'},True);d=await payload(request);s=settings()
    for k in SETTINGS:
        if k not in d:continue
        if k=='review_mode':s[k]=bool(d[k])
        elif k.endswith('_color'):
            if not isinstance(d[k],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',d[k]):raise HTTPException(400,'Warna harus dalam format #RRGGBB.')
            s[k]=d[k]
        elif k.endswith('_url') or k in {'hero_image'}:
            s[k]=safe_url(d[k])
            if s[k].startswith('/files/'):
                with db() as c:m=c.execute('SELECT * FROM media WHERE id=?',(s[k].split('/')[-1],)).fetchone()
                if not m or m['is_private'] or not m['mime'].startswith('image/'):raise HTTPException(400,'Logo dan sampul harus gambar publik.')
        else:s[k]=text(d[k],10000 if k in {'about','history','vision','organization','privacy_text'} else 2000,k=='site_name')
    if s['email'] and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',s['email']):raise HTTPException(400,'Alamat email tidak sah.')
    if not s['review_mode']:
        if u['force_change']:raise HTTPException(400,'Ganti kata sandi awal sebelum menonaktifkan mode peninjauan.')
        if not s['email'] or not s['address'] or not s['phone']:raise HTTPException(400,'Lengkapi alamat, email, dan telepon resmi sebelum peluncuran.')
    with db() as c:c.execute('UPDATE settings SET data=? WHERE id=1',(json.dumps(s,ensure_ascii=False),))
    audit(u,'ubah pengaturan','identitas / tema');return s

async def store_file(upload,private):
    raw=await upload.read(MAX_FILE+1)
    if not raw or len(raw)>MAX_FILE:raise HTTPException(400,'Berkas harus terisi dan maksimal 8 MB.')
    name=Path(str(upload.filename).replace('\\','/')).name[:150] or 'berkas'
    ext=Path(name).suffix.lower()
    if ext in {'.jpg','.jpeg','.png','.webp'}:
        try:
            def process():
                with Image.open(io.BytesIO(raw)) as im:
                    if im.format not in {'JPEG','PNG','WEBP'}:raise ValueError()
                    im=ImageOps.exif_transpose(im)
                    im.thumbnail((3000,3000))
                    im=im.convert('RGBA' if 'A' in im.getbands() else 'RGB')
                    out=io.BytesIO();im.save(out,format='WEBP',quality=88);return out.getvalue()
            raw=await run_in_threadpool(process)
        except Exception:raise HTTPException(400,'Berkas gambar tidak valid atau dimensinya terlalu besar.')
        ext='.webp';mime='image/webp'
    elif ext=='.pdf':
        if not raw.startswith(b'%PDF-'):raise HTTPException(400,'Berkas bukan PDF yang sah.')
        # Conservative content rejection; not a replacement for production antivirus scanning.
        if re.search(rb'/(JavaScript|JS|Launch|EmbeddedFile|OpenAction|AA)\b',raw):raise HTTPException(400,'PDF mengandung fitur aktif atau lampiran tertanam. Gunakan PDF biasa.')
        try:
            reader=await run_in_threadpool(PdfReader,io.BytesIO(raw))
            if reader.is_encrypted or len(reader.pages)>2000:raise ValueError()
        except Exception:raise HTTPException(400,'PDF rusak, terenkripsi, atau terlalu banyak halaman.')
        mime='application/pdf'
    else:raise HTTPException(400,'Hanya gambar JPG, PNG, WebP, atau PDF yang diperbolehkan.')
    mid=secrets.token_hex(16);filename=mid+ext
    (UPLOADS/filename).write_bytes(raw)
    with db() as c:c.execute('INSERT INTO media VALUES (?,?,?,?,?,?,?)',(mid,name,filename,mime,len(raw),int(private),now()))
    return {'id':mid,'name':name,'mime':mime,'size':len(raw),'url':'/files/'+mid,'is_private':bool(private),'created_at':now()}

@app.post('/api/admin/media')
async def upload_media(request:Request):
    u=guard(request,{'superadmin','admin','editor'},True);f=await request.form(max_files=1,max_fields=4)
    upload=f.get('file')
    if not upload or not hasattr(upload,'read'):raise HTTPException(400,'Pilih berkas untuk diunggah.')
    m=await store_file(upload,False);audit(u,'unggah berkas publik',m['name']);return m

@app.get('/api/admin/media')
def media_list(request:Request):
    guard(request,{'superadmin','admin','editor'})
    with db() as c:
        return [{'id':r['id'],'name':r['original_name'],'mime':r['mime'],'size':r['size'],'url':'/files/'+r['id'],'created_at':r['created_at']} for r in c.execute('SELECT * FROM media WHERE is_private=0 ORDER BY created_at DESC')]

@app.get('/files/{mid}')
def get_file(mid:str,request:Request):
    if not re.fullmatch('[a-f0-9]{32}',mid):raise HTTPException(404,'Berkas tidak ditemukan.')
    with db() as c:m=c.execute('SELECT * FROM media WHERE id=?',(mid,)).fetchone()
    if not m:raise HTTPException(404,'Berkas tidak ditemukan.')
    if m['is_private']:guard(request,{'superadmin','admin','operator'})
    path=UPLOADS/m['filename']
    if not path.is_file():raise HTTPException(404,'Berkas tidak tersedia.')
    if m['mime']=='application/pdf':
        return FileResponse(path,media_type=m['mime'],filename=m['original_name'],headers={'Content-Security-Policy':"sandbox; default-src 'none'"})
    return FileResponse(path,media_type=m['mime'])

@app.delete('/api/admin/media/{mid}')
def delete_media(mid:str,request:Request):
    u=guard(request,{'superadmin','admin','editor'},True)
    with db() as c:
        m=c.execute('SELECT * FROM media WHERE id=? AND is_private=0',(mid,)).fetchone()
        if not m:raise HTTPException(404,'Berkas publik tidak ditemukan.')
        url='/files/'+mid
        for row in c.execute('SELECT data FROM posts'):
            if url in row[0]:raise HTTPException(409,'Berkas masih dipakai konten. Lepaskan dari konten terlebih dahulu.')
        if url in json.dumps(settings()):raise HTTPException(409,'Berkas masih dipakai pada identitas atau sampul website.')
        c.execute('DELETE FROM media WHERE id=?',(mid,))
    (UPLOADS/m['filename']).unlink(missing_ok=True);audit(u,'hapus berkas',m['original_name']);return {'ok':True}

@app.post('/api/requests')
async def submit_request(request:Request):
    csrf_guard(request);rate(request,'submit',8,3600)
    f=await request.form(max_files=1,max_fields=15)
    if f.get('website'):raise HTTPException(400,'Permohonan tidak dapat diproses.')
    if f.get('consent') not in {'true','on','1'}:raise HTTPException(400,'Persetujuan penggunaan data diperlukan.')
    try:sid=int(f.get('service_id',''))
    except (ValueError,TypeError):raise HTTPException(400,'Pilih layanan.')
    with db() as c:r=c.execute('SELECT data FROM services WHERE id=?',(sid,)).fetchone()
    if not r or not json.loads(r[0])['active']:raise HTTPException(400,'Layanan tidak tersedia.')
    service=json.loads(r[0]);name=text(f.get('name',''),150,True);email=text(f.get('email',''),254,True)
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):raise HTTPException(400,'Alamat email tidak sah.')
    phone=text(f.get('phone',''),40);institution=text(f.get('institution',''),200)
    message=text(f.get('message',''),12000,True)
    if len(message)<15:raise HTTPException(400,'Jelaskan kebutuhan minimal 15 karakter.')
    attachments=[];upload=f.get('file')
    if upload and getattr(upload,'filename',''):attachments.append(await store_file(upload,True))
    code='BPK-'+datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d')+'-'+secrets.token_hex(4).upper()
    key=secrets.token_urlsafe(18);t=now();demo=settings()['review_mode']
    history=[{'status':'Diterima','message':'Permohonan tercatat dan menunggu pemeriksaan pengelola.','at':t,'type':'status'}]
    with db() as c:
        c.execute('INSERT INTO requests(code,access_hash,service_id,service_name,name,email,phone,institution,message,status,attachments,history,created_at,updated_at,is_demo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (code,digest(key),sid,service['title'],name,email,phone,institution,message,'Diterima',json.dumps(attachments),json.dumps(history),t,t,int(demo)))
    audit(None,'permohonan baru',code)
    return {'code':code,'access_key':key,'status':'Diterima','is_demo':demo}

def verified_request(code,key):
    with db() as c:r=c.execute('SELECT * FROM requests WHERE code=?',(code.upper(),)).fetchone()
    if not r or not hmac.compare_digest(digest(key),r['access_hash']):raise HTTPException(404,'Nomor tiket atau kunci lacak tidak sesuai.')
    return dict(r)

@app.post('/api/track')
async def track(request:Request):
    csrf_guard(request);rate(request,'track',30,600);d=await payload(request)
    r=verified_request(text(d.get('code',''),50,True),text(d.get('access_key',''),100,True))
    return {k:json.loads(r[k]) if k=='history' else r[k] for k in ['code','service_name','status','public_reply','history','created_at','updated_at','is_demo']}

@app.post('/api/requests/followup')
async def followup(request:Request):
    csrf_guard(request);rate(request,'followup',15,3600)
    f=await request.form(max_files=1,max_fields=5)
    r=verified_request(text(f.get('code',''),50,True),text(f.get('access_key',''),100,True))
    if r['status'] in {'Selesai','Ditolak'}:raise HTTPException(400,'Permohonan sudah ditutup. Silakan buat permohonan baru.')
    message=text(f.get('message',''),5000,True);attachments=json.loads(r['attachments'])
    if len(attachments)>=10:raise HTTPException(400,'Maksimal 10 lampiran per permohonan.')
    upload=f.get('file')
    if upload and getattr(upload,'filename',''):attachments.append(await store_file(upload,True))
    history=json.loads(r['history']);history.append({'status':r['status'],'message':message,'type':'pemohon','at':now()})
    with db() as c:c.execute('UPDATE requests SET attachments=?,history=?,updated_at=? WHERE id=?',(json.dumps(attachments),json.dumps(history),now(),r['id']))
    return {'ok':True}

@app.get('/api/admin/requests')
def requests_list(request:Request):
    guard(request,{'superadmin','admin','operator'})
    with db() as c:
        rows=[dict(r) for r in c.execute('SELECT id,code,service_name,name,email,phone,status,assigned_to,created_at,is_demo FROM requests ORDER BY id DESC')]
    return rows

@app.get('/api/admin/requests/{rid}')
def request_detail(rid:int,request:Request):
    guard(request,{'superadmin','admin','operator'})
    with db() as c:r=c.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
    if not r:raise HTTPException(404,'Permohonan tidak ditemukan.')
    d=dict(r);d.pop('access_hash');d['attachments']=json.loads(d['attachments']);d['history']=json.loads(d['history']);return d

@app.put('/api/admin/requests/{rid}')
async def request_update(rid:int,request:Request):
    u=guard(request,{'superadmin','admin','operator'},True);d=await payload(request)
    status=d.get('status','')
    if status not in STATES:raise HTTPException(400,'Status tidak sah.')
    reply=text(d.get('public_reply',''),5000);note=text(d.get('internal_note',''),5000)
    assigned=d.get('assigned_to') or None
    with db() as c:
        r=c.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
        if not r:raise HTTPException(404,'Permohonan tidak ditemukan.')
        if assigned and not c.execute("SELECT 1 FROM users WHERE id=? AND active=1 AND role IN ('superadmin','admin','operator')",(assigned,)).fetchone():raise HTTPException(400,'Petugas tidak sah.')
        history=json.loads(r['history'])
        if status!=r['status'] or reply!=r['public_reply']:
            history.append({'status':status,'message':reply or 'Status permohonan diperbarui oleh pengelola.','type':'status','at':now()})
        c.execute('UPDATE requests SET status=?,public_reply=?,internal_note=?,assigned_to=?,history=?,updated_at=? WHERE id=?',(status,reply,note,assigned,json.dumps(history),now(),rid))
    audit(u,'tindak lanjut permohonan',r['code']);return {'ok':True}

@app.delete('/api/admin/requests/{rid}')
def request_delete(rid:int,request:Request):
    u=guard(request,{'superadmin','admin'},True)
    with db() as c:
        r=c.execute('SELECT * FROM requests WHERE id=?',(rid,)).fetchone()
        if not r:raise HTTPException(404,'Permohonan tidak ditemukan.')
        for m in json.loads(r['attachments']):
            stored=c.execute('SELECT * FROM media WHERE id=? AND is_private=1',(m['id'],)).fetchone()
            if stored:
                (UPLOADS/stored['filename']).unlink(missing_ok=True);c.execute('DELETE FROM media WHERE id=?',(m['id'],))
        c.execute('DELETE FROM requests WHERE id=?',(rid,))
    audit(u,'hapus permohonan dan lampiran privat',r['code']);return {'ok':True}

@app.get('/api/admin/assignees')
def assignees(request:Request):
    guard(request,{'superadmin','admin','operator'})
    with db() as c:return [dict(r) for r in c.execute("SELECT id,display_name FROM users WHERE active=1 AND role IN ('superadmin','admin','operator')")]

@app.get('/api/admin/users')
def users(request:Request):
    guard(request,{'superadmin'})
    with db() as c:return [safe_user(r) for r in c.execute('SELECT * FROM users ORDER BY id')]

@app.post('/api/admin/users')
async def add_user(request:Request):
    u=guard(request,{'superadmin'},True);d=await payload(request)
    username=text(d.get('username',''),64,True);name=text(d.get('display_name',''),100,True)
    if not re.fullmatch('[A-Za-z0-9_.-]{3,64}',username):raise HTTPException(400,'Username 3–64 karakter, huruf/angka/titik/garis bawah/tanda hubung.')
    pw=d.get('password','');validate_password(pw);role=d.get('role','editor')
    if role not in ROLES:raise HTTPException(400,'Peran tidak sah.')
    hashed=await run_in_threadpool(password_hash,pw)
    try:
        with db() as c:
            c.execute('INSERT INTO users(username,display_name,password_hash,role,active,force_change,created_at) VALUES(?,?,?,?,?,?,?)',
             (username,name,hashed,role,int(bool(d.get('active',True))),1,now()))
    except sqlite3.IntegrityError:raise HTTPException(409,'Username sudah digunakan.')
    audit(u,'tambah pengguna',username);return {'ok':True}

@app.put('/api/admin/users/{uid}')
async def edit_user(uid:int,request:Request):
    u=guard(request,{'superadmin'},True);d=await payload(request)
    role=d.get('role','editor');active=int(bool(d.get('active',True)));name=text(d.get('display_name',''),100,True)
    if role not in ROLES:raise HTTPException(400,'Peran tidak sah.')
    if uid==u['id'] and (role!='superadmin' or not active):raise HTTPException(400,'Anda tidak dapat menonaktifkan atau menurunkan peran akun sendiri.')
    pw=d.get('password','');hashed=None
    if pw:validate_password(pw);hashed=await run_in_threadpool(password_hash,pw)
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        old=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not old:raise HTTPException(404,'Pengguna tidak ditemukan.')
        if old['role']=='superadmin' and old['active'] and (role!='superadmin' or not active):
            if c.execute("SELECT COUNT(*) FROM users WHERE role='superadmin' AND active=1").fetchone()[0]<=1:raise HTTPException(400,'Minimal satu superadmin harus tetap aktif.')
        c.execute('UPDATE users SET display_name=?,role=?,active=? WHERE id=?',(name,role,active,uid))
        if hashed:c.execute('UPDATE users SET password_hash=?,force_change=1 WHERE id=?',(hashed,uid))
        if hashed or role!=old['role'] or active!=old['active']:c.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    audit(u,'sunting pengguna',old['username']);return {'ok':True}

@app.delete('/api/admin/users/{uid}')
def delete_user(uid:int,request:Request):
    u=guard(request,{'superadmin'},True)
    if uid==u['id']:raise HTTPException(400,'Anda tidak dapat menghapus akun sendiri.')
    with db() as c:
        c.execute('BEGIN IMMEDIATE')
        r=c.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        if not r:raise HTTPException(404,'Akun tidak ditemukan.')
        if r['role']=='superadmin' and r['active'] and c.execute("SELECT COUNT(*) FROM users WHERE role='superadmin' AND active=1").fetchone()[0]<=1:raise HTTPException(400,'Minimal satu superadmin harus aktif.')
        c.execute('DELETE FROM users WHERE id=?',(uid,))
    audit(u,'hapus pengguna',r['username']);return {'ok':True}

@app.get('/api/admin/audit')
def audit_list(request:Request):
    guard(request,{'superadmin','admin'})
    with db() as c:return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 500')]

def export_rows(dataset):
    with db() as c:
        if dataset=='requests':
            rows=[dict(r) for r in c.execute('SELECT * FROM requests ORDER BY id DESC')]
            for r in rows:r.pop('access_hash',None)
            return rows
        if dataset=='posts':return [dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM posts')]
        if dataset=='services':return [dict(json.loads(r['data']),id=r['id']) for r in c.execute('SELECT * FROM services')]
        if dataset=='users':return [safe_user(r) for r in c.execute('SELECT * FROM users')]
        if dataset=='audit':return [dict(r) for r in c.execute('SELECT * FROM audit')]
    raise HTTPException(400,'Dataset tidak dikenali.')

def csv_bytes(rows):
    out=io.StringIO();fields=list(rows[0]) if rows else ['keterangan']
    writer=csv.DictWriter(out,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    for r in rows:
        safe={}
        for k,v in r.items():
            if isinstance(v,(dict,list)):v=json.dumps(v,ensure_ascii=False)
            if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@','\t','\r')):v="'"+v
            safe[k]=v
        writer.writerow(safe)
    return ('\ufeff'+out.getvalue()).encode('utf-8')

@app.get('/api/admin/export')
def export(request:Request,dataset:str='requests',format:str='csv'):
    u=guard(request)
    allowed={'superadmin':{'requests','posts','services','users','audit','all'},'admin':{'requests','posts','services','audit'},'editor':{'posts'},'operator':{'requests'}}[u['role']]
    if dataset not in allowed:raise HTTPException(403,'Tidak memiliki izin ekspor dataset ini.')
    if dataset=='all':
        if format!='zip':raise HTTPException(400,'Ekspor lengkap menggunakan ZIP.')
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for kind in ['requests','posts','services','users','audit']:z.writestr(kind+'.json',json.dumps(export_rows(kind),ensure_ascii=False,indent=2))
            z.writestr('settings.json',json.dumps(settings(),ensure_ascii=False,indent=2))
            z.writestr('README.txt','Ekspor data beserta berkas; bukan cadangan login. Hash kata sandi, sesi, dan kunci lacak tidak disertakan. Mengandung data pribadi: simpan secara aman. Gunakan backup.py untuk cadangan pemulihan penuh.')
            with db() as c:
                media=[dict(r) for r in c.execute('SELECT * FROM media')]
            z.writestr('media.json',json.dumps(media,ensure_ascii=False,indent=2))
            for m in media:
                p=UPLOADS/m['filename']
                if p.is_file():z.write(p,'uploads/'+m['filename'])
        raw=out.getvalue();mime='application/zip'
    else:
        rows=export_rows(dataset)
        if format=='csv':raw=csv_bytes(rows);mime='text/csv; charset=utf-8'
        elif format=='json':raw=json.dumps(rows,ensure_ascii=False,indent=2).encode();mime='application/json'
        else:raise HTTPException(400,'Format ekspor tidak dikenali.')
    audit(u,'ekspor data',dataset)
    return Response(raw,media_type=mime,headers={'Content-Disposition':f'attachment; filename="bpk-kaltim-{dataset}-{datetime.now():%Y%m%d}.{format}"'})

@app.get('/health')
def health():return {'status':'ok'}

@app.get('/')
@app.get('/admin')
def homepage():return FileResponse(ROOT/'static'/'index.html',media_type='text/html')

app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')

if __name__=='__main__':
    import uvicorn
    print('\nBPK KALTIM — buka http://127.0.0.1:8000\nAkun instalasi pertama: Febryanto / @dmin123, kecuali telah diganti atau diatur melalui lingkungan.\n')
    uvicorn.run(app,host=os.environ.get('BPK_HOST','127.0.0.1'),port=int(os.environ.get('PORT','8000')),proxy_headers=False)
