import copy,csv,io,json,pathlib,sys,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'scripts'))
from unittest import mock
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import run_replay
import ai2abaqus as w
FIXTURE=pathlib.Path(__file__).resolve().parent/'fixtures'
from evaluation import evaluate
from inp_audit import audit

class WorkflowTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.ws=pathlib.Path(self.tmp.name)/'task'
  w.initialize(self.ws,'tied','region','unit-vm','mock')
 def tearDown(self):self.tmp.cleanup()
 def prediction(self):w.predict(self.ws,'developer','Predict a stiffness-weighted neutral axis near Y=20 mm, not geometric mid-height.')
 def patch(self):
  p={'model':'qwen3.7-plus','source_sha256':w.sha(self.ws/'source/build.py'),'old':'region=p.cells','new':"region=p.Set(name='SOLID',cells=p.cells)",'explanation':'Use a named Region-compatible set.'};w.save(self.ws/'incoming.json',p);return p
 def test_license_failure_is_not_a_code_failure(self):
  e=w.classify_failure('Cannot connect to license server system. FlexNet Licensing error:-15,10032');self.assertEqual(e['stage'],'environment');self.assertEqual(e['category'],'license_unavailable')
 def test_region_error_is_distinguished_from_environment(self):
  e=w.classify_failure('TypeError: region; found CellArray, expecting Region');self.assertEqual(e['stage'],'script');self.assertEqual(e['category'],'region_type')
 def test_replay_stops_at_first_license_failure(self):
  output=pathlib.Path(self.tmp.name)/'license-blocked';argv=['run_replay.py','--output',str(output),'--abaqus','unused-native-launcher','--target-id','test-vm']
  with mock.patch.object(sys,'argv',argv),mock.patch.object(w,'run',return_value={'passed':False,'failure':{'stage':'environment','category':'license_unavailable'}}) as run:
   self.assertEqual(run_replay.main(),1);self.assertEqual(run.call_count,1)
  report=w.load(output/'validation.json');self.assertEqual(report['cases'],[]);self.assertFalse(report['passed'])
 def test_init_does_not_overwrite_work(self):
  with self.assertRaises(w.WorkflowError):w.initialize(self.ws,'tied','reference','x')
 def test_contract_is_immutable(self):
  c=w.load(self.ws/'case.json');c['total_load_N']=1000;w.save(self.ws/'case.json',c)
  with self.assertRaises(w.WorkflowError):w.contract_check(self.ws)
 def test_target_mismatch_stops_before_compute(self):
  m=w.load(self.ws/'session.json');m['target']['hostname']='not-this-authorized-vm'
  with self.assertRaises(w.WorkflowError):w.target_check(m)
 def test_prediction_required_before_execution(self):
  w.review(self.ws,'developer','Intentional Region fault demonstration')
  with self.assertRaises(w.WorkflowError):w.run(self.ws,'nonexistent-abaqus')
 def test_prediction_cannot_be_rewritten_after_results(self):
  self.prediction()
  with self.assertRaises(w.WorkflowError):self.prediction()
 def test_patch_stale_source_rejected(self):
  self.prediction();p=self.patch();(self.ws/'source/build.py').write_text('changed',encoding='utf-8')
  with self.assertRaises(w.WorkflowError):w.apply_patch(self.ws,self.ws/'incoming.json')
 def test_patch_keeps_before_after_and_role(self):
  self.prediction();self.patch();out=w.apply_patch(self.ws,self.ws/'incoming.json')
  d=self.ws/'patches'/out['patch_id'];self.assertTrue((d/'before.py').is_file());self.assertTrue((d/'after.py').is_file());self.assertEqual(w.load(d/'provenance.json')['kind'],'model_suggestion_pending_review')
 def test_developer_correction_is_not_attributed_to_model(self):
  self.prediction();p=self.patch();p.pop('model');p['author_role']='developer';w.save(self.ws/'incoming.json',p);r=w.apply_patch(self.ws,self.ws/'incoming.json');v=w.load(self.ws/'patches'/r['patch_id']/'provenance.json');self.assertIsNone(v['model']);self.assertEqual(v['author_role'],'developer')
 def test_bad_patch_syntax_leaves_source_unchanged(self):
  self.prediction();p=self.patch();before=w.sha(self.ws/'source/build.py');p['new']='(' ;w.save(self.ws/'incoming.json',p)
  with self.assertRaises(w.WorkflowError):w.apply_patch(self.ws,self.ws/'incoming.json')
  self.assertEqual(w.sha(self.ws/'source/build.py'),before)
 def test_source_edit_invalidates_review(self):
  self.prediction();w.review(self.ws,'developer','Check the intended fault');(self.ws/'source/build.py').write_text('pass',encoding='utf-8')
  with self.assertRaises(w.WorkflowError):w.run(self.ws,'nonexistent-abaqus')
 def test_submission_path_escape_rejected(self):
  w.save(self.ws/'process.json',{'physics':'../outside.txt'});(self.ws.parent/'outside.txt').write_text('outside')
  with self.assertRaises(w.WorkflowError):w.evidence_packet(self.ws,self.ws/'process.json')
 def feedback_setup(self):
  w.save(self.ws/'process.json',{});r=w.evidence_packet(self.ws,self.ws/'process.json')
  return {'evidence_sha256':r['evidence_sha256'],'dimensions':[{'id':k,'score':0,'reason':'No submitted evidence','evidence_refs':['F1']} for k in w.WEIGHTS],'missing_evidence':['process files'],'next_actions':['submit actual files']}
 def test_source_change_invalidates_collected_feedback(self):
  f=self.feedback_setup();(self.ws/'source/build.py').write_text('pass',encoding='utf-8');w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_process_file_change_invalidates_feedback(self):
  p=self.ws/'physics.txt';p.write_text('Original submitted evidence');w.save(self.ws/'process.json',{'physics':'physics.txt'});r=w.evidence_packet(self.ws,self.ws/'process.json');f={'evidence_sha256':r['evidence_sha256'],'dimensions':[{'id':k,'score':0,'reason':'Missing','evidence_refs':['F1']} for k in w.WEIGHTS],'missing_evidence':[],'next_actions':[]};p.write_text('Changed after submission');w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_old_passed_report_cannot_grade_new_source(self):
  w.save(self.ws/'verification/v0001/report.json',{'passed':True,'source_sha256':'outdated-source','run_id':'r0001'});w.save(self.ws/'process.json',{})
  with self.assertRaises(w.WorkflowError):w.evidence_packet(self.ws,self.ws/'process.json')
 def test_resubmission_preserves_original_packet(self):
  w.save(self.ws/'process.json',{});a=w.evidence_packet(self.ws,self.ws/'process.json');old_path=self.ws/a['packet_path'];old_hash=w.sha(old_path);b=w.evidence_packet(self.ws,self.ws/'process.json')
  self.assertNotEqual(a['submission_id'],b['submission_id']);self.assertEqual(w.sha(old_path),old_hash);self.assertEqual(w.load(self.ws/'submission/evidence.json')['submission_id'],b['submission_id'])
 def test_prediction_edit_invalidates_feedback(self):
  self.prediction();f=self.feedback_setup();p=w.load(self.ws/'prediction.json');p['statement']='Changed after results';w.save(self.ws/'prediction.json',p);w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_verification_report_edit_invalidates_feedback(self):
  p=self.ws/'verification/v0001/report.json';w.save(p,{'passed':False});f=self.feedback_setup();w.save(p,{'passed':True});w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_undefined_feedback_reference_is_preserved_and_rejected(self):
  f=self.feedback_setup();f['dimensions'][0]['evidence_refs']=['invented'];w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
  self.assertEqual(len(list((self.ws/'submission/reports').glob('f*/rejected.json'))),1)
 def test_ai_cannot_finalize_teacher_score(self):
  f=self.feedback_setup();f['teacher_final_score']=100;w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_stale_feedback_rejected(self):
  f=self.feedback_setup();f['evidence_sha256']='0'*64;w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_feedback_score_bounds_and_bool_rejected(self):
  f=self.feedback_setup();f['dimensions'][0]['score']=True;w.save(self.ws/'feedback.json',f)
  with self.assertRaises(w.WorkflowError):w.accept_feedback(self.ws,self.ws/'feedback.json')
 def test_accepted_feedback_keeps_teacher_pending(self):
  f=self.feedback_setup();w.save(self.ws/'feedback.json',f);r=w.accept_feedback(self.ws,self.ws/'feedback.json')
  self.assertIsNone(r['teacher_final_score']);self.assertFalse(r['technical_passed']);self.assertEqual(r['teacher_status'],'pending_review')

class PhysicalAuditTests(unittest.TestCase):
 def setUp(self):
  self.spec=w.load(w.ASSET/'spec.json');self.case=next(c for c in self.spec['cases'] if c['connection']=='tied');self.inp=(FIXTURE/'tied.inp').read_text(encoding='utf-8')
 def test_actual_tied_deck_passes(self):self.assertTrue(audit(self.inp,self.spec,self.case)['passed'])
 def test_successful_tied_solve_does_not_satisfy_sliding_task(self):
  case=next(c for c in self.spec['cases'] if c['connection']=='sliding');a=audit(self.inp,self.spec,case);self.assertFalse(a['passed']);self.assertIn('INTERFACE_KIND',{x['code'] for x in a['errors']})
 def test_changed_material_rejected(self):
  altered=self.inp.replace('75000.', '70000.').replace('75000,','70000,');self.assertNotEqual(altered,self.inp);self.assertFalse(audit(altered,self.spec,self.case)['passed'])
 def test_unexpanded_include_rejected(self):self.assertFalse(audit(self.inp+'\n*INCLUDE, INPUT=hidden.inp\n',self.spec,self.case)['passed'])
 def test_relabelled_csv_values_rejected(self):
  extracted=w.load(FIXTURE/'tied_extracted.json');text=(FIXTURE/'tied.csv').read_text();rows=list(csv.DictReader(io.StringIO(text)));rows[1]['strain']='0.0123';buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
  self.assertFalse(evaluate(self.inp,buf.getvalue(),extracted,extracted,self.spec,self.case)['passed'])
 def test_balance_residual_is_independent_acceptance_condition(self):
  ex=w.load(FIXTURE/'tied_extracted.json');bad=copy.deepcopy(ex);bad['force_residual_relative']=.1
  self.assertFalse(evaluate(self.inp,(FIXTURE/'tied.csv').read_text(),bad,ex,self.spec,self.case)['passed'])
if __name__=='__main__':unittest.main()
