from __future__ import print_function
import json,sys,csv,math,os
from odbAccess import openOdb
from abaqusConstants import ELEMENT_NODAL

def extract(odb_path,spec,case):
 odb=openOdb(path=odb_path,readOnly=True)
 try:
  steps=list(odb.steps.keys());step=odb.steps[steps[-1]];frame=step.frames[-1]
  if not case.get('reference_lcp',False) and not frame.frameValue>=.999999:raise ValueError('Target load is not complete')
  if 'E' not in frame.fieldOutputs:raise ValueError('E field is missing')
  result={'reference_lcp':case.get('reference_lcp',False),'step':steps[-1],'frame_value':float(frame.frameValue),'points':[],'instances':{},'reaction':[0.,0.,0.],'reaction_moment':[0.,0.,0.]}
  nodes={}
  for name,inst in odb.rootAssembly.instances.items():
   if len(inst.nodes)==0:continue
   nodes[name]={n.label:tuple(float(x) for x in n.coordinates) for n in inst.nodes}
   coords=list(nodes[name].values());result['instances'][name]={'nodes':len(coords),'elements':len(inst.elements),'min':[min(x[i] for x in coords) for i in range(3)],'max':[max(x[i] for x in coords) for i in range(3)],'element_types':sorted(set(e.type for e in inst.elements))}
  for p in spec['points']:
   name=p['layer'].upper()
   if name not in odb.rootAssembly.instances:raise ValueError('Required instance is missing: '+name)
   inst=odb.rootAssembly.instances[name];coord=nodes[name]
   candidates=[label for label,xyz in coord.items() if max(abs(xyz[i]-p[k]) for i,k in enumerate(['x','y','z']))<1e-5]
   if len(candidates)!=1:raise ValueError('Measurement point is not one unique node: '+p['id'])
   label=candidates[0];field=frame.fieldOutputs['E'].getSubset(region=inst,position=ELEMENT_NODAL).getScalarField(componentLabel=p['component'])
   vals=[float(v.data) for v in field.values if v.nodeLabel==label and v.instance.name==name]
   if not vals or not all(math.isfinite(x) for x in vals):raise ValueError('Invalid nodal strain')
   result['points'].append({'point':p['id'],'instance':name,'node_label':label,'x_mm':p['x'],'y_mm':p['y'],'z_mm':p['z'],'component':p['component'],'strain':sum(vals)/len(vals),'element_nodal_contributions':len(vals)})
  for v in frame.fieldOutputs['RF'].values:
   if v.instance.name not in nodes:continue
   x,y,z=nodes[v.instance.name][v.nodeLabel];a,b,c=map(float,v.data)
   for i,f in enumerate([a,b,c]):result['reaction'][i]+=f
   for i,m in enumerate([y*c-z*b,z*a-x*c,x*b-y*a]):result['reaction_moment'][i]+=m
  F=case['total_load_N'];result['force_residual_relative']=math.sqrt(result['reaction'][0]**2+(result['reaction'][1]-F)**2+result['reaction'][2]**2)/F
  result['moment_residual_relative']=abs(result['reaction_moment'][2]-F*320)/(F*320)
  return result
 finally:odb.close()
if __name__=='__main__':
 spec=json.load(open(sys.argv[2],'r'));case=json.load(open(sys.argv[3],'r'));r=extract(sys.argv[1],spec,case)
 with open(sys.argv[4],'w') as f:json.dump(r,f,indent=2)
 print('INDEPENDENT_EXTRACTION_OK')
