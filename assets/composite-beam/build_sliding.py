"""Reviewed composite-beam reference; preserve task conditions when adapting."""
from abaqus import *
from abaqusConstants import *
import part,material,section,assembly,step,interaction,load,job,sketch,visualization
import mesh,regionToolset,json,csv,math,time,os
from odbAccess import openOdb
case=json.load(open('case.json'))
materials={'steel':(203000.0,.26),'aluminum':(75000.0,.31),'copper':(104000.0,.40)}
assert case['top_material'] in materials and case['bottom_material'] in materials
assert case['connection'] in ('sliding','tied') and case['total_load_N'] in (1000,2000)
Mdb()
m=mdb.Model(name='BeamModel')
for key,props in materials.items():
 m.Material(name=key).Elastic(table=(props,))
 m.HomogeneousSolidSection(name=key,material=key)
parts={}
for name,key in [('BOTTOM',case['bottom_material']),('TOP',case['top_material'])]:
 s=m.ConstrainedSketch(name='profile_'+name,sheetSize=1300)
 s.rectangle(point1=(0.,0.),point2=(640.,26.))
 p=m.Part(name=name,dimensionality=THREE_D,type=DEFORMABLE_BODY)
 p.BaseSolidExtrude(sketch=s,depth=16.)
 for y in (6.,13.,20.):
  feat=p.DatumPlaneByPrincipalPlane(principalPlane=XZPLANE,offset=y)
  p.PartitionCellByDatumPlane(cells=p.cells,datumPlane=p.datums[feat.id])
 p.SectionAssignment(region=p.Set(name='SOLID',cells=p.cells),sectionName=key)
 for edge in p.edges:
  ids=edge.getVertices();v=[p.vertices[i].pointOn[0] for i in ids]
  delta=[abs(v[0][i]-v[1][i]) for i in range(3)]
  axis=delta.index(max(delta));number=(32,1,4)[axis]
  p.seedEdgeByNumber(edges=(edge,),number=number,constraint=FIXED)
 p.setMeshControls(regions=p.cells,elemShape=HEX,technique=STRUCTURED)
 p.setElementType(regions=(p.cells,),elemTypes=(mesh.ElemType(elemCode=C3D20R,elemLibrary=STANDARD),))
 p.generateMesh()
 assert len(p.elements)==512 and len(p.nodes)==2945,(name,len(p.elements),len(p.nodes))
 parts[name]=p
m.rootAssembly.DatumCsysByDefault(CARTESIAN)
a=m.rootAssembly
for name,y in [('BOTTOM',0.),('TOP',26.)]:
 a.Instance(name=name,part=parts[name],dependent=ON)
 a.translate(instanceList=(name,),vector=(0.,y,-8.))
a.regenerate()
def nodeset(name,instance,predicate,expected):
 inst=a.instances[instance];labels=tuple(n.label for n in inst.nodes if predicate(n.coordinates))
 assert len(labels)==expected,(name,len(labels),expected)
 return a.Set(name=name,nodes=inst.nodes.sequenceFromLabels(labels=labels))
def near(a,b):return abs(a-b)<1e-5
for name,y in [('BOTTOM',0.),('TOP',26.)]:
 coords=[n.coordinates for n in a.instances[name].nodes]
 assert all(near(min(v[i] for v in coords),[0,y,-8][i]) and near(max(v[i] for v in coords),[640,y+26,8][i]) for i in range(3)),name
left=nodeset('LEFT_SUPPORT','BOTTOM',lambda c:near(c[0],0) and near(c[1],0),9)
right=nodeset('RIGHT_SUPPORT','BOTTOM',lambda c:near(c[0],640) and near(c[1],0),9)
m.DisplacementBC(name='LEFT_SUPPORT',createStepName='Initial',region=left,u1=0.,u2=0.,u3=0.)
m.DisplacementBC(name='RIGHT_SUPPORT',createStepName='Initial',region=right,u2=0.,u3=0.)
bottom=a.Surface(name='BOTTOM_TOP',side1Faces=a.instances['BOTTOM'].faces.findAt(((320.,26.,0.),)))
top=a.Surface(name='TOP_BOTTOM',side1Faces=a.instances['TOP'].faces.findAt(((320.,26.,0.),)))
# Teacher baseline: perfectly bonded interface.
cp = m.ContactProperty('INTER_PROP')
cp.NormalBehavior(pressureOverclosure=HARD, allowSeparation=ON, constraintEnforcementMethod=DIRECT)
cp.TangentialBehavior(formulation=FRICTIONLESS)
m.SurfaceToSurfaceContactStd(name='CONTACT_INT', createStepName='Initial', main=bottom, secondary=top, sliding=SMALL, interactionProperty='INTER_PROP', enforcement=SURFACE_TO_SURFACE, adjustMethod=NONE)
g0=nodeset('GAUGE_0','TOP',lambda c:near(c[0],0.) and near(c[1],26.) and near(c[2],0.),1)
m.DisplacementBC(name='GAUGE_0',createStepName='Initial',region=g0,u1=0.,u3=0.)
gL=nodeset('GAUGE_640','TOP',lambda c:near(c[0],640.) and near(c[1],26.) and near(c[2],0.),1)
m.DisplacementBC(name='GAUGE_640',createStepName='Initial',region=gL,u3=0.)

m.StaticStep(name='LOAD',previous='Initial',nlgeom=OFF,timePeriod=1.,initialInc=1.,minInc=1e-8,maxInc=1.,maxNumInc=200)
m.FieldOutputRequest(name='FIELDS',createStepName='LOAD',variables=('U','RF','E','S'))
weights=(1,4,2,4,2,4,2,4,1)
for x in (200.,440.):
 inst=a.instances['TOP'];ns=sorted([n for n in inst.nodes if near(n.coordinates[0],x) and near(n.coordinates[1],52)],key=lambda n:n.coordinates[2])
 assert len(ns)==9
 for i,(node,weight) in enumerate(zip(ns,weights)):
  reg=a.Set(name='LOAD_%d_%d'%(x,i),nodes=inst.nodes.sequenceFromLabels(labels=(node.label,)))
  m.ConcentratedForce(name='LOAD_%d_%d'%(x,i),createStepName='LOAD',region=reg,cf2=-float(case['total_load_N'])*weight/48.)
mdb.saveAs(pathName='model.cae')
job=mdb.Job(name='beam',model='BeamModel',numCpus=2,numDomains=2,numGPUs=0,memory=4096,memoryUnits=MEGA_BYTES)
job.writeInput();job.submit();job.waitForCompletion()
deadline=time.time()+240.
while time.time()<deadline:
 try:
  status=open('beam.sta','r',errors='replace').read()
 except (OSError,IOError):status=''
 if 'THE ANALYSIS HAS NOT BEEN COMPLETED' in status:raise RuntimeError('SOLVER_ABORTED')
 if 'THE ANALYSIS HAS COMPLETED SUCCESSFULLY' in status and not os.path.exists('beam.lck'):break
 time.sleep(.5)
else:raise RuntimeError('SOLVER_COMPLETION_NOT_CONFIRMED')
odb=openOdb(path='beam.odb',readOnly=True)
try:
 frame=odb.steps['LOAD'].frames[-1]
 if case.get('solver','static_general')!='lcp':assert abs(frame.frameValue-1.)<1e-6
 points=[('TOP',52,'E33'),('TOP',52,'E11'),('TOP',46,'E11'),('TOP',39,'E11'),('TOP',32,'E11'),('BOTTOM',20,'E11'),('BOTTOM',13,'E11'),('BOTTOM',6,'E11'),('BOTTOM',0,'E11'),('BOTTOM',0,'E33')]
 rows=[]
 for i,(name,y,comp) in enumerate(points,1):
  inst=odb.rootAssembly.instances[name]
  labels=[n.label for n in inst.nodes if near(n.coordinates[0],320) and near(n.coordinates[1],y) and near(n.coordinates[2],0)]
  assert len(labels)==1,(name,y,labels)
  field=frame.fieldOutputs['E'].getSubset(region=inst,position=ELEMENT_NODAL).getScalarField(componentLabel=comp)
  values=[float(v.data) for v in field.values if v.nodeLabel==labels[0] and v.instance.name==name]
  assert values and all(math.isfinite(v) for v in values)
  rows.append(dict(point='P'+str(i),instance=name,x_mm=320,y_mm=y,z_mm=0,component=comp,strain=sum(values)/len(values)))
 with open('result.csv','w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['point','instance','x_mm','y_mm','z_mm','component','strain']);w.writeheader();w.writerows(rows)
finally:odb.close()
