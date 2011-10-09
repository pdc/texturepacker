# -*-coding: UTF-8-*-

"""Given the alleged URL of a texture pack, find plausing forum and download URLs.

This is tricky because often they are embedded in a page that is wrapped in
a bit.ly link which is wrapped in an adf.ly link and the download is hosted on Mediafire
behind yeat another layer of redirects."""

import unittest
from mock import Mock, patch

import sys
import os
import httplib2
import json
from texturepacker.unwrapper import *

def get_data(file_name):
    """Return the raw data."""
    file_path = os.path.join(os.path.dirname(__file__), 'test_data/unwrapper', file_name)
    with open(file_path, 'rb') as strm:
        return strm.read()
        
def get_json(file_name):
    """Return the JSON-encoded data."""
    file_path = os.path.join(os.path.dirname(__file__),  'test_data/unwrapper', file_name)
    with open(file_path, 'rb') as strm:
        return json.load(strm)
        
        
class HttpStub(object):
    def __init__(self):
        self.responses = {}
        self.requests = []
        
    def add(self, url, name):
        self.responses[url] = name
        
    def request(self, url, *args, **kwargs):
        name = self.responses[url]
        self.requests.append((name, kwargs.get('headers')))
        resp = get_json('%s.json' % name)
        body = get_data('%s.html' % name)
        return resp, body
        
def stub_http(*args):
    """Decorator to set up a temporary fake HTTP client library.
    
    Arguments --
        Tuples (URL, NAME) where NAME is used to find data files to
        use as the result of requesting the URL.
        
    Returns -- 
        A function that decorates the function this decorator is decorating.
    """
    http = HttpStub()
    for url, name in args:
        http.add(url, name)
    http_class = Mock()
    http_class.return_value = http
    inner_decorator = patch('httplib2.Http', http_class)
    def outer_decorator(func):
        def decorated_func(*args, **kwargs):
            args += (http,)
            return inner_decorator(func)(*args, **kwargs)
        return decorated_func
    return outer_decorator
    
class TestStubbity(unittest.TestCase):
    # Check that the stubbing itself is effective.
    @stub_http(('http://example.org/foo/bar/baz/quux', 'adfly'))
    def test_adfly_stubbed(self, http):
        http = httplib2.Http()
        resp, body = http.request('http://example.org/foo/bar/baz/quux')
        self.assertTrue('http://adf.ly/favicon.ico' in body)
        self.assertEqual('http://adf.ly/380075/forestdepths', resp['content-location'])
        self.assertEqual(['adfly'], http.requests)
        
# Tests for the individual sites’ unwrappers.
class TestHelperUnwrappers(unittest.TestCase):        
    def test_unwrap_adfly(self):
        urls = unwrap_adfly('http://adf.ly/380075/forestdepths', get_json('adfly.json'), get_data('adfly.html'))
        self.assertEqual('http://bit.ly/pXTHAp', urls['next'])
        
    def test_unwrap_bitly(self):
        resp, body = get_json('forum1.json'), get_data('forum1.html')
        urls = unwrap_bitly('http://bit.ly/pXTHAp', resp, body)
        self.assertEqual(('http://www.minecraftforum.net/topic/617455-16x-18-forest-depths-wip-v04/', resp, body),
            urls['next'])
        
    def test_unwrap_mediafire(self):
        resp, body = get_json('mediafire.json'), get_data('mediafire.html')
        urls = unwrap_mediafire('http://www.mediafire.com/?p6gbi987u93t6os', resp, body)
        
        expected = 'http://www.mediafire.com/dynamic/download.php?qk=p6gbi987u93t6os&pk1=f8cff2a113114097978837db48750c2f0dbe1ae019c327dd15760ee74e3cb0aa93ed8fc77d41bccfedcc9f367b3597dc&r=3p0y3' 
        self.assertEqual(expected, urls['next'])
        
    def test_unwrap_mediafire_download(self):
        
        resp, body = get_data('mediafire-download-2.json'), get_data('mediafire-download-2.html')
        urls = unwrap_mediafire_download('http://www.mediafire.com/dynamic/download.php?qk=xxx&pk1=xxx&r=xxx', resp, body)
        
        # This is my best guess based on poking through the JavaScript code!
        expected = 'http://download197.mediafire.com/010eb3678beg/p6gbi987u93t6os/ForestDepths+v0.4.zip'
        self.assertEqual(expected, urls['next'])
        
        
class TestMinecraftforumUnwrapper(unittest.TestCase):
    def setUp(self):
        resp, body = get_json('forum1.json'), get_data('forum1.html')
        self.urls = unwrap_minecraftforum('http://www.minecraftforum.net/topic/617455-16x-18-forest-depths-wip-v04/', resp, body)

    def test_forum_url(self):
        self.assertEqual('http://www.minecraftforum.net/topic/617455-16x-18-forest-depths-wip-v04/', self.urls['forum'])
        
    def test_next_url(self):
        self.assertEqual('http://www.mediafire.com/?p6gbi987u93t6os', self.urls['next'])
        
class TestMinecraftforumz(unittest.TestCase):
    def do_unwrap(self, name, url=None):
        if not url:
            url = 'http://example.com/%s' % name
        resp, body = {'content-location': url}, get_data('%s.html' % name)
        urls = unwrap_minecraftforum(url, resp, body)
        return urls
        
    def test_bitly_address_with_image_label(self):
        urls = self.do_unwrap('forum2', 'http://www.minecraftforum.net/topic/584177-16x18-%e2%80%a2%e2%80%a2%e2%80%a2%e2%96%ba-comfy-n-cozy-%e2%97%84%e2%80%a2%e2%80%a2%e2%80%a2/')
        self.assertEqual('http://bit.ly/nUClBn', urls['next'])         
        
    def test_adfly_address_with_text_label(self):
        urls = self.do_unwrap('forum3', 'http://www.minecraftforum.net/topic/572115-16x16-olive-173/')
        self.assertEqual('http://adf.ly/2fjAh', urls['next'])
        
    def test_alicence(self):
        urls = self.do_unwrap('forum3', 'http://www.minecraftforum.net/topic/572115-16x16-olive-173/')
        self.assertEqual('http://creativecommons.org/licenses/by-nc-nd/3.0/', urls['licence'])
        
    def test_adfly_address_with_text_label(self):
        # In this case it is really the home page not the download page.
        urls = self.do_unwrap('forum4')
        self.assertEqual('http://fl.xrbpowered.com/', urls['next'])
        
        
class TestGuessUrls(unittest.TestCase):
    def test_negative(self):
        self.assertEqual(0, guess_url_is_download('http://creativecommons.org/licenses/by-nc-nd/3.0/'))
        
    def test_mediafire(self):
        self.assertTrue(guess_url_is_download('http://www.mediafire.com/?p6gbi987u93t6os'))
    
    def test_dot_zip(self):
        self.assertTrue(guess_url_is_download('http://www.example.com/foo/nbar/baz.zip'))
        
    def test_mediafire(self):
        self.assertTrue(guess_url_is_home('http://www.planetminecraft.com/texture_pack/leostereos-textures-revamped/'))
    
        
# Test for taking a URL through several hops to its final source.
class TestUnwrapper(unittest.TestCase):
    @stub_http(('http://adf.ly/380075/forestdepths', 'adfly'), ('http://bit.ly/pXTHAp', 'forum1'), ('http://www.mediafire.com/?p6gbi987u93t6os', 'mediafire'), ('http://www.mediafire.com/dynamic/download.php?qk=p6gbi987u93t6os&pk1=f8cff2a113114097978837db48750c2f0dbe1ae019c327dd15760ee74e3cb0aa93ed8fc77d41bccfedcc9f367b3597dc&r=3p0y3', 'mediafire-download-2'))
    def setUp(self, http):
        self.http = http
        self.http.requests = []
        self.unwrapper = Unwrapper()
        self.urls = self.unwrapper.unwrap('http://adf.ly/380075/forestdepths')
        
    def test_checked_them_all(self):
        self.assertEqual(['adfly', 'forum1', 'mediafire', 'mediafire-download-2'], [x for (x, y) in self.http.requests])
        
    def test_found_forum(self):
        self.assertEqual('http://www.minecraftforum.net/topic/617455-16x-18-forest-depths-wip-v04/', self.urls['forum'])
        
    def test_found_download(self):
        expected = 'http://www.mediafire.com/?p6gbi987u93t6os'
        self.assertEqual(expected, self.urls['download'])
        
    def test_found_final_url(self):
        expected = 'http://download197.mediafire.com/010eb3678beg/p6gbi987u93t6os/ForestDepths+v0.4.zip'
        self.assertEqual(expected, self.urls['final'])

    def test_copied_cookie(self):
        # I don’t think the Mediafire download will work without it!
        self.assertTrue('ukey=c6keq7fw96q395gyxlyfg19ht1bj7o8s' in self.http.requests[-1][1]['cookie'])
        
        
# Test for upwrapping a URL ponly enough to find the download URL
class TestPartialUnwrapper(unittest.TestCase):
    @stub_http(('http://adf.ly/380075/forestdepths', 'adfly'), ('http://bit.ly/pXTHAp', 'forum1'))
    def setUp(self, http):
        self.http = http
        self.http.requests = []
        self.unwrapper = Unwrapper()
        self.urls = self.unwrapper.unwrap('http://adf.ly/380075/forestdepths', until=['download', 'forum'])
        
    def test_checked_them_all(self):
        self.assertEqual(['adfly', 'forum1'], [x for (x, y) in self.http.requests])
        
    def test_found_forum(self):
        self.assertEqual('http://www.minecraftforum.net/topic/617455-16x-18-forest-depths-wip-v04/', self.urls['forum'])
        
    def test_found_download(self):
        expected = 'http://www.mediafire.com/?p6gbi987u93t6os'
        self.assertEqual(expected, self.urls['download'])
        
    def test_not_found_final_url(self):
        expected = 'http://download197.mediafire.com/010eb3678beg/p6gbi987u93t6os/ForestDepths+v0.4.zip'
        self.assertFalse('final' in self.urls)
        
        
        
        
if __name__ == '__main__':
    sys.exit(unittest.main())
    

    
    



