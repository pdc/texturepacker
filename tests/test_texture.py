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

from texturepacker import *
from datetime import datetime, timedelta
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from StringIO import StringIO
from base64 import b64encode
import shutil
import httplib2
import json


class TestCase(unittest.TestCase):
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_data'))
    test_dir = os.path.abspath(os.path.join(os.path.dirname(__file__),  'test_working'))

    def setUp(self):
        if not os.path.exists(self.test_dir):
            os.mkdir(self.test_dir)

        cache_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'test_cache'))
        if not os.path.exists(cache_dir):
            os.mkdir(cache_dir)
        set_http_cache(cache_dir)

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

    def assert_PNGs_match(self, bytes1, bytes2, msg=None):
        im1 = Image.open(StringIO(bytes1))
        if isinstance(bytes2, ResourceBase):
            bytes2 = bytes2.get_bytes()
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
        m = self.atlas.get_map('a.png', None)
        self.assertEqual((0, 0, 16, 16), m.get_box('yellow'))

    def test_grid_map(self):
        m = self.atlas.get_map({
            'source_rect': {'width': 32, 'height': 32},
            'cell_rect': {'width': 16, 'height': 16},
            'names': ['p', 'q', 'r', 's']
        }, None)
        self.assertEqual((16, 16, 32, 32), m.get_box('s'))

    def test_composite_map(self):
        m = self.atlas.get_map([
            'a.png',
            {
                'source_rect': {'x': 32, 'y': 0, 'width': 32, 'height': 32},
                'cell_rect': {'width': 16, 'height': 16},
                'names': ['p', 'q', 'r', 's']
            }
        ], None)
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
        self.assert_PNGs_match(self.get_data('a_b_replace.png'), bytes)


class ExternalResourceTests(TestCase):
    def setUp(self):
        super(ExternalResourceTests, self).setUp()
        self.file_name = 'stuff.json'
        self.file_path = os.path.join(self.test_dir, self.file_name)
        self.stuff = {'foo': 'bar', 'baz': 'quux'}
        with open(self.file_path, 'wb') as strm:
            json.dump(self.stuff, strm)
        self.loader = Loader()

    def test_bytes_file(self):
        with open(self.file_path, 'rb') as strm:
            expected_bytes = strm.read()
        actual_bytes = self.loader.get_bytes({'file': self.file_path}, base=None)
        self.assertEqual(expected_bytes, actual_bytes)

    def test_base(self):
        with open(self.file_path, 'rb') as strm:
            expected_bytes = strm.read()
        actual_bytes = self.loader.get_bytes({'file': self.file_name}, base='file:///' + self.test_dir)
        self.assertEqual(expected_bytes, actual_bytes)

    def test_base2(self):
        with open(self.file_path, 'rb') as strm:
            expected_bytes = strm.read()
        actual_bytes = self.loader.get_bytes({'file': self.file_name}, base={'file': self.test_dir})
        self.assertEqual(expected_bytes, actual_bytes)

    def test_base3(self):
        with open(self.file_path, 'rb') as strm:
            expected_bytes = strm.read()
        actual_bytes = self.loader.get_bytes({'file': self.file_name},
                base={'file': os.path.join(self.test_dir, 'other.json')})
        self.assertEqual(expected_bytes, actual_bytes)

    def test_get_spec(self):
        spec = self.loader.maybe_get_spec({'file': self.file_path}, base=None)
        self.assertEqual(self.stuff, spec)

    def test_get_spec_infer_suffix(self):
        spec = self.loader.maybe_get_spec({'file': os.path.join(self.test_dir, 'stuff')}, base=None, ext='json')
        self.assertEqual(self.stuff, spec)

    def test_get_spec_yaml(self):
        file_path = os.path.join(self.test_dir, 'nonsense.tpmaps')
        with open(file_path, 'wt') as strm:
            strm.write('hello: world\nthis:\n- that\n- the other\n')
        spec = self.loader.maybe_get_spec({'file': file_path}, base=None)
        self.assertEqual({'hello': 'world', 'this': ['that', 'the other']}, spec)

    def test_get_spec_inline(self):
        spec = self.loader.maybe_get_spec({'alpha': 'omega'}, base=None)
        self.assertEqual({'alpha': 'omega'}, spec)

    def test_get_spec_twice_loads_it_once(self):
        # testing caching
        spec1 = self.loader.maybe_get_spec({'file': self.file_path}, base=None)
        spec2 = self.loader.maybe_get_spec({'file': self.file_name}, base={'file': self.test_dir})
        self.assertTrue(spec1 is spec2)

    def test_url_1(self):
        self.assertEqual('file://' + os.path.abspath(self.file_path),
            self.loader.get_url({'file': self.file_path}, base=None))

    def test_url_2(self):
        self.assertEqual('file://' + os.path.abspath(self.file_path),
            self.loader.get_url({'file': self.file_name}, base={'file': self.test_dir}))

    @patch('__builtin__.open')
    def test_internal_url(self, mock_open):
        mock_open.return_value = StringIO('fish')
        url = 'minecraft:texturepacks/foo.tprx'
        spec = self.loader.maybe_get_spec({'href': url}, base=None)
        self.assertEqual('fish', spec)
        self.assertTrue(mock_open.called)

        expected_path = os.path.join(minecraft_texture_pack_dir_path(), 'foo.tprx')
        self.assertEqual(expected_path, mock_open.call_args[0][0])
        self.assertTrue(mock_open.call_args[0][1].startswith('r'))

        # XXX Add test requiring URLDECODE

    def test_custom_scheme(self):
        mock_func = Mock()
        mock_func.return_value = ({'content-type': 'text/plain'}, StringIO('hello'))
        self.loader.add_scheme('bim', mock_func)
        self.assertEqual('hello', self.loader.get_bytes('bambi', 'bim:///gooshy/gooshy/gander'))
        self.assertEqual('///gooshy/gooshy/bambi', mock_func.call_args[0][0])


class ResolveUrlTests(unittest.TestCase):
    # I ended up creating my own generic URL resolver, because
    # the standard library’s urljoin seems reluctant to tackle
    # unknown URL schemes. (Not entirely unreasonably.)
    def test_relative(self):
        self.assertEqual('foop:///derp/yum', resolve_generic_url('foop:///derp/herp', 'yum'))

    def test_relative_final_slash(self):
        self.assertEqual('foop:///derp/herp/yum', resolve_generic_url('foop:///derp/herp/', 'yum'))

    def test_relative_zero_length_path(self):
        self.assertEqual('foop:///derp/yum', resolve_generic_url('foop:///derp/', 'yum'))

    def test_relative_omitted_path(self):
        self.assertEqual('foop://derp/yum', resolve_generic_url('foop://derp', 'yum'))

    def test_relative_omitted_authority(self):
        self.assertEqual('foop:///derp/yum', resolve_generic_url('foop:///derp/herp', 'yum'))

    def test_abspath(self):
        self.assertEqual('foop:///yum', resolve_generic_url('foop:///derp/herp/', '/yum'))

    def test_abspath_authority(self):
        self.assertEqual('foop://bonk/yum', resolve_generic_url('foop://bonk/derp/herp/', '/yum'))

    def test_absolute(self):
        self.assertEqual('shump://bank/flank/gazank',
                resolve_generic_url('foop://bink/fink', 'shump://bank/flank/gazank'))

    def test_dotdot(self):
        self.assertEqual('smuurf://smurf/derf/lerf',
                resolve_generic_url('smuurf://smurf/derf/bink/bank.frankly.dank', '../lerf'))

    def test_dotdotdotdot(self):
        self.assertEqual('smuurf://smurf/lerf',
                resolve_generic_url('smuurf://smurf/derf/bink/bank.frankly.dank', '../../lerf'))

    def test_dotdot_respects_authority(self):
        self.assertEqual('smuurf://smurf/lerf',
                resolve_generic_url('smuurf://smurf/derf/bink/bank.frankly.dank', '../../../lerf'))

    def test_dot(self):
        self.assertEqual('smuurf://smurf/derf/bink/lerf',
                resolve_generic_url('smuurf://smurf/derf/bink/bank.frankly.dank', './lerf'))

    def test_dotslash(self):
        self.assertEqual('smuurf://smurf/derf/bink/',
                resolve_generic_url('smuurf://smurf/derf/bink/bank.frankly.dank', './'))

    def test_nothing_at_all(self):
        self.assertEqual('smuurf://smurf/derf/bink/bank.frankly.dank',
                resolve_generic_url('smuurf://smurf/derf/bink/bank.frankly.dank', ''))

    def test_something_dotdot_something_for_heavens_sake(self):
        self.assertEqual('smuurf://smurf/derf/bink/bink/bib/nib/jib',
                resolve_generic_url('smuurf://smurf/derf/bink/bink/frothwagon', 'bib/fib/../nib/jib'))

    def test_something_dotdot_sneak_attacj(self):
        self.assertEqual('smuurf://smurf/etc/passwd',
                resolve_generic_url('smuurf://smurf/derf/bink/bink/frothwagon', 'bib/../../../../../../../../../../etc/passwd'))


class MixerTests(TestCase):
    def test_get_pack_by_name(self):
        pack1 = self.sample_pack()

        mixer = Mixer()
        mixer.add_pack('zuul', pack1)

        pack2 = mixer.get_pack('$zuul')
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
                self.assert_PNGs_match(
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

    def test_get_pack_by_naked_data_url(self):
        pack1, data1 = self.sample_pack_and_bytes()
        url = 'data:application/zip;base64,' + b64encode(data1)
        pack2 = Mixer().get_pack(url)
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

    def test_get_pack_from_naked_file_uri(self):
        pack1 = self.sample_pack()
        file_path = os.path.join(self.test_dir, 'zum.zip')
        with open(file_path, 'wb') as strm:
            pack1.write_to(strm)
        pack2 = Mixer().get_pack('file://' + os.path.abspath(file_path))
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

    # Identical to the abover except passing the URL as a string not dict.
    @patch('httplib2.Http.request')
    def test_get_pack_from_naked_http(self, mock_meth):
        # Arrange that downloading any URL returns our pack.
        pack1, data1 = self.sample_pack_and_bytes()
        mock_meth.return_value = ({
            'status': '200',
            'content-type': 'application/zip',
            'content-length': str(len(data1)),
        }, data1)

        pack2 = Mixer().get_pack('http://example.org/frog.zip')
        # Not laoded yet:
        self.assertFalse(mock_meth.call_args)

        res = pack2.get_resource('a.png')
        # Has now downloaded the data:
        self.assertEqual('http://example.org/frog.zip', mock_meth.call_args[0][0])
        self.assert_same_packs(pack1, pack2)

    def test_get_pack_from_relative_file(self):
        pack1 = self.sample_pack()
        file_path = os.path.join(self.test_dir, 'zum.zip')
        with open(file_path, 'wb') as strm:
            pack1.write_to(strm)
        pack2 = Mixer().get_pack({'file': 'zum.zip'},
                base='file://' + os.path.join(self.test_dir, 'zip.json'))
        self.assert_same_packs(pack1, pack2)

    def test_get_pack_from_naked_relative_file(self):
        pack1 = self.sample_pack()
        file_path = os.path.join(self.test_dir, 'zum.zip')
        with open(file_path, 'wb') as strm:
            pack1.write_to(strm)
        pack2 = Mixer().get_pack('zum.zip',
                base='file://' + os.path.join(self.test_dir, 'zip.json'))
        self.assert_same_packs(pack1, pack2)

    @patch('httplib2.Http.request')
    def test_get_pack_from_http(self, mock_meth):
        # Arrange that downloading any URL fails.
        pack1, data1 = self.sample_pack_and_bytes()
        mock_meth.return_value = ({
            'status': '404',
        }, 'Not found')

        with self.assertRaises(CouldNotLoad):
            pack2 = Mixer().get_pack({'href': 'http://example.org/frog.zip'})

            # Force it to be loaded:
            res = pack2.get_resource('a.png')

    def test_get_pack_from_minecraft(self):
        pack1, data1 = self.sample_pack_and_bytes()

        with patch('__builtin__.open') as mock_open:
            mock_open.return_value = StringIO(data1)
            pack2 = Mixer().get_pack({'href': 'minecraft:texturepacks/foobar.zip'})
            self.assert_same_packs(pack1, pack2)

            expected_path = os.path.join(minecraft_texture_pack_dir_path(), 'foobar.zip')
            self.assertEqual(expected_path, mock_open.call_args[0][0])

    def test_get_pack_from_dir(self):
        # So many permutations, so many tests …
        pack_name = 'bilbo_baggins'
        pack_path = os.path.join(self.test_dir, pack_name)
        if os.path.exists(pack_path):
            shutil.rmtree(pack_path)
        os.mkdir(pack_path)
        with open(os.path.join(pack_path, 'a.png'), 'wb') as strm:
            strm.write(self.get_data('a.png'))
        with open(os.path.join(pack_path, 'b.png'), 'wb') as strm:
            strm.write(self.get_data('b.png'))
        pack = Mixer().get_pack({'file': pack_name}, base={'file': self.test_dir})
        self.assertEqual(set(['a.png', 'b.png']), set(pack.get_resource_names()))

    def test_get_pack_from_naked_dir(self):
        # So many permutations, so many tests …
        pack_name = 'bilbo_baggins'
        pack_path = os.path.join(self.test_dir, pack_name)
        if os.path.exists(pack_path):
            shutil.rmtree(pack_path)
        os.mkdir(pack_path)
        with open(os.path.join(pack_path, 'a.png'), 'wb') as strm:
            strm.write(self.get_data('a.png'))
        with open(os.path.join(pack_path, 'b.png'), 'wb') as strm:
            strm.write(self.get_data('b.png'))
        pack = Mixer().get_pack(pack_name, base={'file': self.test_dir})
        self.assertEqual(set(['a.png', 'b.png']), set(pack.get_resource_names()))

    def test_b_plus_c(self):
        self.check_recipe({
            'parameters': {
                'packs': [
                    'alpha_bravo',
                    'charlie',
                ]
            },
            'mix': [
                {'pack': '$alpha_bravo', 'files': ['b.png']},
                {'pack': '$charlie', 'files': ['c.png']}
            ]
        }, {'b.png': 'b.png', 'c.png': 'c.png'}, ['a.png'])

    def test_c_replaces_b(self):
        self.check_recipe({
            "mix": [
                {
                    'pack': '$alpha_bravo',
                    'files': [
                        'a.png',
                    ]
                },
                {
                    'pack': '$charlie',
                    'files': [
                        {
                            'file': 'b.png',
                            'source': 'c.png',
                        }
                    ]
                }
            ]
        }, {'a.png': 'a.png', 'b.png': 'c.png'}, ['c.png'])

    def test_c_replaces_b_star(self):
        # Same as the above, except using `*` to copy
        # all missing files from alpha_bravo
        # instead of listing them explicity.
        self.check_recipe({
            'parameters': {
                'packs': [
                    'alpha_bravo',
                    'charlie',
                ]
            },
            "mix": [
                {
                    'pack': '$alpha_bravo',
                    'files': [
                        '*.png',
                    ]
                },
                {
                    'pack': '$charlie',
                    'files': [
                        {
                            'file': 'b.png',
                            'source': 'c.png',
                        }
                    ]
                },
            ]
        }, {'a.png': 'a.png', 'b.png': 'c.png'}, ['c.png'])

    def test_a_b_replace_using_expliict_maps(self):
        # Previous tests used maps preloaded in to the Mixer.
        self.check_recipe({
            'parameters': {
                'packs': [
                    'alpha_bravo',
                ]
            },
            'mix': [
                {
                    'pack': '$alpha_bravo',
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
                    'pack': '$alpha_bravo',
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
        # The difference here is that the mix can be 1 dict instead of a lst
        self.check_recipe({
            'mix': {
                'pack': '$alpha_bravo',
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
                'pack': '$alpha_only',
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
                                'pack': '$only_bravo',
                                'source': 'b.png',
                                'cells': ['b', 'c'],
                            },
                        ]
                    }
                ]
            }
        }, {'a.png': 'a_b_replace.png'}, ['b.png'])

    def test_a_b_replace_two_files(self):
        with open(os.path.join(self.test_dir, 'xa.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'aa', 'aaaa', {'a.png': ('a.png', None)})
        with open(os.path.join(self.test_dir, 'xb.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'bb', 'bb', {'b.png': ('b.png', None)})
        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'mix': {
                'pack': {
                    'href': 'xb.zip',  # relative file name
                    'maps': {
                        'b.png': {
                            'source_rect': {'width': 32, 'height': 32},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['a', 'b', 'c', 'd'],
                        }
                    }
                },
                'files': [
                    '*.png',
                    {
                        'file': 'ab.png',
                        'source': 'b.png',
                        'replace': {
                            'pack': {
                                'file': os.path.join(self.test_dir, 'xa.zip'), # absolute file name
                                'maps': {
                                    'a.png': {
                                        'source_rect': {'width': 32, 'height': 32},
                                        'cell_rect': {'width': 16, 'height': 16},
                                        'names': ['a', 'b', 'c', 'd'],
                                    }
                                }
                            },
                            'source': 'a.png',
                            'cells': {'d': 'a', 'a': 'd'},
                        }
                    }
                ]
            }
        }
        pack = Mixer().make(recipe, base='file://' + os.path.abspath(self.test_dir) + '/')

        self.assertEqual('ab', pack.label)
        self.assertEqual('ababababk', pack.desc)
        self.check_pack(pack, {'ab.png': 'a_b_replace.png', 'b.png': 'b.png'}, [])

    def test_a_b_replace_two_files_declared(self):
        with open(os.path.join(self.test_dir, 'xa.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'aa', 'aaaa', {'a.png': ('a.png', None)})
        with open(os.path.join(self.test_dir, 'xb.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'bb', 'bb', {'b.png': ('b.png', None)})
        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'packs': {
                'aa': {
                    'file': os.path.join(self.test_dir, 'xa.zip'), # absolute file name
                    'maps': {
                        'a.png': {
                            'source_rect': {'width': 32, 'height': 32},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['a', 'b', 'c', 'd'],
                        }
                    }
                },
                'bb': {
                    'file': 'xb.zip',  # relative file name
                    'maps': {
                        'b.png': {
                            'source_rect': {'width': 32, 'height': 32},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['a', 'b', 'c', 'd'],
                        }
                    }
                }
            },
            'mix': {
                'pack': '$bb',
                'files': [
                    {
                        'file': 'ab.png',
                        'source': 'b.png',
                        'replace': {
                            'pack': '$aa',
                            'source': 'a.png',
                            'cells': {'d': 'a', 'a': 'd'},
                        }
                    }
                ]
            }
        }
        pack = Mixer().make(recipe, base='file://' + os.path.abspath(self.test_dir))

        self.assertEqual('ab', pack.label)
        self.assertEqual('ababababk', pack.desc)
        self.check_pack(pack, {'ab.png': 'a_b_replace.png'}, ['b.png'])

    def test_a_b_replace_external_atlas(self):
        with open(os.path.join(self.test_dir, 'ab_maps.json'), 'wb') as strm:
            json.dump({
                'a.png': {
                    'source_rect': {'width': 32, 'height': 32},
                    'cell_rect': {'width': 16, 'height': 16},
                    'names': ['a', 'b', 'c', 'd'],
                },
                'b.png': {
                    'source_rect': {'width': 32, 'height': 32},
                    'cell_rect': {'width': 16, 'height': 16},
                    'names': ['a', 'b', 'c', 'd'],
                }
            }, strm)
        with open(os.path.join(self.test_dir, 'xa.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'aa', 'aaaa', {'a.png': ('a.png', None)})
        with open(os.path.join(self.test_dir, 'xb.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'bb', 'bb', {'b.png': ('b.png', None)})
        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'packs': {
                'aa': {
                    'file': os.path.join(self.test_dir, 'xa.zip'), # absolute file name
                    'maps': {'file': 'ab_maps.json'}
                },
                'bb': {
                    'file': 'xb.zip',  # relative file name
                    'maps': {'file': 'ab_maps.json'}
                }
            },
            'mix': {
                'pack': '$bb',
                'files': [
                    {
                        'file': 'ab.png',
                        'source': 'b.png',
                        'replace': {
                            'pack': '$aa',
                            'source': 'a.png',
                            'cells': {'d': 'a', 'a': 'd'},
                        }
                    }
                ]
            }
        }
        pack = Mixer().make(recipe, base='file://' + os.path.abspath(self.test_dir))

        self.assertEqual('ab', pack.label)
        self.assertEqual('ababababk', pack.desc)
        self.check_pack(pack, {'ab.png': 'a_b_replace.png'}, ['b.png'])

    def test_composite_atlas(self):
        with open(os.path.join(self.test_dir, 'a.tpmaps'), 'wb') as strm:
            json.dump({
                'a.png': {
                    'source_rect': {'width': 32, 'height': 32},
                    'cell_rect': {'width': 16, 'height': 16},
                    'names': ['aa', 'ab', 'ac', 'ad'],
                }
            }, strm)
        with open(os.path.join(self.test_dir, 'xa.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'aa', 'aaaa', {'a.png': ('a.png', None)})
        with open(os.path.join(self.test_dir, 'xb.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'bb', 'bb', {'b.png': ('b.png', None)})
        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'maps': [
                {'file': 'a.tpmaps'}, # external ref
                { # inline spec
                    'b.png': {
                        'source_rect': {'width': 32, 'height': 32},
                        'cell_rect': {'width': 16, 'height': 16},
                        'names': ['ba', 'bb', 'bc', 'bd'],
                    }
                }
            ],
            'packs': {
                'aa': {
                    'file': os.path.join(self.test_dir, 'xa.zip'), # absolute file name
                },
                'bb': {
                    'file': 'xb.zip',  # relative file name
                }
            },
            'mix': {
                'pack': '$bb',
                'files': [
                    {
                        'file': 'ab.png',
                        'source': 'b.png',
                        'replace': {
                            'pack': '$aa',
                            'source': 'a.png',
                            'cells': {'bd': 'aa', 'ba': 'ad'},
                        }
                    }
                ]
            }
        }
        pack = Mixer().make(recipe, base='file://' + os.path.abspath(self.test_dir))

        self.assertEqual('ab', pack.label)
        self.assertEqual('ababababk', pack.desc)
        self.check_pack(pack, {'ab.png': 'a_b_replace.png'}, ['b.png'])

    def test_composite_atlas_multi_files(self):
        # This eleaborate set-up represents the case where
        # we have a beta 1.2 atlas which we want to augment
        # to describe a texure pack woith extra (alternate) textures.
        map_dir = os.path.join(self.test_dir, 'mapz')
        if not os.path.exists(map_dir):
            os.mkdir(map_dir)
        with open(os.path.join(map_dir, 'a1.tpmaps'), 'wb') as strm:
            json.dump({
                'a.png': {
                    'source_rect': {'width': 32, 'height': 16},
                    'cell_rect': {'width': 16, 'height': 16},
                    'names': ['aa', 'ab'],
                }
            }, strm)
        with open(os.path.join(map_dir, 'a2.tpmaps'), 'wb') as strm:
            json.dump([ # composite of many atlases
                {'file': 'a1.tpmaps'},
                {
                    'a.png': [ # composite map
                        'a.png', # from a1.tpmaps
                        {
                            'source_rect': {'y': 16, 'width': 32, 'height': 16},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['ac', 'ad'],
                        }]
                }
            ], strm)
        with open(os.path.join(self.test_dir, 'xa.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'aa', 'aaaa', {'a.png': ('a.png', None)})
        with open(os.path.join(self.test_dir, 'xb.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'bb', 'bb', {'b.png': ('b.png', None)})
        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'maps': [
                {'file': 'mapz/a2.tpmaps'}, # external ref
                { # inline spec
                    'b.png': {
                        'source_rect': {'width': 32, 'height': 32},
                        'cell_rect': {'width': 16, 'height': 16},
                        'names': ['ba', 'bb', 'bc', 'bd'],
                    }
                }
            ],
            'packs': {
                'aa': {
                    'file': os.path.join(self.test_dir, 'xa.zip'), # absolute file name
                },
                'bb': {
                    'file': 'xb.zip',  # relative file name
                }
            },
            'mix': {
                'pack': '$bb',
                'files': [
                    {
                        'file': 'ab.png',
                        'source': 'b.png',
                        'replace': {
                            'pack': '$aa',
                            'source': 'a.png',
                            'cells': {'bd': 'aa', 'ba': 'ad'},
                        }
                    }
                ]
            }
        }
        pack = Mixer().make(recipe, base='file://' + os.path.abspath(self.test_dir))

        self.assertEqual('ab', pack.label)
        self.assertEqual('ababababk', pack.desc)
        self.check_pack(pack, {'ab.png': 'a_b_replace.png'}, ['b.png'])

    @patch('httplib2.Http.request')
    def test_composite_atlas_multi_http(self, mock_request):
        # This eleaborate set-up represents the case where
        # we have a beta 1.2 atlas which we want to augment
        # to describe a texure pack woith extra (alternate) textures.
        files = [
            json.dumps([ # composite of many atlases
                {'href': 'a1.tpmaps'},
                {
                    'a.png': [ # composite map
                        'a.png', # from a1.tpmaps
                        {
                            'source_rect': {'y': 16, 'width': 32, 'height': 16},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['ac', 'ad'],
                        }]
                }
            ]),
            json.dumps({
                'a.png': {
                    'source_rect': {'width': 32, 'height': 16},
                    'cell_rect': {'width': 16, 'height': 16},
                    'names': ['aa', 'ab'],
                }
            })
        ]
        mock_request.side_effect = lambda *args, **kwargs: ({'status': '200', 'content-type': 'application/json'}, files.pop(0))

        with open(os.path.join(self.test_dir, 'xa.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'aa', 'aaaa', {'a.png': ('a.png', None)})
        with open(os.path.join(self.test_dir, 'xb.zip'), 'wb') as strm:
            self.write_pack_contents(strm, 'bb', 'bb', {'b.png': ('b.png', None)})
        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'maps': [
                {'href': 'http://example.org/mapz/a2.tpmaps'}, # external ref
                { # inline spec
                    'b.png': {
                        'source_rect': {'width': 32, 'height': 32},
                        'cell_rect': {'width': 16, 'height': 16},
                        'names': ['ba', 'bb', 'bc', 'bd'],
                    }
                }
            ],
            'packs': {
                'aa': {
                    'file': os.path.join(self.test_dir, 'xa.zip'), # absolute file name
                },
                'bb': {
                    'file': 'xb.zip',  # relative file name
                }
            },
            'mix': {
                'pack': '$bb',
                'files': [
                    {
                        'file': 'ab.png',
                        'source': 'b.png',
                        'replace': {
                            'pack': '$aa',
                            'source': 'a.png',
                            'cells': {'bd': 'aa', 'ba': 'ad'},
                        }
                    }
                ]
            }
        }
        pack = Mixer().make(recipe, base='file://' + os.path.abspath(self.test_dir))

        self.assertEqual(2, mock_request.call_count)
        self.assertEqual('http://example.org/mapz/a2.tpmaps', mock_request.call_args_list[0][0][0])
        self.assertEqual('http://example.org/mapz/a1.tpmaps', mock_request.call_args_list[1][0][0])

        self.assertEqual('ab', pack.label)
        self.assertEqual('ababababk', pack.desc)
        self.check_pack(pack, {'ab.png': 'a_b_replace.png'}, ['b.png'])


    def test_copy_star_png_from_dir_within_dir(self):
        # Test added to find a bug.
        dir_path = os.path.join(self.test_dir, 'flippy')
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        os.mkdir(dir_path)
        subdir_path = os.path.join(dir_path, 'floo')
        os.mkdir(subdir_path)
        before = datetime.now()
        with open(os.path.join(subdir_path, 'a.png'), 'wb') as strm:
            strm.write(self.get_data('a.png'))
        with open(os.path.join(dir_path, 'b.png'), 'wb') as strm:
            strm.write(self.get_data('b.png'))

        recipe = {
            'label': 'ab',
            'desc': 'ababababk',
            'mix': {
                'pack': {
                    'href': 'flippy/',
                    'maps': {
                        'a.png': {
                            'source_rect': {'width': 32, 'height': 32},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['a1', 'a2', 'a3', 'a4'],
                        },
                        'b.png': {
                            'source_rect': {'width': 32, 'height': 32},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['b1', 'b2', 'b3', 'b4'],
                        }
                    },
                },
                'files': ['*.png'],
            }
        }
        pack = Mixer().make(recipe, 'file://' + os.path.join(os.path.abspath(self.test_dir), 'foo.tprx'))
        self.check_pack(pack, {'floo/a.png': 'a.png', 'b.png': 'b.png'}, [])

    def test_missing_parameters(self):
        recipe = {
            'label': 'monster',
            'desc': 'foo',
            'parameters': {
                'packs': ['alphabeta'],
            },
            'mix': {
                'pack': '$alphabeta',
                'files': ['*.png'],
            }
        }
        with self.assertRaises(MissingParameter):
            pack = Mixer().make(recipe, None)

    def test_parametized_label(self):
        recipe = {
            'label': '{{ alpha_only.label }}{{ only_bravo.label }}',
            'desc': '{{ alpha_only.desc }}! {{ only_bravo.desc }}!!',
            'mix': [
                {
                    'pack': '$alpha_only',
                    'files': ['*.png'],
                },
                {
                    'pack': '$only_bravo',
                    'files': ['*.png'],
                }
            ]
        }
        pack = self.make_mixer_with_packs().make(recipe)
        self.assertEqual('AB', pack.label)
        self.assertEqual('Has A! Has B!!', pack.desc)

    def check_recipe(self, recipe, expected_resources, unexpected_resources):
        recipe.update({
            'label': 'Composite pack',
            'desc': 'A crazy mixed-up pack',
        })
        mixer = self.make_mixer_with_packs()
        pack = mixer.make(recipe)

        self.assertEqual('Composite pack', pack.label)
        self.assertEqual('A crazy mixed-up pack', pack.desc)
        self.check_pack(pack, expected_resources, unexpected_resources)
        return pack

    def make_mixer_with_packs(self):
        simple_map = GridMap((32, 32), (16, 16), ['a', 'b', 'c', 'd'])

        mixer = Mixer()
        mixer.add_pack('alpha_bravo', self.make_source_pack('AB', 'Has A and B', {'a.png': ('a.png', simple_map), 'b.png': ('b.png', simple_map)}))
        mixer.add_pack('charlie', self.make_source_pack('C', 'Has C', {'c.png': ('c.png', simple_map)}))
        mixer.add_pack('alpha_only', self.make_source_pack('A', 'Has A', {'a.png': ('a.png', simple_map)}))
        mixer.add_pack('only_bravo', self.make_source_pack('B', 'Has B', {'b.png': ('b.png', simple_map)}))
        return mixer

    def check_pack(self, pack, expected_contents, expected_absent):
        strm = StringIO()
        pack.write_to(strm)

        with open(os.path.join(self.test_dir, 'tmp.zip'), 'wb') as f:
            f.write(strm.getvalue())

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            for file_name, resource_name in expected_contents.items():
                self.assert_PNGs_match(
                        self.get_data(resource_name),
                        zip.read(file_name),
                        'Expected contents of {actual} to match {expected}'.format(
                                actual=file_name, expected=resource_name))
            for file_name in expected_absent:
                try:
                    zip.read(file_name)
                    self.fail('Should not find {0}'.format(file_name))
                except KeyError:
                    pass


class TestTexturePackDir(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("darwin"), "requires Mac OS X")
    def test_mac_os_x(self):
        expected = os.path.expanduser('~/Library/Application Support/minecraft/texturepacks')
        actual = minecraft_texture_pack_dir_path()
        self.assertEqual(expected, actual)


class TestLastModified(TestCase):
    def assert_datetime_between(self, before, actual, after, epsilon):
        """Assert that the 3 datetimes are in nondecreasing order.

        Arguments --
            before, actual, after -- three datetime values to compare
            epsilon -- timedelta represeneding the precision of actual.

        Two datetimes will be considered equal if they differ by
        no more than epsilon.

        The epsilon parameter is required because filetimes are
        recorded to the nearest second, and ZIP archive members
        to the nearest 2 seconds.
        """
        self.assertTrue(before - epsilon <= actual  <= after + epsilon,
            'Expected {0} <= {1} <= {2} within {3}'.format(
                before, actual, after, epsilon))

    def check_modified_since(self, x):
        self.assertTrue(x.is_modified_since(x.get_last_modified() + timedelta(seconds=-1)))
        self.assertFalse(x.is_modified_since(x.get_last_modified()))
        self.assertFalse(x.is_modified_since(x.get_last_modified() + timedelta(seconds=1)))

    def test_file_pack(self):
        simple_map = GridMap((32, 32), (16, 16), ['a', 'b', 'c', 'd'])

        file_path = os.path.join(self.test_dir, 'manga.zip')
        before = datetime.now()
        with open(file_path, 'wb') as strm:
            self.write_pack_contents(strm,'AB', 'Has A and B',
                    {'a.png': ('a.png', simple_map)})
        after = datetime.now()

        fake_time = (2010, 2, 20, 10, 39, 55)
        with ZipFile(file_path, 'a') as zip:
            zip.writestr(ZipInfo('b.png', fake_time), self.get_data('b.png'))

        pack = SourcePack(file_path, Atlas())
        self.assert_datetime_between(before, pack.get_last_modified(), after, timedelta(seconds=2))

        res_a = pack.get_resource('a.png')
        # In this case the timne recorded is the instant the
        # resource was added to the ZIP since we do not specify a timestamp.
        self.assert_datetime_between(before, res_a.get_last_modified(), after,timedelta(seconds=2))

        res_b = pack.get_resource('b.png')
        dt = datetime(*fake_time)
        self.assert_datetime_between(dt, res_b.get_last_modified(), dt, timedelta(seconds=2))

        self.check_modified_since(res_a)
        self.check_modified_since(res_b)

        for n in pack.get_resource_names():
            print n, pack.get_resource(n).is_modified_since(pack.get_last_modified())
        self.check_modified_since(pack)

    def test_directory_pack(self):
        dir_path = os.path.join(self.test_dir, 'happipakq')
        if os.path.exists(dir_path):
            shutil.rmtree(dir_path)
        os.mkdir(dir_path)
        before = datetime.now()
        with open(os.path.join(dir_path, 'a.png'), 'wb') as strm:
            strm.write(self.get_data('a.png'))
        after = datetime.now()
        shutil.copy2(os.path.join(self.data_dir, 'b.png'),
                os.path.join(dir_path, 'b.png'))
        # Since that copied the last-modified time of the file,
        # we now have a dir containing files with 2 different modified times.

        pack = SourcePack(dir_path, Atlas())
        self.assert_datetime_between(before, pack.get_last_modified(), after, timedelta(seconds=1))

        res_a = pack.get_resource('a.png')
        self.assert_datetime_between(before, res_a.get_last_modified(), after,timedelta(seconds=1))

        res_b = pack.get_resource('b.png')
        t = datetime.fromtimestamp(os.stat(os.path.join(dir_path, 'b.png')).st_mtime)
        self.assert_datetime_between(t, res_b.get_last_modified(), t,timedelta(seconds=1))

        self.check_modified_since(res_a)
        self.check_modified_since(res_b)
        self.check_modified_since(pack)

    def test_composite_resource(self):
        # Create 2 resources
        simple_map = GridMap((32, 32), (16, 16), ['a', 'b', 'c', 'd'])

        file_path = os.path.join(self.test_dir, 'aa.zip')
        before = datetime.now()
        with open(file_path, 'wb') as strm:
            self.write_pack_contents(strm,'AB', 'Has A and B',
                    {'a.png': ('a.png', simple_map)})
        after = datetime.now()

        fake_time = (2010, 2, 20, 10, 39, 55)
        with ZipFile(file_path, 'a') as zip:
            zip.writestr(ZipInfo('b.png', fake_time), self.get_data('b.png'))

        pack = SourcePack(file_path, Atlas({'a.png': simple_map, 'b.png': simple_map}))
        res = CompositeResource('ab.png', pack.get_resource('b.png'), simple_map)
        res.replace(pack.get_resource('a.png'), simple_map, {'a': 'd', 'd': 'a'})
        self.assert_datetime_between(before, res.get_last_modified(), after, timedelta(seconds=2))

        self.check_modified_since(res)
        self.check_modified_since(pack)

    def test_renamed_resource(self):
        before = datetime.now()
        pack = self.make_source_pack('Sign pack', 'Just a test', {'item/sign.png': ('sign.png', None)})
        after = datetime.now()
        res = RenamedResource('portent.png', pack.get_resource('item/sign.png'))
        self.assert_datetime_between(before, res.get_last_modified(), after, timedelta(seconds=2))

        self.check_modified_since(res)


class PackPngTests(TestCase):
    def setUp(self):
        self.map = GridMap((256, 256), (16, 16), ['{0:02X}'.format(x) for x in range(256)])
        self.pack = self.make_source_pack('Zumpy', 'Ging', {'terrain.png': ('gingham.png', self.map)})

    def test_10(self):
        res = PackIconResource(self.pack.get_resource('terrain.png'), self.map,
            ['ED', 'DA', 'EB', 'FE', '31', 'ED', 'AC', 'BF', 'DA', '96'])
            # Was DEADBEEF13DECAFBAD69 but I got the coordinates reversed in the test image.
        with open(os.path.join(self.test_dir, 'pack10.png'), 'wb') as strm:
            strm.write(res.get_bytes())
        self.assert_PNGs_match(self.get_data('gingham10.png'), res.get_bytes())

    def test_recipe_10(self):
        m = Mixer()
        m.add_pack('gingham', self.pack)
        pack = m.make({
            'label': 'lab',
            'desc': 'desc',
            'mix': {
                'pack': '$gingham',
                'files': [
                    'terrain.png',
                    {
                        'source': 'terrain.png',
                        'pack_icon': {
                            'cells': ['ED', 'DA', 'EB', 'FE', '31', 'ED', 'AC', 'BF', 'DA', '96'],
                        }
                    }
                ]
            }
        })
        print pack.get_resource_names()
        with open(os.path.join(self.test_dir, 'recipe_10.zip'), 'wb') as strm:
            pack.write_to(strm)
        self.assert_PNGs_match(self.get_data('gingham10.png'),
            pack.get_resource('pack.png').get_bytes())


class GuessPackTests(TestCase):
    def setUp(self):
        self.zip_path = os.path.join(self.test_dir, 'brukken.zip')
        with ZipFile(self.zip_path, 'w') as zip:
            zip.writestr('terrain.png', self.get_data('gingham.png'))
            zip.writestr('sign.png', self.get_data('sign.png'))
            zip.writestr('irrelevant.png', self.get_data('a.png'))

    def test_from_zip(self):
        pack = Mixer().make({
            'label': 'unjumbled',
            'desc': 'untwisted',
            'mix': {
                'pack': {
                    'href': url_from_file_path(self.zip_path),
                    'unjumble': {
                        'terrain.png': {
                            'source_rect': {'width': 256, 'height': 256},
                            'cell_rect': {'width': 16, 'height': 16},
                            'names': ['{0:02X}'.format(x) for x in range(256)],
                        },
                        'item/sign.png': None,
                    },
                },
                'files': [
                    '*.png',
                    {
                        'source': 'terrain.png',
                        'pack_icon': {
                            'cells': ['ED', 'DA', 'EB', 'FE', '31', 'ED', 'AC', 'BF', 'DA', '96'],
                        }
                    }
                ]
            }
        })
        self.check_fantasitic_pack(pack)

    def check_fantasitic_pack(self, pack):
        with open(os.path.join(self.test_dir, 'unjumbled.zip'), 'w') as strm:
            pack.write_to(strm)
        self.assert_PNGs_match(self.get_data('gingham.png'), pack.get_resource('terrain.png'))
        self.assert_PNGs_match(self.get_data('sign.png'), pack.get_resource('item/sign.png'))
        self.assert_PNGs_match(self.get_data('gingham10.png'), pack.get_resource('pack.png'))
        self.assertEqual('unjumbled', pack.label)
        self.assertEqual('untwisted', pack.desc)

    def test_from_zip_parametized(self):
        mixer = Mixer();
        mixer.add_pack('mary', mixer.get_pack(url_from_file_path(self.zip_path)))
        pack = mixer.make({
            'label': 'unjumbled',
            'desc': 'untwisted',
            'parameters': {
                'packs': [
                    {
                        'name': 'mary',
                        'unjumble': {
                            'terrain.png': {
                                'source_rect': {'width': 256, 'height': 256},
                                'cell_rect': {'width': 16, 'height': 16},
                                'names': ['{0:02X}'.format(x) for x in range(256)],
                            },
                            'item/sign.png': None,
                        },
                    }
                ]
            },
            'mix': {
                'pack': "$mary",
                'files': [
                    '*.png',
                    {
                        'source': 'terrain.png',
                        'pack_icon': {
                            'cells': ['ED', 'DA', 'EB', 'FE', '31', 'ED', 'AC', 'BF', 'DA', '96'],
                        }
                    }
                ]
            }
        })
        self.check_fantasitic_pack(pack)

    def test_relax_when_missing(self):
        mixer = Mixer();
        mixer.add_pack('mary', mixer.get_pack(url_from_file_path(self.zip_path)))
        recipe = {
            'label': 'unjumbled',
            'desc': 'untwisted',
            'parameters': {
                'packs': [
                    {
                        'name': 'mary',
                        'unjumble': {
                            'terrain.png': {
                                'source_rect': {'width': 256, 'height': 256},
                                'cell_rect': {'width': 16, 'height': 16},
                                'names': ['{0:02X}'.format(x) for x in range(256)],
                            },
                            'item/sign.png': None,
                        },
                    }
                ]
            },
            'mix': {
                'pack': "$mary",
                'files': [
                    '*.png',
                    {
                        'source': 'terrain.png',
                        'pack_icon': {
                            'cells': ['ED', 'DA', 'EB', 'FE', '31', 'ED', 'AC', 'BF', 'DA', '96'],
                        }
                    },
                    {
                        'file': 'gui/items.png',
                    }
                ]
            }
        }
        with self.assertRaises(NotInPack):
            pack = mixer.make(recipe)

        recipe['mix']['files'][-1]['if_missing'] = 'relax'
        pack = mixer.make(recipe)
        self.check_fantasitic_pack(pack)
        self.assertTrue('gui/items.png' not in pack.get_resource_names())


class TestAltGuessings(TestCase):
    def test_simple_case(self):
        map = GridMap((0, 0, 32, 32), (16, 16), ['cat', 'dog', 'cat_1', 'dog_1'])
        alts = map.get_alts_list()
        self.assertEqual([('cat', [['cat', 'cat_1']]), ('dog', [['dog', 'dog_1']])], alts)


    def test_shapely_box(self):
        map = GridMap((0, 0, 64, 32), (16, 16), ['cat_top', 'potato', 'cat_top_1', 'grapefruit',
            'cat_side', 'cat_front', 'cat_side_1', 'cat_front_1'])
        alts = map.get_alts_list()
        self.assertEqual([('cat', [['cat_front', 'cat_front_1'], ['cat_side', 'cat_side_1'], ['cat_top', 'cat_top_1']])], alts)


if __name__ == '__main__':
	unittest.main()
