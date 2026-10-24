"""Licensed integration replay. Runs only on the explicitly selected authorized machine."""
import argparse,json,pathlib,platform,sys,traceback
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
import ai2abaqus as w
from verify import verify
from inp_audit import audit

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--abaqus',required=True);p.add_argument('--target-id',required=True);a=p.parse_args();out=pathlib.Path(a.output).resolve()
 w.require(not out.exists() or not any(out.iterdir()),'Replay output must be new; inspect earlier evidence instead of resubmitting unchanged')
 out.mkdir(parents=True,exist_ok=True);summary={'schema_version':1,'version':'0.1.0','kind':'archived_response_replay_and_actual_abaqus_execution','new_model_requests':0,'new_real_student_observations':0,'location':'explicitly selected machine; execution host bound in each private session','cases':[],'passed':False,'started_utc':w.now()}
 try:
  for name in ['region','sliding']:
   recipe=w.load(w.ASSET/'replays'/(name+'.json'));ws=out/name;w.initialize(ws,recipe['case'],recipe['mode'],a.target_id,'developer-demo');w.predict(ws,'developer',recipe['prediction']);stages=[]
   if name=='region':
    w.review(ws,'developer','Explicit teacher-seeded Region fault demonstration; failure is expected and recorded')
    initial=w.run(ws,a.abaqus);w.require(not initial['passed'] and initial.get('failure',{}).get('category')=='region_type','Seed fault was not reached; stop on environment or unrelated failure');stages.append({'stage':'seeded_teacher_fault','actual_run':initial['run_id'],'expected_failure_observed':True})
   active=None
   for i,step in enumerate(recipe['steps'],1):
    p0=step['patch'];old=active if active is not None else p0['old'];patch={'author_role':step['author_role'],'source_sha256':w.sha(ws/'source/build.py'),'old':old,'new':p0['new'],'explanation':p0['explanation'],'replay_kind':recipe['kind'],'old_span_rebased_by_controller':active is not None,'original_receipt_sha256':step.get('original_receipt_sha256')}
    if step['author_role']=='model':patch['model']=step['model'];patch['receipt_sha256']=step['original_receipt_sha256']
    incoming=ws/('replay_patch_%02d.json'%i);w.save(incoming,patch);pr=w.apply_patch(ws,incoming);active=patch['new']
    stages.append({'stage':'patch','patch_id':pr['patch_id'],'author_role':step['author_role'],'original_receipt_sha256':step.get('original_receipt_sha256')})
    if step['expected_run']=='review_only':
     w.review(ws,'developer','Review identifies missing required TOP gauges; do not execute until separately recorded developer correction','reject');continue
    w.review(ws,'developer','Replay review: exact recorded replacement, protected conditions outside span preserved; independent physics audit remains required')
    run=w.run(ws,a.abaqus);expected=step['expected_run']=='pass';w.require(run['passed']==expected,'Software outcome differed from declared replay outcome')
    if not expected:w.require(run.get('failure',{}).get('category')==step['expected_failure_category'],'Stop: the expected script failure was not reached')
    stages.append({'stage':'software','run_id':run['run_id'],'passed':run['passed'],'expected':step['expected_run']})
   grade=verify(ws,run['run_id'],a.abaqus);w.require(grade['passed'],'Independent verification failed')
   inp=(ws/'runs'/run['run_id']/'beam.inp').read_text(encoding='utf-8-sig');spec=w.load(ws/'spec.json');other=next(c for c in spec['cases'] if c['case_id']!=grade['case_id']);counter=audit(inp,spec,other)
   w.require(not counter['passed'],'A solved model must not satisfy the opposite interface task')
   ex=w.load(ws/'verification'/grade['verification_id']/'original/extracted.json')
   row={'case_id':grade['case_id'],'kind':recipe['kind'],'passed':grade['passed'],'stages':stages,'original_software_submissions':len(list((ws/'runs').glob('r*/run.json'))),'cae_reopened':grade['cae_audit']['passed'],'clean_replay_passed':grade['replay_numeric']['passed'],'opposite_task_rejected':not counter['passed'],'force_residual_relative':ex['force_residual_relative'],'moment_residual_relative':ex['moment_residual_relative'],'points':ex['points'],'final_source_sha256':grade['source_sha256']}
   summary['cases'].append(row);w.save(out/'validation.json',summary)
  summary['passed']=all(c['passed'] for c in summary['cases']) and len(summary['cases'])==2
 except Exception as e:summary.update(error=repr(e),traceback=traceback.format_exc())
 summary['finished_utc']=w.now();summary['code_sha256']={p.name:w.sha(p) for p in (w.ROOT/'scripts').glob('*.py')};w.save(out/'validation.json',summary);print(json.dumps({'passed':summary['passed'],'cases':len(summary['cases'])}));return 0 if summary['passed'] else 1
if __name__=='__main__':sys.exit(main())
