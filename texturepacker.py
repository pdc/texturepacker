# -*-coding: UTF-8-*-
"""
texture.py

Created by Damian Cugley on 2011-01-12.
Copyright (c) 2011 Damian Cugley. All rights reserved.
"""

import sys
import os
import weakref
import re
from zipfile import ZipFile, ZIP_DEFLATED
from StringIO import StringIO
from base64 import b64decode
from datetime import datetime
import Image
import httplib2
import fnmatch
import json
import yaml
from urlparse import urljoin

_http = None
_cache = None
def set_http_cache(cache):
    """Future HTTP requests will use this cache.

    Arguments --
        cache -- either the name of a directory to store files
            in, or an httplib2 cache object
    """
    global _cache
    if _cache != cache:
        _cache = cache
        _http = None

def _get_http():
    """Helper function to get the HTTP object."""
    global _http
    if _http is None:
        _http = httplib2.Http(_cache)
    return _http


MINECRAFT_DIR_PATH_FUNCS = {
    'windows': lambda: os.path.expandvars('%appdata%\\.minecraft'),
    'darwin': lambda: os.path.expanduser('~/Library/Application Support/minecraft'),
    'default': lambda: os.path.expanduser('~/.minecraft'),
}

def minecraft_dir_path():
    """Return the path to the directory containing directories for Minecraft customization."""
    func = (MINECRAFT_DIR_PATH_FUNCS.get(sys.platform)
        or MINECRAFT_DIR_PATH_FUNCS['default'])
    return func()

def minecraft_texture_pack_dir_path():
    """Return the path to the directory for installing texture packs."""
    return os.path.join(minecraft_dir_path(), 'texturepacks')

def resolve_file_path(file_path, base):
    """Given a file path and a base URL, return a file path."""
    if base and hasattr(base, 'items'):
        if 'file' in base:
            base = 'file:///' + base['file']
    if base and base.startswith('file://'):
        base_path = base[7:]
        if not os.path.exists(base_path) or not os.path.isdir(base_path):
            base_path = os.path.dirname(base_path)
        file_path = os.path.join(base_path, file_path)
    return file_path

def url_from_file_path(file_path):
    """Given a file path, return a file URL."""
    url = 'file:///' + os.path.abspath(file_path).lstrip('/\\')
    if os.path.isdir(file_path):
        url += '/'
    return url


GENERIC_RE = re.compile(r"""
    ^
    (?P<scheme> [\w.+-]+ ) :
    //
    (?P<authority>
        [\w@:.+-]*
    )
    (?:
        /
        (?P<path> [^?#]* / )?
        (?P<final> [^/?#]* )
    )?
    $
""", re.VERBOSE + re.IGNORECASE)


def resolve_generic_url(base_url, url_ref):
    """Resolve a relative reference per RFC 3986

    Used for the custom URI schemes supplied by
    clients of the Mixer: HTTP URIs are processed
    using the Python library’s urlparse module.

    Arguments --
        base_url -- absolute URL that is used
            to interpret url_ref
        url_ref -- may be an absolute URL
            (which will be returned unchanged)
            or a relative reference to be
            resolved relative to base_url.

    <http://tools.ietf.org/html/rfc3986>
    """
    if not url_ref:
        return base_url

    if GENERIC_RE.match(url_ref):
        return url_ref
    m = GENERIC_RE.match(base_url)
    if url_ref.startswith('/'):
        return m.group('scheme') + '://' + m.group('authority') + url_ref

    scheme, authority, path = m.group('scheme'), m.group('authority'), (m.group('path') or '')

    # Split reference up at slashes and strip out irrelevant .. and .:
    elts = []
    for elt in url_ref.split('/'):
        if elt == '..' and elts and elts[-1] != '..':
            elts.pop(-1)
        else:
            elts.append(elt)

    # Now adjust path from base URL according to
    # .. and . at the join.
    while elts:
        if elts[0] == '..':
            if path:
                path = path[:-1]
                q = path.rfind('/')
                if q >= 0:
                    path = path[:q + 1]
                else:
                    path = ''
            elts.pop(0)
        elif elts[0] == '.':
            elts.pop(0)
        else:
            break

    return scheme + '://' + authority + '/' + path + '/'.join(elts)

class CouldNotLoad(Exception): pass

class DudeItsADirectory(Exception):
    def __init__(self, path):
        self.path = path
        super(DudeItsADirectory, self).__init__('{0!r}: is a directory'.format(path))

class Loader(object):
    def __init__(self):
        self._specs = {}
        self._things = {}
        self._schemes = {}

    def add_scheme(self, prefix, func):
        self._schemes[prefix] = func

    def get_url(self, spec, base=None):
        """Given a spec, return URL for the resource it specifes.

        The spec can have a 'file' member specifying a file path.
        """
        if isinstance(spec, basestring):
            spec = {'href': spec}
        if 'file' in spec:
            file_path = resolve_file_path(spec['file'], base)
            return url_from_file_path(file_path)
        if 'href' in spec:
            url = spec['href']
            if url.startswith('minecraft:'):
                file_path = url[10:].lstrip('/\\')
                file_path = os.path.join(minecraft_dir_path(), file_path)
                return url_from_file_path(file_path)
            if base:
                if hasattr(base, 'items'):
                    base_url = self.get_url(base)
                else:
                    base_url = base

                url0 = url
                p = base_url.find(':')
                if p > 1 and base_url[:p].lower() in self._schemes:
                    url = resolve_generic_url(base_url, url)
                else:
                    url = urljoin(base_url, url)
            if url.startswith('file://'):
                url = url_from_file_path(url[7:])
            return url
        # If we get this far we have failed to resolve the URL
        return None

    def get_stream(self, spec, base=None):
        """Given a spec, return input stream it specifies.

        The spec can have a 'file' member specifying a file path,
        an 'href' member specifying a URL, 'data' or 'base64'
        member specifyting immediate data, or be a string,
        which is treated as a URL.
        """
        if isinstance(spec, basestring):
            spec = {'href': spec}

        # Inline data.
        if 'data' in spec:
            return StringIO(spec['data'])
        if 'base64' in spec:
            return StringIO(b64decode(spec['base64']))

        # Simply a file.
        if 'file' in spec:
            file_path = resolve_file_path(spec['file'], base)
            if os.path.isdir(file_path):
                raise DudeItsADirectory(file_path)
            return open(file_path, 'rb')

        # Various external sources decribed using a URL.
        url = self.get_url(spec, base)
        if url:
            meta, strm = self.get_url_stream(url)
            return strm

        # If we get this far, we can’t work out a way to get a stream.
        return None

    def get_url_stream(self, url, ext='tpmaps'):
        """Given a URL, return input stream it specifies.

        Returns --
            meta, strm
            where --
                meta is a dict containing 'content-type'
                strm is a file-like object
        """
        if url.startswith('file://'):
            file_path = url[7:]

            if not os.path.exists(file_path) and os.path.exists(file_path + '.' + ext):
                file_path += '.' + ext

            if os.path.isdir(file_path):
                raise DudeItsADirectory(file_path)

            meta = {'content-type': 'application/json' if url.endswith('.json') else 'application/yaml'}
            # XXX allow for more contenbt-types than this!

            return meta, open(file_path, 'rb')

        if url.startswith('data:application/zip;base64,'):
            return {'content-type': 'application/zip'}, StringIO(b64decode(url[28:]))
            # XXX Allow for more content-types

        if url.startswith('http'):
            response, body = _get_http().request(url)
            if response['status'] in ['200', '304']:
                return response, StringIO(body)
            raise CouldNotLoad('{0!r}: could not load: status={1}'.format(url, response['status']))

        p = url.find(':')
        if p > 0:
            prefix, path = url[:p], url[p + 1:]
            func = self._schemes.get(prefix.lower())
            if func:
                return func(path)

        raise CouldNotLoad('{0!r}: unknown URL scheme'.format(url))

    def get_bytes(self, spec, base=None):
        """Given a spec, return the data at the location specified.

        The spec can have a 'file' member specifying a file path.
        """
        strm = self.get_stream(spec, base)
        try:
            return strm.read()
        finally:
            strm.close()

    def maybe_get_spec(self, spec, base=None, ext='tprx'):
        """Given a spec, return spec it refers to or the spec.

        The spec can have a 'file' member specifying a file path.

        If there is no reference to external spec, then
        return this spec.
        """
        url = self.get_url(spec, base)
        if not url:
            return spec
        spec = self._specs.get(url)
        if spec:
            return spec
        meta, strm = self.get_url_stream(url, ext=ext)
        if meta['content-type'] == 'application/json':
            spec = json.load(strm)
        else:
            spec = yaml.load(strm)
        self._specs[url] = spec
        return spec


class ResourceBase(object):
    def __init__(self, name):
        self.name = name

    def get_bytes(self):
        raise NotImplementedError('{0}.get_bytes'.format(self.__class__.__name__))

    def get_image(self):
        raise NotImplementedError('{0}.get_image'.format(self.__class__.__name__))

    def get_last_modified(self):
        """When was the laast time this resource was changed?"""
        raise NotImplementedError('{0}.get_last_modified'.format(self.__class__.__name__))

    def is_modified_since(self, then):
        """Has this resource been modified since this date?"""
        return self.get_last_modified() > then


class TextResource(ResourceBase):
    """A document whose content is a literal string."""
    def __init__(self, name, content, last_modified=None):
        super(TextResource, self).__init__(name)
        self.content = content
        self.last_modified = last_modified or datetime.now()

    def get_content(self):
        return self.content

    def get_bytes(self):
        """Get the byte sequence that will go in the ZIP archive"""
        return self.get_content().encode('UTF-8')

    def get_last_modified(self):
        return self.last_modified


class NotInPack(Exception):
    def __init__(self, name, pack):
        self.name = name
        self.pack = pack
        super(NotInPack, self).__init__('{name}: not in pack {pack}'.format(name=name, pack=pack))

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
        raise NotImplementedError('{0}.get_resource'.format(self.__class__.__name__))

    def get_resource_names(self):
        """A list of all resources in the pack."""
        raise NotImplementedError('{0}.get_resource_names'.format(self.__class__.__name__))

    def write_to(self, strm):
        with ZipFile(strm, 'w', ZIP_DEFLATED) as zip:
            for name in sorted(self.get_resource_names()):
                zip.writestr(name, self.get_resource(name).get_bytes())

    def get_last_modified(self):
        """Return a datetime object giving the last time a resource was modified.

        Note that what matters is the modification times of
        the resources in the pack. For example, two zips
        created at different times but with the same timestamps
        recorded for their contents will have the same last-modified time.

        This is returned as an instance of datetime.
        The precision will depend on the type of pack; for fiels
        stored in a ZIP this is only to the nearest 2 seconds
        (because of limitations in the ZIP format).
        """
        return max(self.get_resource(n).get_last_modified()
                for n in self.get_resource_names())

    def is_modified_since(self, then):
        """Return true iff this pack has had a respource changed since the given date.

        Because the precision of timestamps varies according
        to the format the pack is stored in, near misses
        will be unreliable except when the given date
        is the same as the result of an earlier call to get_last_modified.
        """
        return any(self.get_resource(n).is_modified_since(then)
                for n in self.get_resource_names())

    def __str__(self):
        return self.__unicode__().encode('UTF-8')


class RecipePack(PackBase):
    """A texture pack assembled from other resources."""

    def __init__(self, label, desc, atlas=None):
        super(RecipePack, self).__init__(atlas or Atlas())
        self.label = label
        self.desc = desc

        self.resources = {}
        self.add_resource(TextResource('pack.txt', u'{label}\n{desc}'.format(label=label, desc=desc)))

    def add_resource(self, resource):
        self.resources[resource.name] = resource

    def get_resource(self, name):
        try:
            return self.resources[name]
        except KeyError:
            raise NotInPack(name, self)

    def get_resource_names(self):
        return self.resources.keys()

    def is_modified_since(self, then):
        for n in self.get_resource_names():
            if n != 'pack.txt' and self.get_resource(n).is_modified_since(then):
                return True
        return False

    def __unicode__(self):
        return '<RecipePack {0!r}>'.format(self.label)


class SourcePack(PackBase):
    """A texture pack that gets resources from a ZIP file or directory."""
    def __init__(self, zip_data, atlas):
        super(SourcePack, self).__init__(atlas)
        if (isinstance(zip_data, basestring)
                and os.path.isdir(zip_data)):
            self.dir_path = zip_data.rstrip('\\/')
        else:
            self.zip = ZipFile(zip_data)
        self.loaded_resources = weakref.WeakValueDictionary()

    def __del__(self):
        if hasattr(self, 'zip'):
            self.zip.close()
            del self.zip

    def get_resource(self, name):
        """Get the named resource

        Arguments --
            name -- specifies the resource to return

        Returns --
            A resource (subclass of ResourceBase)

        """
        res = self.loaded_resources.get(name)
        if res:
            return res
        if name.endswith('.txt'):
            text = self.get_resource_bytes(name).decode('UTF-8')
            last_modified = self.get_resource_last_modified(name)
            res = TextResource(name, text, last_modified)
        else:
            res = SourceResource(self, name)
        self.loaded_resources[name] = res
        return res

    def get_resource_bytes(self, name):
        if hasattr(self, 'dir_path'):
            with open(os.path.join(self.dir_path, name), 'rb') as strm:
                return strm.read()
        return self.zip.read(name)

    def get_resource_last_modified(self, name):
        """Helper function to get last-modified of a resource.

        Used by the resource’s get_last_modified method."""
        if hasattr(self, 'dir_path'):
            file_path = os.path.join(self.dir_path, name)
            t = os.stat(file_path).st_mtime
            return datetime.fromtimestamp(t)
        inf = self.zip.getinfo(name)
        return datetime(*inf.date_time)

    def get_resource_names(self):
        # We want all resources, not just recently mentioned ones.
        if hasattr(self, 'dir_path'):
            for subdir, subdirs, file_names in os.walk(self.dir_path):
                if subdir.startswith(self.dir_path):
                    subdir = subdir[len(self.dir_path) + 1:]
                for file_name in file_names:
                    if file_name.endswith('.png') or file_name.endswith('.txt'):
                        yield subdir + '/' + file_name if subdir else file_name
        else:
            for name in self.zip.namelist():
                yield name

    @property
    def label(self):
        res = self.get_resource('pack.txt')
        return res.get_content().split('\n', 1)[0]

    @property
    def desc(self):
        res = self.get_resource('pack.txt')
        return res.get_content().split('\n', 1)[1].rstrip()

    def get_last_modified(self):
        """Get a timestamp for the last time the content of the pack was changed.

        Note that the contents timestamps are what matter;
        the same files archived twice will have the same
        last-modified time.
        """
        if hasattr(self, 'dir_path'):
            t = None
            for subdir, subdirs, files in os.walk(self.dir_path):
                for file_name in files:
                    s = os.stat(os.path.join(subdir, file_name))
                    if not t or s.st_mtime > t:
                        t = s.st_mtime
            return datetime.fromtimestamp(t)
        # Is a Zip
        ymdhms = max(inf.date_time for inf in self.zip.infolist())
        return datetime(*ymdhms)


class LazyPack(PackBase):
    """A pack specified by a URL that will be loaded when required.

    Actually performing the network operation will be deferred
    until it can no longer be avoided."""
    def __init__(self, loader, url, atlas):
        super(LazyPack, self).__init__(atlas)
        self.loader = loader
        self.url = url
        self.pack = None

    def get_pack(self):
        """If we have not done so already, download the pack."""
        if not self.pack:
            meta, strm = self.loader.get_url_stream(self.url, 'zip')
            # XXX exception if wrong type of data?
            self.pack = SourcePack(strm, self.atlas)
        return self.pack

    def get_resource(self, name):
        """Get the named resource

        Arguments --
            name -- specifies the resource to return

        Returns --
            A resource (subclass of ResourceBase)
        """
        return self.get_pack().get_resource(name)

    def get_resource_names(self):
        return self.get_pack().get_resource_names()

    @property
    def label(self):
        return self.get_pack().label

    @property
    def desc(self):
        return self.get_pack().desc

    def get_last_modified(self):
        """Get a timestamp for the last time the content of the pack was changed.

        Note that the contents timestamps are what matter;
        the same files archived twice will have the same
        last-modified time.
        """
        return self.get_pack().get_last_modified()


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

    def get_last_modified(self):
        return self.source.get_resource_last_modified(self.name)

    def get_image(self):
        if self.image is None:
            strm = StringIO(self.get_bytes())
            self.image = Image.open(strm)
        return self.image


class RenamedResource(ResourceBase):
    def __init__(self, name, res):
        self.name = name
        self.res = res

    def get_bytes(self):
        return self.res.get_bytes()

    def get_image(self):
        return self.res.get_image()

    def get_last_modified(self):
        return self.res.get_last_modified()


class MapBase(object):
    def get_alts_list(self):
        alt_re = re.compile('_[0-9]$')
        side_re = re.compile('_(front|back|side|left|right|top|bottom|head|foot)$')

        groups = {}
        # First pass: Find alt versions of cells.
        for name in self.names:
            m = alt_re.search(name)
            if m:
                cell_name = name[:m.start(0)]
                m = side_re.search(cell_name)
                group_name = cell_name[:m.start(0)] if m else cell_name
                groups.setdefault(group_name, {}).setdefault(cell_name, []).append(name)

        # Second pass: Add cells for which alt versions exist.
        for cell_name in self.names:
            m = side_re.search(cell_name)
            group_name = cell_name[:m.start(0)] if m else cell_name
            names = groups.get(group_name, {}).get(cell_name)
            if names:
                names.insert(0, cell_name)
        return sorted((cn, sorted(ns.values())) for (cn, ns) in groups.items())


class NotInMap(Exception):
    def __init__(self, name, map):
        super(NotInMap, self).__init__('{0!r} not found in map (must be one of {1})'.format(
            name, ', '.join(map.names)))
        self.name = name
        self.maop = map

class GridMap(MapBase):
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
            raise NotInMap(name, self)
        u, v = i % self.nx, i // self.nx
        result = (self.im_left + self.cell_wd * u, self.im_top + self.cell_ht * v,
            self.im_left + self.cell_wd * (u + 1), self.im_top + self.cell_ht * (v + 1))
        return result

class CompositeMap(MapBase):
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
        raise NotInMap(name, self)

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

    #__slots__ = ['maps']
    def __init__(self, maps={}):
        self.maps = dict(maps)

    def add_map(self, name, map):
        """Add a map to the collection

        Arguments --
            name -- will be used to retrieve this map with get_map
            map -- the map, a subclass of MapBase"""
        self.maps[name] = map

    def get_map(self, spec, base):
        """Get the specified map.

        Arguments --
            spec (string, list, or dict) -- specifies a map
            base -- how to interpret file names

        Returns --
            a map

        Raises --
            NotInAtlas the named map canot be found

        If spec is a string, it names a map added with add_map.

        If it is a dictionary it specifies a new map.
        At present this is alwaus a GridMap. It must define
        cell_rect, source_rect, and names (a list).

        If it is a lisst, its elements must recursively
        be map specs and the result is the composition of all the maps.
        (Order is important if more than one map defines the same
        name: the earliest-listed map will be used.)
        """
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
        return CompositeMap(self.get_map(x, base) for x in spec)

    def get_map_names(self):
        return self.maps.keys()

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


class ImagingResourceBase(ResourceBase):
    """Base class for images that are lazily constructed using the Imaging library."""
    def __init__(self, name):
        super(ImagingResourceBase, self).__init__(name)
        self._image = None
        self._bytes = None

    def _calc(self):
        """Generate the image resource and return the image"""
        raise NotImplementedError('{n}._calc'.format(n=self.__class__.__name__))

    def _invalidate(self):
        """Call this if the recipe changes, so cached images should be discarded."""
        self._image = None
        self._bytes = None

    def get_image(self):
        """Get the composite image."""
        if self._image is None:
            self._image = self._calc()
        return self._image

    def get_bytes(self):
        """Get the bytes representing the composite image in PNG format."""
        if self._bytes is None:
            strm = StringIO()
            self.get_image().save(strm, 'PNG', optimize=True)
            self._bytes = strm.getvalue()
        return self._bytes


class CompositeResource(ImagingResourceBase):
    """An image made by replacing some cells in an image with parts of another"""
    def __init__(self, name, base_res, base_map):
        """Create a composite resouce (with no substitutions)

        Arguments --
            name -- what this resource will be named
                (usually a file name like terrain.png)
            base_res -- a resource to copy as the basis of the new one
            base_map -- the map describing cells in the new resource
                (this may include cells not in the base resource
                assuming these cells will be filled in later)"""
        super(CompositeResource, self).__init__(name)
        self.res = base_res
        self.map = base_map
        self.replacements = []

    def replace(self, source_res, source_map, cells):
        """Replacing cell(s) in the image with cells from another

        Arguments --
            res (image resource) -- copy image data out of this
            map -- gives names to cells within res
            cells (dict or list)-- specifies cells to modify

        If cells is a dict, keys are cell names within this resouce,
        and values are the cell to get image data from in res.
        If cells is a list, the named cells are replaced with
        the same-named cells in the source.
        """
        if not hasattr(cells, 'items'):
            cells = dict((x, x) for x in cells)
        self.replacements.append((source_res, source_map, cells))

        # This invalidates any cached image.
        self._invalidate()

    def _calc(self):
        """Called when the image data is required.

        We defer generating the image until it is required.
        """
        im = self.res.get_image().copy()
        for src_res, src_map, cells in self.replacements:
            for dst_name, src_name in cells.iteritems():
                dst_box = self.map.get_box(dst_name)
                src_box = src_map.get_box(src_name)
                src_im = src_res.get_image().crop(src_box)
                im.paste(src_im, dst_box)
        return im

    def get_last_modified(self):
        return max([self.res.get_last_modified()]
            + [x.get_last_modified() for x, _, _ in self.replacements])


class PackIconResource(ImagingResourceBase):
    def __init__(self, res, map, names):
        super(PackIconResource, self).__init__('pack.png')
        self.res = res
        self.map = map
        self.names = names

    def _calc(self):
        src_im = self.res.get_image()
        im = Image.new('RGBA', (128, 128), (255, 255, 255))
        seq = [(0, 0, 64), (64, 0, 64), (64, 64, 64),
            (32, 96, 32), (0, 96, 32), (0, 64, 32),
            (32, 64, 16), (48, 64, 16), (48, 80, 16),
            (32, 80, 16)]
        for (x, y, wh), name in zip(seq, self.names):
            dst_box = x, y, x + wh, y + wh
            src_box = self.map.get_box(name)
            cell_im = src_im.crop(src_box).resize((wh, wh))
            im.paste(cell_im, dst_box)
        return im

    def get_last_modified(self):
        return self.res.get_last_modified()


class UnknownPack(Exception):
    """Raised if you ask a mixer to use a pack it does not know about."""
    def __init__(self, pack_spec, exc=None):
        extra = ': ' + unicode(exc) if exc else ''
        super(UnknownPack, self).__init__(
            '{0!r}: specified pack is not in mixer{1}'.format(pack_spec, extra))
        self.inner_exception = exc

class MissingParameter(Exception):
    """Raised if you ask a mixer to make a recipe without supplying the needed parameters."""
    def __init__(self, param_spec, exc=None):
        extra = ': ' + unicode(exc) if exc else ''
        super(MissingParameter, self).__init__(
            '{0!r}: required parameter is not in mixer{1}'.format(param_spec, extra))
        self.inner_exception = exc
        self.param = param_spec


TEMPLATE_RE = re.compile(u'\{\{([^{}]+)\}\}')

class Mixer(object):
    """Create texture packs by mixing together existing ones.

    As well as interpreting the recipes, the mixer keeps
    track of the packs and loads them as needed.
    """
    def __init__(self):
        self.packs = {}
        self.atlas = Atlas()
        self._atlas_cache = weakref.WeakValueDictionary()
        self.loader = Loader()

    def add_pack(self, name, pack):
        """Add this pack to the repertoire of this mixer.

        Arguments --
            name -- the name for the pack
            pack -- a texture pack object

        Afterwards this pack can be referred to in recipes using this name.
        """
        self.packs[name] = pack

    def make(self, recipe, base=None):
        """Create a new pack by following this this recipe.

        Arguments --
            recipe -- a dictionary with specific contents
                that describes how to assemble the new pack
                using other packs.

        Returns --
            A new pack object (subclass of PackBase).
        """

        # Check we have been supplied with the parameters we have declared.
        # Also unjumble any parameters marked for this odd treatment.
        # XXX this will affect uses of the same param in later calls. Bad?
        param_specss = recipe.get('parameters')
        if param_specss:
            pack_specs = param_specss.get('packs')
            if pack_specs:
                for param_spec in pack_specs:
                    if isinstance(param_spec, basestring):
                        if param_spec not in self.packs:
                            raise MissingParameter(param_spec)
                        continue
                    param_name = param_spec['name']
                    if param_name not in self.packs:
                        raise MissingParameter(param_spec)
                    if 'unjumble' in param_spec:
                        unjumbled_atlas = self.get_atlas(param_spec['unjumble'], base=base)
                        unjumbled_pack = self.make_unjumbled_pack(self.packs[param_name], unjumbled_atlas)
                        self.packs[param_name] = unjumbled_pack

        if 'maps' in recipe:
            self.get_atlas(recipe['maps'], base, self.atlas)

        if 'packs' in recipe:
            for name, pack_spec in recipe['packs'].items():
                self.add_pack(name, self.get_pack(pack_spec, base=base))

        label = self.expand_template(recipe['label'])
        desc = self.expand_template(recipe['desc'])
        new_pack = RecipePack(label, desc)

        mix = recipe['mix']
        if hasattr(mix, 'items'):
            # Allow a single ingredient to stand in for a singleton list.
            mix = [mix]
        for ingredient in mix:
            src_pack = self.get_pack(ingredient['pack'], base=base)
            for res in self.iter_resources(src_pack, ingredient['files'], base=base):
                new_pack.add_resource(res)
        return new_pack

    def expand_template(self, tpl):
        return TEMPLATE_RE.sub(self.expand_template_sub, tpl)

    def expand_template_sub(self, m):
        parts = m.group(1).strip().split('.')
        x = self.get_pack('$' + parts.pop(0))
        for part in parts:
            x = getattr(x, part)
            if callable(x):
                x = x()
        return x

    def iter_resources(self, src_pack, resources_spec, base):
        """Given a files spec, yield a sequence of resources.

        """
        for file_spec in resources_spec:
            if isinstance(file_spec, basestring):
                if '*' in file_spec:
                    # Its a wildcard: straight copy of all matching extant resources.
                    res_names = src_pack.get_resource_names()
                    res_names = fnmatch.filter(res_names, file_spec)
                    for res_name in res_names:
                        yield src_pack.get_resource(res_name)
                else:
                    # The simplest case: a single named resource.
                    res = src_pack.get_resource(file_spec)
                    yield res
            else:
                # A recipe for creating a new resource from one or more sources.
                if 'pack_icon' in file_spec:
                    res_name = file_spec.get('file', 'pack.png')
                else:
                    res_name = file_spec['file']
                try:
                    src_res = src_pack.get_resource(file_spec.get('source', res_name))
                except NotInPack:
                    if file_spec.get('if_missing') == 'relax':
                        continue
                    else:
                        raise
                if 'replace' in file_spec:
                    src_map = self.get_map(src_pack.atlas, file_spec.get('map', src_res.name), base)
                    res = CompositeResource(res_name, src_res, src_map)
                    specs = file_spec['replace']
                    if hasattr(specs, 'items'):
                        specs = [specs]
                    for spec in specs:
                        src2_pack = self.get_pack(spec.get('pack'), src_pack, base=base)
                        src2_res = src2_pack.get_resource(
                                spec.get('source', res_name))
                        src2_map = self.get_map(src2_pack.atlas,
                                spec.get('map', src2_res.name), base)
                        cells = spec['cells']
                        res.replace(src2_res, src2_map, cells)
                elif res_name == src_res.name:
                    res = src_res
                elif 'pack_icon' in file_spec:
                    src_map = self.get_map(src_pack.atlas, file_spec.get('map', src_res.name), base)
                    res = PackIconResource(src_res, src_map, file_spec['pack_icon']['cells'])
                else:
                    res = RenamedResource(res_name, src_res)
                yield res

    def get_pack(self, pack_spec, fallback_pack=None, base=None):
        """Get a pack specified, or return the fallback pack.

        Arguments --
            pack_spec --
                Specifies a pack.
                If it is a string and starts with a $,
                then it names one of the packs
                added with add_pack.
                A string without a $ is treated as
                a URL (same as {href: URL}).

                If it is a dictionary, then
                the meaning depends on its attributes:
                    file -- names a file containing a ZIP archive;
                    href -- secifies a URI from which data may
                        be downloaded (HTTP, file, and data URIs
                        are supported so far);
                    data -- value must be a ZIP archive;
                    base64 -- value must be a ZIP archive,
                        converted to ASCII with the base64 codec.
                    unjumble -- assume the files in the pack
                        have the right names byt the wrong folders
                        and use the atlass to determine which files
                        to pull out of the ZIP
            fallback_pack (optional) --
                If the pack_spec is the empty string or None,
                then use this value instead.
            base (optional URI) --
                If the pack uses relative URL or file name,
                then it is interpreted relative to this.
                Must be a file or http URL.

        Returns --
            A pack object

        Raises --
            UnknownPack -- when the specified pack does not exist.
        """
        if not pack_spec and fallback_pack:
            return fallback_pack

        if isinstance(pack_spec, basestring) and pack_spec.startswith('$'):
            result = self.packs.get(pack_spec[1:])
            if not result:
                raise UnknownPack(pack_spec)
            return result

        atlas_spec = hasattr(pack_spec, 'get') and pack_spec.get('maps', pack_spec.get('unjumble'))
        atlas = self.get_atlas(atlas_spec, base)

        pack = self._load_raw_pack(atlas, pack_spec, base)
        if hasattr(pack_spec, 'get'):
            unjumble_spec = pack_spec.get('unjumble')
            if unjumble_spec:
                unjumble_atlas = atlas if 'maps' not in pack_spec else self.get_atlas(unjumble_spec, base)
                pack = self.make_unjumbled_pack(pack, unjumble_atlas)
        return pack

    def _load_raw_pack(self, atlas, pack_spec, base):

        # Various ways of decoding the pack spec.
        url = self.loader.get_url(pack_spec, base)
        if url and url.startswith('http://'):
            return LazyPack(self.loader, url, atlas)

        try:
            if url:
                meta, strm = self.loader.get_url_stream(url)
            else:
                strm = self.loader.get_stream(pack_spec, base)
        except CouldNotLoad, e:
            raise UnknownPack(pack_spec, e)
        except DudeItsADirectory, e:
            return SourcePack(e.path, atlas)

        # If we have data, unpack it.
        if not strm:
            raise UnknownPack(pack_spec)

        return SourcePack(strm, atlas)

    def make_unjumbled_pack(self, pack, atlas):
        """Make an unjumbled copy of this pack using this atlas.

        Given a pack with correct file names but possibly wrong folder names
        create a new pack that rearranges the files to conform
        to texturepack conventions.
        """
        pack_names = list(pack.get_resource_names())
        new_pack = RecipePack('unjumbled', 'unjumbled', atlas=atlas)
        for desired_name in atlas.get_map_names():
            nick = desired_name.split('/')[-1]
            slash_nick = '/' + nick
            for i, available_name in enumerate(pack_names):
                if available_name == nick or available_name.endswith(slash_nick):
                    res = pack.get_resource(available_name)
                    if desired_name != available_name:
                        res = RenamedResource(desired_name, res)
                    new_pack.add_resource(res)
                    del pack_names[i]
                    break
        return new_pack

    def get_map(self, atlas, spec, base):
        """Get a map from the pack if possible, otherwise try the global atlas."""
        try:
            if atlas:
                return atlas.get_map(spec, base)
        except NotInAtlas:
            pass
        return self.atlas.get_map(spec, base)

    def get_atlas(self, atlas_spec, base, atlas=None):
        """Get an atlas from this spec.

        Arguments --
            atlas_spec -- dict or list specifying atlas
            base -- used when licating external references (if any)
            atlas -- merge new atlas data in to this atlas.
                Default is to create a new atlas.

        The spec is either a dictionary mapping
        resource names to map specs,
        or is a dictionary with a single member
        'file' specifying a file to read the atlas from.
        """
        if not atlas:
            atlas = Atlas()
        if atlas_spec:
            atlas_base = (base
                if not hasattr(atlas_spec, 'items')
                else {'file': resolve_file_path(atlas_spec['file'], base)}
                if 'file' in atlas_spec
                else self.loader.get_url(atlas_spec, base))
            if hasattr(atlas_spec, 'items'):
                atlas_spec = self.loader.maybe_get_spec(atlas_spec, base, 'tpmaps')
            if hasattr(atlas_spec, 'items'):
                for name, map_spec in atlas_spec.items():
                    atlas.add_map(name, map_spec and self.get_map(atlas, map_spec, atlas_base))
            else:
                # Atlas is a list of atlasses to be merged.
                for spec in atlas_spec:
                    self.get_atlas(spec, atlas_base, atlas)
        return atlas
