#!/usr/bin/env python
# encoding: utf-8
"""
texture.py

Created by Damian Cugley on 2011-01-12.
Copyright (c) 2011 Damian Cugley. All rights reserved.
"""

import sys
import os
import unittest
from mock import Mock, patch

from alleged.minecraft.texture import *
from zipfile import ZipFile, ZIP_DEFLATED
from StringIO import StringIO
from base64 import b64encode
import shutil
import httplib2


class TestCase(unittest.TestCase):
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_data'))
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),  'test_working'))

    if not os.path.exists(test_dir):
        os.mkdir(test_dir)

    def get_data(self, file_name):
        with open(os.path.join(self.data_dir, file_name), 'rb') as strm:
            bytes = strm.read()
        return bytes

    def make_source_pack(self, name, desc, resources_and_maps_by_file_name):
        strm = StringIO()
        self.write_pack_contents(strm, name, desc, resources_and_maps_by_file_name)
        strm.seek(0)

        # Open it as a SourceTexturePack
        atlas = Atlas(dict((k, m) for (k, (_, m)) in resources_and_maps_by_file_name.items() if m))
        pack = SourcePack(strm, atlas)
        return pack

    def write_pack_contents(self, strm, name, desc, resources_and_maps_by_file_name):
        with ZipFile(strm, 'w') as zip:
            for file_name, (res_name, _) in resources_and_maps_by_file_name.items():
                zip.writestr(file_name, self.get_data(res_name))
            zip.writestr('pack.txt', '{0}\n{1}'.format(name, desc).encode('UTF-8'))

    def assertRepresentIdenticalImages(self, bytes1, bytes2, msg=None):
        im1 = Image.open(StringIO(bytes1))
        im2 = Image.open(StringIO(bytes2))
        self.assertEqual(im1.size, im2.size)
        w, h = im1.size
        for i, (b1, b2) in enumerate(zip(im1.getdata(), im2.getdata())):
            self.assertEqual(b1, b2, '{msg}Pixels at ({x}, {y}) differ: {b1!r} != {b2!r}'.format(
                msg=msg + ': ' if msg else '',
                x=i % w,
                y=i // h,
                b1=b1,
                b2=b2
            ))


class TextResourceTests(TestCase):
	def setUp(self):
		pass

	def test_pack_txt(self):
	    doc = TextResource('pack.txt', u'Test pack\nBy Fréd the Deäd')
	    self.assertEqual('pack.txt', doc.name)
	    self.assertEqual('Test pack\nBy Fréd the Deäd', doc.get_bytes())
	    # This test relies on the encoding of the source file being UTF-8!!


class SourcePackTests(TestCase):
    def setUp(self):
        super(SourcePackTests, self).setUp()
        self.dir_pack_path = os.path.join(self.test_dir, 'bonka')
        if os.path.exists(self.dir_pack_path):
            shutil.rmtree(self.dir_pack_path)
            
    def test_sign(self):
        pack = self.make_source_pack('Sign pack', 'Just a test', {'item/sign.png': ('sign.png', None)})
        self.check_pack_is_sign_pack(pack)

    def check_pack_is_sign_pack(self, pack):
        self.assertEqual('Sign pack', pack.label)
        self.assertEqual('Just a test', pack.desc)

        # Check there is a SourceResource correspoding to the sign
        res = pack.get_resource('item/sign.png')
        self.assertEqual('item/sign.png', res.name)

        # Check the data returned from the resource maches what went in to the ZIP
        self.assertEqual(self.get_data('sign.png'), res.get_bytes())

    def test_pack_from_file_name(self):
        file_path = os.path.join(self.test_dir, 'bonko.zip')
        with open(file_path, 'wb') as strm:
            self.write_pack_contents(strm, 'Sign pack', 'Just a test', {'item/sign.png': ('sign.png', None)})

        # Open it as a SourceTexturePack
        pack = SourcePack(file_path, Atlas())
        self.check_pack_is_sign_pack(pack)
        
        
    def test_pack_from_directory(self):
        pack = self.create_sign_directory()
            
        # Open it as a SourceTexturePack
        self.check_pack_is_sign_pack(pack)
        
    def test_dirctory_pack_includes_resources(self):
        pack = self.create_sign_directory()
        
        # Save as ZIP
        file_path = os.path.join(self.test_dir, 'bonko.zip')
        pack.write_to(file_path)
        
        # Reopen & recheck
        pack = SourcePack(file_path, Atlas())
        self.check_pack_is_sign_pack(pack)
        
    def create_sign_directory(self):
        # Create dir from scratch with contesnts of a pack.
        os.mkdir(self.dir_pack_path)
        os.mkdir(os.path.join(self.dir_pack_path, 'item'))
        with open(os.path.join(self.dir_pack_path, 'item', 'sign.png'), 'wb') as strm:
            strm.write(self.get_data('sign.png'))
        with open(os.path.join(self.dir_pack_path, 'pack.txt'), 'wt') as strm:
            strm.write('Sign pack\nJust a test\n')
        
        pack = SourcePack(self.dir_pack_path, Atlas())
        return pack


class RecipePackTests(TestCase):
    def test_pack_txt_from_init(self):
        pack = RecipePack(u'Test pack', u'It’s testy')
        self.assertEqual(u'Test pack\nIt’s testy', pack.get_resource('pack.txt').get_content())

    def test_zip_1(self):
        pack = RecipePack(u'Yummy pack', u'It’s tasty')
        pack.add_resource(TextResource('doc/news.txt', 'This is a news file.'))

        # Now generate the archive and check it contains the expected files.
        strm = StringIO()
        pack.write_to(strm)

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            self.assertEqual(u'Yummy pack\nIt’s tasty', zip.read('pack.txt').decode('UTF-8'))
            self.assertEqual(u'This is a news file.', zip.read('doc/news.txt').decode('UTF-8'))

    def test_zip_with_image_from_source_pack(self):
        simple_map = GridMap((32, 32), (16, 16), ['a', 'b', 'c', 'd'])
        pack_ab = self.make_source_pack('AB', 'Has A and B', {'a.png': ('a.png', simple_map), 'b.png': ('b.png', simple_map)})
        pack_c = self.make_source_pack('C', 'Has C', {'c.png': ('c.png', simple_map)})

        new_pack = RecipePack(u'Composite pack', u'It’s composite')
        new_pack.add_resource(pack_ab.get_resource('a.png'))
        new_pack.add_resource(pack_c.get_resource('c.png'))

        # Now generate the archive and check it contains the expected files.
        strm = StringIO()
        new_pack.write_to(strm)

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            self.assertEqual(self.get_data('a.png'), zip.read('a.png'))
            self.assertEqual(self.get_data('c.png'), zip.read('c.png'))
            try:
                zip.read('b.png')
                self.fail('Should not find b.png')
            except KeyError:
                pass


class GridMapTests(TestCase):
    def test_coords(self):
        mappe = GridMap((32, 32), (16, 16), ['alpha', 'bravo', 'charlie', 'delta'])

        # Same coordinate conventions as PIL: (left, top, right, bottom),
        # where (0, 0) is to the left and above the top-left pixel.
        self.assertEqual((0, 0, 16, 16), mappe.get_box('alpha'))
        self.assertEqual((16, 0, 32, 16), mappe.get_box('bravo'))
        self.assertEqual((0, 16, 16, 32), mappe.get_box('charlie'))
        self.assertEqual((16, 16, 32, 32), mappe.get_box('delta'))

    def test_missing(self):
        mappe = GridMap((32, 32), (16, 16), ['alpha', 'bravo', 'charlie', 'delta'])

        with self.assertRaises(NotInMap):
            mappe.get_box('echo')

    def test_coords_offset(self):
        map2 = GridMap((0, 96, 32, 128), (16, 16), ['whiskey', 'x-ray', 'yankee', 'zulu'])
        self.assertEqual((0, 96, 16, 112), map2.get_box('whiskey'))
        self.assertEqual((16, 96, 32, 112), map2.get_box('x-ray'))
        self.assertEqual((0, 112, 16, 128), map2.get_box('yankee'))
        self.assertEqual((16, 112, 32, 128), map2.get_box('zulu'))

    def test_names(self):
        names = [x + y for x in 'abcd' for y in 'lmno']
        map3 = GridMap((32, 32), (8, 8), names)
        self.assertEqual(names, map3.names)

class CompositeMapTests(TestCase):
    def test_two_grids(self):
        names1 = [
            'grass', 'stone', 'dirt', 'dirt_grass', 'planks', 'step_side', 'stop_top', 'brick',
                'tnt_side', 'tnt_top', 'tnt_bottom', 'web', 'rose', 'dendelion', 'water', 'sapling',
            'cobble', 'bedrock', 'sand', 'gravel', 'log_side', 'log_top', 'iron', 'gold',
                'diamond', 'chest_top', 'chest_side', 'chest_front', 'red_mushroom', 'gray_mushroom', 'blank1', 'fire']
        names2 = ['black_wool', 'gray_wool',
            'red_wool', 'pink_wool',
            'green_wool', 'lime_wool',
            'brown_wool', 'yellow_wool',
            'blue_wool', 'light_blue_wool',
            'purple_wool', 'magenta_wool',
            'cyan_wool', 'orange_wool',
            'light_gray_wool']
        map1 = GridMap((256, 32), (16, 16), names1)
        map2 = GridMap((16, 112, 48, 240), (16, 16), names2)
        map3 = CompositeMap([map1, map2])

        self.assertEqual((0, 0, 16, 16), map3.get_box('grass'))
        self.assertEqual((128, 16, 144, 32), map1.get_box('diamond'))
        self.assertEqual((128, 16, 144, 32), map3.get_box('diamond'))
        self.assertEqual((16, 112, 32, 128), map3.get_box('black_wool'))
        self.assertEqual((32, 208, 48, 224), map3.get_box('orange_wool'))

        self.assertEqual(set(names1) | set(names2), set(map3.names))


class AtlasTests(TestCase):
    def setUp(self):
        super(AtlasTests, self).setUp()

        map_a = GridMap((32, 32), (16, 16), ['yellow', 'red', 'orange', 'green'])
        map_b = GridMap((32, 32), (16, 16), ['blue', 'cyan', 'green', 'magenta'])
        self.atlas = Atlas()
        self.atlas.add_map('a.png', map_a)
        self.atlas.add_map('b.png', map_b)

    def test_named_map(self):
        m = self.atlas.get_map('a.png')
        self.assertEqual((0, 0, 16, 16), m.get_box('yellow'))

    def test_grid_map(self):
        m = self.atlas.get_map({
            'source_rect': {'width': 32, 'height': 32},
            'cell_rect': {'width': 16, 'height': 16},
            'names': ['p', 'q', 'r', 's']
        })
        self.assertEqual((16, 16, 32, 32), m.get_box('s'))

    def test_composite_map(self):
        m = self.atlas.get_map([
            'a.png',
            {
                'source_rect': {'x': 32, 'y': 0, 'width': 32, 'height': 32},
                'cell_rect': {'width': 16, 'height': 16},
                'names': ['p', 'q', 'r', 's']
            }
        ])
        self.assertEqual((0, 0, 16, 16), m.get_box('yellow'))
        self.assertEqual((48, 16, 64, 32), m.get_box('s'))



class CompositeResourceTests(TestCase):
    def test_change_one(self):
        # Create a pack with 2 resources in it.
        pack_ab = self.make_source_pack('AB', 'Has A and B', {'a.png': ('a.png', None), 'b.png': ('b.png', None)})
        res_a = pack_ab.get_resource('a.png')
        res_b = pack_ab.get_resource('b.png')
        map_a = GridMap((32, 32), (16, 16), ['yellow', 'red', 'orange', 'green'])
        map_b = GridMap((32, 32), (16, 16), ['blue', 'cyan', 'green', 'magenta'])

        # Now define a resource that combines these 2 resources.
        res = CompositeResource('b.png', res_b, map_b)
        res.replace(res_a, map_a, {'blue': 'green', 'magenta': 'yellow'})

        with open(os.path.join(self.test_dir, 'change_one.png'), 'wb') as strm:
            strm.write(res.get_bytes())

        # Check it matches the manually created image.
        bytes = res.get_bytes()
        self.assertRepresentIdenticalImages(self.get_data('a_b_replace.png'), bytes)


class MixerTests(TestCase):
    def test_get_pack_by_name(self):
        pack1 = self.sample_pack()
        
        mixer = Mixer()
        mixer.add_pack('zuul', pack1)
        
        pack2 = mixer.get_pack('zuul')
        self.assertTrue(pack1 is pack2)
        
    def sample_pack(self):
        simple_map = GridMap((32, 32), (16, 16), ['a', 'b', 'c', 'd'])
        return self.make_source_pack('AB', 'Has A and B', {'a.png': ('a.png', simple_map), 'b.png': ('b.png', simple_map)})
        
    def sample_pack_and_bytes(self):
        pack1 = self.sample_pack()        
        strm = StringIO()
        pack1.write_to(strm)
        return pack1, strm.getvalue()
        
    def assert_same_packs(self, pack1, pack2):
        self.assertEqual(pack1.label, pack2.label)
        self.assertEqual(pack1.desc, pack2.desc)
        for n in pack1.get_resource_names():
            if n.endswith('.txt'):
                self.assertEqual(pack1.get_resource(n).get_content(),
                    pack2.get_resource(n).get_content())
            else:
                self.assertRepresentIdenticalImages(
                        pack1.get_resource(n).get_bytes(), 
                        pack2.get_resource(n).get_bytes())
                        
    def test_get_pack_by_data(self):
        pack1, data1 = self.sample_pack_and_bytes()
        pack2 = Mixer().get_pack({'data': data1})
        self.assert_same_packs(pack1, pack2)
                
    def test_get_pack_by_base64(self):
        pack1, data1 = self.sample_pack_and_bytes()
        pack2 = Mixer().get_pack({'base64': b64encode(data1)})
        self.assert_same_packs(pack1, pack2)
        
    def test_get_pack_by_data_url(self):
        pack1, data1 = self.sample_pack_and_bytes()
        url = 'data:application/zip;base64,' + b64encode(data1)
        pack2 = Mixer().get_pack({'href': url})
        self.assert_same_packs(pack1, pack2)
        
    def test_get_pack_from_file(self):
        pack1 = self.sample_pack()
        file_path = os.path.join(self.test_dir, 'zum.zip')
        with open(file_path, 'wb') as strm:
            pack1.write_to(strm)
        pack2 = Mixer().get_pack({'file': file_path})
        self.assert_same_packs(pack1, pack2)
                
    def test_get_pack_from_file_uri(self):
        pack1 = self.sample_pack()
        file_path = os.path.join(self.test_dir, 'zum.zip')
        with open(file_path, 'wb') as strm:
            pack1.write_to(strm)
        pack2 = Mixer().get_pack({'href': 'file://' + os.path.abspath(file_path)})
        self.assert_same_packs(pack1, pack2)
        
    @patch('httplib2.Http.request')
    def test_get_pack_from_http(self, mock_meth):
        # Arrange that downloading any URL returns our pack.
        pack1, data1 = self.sample_pack_and_bytes()
        mock_meth.return_value = ({
            'status': '200',
            'content-type': 'application/zip',
            'content-length': str(len(data1)),
        }, data1)
        
        pack2 = Mixer().get_pack({'href': 'http://example.org/frog.zip'})
        self.assertEqual('http://example.org/frog.zip', mock_meth.call_args[0][0])
        self.assert_same_packs(pack1, pack2)   
        
    @patch('httplib2.Http.request')
    def test_get_pack_from_http(self, mock_meth):
        # Arrange that downloading any URL fails.
        pack1, data1 = self.sample_pack_and_bytes()
        mock_meth.return_value = ({
            'status': '404',
        }, 'Not found')
        
        with self.assertRaises(NotInMixer):
            pack2 = Mixer().get_pack({'href': 'http://example.org/frog.zip'})
        
    def test_b_plus_c(self):
        self.check_recipe({
            'mix': [
                {'pack': 'alpha_bravo', 'files': ['b.png']},
                {'pack': 'charlie', 'files': ['c.png']}
            ]
        }, {'b.png': 'b.png', 'c.png': 'c.png'}, ['a.png'])

    def test_a_b_replace_using_expliict_maps(self):
        self.check_recipe({
            'mix': [
                {
                    'pack': 'alpha_bravo',
                    'files': [
                        {
                            'file': 'a.png',
                            'source': 'b.png',
                            'map': {
                                'cell_rect': {'width': 16, 'height': 16},
                                'source_rect': {'width': 32, 'height': 32},
                                'names': ['blue', 'cyan', 'green', 'magenta']
                            },
                            'replace': {
                                'source': 'a.png',
                                'map': {
                                    'cell_rect': {'width': 16, 'height': 16},
                                    'source_rect': {'width': 32, 'height': 32},
                                    'names': ['yellow', 'red', 'orange', 'green']
                                },
                                'cells': {'blue': 'green', 'magenta': 'yellow'},
                            }
                        }
                    ]
                }
            ]
        }, {'a.png': 'a_b_replace.png'}, ['b.png'])


    def test_a_b_replace_using_pack_atlas(self):
        self.check_recipe({
            'mix': [
                {
                    'pack': 'alpha_bravo',
                    'files': [
                        {
                            'file': 'a.png',
                            'source': 'b.png',
                            'replace': {
                                'source': 'a.png',
                                'cells': {'a': 'd', 'd': 'a'},
                            }
                        }
                    ]
                }
            ]
        }, {'a.png': 'a_b_replace.png'}, ['b.png'])
        
        
    def test_a_b_replace_single_mix(self):
        self.check_recipe({
            'mix': {
                'pack': 'alpha_bravo',
                'files': [
                    {
                        'file': 'a.png',
                        'source': 'b.png',
                        'replace': {
                            'source': 'a.png',
                            'cells': {'a': 'd', 'd': 'a'},
                        }
                    }
                ]
            }
        }, {'a.png': 'a_b_replace.png'}, ['b.png'])
        
    def test_a_b_replace_two_packs(self):
        self.check_recipe({
            'mix': {
                'pack': 'alpha_only',
                'files': [
                    {
                        'file': 'a.png',
                        'replace': [
                            {   # rearrange existing image
                                # source implicitly same as file
                                'cells': {
                                    'a': 'd', 'd': 'a'
                                }
                            },
                            { # grab bits from another image
                                'pack': 'only_bravo',
                                'source': 'b.png',
                                'cells': ['b', 'c'],
                            },
                        ]
                    }
                ]
            }
        }, {'a.png': 'a_b_replace.png'}, ['b.png'])


    def check_recipe(self, recipe, expected_resources, unexpected_resources):
        recipe.update({
            'label': 'Composite pack',
            'desc': 'A crazy mixed-up pack',
        })

        simple_map = GridMap((32, 32), (16, 16), ['a', 'b', 'c', 'd'])

        mixer = Mixer()
        mixer.add_pack('alpha_bravo', self.make_source_pack('AB', 'Has A and B', {'a.png': ('a.png', simple_map), 'b.png': ('b.png', simple_map)}))
        mixer.add_pack('charlie', self.make_source_pack('C', 'Has C', {'c.png': ('c.png', simple_map)}))
        mixer.add_pack('alpha_only', self.make_source_pack('A', 'Has A', {'a.png': ('a.png', simple_map)}))
        mixer.add_pack('only_bravo', self.make_source_pack('B', 'Has B', {'b.png': ('b.png', simple_map)}))
        
        pack = mixer.make(recipe)

        self.assertEqual('Composite pack', pack.label)
        self.assertEqual('A crazy mixed-up pack', pack.desc)
        self.check_pack(pack, expected_resources, unexpected_resources)
        return pack

    def check_pack(self, pack, expected_contents, expected_absent):
        strm = StringIO()
        pack.write_to(strm)

        with open(os.path.join(self.test_dir, 'tmp.zip'), 'wb') as f:
            f.write(strm.getvalue())

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            for file_name, resource_name in expected_contents.items():
                self.assertRepresentIdenticalImages(
                        self.get_data(resource_name),
                        zip.read(file_name),
                        'Expected contents of {actual} to match {expected}'.format(actual=file_name, expected=resource_name))
            for file_name in expected_absent:
                try:
                    zip.read(file_name)
                    self.fail('Should not find {0}'.format(file_name))
                except KeyError:
                    pass


if __name__ == '__main__':
	unittest.main()