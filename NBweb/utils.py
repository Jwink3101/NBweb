#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Collection of utilities used in the processing of the pages
"""
from __future__ import division, print_function, unicode_literals, absolute_import

import os,sys
import re
import markdown
from collections import namedtuple,defaultdict,OrderedDict,deque
from io import open
from datetime import datetime,timedelta
import time
import unicodedata
import fnmatch
import json
import copy
import random

import NBCONFIG

if sys.version_info >= (3,):
    unicode = str

import bottle
## NBweb
from . import stop_words # Source: http://www.ranks.nl/stopwords


class mmd_(object):
    def __init__(self,automatic_line_breaks=True):
        # Stored regex
        self.re_toc = re.compile('^\ {0,3}\[TOC\]|\n\ {0,3}\[TOC\]|^\ {0,3}\{\{TOC\}\}|\n\ {0,3}\{\{TOC\}\}') # new line or start of line, 0-3 leading spaces
        self.re_wikilinks = re.compile('(?<!\\\)\[\[(.+?)\]\]')
        self.re_del = re.compile('(?<!~)~~(.+?)~~(?!~)') # Only two ~
        self.re_link_img = re.compile('\!\{(.*?)\}([\(\[].+?[\)\]])') # Images with and without reference text
        self.re_prism_highlight = re.compile('<pre><code class=\"(.*?)\">')
        self.re_html_block = re.compile("^ {0,3}<htmlblock> *$\n(.*?)^</htmlblock> *$",flags=re.DOTALL|re.MULTILINE)
        self.re_gallery_block = re.compile("^ {0,3}<gallery> *$\n(.*?)^</gallery> *$",flags=re.DOTALL|re.MULTILINE)

        self.extensions = ['markdown.extensions.extra',
                           'markdown.extensions.toc',
                           'markdown.extensions.sane_lists']

        if automatic_line_breaks:
            self.extensions.append('markdown.extensions.nl2br')

        self.Markdown = markdown.Markdown(extensions=self.extensions)
            
        self.rand_replacement = ''.join(random.choice('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(50))

    def __call__(self,text_in):
        """
        compile an input Markdown text file

        Also handle special markdown additions
        """
        if not isinstance(text_in,unicode):
            text_in = unicode(text_in, "utf-8")

        text_in = text_in.expandtabs(4)

        text_in = self.re_toc.sub('\n[TOC]',text_in)
        text_in = self.re_wikilinks.sub('[`\\1`](\\1)',text_in)
        text_in = self.re_link_img.sub('[![\\1]\\2]\\2',text_in) # !{}(path) syntax
        
        # <gallery> block. Must be before <htmlblock>
        text_in = self.re_gallery_block.sub(self.replace_gallery_txt,text_in)
        
        
        # <htmlblock> blocks
        html_blocks = self.re_html_block.findall(text_in)
        text_in = self.re_html_block.sub(self.rand_replacement,text_in)

        self.Markdown.reset() # IMPORTANT. Otherwise, the instance gets mucked
                              # up with caches, etc.
        text_out =   self.Markdown.convert(text_in)

        # Apply the del AFTERWARDS
        text_out = self.re_del.sub(' <del>\\1</del> ',text_out)

        # Apply prism.js code highlighting. Requires "language-XXX"
        text_out = self.re_prism_highlight.sub('<pre><code class=\"language-\\1\">',text_out)

        # Re-add the html blocks. Note that we only add one at a time
        for html_block in html_blocks:
            text_out = text_out.replace(self.rand_replacement,'\n'+html_block+'\n',1)

        return text_out
    
    def replace_gallery_txt(self,re_match):
        """
        Parse gallery text that can be of the following forms:
        
            [![alt_txt](/path/to/thumb.jpg)](/path/to/img.jpg)
            optional caption that must be just a single line w/o images, etc.
    
            ![alt_txt](/path/to/img.jpg)
            !{alt_txt}(/path/to/img.jpg)
    
        into a list of tuples: (img,thumb,alt,caption)
        """
        gallery_txt = re_match.group(1)
        
        # Split it up and remove any blank lines and leading/trailing whitespace
        gallery_txt = (l.strip() for l in gallery_txt.split('\n') if len(l.strip())>0)
        images = []

        for lines in overlapping_window(gallery_txt,N=2):
            curr_line = lines[0]
            if curr_line.startswith('[!['):
                alt,thumb,img = re.findall('\[\!\[(.*?)\]\((.*?)\)\]\((.*?)\)',curr_line)[0]
            elif curr_line.startswith('!['):
                alt,thumb = re.findall('\!\[(.*?)\]\((.*?)\)',curr_line)[0]
                img = thumb
            elif curr_line.startswith('!{'):
                alt,img = re.findall('\!\{(.*?)\}\((.*?)\)',curr_line)[0]
                thumb = img
            else:
                # Not a line
                continue
    
            # Now, see if there is a caption
            caption = ""
            if len(lines) == 2 and not any(lines[1].startswith(a) for a in ['[![','![','!{']):
                caption = lines[1]
    
            images.append( (img,thumb,alt,caption))
        
        text = html_snippet('mult_photo.html',
                                bottle_template={
                                    'all_img_paths':images
                                })
        return text
     

mmd = mmd_(automatic_line_breaks=True)

def parse_file(filepath):
    """
    Return the text and the metadata of a file
    Must specify the full system path of the file
    """
    filename,ext = os.path.splitext(filepath)

    with open(filepath,encoding='utf8') as F:
        filetext = F.read()

    filetext,meta = parse_filetxt(filetext)

    # Edge case: blank index
    if os.path.basename(filename) == 'index' and len(filetext.strip()) == 0:
        meta['title'] = 'index'

    return filetext,meta

def parse_filetxt(filetext):
    filetext = to_unicode(filetext).replace(u'\ufeff', '')
                                            # ^^^ Remove BOM from windows
    meta = {'tags':set()}
    meta['meta_line_offset'] = 0
    if filetext.strip()[:10].lower().startswith('title'): # has metadata. Do not do the whole thing for speed
        filetext = filetext.split('\n') + ['']*4 # in case of empty
        line = filetext.pop(0)
        meta['meta_line_offset'] += 1
        while len(line.strip())>0:
            try:
                key,val = line.split(':',1)
            except ValueError:
                print('ERROR in metadata for {}. Not parsing remaining metadata'.format(filepath))
                break

            key = key.strip().lower()
            if key in ['tag','tags']:
                meta['tags'].update( [standard_tag(tag) for tag in val.split(',')] )
            else:
                meta[key] = val.strip()

            line = filetext.pop(0)
            meta['meta_line_offset'] += 1
        filetext = '\n'.join(filetext)
    else:
        title = filetext.strip().split('\n',1)[0].strip() # Remove leading lines too
        while len(title)>1 and title.startswith('#'):
            title = title[1:].strip()
        meta['title'] = title

    if 'date' not in meta:
        date = parse_date(meta['title']) # Try to parse it in case the title is a date. Do not actually use the parse date
        if date is not None:
            meta['date'] = meta['title']

    if len(meta['title'].strip()) == 0:
        meta['title'] = 'untitled'

    return filetext,meta


def join(*A,**K):
    outpath = os.path.normpath(os.path.join(*A,**K))
    if outpath.startswith('./'):
        return outpath[2:]
    if outpath == '.':
        return ''
    return outpath

def html_escape(text,rev=False):
    escape = {
        "&": "&amp;",
        '"': "&quot;",
        "'": "&apos;",
        ">": "&gt;",
        "<": "&lt;",
        }

    if rev:
        escape = {v:k for k,v in escape.items()}

    return "".join(escape.get(c,c) for c in text)

def parse_date(input):
    """
    Attempt to parse dates

    Heuristic matching algorithm:
      * Convert all punctuation to spaces
      * Get the length of each fmt's output and sort fmts reversed
      * If the input is shorter than the output, skip
      * If the input is longer than the output, truncate the input to the size
        of the output and try to match
          * Important to have the fmts sorted so more specific gets matched
      * Break at first match
    """

    fmts = [ "%Y %m %d %H%M%S" , "%Y %m %d %H%M"     , "%y %m %d %H %M %S" ,
             "%y%m%d%H%M%S"    , "%y%m%d %H %M"      , "%Y%m%d %H"         ,
             "%y%m%d %H%M"     , "%y%m%d%H%M"        , "%y%m%d"            ,
             "%Y%m%d %H %M %S" , "%Y %m %d %H"       , "%y %m %d"          ,
             "%Y%m%d %H %M"    , "%Y%m%d %H%M%S"     , "%y%m%d %H"         ,
             "%Y%m%d %H%M"     , "%y %m %d %H%M%S"   , "%Y%m%d%H%M"        ,
             "%Y%m%d"          , "%y%m%d %H %M %S"   , "%y %m %d %H"       ,
             "%Y %m %d"        , "%y%m%d %H%M%S"     , "%y %m %d %H %M"    ,
             "%y %m %d %H%M"   , "%Y %m %d %H %M %S" , "%Y%m%d%H%M%S"      ,
             "%Y %m %d %H %M"  ]

    if input is None:
        return None
    # Replace all punctuation with spaces
    for punc in ''',.:;"'!?[](){}-_@#$^&*''':
        input = input.replace(punc,' ').strip()

    now = datetime.now()
    fmts = [(fmt,now.strftime(fmt)) for fmt in fmts]
    fmts.sort(key=lambda f:len(f[1]),reverse=True)

    date = None

    for fmt in fmts:
        fmt,output = fmt

        if len(input) < len(output):
            continue # Will never work

        # Try to match with the input truncated to the output length
        try:
            date = datetime.strptime(input[:len(output)],fmt)
            break
        except:
            pass

    return date


def convert_relative_links(rootname,html):
    """
    Convert relative links from the original rootname (including the
    file name) to be "absolute" to the root of the folder

    Considered src,href,action

    Example:
       IN : convert_relative_links('path/to/bla/','<a href="hi">')
       OUT: '<a href="/path/to/bla/hi">'
       In : utils.convert_relative_links('path/to/bla/','<a href="../hi">')
       Out: '<a href="/path/to/hi">'

    """
    if rootname.endswith('/'):
        filedir = rootname
    else:
        filedir = os.path.split(rootname)[0]

    if filedir.startswith('/'):
        filedir = filedir[1:]

    re_refs = re.compile('(href|src|action)=\"([^\#]+?)\"',re.IGNORECASE)

    replace_queue = set()

    for link in re_refs.finditer(html):
        path = link.group(2)

        if not is_relative_link(path):
            continue

        if path.startswith('/'):
            continue

        new_path = '/'+join(filedir,path) # Will normpath too

        # Reconstruct the full command
        new = link.group(1) + '="' + new_path + '"'

        replace_queue.add((link.group(0),new))

    for old,new in replace_queue:
        html = html.replace(old,new)

    return html

def convert_internal_extension(html,extensions=None,return_links=False):
    """
    Convert all internal links to .html if they are in any of the
    allowed extensions (we don't want to convert images)
    """
    if extensions is None:
        extensions= [ ]
    
    re_refs = re.compile('(href|src|action)=\"([^\#]+?)\"',re.IGNORECASE)

    replace_queue = set()
    links = set()

    extensions = [e.lower() for e in extensions]

    for link in re_refs.finditer(html):
        path = link.group(2)

        if not is_internal_link(path):
            continue

        base,ext = os.path.splitext(path)
        if ext == '.html':
            links.add(path)
            continue

        if ext.lower() not in extensions + ['.html','.md','']: # skip media, etc
            continue

        newpath = base + '.html'

        links.add(newpath)

        # Reconstruct the full command
        new = link.group(1) + '="' + newpath + '"'

        replace_queue.add((link.group(0),new))

    for old,new in replace_queue:
        html = html.replace(old,new)

    if return_links:
        return html,list(links)
    else:
        return html

def get_media_links(html,non_media_extensions=None):
    """
    Return all internal links that are to media (i.e. extension is
    not in non_media_extensions
    """
    if non_media_extensions is None:
        non_media_extensions = []
    non_media_extensions.extend(['.html','.md',''])
    
    re_refs = re.compile('(href|src|action)=\"([^\#]+?)\"',re.IGNORECASE)
    links = set()

    for link in re_refs.finditer(html):
        path = link.group(2)

        if not is_internal_link(path):
            continue

        base,ext = os.path.splitext(path)
        if ext.lower() in non_media_extensions:
            continue   
            
        links.add(link.group(2))
    return links 
    
    

def annotate_links(html,internal=True):
    """
    Finds all internal (or any with internal=False) links (`href`) and
    other content (`src`) and adds an annotation.

    Note that it does NOT include `action`. Also, it may not be perfect as it
    will simply add a `[N]` before the leading `<`
    """

    re_ann = re.compile('\<[^>]*?(href|src)=\"([^#]+?)\"',re.IGNORECASE)

    types = {'href':'link','src':'src'}

    replacements = set()
    references = OrderedDict() # we will call it in order later

    for link in re_ann.finditer(html):

        original = link.group(0)
        path = link.group(2)

        if internal and not is_internal_link(path):
            continue

        type = types[link.group(1)]

        # See if we already had this one
        if path in references:
            reference = references[path]
        else:
            reference = len(references) + 1
            references[path] = reference

        replacement = (original,'<sup>[{}:{}]</sup>{:s}'.format(type,reference,original))
        replacements.add(replacement) # uses a set in case this isn't new

    # Do replacements
    for old,new in replacements:
        html = html.replace(old,new)

    # Add the bottom part
    add_html = ['<hr></hr>','<h4>Link Annotations:</h4>']
    for path,id in references.items():
        add_html.append('<br>[{id}]: <a href="{p}">{p}</a>'.format(id=id,p=path))

    html += '\n' + '\n'.join(add_html)
    return html

def is_internal_link(link,basename=None):
    """
    Heuristic-based detection of whether a link is internal/local.

    If specified, `basename` will be removed from the link. It will
    automatically remove both http and https. Basename may be specified as
    a string or a list of multiple base names.

    This is useful when  wanting to make links to your own site relative
    """
    link = link.lower()
    link = remove_link_basename(link,basename)

    if any(link.startswith(sw) for sw in ['/','file://','~/','{','./','../']):
        return True

    if '://' in link: # Anything *other than* file://
        return False

    # Anything relative is internal
    return True

def is_relative_link(link,basename=None):
    """
    heuristic based detection of whether or not a link.

    If specified, `basename` will be removed from the link. It will
    automatically remove both http and https. Basename may be specified as
    a string or a list of multiple base names.
    """

    link = link.lower()
    link = remove_link_basename(link,basename)

    if any(link.startswith(sw) for sw in ['./','../']):
        return True

    if '://' in link: # INCLUDE file://
        return False
    if link.startswith('/'):
        return False

    # Anything else should be relative
    return True

def remove_link_basename(link,basename):
    """
    Remove basename with automatically considering https for http and vice-versa

    Note that subdomains are NOT automatic

    Example:
        link = 'https://www.example.com/path/to/file.html'
        link = remove_link_basename(link,\
                ['http://www.example.com','http://example.com'])
        print(link) # /path/to/file.html

    Specify as None to do nothing
    """
    link0 = link.lower()
    if basename is not None:
        if not isinstance(basename,(list,tuple,set)):
            basenames = [basename]
        else:
            basenames = basename

        basenames = [b.lower() for b in basenames]

        for basename in basenames[:]: # [:] makes it a slice/view
            if re.search('[a-z].+[^s]\:\/\/',basename): # URL w/o s
                basenames.append(basename.replace('://','s://'))
            if re.search('[a-z].+s\:\/\/',basename): # URL w/ s
                basenames.append(basename.replace('s://','://'))
        for basename in set(basenames):
            if link0.startswith(basename):
                link = link[len(basename):]

    return link

def to_unicode(txt,verbose=False):
    for objtype in [list,tuple,set]:
        if isinstance(txt,objtype):
            return objtype(to_unicode(a) for a in txt)

    if sys.version_info[0] > 2:
        unicode_ = str
    else:
        unicode_ = unicode

    if verbose:
        def _print(*A,**K):
            print(*A,**K)
    else:
        def _print(*A,**K):
            pass


    if isinstance(txt,unicode_):
        _print('Already Unicode')
        return txt

    encs = ['utf8']

    # Try to decode it first
    for enc in encs:
        try:
            return unicode_(txt,enc)
        except Exception as E:
            _print("failed `unicode_(txt,'{}')`".format(enc),E)

    for enc in encs:
        try:
            return unicode_(txt,enc,'replace')
        except Exception as E:
            _print("failed `unicode_(txt,'{}','replace')`".format(enc),E)

    for enc in encs:
        try:
            return unicode_(txt,enc,'ignore')
        except Exception as E:
            _print("failed `unicode_(txt,'{}','ignore')`".format(enc),E)

    try:
        return unicode_(txt)
    except Exception as E:
        _print("failed `unicode_(txt)`",E)

    _print('giving up...')
    return txt

re_html = re.compile('\<.*?\>') # Remove all HTML and line breaks. Make lower case
re_alphanumeric = re.compile(r'[^\s\w_]+') # Remove everything but alphanumerics and spaces
re_multspace = re.compile('\s\s.*?([^\s])')

def remove_html(text):
    return re_html.sub(' ',text) # Remove html

def clean_for_search(text_html):
    """ Clean up for searching """
    text_html = to_unicode(text_html)
    text = remove_html(text_html).replace('\n',' ').lower() # Remove html, line breaks, and make lower case
    text = unicodedata.normalize('NFKD', text).encode('ascii','ignore') # https://www.peterbe.com/plog/unicode-to-ascii convert to ascii
    text = to_unicode(text)
    text = re_alphanumeric.sub(' ',text)
    text = re_multspace.sub(' \\1',text).strip() # Remove all multiple spaces

    add_stop = ['in','a','http','https']
    text = ' '.join(word for word in text.split() if not word in stop_words.stop_words + add_stop and len(word)>=3)

    return text


def standard_tag(tag):
    return tag.strip().replace(' ','_').replace('-','_').lower()

def fileparts(name,root=None):
    """
    Split a file path into parts. If root is None, will return
        dirname,basename,ext as a namedtuple
    If root is specified, will return
        dirname,basename,ext,rootpath,rootdirname,rootfullname


    NOTE: If the name ends with '/' it will assume it is a folder and set
          everything else accordingly

    The following examples should illustrate these concepts

        name = '/path/to/notebook/source/subdir/page1.md'
        root = '/path/to/notebook/source'

        fileparts(dirname='/path/to/notebook/source/subdir',
                  basename='page1',
                  ext='.md',
                  rootname=u'/subdir/page1.md',
                  rootdirname=u'/subdir',
                  rootbasename=u'/subdir/page1')

        name = '/path/to/notebook/source/subdir/' # Notice the trailing /
        fileparts(dirname='/path/to/notebook/source/subdir',
                  basename=u'',
                  ext=u'',
                  rootbasename=u'/subdir',
                  rootdirname=u'/subdir',
                  rootname=u'/subdir')
    """
    if name.endswith('/'):
        basename = ext = ''
        dirname = name[:-1] # Remove '/'
    else:
        basename,ext = os.path.splitext(name)
        dirname,basename = os.path.split(basename)

    if root is None:
        fp = namedtuple('fileparts',['dirname','basename','ext'])
        return fp(dirname=dirname,basename=basename,ext=ext)
    else:
        rootpath = os.path.relpath(name,root)
        if basename == '': # folder set above
            if rootpath == '.':
                rootpath = ''
            rootdirname = rootname = rootbasename = '/' + rootpath
        else:
            rootdirname = '/' + os.path.split(rootpath)[0]
            rootname = '/' + rootpath
            rootbasename = os.path.join(rootdirname,basename)

        fp = namedtuple('fileparts',['dirname','basename','ext','rootbasename','rootdirname','rootname'])
        return fp(dirname=dirname,basename=basename,ext=ext,rootbasename=rootbasename,rootdirname=rootdirname,rootname=rootname)

def patterns_check(rootname,patterns=None,isdir=False):
    """
    patterns_check the rootname with the patterns

    Either manually set `isdir` or send a name with trailing `/`
    """
    assert patterns is not None
    if not rootname.startswith('/'):
        rootname = '/' + rootname

    if rootname.endswith('/'):
        isdir = True
        rootname = rootname[:-1]

    filename = os.path.split(rootname)[-1]

    # rootname
    if any( fnmatch.fnmatch(rootname,exc) for exc in patterns):
        return True

    # filename
    if any( fnmatch.fnmatch(filename,exc) for exc in patterns):
        return True

    if isdir and any( fnmatch.fnmatch(rootname+'/',exc) for exc in patterns):
        return True

    # filename
    if isdir and any( fnmatch.fnmatch(filename+'/',exc) for exc in patterns):
        return True

    return False

def chunks(seq,n):
    """
    yield a len(n) tuple from seq. If not divisible, the last one would be less
    than n
    """
    _n = 0;
    for item in seq:
        if _n == 0:
            group = [item]
        else:
            group.append(item)
        _n += 1

        if _n == n:
            yield tuple(group)
            _n = 0
    if _n > 0:
        yield tuple(group)


def combine_html(item_list,annotate=False,add_date=False,show_path=False):
    """
    Combine all items in item_list (in that order) into a single HTML file

    annotate tells whether or not to annotate the files
    add_date specified if it should add the date as well
    """
    # First process into their main page and then combine
    combined = []

    for item in item_list:
        html = item['html']

        if annotate:
            html = annotate_links(html)

        page = ['<h2><a href="{rootbasename}.html">{ref_name}</a></h2>'.format(**item)]

        if show_path:
            page.append('<p><code>{rootname}</code></p>\n'.format(**item))

        date = parse_date(item.get('meta_date',''))
        if date is not None and add_date:
            page.append(date.strftime('<p>%A, %B %d, %Y, %I:%M %p</p>'))

        page.append(html)

        combined.append( '\n'.join(page) )

    return '\n<hr></hr>\n'.join(combined)

def bread_crumb(rootbasename,title=None):
    """
    Create a breadcumb for a given rootname
    """
    if rootbasename.endswith('/'):
        rootbasename += 'index'

    is_folder = os.path.split(rootbasename)[1] == 'index'

    rootbasename += '.html'
    folderPath = os.path.split(rootbasename)[0].split('/')

    crumb = [u'<a href="/">Home</a>']
    for ii,Folder in enumerate(folderPath):
        # Edge cases
        if Folder == '':continue
        if Folder == '.': continue

        # Build Links
        link = '/'.join(folderPath[:(ii+1)])
        crumb.append(u'<a href="{:s}/index.html">{:s}</a>'.format(link,Folder))

    if title is None:
        crumb += ['']
    else:
        crumb += [title] # Add the title of the page if it is specified

    return ' &gt; '.join(crumb)


def now(spaces=True):
    if spaces:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    else:
        return datetime.now().strftime('%Y-%m-%d_%H%M%S')


def filetxt_if_txt(filepath):
    """
    return filetxt if the file is text. Otherwise, raise IOError
    """
    lines = []
    with open(filepath,'rb') as F:
        for line in F:
            if b'\0' in line:
                raise IOError('File is binary (or contains a null character)')

            try:
                line = line.decode('utf8')
            except UnicodeDecodeError:
                raise IOError('File is binary (or not utf8 encoded)')

            lines.append(line)
    return ''.join(lines)

from collections import OrderedDict
def dict_factory(cursor, row):
    d = OrderedDict()
    for idx,col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class memoize:
    """
    Cache (or 'memoize') the results of a function
    
    Note that this can handle many, but not all datatypes and may not
    distinguish between tuple and list arguments
    
    Use as a decorator
    """
    max_freeze = 15
    def __init__(self, function):
        self.function = function
        self.memoized = {}
    def __call__(self, *args, **kwargs):
        key = (self.freeze(args),self.freeze(kwargs)) 
        try:
            return self.memoized[key]
        except KeyError:
            self.memoized[key] = self.function(*args, **kwargs)
            return self.memoized[key]
    @classmethod
    def freeze(cls,item,d=0):
        """
        Return a "frozen" version of an item recursivly for certain
        (but not all) datatypes
        """
        if d >= cls.max_freeze:
            return item
        
        if isinstance(item,(list,tuple)): # make sure sub items get frozen
            return tuple( cls.freeze(i,d=d+1) for i in item)
        if isinstance(item,dict):
            # use a frozenset to order doesn't matter
            return frozenset( (key,cls.freeze(val,d=d+1)) for key,val in item.items() )
        if isinstance(item,set):
            return frozenset( cls.freeze(i,d=d+1) for i in item)
        # otherwise...
        return item

def html_snippet(name,bottle_template=None):
    """
    Return the HTML snippet. If (and only if) `bottle_template` is a dictionary
    then the snippet is rendered via Bottle's template engine
    """
    text = _load_snippet(name)

    if isinstance(bottle_template,dict):
        text = bottle.template(text,**bottle_template)
    
    return text

@memoize
def _load_snippet(name):
    """
    Just load the snippet text. This is separate from html_snippet
    since we want to cache (memoize) this part but *not* the bottle template
    part
    """
    snippet_path = os.path.join(os.path.dirname(__file__),'HTML_snippets',name)
    with open(snippet_path,'r',encoding='utf8') as F:
        text = F.read()
    return text

@memoize
def clean_new_rootpath(rootpath):
    """
    Clean up names for a rootpath
    
    * Must be alphanumeric
    * Must just be ASCII characters
    * Name must *start* with an alphanumeric though may contain (some) others
    * If either does not have an extension or the extension is not in the 
      allowed, use the first extension
    """
    alphanumeric = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    ALLOWED_CHARS= alphanumeric + '._-()+'

    rootpath = rootpath[1:] if rootpath.startswith('/') else rootpath
    rootpath = rootpath.replace(' ','_')

    # Convert any odd characters to ASCII and then back to Unicode
    rootpath = unicodedata.normalize('NFKD', rootpath).encode('ascii','ignore') # https://www.peterbe.com/plog/unicode-to-ascii conver to ascii
    rootpath = to_unicode(rootpath)
    rootpath = ''.join(r for r in rootpath if r in ALLOWED_CHARS)

    while rootpath[0] not in alphanumeric:
        rootpath = rootpath[1:]

    while rootpath[-1] not in alphanumeric:
        rootpath = rootpath[:-1]

    if os.path.splitext(rootpath)[-1] not in NBCONFIG.extensions:
        rootpath += NBCONFIG.extensions[0]
    return rootpath

def titledict(meta):
    """
    Create a dictionary of title keys with some logic

    {title}          -- Parsed title
    {raw_date}       -- Datestring as provided in meta data
    {short_date}     -- '%Y-%m-%d' format
    {long_date}      -- '%Y-%m-%d_%H%M%S' format
    {loc_long_date}  -- '%Y-%m-%d_%H%M%S' at current time locally
    {loc_short_date} -- ''%Y-%m-%d' at current time locally

    """
    res = {}
    res['title'] = meta['title']

    res['raw_date'] = meta.get('date','')
    date = parse_date(res['raw_date'])
    if date is None:
         res['long_date'] = res['short_date'] = ''
    else:
        res['long_date'] = date.strftime('%Y-%m-%d_%H%M%S')
        res['short_date'] = date.strftime('%Y-%m-%d')

    date_loc = datetime_adjusted(NBCONFIG.time_zone)
    res['loc_long_date'] = date_loc.strftime('%Y-%m-%d_%H%M%S')
    res['loc_short_date'] = date_loc.strftime('%Y-%m-%d')

    return res

def datetime_adjusted(tz=0):
    """
    Return a datetime object with the time zone adjusted to
    `tz`. 
    
    Input:
        tz  : Time zone offset. Must be either a numerical value 
              or a string of the form '-0700'
              Or None for default
    """
    if tz is None:
        return datetime.now() 
    
    if isinstance(tz,(str,unicode)):
        if len(tz) != 5:
            raise ValueError('tz must be a string format, ex: +0500')

        # Convert to float
        tz = float(tz[0] + '1') * ( float(tz[1:3]) + float(tz[3:5])/60.0)
    
    tz = float(tz) # To make sure it can be converted to a float!

    offset = time.timezone if (time.localtime().tm_isdst == 0) else time.altzone
    offset = offset // -3600 # Time adjusts west.

    # Get the difference between tz and offset
    change = tz - offset
    return datetime.now() + timedelta(hours=change)

def overlapping_window(iterable,N=2):
    """
    Generate OVERLAPPING windows of size N, if possible.
    Example:
        overlapping_window('abcde',N=3)
        [ ('a','b','c'), ('b','c','d'), ('c','d','e'),('d','e'),('e',)]
    
    Note that the sequence need not have a length
    """
    wind = deque(maxlen=N)
    for item in iterable:
        wind.append(item)
        if len(wind) == N:
            yield tuple(wind)
    
    # There are some edge cases:
    if len(wind) == 0: # Empty iterable
        raise StopIteration
    
    if N == 1: # All yielded
        raise StopIteration
    
    if len(wind) < N: # It never yielded above ( N < len(iterable))
        yield tuple(wind) # This will also handle len(iterable) == 1 with N>1
                          # (N>1 will be done above)
    while True: # Exhaust the rest
        wind.popleft()
        if len(wind) == 0:
            break
        yield tuple(wind)

















