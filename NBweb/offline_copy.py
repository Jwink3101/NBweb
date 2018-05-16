#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals, absolute_import

import os,sys
from io import open
import re

# Python Compatability
if sys.version_info[0] >= 3:
    unicode = str
    xrange = range

from bottle import HTTPError

from . import utils
from . import main
from .nbconfig import NBCONFIG

# Incomplete todo:
# - [X] Home page / blog
# - [X] Link to homepage
# - [C] Reroute ?map=true to _sitemap
# - [X] Fix bug with all page on sitemap (and maybe original home?)
# - [X] Special pages
#     - [X] todo
#     - [X] tags
#     - [X] random
# - [X] Photo Galleries

def offline_copy(_export_path):
    """ 
    This is the main tool for the offline copy. It has to do some dirty
    tricks to get it to work. 
    
    It is not designed to be efficient and will make a full copy on each run
    """
    global export_path
    export_path = _export_path
    
    # First, monkey patch the original config
    main.NBCONFIG.protectect_dirs = []
    main.NBCONFIG.protected_users = {}
    main.NBCONFIG.edit_users = {}
    
    # Now monkey patch NBweb
    main.REQUIRELOGIN = False

    pages = []

    # Copy and work all source files 
    for dirpath,dirnames,filenames in os.walk(NBCONFIG.source):
        for dirname in dirnames[:]: # Iterate a copy since we will delete in place
            if any(dirname.startswith(i) for i in ['.']):
                dirnames.remove(dirname) # So we do not parse it later
                continue
            if dirname == '_scratch':
                dirnames.remove(dirname) # So we do not parse it later
                continue
            
            # Names
            src_systemname = os.path.join(dirpath,dirname)
            rootname = os.path.relpath(src_systemname,NBCONFIG.source) # No leading / though
            dest_systemname = os.path.join(export_path,rootname)
            
            mkdir(rootname,isfile=False) # Will make the dir no matter what
            
            # Index
            dest = os.path.join(export_path,rootname, 'index.html')
            
            # Exclusions.
            if main.exclusion_check(utils.join('/',rootname +'/')):
                with open(dest,'w',encoding='utf8') as FF:
                    FF.write('')
                continue
                
            try:
                html = main.main_route('/' + rootname + '/')
            except HTTPError:
                # Likely some additional resource in _NBweb
                try:
                    os.rmdir(dest_systemname) # Should be empty
                except OSError:
                    pass
                os.symlink(src_systemname,dest_systemname)
                continue
                
                
            html = process_page(html,dest)
            with open(dest,'w',encoding='utf8') as FF:
                FF.write(html)
            
            # _all
            dest = os.path.join(export_path,'_all',rootname, 'index.html')
            mkdir(dest,isfile=True,isfull=True)
            
            html = main.allpage('/'+ rootname +'/')
            html = process_page(html,dest)
            with open(dest,'w',encoding='utf8') as FF:
                FF.write(html)
            
        
        # Loop each file
        for filename in filenames:
            if os.path.splitext(filename)[0] == 'index':
                continue    # Already made above
                
            # Names
            src_systemname = os.path.join(dirpath,filename)
            rootname = os.path.relpath(src_systemname,NBCONFIG.source) # No leading / though
            dest_systemname = os.path.join(export_path,rootname)
            
            mkdir(rootname,isfile=True) # Will make the dir no matter what
            try:
                os.symlink(src_systemname,dest_systemname)           
            except OSError:
                os.remove(dest_systemname)
                os.symlink(src_systemname,dest_systemname)
            
            rootbasename,ext = os.path.splitext(rootname)
            if ext in NBCONFIG.extensions:
                dest = os.path.join(export_path,rootbasename + '.html')
                try:
                    html = main.main_route(rootbasename + '.html')
                except:
                    print('Issue with: {}'.format(rootname))
                
                html = process_page(html,dest)
                 
                with open(dest,'w',encoding='utf8') as FF:
                    FF.write(html)
                pages.append(rootbasename)

    ## Index pages
    # Home page w/o blog
    dest_systemname = os.path.join(export_path,'')
    dest = os.path.join(export_path,'index.html')
    
    html0 = main.main_route('/',map_view=True)
    
    html = process_page(html0,dest)
    with open(dest,'w',encoding='utf8') as FF:
        FF.write(html)

    # Also write the sitemap
    dest = os.path.join(export_path,'_sitemap/index.html')
    mkdir('/_sitemap',isfile=False)
    html = process_page(html0,dest)
    with open(dest,'w',encoding='utf8') as FF:
        FF.write(html)
    
    # _all
    dest = os.path.join(export_path,'_all','index.html')
    
    html = main.allpage('/')
    html = process_page(html,dest)
    with open(dest,'w',encoding='utf8') as FF:
        FF.write(html)
    
    ## Blog Pages
    if len(NBCONFIG.blog_dirs) > 0:
        blog_num = 0
        while True:
            dest = os.path.join(export_path,'_blog',unicode(blog_num),'index.html')
                
            try:
                html = main.main_route('/',map_view=False,blog_num=blog_num)
            except HTTPError:
                break # At the last one
            
            mkdir(dest,isfile=True,isfull=True)  
            
            html = process_page(html,dest)
            with open(dest,'w',encoding='utf8') as FF:
                FF.write(html)
            blog_num += 1
        # Make the home page. 
        dest = os.path.join(export_path,'index.html')
        html = main.main_route('/',map_view=False,blog_num=0)
        html = process_page(html,dest)
        with open(dest,'w',encoding='utf8') as FF:
            FF.write(html)
    
    ## Special Pages
    make_random_forward(pages)
    
    # Tags
    dest = os.path.join(export_path,'_tags/index.html')
    mkdir(dest,isfile=True,isfull=True)  
    html = main.return_tags()
    html = process_page(html,dest)
    with open(dest,'w',encoding='utf8') as FF:
        FF.write(html)
    
    # ToDos
    dest = os.path.join(export_path,'_todo/index.html')
    mkdir(dest,isfile=True,isfull=True)  
    html = main.return_todo()
    html = process_page(html,dest)
    with open(dest,'w',encoding='utf8') as FF:
        FF.write(html)
    
    txt = main.return_todo_txt()
    dest = os.path.join(export_path,'_todo/todo.txt')
    with open(dest,'w',encoding='utf8') as FF:
        FF.write(txt)
    
    # Galleries
    cpsym( utils.join(NBCONFIG.scratch_path,'_galleries'),utils.join(export_path,'_galleries'))
        
    ## Clean up
    for F in [utils.join(export_path,'_NBweb',a) for a in ['NBCONFIG.py','NBCONFIG.pyc','template.html']]:
        try:
            os.remove(F)
        except:
            pass
    
    # Make sure there are never any directory listings
    for dirpath,dirnames,filenames in os.walk(export_path):
        if 'index.html' not in filenames:
            with open(utils.join(dirpath,'index.html'),'w',encoding='utf8') as F:
                F.write('')
    
    
def make_random_forward(pages):
    """Write out a page to randomly forward"""

    txt = """\
    <script type="text/javascript">

    var urls = new Array(PAGES);

    function redirect()
    {
        window.location = urls[Math.floor(urls.length*Math.random())];
    }

    redirect()
    </script>
    """.replace('    ','')

    pages = ('"./../'+page+ '.html"' for page in pages)
    pages = (utils.to_unicode(page) for page in pages)
    
    rand_file = utils.join(export_path,'_random/index.html')
    mkdir(rand_file,isfile=True,isfull=True)
    
    with open(rand_file,'wb') as F:
        F.write(txt.replace('PAGES',','.join(pages)).encode('utf8'))



re_dirlinks = re.compile('(href|src)=\"/(.*?)/\"') # Starts with /, Ends in /
re_all = re.compile('(href|src)=\"/_all/(.*?)\"') # starts with /_all
re_intlinks = re.compile('(href|src)=\"/(.*?)\"') # Starts with /
def process_page(html,dest):
    """
    Fix the pages for offline
    
    * Fix internal links to be relative
    * Fix links to directories to end in 'index.html'
    
    Notes:
        
    * all internal links will, by previous processing, start with '/' and
      pages will end in .html IF they are in the main content. We have to
      work around special pages that do not have a directory name
    
    """
    html0 = html[:]
    to_root = os.path.relpath(export_path,dest)
    to_root = to_root[1:]# Change '../' or '..' to '.' or './'
    
    # Fix links to directories first since that is easier to find
    html,N1 = re_dirlinks.subn(r'\1="/\2/index.html"',html)
    
    # all pages links
    html,N2 = re_all.subn(r'\1="/_all/\2/index.html"',html)
    
    # Add index.html for any other internal links. NOTE: by preprocessing
    # all internal links from the main content will already end in .html so this
    # is just special pages.
    for match in re_intlinks.finditer(html):
        dest = match.groups()[-1]
        ext = os.path.splitext(dest)[-1]
        if ext == '':
            old = r'{}="/{}"'.format(*match.groups())
            new = r'{}="/{}"'.format(match.groups()[0], os.path.join(match.groups()[1],'index.html') )
            html = html.replace(old,new)
    
    # Now make all links to the root
    html,N3 = re_intlinks.subn(r'\1="{}/\2"'.format(to_root),html)
    
    # Remove the search stuff
    out = []
    ff = False
    for line in html.split('\n'):
        if not ff and '<!-- search -->' not in line:
            out.append(line)
            continue
        
        if '<!-- search -->' in line:
            ff = True
        
        if ff and '<!-- /search -->' in line:
            ff = False

    html = '\n'.join(out)
    return html
    

def cpsym(src,dest):
    """
    symlink copy all files
    """
    
    src = os.path.normpath(src)
    dest = os.path.normpath(dest)
    
    if not os.path.exists(src):
        return
    
    for dirpath,dirnames,filenames in os.walk(src):
        rel_dirpath = os.path.relpath(dirpath,src)
        dest_dirpath = os.path.join(dest,rel_dirpath)
        mkdir(dest_dirpath,isfull=True)
    
        for filename in filenames:
            src_filename = os.path.join(dirpath,filename)
            rel_filename = os.path.relpath(src_filename,src)
            
            dest_filename = os.path.join(dest,rel_filename)
            try:
                os.symlink(src_filename,dest_filename)
            except OSError:
                pass
    
    


def mkdir(path,isfile=False,isfull=False):
    if isfile:
        path = os.path.split(path)[0]
    
    if isfull:
        full = path
    else:
        if path.startswith('/'):
            path = path[1:]
        full = os.path.join(export_path,path)
    try:
        os.makedirs(full)
    except OSError:
        pass










