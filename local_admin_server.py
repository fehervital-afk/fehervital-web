from __future__ import annotations
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import base64, json, mimetypes, os, re, secrets, shutil, subprocess, time, uuid
from urllib.parse import urlparse
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parent / 'scripts'))
from automation_policy import evaluate_action, write_audit_event

ROOT=Path(__file__).resolve().parent
CONTENT=ROOT/'assets'/'content'/'pages.json'
UPLOADS=ROOT/'assets'/'uploads'; UPLOADS.mkdir(parents=True,exist_ok=True)
BACKUPS=ROOT/'.local_backups'; BACKUPS.mkdir(parents=True,exist_ok=True)
PREVIEW_CONTENT={'data':None}
AUTOMATION_PATH=ROOT/'assets'/'content'/'automation.json'
AI_TASKS_PATH=ROOT/'assets'/'content'/'ai_tasks.json'
AI_AUDIT_PATH=ROOT/'assets'/'content'/'ai_audit.json'
AI_LOG_PATH=ROOT/'assets'/'content'/'ai_log.json'
MARKETING_PATH=ROOT/'assets'/'content'/'marketing.json'
EXECUTION_PATH=ROOT/'assets'/'content'/'execution_queue.json'
AUTOPILOT_PATH=ROOT/'assets'/'content'/'autopilot.json'
CONTENT_GENERATOR_PATH=ROOT/'assets'/'content'/'content_generator.json'
AGENTS_PATH=ROOT/'assets'/'content'/'agents.json'
CEO_PATH=ROOT/'assets'/'content'/'ceo.json'
BOS_PATH=ROOT/'assets'/'content'/'business_os.json'
WEEKLY_REPORT_PATH=ROOT/'assets'/'content'/'weekly_report.json'
BUSINESS_MEMORY_PATH=ROOT/'assets'/'content'/'business_memory.json'
BI_PATH=ROOT/'assets'/'content'/'business_intelligence.json'
STRATEGIC_GOALS_PATH=ROOT/'assets'/'content'/'strategic_goals.json'
ALLOWED_IMAGE={'.jpg','.jpeg','.png','.webp','.gif'}
ALLOWED_VIDEO={'.mp4','.webm','.ogg'}
MAX_IMAGE=15*1024*1024; MAX_VIDEO=90*1024*1024
ADMIN_CSRF_TOKEN=secrets.token_urlsafe(32)

def local_admin_request_allowed(host:str, origin:str|None, token:str|None, require_token=True)->bool:
    try:
        hostname=(urlparse('//' + str(host or '')).hostname or '').lower()
    except Exception:
        return False
    if hostname not in {'localhost','127.0.0.1'}:
        return False
    if origin:
        try:
            parsed=urlparse(origin)
            if parsed.scheme not in {'http','https'} or (parsed.hostname or '').lower() not in {'localhost','127.0.0.1'}:
                return False
        except Exception:
            return False
    if require_token and not secrets.compare_digest(str(token or ''), ADMIN_CSRF_TOKEN):
        return False
    return True

def safe_media_path(rel:str)->Path:
    rel=rel.replace('\\','/').lstrip('/')
    if not rel.startswith('assets/uploads/'): raise ValueError('Csak a médiatár fájljai kezelhetők.')
    p=(ROOT/rel).resolve()
    if UPLOADS.resolve() not in p.parents: raise ValueError('Érvénytelen médiaútvonal.')
    return p

def create_backup():
    if not CONTENT.exists(): return None
    stamp=time.strftime('%Y%m%d-%H%M%S')
    target=BACKUPS/f'pages-{stamp}-{uuid.uuid4().hex[:5]}.json'
    shutil.copy2(CONTENT,target)
    files=sorted(BACKUPS.glob('pages-*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    for old in files[25:]: old.unlink(missing_ok=True)
    return target.name

def media_list():
    out=[]
    for p in sorted(UPLOADS.iterdir(),key=lambda x:x.stat().st_mtime,reverse=True):
        if not p.is_file(): continue
        ext=p.suffix.lower(); kind='image' if ext in ALLOWED_IMAGE else 'video' if ext in ALLOWED_VIDEO else 'other'
        if kind=='other': continue
        st=p.stat(); out.append({'name':p.name,'path':f'assets/uploads/{p.name}','kind':kind,'size':st.st_size,'modified':int(st.st_mtime)})
    return out

class Handler(SimpleHTTPRequestHandler):
    def translate_path(self,path):
        raw=super().translate_path(path); rel=Path(raw).relative_to(Path.cwd()); return str(ROOT/rel)
    def end_headers(self):
        self.send_header('Cache-Control','no-store'); self.send_header('X-Content-Type-Options','nosniff'); super().end_headers()
    def _json(self,data,status=200):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8'); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def _read_json(self,max_bytes=130*1024*1024):
        n=int(self.headers.get('Content-Length','0') or 0)
        if n<=0 or n>max_bytes: raise ValueError('Érvénytelen vagy túl nagy kérés.')
        return json.loads(self.rfile.read(n).decode('utf-8'))
    def do_GET(self):
        if urlparse(self.path).path == '/__admin/security-token':
            if not local_admin_request_allowed(self.headers.get('Host',''), self.headers.get('Origin'), None, require_token=False):
                self._json({'error':'Local admin origin rejected.'},403); return
            self._json({'token':ADMIN_CSRF_TOKEN},200); return
        if self.path == '/__admin/ai-state':
            def loadj(p, default):
                try: return json.loads(p.read_text(encoding='utf-8'))
                except Exception: return default
            self._json({
                'automation': loadj(AUTOMATION_PATH, {}),
                'tasks': loadj(AI_TASKS_PATH, {'tasks':[]}),
                'audit': loadj(AI_AUDIT_PATH, {}),
                'log': loadj(AI_LOG_PATH, {'version':1,'entries':[]})
            },200)
            return
        if self.path == '/__admin/bi-state':
            def _load(p,default):
                try: return json.loads(p.read_text(encoding='utf-8'))
                except Exception: return default
            self._json({
                'bi':_load(BI_PATH,{}),
                'goals':_load(STRATEGIC_GOALS_PATH,{'goals':[]})
            },200)
            return

        if self.path == '/__admin/bos-state':
            def _load(p,default):
                try: return json.loads(p.read_text(encoding='utf-8'))
                except Exception: return default
            self._json({
                'bos':_load(BOS_PATH,{}),
                'weekly':_load(WEEKLY_REPORT_PATH,{}),
                'memory':_load(BUSINESS_MEMORY_PATH,{})
            },200)
            return

        if self.path == '/__admin/ceo-state':
            try: ceo=json.loads(CEO_PATH.read_text(encoding='utf-8'))
            except Exception: ceo={}
            self._json({'ceo':ceo},200)
            return

        if self.path == '/__admin/content-generator-state':
            try: content=json.loads(CONTENT_GENERATOR_PATH.read_text(encoding='utf-8'))
            except Exception: content={}
            try: agents=json.loads(AGENTS_PATH.read_text(encoding='utf-8'))
            except Exception: agents={}
            self._json({'content':content,'agents':agents},200)
            return

        if self.path == '/__admin/autopilot-state':
            try:
                data=json.loads(AUTOPILOT_PATH.read_text(encoding='utf-8'))
            except Exception:
                data={}
            self._json(data,200)
            return

        if self.path == '/__admin/execution-state':
            try:
                data=json.loads(EXECUTION_PATH.read_text(encoding='utf-8'))
            except Exception:
                data={'version':1,'settings':{},'items':[],'history':[]}
            self._json(data,200)
            return

        if self.path == '/__admin/task-center':
            try:
                q=json.loads(AI_TASKS_PATH.read_text(encoding='utf-8'))
            except Exception:
                q={'version':2,'tasks':[]}
            self._json(q,200)
            return

        if self.path == '/__admin/marketing-state':
            try:
                data=json.loads(MARKETING_PATH.read_text(encoding='utf-8'))
            except Exception:
                data={}
            self._json(data,200)
            return

        if self.path == '/__admin/preview-content':
            data = PREVIEW_CONTENT.get('data')
            if data is None:
                try:
                    data = json.loads((ROOT / 'assets' / 'content' / 'pages.json').read_text(encoding='utf-8'))
                except Exception:
                    data = {}
            self._json(data,200)
            return

        p=urlparse(self.path).path
        if p=='/__admin/content':
            try:self._json(json.loads(CONTENT.read_text(encoding='utf-8')))
            except Exception as e:self._json({'error':str(e)},500)
            return
        if p=='/__admin/media': self._json({'items':media_list()}); return
        if p=='/__admin/backups':
            items=[{'name':x.name,'modified':int(x.stat().st_mtime),'size':x.stat().st_size} for x in sorted(BACKUPS.glob('pages-*.json'),key=lambda q:q.stat().st_mtime,reverse=True)]
            self._json({'items':items}); return
        if p in ('/admin','/admin/'):
            self.send_response(302); self.send_header('Location','/_local_admin/index.html'); self.end_headers(); return
        return super().do_GET()
    def do_POST(self):
        if not local_admin_request_allowed(self.headers.get('Host',''), self.headers.get('Origin'),
                                           self.headers.get('X-Fehervital-CSRF'), require_token=True):
            self._json({'error':'Unsafe local admin request rejected.'},403); return
        if self.path in ('/__admin/ai-approve','/__admin/ai-reject'):
            data = self._read_json()
            task_id = str(data.get('id','')).strip()
            if not task_id:
                self._json({'error':'Hiányzó feladatazonosító.'},400); return
            arg = '--approve-task' if self.path.endswith('ai-approve') else '--reject-task'
            try:
                p = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts' / 'ai_webmaster.py'), arg, task_id],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=30
                )
                if p.returncode != 0:
                    self._json({'error':(p.stderr or p.stdout or 'A művelet sikertelen.').strip()},400); return
                try: payload = json.loads((p.stdout or '{}').strip())
                except Exception: payload = {'ok':True}
                self._json(payload,200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/bi-refresh':
            try:
                p=subprocess.run([sys.executable,str(ROOT/'scripts'/'business_intelligence.py'),'--refresh'],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=90)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Business Intelligence frissítési hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/strategic-goal':
            data=self._read_json()
            try: g=json.loads(STRATEGIC_GOALS_PATH.read_text(encoding='utf-8'))
            except Exception: g={'version':1,'goals':[]}
            gid=str(data.get('id') or '').strip()
            goal=next((x for x in g.get('goals',[]) if str(x.get('id'))==gid),None)
            if not goal:
                self._json({'error':'Stratégiai cél nem található.'},404); return
            for k in ('title','horizon','target','unit','status','owner'):
                if k in data: goal[k]=data[k]
            goal['updated_at']=datetime.now(timezone.utc).isoformat()
            g['updated_at']=goal['updated_at']
            STRATEGIC_GOALS_PATH.write_text(json.dumps(g,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'goal':goal},200)
            return

        if self.path == '/__admin/bos-refresh':
            try:
                p=subprocess.run([sys.executable,str(ROOT/'scripts'/'ceo_orchestrator.py'),'--refresh-bos'],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=60)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Business OS frissítési hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/weekly-report':
            try:
                p=subprocess.run([sys.executable,str(ROOT/'scripts'/'ceo_orchestrator.py'),'--weekly'],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=60)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Heti jelentés hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/business-memory':
            data=self._read_json()
            try: mem=json.loads(BUSINESS_MEMORY_PATH.read_text(encoding='utf-8'))
            except Exception: mem={'version':1,'wins':[],'experiments':[],'lessons':[]}
            text=str(data.get('text') or '').strip()
            bucket=str(data.get('bucket') or 'lessons')
            if bucket not in ('wins','experiments','lessons'): bucket='lessons'
            if not text:
                self._json({'error':'A memória szövege kötelező.'},400); return
            item={'time':datetime.now(timezone.utc).isoformat(),'text':text,'source':'admin'}
            mem.setdefault(bucket,[]).append(item)
            mem['updated_at']=item['time']
            BUSINESS_MEMORY_PATH.write_text(json.dumps(mem,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'memory':mem},200)
            return

        if self.path == '/__admin/ceo-run':
            data=self._read_json()
            args=[sys.executable,str(ROOT/'scripts'/'ceo_orchestrator.py'),'--run']
            if not bool(data.get('use_ai',True)): args.append('--no-ai')
            if not bool(data.get('create_tasks',True)): args.append('--no-tasks')
            try:
                p=subprocess.run(args,cwd=str(ROOT),capture_output=True,text=True,timeout=180)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'AI Cégvezető hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/ceo-settings':
            data=self._read_json()
            try: ceo=json.loads(CEO_PATH.read_text(encoding='utf-8'))
            except Exception: ceo={}
            if 'enabled' in data: ceo['enabled']=bool(data['enabled'])
            if 'mode' in data: ceo['mode']=data['mode']
            if 'primary_goal' in data: ceo['primary_goal']=data['primary_goal']
            CEO_PATH.write_text(json.dumps(ceo,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'ceo':ceo},200)
            return

        if self.path == '/__admin/content-generate':
            data=self._read_json()
            kind=str(data.get('kind') or 'article')
            topic=str(data.get('topic') or '').strip()
            page=str(data.get('page') or '').strip()
            if not topic:
                self._json({'error':'A téma megadása kötelező.'},400); return
            args=[sys.executable,str(ROOT/'scripts'/'content_generator.py'),'--generate',kind,'--topic',topic]
            if page: args += ['--page',page]
            try:
                p=subprocess.run(args,cwd=str(ROOT),capture_output=True,text=True,timeout=120)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Tartalomgenerálási hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/content-qa':
            data=self._read_json()
            draft_id=str(data.get('id') or '')
            try:
                p=subprocess.run([sys.executable,str(ROOT/'scripts'/'content_generator.py'),'--qa',draft_id],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=60)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'QA hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/content-send-webmaster':
            data=self._read_json()
            draft_id=str(data.get('id') or '')
            try:
                p=subprocess.run([sys.executable,str(ROOT/'scripts'/'content_generator.py'),'--send',draft_id],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=60)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Átadási hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/brand-memory':
            data=self._read_json()
            try: st=json.loads(CONTENT_GENERATOR_PATH.read_text(encoding='utf-8'))
            except Exception: st={}
            st.setdefault('brand_memory',{})
            for k in ('brand_name','tone','audience','must_include','avoid'):
                if k in data: st['brand_memory'][k]=data[k]
            CONTENT_GENERATOR_PATH.write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'brand_memory':st['brand_memory']},200)
            return

        if self.path == '/__admin/agents-settings':
            data=self._read_json()
            try: ag=json.loads(AGENTS_PATH.read_text(encoding='utf-8'))
            except Exception: ag={}
            for a in ag.get('agents',[]):
                if str(a.get('id')) in data.get('enabled',{}):
                    a['enabled']=bool(data['enabled'][str(a.get('id'))])
            if 'mode' in data:
                ag.setdefault('orchestration',{})['mode']=data['mode']
            AGENTS_PATH.write_text(json.dumps(ag,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'agents':ag},200)
            return

        if self.path == '/__admin/autopilot-run':
            try:
                p=subprocess.run(
                    [sys.executable,str(ROOT/'scripts'/'autopilot.py'),'--run'],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=240
                )
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Autopilot hiba.').strip()},400); return
                try: payload=json.loads((p.stdout or '{}').strip() or '{}')
                except Exception: payload={'ok':True,'stdout':p.stdout}
                self._json(payload,200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/autopilot-settings':
            data=self._read_json()
            try: cfg=json.loads(AUTOPILOT_PATH.read_text(encoding='utf-8'))
            except Exception: cfg={}
            for k in ('enabled','auto_apply_low_risk','rollback_on_score_drop'):
                if k in data: cfg[k]=bool(data[k])
            for k in ('mode','interval_minutes','max_score_drop'):
                if k in data: cfg[k]=data[k]
            AUTOPILOT_PATH.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'autopilot':cfg},200)
            return

        if self.path == '/__admin/execution-sync':
            try:
                p=subprocess.run(
                    [sys.executable,str(ROOT/'scripts'/'executor_engine.py'),'--sync'],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=30
                )
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Szinkronizálási hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path in ('/__admin/execution-approve','/__admin/execution-reject','/__admin/execution-rollback'):
            data=self._read_json()
            item_id=str(data.get('id','')).strip()
            if not item_id:
                self._json({'error':'Hiányzó végrehajtási azonosító.'},400); return
            arg='--approve' if self.path.endswith('approve') else '--reject' if self.path.endswith('reject') else '--rollback'
            try:
                p=subprocess.run(
                    [sys.executable,str(ROOT/'scripts'/'executor_engine.py'),arg,item_id],
                    cwd=str(ROOT),capture_output=True,text=True,timeout=45
                )
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Végrehajtási hiba.').strip()},400); return
                self._json(json.loads((p.stdout or '{}').strip() or '{}'),200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/execution-settings':
            data=self._read_json()
            try: q=json.loads(EXECUTION_PATH.read_text(encoding='utf-8'))
            except Exception: q={'version':1,'settings':{},'items':[],'history':[]}
            q.setdefault('settings',{})
            for k in ('enabled','auto_mode','auto_apply_low_risk','create_backup_before_apply'):
                if k in data: q['settings'][k]=bool(data[k])
            EXECUTION_PATH.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'settings':q['settings']},200)
            return

        if self.path == '/__admin/task-update':
            data=self._read_json()
            task_id=str(data.get('id','')).strip()
            if not task_id:
                self._json({'error':'Hiányzó feladatazonosító.'},400); return
            try:
                q=json.loads(AI_TASKS_PATH.read_text(encoding='utf-8'))
            except Exception:
                q={'version':2,'tasks':[]}
            task=next((t for t in q.get('tasks',[]) if str(t.get('id'))==task_id),None)
            if not task:
                self._json({'error':'Feladat nem található.'},404); return
            allowed={'status','priority','category','impact','reason','owner'}
            for k in allowed:
                if k in data:
                    task[k]=data[k]
            task['updated_at']=datetime.now(timezone.utc).isoformat()
            AI_TASKS_PATH.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'task':task},200)
            return

        if self.path == '/__admin/task-delete':
            data=self._read_json()
            task_id=str(data.get('id','')).strip()
            try:
                q=json.loads(AI_TASKS_PATH.read_text(encoding='utf-8'))
            except Exception:
                q={'version':2,'tasks':[]}
            before=len(q.get('tasks',[]))
            q['tasks']=[t for t in q.get('tasks',[]) if str(t.get('id'))!=task_id]
            if len(q['tasks'])==before:
                self._json({'error':'Feladat nem található.'},404); return
            AI_TASKS_PATH.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True},200)
            return

        if self.path == '/__admin/task-create':
            data=self._read_json()
            prompt=str(data.get('prompt','')).strip()
            if not prompt:
                self._json({'error':'A feladat leírása kötelező.'},400); return
            try:
                q=json.loads(AI_TASKS_PATH.read_text(encoding='utf-8'))
            except Exception:
                q={'version':2,'tasks':[]}
            task={
                'id':str(uuid.uuid4()),
                'prompt':prompt,
                'status':str(data.get('status') or 'pending'),
                'priority':str(data.get('priority') or 'medium'),
                'category':str(data.get('category') or 'manual'),
                'impact':str(data.get('impact') or ''),
                'reason':str(data.get('reason') or ''),
                'owner':str(data.get('owner') or 'AI Webmester'),
                'created_at':datetime.now(timezone.utc).isoformat(),
                'source':'task_center'
            }
            q.setdefault('tasks',[]).append(task)
            AI_TASKS_PATH.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8')
            write_audit_event('task_created',task_id=task['id'],actor='local_admin',action='create_task',
                              target='assets/content/ai_tasks.json',policy_risk='LOW',result='created',
                              reason='Manual task created in local admin.')
            self._json({'ok':True,'task':task},200)
            return

        if self.path == '/__admin/marketing-run':
            data = self._read_json()
            use_ai = bool(data.get('use_ai', True))
            args=[sys.executable, str(ROOT/'scripts'/'marketing_manager.py'), '--analyze']
            if not use_ai: args.append('--no-ai')
            try:
                p=subprocess.run(args,cwd=str(ROOT),capture_output=True,text=True,timeout=120)
                if p.returncode!=0:
                    self._json({'error':(p.stderr or p.stdout or 'Marketing elemzés sikertelen.').strip()},400); return
                self._json({'ok':True,'stdout':p.stdout},200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/marketing-settings':
            data=self._read_json()
            try: cfg=json.loads(MARKETING_PATH.read_text(encoding='utf-8'))
            except Exception: cfg={}
            for k in ('enabled','mode','goal','target_audience','content_cadence'):
                if k in data: cfg[k]=data[k]
            MARKETING_PATH.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'marketing':cfg},200)
            return

        if self.path == '/__admin/marketing-queue':
            data=self._read_json()
            ids=data.get('ids') or []
            try:
                marketing=json.loads(MARKETING_PATH.read_text(encoding='utf-8'))
                q=json.loads(AI_TASKS_PATH.read_text(encoding='utf-8'))
            except Exception as e:
                self._json({'error':str(e)},500); return
            wanted=set(str(x) for x in ids)
            added=[]
            for rec in marketing.get('recommendations') or []:
                if wanted and str(rec.get('id')) not in wanted: continue
                if rec.get('status')=='queued': continue
                prompt=str(rec.get('task_prompt') or '').strip()
                if not prompt: continue
                task={
                    'id':str(uuid.uuid4()),
                    'prompt':prompt,
                    'status':'pending',
                    'created_at':datetime.now(timezone.utc).isoformat(),
                    'source':'ai_marketing_manager',
                    'marketing_recommendation_id':rec.get('id')
                }
                q.setdefault('tasks',[]).append(task)
                rec['status']='queued'
                added.append(task['id'])
            AI_TASKS_PATH.write_text(json.dumps(q,ensure_ascii=False,indent=2),encoding='utf-8')
            MARKETING_PATH.write_text(json.dumps(marketing,ensure_ascii=False,indent=2),encoding='utf-8')
            self._json({'ok':True,'queued':added},200)
            return

        if self.path == '/__admin/ai-task':
            data = self._read_json()
            try:
                q = json.loads(AI_TASKS_PATH.read_text(encoding='utf-8'))
            except Exception:
                q = {'version':1,'tasks':[]}
            task = {
                'id': str(uuid.uuid4()),
                'prompt': str(data.get('prompt','')).strip(),
                'status': 'pending',
                'created_at': datetime.now(timezone.utc).isoformat(),
                'source': 'local_admin'
            }
            if not task['prompt']:
                self._json({'error':'A parancs nem lehet üres.'},400); return
            q.setdefault('tasks', []).append(task)
            AI_TASKS_PATH.write_text(json.dumps(q, ensure_ascii=False, indent=2), encoding='utf-8')
            write_audit_event('task_created',task_id=task['id'],actor='local_admin',action='create_task',
                              target='assets/content/ai_tasks.json',policy_risk='LOW',result='created',
                              reason='AI Webmaster task created in local admin.')
            self._json({'task':task},200)
            return

        if self.path == '/__admin/ai-settings':
            data = self._read_json()
            try:
                cfg = json.loads(AUTOMATION_PATH.read_text(encoding='utf-8'))
            except Exception:
                cfg = {}
            for k in ('enabled','mode','model','booking_url'):
                if k in data: cfg[k] = data[k]
            AUTOMATION_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')
            self._json({'ok':True,'automation':cfg},200)
            return

        if self.path == '/__admin/ai-run-local':
            try:
                p = subprocess.run(
                    [sys.executable, str(ROOT / 'scripts' / 'ai_webmaster.py'), '--audit', '--process'],
                    cwd=str(ROOT), capture_output=True, text=True, timeout=120
                )
                self._json({'ok':p.returncode==0,'stdout':p.stdout,'stderr':p.stderr},200)
            except Exception as e:
                self._json({'error':str(e)},500)
            return

        if self.path == '/__admin/preview-content':
            PREVIEW_CONTENT['data'] = self._read_json()
            self._json({'ok': True},200)
            return


        if self.path == '/__admin/media-upload':
            data = self._read_json()
            filename = Path(str(data.get('filename','upload.bin'))).name
            raw = base64.b64decode(data.get('data_base64',''))
            if len(raw) > 100 * 1024 * 1024:
                self._json({'error':'A fájl túl nagy. Maximum 100 MB.'},400); return
            safe = re.sub(r'[^A-Za-z0-9._-]+','-', filename).strip('-') or 'upload.bin'
            stem = Path(safe).stem
            ext = Path(safe).suffix.lower()
            target = UPLOADS / safe
            n = 2
            while target.exists():
                target = UPLOADS / f"{stem}-{n}{ext}"
                n += 1
            target.write_bytes(raw)
            self._json({'path':'assets/uploads/' + target.name, 'name':target.name},200)
            return

        if self.path == '/__admin/media-delete':
            data = self._read_json()
            name = Path(str(data.get('name',''))).name
            target = UPLOADS / name
            if target.exists() and target.is_file():
                target.unlink()
            self._json({'ok':True},200)
            return

        if self.path == '/__admin/media-rename':
            data = self._read_json()
            old = Path(str(data.get('old',''))).name
            new = Path(str(data.get('new',''))).name
            if not old or not new:
                self._json({'error':'Hiányzó fájlnév.'},400); return
            new = re.sub(r'[^A-Za-z0-9._-]+','-', new).strip('-')
            src = UPLOADS / old
            dst = UPLOADS / new
            if not src.exists():
                self._json({'error':'A fájl nem található.'},404); return
            if dst.exists():
                self._json({'error':'Ilyen nevű fájl már létezik.'},400); return
            src.rename(dst)
            self._json({'path':'assets/uploads/' + dst.name, 'name':dst.name},200)
            return

        p=urlparse(self.path).path
        try:
            if p=='/__admin/content':
                data=self._read_json(8*1024*1024)
                if not isinstance(data,dict) or not isinstance(data.get('pages'),dict): raise ValueError('Hibás tartalomformátum.')
                backup=create_backup(); tmp=CONTENT.with_suffix('.tmp'); tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8'); tmp.replace(CONTENT)
                self._json({'ok':True,'backup':backup}); return
            if p=='/__admin/upload':
                data=self._read_json(); name=Path(str(data.get('filename','file'))).name; ext=Path(name).suffix.lower()
                if ext not in ALLOWED_IMAGE|ALLOWED_VIDEO: raise ValueError('Nem engedélyezett fájltípus.')
                raw=base64.b64decode(data.get('data_base64',''),validate=True); limit=MAX_VIDEO if ext in ALLOWED_VIDEO else MAX_IMAGE
                if len(raw)>limit: raise ValueError('A fájl túl nagy.')
                stem=re.sub(r'[^a-zA-Z0-9_-]+','-',Path(name).stem).strip('-')[:40] or 'media'; safe=f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{stem}{ext}"
                target=UPLOADS/safe; target.write_bytes(raw); self._json({'ok':True,'path':f'assets/uploads/{safe}','size':len(raw),'kind':'video' if ext in ALLOWED_VIDEO else 'image'}); return
            if p=='/__admin/delete-media':
                data=self._read_json(1024*1024); target=safe_media_path(str(data.get('path','')))
                if not target.exists(): raise ValueError('A médiafájl nem található.')
                target.unlink(); self._json({'ok':True}); return
            if p=='/__admin/restore':
                data=self._read_json(1024*1024); name=Path(str(data.get('name',''))).name
                source=BACKUPS/name
                if not source.exists() or not name.startswith('pages-') or source.suffix!='.json': raise ValueError('A biztonsági mentés nem található.')
                create_backup(); shutil.copy2(source,CONTENT); self._json({'ok':True,'content':json.loads(CONTENT.read_text(encoding='utf-8'))}); return
            if p=='/__admin/publish':
                data=self._read_json(1024*1024)
                policy=evaluate_action({'action':'publish','target':'production','target_type':'production'},
                                       approved=True,actor='local_admin',autopilot=False)
                write_audit_event('publish_requested',actor='local_admin',action='publish',target='production',
                                  policy_risk=policy.risk,result='allowed' if policy.allowed else 'blocked',reason=policy.reason)
                if not policy.allowed: raise PermissionError('Explicit human publish confirmation is required.')
                msg=str(data.get('message') or 'Update Fehervital website content')[:120]
                def run(args): return subprocess.run(args,cwd=ROOT,text=True,capture_output=True,timeout=120)
                r=run(['git','add','assets/content/pages.json','assets/uploads','assets/js/app.js','assets/css/style.css','index.html','biorezonancia.html','harmonyscan.html','ai.html','kapcsolat.html','adatkezeles.html','idopontfoglalas.html','_local_admin/index.html','local_admin_server.py','INDITAS_FEHERVITAL_WEB.bat','.gitignore'])
                if r.returncode: raise RuntimeError(r.stderr or r.stdout)
                if any(UPLOADS.iterdir()):
                    r=run(['git','add','assets/uploads']);
                    if r.returncode: raise RuntimeError(r.stderr or r.stdout)
                st=run(['git','status','--porcelain'])
                if not st.stdout.strip(): self._json({'ok':True,'message':'Nincs új változás, nincs mit közzétenni.'}); return
                r=run(['git','commit','-m',msg]);
                if r.returncode: raise RuntimeError(r.stderr or r.stdout)
                r=run(['git','push']);
                if r.returncode: raise RuntimeError(r.stderr or r.stdout)
                self._json({'ok':True,'message':'Sikeres közzététel. A Render automatikusan frissíti az oldalt.','output':r.stdout[-3000:]}); return
            self._json({'error':'Ismeretlen végpont.'},404)
        except Exception as e:self._json({'error':str(e)},500)

if __name__=='__main__':
    os.chdir(ROOT); port=8000; server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    print('='*58); print(' FEHERVITAL WEB - HELYI ADMIN V17 + BUSINESS INTELLIGENCE'); print('='*58)
    print(f' Weboldal: http://127.0.0.1:{port}/'); print(f' Admin:    http://127.0.0.1:{port}/admin/'); print(' Leallitas: Ctrl+C'); print('='*58)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
