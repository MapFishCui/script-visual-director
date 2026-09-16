import sys
import tempfile
import unittest
from pathlib import Path
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from character_sheet import compose

class SheetTests(unittest.TestCase):
    def test_pixels_dimensions_order_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            paths=[]
            for i,size in enumerate([(7,9),(8,6),(5,12),(10,10)]):
                p=root/('%s.png'%i)
                im=Image.new('RGBA',size,(30*i,20,100,150+i))
                im.putpixel((1,1),(255,0,0,255))
                im.save(p); paths.append(p)
            out=root/'sheet.png'
            r=compose(*paths,out)
            self.assertEqual(r['size'],[20,24])
            with Image.open(out) as sheet:
                for p,view in zip(paths,r['views']):
                    with Image.open(p) as original:
                        self.assertEqual(sheet.crop(view['box']).tobytes(),original.tobytes())
            with self.assertRaises(ValueError): compose(*paths,out)
            self.assertFalse(r['target_h3_validated'])
