"""AI2abaqus: evidence-oriented CAE workflow. Python 3.10+, standard library."""
import argparse,ast,datetime,hashlib,json,os,pathlib,platform,shutil,signal,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
ASSET=ROOT/'assets/composite-beam'
WEIGHTS={'understanding':20,'ai_review':20,'iteration':25,'physics':25,'reflection':10}
ARTIFACTS=['build.py','case.json','model.cae','beam.inp','beam.odb','result.csv']
class WorkflowError(RuntimeError):pass
def require(condition,message):
 if not condition:raise WorkflowError(message)
def load(p):return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def save(p,value):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def inside(root,relative):
 root=pathlib.Path(root).resolve();p=(root/relative).resolve()
 require(p.is_relative_to(root),'Path escapes the session');return p
def reserve(root,prefix):
 root.mkdir(parents=True,exist_ok=True)
 for i in range(1,10000):
  p=root/('%s%04d'%(prefix,i))
  try:p.mkdir();return p
  except FileExistsError:continue
 raise WorkflowError('Too many records')
def session(ws):
 ws=pathlib.Path(ws).resolve();m=load(ws/'session.json')
 require(m['profile']=='composite-beam-v1','Unsupported validation profile')
 return ws,m
def target_check(m):
 require(m['target']['hostname']==platform.node(),'Target mismatch: execute on the machine bound during init; never silently fall back locally')
def initialize(ws,case,mode,target_id,kind='developer-demo'):
 ws=pathlib.Path(ws).resolve();require(not ws.exists() or not any(ws.iterdir()),'Init requires a new/empty session directory')
 spec=load(ASSET/'spec.json');cid=('tied_' if case=='tied' else 'sliding_')+'aluminum_steel'
 case_data=next(x for x in spec['cases'] if x['case_id']==cid)
 if mode=='region':require(case=='tied','Region exercise is the tied task');source=ASSET/'exercise_region.py'
 elif mode=='interface':require(case=='sliding','Interface exercise is the sliding task');source=ASSET/'build_tied.py'
 else:require(mode=='reference','Unknown mode');source=ASSET/('build_'+case+'.py')
 (ws/'source').mkdir(parents=True);shutil.copyfile(source,ws/'source/build.py')
 save(ws/'case.json',case_data);save(ws/'spec.json',spec)
 m={'schema_version':1,'profile':'composite-beam-v1','case_id':cid,'mode':mode,'kind':kind,'model':'qwen3.7-plus','target':{'id':target_id,'hostname':platform.node()},'created_utc':now(),'stage':'prepared','source_origin':'reviewed developer baseline; not autonomous AI generation'}
 save(ws/'session.json',m);save(ws/'contract_hashes.json',{'case.json':sha(ws/'case.json'),'spec.json':sha(ws/'spec.json')})
 return m
def contract_check(ws):
 require(all(sha(ws/n)==h for n,h in load(ws/'contract_hashes.json').items()),'Task contract changed; create a new explicitly defined session')
def predict(ws,role,note):
 ws,m=session(ws);target_check(m);contract_check(ws)
 require(role in ['developer','teacher','student'] and note.strip(),'Identify the actual author and physical prediction')
 require(not (ws/'prediction.json').exists() and not (ws/'runs').exists() and not (ws/'patches').exists(),'Pre-run prediction is immutable; put later corrections in reflection evidence')
 v={'role':role,'statement':note,'kind':m['kind'],'utc':now(),'case_sha256':sha(ws/'case.json')};save(ws/'prediction.json',v)
 m['stage']='predicted';save(ws/'session.json',m);return v

def apply_patch(ws,patch):
 ws,m=session(ws);target_check(m);contract_check(ws);require((ws/'prediction.json').is_file(),'Record a physical prediction before requesting a patch');p=load(patch);src=ws/'source/build.py';before=src.read_text(encoding='utf-8')
 role=p.get('author_role','model');require(role in ['model','developer','teacher','student'],'Unknown patch author role')
 if role=='model':require(p.get('model')=='qwen3.7-plus','This research profile fixes qwen3.7-plus')
 else:require(p.get('model') is None,'Human/developer revisions must not be attributed to a model')
 require(p.get('source_sha256')==sha(src),'Patch is stale: source hash mismatch')
 old,new=p.get('old'),p.get('new')
 require(isinstance(old,str) and old and before.count(old)==1,'Old code must match one exact source span')
 require(isinstance(new,str) and new!=old and len(new)<10000,'Invalid local replacement')
 require(isinstance(p.get('explanation'),str) and bool(p['explanation'].strip()),'Patch explanation is required')
 after=before.replace(old,new,1)
 try:ast.parse(after)
 except SyntaxError as e:raise WorkflowError('Patch syntax: '+str(e))
 d=reserve(ws/'patches','p');shutil.copyfile(src,d/'before.py');save(d/'patch.json',p)
 src.write_text(after,encoding='utf-8');shutil.copyfile(src,d/'after.py')
 save(d/'provenance.json',{'kind':('model_suggestion_pending_review' if role=='model' else role+'_revision_pending_review'),'utc':now(),'before_sha256':p['source_sha256'],'after_sha256':sha(src),'model':p.get('model'),'author_role':role,'receipt_provided':bool(p.get('receipt_sha256'))})
 m['stage']='patch_pending_review';save(ws/'session.json',m);return {'patch_id':d.name,'source_sha256':sha(src)}
def review(ws,role,note,decision='accept'):
 ws,m=session(ws);target_check(m);contract_check(ws)
 require(role in ['developer','teacher','student'],'Review role must identify the actual reviewer')
 require(note.strip(),'Review reasoning is required')
 v={'source_sha256':sha(ws/'source/build.py'),'role':role,'decision':decision,'reason':note,'utc':now(),'kind':m['kind']}
 d=reserve(ws/'reviews','r');save(d/'review.json',v);save(ws/'review.json',v)
 m['stage']='reviewed' if decision=='accept' else 'review_rejected';save(ws/'session.json',m);return v
def child_run(argv,cwd,timeout):
 cwd=pathlib.Path(cwd);start=now();t=time.monotonic();timed=False
 opts={'cwd':str(cwd),'stdin':subprocess.DEVNULL,'shell':False}
 if os.name=='nt':opts['creationflags']=subprocess.CREATE_NO_WINDOW
 else:opts['start_new_session']=True
 with (cwd/'stdout.log').open('wb') as out,(cwd/'stderr.log').open('wb') as err:
  p=subprocess.Popen([str(x) for x in argv],stdout=out,stderr=err,**opts)
  try:code=p.wait(timeout=timeout)
  except subprocess.TimeoutExpired:
   timed=True
   if os.name=='nt':
    killer=pathlib.Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/taskkill.exe'
    subprocess.run([str(killer),'/PID',str(p.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
   else:os.killpg(p.pid,signal.SIGKILL)
   try:code=p.wait(timeout=10)
   except subprocess.TimeoutExpired:code=None
 return {'pid':p.pid,'exitcode':code,'timeout':timed,'started_utc':start,'finished_utc':now(),'elapsed_seconds':round(time.monotonic()-t,3),'argv':[str(x) for x in argv]}
def executable(p):
 found=shutil.which(str(p));require(found is not None,'Abaqus executable not found; supply --abaqus native launcher path')
 require(pathlib.Path(found).suffix.lower() not in ['.bat','.cmd'],'Use the native Windows SMALauncher.exe instead of a batch launcher')
 return str(pathlib.Path(found).resolve())
def classify_failure(text,timed_out=False):
 text=text.lower()
 if timed_out:return {'stage':'environment','category':'execution_timeout'}
 if any(s in text for s in ['flexnet licensing error','cannot connect to license server','license checkout failed','unable to checkout']):return {'stage':'environment','category':'license_unavailable'}
 if 'cellarray' in text and 'region' in text:return {'stage':'script','category':'region_type'}
 if 'name is empty' in text or 'abaqusnameerror' in text:return {'stage':'script','category':'api_argument'}
 if 'has no attribute' in text or 'attributeerror' in text:return {'stage':'script','category':'api_attribute'}
 if 'syntaxerror' in text:return {'stage':'script','category':'python_syntax'}
 if 'analysis has not been completed' in text or 'too many attempts' in text:return {'stage':'solver','category':'solver_failed'}
 return {'stage':'unknown','category':'incomplete_or_unclassified'}

def run_source(source,case,d,abaqus,timeout):
 d.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,d/'build.py');shutil.copyfile(case,d/'case.json')
 p=child_run([abaqus,'cae','noGUI=build.py'],d,timeout)
 sta=(d/'beam.sta').read_text(encoding='utf-8',errors='replace') if (d/'beam.sta').exists() else ''
 complete='THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in sta and 'THE ANALYSIS HAS NOT BEEN COMPLETED' not in sta and not (d/'beam.lck').exists()
 exists=all((d/n).is_file() and (d/n).stat().st_size>0 for n in ARTIFACTS)
 hashes={n:sha(d/n) for n in ARTIFACTS if (d/n).is_file()}
 v={'process':p,'solver_completed':complete,'artifacts_present':exists,'passed':p['exitcode']==0 and not p['timeout'] and complete and exists,'hashes':hashes}
 if not v['passed']:
  text='\n'.join((d/n).read_text(encoding='utf-8',errors='replace')[-30000:] for n in ['stdout.log','stderr.log','beam.msg','beam.sta'] if (d/n).is_file())
  v['failure']=classify_failure(text,p['timeout'])
 save(d/'run.json',v);return v
def run(ws,abaqus,timeout=900):
 ws,m=session(ws);target_check(m);contract_check(ws);require((ws/'prediction.json').is_file(),'Record a physical prediction before execution');r=load(ws/'review.json')
 require(r['decision']=='accept' and r['source_sha256']==sha(ws/'source/build.py'),'Current source requires an explicit, hash-matched review record')
 d=reserve(ws/'runs','r');v=run_source(ws/'source/build.py',ws/'case.json',d,executable(abaqus),timeout)
 v.update(run_id=d.name,review=r,kind=m['kind']);save(d/'run.json',v)
 m['stage']='software_completed_pending_physics' if v['passed'] else 'environment_blocked' if v['failure']['stage']=='environment' else 'software_failed';m['latest_run']=d.name;save(ws/'session.json',m);return v

def evidence_packet(ws,process_files):
 ws,m=session(ws);contract_check(ws);files=load(process_files);require(isinstance(files,dict),'Process files must be a mapping')
 allowed=set(WEIGHTS);require(set(files)<=allowed,'Unknown rubric dimension')
 reports=sorted((ws/'verification').glob('v*/report.json')) if (ws/'verification').exists() else []
 report=load(reports[-1]) if reports else None
 bindings={'source/build.py':sha(ws/'source/build.py'),'case.json':sha(ws/'case.json'),'spec.json':sha(ws/'spec.json')}
 if (ws/'prediction.json').is_file():bindings['prediction.json']=sha(ws/'prediction.json')
 if reports:bindings[str(reports[-1].relative_to(ws))]=sha(reports[-1])
 if report and report['passed']:
  require(report['source_sha256']==bindings['source/build.py'],'Current submission source differs from the verified source')
  rd=inside(ws,'runs/'+report['run_id']);run=load(rd/'run.json')
  for name,h in run['hashes'].items():
   require(sha(rd/name)==h,'Verified artefacts changed before submission');bindings[str((rd/name).relative_to(ws))]=h
 facts={'F1':{'kind':'independent_verification','passed':bool(report and report['passed']),'report':str(reports[-1].relative_to(ws)) if report else None},'F2':{'kind':'rubric','weights':WEIGHTS,'teacher_final_score':None},'F3':{'kind':'recorded_prediction_not_verified_understanding','record':load(ws/'prediction.json') if (ws/'prediction.json').exists() else None}}
 for key,rel in files.items():
  p=inside(ws,rel);require(p.is_file(),'Missing process evidence: '+rel)
  bindings[rel]=sha(p)
  facts['P_'+key]={'kind':'submitted_process_text_not_verified_understanding','path':rel,'sha256':sha(p),'text':p.read_text(encoding='utf-8-sig')[:12000]}
 packet={'schema_version':1,'kind':m['kind'],'model':m['model'],'case_id':m['case_id'],'technical_passed':facts['F1']['passed'],'bindings':bindings,'evidence':facts,'teacher_final_score':None}
 d=reserve(ws/'submission/packets','s');packet['submission_id']=d.name
 save(d/'evidence.json',packet);shutil.copyfile(d/'evidence.json',ws/'submission/evidence.json')
 return {'submission_id':d.name,'packet_path':str((d/'evidence.json').relative_to(ws)),'evidence_sha256':sha(d/'evidence.json'),'evidence_ids':list(facts),'technical_passed':packet['technical_passed']}
def checked_feedback(packet,f,evidence_hash):
 require(isinstance(f,dict) and set(f)=={'evidence_sha256','dimensions','missing_evidence','next_actions'},'Feedback schema mismatch; teacher final score cannot be supplied by AI')
 require(f['evidence_sha256']==evidence_hash,'Stale feedback evidence hash')
 dims=f['dimensions'];require(isinstance(dims,list) and len(dims)==5 and all(isinstance(x,dict) for x in dims) and {x.get('id') for x in dims}==set(WEIGHTS),'Exactly five distinct rubric dimensions are required')
 for x in dims:
  require(type(x.get('score')) is int and 0<=x['score']<=WEIGHTS[x['id']],'Score outside rubric')
  require(isinstance(x.get('reason'),str) and bool(x['reason'].strip()),'Feedback reason is required')
  refs=x.get('evidence_refs');require(isinstance(refs,list) and bool(refs) and all(isinstance(y,str) for y in refs) and set(refs)<=set(packet['evidence']),'Undefined evidence reference')
 require(all(isinstance(f[k],list) and all(isinstance(x,str) for x in f[k]) for k in ['missing_evidence','next_actions']),'Feedback action lists are required')
 return sum(x['score'] for x in dims)
def accept_feedback(ws,feedback):
 ws,m=session(ws);packet=load(ws/'submission/evidence.json');f=load(feedback);d=reserve(ws/'submission/reports','f');save(d/'received.json',f)
 try:
  require(all(sha(inside(ws,n))==h for n,h in packet['bindings'].items()),'Submission files changed after evidence collection; collect a new submission version')
  score=checked_feedback(packet,f,sha(ws/'submission/evidence.json'))
 except WorkflowError as e:save(d/'rejected.json',{'passed':False,'error':str(e),'utc':now()});raise
 out={'kind':m['kind'],'model':m['model'],'technical_passed':packet['technical_passed'],'suggested_score':score,'teacher_final_score':None,'teacher_status':'pending_review','feedback':f,'utc':now()}
 save(d/'feedback.json',out);return out

def main():
 p=argparse.ArgumentParser(description='AI2abaqus: reviewed execution and independent evidence for composite-beam teaching');sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('init');a.add_argument('--workspace',required=True);a.add_argument('--case',choices=['tied','sliding'],required=True);a.add_argument('--mode',choices=['reference','region','interface'],default='reference');a.add_argument('--target-id',required=True);a.add_argument('--kind',choices=['developer-demo','mock','student'],default='developer-demo')
 a=sub.add_parser('predict');a.add_argument('--workspace',required=True);a.add_argument('--role',choices=['developer','teacher','student'],required=True);a.add_argument('--note',required=True)
 a=sub.add_parser('patch');a.add_argument('--workspace',required=True);a.add_argument('--input',required=True)
 a=sub.add_parser('review');a.add_argument('--workspace',required=True);a.add_argument('--role',choices=['developer','teacher','student'],required=True);a.add_argument('--note',required=True);a.add_argument('--decision',choices=['accept','reject'],default='accept')
 for cmd in ['run','verify']:
  a=sub.add_parser(cmd);a.add_argument('--workspace',required=True);a.add_argument('--abaqus',required=True);a.add_argument('--timeout',type=int,default=900)
  if cmd=='verify':a.add_argument('--run-id',required=True)
 a=sub.add_parser('submission');a.add_argument('--workspace',required=True);a.add_argument('--process-files',required=True)
 a=sub.add_parser('feedback');a.add_argument('--workspace',required=True);a.add_argument('--input',required=True)
 a=sub.add_parser('status');a.add_argument('--workspace',required=True)
 args=p.parse_args()
 try:
  if args.command=='init':v=initialize(args.workspace,args.case,args.mode,args.target_id,args.kind)
  elif args.command=='predict':v=predict(args.workspace,args.role,args.note)
  elif args.command=='patch':v=apply_patch(args.workspace,args.input)
  elif args.command=='review':v=review(args.workspace,args.role,args.note,args.decision)
  elif args.command=='run':v=run(args.workspace,args.abaqus,args.timeout)
  elif args.command=='verify':
   from verify import verify
   v=verify(args.workspace,args.run_id,args.abaqus,args.timeout)
  elif args.command=='submission':v=evidence_packet(args.workspace,args.process_files)
  elif args.command=='feedback':v=accept_feedback(args.workspace,args.input)
  else:
   ws,m=session(args.workspace);v=dict(m,source_sha256=sha(ws/'source/build.py'))
  print(json.dumps(v,ensure_ascii=False,indent=2));return 0 if v.get('passed',True) else 3
 except (WorkflowError,ValueError,OSError,KeyError) as e:
  print(json.dumps({'passed':False,'error':str(e)},ensure_ascii=False),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
