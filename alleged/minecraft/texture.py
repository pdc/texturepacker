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

class DocBase(object):
    def __init__(self, name):
        self.name = name

    def get_content(self):
        """Get the text for the resource (as a Unicode string)"""
        raise NotImplemented('get_content')

    def get_bytes(self):
        """Get the byte sequence that will go in the ZIP archive"""
        return self.get_content().encode('UTF-8')

class TextResource(DocBase):
    """A document whose content is a literal string."""
    def __init__(self, name, content):
        super(TextResource, self).__init__(name)
        self.content = content

    def get_content(self):
        return self.content

class RecipeTexturePack(object):
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

###

class TextResourceTests(unittest.TestCase):
	def setUp(self):
		pass

	def test_pack_txt(self):
	    doc = TextResource('pack.txt', u'Test pack\nBy Fréd the Deäd')
	    self.assertEqual('pack.txt', doc.name)
	    self.assertEqual('Test pack\nBy Fréd the Deäd', doc.get_bytes())
	    # This test relies on the encoding of the source file being UTF-8!!

class RecipeTexturePackTests(unittest.TestCase):
    def test_pack_txt_from_init(self):
        pack = RecipeTexturePack(u'Test pack', u'It’s testy')
        self.assertEqual(u'Test pack\nIt’s testy', pack.get_resource('pack.txt').get_content())

    def test_zip_1(self):
        pack = RecipeTexturePack(u'Yummy pack', u'It’s tasty')
        pack.add_resource(TextResource('doc/news.txt', 'This is a news file.'))

        # Now generate the archive and check it contains the expected files.
        strm = StringIO()
        pack.write_to(strm)

        strm.seek(0)
        with ZipFile(strm, 'r') as zip:
            self.assertEqual(u'Yummy pack\nIt’s tasty', zip.read('pack.txt').decode('UTF-8'))
            self.assertEqual(u'This is a news file.', zip.read('doc/news.txt').decode('UTF-8'))

class SourceTexturePack(unittest.TestCase):
    def test_sign(self):
        sign_data = b64decode('iVBORw0KGgoAAAANSUhEUgAAAIAAAABACAYAAADS1n9/AAABoElEQVR42u3bvUoDQRiF4eT2JBAEa0EwIGgRELTTgAG11cJqOzu1FERFtLCJSgpBcjfjLhidXRAJ5Mdhn8ALIU1mdt8cvsNmGiGERkzW74SUOdleTprq/Zg1DQL8Hw67BJAABJAAcxXgrL8WYrLEOemtlqjuLzVmL8DuSojJct6fr8Po5S4pijUXa6/+qqr7S43ZC9Dr/Hxh/j7LKS7o8PEyOb4TYCzAOAFSFWBRCZCsABJAAkiACQXob7ZDzHHOx+A2vD1cJMdRtx32tlolDrrl/aVG/mpGzKcFjF7vw/DpKjm0ADOAGcAMYAaQABJAAkiAGraAYu37G60SKTeArxYwh2cBkXFagBZgBjADmAG0AAlQowSIkABagBZQuxbgWYAWYAbQAswAWoAEkAA5xR8sU7v5g5tzCTCtFlCws76UFON1awFTPhiy6JMrIMCkNH/BDZcAIAD+roExVQFO889iXEQCuJAEAAFAABAABAABQAAQAAQAAUAAEAAEAAFAABAABAABQAAQAAQAAUAAEAAEAAGw2MOhIAAIAAKgFnwCP18LA1iM8R4AAAAASUVORK5CYII=')

        # Create a ZIP file containing the sign.

        # Open it as a SourceTexturePack

        # Check there is a SourceResource correspoding to the sign

        # Check the data returned from the resource maches what went in to the ZIP
if __name__ == '__main__':
	unittest.main()