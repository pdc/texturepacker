Minecraft Texture Maker
=======================

Purpose
-------

Minecraft Texture Maker provides program ``maketexture`` for assembling
texture packs for Minecraft using recipes written in a simple language
expressed using JSON or as Python dicts, and a library of Python classes
that can be used to do the same thing in your own programs.

Texture packs can be created by combining image files in PNG format, or
images extracted from existing texture packs. This enables you to remix
texture packs to use alternative textures for some elements if the
original artist included them, or even to combine textures from two or
more separate packs. One use for this might be to upgrade a pack
designed for an earlier version of Minecraft to work with newly added
items.

Installation
------------

Requirements:

- Python 2.7
- packages listed in the ``REQUIREMENTS`` file

You should be able to install with the following commands::

    $ pip install -r REQUIREMENTS
    $ python setup.py install

You can test it worked with Nose::

    $ nosetests tests

This should print a lot of dots and then report OK at the end.



