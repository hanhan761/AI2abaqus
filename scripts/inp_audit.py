"""Keyword-deck audit independent of generated scripts and self-reports."""
import collections,math,re,pathlib,json

def records(text):
 key=None;params={};data=[]
 for raw in text.splitlines():
  s=raw.strip()
  if not s or s.startswith('**'):continue
  if s.startswith('*'):
   if key is not None:yield key,params,data
   a=[x.strip() for x in s[1:].split(',')];key=a[0].upper();params={};data=[]
   for x in a[1:]:
    if '=' in x:k,v=x.split('=',1);params[k.upper()]=v.strip().strip(chr(34)).upper()
    elif x:params[x.upper()]=True
  else:data.append([x.strip().strip(chr(34)).upper() for x in s.split(',') if x.strip()])
 if key is not None:yield key,params,data

def audit(text,spec,case,odb=None):
 parts={};instances={};sets={};surfaces={};materials={};sections={};ties=[];contacts=[];contact_params=[];props={};boundaries=[];cloads=[];errors=[];part=None;mat=None;prop=None;scope='ASSEMBLY';active_instance=None;nonlinear=False;stabilized=False
 def problem(code,message):errors.append({'code':code,'message':message})
 for key,p,d in records(text):
  if key in {'INCLUDE','MPC','EQUATION','COUPLING','DYNAMIC','VISCO','PLASTIC','USER MATERIAL','SUBMODEL'}:problem('OUTSIDE_PROFILE','Input feature outside the declared beam validation profile: '+key)
  if key=='PART':
   part=p['NAME'];scope=part;parts[part]={'nodes':{},'elements':{},'types':set(),'sections':[]};active_instance=None
  elif key=='END PART':part=None;scope='ASSEMBLY'
  elif key=='INSTANCE':
   active_instance=p['NAME'];instances[active_instance]={'part':p['PART'],'translation':tuple(float(x) for x in d[0]) if d and len(d[0])==3 else (0.,0.,0.)}
   if len(d)>1 or (d and len(d[0])!=3):problem('INSTANCE_TRANSFORM','存在未核验的旋转/变换定义')
  elif key=='END INSTANCE':active_instance=None
  elif key=='NODE' and part:
   for row in d:parts[part]['nodes'][int(row[0])]=tuple(float(x) for x in row[1:4])
  elif key=='ELEMENT' and part:
   typ=p.get('TYPE');parts[part]['types'].add(typ);pending=[];labels=[];n=20 if typ=='C3D20R' else None
   if n is None:problem('ELEMENT_TYPE','单元类型必须为C3D20R')
   else:
    for row in d:
     pending.extend(int(x) for x in row)
     while len(pending)>=n+1:
      eid=pending[0];parts[part]['elements'][eid]=pending[1:n+1];labels.append(eid);pending=pending[n+1:]
    if pending:problem('ELEMENT_CONNECTIVITY','单元连通定义不完整')
   if 'ELSET' in p:sets[(scope,'ELSET',p['ELSET'])]={'instance':None,'items':[str(x) for x in labels]}
  elif key in ('NSET','ELSET'):
   name=p[key];items=[]
   for row in d:
    if 'GENERATE' in p:items.extend(str(x) for x in range(int(row[0]),int(row[1])+1,int(row[2]) if len(row)>2 else 1))
    else:items.extend(row)
   old=sets.setdefault((scope,key,name),{'instance':p.get('INSTANCE'),'items':[]});old['items'].extend(items)
  elif key=='SOLID SECTION' and part:parts[part]['sections'].append(p.get('MATERIAL'))
  elif key=='MATERIAL':mat=p['NAME'];materials[mat]={}
  elif key=='ELASTIC' and mat and d:materials[mat]['elastic']=tuple(float(x) for x in d[0][:2])
  elif key=='SURFACE':surfaces[p['NAME']]={'type':p.get('TYPE','ELEMENT'),'scope':scope,'data':d}
  elif key=='TIE':ties.extend(d)
  elif key=='SURFACE INTERACTION':prop=p['NAME'];props[prop]={'hard':True,'separation':True,'friction':0.,'direct':True}
  elif key=='SURFACE BEHAVIOR' and prop:props[prop]['hard']=p.get('PRESSURE-OVERCLOSURE','HARD')=='HARD';props[prop]['separation']='NO SEPARATION' not in p;props[prop]['direct']=not any(k in p for k in ['PENALTY','AUGMENTED LAGRANGE'])
  elif key=='FRICTION' and prop:props[prop]['friction']=float(d[0][0]) if d else (1. if 'ROUGH' in p else 0.)
  elif key=='CONTACT PAIR':contacts.extend((p.get('INTERACTION'),row) for row in d);contact_params.append(p)
  elif key=='STEP':nonlinear=nonlinear or p.get('NLGEOM','NO')=='YES'
  elif key=='STATIC':stabilized=stabilized or ('STABILIZE' in p and (p['STABILIZE'] is True or float(p['STABILIZE'])!=0))
  elif key=='BOUNDARY':
   if p.get('OP')=='NEW':boundaries=[]
   boundaries.extend(d)
  elif key=='CLOAD':
   if p.get('OP')=='NEW':cloads=[]
   cloads.extend(d)
  elif key in ('DLOAD','DSLOAD'):problem('LOAD_KIND','任务要求二次边一致节点力，出现分布压力/体载荷')
 if nonlinear:problem('STEP_NLGEOM','任务规定小变形，出现nlgeom=YES')
 if stabilized:problem('STABILIZATION','任务不允许自动稳定化')
 def resolve(ref,kind='NSET',inst=None,scope='ASSEMBLY',seen=None):
  seen=set() if seen is None else set(seen);ref=ref.upper()
  if '.' in ref:
   prefix,tail=ref.split('.',1)
   if prefix in instances:return resolve(tail,kind,prefix,instances[prefix]['part'],seen)
  if ref.isdigit():
   if inst is None:raise ValueError('没有实例信息的节点/单元编号 '+ref)
   return {(inst,int(ref))}
  candidates=[(scope,kind,ref)]
  if inst:candidates.append((instances[inst]['part'],kind,ref))
  candidates.append(('ASSEMBLY',kind,ref))
  for k in candidates:
   if k not in sets:continue
   if k in seen:raise ValueError('循环集合 '+ref)
   seen.add(k);v=sets[k];hint=v['instance'] or inst
   out=set()
   for item in v['items']:out.update(resolve(item,kind,hint,k[0],seen))
   return out
  raise ValueError('无法解析集合 '+ref)
 def xyz(iname,label):
  inst=instances[iname];v=parts[inst['part']]['nodes'][label]
  return tuple(v[i]+inst['translation'][i] for i in range(3))
 def at(v,t):return max(abs(a-b) for a,b in zip(v,t))<1e-5
 all_nodes={}
 for iname,which in [('TOP','top'),('BOTTOM','bottom')]:
  if iname not in instances:problem('INSTANCE_NAME','缺少实例 '+iname);continue
  pp=parts.get(instances[iname]['part'],{});all_nodes[iname]={n:xyz(iname,n) for n in pp.get('nodes',{})}
  if len(pp.get('elements',{}))!=512:problem('MESH_COUNT_'+iname,'每层应为512个单元')
  if pp.get('types')!={'C3D20R'}:problem('ELEMENT_TYPE_'+iname,'单元类型不一致')
  for mn in pp.get('sections',[]):
   got=materials.get(mn,{}).get('elastic');want=spec['materials'][case[which+'_material']]
   if not got or abs(got[0]-want['E_MPa'])>.01 or abs(got[1]-want['nu'])>1e-6:problem('MATERIAL_'+iname,'该层弹性模量/泊松比与工况不符')
  if not pp.get('sections'):problem('SECTION_'+iname,'缺少材料截面赋值')
  if all_nodes[iname]:
   lo=[min(v[i] for v in all_nodes[iname].values()) for i in range(3)];hi=[max(v[i] for v in all_nodes[iname].values()) for i in range(3)];Y=26 if which=='top' else 0
   if not at(lo,[0,Y,-8]) or not at(hi,[640,Y+26,8]):problem('GEOMETRY_'+iname,'几何包络或装配位置不符')
   grids=[[float(x*10) for x in range(65)],[Y+y for y in [0,3,6,9.5,13,16.5,20,23,26]],[float(x) for x in range(-8,9,2)]]
   for axis,expected in enumerate(grids):
    got=sorted(set(round(v[axis],6) for v in all_nodes[iname].values()))
    if len(got)!=len(expected) or any(abs(a-b)>1e-5 for a,b in zip(got,expected)):problem('MESH_GRID_'+iname+str(axis),'网格坐标分区与指定方案不符')
 expected_bc={}
 for label,v in all_nodes.get('BOTTOM',{}).items():
  if abs(v[1])<1e-5 and abs(v[0])<1e-5:
   for dof in [1,2,3]:expected_bc[('BOTTOM',label,dof)]=0.
  if abs(v[1])<1e-5 and abs(v[0]-640)<1e-5:
   for dof in [2,3]:expected_bc[('BOTTOM',label,dof)]=0.
 if case['connection']=='sliding':
  for label,v in all_nodes.get('TOP',{}).items():
   if at(v,[0,26,0]):
    for dof in [1,3]:expected_bc[('TOP',label,dof)]=0.
   if at(v,[640,26,0]):expected_bc[('TOP',label,3)]=0.
 actual_bc={}
 try:
  for row in boundaries:
   target=resolve(row[0]);a=1 if row[1]=='ENCASTRE' else int(row[1]);b=6 if row[1]=='ENCASTRE' else int(row[2]) if len(row)>2 else a;value=float(row[3]) if len(row)>3 else 0.
   for ins,n in target:
    for dof in range(a,min(b,3)+1):actual_bc[(ins,n,dof)]=value
  missing=set(expected_bc)-set(actual_bc);extra=set(actual_bc)-set(expected_bc)
  if missing:problem('BOUNDARY_MISSING','缺少规定的支承/定位约束，节点自由度数='+str(len(missing)))
  if extra:problem('BOUNDARY_EXTRA','出现任务之外的位移约束，节点自由度数='+str(len(extra)))
  if any(abs(v)>1e-12 for v in actual_bc.values()):problem('BOUNDARY_VALUE','出现非零强制位移')
 except Exception as e:problem('BOUNDARY_UNRESOLVED',str(e))
 expected_load={}
 for x in [200,440]:
  seq=sorted((v[2],n) for n,v in all_nodes.get('TOP',{}).items() if abs(v[0]-x)<1e-5 and abs(v[1]-52)<1e-5)
  weights=[1 if i in (0,len(seq)-1) else 4 if i%2 else 2 for i in range(len(seq))]
  for (_,n),w in zip(seq,weights):expected_load[('TOP',n,2)]=-case['total_load_N']/2.*w/sum(weights)
 actual_load=collections.defaultdict(float)
 try:
  for row in cloads:
   for ins,n in resolve(row[0]):actual_load[(ins,n,int(row[1]))]+=float(row[2])
  if set(expected_load)!=set(actual_load) or any(abs(actual_load.get(k,0)-v)>1e-3 for k,v in expected_load.items()):problem('LOAD_CONFIGURATION','加载线、方向、分量、总量或二次边节点力权重不符合任务')
 except Exception as e:problem('LOAD_UNRESOLVED',str(e))
 face_indices={'S1':[0,1,2,3],'S2':[4,7,6,5],'S3':[0,4,5,1],'S4':[1,5,6,2],'S5':[2,6,7,3],'S6':[3,7,4,0]}
 def surface_valid(name,iname):
  s=surfaces.get(name);faces=set()
  if not s or s['type']!='ELEMENT':return False
  for row in s['data']:
   f=row[1]
   if f not in face_indices:return False
   for ins,eid in resolve(row[0],'ELSET',None,s['scope']):
    if ins!=iname:return False
    ns=parts[instances[ins]['part']]['elements'][eid]
    if any(abs(xyz(ins,ns[i])[1]-26)>1e-5 for i in face_indices[f]):return False
    faces.add((ins,eid,f))
  return len(faces)==128
 try:
  if case['connection']=='tied':
   if len(ties)!=1 or contacts:problem('INTERFACE_KIND','绑定工况须为唯一Tie界面')
   elif not ((surface_valid(ties[0][0],'TOP') and surface_valid(ties[0][1],'BOTTOM')) or (surface_valid(ties[0][1],'TOP') and surface_valid(ties[0][0],'BOTTOM'))):problem('INTERFACE_SURFACES','Tie未覆盖正确的完整层间界面')
  else:
   if ties or len(contacts)!=1:problem('INTERFACE_KIND','滑移工况须采用唯一无摩擦接触，不能有Tie')
   else:
    pn,pair=contacts[0];pr=props.get(pn,{});cp=contact_params[0]
    if cp.get('TYPE')!='SURFACE TO SURFACE' or 'SMALL SLIDING' not in cp or 'FINITE SLIDING' in cp:problem('INTERFACE_KINEMATICS','滑移任务须采用small-sliding面面接触')
    if not pr.get('hard') or not pr.get('separation') or not pr.get('direct') or pr.get('friction')!=0:problem('INTERFACE_PROPERTIES','滑移接触的法向/切向属性错误')
    if not ((surface_valid(pair[0],'TOP') and surface_valid(pair[1],'BOTTOM')) or (surface_valid(pair[1],'TOP') and surface_valid(pair[0],'BOTTOM'))):problem('INTERFACE_SURFACES','接触未覆盖正确的完整层间界面')
 except Exception as e:problem('INTERFACE_UNRESOLVED',str(e))
 return {'passed':not errors,'errors':errors,'instances':list(instances),'nodes':{k:len(v) for k,v in all_nodes.items()},'boundary_dofs':len(actual_bc),'load_dofs':len(actual_load)}
