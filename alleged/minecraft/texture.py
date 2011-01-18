#!/usr/bin/env python
# encoding: utf-8
"""
texture.py

Created by Damian Cugley on 2011-01-12.
Copyright (c) 2011 __MyCompanyName__. All rights reserved.
"""

import sys
import os
import unittest
from zipfile import ZipFile, ZIP_DEFLATED
from StringIO import StringIO
from base64 import b64decode

class ResourceBase(object):
    def __init__(self, name):
        self.name = name

    def get_bytes(self):
        raise NotImplemented('get_bytes')


class TextResource(ResourceBase):
    """A document whose content is a literal string."""
    def __init__(self, name, content):
        super(TextResource, self).__init__(name)
        self.content = content

    def get_content(self):
        return self.content

    def get_bytes(self):
        """Get the byte sequence that will go in the ZIP archive"""
        return self.get_content().encode('UTF-8')

class RecipePack(object):
    """Represents a texture pack."""
    def __init__(self, label, desc):
        self.label = label
        self.desc = desc
        self.resources = {}

        self.add_resource(TextResource('pack.txt', u'{label}\n{desc}'.format(label=label, desc=desc)))

    def add_resource(self, resource):
        self.resources[resource.name] = resource

    def get_resource(self, name):
        return self.resources[name]

    def write_to(self, strm):
        with ZipFile(strm, 'w', ZIP_DEFLATED) as zip:
            for name, resource in sorted(self.resources.items()):
                zip.writestr(name, resource.get_bytes())


class SourcePack(object):
    def __init__(self, zip_data):
        self.zip = ZipFile(zip_data)
        self.resources = {}

    def __del__(self):
        self.zip.close()

    def get_resource(self, name):
        res = self.resources.get(name)
        if res:
            return res
        if name.endswith('.txt'):
            text = self.zip.read(name).decode('UTF-8')
            res = TextResource(name, text)
        else:
            res = SourceResource(self, name)
        self.resources[name] = res
        return res

    def get_resource_bytes(self, name):
        return self.zip.read(name)

    @property
    def label(self):
        res = self.get_resource('pack.txt')
        return res.get_content().split('\n', 1)[0]

    @property
    def desc(self):
        res = self.get_resource('pack.txt')
        return res.get_content().split('\n', 1)[1]

class SourceResource(ResourceBase):
    def __init__(self, source, name):
        self.source = source
        self.name = name
        self.bytes = None

    def get_bytes(self):
        if self.bytes is None:
            self.bytes = self.source.get_resource_bytes(self.name)
        return self.bytes

class Mixer(object):
    def __init__(self):
        self.packs = {}

    def add_pack(self, name, pack):
        self.packs[name] = pack

    def make(self, recipe):
        new_pack = RecipePack(recipe['label'], recipe['desc'])
        for ingredient in recipe['mix']:
            pack = self.packs[ingredient['pack']]
            for file_spec in ingredient['files']:
                res_name = file_spec
                res = pack.get_resource(res_name)
                new_pack.add_resource(res)
        return new_pack

###

class TestCase(unittest.TestCase):
    data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'test_data'))

    def get_resource(self, file_name):
        with open(os.path.join(self.data_dir, file_name), 'rb') as strm:
            bytes = strm.read()
        return bytes

    def make_source_pack(self, name, desc, resources_by_file_name):
        strm = StringIO()
        with ZipFile(strm, 'w') as zip:
            for file_name, res_name in resources_by_file_name.items():
                zip.writestr(file_name, self.get_resource(res_name))
            zip.writestr('pack.txt', '{0}\n{1}'.format(name, desc).encode('UTF-8'))
        strm.seek(0)

        # Open it as a SourceTexturePack
        pack = SourcePack(strm)
        return pack

class TextResourceTests(TestCase):
	def setUp(self):
		pass

	def test_pack_txt(self):
	    doc = TextResource('pack.txt', u'Test pack\nBy Fréd the Deäd')
	    self.assertEqual('pack.txt', doc.name)
	    self.assertEqual('Test pack\nBy Fréd the Deäd', doc.get_bytes())
	    # This test relies on the encoding of the source file being UTF-8!!

class SourcePackTests(TestCase):
    def test_sign(self):
        pack = self.make_source_pack('Sign pack', 'Just a test', {'item/sign.png': 'sign.png'})
        self.assertEqual('Sign pack', pack.label)
        self.assertEqual('Just a test', pack.desc)

        # Check there is a SourceResource correspoding to the sign
        res = pack.get_resource('item/sign.png')
        self.assertEqual('item/sign.png', res.name)

        # Check the data returned from the resource maches what went in to the ZIP
        self.assertEqual(self.get_resource('sign.png'), res.get_bytes())

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
        pack_ab = self.make_source_pack('AB', 'Has A and B', {'a.png': 'a.png', 'b.png': 'b.png'})
        pack_c = self.make_source_pack('C', 'Has C', {'c.png': 'c.png'})

        new_pack = RecipePack(u'Composite pack', u'It’s composite')
        new_pack.add_resource(pack_ab.get_resource('a.png'))
        new_pack.add_resource(pack_c.get_resource('c.png'))

        # Now generate the archive and check it contains the expected files.
        strm = StringIO()
        new_pack.write_to(strm)

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            self.assertEqual(self.get_resource('a.png'), zip.read('a.png'))
            self.assertEqual(self.get_resource('c.png'), zip.read('c.png'))
            try:
                zip.read('b.png')
                self.fail('Should not find b.png')
            except KeyError:
                pass

class MixerTests(TestCase):
    def test_b_plus_c(self):
        mixer = Mixer()
        mixer.add_pack('alpha_bravo', self.make_source_pack('AB', 'Has A and B', {'a.png': 'a.png', 'b.png': 'b.png'}))
        mixer.add_pack('charlie', self.make_source_pack('C', 'Has C', {'c.png': 'c.png'}))

        recipe = {
            'label': 'Composite pack',
            'desc': 'A crazy mixed-up pack',
            'mix': [
                {'pack': 'alpha_bravo', 'files': ['b.png']},
                {'pack': 'charlie', 'files': ['c.png']}
            ]
        }
        pack = mixer.make(recipe)

        self.assertEqual('Composite pack', pack.label)
        self.assertEqual('A crazy mixed-up pack', pack.desc)
        self.check_pack(pack, {'b.png': 'b.png', 'c.png': 'c.png'}, ['a.png'])

    def check_pack(self, pack, expected_contents, expected_absent):
        strm = StringIO()
        pack.write_to(strm)

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            for file_name, resource_name in expected_contents.items():
                self.assertEqual(
                        self.get_resource(resource_name),
                        zip.read(file_name),
                        'Expected to contain {0}'.format(file_name))
            for file_name in expected_absent:
                try:
                    zip.read(file_name)
                    self.fail('Should not find {0}'.format(file_name))
                except KeyError:
                    pass


if __name__ == '__main__':
	unittest.main()