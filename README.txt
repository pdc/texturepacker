Texturepacker
=============

Minecraft Texture-Pack Maker

Purpose
-------

Texturepacker provides program ``maketexture`` for assembling
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
- Distribute (or Setuptools might work)

You should be able to install with the following command::

    $ python setup.py install

You can test it worked by running it on an example recipe::

    $ maketexture -v examples/groovystipple.zip

(These are included in the source distribution but will not be
included in a binary install.)

To run automated tests, you need to install 2 more packages and
then use Nose::

    $ pip install nose mock
    $ nosetests tests

This should print a lot of dots and then report OK at the end.
