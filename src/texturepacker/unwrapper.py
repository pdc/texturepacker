# -*-coding: UTF-8-*-

"""Given the alleged URL of a texture pack, find plausing forum and download URLs.

This is tricky because often they are embedded in a page that is wrapped in
a bit.ly link which is wrapped in an adf.ly link and the download is hosted on Mediafire
behind yeat another layer of redirects."""

import sys
import os
import httplib2
import re
from BeautifulSoup import BeautifulSoup
import json

# Unwrapper functions take a URL and optiopnal Http object
# and return a dict of categorized URLs or None.

ADFLY_RE = re.compile(ur"""
    function \s close_bar\(\) \s \{ \s+
    self\.location \s = \s '(?P<next>[^']*)'; \s+
    \}
    """, re.VERBOSE)
def unwrap_adfly(url, resp, body, http=None):
    # adf.ly wraps the target page in a frameset or something
    # It has a close button which restores the target page.
    m = ADFLY_RE.search(body)
    if m:
        return m.groupdict()
    
def unwrap_bitly(url, resp, body):
    # Redirects happen transparently
    # We just need to tell caller to process the results using the next unwrapper.
    return {
        'next': (resp['content-location'], resp, body),
    }
    

URL_SCORES = [
    (re.compile(r'^http://(www\.)?mediafire\.com/'), 50),
    (re.compile(r'^http://bit\.ly/'), 25),
    (re.compile(r'^http://adf\.ly/'), 25),
]
LABEL_SCORES = [
    (re.compile('download', re.IGNORECASE), 100),
]
LICENCE_SCORES = [
    (re.compile('^http://creativecommons.org/licenses/'), 100),
]
WOT_NO_SLASH_RE = re.compile(r'^https?://[\w.-]+$')

def unwrap_minecraftforum(url, resp, body):
    urls = {
        'forum': url, # This *is* the forum page!
    }
    
    # It might also have clues as to where the downloads are.
    soup = BeautifulSoup(body)
    post_elt = soup.first('div', 'entry-content')
    
    best_href = None
    best_score = 0
    for a_elt in post_elt.findAll('a', 'bbc_url'): # This class distinguishes URLS inserted by the author of the post.
        try:
            href = a_elt['href']
            
            # Many entries contain self-links.
            if href == url:
                continue

            # Check for licence link.
            licence_score = sum(pat_score for (pat, pat_score) in LICENCE_SCORES if pat.search(href))
            if licence_score:
                urls['licence'] = href
                continue
                
            # Otherwise, this is a candidate for download or home link.
            score = sum(pat_score for (pat, pat_score) in URL_SCORES if pat.search(href))
            labels = []
            try:
                label = ''.join(a_elt.findAll(text=True))
                if label:
                    labels.append(label)
            except AttributeError:
                pass
            # Look for label immediately preceeding link:
            label = a_elt.findPreviousSibling(text=True)
            if label:
                labels.append(label)
            
            for label in labels:
                score += sum(pat_score for (pat, pat_score) in LABEL_SCORES if pat.search(label))
            if a_elt.img:
                score += 10
            if score > best_score:
                best_href, best_score = href, score
                print href, score
        except KeyError, e:
            print >>sys.stderr, a_elt, 'did not have', e
    if best_href:
        if WOT_NO_SLASH_RE.match(best_href):
            best_href += '/'
        urls['next'] = best_href        
        
    return urls
    
MEDIAFIRE_PKR_RE = re.compile(r"^<!--\s*var LA=\s*false;\s*pKr='([^']+)';")
MEDIAFIRE_CALL_RE = re.compile(r'^DoShow\("notloggedin_wrapper"\);\s*cR\(\);\s*(\w+)\(\);')
MEDIAFIRE_CALL2_RE = re.compile(r"\w+\('\w+','([a-f\d]+)'\)")

def unwrap_mediafire(url, resp, body):
    """Mediafire wrap downloads in a mass of obsfucated JavaScript. Extract and return the next URL."""
    urls = {
        'download': url,
    }
    
    soup = BeautifulSoup(body)
    
    # The first of three codes needed to generate the next URL.
    secret_qk = url.split('?', 1)[1]
    
    # The JavaScript calls a function whose name is randomized.
    # So our first job is to find the name of the function.
    for elt in soup.body.findAll('script', type='text/javascript', language=None):
        m = MEDIAFIRE_CALL_RE.search(elt.string)
        if m:
            secret_func = m.group(1)     
            break
            
    # That function has within it some 'encrypted' code
    # which in turn contains the third key.
    FUNC_PAT = re.compile(r"""
        function \s %s .*
        unescape\('(?P<cyphertext>[a-f\d]+)'\); \s*
        \w+ = (?P<count>\d+) ; \s*
        for \( .* \) .*
        \w+ = \w+ \+ \(String.fromCharCode\(parseInt\(\w+.substr\(i\s\*\s2,\s2\),\s16\) \^ 
                (?P<key>[\d^]+)
        \)\); \s*
        eval\(\w+\); 
        """ % secret_func, re.VERBOSE)

    for elt in soup.body.findAll('script', type='text/JavaScript', language='JavaScript'): # lol capitalization
        m = MEDIAFIRE_PKR_RE.search(elt.string)
        if m:
            # This is the second code needed to get the next URL.
            secret_pKr = m.group(1)
            
            # Now to find the 'encrypted' function and pull the third code out of it.
            m = FUNC_PAT.search(elt.string)
            if m:
                plaintext = mediafire_decode(m.group('cyphertext'), m.group('count'), m.group('key'))
                
                # Now hoik the third code out of the plaintext.
                m = MEDIAFIRE_CALL2_RE.match(plaintext)
                secret_pk1 = m.group(1)
            break
        
    # The next URL is also on Mediafire -- this is the dynamically generated page
    # that is loaded in to an invisible IFRAME.
    urls['next'] = ('http://www.mediafire.com/dynamic/download.php?qk=%s&pk1=%s&r=%s' 
                % (secret_qk, secret_pk1, secret_pKr))    
    return urls
    
def mediafire_decode(cyphertext, count, key):
    """Mediafire use a simple cypher to obscure some codes embedded in their HTML.
    
    Arguments --
        cyphertext -- lowercase hexadecimal digits. Mediafire needlessly wrap it in unescape(...).
        count -- number of pairs of digits to consider; a int or string representation of an int.
        key -- the expression XORed with all bytes, in the form of a string
                containing ^-separated integers. For example, "13^7".
                
    Returns --
        A byte string, usually containg JavaScript code to pass to eval.
    """
    # Super-secred decryption in progress!!
    count = int(count)
    key = reduce(lambda x, y: x ^ y, [int(x) for x in key.split('^')])
    plaintext = ''.join(chr(int(cyphertext[2 * i:2 * i + 2], 16) ^ key) for i in range(count))
    return plaintext

MF_DOWNLOAD_ENIGMA_RE = re.compile(r""" 
    unescape\('(?P<cyphertext>[a-f\d]+)'\); 
    \w+ = (?P<count>\d+) ; 
    for \(i = 0; i < \w+; i\+\+ \)
    \w+ = \w+ \+ \(String.fromCharCode\(parseInt\(\w+.substr\(i\s\*\s2,\s2\),\s16\) \^ 
            (?P<key>[\d^]+)
    \)\);
    eval\(\w+\); """, re.VERBOSE)
MF_DOWNLOAD_ROTOR_RE = re.compile(r"(\w+)='(\w+)';")
MF_DOWNLOAD_INNERHTML_RE = re.compile(r"""
    case \s 15:  # Ensure we have the correct branch of the switch
    .*? 
    href=\\"(?P<prefix>http://download\d+.mediafire.com/)" 
    \s* \+ \s*
    (?P<key>\w+)
    \s* \+ \s*
    "(?P<suffix>[^"]+\.zip)\\"
    """, re.VERBOSE)
   
    
def unwrap_mediafire_download(url, resp, body):
    """Pull out the link to the actual download from Medafire’s hidden page"""
    
    # This only works if the cookies and other stuff are set up correctly.
    # There is only one SCRIPT element so no point in anlysing the HTML structure …
    m = MF_DOWNLOAD_ENIGMA_RE.search(body)
    if m:
        code = mediafire_decode(m.group('cyphertext'), m.group('count'), m.group('key'))
        enigma = dict(MF_DOWNLOAD_ROTOR_RE.findall(code))
        m = MF_DOWNLOAD_INNERHTML_RE.search(body)
        href = m.group('prefix') + enigma[m.group('key')] + m.group('suffix')
        return {
            'next': href,
        }
    return {}
    
def unwrap_anything_and_save_it(url, resp, body):
    """For debugging! This unwrapper saves its arguments to disk for later analysis."""
    name = url.split('/')[2].replace('www.', '')
    with open('%s.json' % name, 'wb') as strm:
        json.dump(resp, strm, indent=4)
    print >>sys.stderr, 'Wrote headers to %s.json' % name
    with open('%s.html' % name, 'wb') as strm:
        strm.write(body)
    print >>sys.stderr, 'Wrote body to %s.html' % name
    return {}
    
    
URL_IS_DOWNLOAD_SCORES = [
    (re.compile('^http://(www\.)?mediafire.com/', re.IGNORECASE), 50),
    (re.compile('\.zip$', re.IGNORECASE), 50),
]
def guess_url_is_download(url):
    """Return a positive number if this URL looks likely to be a ZIP download."""
    return sum(score for (pat, score) in URL_IS_DOWNLOAD_SCORES if pat.search(url))
    
URL_IS_HOME_SCORES = [
    (re.compile('^http://(www\.)?planetminecraft\.com/texture_pack/[\w-]+/', re.IGNORECASE), 100),
]
def guess_url_is_home(url):
    """Return a positive number if this URL looks likely to be an external homepage for the pack.."""
    return sum(score for (pat, score) in URL_IS_HOME_SCORES if pat.search(url))
    
    
    
# DRIVER
    
_PREFIX_UNWRAPPERS = [
    ('adf.ly', unwrap_adfly),
    ('bit.ly', unwrap_bitly),
    ('minecraftforum.net', unwrap_minecraftforum),
    ('mediafire.com/?', unwrap_mediafire),
    ('mediafire.com/dynamic/download.php?', unwrap_mediafire_download),
]
COOKIE_EXPIRES_RE = re.compile("""
    expires=
    (Mon|Tue|Wed|Thu|Fri|Sat|Sun), \s [^;,]+
    [;,]?
    """, re.VERBOSE)
    
class Unwrapper(object):
    """Device for peeling back layers of redirection web sites to get the actual download link"""
    def __init__(self, http=None):
        self.http = http or httplib2.Http()
    
    def unwrap(self, url, until=None):
        if until:
            until = set(until)
        
        cookie_jar = {}
        queue = [url]
        result = {}
        while queue:
            url_resp_body = queue.pop(0)
            need_download = isinstance(url_resp_body, basestring)
            if need_download:
                url = url_resp_body
            else:
                url, resp, body = url_resp_body
            x = url
            if x.startswith('http://'):
                x = x[7:]
            if x.startswith('www.'):
                x = x[4:]
            for prefix, func in _PREFIX_UNWRAPPERS:
                if x.startswith(prefix):
                    # Have found a handler for this URL.
                    if need_download:
                        # Dereference the URL; also takes care of copying cookies beetween requests.
                        headers = {}
                        if cookie_jar:
                            headers['cookie'] = ';'.join('%s=%s' % (key, val) for (key, val) in cookie_jar.items())
                        resp, body = self.http.request(url, headers=headers)
                        if 'set-cookie' in resp:
                            # Highly simplified cookie-wrangling—we assume we just want to copy all of them.
                            cookies_line = COOKIE_EXPIRES_RE.sub('', resp['set-cookie'])
                            for cookie_def in cookies_line.split(','):
                                parts = cookie_def.strip().split(';')
                                cookie_name, cookie_value = parts[0].split('=', 1)
                                cookie_jar[cookie_name] = cookie_value
                    res = func(url, resp, body)
                    
                    if res and 'forum' in res and 'next' in res:
                        # We have found a forum page; its links might be download or home.
                        # Only the obvious cases are handled here (e.g., *.zip is a download).
                        # More subtle cases will require a further download.
                        u = res['next']
                        if 'download' not in res and guess_url_is_download(u):
                            res['download'] = u
                        if 'home' not in res and guess_url_is_home(u):
                            res['home'] = u
                    
                    result.update(res)
                    break
            else:
                # Could not unwrap this URL, so we assume it is the final source.
                result['final'] = url
            if until and not (until - set(result.keys())):
                break
            if 'next' in result:
                queue.append(result.pop('next'))
        return result
        
default_unwrapper = None

def unwrap(*args, **kwargs):
    """"Shortcut for unwrapping a URL.
    
    Equivalent to Unwrapper().unwrap(...).
    """
    global default_unwrapper
    if not default_unwrapper:
        default_unwrapper = Unwrapper()
    return default_unwrapper.unwrap(*args, **kwargs)
        
if __name__ == '__main__':
    u = 'http://adf.ly/380075/forestdepths'
    print Unwrapper().unwrap(u)
    
