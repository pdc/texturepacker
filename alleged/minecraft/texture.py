#!/usr/bin/env python
# encoding: utf-8
"""
texture.py

Created by Damian Cugley on 2011-01-12.
Copyright (c) 2011 __MyCompanyName__. All rights reserved.
"""

import sys
import os
from zipfile import ZipFile, ZIP_DEFLATED
from StringIO import StringIO
from base64 import b64decode
import Image

class ResourceBase(object):
    def __init__(self, name):
        self.name = name

    def get_bytes(self):
        raise NotImplemented('{0}.get_bytes'.format(self.__class__.__name))

    def get_image(self):
        raise NotImplemented('{0}.get_image'.format(self.__class__.__name))


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


class PackBase(object):
    """Base class for a texture pack.

    Supplies two main features: resources (files) and maps
    (which say how textures are arranged within resources)."""
    def __init__(self, atlas):
        self.atlas = atlas

    def get_resource(self, name):
        """Retrieve a resource object.

        Arguments --
            name -- names the resourece

        Names use thenames of file within the archive, such as
        'texture.png' or 'item/sign.png'.

        Returns --
            ResoureBase subclass instance

        """
        raise NotImplemented('{0}.get_resource'.format(self.__class__.__name__))


class RecipePack(PackBase):
    """A texture pack assembled from other resources."""
    def __init__(self, label, desc):
        super(RecipePack, self).__init__(Atlas())
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


class SourcePack(PackBase):
    """A texture pack that gets resources from a ZIP file."""
    def __init__(self, zip_data, atlas):
        super(SourcePack, self).__init__(atlas)
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
        self.image = None

    def get_bytes(self):
        if self.bytes is None:
            self.bytes = self.source.get_resource_bytes(self.name)
        return self.bytes

    def get_image(self):
        if self.image is None:
            strm = StringIO(self.get_bytes())
            self.image = Image.open(strm)
        return self.image

class Map(object):
        pass

class NotInMap(Exception):
    def __init__(self, name):
        super(NotInMap, self).__init__('{0!r} not found in map'.format(name))

class GridMap(Map):
    def __init__(self, source_box, cell_box, names):
        """Create a grid map with this size and names.

        Arguments --
            source_box -- pair (WIDTH, HEIGHT)
                or tuple (LEFT, TOP, RIGHT, BOTTOM) -- size of the overall image
            cell_box -- pair (WIDTH, HEIGHT) -- size of cells within the image
                The image width should be a multiple of the cell width
                and similarly for the heights.
            names --
                List of names, in order left to right, top to bottom.
        """
        self.cell_wd, self.cell_ht = cell_box
        if len(source_box) == 2:
            self.im_left = self.im_top = 0
            im_wd, im_ht = source_box
        else:
            self.im_left, self.im_top, right, bottom = source_box
            im_wd = right - self.im_left
            im_ht = bottom - self.im_top
        self.nx, self.ny = im_wd // self.cell_wd, im_ht // self.cell_ht

        self.names = names

    def get_box(self, name):
        try:
            i = self.names.index(name)
        except ValueError:
            raise NotInMap(name)
        u, v = i % self.nx, i // self.nx
        return (self.im_left + self.cell_wd * u, self.im_top + self.cell_ht * v,
            self.im_left + self.cell_wd * (u + 1), self.im_top + self.cell_ht * (v + 1))

class CompositeMap(Map):
    """A map that combines several other maps.

    Each submap is searched in turn for the desired item.
    """
    def __init__(self, maps):
        self.maps = list(maps)

    def get_box(self, name):
        for m in self.maps:
            try:
                return m.get_box(name)
            except NotInMap:
                pass
        raise NotInMap(name)

    @property
    def names(self):
        names = []
        for m in self.maps:
            names.extend(list(m.names))
        return names


class NotInAtlas(Exception):
    def __init__(self, spec):
        super(NotInAtlas, self).__init__('{0!r}: not in atlas'.format(spec))

class Atlas(object):
    """Creates and stores maps.

    Maps can be retrieved by name, or you can just supply a spec
    that defines the map inline, as it were.
    """

    __slots__ = ['maps']
    def __init__(self, maps={}):
        self.maps = dict(maps)

    def add_map(self, name, map):
        self.maps[name] = map

    def get_map(self, spec):
        if isinstance(spec, basestring):
            try:
                return self.maps[spec]
            except KeyError:
                raise NotInAtlas(spec)
        if hasattr(spec, 'items'):
            cell_box = pil_box(**spec['cell_rect'])
            source_box = pil_box(**spec['source_rect'])
            names = spec['names']
            if cell_box[0:2] != (0, 0):
                raise ValueError('{0!r}: cell_box must have (left, top) == (0, 0)'.format(cell_box))
            cell_box = cell_box[2:]
            return GridMap(source_box, cell_box, names)
        # It had better be a list of maps if we get this far.
        return CompositeMap(self.get_map(x) for x in spec)


def pil_box(left=None, top=None, right=None, bottom=None, x=None, y=None, width=None, height=None):
    """Return a bounding box of form (LEFT, TOP, RIGHT, BOTTOM) used by PIL.

    You can supply a subset of the parameters, but hte usual ones
    will be

        x, y, width, height -- coordinates of top-left corner and size of box
        left, top, right, bottom -- coordinates of top-left and bottom-right corners

    Coordinates are assumed to come between pixels (that is, the
    top left corner pixel has bbox (0, 0, 1, 1), and the bottom-right
    pixel of a 16x16 image is at (15, 15, 16, 16))

    If x, y, left, and right are omitted, then the top left corner is at (0, 0)
    """
    left = left or x or 0
    top = top or y or 0
    right = right if right is not None else left + (width or 0)
    bottom = bottom if bottom is not None else top + (height or 0)
    return left, top, right, bottom


class CompositeResource(ResourceBase):
    def __init__(self, name, base_res, base_map):
        super(CompositeResource, self).__init__(name)
        self.res = base_res
        self.map = base_map
        self.replacements = []
        self.image = None

    def replace(self, res, map, cells):
        self.replacements.append((res, map, cells))
        self.im = None
        self.bytes = None

    def _calc(self):
        im = self.res.get_image().copy()
        for src_res, src_map, cells in self.replacements:
            for dst_name, src_name in cells.iteritems():
                dst_box = self.map.get_box(dst_name)
                src_box = src_map.get_box(src_name)
                src_im = src_res.get_image().crop(src_box)
                im.paste(src_im, dst_box)
        self.image = im

    def get_bytes(self):
        if self.bytes is None:
            if self.image is None:
                self._calc()
            strm = StringIO()
            self.image.save(strm, 'PNG', optimize=True)
            self.bytes = strm.getvalue()
        return self.bytes


class Mixer(object):
    """Create texture packs by mixing together existing ones.

    As well as interpreting the recipes, the mixer keeps
    track of the packs and loads them as needed.
    """
    def __init__(self):
        self.packs = {}
        self.atlas = Atlas()

    def add_pack(self, name, pack):
        self.packs[name] = pack

    def make(self, recipe):
        new_pack = RecipePack(recipe['label'], recipe['desc'])
        for ingredient in recipe['mix']:
            src_pack = self.packs[ingredient['pack']]
            for file_spec in ingredient['files']:
                if isinstance(file_spec, basestring):
                    res = src_pack.get_resource(file_spec)
                else:
                    src_res = src_pack.get_resource(file_spec['source'])
                    src_map = self.get_pack_map(src_pack, file_spec.get('map', src_res.name))
                    res = CompositeResource(file_spec['file'], src_res, src_map)
                    specs = file_spec['replace']
                    if hasattr(specs, 'items'):
                        specs = [specs]
                    for spec in specs:
                        src_res = src_pack.get_resource(spec['source'])
                        src_map = self.get_pack_map(src_pack, spec.get('map', src_res.name))
                        cells = spec['cells']
                        res.replace(src_res, src_map, cells)
                new_pack.add_resource(res)
        return new_pack

    def get_pack_map(self, pack, spec):
        """Get a map from the pack if possible, otherwise try the global atlas."""
        try:
            return pack.atlas.get_map(spec)
        except NotInAtlas:
            pass
        return self.atlas.get_map(spec)
