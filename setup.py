# encoding: UTF-8

from distutils.core import setup
setup(
    name='texturepacker',
    version='0.1',
    description='Assemble texture packs for Minecraft',
    long_description="""Provides program 'maketexture' for assembling texture packs for Minecraft
using recipes written in a simple language expressed as JSON or as Python dicts,
and a library of Python classes that can be used to do the same thing in
your own programs.

Texture packs can be created by combining image files in PNG format,
or images extracted from existing texture packs. This enables you to
remix texture packs to use alternative textures for some elements
if the original artist included them, or even to combine textures
from two or more separate packs. One use for this might be to upgrade
a pack designed for an earlier version of Minecraft to work with newly
added items.
""",
    author='Damian Cugley',
    author_email='pdc@alleged.org.uk',
    url = 'http://pdc.github.com/texturepacker/',

    requires=[
        'PIL(>=1.1.7)',
        'PyYAML(>=3.0.9)',
        'httplib2(>=0.6.0)',

        # Used for testing:
        'mock(>=0.7.0b4)',
        'nose(>=1.0.0)',
    ],

    packages=['alleged', 'alleged.minecraft'],
    scripts=['script/maketexture'],
    # The sample images & recipes are not included in a binary distribution.
)