"""Independent verification of the composite-beam profile, not an arbitrary CAE validator."""
import json,pathlib,re,shutil
import ai2abaqus as core
from evaluation import evaluate
from inp_audit import audit

def numeric(run_dir,ws,out,abaqus,timeout):
 out.mkdir(parents=True,exist_ok=True)
 proc=core.child_run([abaqus,'python',str(core.ROOT/'scripts/extract_odb.py'),str(run_dir/'beam.odb'),str(ws/'spec.json'),str(ws/'case.json'),str(out/'extracted.json')],out,timeout)
 if proc['exitcode']!=0 or proc['timeout'] or not (out/'extracted.json').is_file():return {'passed':False,'extraction_process':proc,'error':'Independent ODB extraction failed'}
 case=core.load(ws/'case.json');spec=core.load(ws/'spec.json');ex=core.load(out/'extracted.json')
 reference=core.ASSET/'reference'/('tied.json' if case['connection']=='tied' else 'sliding.json')
 v=evaluate((run_dir/'beam.inp').read_text(encoding='utf-8-sig'),(run_dir/'result.csv').read_text(encoding='utf-8-sig'),ex,core.load(reference),spec,case)
 frame_ok=abs(ex['frame_value']-1.0)<1e-6
 v.update(extraction_process=proc,completion_frame_passed=frame_ok,reference_sha256=core.sha(reference),spec_sha256=core.sha(ws/'spec.json'))
 v['passed']=v['passed'] and frame_ok
 core.save(out/'numeric.json',v);return v

def verify(ws,run_id,abaqus,timeout=900):
 ws,m=core.session(ws);core.target_check(m);core.contract_check(ws)
 core.require(re.fullmatch(r'r[0-9]{4}',run_id) is not None,'Invalid run identifier')
 d=core.inside(ws,'runs/'+run_id);run=core.load(d/'run.json')
 core.require(run['passed'],'Software did not complete; inspect the recorded failure before verification')
 core.require(set(run['hashes'])==set(core.ARTIFACTS),'Run manifest lacks required artefact hashes')
 core.require(all(core.sha(d/n)==h for n,h in run['hashes'].items()),'Run artefacts changed after execution')
 core.require(run['review']['source_sha256']==core.sha(d/'build.py'),'Executed source differs from reviewed source')
 abq=core.executable(abaqus);out=core.reserve(ws/'verification','v')
 report={'schema_version':1,'profile':m['profile'],'case_id':m['case_id'],'kind':m['kind'],'run_id':run_id,'verification_id':out.name,'source_sha256':core.sha(d/'build.py'),'passed':False,'created_utc':core.now()}
 report['original']=numeric(d,ws,out/'original',abq,timeout)
 if report['original']['passed']:
  reopen=out/'reopen';reopen.mkdir()
  code='from abaqus import *\nfrom abaqusConstants import *\nopenMdb(pathName='+json.dumps(str(d/'model.cae'))+')\nj=mdb.Job(name="audit",model="BeamModel")\nj.writeInput()\n'
  (reopen/'reopen.py').write_text(code,encoding='utf-8')
  proc=core.child_run([abq,'cae','noGUI=reopen.py'],reopen,timeout);report['cae_reopen_process']=proc
  if proc['exitcode']==0 and not proc['timeout'] and (reopen/'audit.inp').exists():report['cae_audit']=audit((reopen/'audit.inp').read_text(encoding='utf-8-sig'),core.load(ws/'spec.json'),core.load(ws/'case.json'))
  else:report['cae_audit']={'passed':False,'error':'Saved CAE could not be reopened and exported'}
  if report['cae_audit']['passed']:
   replay=out/'replay';report['replay_run']=core.run_source(d/'build.py',d/'case.json',replay,abq,timeout)
   if report['replay_run']['passed']:report['replay_numeric']=numeric(replay,ws,out/'replay_check',abq,timeout)
 report['passed']=bool(report['original']['passed'] and report.get('cae_audit',{}).get('passed') and report.get('replay_run',{}).get('passed') and report.get('replay_numeric',{}).get('passed'))
 report['original_hashes_unchanged']=all(core.sha(d/n)==h for n,h in run['hashes'].items());report['passed']=report['passed'] and report['original_hashes_unchanged']
 core.save(out/'report.json',report);core.save(ws/'report.json',report)
 (ws/'report.md').write_text('# AI2abaqus verification\n\nCase: '+m['case_id']+'\n\nTechnical acceptance: '+str(report['passed'])+'\n\nEvidence: verification/'+out.name+'/report.json\n\nKind: '+m['kind']+'; teacher/student contribution is not inferred from a successful solve.\n',encoding='utf-8')
 m['stage']='independently_verified' if report['passed'] else 'verification_failed';m['latest_verification']=out.name;core.save(ws/'session.json',m)
 return report
