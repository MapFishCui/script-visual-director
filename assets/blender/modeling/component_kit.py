"""Editable Blender components. Coordinates: metres, Z up, actor front is -Y."""
import json
import math
import bpy
from mathutils import Vector, Matrix
from collision_math import segment_box_distance, segment_segment_distance


def material(name,color):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    shader=m.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=(*color,1)
    shader.inputs['Roughness'].default_value=.72
    return m


def empty(name,position=(0,0,0),parent=None):
    o=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(o)
    o.parent=parent;o.location=position;o.empty_display_type='SPHERE';o.empty_display_size=.06;return o


def box(name,center,size,mat,parent=None,collider=True):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center);o=bpy.context.object;o.name=name
    o.scale=size;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.parent=parent;o.data.materials.append(mat)
    if collider:o['collision_half_extents']=[v/2 for v in size]
    bevel=o.modifiers.new('edge readability','BEVEL');bevel.width=min(.02,min(size)*.1);bevel.segments=2
    return o


def ellipsoid(name,center,scale,mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20,ring_count=12,location=center)
    o=bpy.context.object;o.name=name;o.scale=scale;bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    for face in o.data.polygons:face.use_smooth=True
    return o


def rod(name,a,b,radius,mat):
    a,b=Vector(a),Vector(b);bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=radius,depth=(b-a).length,location=(a+b)/2)
    o=bpy.context.object;o.name=name;o.rotation_quaternion=(b-a).to_track_quat('Z','Y');o.rotation_mode='QUATERNION'
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True);o.data.materials.append(mat)
    for face in o.data.polygons:face.use_smooth=True
    return o


def physics(o,mode,mass=1):
    if mode=='none':return
    bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.rigidbody.object_add();o.select_set(False)
    body=o.rigid_body;body.type='PASSIVE' if mode=='static' else 'ACTIVE';body.kinematic=mode=='kinematic'
    body.collision_shape='BOX';body.use_margin=True;body.collision_margin=.002;body.mass=mass


def structure(c,mat):
    root=empty(c['id'],c['position']);root.rotation_euler.z=math.radians(c.get('rotation_z',0));parts=[]
    typ=c['type']
    if typ=='box':parts=[box(c['id']+'/body',(0,0,0),c['size'],mat,root)]
    elif typ=='wall_opening':
        w,h,t=c['width'],c['height'],c['thickness'];opening=c['opening'];ow,oh=opening['width'],opening['height'];off=opening.get('offset',0)
        left=off-ow/2;right=off+ow/2
        if left>-w/2:parts.append(box(c['id']+'/left',((-w/2+left)/2,0,h/2),(left+w/2,t,h),mat,root))
        if right<w/2:parts.append(box(c['id']+'/right',((right+w/2)/2,0,h/2),(w/2-right,t,h),mat,root))
        if oh<h:parts.append(box(c['id']+'/lintel',(off,0,(oh+h)/2),(ow,t,h-oh),mat,root))
    elif typ=='stairs':
        for i in range(c['steps']):
            h=(i+1)*c['rise'];parts.append(box(c['id']+'/step'+str(i),(0,(i+.5)*c['tread'],h/2),(c['width'],c['tread'],h),mat,root))
    elif typ=='door':
        parts=[box(c['id']+'/leaf',(c['width']/2,0,c['height']/2),(c['width'],c['thickness'],c['height']),mat,root)]
        root.rotation_euler.z=math.radians(c.get('rotation_z',0)+c.get('angle',0))
    for o in parts:physics(o,c.get('physics','none'),c.get('mass',1))
    for key in c.get('keys',[]):
        frame=key['frame']
        if 'position' in key:root.location=key['position'];root.keyframe_insert('location',frame=frame)
        if 'angle' in key:root.rotation_euler.z=math.radians(c.get('rotation_z',0)+key['angle']);root.keyframe_insert('rotation_euler',frame=frame)
    return root,parts


def actor(c,mat):
    scale=c.get('height',1.75)/1.75;v=lambda p:Vector(p)*scale
    root=empty(c['id'],c['position']);root.rotation_euler.z=math.radians(c.get('rotation_z',0));rig_data=bpy.data.armatures.new(c['id']+'/skeleton');rig=bpy.data.objects.new(c['id']+'/rig',rig_data)
    bpy.context.collection.objects.link(rig);rig.parent=root;rig.show_in_front=True
    bpy.context.view_layer.objects.active=rig;rig.select_set(True);bpy.ops.object.mode_set(mode='EDIT')
    defs={'pelvis':((0,0,.85),(0,0,1.03),None),'spine':((0,0,1.03),(0,0,1.48),'pelvis'),'head':((0,0,1.48),(0,0,1.70),'spine')}
    for side,sign in [('L',-1),('R',1)]:
        defs['upper_arm.'+side]=((sign*.22,0,1.43),(sign*.34,-.08,1.18),'spine')
        defs['forearm.'+side]=((sign*.34,-.08,1.18),(sign*.40,-.04,.94),'upper_arm.'+side)
        defs['thigh.'+side]=((sign*.105,0,.90),(sign*.105,-.07,.49),'pelvis')
        defs['shin.'+side]=((sign*.105,-.07,.49),(sign*.105,0,.09),'thigh.'+side)
    for name,(a,b,parent) in defs.items():
        bone=rig_data.edit_bones.new(name);bone.head=v(a);bone.tail=v(b)
        if parent:bone.parent=rig_data.edit_bones[parent]
        if name.startswith(('forearm','shin')):bone.use_connect=True
    bpy.ops.object.mode_set(mode='OBJECT');rig.select_set(False)
    def bind(mesh,bone):
        mesh.parent=root
        vg=mesh.vertex_groups.new(name=bone);vg.add(list(range(len(mesh.data.vertices))),1,'REPLACE')
        mod=mesh.modifiers.new('rig deformation','ARMATURE');mod.object=rig
    body=ellipsoid(c['id']+'/torso',v((0,0,1.25)),v((.235,.13,.30)),mat);bind(body,'spine')
    body=ellipsoid(c['id']+'/hips',v((0,0,.94)),v((.17,.125,.135)),mat);bind(body,'pelvis')
    body=ellipsoid(c['id']+'/head',v((0,-.012,1.625)),v((.105,.115,.135)),mat);bind(body,'head')
    controls={};radii={};endpoints={};chains={}
    for side,sign in [('L',-1),('R',1)]:
        for name,radius in [('upper_arm',.056),('forearm',.046),('thigh',.075),('shin',.052)]:
            bone=name+'.'+side;a,b,_=defs[bone];radii[bone]=radius*scale
            bind(rod(c['id']+'/'+bone,v(a),v(b),radius*scale,mat),bone)
            bind(ellipsoid(c['id']+'/'+bone+'/joint',v(a),v((radius,)*3),mat),bone)
        for effector,bone in [('hand','forearm.'+side),('foot','shin.'+side)]:
            a,b,_=defs[bone];target=empty(c['id']+'/'+effector+'.'+side,v(b),root)
            pole=empty(c['id']+'/'+effector+'.'+side+'/pole',v((sign*.55,-.7,1.23) if effector=='hand' else (sign*.105,-.7,.48)),root)
            pb=rig.pose.bones[bone];ik=pb.constraints.new('IK');ik.name='Contact IK';ik.target=target;ik.pole_target=pole;ik.chain_count=2;ik.use_stretch=False
            # Pole angle is explicit per chain; validate solved endpoints and poses after evaluation.
            ik.pole_angle=math.radians(c.get('pole_angles',{}).get(effector+'.'+side,0))
            for n in (bone,defs[bone][2]):rig.pose.bones[n].ik_stretch=0
            controls[effector+'.'+side]=target;controls[effector+'.'+side+'/pole']=pole
            end=empty(c['id']+'/'+effector+'.'+side+'/actual')
            con=end.constraints.new('COPY_LOCATION');con.target=rig;con.subtarget=bone;con.head_tail=1
            rot=end.constraints.new('COPY_ROTATION');rot.target=rig if effector=='hand' else root
            if effector=='hand':rot.subtarget=bone
            endpoints[effector+'.'+side]=end;chains[effector+'.'+side]=bone
            prefix=c['id']+'/'+effector+'.'+side
            def part(label,offset,dims):
                if effector=='hand':
                    bind(ellipsoid(prefix+'/'+label,v(b)+v(offset),v(dims),mat),bone)
                else:
                    mesh=ellipsoid(prefix+'/'+label,v(offset),v(dims),mat)
                    mesh.parent=end
            if effector=='hand':
                # A readable palm, four separate fingers and an inward thumb.
                # Rigidly follows the forearm; no finger animation is implied.
                part('palm',(0,-.01,-.042),(.039,.023,.047))
                for index,(x,length) in enumerate([(-.029,.057),(-.010,.070),(.010,.075),(.029,.062)]):
                    part('finger'+str(index+1),(sign*x,-.01,-.075-length/2),(.008,.010,length/2+.006))
                start=v(b)+v((-sign*.033,-.013,-.027));tip=v(b)+v((-sign*.063,-.02,-.071))
                bind(rod(prefix+'/thumb',start,tip,.012*scale,mat),bone)
                bind(ellipsoid(prefix+'/thumb_tip',tip,v((.012,)*3),mat),bone)
            else:
                # Distinguishable ankle, heel and broad forefoot, facing -Y.
                part('ankle',(0,0,-.006),(.044,.045,.055))
                part('heel',(0,.012,-.043),(.052,.060,.042))
                part('forefoot',(0,-.086,-.046),(.061,.107,.035))
                part('toe',(0,-.161,-.049),(.058,.043,.029))
    # Keyframes are explicit pose proposals, not an automatic walking controller.
    for key in c.get('keys',[]):
        if 'position' in key:root.location=key['position'];root.keyframe_insert('location',frame=key['frame'])
        if 'angle' in key:root.rotation_euler.z=math.radians(c.get('rotation_z',0)+key['angle']);root.keyframe_insert('rotation_euler',frame=key['frame'])
        for name,position in key.get('targets',{}).items():
            controls[name].location=position;controls[name].keyframe_insert('location',frame=key['frame'])
    return {'root':root,'rig':rig,'controls':controls,'endpoints':endpoints,'chains':chains,'radii':radii,'scale':scale}


def build(spec):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    mats={name:material('clay/'+name,color) for name,color in [('structure',(.61,.65,.69)),('actor',(.035,.24,.75)),('prop',(.65,.46,.25))]}
    objects={};actors={};colliders=[];imports=[]
    for c in spec['components']:
        if c['type']=='actor':
            actors[c['id']]=actor(c,mats['actor']);objects[c['id']]=actors[c['id']]['root']
        elif c['type']=='asset':
            from imported_asset import imported
            root,parts,info=imported(c,mats[c['category']],empty,box);objects[c['id']]=root;colliders+=parts;imports.append(info)
        elif c['type']=='anchor':objects[c['id']]=empty(c['id'],c['position'])
        else:
            root,parts=structure(c,mats['prop'] if c.get('category')=='prop' else mats['structure']);objects[c['id']]=root;colliders+=parts
    for attachment in spec.get('attachments',[]):
        obj=objects[attachment['object']];a=actors[attachment['actor']]
        obj.parent=a['endpoints'][attachment['effector']];obj.location=attachment.get('offset',[0,0,0]);obj.rotation_euler=(0,0,0)
    for contact in spec.get('contacts',[]):
        a=actors[contact['actor']];ctrl=a['controls'][contact['effector']];con=ctrl.constraints.new('COPY_LOCATION');con.target=objects[contact['target']]
        start,end=contact['start'],contact['end']
        for frame,value in [(start-1,0),(start,1),(end,1),(end+1,0)]:
            con.influence=value;con.keyframe_insert('influence',frame=frame)
    scene=bpy.context.scene;scene.render.fps=spec.get('fps',12);scene.frame_start=1;scene.frame_end=spec.get('frames',1)
    scene.render.engine='CYCLES';scene.cycles.samples=12;scene.render.resolution_x=spec.get('preview',{}).get('width',640);scene.render.resolution_y=spec.get('preview',{}).get('height',480);scene.render.resolution_percentage=100
    scene.world.color=(.3,.3,.3)
    camera_spec=spec.get('preview',{});target=Vector(camera_spec.get('target',[0,0,1]));position=Vector(camera_spec.get('position',[6,-8,5]))
    bpy.ops.object.camera_add(location=position);camera=bpy.context.object;camera.name='observer';camera.rotation_euler=(target-position).to_track_quat('-Z','Y').to_euler();camera.data.lens=42;scene.camera=camera
    bpy.ops.object.light_add(type='AREA',location=(1,-3,6));light=bpy.context.object;light.data.energy=1400;light.data.shape='DISK';light.data.size=6
    if any(c.get('physics')=='dynamic' for c in spec['components']):
        cache=scene.rigidbody_world.point_cache;cache.frame_start=1;cache.frame_end=scene.frame_end
        with bpy.context.temp_override(point_cache=cache):bpy.ops.ptcache.bake(bake=True)
    scene.frame_set(1);bpy.context.view_layer.update()
    return {'actors':actors,'objects':objects,'colliders':colliders,'spec':spec,'imported_assets':imports}


def capsules(a,deps):
    rig=a['rig'].evaluated_get(deps);m=rig.matrix_world;scale=a['scale'];rows=[]
    for name,radius in a['radii'].items():
        pb=rig.pose.bones[name];rows.append((name,m@pb.head,m@pb.tail,radius))
    p=rig.pose.bones['spine'];rows.append(('torso',m@p.head,m@p.tail,.13*scale))
    p=rig.pose.bones['head'];rows.append(('head',m@p.head,m@p.tail,.105*scale))
    return rows


def check_scene(model):
    spec=model['spec'];findings=[];tolerance=spec.get('collision_tolerance',.008);frames=spec.get('frames',1)
    allowed={(x['actor'],x['part'],x['object']):x for x in spec.get('allowed_contacts',[])}
    samples=spec.get('substeps',2)
    # Sample both integer frames and intermediate evaluated poses, including moving obstacles.
    for step in range((frames-1)*samples+1):
        time=1+step/samples;bpy.context.scene.frame_set(int(time),subframe=time-int(time));deps=bpy.context.evaluated_depsgraph_get()
        def report(kind,actor,part,obj,amount):
            findings.append({'frame':time,'kind':kind,'actor':actor,'part':part,'object':obj,'error_m':round(amount,5)})
        for aid,a in model['actors'].items():
            cap=capsules(a,deps)
            for part,p,q,radius in cap:
                for source in model['colliders']:
                    obj=source.evaluated_get(deps);m=obj.matrix_world;rot=m.to_quaternion().to_matrix();center=m.translation
                    x=rot.transposed()@(p-center);y=rot.transposed()@(q-center);half=[x*abs(y) for x,y in zip(source['collision_half_extents'],m.to_scale())]
                    distance=segment_box_distance(x,y,half);depth=radius-distance
                    allow=allowed.get((aid,part,source.parent.name))
                    limit=allow['max_penetration'] if allow and allow['start']<=time<=allow['end'] else tolerance
                    if depth>limit:report('environment_intersection',aid,part,source.parent.name,depth)
            # Distal limbs against torso/head: explicit subset, not full mesh self-collision.
            for name,p,q,radius in cap:
                if not name.startswith(('forearm','shin')):continue
                for other,u,v,r in cap:
                    if other not in ('torso','head'):continue
                    depth=radius+r-segment_segment_distance(p,q,u,v)
                    if depth>tolerance:report('self_intersection',aid,name,other,depth)
            for effector,bone in a['chains'].items():
                actual=a['endpoints'][effector].evaluated_get(deps).matrix_world.translation
                expected=a['controls'][effector].evaluated_get(deps).matrix_world.translation
                error=(actual-expected).length
                if error>spec.get('ik_tolerance',.025):report('ik_target_unreached',aid,effector,'IK target',error)
        for c in spec.get('contacts',[]):
            if not c['start']<=time<=c['end']:continue
            actual=model['actors'][c['actor']]['endpoints'][c['effector']].evaluated_get(deps).matrix_world.translation
            target=model['objects'][c['target']].evaluated_get(deps).matrix_world.translation;error=(actual-target).length
            if error>c.get('tolerance',.025):report('contact_lost',c['actor'],c['effector'],c['target'],error)
    # Keep representative first/worst observations per pair instead of thousands of duplicates.
    grouped={}
    for f in findings:
        key=(f['kind'],f['actor'],f['part'],f['object'])
        if key not in grouped:grouped[key]={**f,'first_frame':f['frame'],'occurrences':1}
        else:
            old=grouped[key];old['occurrences']+=1
            if f['error_m']>old['error_m']:old.update(frame=f['frame'],error_m=f['error_m'])
    return {'status':'failed' if findings else 'partial' if model.get('imported_assets') else 'passed','findings':list(grouped.values()),'samples':(frames-1)*samples+1,
            'scope':'IK endpoint/contact distances; limb/torso/head capsule proxies against oriented boxes; distal limb vs torso/head.',
            'limitations':['Finite temporal sampling can miss very fast crossings.','Not full mesh self-collision, finger anatomy, cloth, or an automatic collision response controller.','A physics flag alone does not stop director-controlled actors.'],
            'imported_assets':model.get('imported_assets',[]),'user_approved':False}
