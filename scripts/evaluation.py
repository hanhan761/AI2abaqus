"""Composite-beam acceptance; checks real INP, independent ODB extraction and CSV."""
import csv,io,json,math
from inp_audit import audit
def validate_csv(text,spec,extracted):
 errors=[]
 def err(c,m):errors.append({'code':c,'message':m})
 try:
  reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')));rows=list(reader)
  required=['point','instance','x_mm','y_mm','z_mm','component','strain']
  if reader.fieldnames!=required:err('CSV_SCHEMA','CSV列名或顺序不符合指定契约')
  if len(rows)!=10:err('CSV_ROWS','CSV必须恰有P1至P10十行')
  ids=[r.get('point') for r in rows]
  if sorted(ids)!=sorted(p['id'] for p in spec['points']):err('CSV_POINTS','测点存在缺失、重复或错误')
  truth={r['point']:r for r in extracted.get('points',[])}
  for p in spec['points']:
   rr=[r for r in rows if r.get('point')==p['id']]
   if len(rr)!=1:continue
   r=rr[0];ins='TOP' if p['layer']=='top' else 'BOTTOM'
   if r.get('instance','').upper()!=ins or r.get('component')!=p['component']:err('CSV_TARGET_'+p['id'],'实例或应变分量不符')
   if any(abs(float(r[a+'_mm'])-p[a])>1e-5 for a in ['x','y','z']):err('CSV_COORD_'+p['id'],'提取坐标不符')
   value=float(r['strain']);t=float(truth[p['id']]['strain'])
   if not math.isfinite(value) or abs(value-t)>max(1e-10,abs(t)*1e-5):err('CSV_VALUE_'+p['id'],'报告值与独立ODB提取不一致；检查量纲、帧和平均方式')
 except Exception as e:err('CSV_PARSE',str(e))
 return {'passed':not errors,'errors':errors}
def evaluate(inp_text,csv_text,extracted,reference,spec,case):
 structure=audit(inp_text,spec,case);extraction=validate_csv(csv_text,spec,extracted);errors=[];comparisons=[]
 ref={p['point']:float(p['strain']) for p in reference['points']}
 for p in extracted.get('points',[]):
  x=float(p['strain']);r=ref[p['point']];tol=max(spec['acceptance']['absolute_strain_tolerance'],spec['acceptance']['relative_strain_tolerance']*abs(r));passed=math.isfinite(x) and abs(x-r)<=tol
  comparisons.append({'point':p['point'],'strain':x,'reference':r,'absolute_error':abs(x-r),'tolerance':tol,'passed':passed})
  if not passed:errors.append({'code':'STRAIN_'+p['point'],'message':'该测点未满足预注册的绝对/相对混合误差阈值；复核物理模型与提取'})
 if len(comparisons)!=10:errors.append({'code':'ODB_POINTS','message':'独立ODB提取未得到十个测点'})
 for key,limit in [('force_residual_relative','force_balance_relative'),('moment_residual_relative','moment_balance_relative')]:
  if not math.isfinite(extracted.get(key,float('nan'))) or extracted.get(key,float('inf'))>spec['acceptance'][limit]:errors.append({'code':key.upper(),'message':'整体平衡残差超过1%'})
 physics={'passed':not errors,'errors':errors,'comparisons':comparisons}
 return {'passed':structure['passed'] and extraction['passed'] and physics['passed'],'structure':structure,'extraction':extraction,'physics':physics}
