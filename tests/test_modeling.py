import copy,sys,unittest
from pathlib import Path
import modeling
sys.path.insert(0,str(modeling.KIT))
from collision_math import segment_box_distance,segment_segment_distance

class ModelingCase(unittest.TestCase):
    def spec(self):return {'schema_version':1,'frames':12,'components':[{'id':'actor','type':'actor','position':[0,0,0]},{'id':'grip','type':'anchor','position':[.4,0,1]}]}
    def test_geometry_distances(self):
        self.assertEqual(segment_box_distance((-2,0,0),(2,0,0),(1,1,1)),0)
        self.assertAlmostEqual(segment_box_distance((-2,2,0),(2,2,0),(1,1,1)),1)
        self.assertAlmostEqual(segment_box_distance((2,2,0),(2,2,0),(1,1,1)),2**.5)
        self.assertAlmostEqual(segment_segment_distance((0,0,0),(1,0,0),(0,2,0),(1,2,0)),2)
        self.assertEqual(segment_segment_distance((0,0,0),(1,0,0),(.5,-1,0),(.5,1,0)),0)
    def test_validation_rejects_ambiguous_controls(self):
        s=self.spec();modeling.validate(s)
        s['contacts']=[{'actor':'actor','effector':'hand.R','target':'missing','start':1,'end':12}]
        with self.assertRaises(ValueError):modeling.validate(s)
        s['contacts'][0]['target']='actor'
        with self.assertRaises(ValueError):modeling.validate(s)
        s['contacts'][0]['target']='grip';modeling.validate(s)
        s['contacts'].append(copy.deepcopy(s['contacts'][0]))
        with self.assertRaises(ValueError):modeling.validate(s)
    def test_rejects_invalid_structure_and_duration(self):
        s=self.spec();s['components'].append({'id':'wall','type':'wall_opening','position':[0,0,0],'width':2,'height':2,'thickness':.2,'opening':{'width':3,'height':1}})
        with self.assertRaises(ValueError):modeling.validate(s)
        s=self.spec();s['beats']=[{'id':'b','duration':2,'action':'walk','start_state':'start','end_state':'end'}]
        with self.assertRaises(ValueError):modeling.validate(s)
    def test_attachment_rejects_dual_drivers(self):
        s=self.spec();s['components'].append({'id':'prop','type':'box','position':[0,0,0],'size':[.1,.1,.1],'physics':'dynamic'})
        s['attachments']=[{'actor':'actor','effector':'hand.L','object':'prop'}]
        with self.assertRaises(ValueError):modeling.validate(s)

if __name__=='__main__':unittest.main()
