#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Main web application
"""
from __future__ import division, print_function, unicode_literals, absolute_import

# std lib
import os
import sys
from collections import OrderedDict
import functools
from functools import wraps
import glob
import re
import json
from datetime import datetime
import time
import random
from io import open
import unicodedata
import shutil
from threading import Thread
import subprocess
import gc
import logging
import sqlite3
import hashlib

# 3rd party

from bottle import route,run,static_file,request,redirect,\
    response,install,hook,error,abort
import bottle


# walk with scandir vs listdir
if sys.version_info >= (3,5):
    walk = os.walk
    scandir = os.scandir
    _scandir = True
else:
    try:
        from scandir import walk
        from scandir import scandir
        _scandir = True
    except ImportError:
        walk = os.walk
        _scandir = False


# Python Compatability
if sys.version_info[0] >= 3:
    unicode = str
    xrange = range


# part of NBweb
from . import utils
from .utils import html_snippet
from . import todo_tags
from . import search
from . import bottlesession
from .photo_sort import photo_sort
from .photo_parse import photo_parse

FORMATS = {
    'img':[".bmp",".eps", ".gif", ".jpe", ".jpeg", ".jpg",
           ".png", ".tif", ".tiff"],
    'video':['.mp4','.mov'],
}

# All config files and inject settings
import NBCONFIG

NBCONFIG.extensions = [a.lower() for a in NBCONFIG.extensions]
NBCONFIG.exclusions = list(set(NBCONFIG.exclusions + ['.git/','.svn/','.*','_*']))
USERS = NBCONFIG.edit_users.copy()
USERS.update(NBCONFIG.protected_users)
REQUIRELOGIN = len(USERS) > 0
NBCONFIG.FORMATS = FORMATS



with open(utils.join(NBCONFIG.source,'_NBweb/template.html'),encoding='utf8') as F:
    template = F.read()

try:
    os.makedirs(utils.join(NBCONFIG.scratch_path,'sessions'))
except:
    pass

# Logins
session_manager = bottlesession.JSONSession(session_dir=utils.join(NBCONFIG.scratch_path,'sessions'))
if REQUIRELOGIN:
    authenticate = bottlesession.authenticator(session_manager,login_url='/_login')
else:
    authenticate = lambda:lambda b:b # Wrapper that does nothing

## set up the logger
logger = logging.getLogger('myapp')
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler('NBweb.log')
formatter = logging.Formatter('%(msg)s')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)


## GLobal re
re_tags = re.compile('tt_(.+?)[\W$]',re.UNICODE) # This will *not* catch last line but we add spaces upon read
re_todo = re.compile('[\*|-] \[ \] (.+)')
re_links = re.compile('href="(.+?)"',re.IGNORECASE)

        # ('id','int'),         ### id is TEMP. Will remove later and use rowid
SCHEMA = [('systempath', 'text'),
          ('rootname', 'text PRIMARY KEY'),
          ('rootdirname', 'text'),
          ('rootbasename', 'text'),
          ('ext', 'text'),
          ('basename', 'text'),
          ('mtime', 'real'),
          ('meta_date', 'text'),
          ('meta_title', 'text'),
          ('meta_tags', 'text'),
          ('meta_id','text'),
          ('meta_other', 'text'),
          ('ref_name', 'text'),
          ('draft', 'int'),
          ('todo', 'text'),
          ('tags', 'text'),
          ('blog_date', 'text'),
          ('blogged', 'int'),
          ('html', 'text'),
          ('outgoing_links', 'text'),
          ('stext', 'text'),
          ('meta_draft', 'text')]

################### Parsing
# Define markdown parser. Also inject it into NBCONFIG
MD = utils.mmd_(automatic_line_breaks=NBCONFIG.automatic_line_breaks)
NBCONFIG.MD = MD

# Parsing
def parse_all(reset=False):
    db = db_conn()

    count = 0

    rootnames = set()
    for dirpath, dirnames, filenames in walk(NBCONFIG.source):
        # directory exclusions
        for dirname in dirnames[:]: # Loop over copy
            rootname = get_rootname(dirpath,dirname)
            if exclusion_check(rootname,isdir=True):
                dirnames.remove(dirname)

        for filename in filenames:
            rootname = get_rootname(dirpath,filename)
            if exclusion_check(rootname,isdir=False):
                continue
            rootnames.add(rootname) # Track all rootnames to handle deletions

            systempath = utils.join(dirpath,filename)
            item = parse_path(systempath,db,commit=False,force=reset)
            if item is not None and not item['cached']:
                count += 1
                txt = 'Proc {}'.format(count)
                sys.stderr.write('\r%s' % txt)
                sys.stderr.flush()

    # Purge deleted files from the DB
    rootnames_DB = set(item['rootname'] for item in
                    db.execute('SELECT rootname FROM file_db'))

    for deleted_rootname in (rootnames_DB - rootnames):
        cursor = db.cursor()
        cursor.execute('''DELETE FROM file_db WHERE
                          rootname=?''',[deleted_rootname])
        cursor.close()

    db.commit()
    db.close()

    # Explicitly clear some variables (just to be safe)
    #del DB
    del rootnames_DB
    del rootnames
    gc.collect()
    print('')

def parse_path(systempath,db,commit=True,force=False):
    """
    Parse and add to the DB. systempath should the *system* path of the file

    Returns the DB entry so that you do not need to reparse it later
    """
    if not os.path.exists(systempath):
        # Even if it is in the DB, this check comes first
        raise ValueError('path {} does not exists'.format(systempath))

    parts = utils.fileparts(systempath,root=NBCONFIG.source)

    if parts.ext not in NBCONFIG.extensions:
        return

    # Shouldn't happen but just in case
    if exclusion_check(parts.rootname,isdir=False):
        return

    mtime = os.path.getmtime(systempath)

    found = db.execute('SELECT * FROM file_db where rootname=?',(parts.rootname,)).fetchall()
    if len(found) == 1:
        if not force and abs( found[0]['mtime'] - mtime ) <= 1:
            found[0]['cached'] = True
            return found[0]
    elif len(found) > 1:
        print('ERROR: Duplicate entry for {}. Removing all'.format(parts.rootname))
        db.execute('''DELETE FROM file_db WHERE
                          rootname=?''',[parts.rootname])
        db.commit() # Commit no matter what
        return parse_path(systempath,db,commit=commit)


    item = OrderedDict()

    # Paths
        # systempath = '/path/to/notebook/source/subdir/page1.md'
        # root = '/path/to/notebook/source'
    item['systempath'] = systempath             # /path/to/notebook/source/subdir/page1.md
    item['rootname'] = parts.rootname           # /subdir/page1.md
    item['rootdirname'] = parts.rootdirname     # /subdir
    item['rootbasename'] = parts.rootbasename   # /subdir/page1
    item['ext'] = parts.ext                     # .md
    item['basename'] = parts.basename           # page1

    item['mtime'] = mtime

    # Get the actual text
    filetext,meta = utils.parse_file(systempath)

    if parts.ext == '.gallery':
        filetext = photo_parse(filetext,meta,NBCONFIG)

    # Store the metadata as meta_key for allowed keys
    meta_keys = ['title','date','tags','draft','id'] # everything else will be stored as one entry
    meta_other = dict()
    for key,value in meta.items():
        if key in meta_keys:
            if isinstance(value,(str,unicode)):
                item['meta_'+key] = value
            elif isinstance(value,(set,tuple,list)):
                item['meta_'+key] = ','.join(value)
            else:
                item['meta_'+key] = repr(value)
        else:
            meta_other[key] = value
    item['meta_other'] = json.dumps(meta_other)

    # Reference Name
    if NBCONFIG.ref_type.lower() == 'path':
        item['ref_name'] = os.path.split(item['rootname'])[-1]
    elif NBCONFIG.ref_type.lower() == 'title':
        item['ref_name'] = item['meta_title']
    elif NBCONFIG.ref_type.lower() == 'both':
        n = item['meta_title']
        p = os.path.split(item['rootname'])[-1]
        item['ref_name'] = '{n} ({p})'.format(n=n,p=p)

    # Add "[DRAFT]" to both the title and the ref_name if draft. Note this
    # is done *after* reference name is calculated so it isn't duplicated
    item['draft'] = item.get('meta_draft','false').lower().strip() in ['true','yes','1']
    if item['draft']:
        item['meta_title'] = '[DRAFT] {:s} [DRAFT]'.format(item['meta_title'])
        item['ref_name'] = '[DRAFT] {:s} [DRAFT]'.format(item['ref_name'])
    if 'meta_draft' in item:
        del item['meta_draft'] # No need to keep this key in the DB

    # Todo
    todos = []
    for il,line in enumerate(filetext.split('\n')):
        for todo in re_todo.finditer(line):
            todos.append( {'line':il+1+meta['meta_line_offset'],
                            'text':todo.group(1).strip()} )
    if len(todos) > 0:
        item['todo'] = json.dumps(todos)
    else:
        item['todo'] = None

    # Tags: both from the text (re) and from the meta
    tags = item.get('meta_tags','').split(',') + re_tags.findall(filetext)
    item['tags'] = ','.join(tags) # Save as single string

    # Check for special properties
    item['blog_date'] = None
    item['blogged'] = False
    if utils.patterns_check(parts.rootname,patterns=NBCONFIG.blog_dirs):
        date = utils.parse_date(item.get('meta_date','')) # Must have a date
        if date is not None:
            item['blog_date'] = time.mktime(date.timetuple())
            item['blogged'] = True

    ## Process to HTML
    #item['md'] = filetext
    item['html'] = MD(filetext)

    # Make all relative links absolute (can be undone later)
    item['html'] = utils.convert_relative_links(parts.rootname,item['html'])

    # Note that at this point, outgoing_links will ALL be absolute
    # Make them end in .html
    
    item['html'],outgoing_links = utils.convert_internal_extension(\
                                    item['html'],extensions=NBCONFIG.extensions,\
                                    return_links=True)

    item['outgoing_links'] = ','.join(outgoing_links)
    item['stext'] = utils.clean_for_search(item['html'])

    # Either insert or update

    item_list = [item.get(key[0],None) for key in SCHEMA]    # Items to be inserted

    cursor = db.cursor()
    if len(found) == 0: # new
        qmarks = '(' + ','.join('?' for _ in item_list) + ')' # (?,?,...,?)
        cursor.execute("""INSERT INTO file_db VALUES """ + qmarks,item_list)
    else:
        qmarks = ','.join('{}=?'.format(key[0]) for key in SCHEMA) # key1=?,key2=?,...
        item_list.append(item['rootname'])
        cursor.execute("""UPDATE file_db
                          SET {qmarks}
                          WHERE rootname=?""".format(qmarks=qmarks),item_list)
    if commit:
        db.commit()

    item['cached'] = False # Not in the DB but useful
    return item


################### Web Helpers
def dir_listings(rootname,db,show_empty=False,drafts=False):
    """
    Get a listing of dir items. End folders with '/' and are only
    included if they have sub items
    """

    systemname = get_systemname(rootname) # Will end with '/' if dir
    if systemname is None or not systemname.endswith('/'):
        return

    def has_subitems(systemdirname):
        if not systemdirname.endswith('/'):
            systemdirname = systemdirname + '/'

        query = """SELECT * from file_db WHERE systempath LIKE ?"""
        if not drafts:
            query += ' AND draft=0'

        sub = db.execute(query,(systemdirname + '%',)).fetchone()
        return sub is not None and len(sub)>0

    res = ['<p><a href="{}"><strong>All Sub Pages</strong></a></p>'.format( utils.join('/_all',strip_leading(rootname)) ) ]
    res.append('<ul>')

    if not (rootname == '' or rootname == '/'):
        res.append('<li><a href="../">⇧ <code>../</code></a></li>')

    if _scandir:
        items = [ (item.path,item.is_dir()) for item in scandir(systemname) ]
    else:
        items = [ (utils.join(systemname,item),os.path.isdir(utils.join(systemname,item))) for item in os.listdir(systemname)]

    listings_files = []
    listings_dirs = []
    
    for sub_systempath,isdir in items:
        if not isdir:
            if exclusion_check(get_rootname(sub_systempath)):
                continue
            fitem = parse_path(sub_systempath,db)
            if fitem is None:
                continue

            if not drafts and fitem['draft']:
                continue

            if fitem['basename'] == 'index':
                continue

            txt = '<li><a href="{rootbasename}.html">{ref_name}</a></li>'.format(**fitem)
            
            if NBCONFIG.sort_type == 'title':
                sortname = fitem['meta_title'].lower()
            elif NBCONFIG.sort_type == 'path':
                sortname = os.path.basename(sub_systempath).lower() # Default
            elif NBCONFIG.sort_type == 'ref':
                sortname = fitem['ref_name'].lower()
            else:
                raise ValueError('no valid sort_type')
                
            listings_files.append((sortname,txt))
        

        elif has_subitems(sub_systempath) or show_empty:
            rootname = get_rootname(sub_systempath)
            name = os.path.split(rootname)[-1]
            txt = '<li><a href="{rootname}/"><small>▶</small> {name}/</a> -- <a href="/_all{rootname}"><strong>All Sub Pages</strong></a></li>'.format(rootname=rootname,name=name)
            sortname = os.path.basename(sub_systempath).lower()
            listings_dirs.append((sortname,txt))
    
    if NBCONFIG.dirs_on_top:
        res.extend(i[1] for i in sorted(listings_dirs))    
        #res.append('<hr></hr>')
        res.extend(i[1] for i in sorted(listings_files))
    else:
        res.extend(i[1] for i in sorted(listings_dirs + listings_files))    
    

    res.append('</ul>')
    return '\n'.join(res)


def get_blog_page(num,db,drafts=False):
    """
    Get the blog page number as a list of items

    Also return if this is the end.
    """
    if drafts:
        draft_sql = ""
    else:
        draft_sql = "AND draft=0"

    Npp = 8

    # Note that we request an additional 5 per page. What this does is
    # (a) leave room for deleted files and (b) let us know that if we get
    # <= Npp, we're at the end! (ex: if there are Npp=8 and we only get <=8,
    # despite requesting >8, we are at the end)
    blog_list = db.execute("""
        SELECT *
        FROM file_db
        WHERE blogged=1
        {draft_sql}
        ORDER BY -blog_date
        LIMIT ?
        OFFSET ?""".format(draft_sql=draft_sql),(Npp+5,num*Npp)).fetchall()

    is_end = len(blog_list) <= Npp

    # Filter to make sure it still exists. We do NOT delete from the DB here
    # for speed. Will get removed on next parse_all
    # If there too many any deleted, it will show less than Npp per page.
    # (extreme edge case)
    blog_list = [item for item in blog_list if os.path.exists(item['systempath'])]

    return blog_list[:Npp],is_end

def get_all_page(name,db,is_systemname=False,drafts=False):
    """
    Get a list of items in a directory
    """

    if is_systemname:
        systemname = name
        rootname = get_rootname(systemname,auto_abort=True)
    else:
        rootname = name
        systemname = get_systemname(name,auto_abort=True)

    if exclusion_check(rootname):
        return []

    ## Allow full recursion with '?recursive=true'. Not enabled at the moment
    if False and request.query.get('recursive','') == 'true':
        # Get login and session
        logged_in,session = check_logged_in()
        if session.get('name','') in NBCONFIG.edit_users:
            return db.execute('SELECT * from file_db WHERE rootname LIKE ? ORDER BY LOWER(rootname)',[os.path.join(rootname,'%')]).fetchall()

    if _scandir:
        item_list = (p.path for p in scandir(systemname) if not p.is_dir())
    else:
        item_list = (utils.join(systemname,p) for p in os.listdir(systemname))
        item_list = (p for p in item_list if not os.path.isdir(p))

    item_list = (parse_path(p,db) for p in item_list) # Will be None if not allowed
    item_list = (p for p in item_list if p is not None)
    if not drafts:
        item_list = (p for p in item_list if not p['draft'])

    # Finally, sort it (which will make it a list)
    return sorted(item_list,key=lambda a:a['rootname'].lower())

def cross_ref(item,db):
    """
    Returns the cross ref html for a page
    """
    crossref = []

    outgoing = set()
    for link in item['outgoing_links'].split(','):
        link = link.strip()
        if link == '': 
            continue
            
        # ID links
        if link.startswith('/_id/'):
            linkid = link[5:]
            # Get the first item with the ID. 
            match = db.execute("""  SELECT rootbasename 
                                    FROM file_db 
                                    WHERE meta_id=?""",(linkid,)).fetchone()
            if match is None:
                print('\nBroken link:\n to: {}\n in: {}'.format(link,item['rootbasename']))
                continue
            link = match['rootbasename'] + '.html'
        
        outgoing.add(link)
    
    outgoing = sorted(outgoing,key=lambda a:a.lower())

    if len(outgoing) > 0:
        crossref.append('<p>Outgoing:</p>\n<ul>')
        for out in outgoing:
            rootbasename = os.path.splitext(out)[0]
            subitem = db.execute('SELECT rootbasename,ref_name FROM file_db WHERE rootbasename=?',(rootbasename,)).fetchone()
            if subitem is None or len(subitem)==0:
                print('\nBroken link:\n to: {}\n in: {}'.format(out,item['rootbasename']))
                continue
            crossref.append('<li><a href="{rootbasename}.html">{ref_name}</a></li>'.format(**subitem))
        crossref.append('</ul>\n')
    
    # Query for all incoming links. All `outgoing_links` DB column are *full*
    # paths. Note that the SQL query can be fooled since it is a 
    # `LIKE %/link/to/me% query so anything starting with it will come up.
    # We check for that later. If this current item does not have an ID, use
    # some junk
    idquery = item.get('meta_id')
    if idquery is None or len(idquery) == 0:
        idquery = utils.randstr(50)
    else:
        idquery = '/_id/' + idquery
    
    incoming = db.execute("""
            SELECT * FROM file_db 
            WHERE outgoing_links LIKE ? 
            OR outgoing_links LIKE ?
            ORDER BY rootbasename""",
            ('%' + item['rootbasename'] + '.%','%' + idquery + '%')).fetchall() 
            
    if len(incoming) > 0:
        crossref.append('<p>Incoming:</p>\n<ul>')
        for subitem in incoming:
            if subitem['draft']:
                # Get login and session
                logged_in,session = check_logged_in()
                is_edit_user = session.get('name','') in NBCONFIG.edit_users
                if not is_edit_user:
                    continue
            
            # Make sure that it *actually* links to this page and not something 
            # that starts the same (see note above)
            subitem_outgoings = subitem['outgoing_links'].split(',')
            found = False
            for subitem_outgoing in subitem_outgoings:
                if subitem_outgoing == idquery: # Compare ID
                    found = True
                    break
                # compare the base of the outgoing link to rootbasename
                if os.path.splitext(subitem_outgoing)[0] == item['rootbasename']:
                    found = True
                    break
            if not found:
                continue

            crossref.append('<li><a href="{rootbasename}.html">{ref_name}</a></li>'.format(**subitem))
        crossref.append('</ul>\n')
    return '\n'.join(crossref)

################## Authentication web routes

@route('/_login',method=['get','post'])
@route('/_login/',method=['get','post'])
@route('/_login/<path:path>',method=['get','post'])
def login(path=None):
    """
    Login. Use  @authenticate decorator for a given path
    or call this function with a path to redirect to that path
    """
    if path is None: # for @authenticate decorator
        path = request.get_cookie('validuserloginredirect', '/')

    # Check if already logged in and valled
    logged,session = check_logged_in()
    if logged:
        redirect(utils.join('/',path)) # SUCCESS!

    if request.method == 'GET':

        if NBCONFIG.https_login and request.get_header('X-Forwarded-Proto', 'http') == 'http':
            url = request.url.replace('http://', 'https://', 1)
            redirect(url)

        toptxt = "<p>Login:</p>"
        if request.query.get('failed',default='false').lower() == 'true':
            toptxt = "<p>Login Failed. Try again</p>"

        if hasattr(NBCONFIG,'protected_comment'):
            toptxt += NBCONFIG.protected_comment

        content = html_snippet('login_body.html').format(toptxt=toptxt,path=path)
        item = {'html':content,'title':'Login'}
        return fill_template(item)

    else:
        username = request.POST.get('username').lower()
        password = salthash(request.POST.get('password'))
        if USERS.get(username,'_') ==  password:
            session['valid'] = True
            session['name'] = username

            remember = request.POST.get('remember','no') == 'yes'
            if remember:
                session['expire'] = time.time() + 86400 * 15 # 15 days
            else:
                session['expire'] = time.time() + 600 # 10 min

            session_manager.save(session)
            redirect(utils.join('/',path)) # SUCCESS!
        else:
            session['valid'] = False
            session_manager.save(session)
            if path == '/':
                redirect('/_login?failed=true')
            redirect(utils.join('/_login/',path + '?failed=true')) # Fail!

def check_logged_in():
    """
    Use this to check if already logged in
    """
    # Check if it is a valid session. Sessions are stored locally so this
    # shouldn't be something a user could fake.
    if not REQUIRELOGIN:
        return (True,dict())

    session = session_manager.get_session()

    if session['valid'] and session.get('expire',0) > time.time():
        return (True,session)
    return (False,session)

@route('/_logout')
@route('/_logout/')
@route('/_logout/<path:path>')
def logout(path='/'):
    session = session_manager.get_session()
    session['valid'] = False
    session_manager.save(session)
    redirect(utils.join('/',path))

@route('/_logstat')
def logstat():
    logged,session = check_logged_in()
    txt = []
    txt.append('logged: {}'.format(logged))
    txt.append(' session: {}'.format(json.dumps(session)))
    response.content_type = 'text/text; charset=UTF8' # Just raw text
    return '\n'.join(txt)

@route('/_gc')
def run_gc_web():
    """
    Run garbage collection and display memory before and after. NOT perfect
    and will show if more than one NBweb is running at a time
    """
    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect('/_login/_gc') # Shouldn't get here w/o being logged in but just in case
    elif session.get('name','') not in NBCONFIG.edit_users:
        abort(401)


    cmd = 'ps -u {} -o rss,etime,pid,command|grep {} |grep -v grep'.format(os.environ['USER'],NBCONFIG.source)
    response.content_type = 'text/text; charset=UTF8' # Just raw text
    p1 = subprocess.check_output(cmd,shell=True)
    yield utils.to_unicode(p1) + '\n'
    gc.collect()
    p2 = subprocess.check_output(cmd,shell=True)
    yield utils.to_unicode(p2) + '\n'

def run_gc_thread():
    """
    run garbage collection every 5 minutes

    WARNING: This *must* be started as a targe to a daemon thread.
             Otherwise, it will run forever
    """
    while True:
        gc.collect()
        time.sleep(5*60)

################### Management web routes

@route('/_refresh')
def refresh(wait=''):
    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect('/_login/_refresh') # Shouldn't get here w/o being logged in but just in case
    elif session.get('name','') not in NBCONFIG.edit_users:
        abort(401)

    yield "<p>Refreshing Index...</p>"
    parse_all()
    yield "<p>...Done</p>"
    txt = utils.html_snippet('JS_forward.html')
    yield txt.replace('DEST','/')

@route('/_bashcmd',method='POST')
def bashcmd():
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect('/_login/_git_pcp') # Shouldn't get here w/o being logged in but just in case
    elif session.get('name','') not in NBCONFIG.edit_users:
        abort(401)

    # get the ID. It is the *only* POST item and is 'cmdN'
    ID = list(request.POST.keys())[0]
    ID = int(ID[3:])

    cmd = ['# Set by NBweb',
           'cd {}'.format(NBCONFIG.source)]
    name,cmd1 = NBCONFIG.bashcmds[ID]

    cmd.append('')
    cmd.append('# set by config')
    cmd.append(cmd1)

    cmd = '\n'.join(cmd).split('\n') # Split up \n inside commands

    html = ''
    html += '<p>CMD {}: {}</p>'.format(ID,name)
    html += '<pre><code>' + '\n'.join('$ ' + utils.html_escape(l) for l in cmd) + '</code></pre>'

    yield fill_template({'title':name,'html':html},special=True)

    proc = subprocess.Popen('\n'.join(cmd),shell=True,stderr=subprocess.PIPE,stdout=subprocess.PIPE)
    out,err = proc.communicate()
    out = utils.html_escape(utils.to_unicode(out))
    err = utils.html_escape(utils.to_unicode(err))

    outtxt = '\n'.join(l for l in out.split('\n')).rstrip()
    yield '<p>STDOUT:</p>\n<pre><code>' + outtxt + '</code></pre>'
    errtxt = '\n'.join(l for l in err.split('\n')).rstrip()
    yield '<p>STDERR:</p>\n<pre><code>' + errtxt + '</code></pre>'

    # save it
    dtstring = utils.datetime_adjusted(NBCONFIG.time_zone)
    dtstring = dtstring.strftime('%Y-%m-%d_%H%M%S')
    logname = os.path.join(NBCONFIG.scratch_path,'bash_logs')
    try:
        os.makedirs(logname)
    except OSError:
        pass
    logname += '/' + dtstring + '.log'
    
    with open(logname,'wt',encoding='utf8') as F:
        F.write('bashcmd: ' + dtstring + '\n')
        F.write('\n'.join('    $ ' + l for l in cmd) + '\n\n')
        F.write('STDOUT: \n\n' + '\n'.join('> ' + o for o in outtxt.split('\n')) + '\n\n')
        F.write('STDOUT: \n\n' + '\n'.join('> ' + o for o in errtxt.split('\n')) + '\n\n')
    

    final = """\
        <p>
        Logged saved in <code>{}</code>
        <p>
        <button onclick="location.href='/_refresh'" type="button">Refresh DB</button> &nbsp;
        <button onclick="location.href='/'" type="button">Home</button></p>""".format(logname)
    yield final


@route('/_')
@route('/_/')
@route('/_/<path:path>')
def fix_empty(path='/'):
    redirect(utils.join('/',path))

@route('/_new')
@route('/_new/')
@route('/_new/<rootdirname:path>')
def new(rootdirname='/'):
    newtype = request.query.get('type','file')

    rootdirname = utils.join('/',rootdirname)
    systemdirname = utils.join(NBCONFIG.source,rootdirname[1:])

    parts = utils.fileparts(systemdirname,NBCONFIG.source)

    # Redirect if it is a file
    if not os.path.isdir(systemdirname):
        newurl = os.path.dirname(rootdirname) + '?' + '&'.join('{}={}'.format(k,v) for k,v in request.query.iteritems())
        return redirect('/_new' + newurl)

    if not os.path.exists(systemdirname):
        abort(404) # The directory must exist and it must be a directory.
                   # The main_route will strip of index.html

    if newtype in ['file','photo']:
        # Send it to edit but tell edit that it is new
        return edit(rootpath=rootdirname,new=True)

@route('/_newphoto')
@route('/_newphoto/')
@route('/_newphoto/<rootdirname:path>')
def newphoto(rootdirname='/'):
    rootdirname = utils.join('/',rootdirname)
    request.query['type'] = 'photo' # force it

    systemdirname = utils.join(NBCONFIG.source,rootdirname[1:])
    if not os.path.isdir(systemdirname):
        rootdirname = os.path.dirname(rootdirname) # Just the dir

    newurl = rootdirname + '?' + '&'.join('{}={}'.format(k,v) for k,v in request.query.items())
    return redirect('/_new' + newurl)

@route('/_newdir')
@route('/_newdir/')
@route('/_newdir/<rootdirname:path>')
def newdir(rootdirname='/'):
    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect(utils.join('/_login/',rootdirname)) # Shouldn't get here w/o being logged in but just in case
    elif session.get('name','') not in NBCONFIG.edit_users:
        abort(401)

    rootdirname = utils.join('/',rootdirname)
    systemdirname = utils.join(NBCONFIG.source,rootdirname[1:])
    if not os.path.isdir(systemdirname):
        rootdirname = os.path.dirname(rootdirname)

    return utils.html_snippet('new_dir_prompt.html').replace('ROOT',rootdirname)

@route('/_newdir',method='POST')
def newdir_post(dirpath='NONE'):
     # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect('/_login/') # Shouldn't get here w/o being logged in but just in case
    elif session.get('name','') not in NBCONFIG.edit_users:
        abort(401)

    dirpath = utils.join('/',request.POST.get('newdir',''))
    systempath = os.path.normpath(utils.join(NBCONFIG.source,dirpath[1:]))

    rel = os.path.relpath(systempath,NBCONFIG.source)
    if '..' in rel:
        abort(403)

    try:
        os.makedirs(systempath)
    except OSError:
        pass

    # We also want to make an index page in case one doesn't exist.
    # This is so that the empty directory shows
    if get_systemname(utils.join(dirpath,'index')) is None:
        with open(utils.join(systempath,'index'+NBCONFIG.extensions[0]),'w',encoding='utf8') as F:
            F.write(u'')
    redirect(dirpath)

def alert(text,dest):
    """
    Return an alert with text and dest.
    """
    text = text.replace('"','\"')
    template = utils.html_snippet('alert.html')
    template = template.replace('ALERT',text).replace('DEST',dest)
    return template

@route('/_edit/',method='POST')
@route('/_edit',method='POST')
@route('/_edit/<rootpath:path>',method='POST')
def edit_post(rootpath='/'):
    """
    Save files
    """
    #response.content_type = 'text/text; charset=UTF8' # Just raw text
    #return dict(list(request.POST.items()))
    rootpath = strip_leading(rootpath)

    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect(utils.join('/_login/_edit/',strip_leading(rootpath)))
    elif session.get('name','') not in NBCONFIG.edit_users:
        return abort(401)

    new = 'filename' in request.POST # Will only be on "new" pages

    if 'cancel' in request.POST:
        redirect(utils.join('/',rootpath))

    content = utils.to_unicode(request.POST['content'])

    if new:
        filename = request.POST['filename'].strip()
        if request.POST.get('isphoto','') == 'true':
            # Content is always empty
            # Filename is based on the 1-line input.
            #   * if empty (filename will be ""), will just be the current date and time
            #   * if set, will be date and time + filename

            dtstring = utils.datetime_adjusted(NBCONFIG.time_zone)
            dtstring = dtstring.strftime('%Y-%m-%d_%H%M%S')

            filename = filename.strip()
            content = 'title: Photo: ' + filename
            if len(filename) == 0: # No file name given or just default (removed above0
                  content += dtstring

            content += '\ndate: ' + dtstring
            
            # Add an id:
            if NBCONFIG.new_media_id_string is not None:
                id_str =  '\nid: ' +  NBCONFIG.new_media_id_string.strip()
                id_str = utils.datetime_adjusted(NBCONFIG.time_zone).strftime(id_str)
                id_str = id_str.format(numeric_id=get_numeric_id())
                
                content += id_str + '\n'
                
            filename = dtstring + '_' + filename

        elif len(filename) == 0:
            _,newmeta = utils.parse_filetxt(content)
            titledict = utils.titledict(newmeta)
            filename = NBCONFIG.auto_filename.format(**titledict)
        filename = utils.clean_new_rootpath(filename)
        systemname = utils.join(NBCONFIG.source,rootpath,filename)

        if not filename.endswith(NBCONFIG.extensions[0]):
            # This happens sometime but I cannot figure out WHY???????
            sys.stderr.write("didn't have ext???\nfilename:{}\n".format(filename))
            systemname += NBCONFIG.extensions[0]
            filename += NBCONFIG.extensions[0]
    else:
        systemname = get_systemname(rootpath,auto_abort='no_404') # Will deal with most things but allow new to go
        if systemname is None:
            return return_error('Can not edit non-existant file w/o using `/_new` path')

    parts = utils.fileparts(systemname,NBCONFIG.source) # We will *only* use this now

    # Uploads
    upload_comments = 'attachment: ' + rootpath
    uploads_txt = upload_helper(comments=upload_comments,root=parts.rootdirname)
    if len(uploads_txt.strip())>0:
        content += '\n\n' + uploads_txt

    try:
        os.makedirs(utils.fileparts(systemname).dirname)
    except OSError:
        pass

    warn = None
    if new:
        systemname0 = systemname
        ii = 1
        while os.path.exists(systemname):
            base,ext = os.path.splitext(systemname)
            if ii >1:
                base = '_'.join(base.split('_')[:-1]) # Remove previous _N
            systemname = base + '_{}'.format(ii) + ext
            ii += 1
        if ii >1:
            # Note the r'' to make sure javascript is ok with it.
            A = os.path.basename(systemname0)
            B = os.path.basename(systemname)
            warn = r'\n'.join(['WARNING: cannot create a *new* file over existing',
                              ' {} --> {}'.format(A,B)])
            parts = utils.fileparts(systemname,NBCONFIG.source)


    # Clean up & save
    content = content.replace(u'\ufeff','') # Byte Order Marks
    content = content.replace('\r','') # Remove `^M` characters
    with open(systemname,'w',encoding='utf8') as F:
        F.write(content) 
    
    rootbasename = strip_leading(parts.rootbasename)

    if 'saveV' in request.POST:
        forward = utils.join('/',rootbasename + '.html')
    elif 'saveE' in request.POST:
        # Reparse the page in case it is never viewed
        parse_path(systemname,db_conn(),commit=True,force=False)
        forward = utils.join('/_edit/',rootbasename + '.html')

    ## Settings: get some of the settings and set the cookies with that value
    # Set line number cookies if it is there
    # Go back to the line
    linenumber = request.POST.get('ln','').strip()
    response.set_cookie(str('ace_pos'),linenumber,max_age=5) # 5 second cookie. Use str() since Bottle needs the corresponding for py2,3

    editsize = request.POST.get('editsize','')
    response.set_cookie(str('ace_editsize'),editsize,max_age=60)

    # Be on our way
    if warn is not None:
        return alert(warn,forward)
    redirect(forward)



@route('/_edit/<rootpath:path>')
@route('/_edit/')
def edit(rootpath='/',new=False):
    """
    This is the main edit control for both existing and new files.
    If the file is new, it will have text automatically unless it is new
    and a photos
    """
    rootpath = strip_leading(rootpath) # Just in case

    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect(utils.join('/_login/_edit/',strip_leading(rootpath)))
    elif session.get('name','') not in NBCONFIG.edit_users:
        return abort(401)

    # Editing an index page.
    if (rootpath.endswith('/') or rootpath == '') and not new:
        redirect(utils.join('/_edit',rootpath[:-1],'index'))

    # Get the system name and fix the extension if the basename already exists
    systemname = get_systemname(rootpath,auto_abort='no_404') # Will deal with most things but allow new to go
    if systemname is None and not new: # Edge case. It is a new index page. Shows with "edit" option
        if rootpath == 'index' or rootpath.endswith('/index'):
            redirect('/_new/' + os.path.dirname(rootpath) + '?newtitle=index')
        return return_error('Cannot edit a page that does not exist')

    # Handle if it is a directory
    if not new and systemname.endswith('/'):
        redirect(utils.join('/_edit/',strip_leading(rootpath),'index')) # Do not add extension

    ace = None
    item = {}

    if new:
        if request.query.get('blank','').lower() == 'true':
            filetext = ""
        else:
            filetext = utils.datetime_adjusted(NBCONFIG.time_zone).strftime(NBCONFIG.new_page_txt)
            filetext = filetext.format(numeric_id=get_numeric_id())
        item['title'] = 'New Page'
        newtype = request.query.get('type','file')
        if newtype == 'photo':
            ace = False
    else:
        parts = utils.fileparts(systemname,NBCONFIG.source) # We will *only* use this now
        # Make sure we are allowed to edit this one!
        if parts.ext not in NBCONFIG.extensions:
            #pass # - [ ] Change this if we ever want to allow edit of all
            redirect(utils.join('/',parts.rootname))

        try:
            filetext = utils.filetxt_if_txt(systemname)
        except IOError:
            abort(415)

        filetext = filetext.replace(u'\ufeff', '') # Remove BOM from windows
        item['title'] = 'Editor: ' + parts.rootname

    ## Determine if using the ace editor
    # Prioritize: 1) prev ace setting, 2) query, 3) cookie
    ace_override = request.query.get('ace',request.get_cookie(str('ace_set'),default=None))
    if ace is None and ace_override is not None  :
        if ace_override.lower() == 'true':
            ace = True
        elif ace_override.lower() == 'false':
            ace = False
        elif ace_override.lower() == 'auto':
            ace = 'auto'
        # Save it for next time
        response.set_cookie(str('ace_set'),utils.to_unicode(ace),max_age=15*60) 
            # 15 minutes then resets
        
    if ace is None: # Not set from the query
        ace = NBCONFIG.use_ace_editor

    if ace == 'auto':
        ace = True
        agent = request.headers.get('User-Agent').lower()
        if any(a in agent for a in ['iphone','android','ipad']):
            ace = False

    if new and newtype == 'photo':
        item['html'] = html_snippet('edit_newphoto_body.html').replace('{rootpath}',rootpath)
        item['head'] = html_snippet('edit_textarea_head.html')
        form = """\
        <br>
        <input type="hidden" size="50" name="content" placeholder="Default based on title and/or date" value="">
               <input type="hidden" name="isphoto" value="true">
        Title: <input type="text"   size="50" name="filename" placeholder="short description or blank. Can add more later" value="">
        """

        item['html'] = item['html'].replace('<!-- new_page_placeholder -->',form)
        item['title'] = 'New Photo'
    elif ace:
        item['html'] = html_snippet('edit_ace_body.html').replace(
                '{rootpath}',rootpath).replace(
                '{markdown}',utils.html_escape(filetext)) # Make sure markdown is last
        
        # Other settings from cookies
        linenumber = request.get_cookie(str('ace_pos'),'100000+0')
        row,col = linenumber.split('+')
        item['html'] = item['html'].replace('{linenumber_row}','{}'.format(int(row)+1))
        item['html'] = item['html'].replace('{linenumber_col}','{}'.format(int(col)+1))
        
        editsize = request.get_cookie(str('ace_editsize'),'400')
        item['head'] = html_snippet('edit_ace_head.html')
        item['html'] = item['html'].replace('{ace_editsize}',editsize)
        item['head'] = item['head'].replace('{ace_editsize}',editsize)

    else:
        item['html'] = html_snippet('edit_textarea_body.html').format(markdown=utils.html_escape(filetext),rootpath=rootpath)
        item['head'] = html_snippet('edit_textarea_head.html')


    if new and newtype != 'photo':
        # Add the additional form
        newtitle = request.query.get('newtitle','') # Only used for index pages
        form = """\
        <p>
        Page Name: <input type="text" size="50" name="filename" placeholder="Default based on title and/or date" value="{}">
        </p>""".format(newtitle)

        item['html'] = item['html'].replace('<!-- new_page_placeholder -->',form)


    return fill_template(item,special=True)

@route('/_manage',method=['POST','GET'])
@route('/_manage/',method=['POST','GET'])
@route('/_manage/<rootpath:path>',method=['POST','GET'])
@authenticate()
def manage(rootpath=''):

    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect(utils.join('/_login/_manage/',strip_leading(rootpath)))
    elif session.get('name','') not in NBCONFIG.edit_users:
        return abort(401)

    if request.method == 'GET':
        # While validation will *also* be done on post, we need to deal with
        # validating here.
        rootpath0 = rootpath
        systemname = get_systemname(rootpath,auto_abort=True)
        isdir = systemname.endswith('/')

        rootpath = get_rootname(systemname)

        # Redirect the URL to the real page extension. This isn't needed but makes
        # it more explicit
        if not strip_leading(rootpath) == rootpath0:
            redirect('/_manage/' + strip_leading(rootpath))


        content = html_snippet('manage_body.html',
                    bottle_template={'isdir':isdir,
                                     'bashcmds':NBCONFIG.bashcmds
                                     }
                             )

        warn = ['<strong>WARNING</strong>: These operations can overwrite existing files']
        if isdir:
            warn.append('<strong>WARNING</strong>: this is a directory')

        warn = '<p>' + '<br>\n'.join(warn) + '</p>'
        item = {'title':'Manage Files','html':content.format(path=rootpath,warn=warn)}
        return fill_template(item,special=True)

    ## Do the management on POST
    if 'move' in request.POST:
        src = request.POST.get('src','')
        dest = request.POST.get('dest','')

        if len(src) == 0 or len(dest) == 0:
            return return_error("ERROR: Must specify 'source' and 'dest'")

        # Get the source from systemname
        src = get_systemname(src,auto_abort=True)

        # Manually create the system name of the dest since get_systemname requires
        # the file exists. Do some security checks before and after

        if dest.startswith('_') or '/_' in dest:
            abort(403) # Cannot move to special directory!

        dest = utils.join(NBCONFIG.source,strip_leading(dest))

        if '..' in os.path.relpath(dest,NBCONFIG.source):
            abort(403)

        try:
            shutil.move(src,dest)
            redirect(utils.join('/',get_rootname(dest)))
        except IOError:
            return return_error('IOError Occurred. Make sure the destination directory exists')

    elif 'delete' in request.POST:
        path = request.POST.get('path','')
        path0 = path
        path = get_systemname(path,auto_abort=True) # Will end in a '/'

        if path.endswith('/'):
            if request.POST.get('recursive_test','') == request.POST.get('recursive_challenge',''):
                try:
                    shutil.rmtree(path)
                except OSError:
                    return return_error('OSError on recursive delete')
            else:
                try:
                    os.rmdir(path)
                except OSError:
                    return return_error('Could not delete. Was it empty? Try recursive')
            db = db_conn()
            db.execute("""DELETE FROM file_db WHERE
                          systempath LIKE ?""",[path + '%'])
            db.commit()

            # return up one more. Also remove last character even if not '/'
            uppath = utils.join('/',os.path.dirname(path0[:-1]),'..')

        else:
            if not request.POST.get('confirm','n').lower().startswith('d'):
                dest = utils.join('/_manage/',rootpath)
                msg = "Must enter 'd' into confirm box for file deletions"
                return alert(msg,dest)
            
            db = db_conn()
            if 'deletemedia' in request.POST:
                html = db.execute("""SELECT html FROM file_db
                                     WHERE rootname=?""",[path0]).fetchone()['html']
                for medialink in utils.get_media_links(html,NBCONFIG.extensions):
                    fullpath = get_systemname(medialink)
                    if fullpath is not None:
                        try:
                            os.remove(fullpath)
                        except OSError:
                            pass # may have already been deleted
            try:
                os.remove(path)
            except OSError:
                return return_error('OSError. Try again. Make sure path exists')


            db.execute("""DELETE FROM file_db WHERE
                          systempath=?""",[path])
            db.commit()
            uppath = utils.join('/',os.path.dirname(path0[:-1]))
        redirect(uppath)

@route('/_upload')
@route('/_upload/')
@route('/_upload/<rootpath:path>') # To catch ?nav stuff
def upload_get(rootpath=None):
    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect('/_login/_upload')
    elif session.get('name','') not in NBCONFIG.edit_users:
        return abort(401)

    if rootpath is not None or rootpath == '': # So that Nav always sends us here
        redirect('/_upload')

    dest_dir = utils.join('/',NBCONFIG.media_dir)
    dest_dir = os.path.join(NBCONFIG.source,dest_dir[1:])
    try:
        os.makedirs(dest_dir)
    except OSError:
        pass

    try:
        with open(os.path.join(dest_dir,'media_log.log'),'r',encoding='utf8') as F:
            prev = F.read()
    except:
        prev = '** No Photos in log **'

    content = html_snippet('upload_body.html').format(utils.html_escape('\n'+prev))

    item = {'title':'Upload Images/Media','html':content}
    item['head'] = html_snippet('upload_head.html')

    return fill_template(item,special=True)



@route('/_upload', method='POST')
def upload_post():
    # Get login and session
    logged_in,session = check_logged_in()
    if not logged_in:
        redirect('/_login/_upload')
    elif session.get('name','') not in NBCONFIG.edit_users:
        return abort(401)

    upload_helper(root='/') # These should be to the root
    redirect('/_upload')

def upload_helper(comments=None,root='/'):
    """
    Helper to handle uplods. So it may be reused by multiple routes.

    Will always save to the log with the desired comments. If comments
    are specified here, they will be used, Otherwise, it will come from
    the form `name="comments"` field.

    root specifies the current location. Must be a directory otherwise
    it will fail
    """
    sort_thumb = 'sort_thumb' in request.forms

    dest_dir = utils.join('/',root,NBCONFIG.media_dir) # NBweb local. media_dir can be relative or absolute
    dest_dir = utils.join(NBCONFIG.source,dest_dir[1:])

    tmp_path_sort   = utils.join(dest_dir,'_tmpsort')
    tmp_path_nosort = utils.join(dest_dir,'_tmpnosort')

    for tmp_path in [tmp_path_nosort,tmp_path_sort]:
        try:
            os.makedirs(tmp_path)
        except OSError:
            pass # Already exists

    uploads = request.files.getall('upload')

    has_file = False # This tells if we ever hit any uploads
    # Perform the uploads
    for upload in uploads:
        if upload.filename.startswith('.'):
            continue
        has_file = True

        tmp_path = tmp_path_nosort # Default

        name, ext = os.path.splitext(upload.filename)
        if sort_thumb and ext.lower() in FORMATS['img']: # sortable
            tmp_path = tmp_path_sort

        file_path = "{path}/{file}".format(path=tmp_path, file=upload.filename)
        upload.save(file_path)
        del upload # Some cleanup to help save memory

    del uploads

    if not has_file:
        return ''
    ########### Sort it
    txt = list()

    if sort_thumb: # Applies jpeg rotation, makes thumbnails, and sorts by exif if possible
        fmt = "%Y/%m/%Y-%m-%d_%H%M%S" if NBCONFIG.sort_year_month else '%Y-%m-%d_%H%M%S'
        OPTS = {
            'source_dir':tmp_path_sort,
            'dest_root':dest_dir,
            'fmt':fmt,
            'thumb': 1000,
            'progress':False,
            'group_files':False,
        }
        results = photo_sort(**OPTS)
        
        for result in results:                              # ˯˯˯--- relative path since result is systempaths
            res = [os.path.join('/',root,NBCONFIG.media_dir, os.path.relpath(r,dest_dir)) for r in result]
            txt.append('[![]({})]({})   '.format(res[1],res[0]))

     # Sort the remaining in tmp_path_nosort
    if NBCONFIG.sort_year_month:
        now = utils.datetime_adjusted(NBCONFIG.time_zone)
        save_path = utils.join(dest_dir,now.strftime("%Y/%m"))
    else:
        save_path = dest_dir

    try:
        os.makedirs(save_path)
    except OSError:
        pass

    for item in os.listdir(tmp_path_nosort):
        if item.startswith('.'):
            continue
        src = utils.join(tmp_path_nosort,item)
        dest = utils.join(save_path,item)

        ii = 0
        while os.path.exists(dest):
            # Add an increment
            base,ext = os.path.splitext(dest)
            dest = base + '.{}'.format(ii) + ext
            ii += 1

        shutil.move(src,dest)

        newpath = utils.join('/',os.path.relpath(dest,NBCONFIG.source))

        ext = os.path.splitext(newpath)[-1].lower()

        if ext in FORMATS['video'] and sort_thumb:
            # Make it a video
            newtext = '\n'.join(['<video controls="controls" preload="metadata">',
                                 '    <source src="{}" type="video/mp4">'.format(newpath),
                                 '</video>'])
        else:
            # Just link it
            base = os.path.split(newpath)[-1]
            newtext = utils.to_unicode('[{}]({})   '.format(base,newpath))

        txt.append(newtext)

    ## Cleanup
    for tmp_path in [tmp_path_nosort,tmp_path_sort]:
        try:
            os.rmdir(tmp_path)
        except OSError:
            pass # May not have been created

    ## Log
    if comments is None:
        comments = request.forms.get('comments','')

    logtxt = []
    logtxt.append( '='*32 + datetime.now().strftime(' %Y-%m-%d_%H%M%S'))
    logtxt.append('== {}\n'.format(comments))
    logtxt.extend(txt)
    logtxt.append('\n\n' + '='*50  + '\n')

    media_log_path = utils.join('/',NBCONFIG.media_dir,'media_log.log') # Always at the root version
    media_log_path = utils.join(NBCONFIG.source,media_log_path[1:])

    try:
        os.makedirs(os.path.dirname(media_log_path))
    except OSError:
        pass

    try:
        with open(media_log_path,'r',encoding='utf8') as F:
            prev = F.read()
    except IOError:
        prev = ''
    with open(media_log_path,'w',encoding='utf8') as F:
        F.write('\n'.join(logtxt) + '\n' + prev)

    return '\n'.join(txt)

@route('/_galleries/<ppath:path>')
def gallery_serve(ppath=''):
    """
    Serve the photos for the gallery pages
    """
    galpath = os.path.join(NBCONFIG.scratch_path,'_galleries',ppath)

    if not os.path.exists(galpath):
        abort(404)

    if '..' in os.path.relpath(galpath,NBCONFIG.scratch_path):
        abort(403)

    if os.path.isdir(galpath):
        abort(403)
    
    # Get login and session
    logged_in,session = check_logged_in()
    parts = utils.fileparts(galpath,root=NBCONFIG.source) # Will handle it differently if ends with /
    
    # Check special properties. Note: exclusions ARE allowed here
    if utils.patterns_check(parts.rootname,patterns=NBCONFIG.protectect_dirs) and not logged_in:
        redirect(utils.join('/_login/',utils.join('_galleries',ppath)))
    
    return static_file(galpath,'/')

def get_numeric_id():
    """
    Return the next numeric id that is number of pages +1 increased intil the id
    is not present
    """
    db = db_conn()   
    N = db.execute('SELECT Count(*) FROM file_db').fetchone()['Count(*)']
    N += 1
    
    def _indb(id0):
        return db.execute("""
                        SELECT rootname FROM file_db
                        WHERE meta_id=?""",(id0,)).fetchone() is not None
    # Try the next 50 then fall back
    for id0 in range(N,N+50):
        if not _indb(id0):
            break
    else: # somehow did not find a match
        for id0 in xrange(N+1): # There *must* be a match
            if not _indb(id0):
                break
        else: # I do not see how you could end up here...
            raise ValueError('Error in finding suitable id')    
    return id0
            
    
################## Main Web Routes
@route('/_search')
def return_search():
    query = request.query.get('q',default='')
    query = utils.to_unicode(query)
    content = "NBweb search engine results (beta)"
    db = db_conn()

    if len(query)>0:
        results = search.search(query,db)
        content += '\n<hr></hr>\n' + results
    item = {'title': 'Search: "{}"'.format(query),'html':content}
    db.close()
    return fill_template(item,special=True)

@route('/_todo')
@route('/_todo/')
def return_todo(txt=False):
    db = db_conn()
    todo_text,todo_html = todo_tags.todos(db)
    if txt:
        response.content_type = 'text/text; charset=UTF8' # Just raw text
        return todo_text
    item = {'title':'To Do Items','html':todo_html}
    db.close()
    return fill_template(item,special=True)

@route('/_todo/txt')
def return_todo_txt():
    db = db_conn()
    todo_text,todo_html = todo_tags.todos(db)
    response.content_type = 'text/text; charset=UTF8' # Just raw text
    db.close()
    return todo_text

@route('/_no_ref/<rootname:path>')
def stop_refresh(rootname='/'):
    redirect(utils.join('/',rootname + '?refresh=-1'))
@route('/_start_ref/<rootname:path>')
def start_refresh(rootname='/'):
    redirect(utils.join('/',rootname + '?refresh=10'))

@route('/_tags')
@route('/_tags/')
def return_tags():
    db = db_conn()
    tags_html = todo_tags.tags(db)
    item = {'title':'All Tags','html':tags_html}
    db.close()
    return fill_template(item,special=True)

@route('/_latest/')
@route('/_latest/<rootpath:path>')
def get_latest_rootname(rootpath='/'):
    systemname = get_systemname(rootpath,auto_abort=True)

    if not systemname.endswith('/'):
        return return_error('Must specify a DIRECTORY')

    t = 0.0
    latest = None

    for dirpath, dirnames, filenames in walk(systemname):
        # directory exclusions
        for dirname in dirnames[:]: # Notice we loop over a copy since we will be deleting
            rootname = get_rootname(dirpath,dirname)
            if any(dirname.startswith(i) for i in ['_','.']):
                dirnames.remove(dirname)
                continue

            if exclusion_check(rootname,isdir=True):
                dirnames.remove(dirname)
                continue

        for filename in filenames:
            rootname = get_rootname(dirpath,filename)

            if exclusion_check(rootname,isdir=False):
                continue

            ext = os.path.splitext(rootname)[-1]
            if ext not in NBCONFIG.extensions:
                continue

            mtime = os.path.getmtime(utils.join(dirpath,filename))
            if mtime > t:
                t = mtime
                latest = rootname

    redirect(utils.join('/',latest))


@route('/_all')
@route('/_all/')
@route('/_all/<rootpath:path>')
def allpage(rootpath='/'):
    """
    All page listings. Some of this is borrowed from the main_route
    """
    # Is it an index.ext page? Remove that!
    parts = utils.fileparts(rootpath)
    if parts.basename == 'index': # Folder pages. Will handle index page text later
        redirect('/_all/'+strip_leading(parts.dirname) + '/')

    # Get the systemname
    systemname = get_systemname(rootpath,auto_abort=True) # Will add '/' to end if dir


    if systemname is None:
        abort(404)

    if not systemname.endswith('/'): # In case sent to a file
        redirect(utils.join('/',rootpath))

    isdir = systemname.endswith('/')

    if isdir and not rootpath.endswith('/'): # We want directories to end with '/'
        redirect('/_all/'+ strip_leading(rootpath) + '/') # From the above, we know index.ext is removed

    parts = utils.fileparts(systemname,NBCONFIG.source)
    # Get login and session
    logged_in,session = check_logged_in()
    if utils.patterns_check(parts.rootname,patterns=NBCONFIG.protectect_dirs) and not logged_in:
        redirect(utils.join('/_login/',strip_leading(rootpath)))

    is_edit_user = session.get('name','') in NBCONFIG.edit_users

    db = db_conn()
    all_list = get_all_page(systemname,db,is_systemname=True,drafts=is_edit_user)
    db.close()

    if all_list is None:
        abort(403,'Excluded paths')

    rootbasename = utils.fileparts(systemname,root=NBCONFIG.source).rootbasename
    rootbasename += '' if rootbasename.endswith('/') else '/'

    item = {}
    item['html'] = utils.combine_html(all_list,\
                    annotate=NBCONFIG.annotate_all_page,add_date=False,show_path=True)
    item['title'] = 'All Sub Pages: ' + rootbasename
    item['breadcrumb'] = utils.bread_crumb(rootbasename,'All Sub Pages')
    return fill_template(item,special=True)


@route('/_NBweb')
@route('/_NBweb/<filepath:path>')
def config_files(filepath=''):
    if '..' in filepath:
        abort(403)

    if filepath in ['NBCONFIG.py','template.html']:
        abort(403,'Not Allowed') #return 'NOT ALLOWED'
    return static_file(filepath,utils.join(NBCONFIG.source,'_NBweb'))

@route('/_resources/<fp:path>')
def resources(fp=''):
    """
    Send resources
    """
    if '..' in fp:
        abort(403)

    resource_path = utils.join( os.path.dirname(__file__),'resources',fp)
    if not os.path.exists(resource_path):
        abort(404)

    return static_file(resource_path,'/')



@route('/_random')
def random_forward():
    db = db_conn()

    # Original
    # item = db.execute('''SELECT rootbasename
    #                      FROM file_db
    #                      ORDER BY random()
    #                      LIMIT 1''').fetchone()

    # Faster from: https://stackoverflow.com/a/32572847/3633154
    item = db.execute('''SELECT rootbasename
                         FROM file_db
                         LIMIT 1
                         OFFSET ABS(RANDOM()) %
                            MAX((SELECT COUNT(*) FROM file_db),1)''').fetchone()

    dest = item['rootbasename']
    db.close()

    ## Note: stopped using `redirect` since it messes with the history
    #        in some browsers. Using javascript instead
    #redirect(dest)
    txt = utils.html_snippet('JS_forward.html')
    return txt.replace('DEST',dest)

@route('/_sitemap')
def sitemap():
    return main_route(rootpath='/',map_view=True)

@route('/_rss')
def rss():
    # Get the base path of the site. It is everything up to "_rss" 
    url = request.url[:-len('_rss')-1] # Make sure NOT to include the trailing /
    
    # Get the last 10 blogged pages
    db = db_conn()
    pages,_ = get_blog_page(0,db,drafts=False)
    
    
    txt =  html_snippet('rss.rss',bottle_template={
                        'url':url,
                        'NBCONFIG':NBCONFIG,
                        'pages':pages,
                        'rh':utils.remove_html
                        })
    response.content_type = 'application/rss+xml' 
    return txt


@route('/_id/<meta_id:path>') # use path filter to allow *anything*
def id_forward(meta_id=None):
    """
    Find and forward to the id
    """
    if meta_id is None:
        abort(404)
    db = db_conn()
    match = db.execute("""  SELECT rootbasename 
                            FROM file_db 
                            WHERE meta_id=?""",(meta_id,)).fetchone()
    if match is None:
        abort(404)
        
    return redirect(match['rootbasename']+'.html')
    
@route('/_blog')
@route('/_blog/<blog_num:int>')
def blog(blog_num=0):
    return main_route(rootpath='/',blog_num=blog_num)
    
@route('/')
@route('/<rootpath:path>')
def main_route(rootpath='/',map_view=False,blog_num=0):
    """
    Main route for standard traffic. Handle's special routing for directories
    and forwarding for requests.

    map_view is used ONLY for the sitemap. Calling with other pages may
    not work as expected
    """
    # Is it an index.ext page? Remove that!
    parts = utils.fileparts(rootpath)
    if parts.basename == 'index': # Folder pages. Will handle index page text later
        if parts.dirname != '':
            redirect('/'+parts.dirname + '/')
        else:
            redirect('/')

    original_ext = parts.ext

    # No special pages here!
    if any(rootpath.startswith(r) for r in ['/_','_']):
        abort(403)

    # Get the systemname. Will add '/' for dir and abort if not found
    # Will also handle files vs dirs with the same base name
    systemname = get_systemname(rootpath,auto_abort=True)

    isdir = systemname.endswith('/')

    if isdir and not rootpath.endswith('/'): # We want directories to end with '/'
        redirect('/'+ rootpath + '/') # From the above, we know index.ext is removed

    parts = utils.fileparts(systemname,root=NBCONFIG.source) # Will handle it differently if ends with /

    # Get login and session
    logged_in,session = check_logged_in()
    is_edit_user = session.get('name','') in NBCONFIG.edit_users

    # Check special properties. Note: exclusions ARE allowed here
    if utils.patterns_check(parts.rootname,patterns=NBCONFIG.protectect_dirs) and not logged_in:
        redirect(utils.join('/_login/',strip_leading(rootpath)))

    # Static files
    if parts.ext not in NBCONFIG.extensions + ['.html'] and not isdir:
        return static_file(parts.rootname[1:],NBCONFIG.source)

    if not isdir and  original_ext != '.html': # Forward to the .html version
        redirect(utils.join('/',parts.rootbasename + '.html'))

    #########################################################################
    ##### I think this is no longer used since a newtype is not appended
    ##### like nav=new&newtype=dir. Now it is nav=newdir.
    ##### - [ ] Investigate cutting this
    newtype = request.query.get('newtype',default=None)
    if newtype is not None:
        page = request.query.get('page',default='')
        page = page[1:] if page.startswith('/') else page
        page = utils.join(parts.rootbasename,page)
        redirect('/_new?newtype={newtype}&page={page}'.format(\
            page=page,newtype=newtype))
    #########################################################################
    
    ## Get the db
    db = db_conn()

    ## Get the content and return
    if isdir:
        ### Blog
        if parts.rootname == '/' and len(NBCONFIG.blog_dirs) > 0 and not map_view:

            blog_items,is_end = get_blog_page(blog_num,db,drafts=is_edit_user)
            if len(blog_items) == 0:
                abort(404)
            blog_html = utils.combine_html(blog_items,annotate=False,add_date=True)

            blog_top = [] #['<h1>' + NBCONFIG.title + '</h1>']
            #blog_top.append('<p>page {}/{}</p>'.format(blog_num,Nmax-1))
            arrows = ['\n<p>']
            if not is_end:
                arrows.append('<a href="/_blog/{}">'.format(blog_num+1) + '&lt;'*4 + '</a>')# '<'*4
            arrows.append('&nbsp;'*3 + ' page {} '.format(blog_num) + '&nbsp;'*3)
            if blog_num > 0:
                arrows.append('<a href="/_blog/{}">'.format(blog_num-1) + '&gt;'*4 + '</a>')# '>'*4
            arrows.append('</p>\n')
            arrows = ' '.join(arrows)
            blog_html = '\n'.join(blog_top) + arrows + blog_html + arrows

            item = dict()
            item['html'] = blog_html
            item['title'] = '{}, page {}'.format(NBCONFIG.title,blog_num)
            db.close()
            return fill_template(item,special=True)


        ### Directory
        # is there a page for this
        indexrootname = utils.join(parts.rootdirname,'index')
        cursor = db.cursor()
        indexpage = cursor.execute("""\
                SELECT * from file_db WHERE rootname LIKE ? """,
                (indexrootname[:-1] + '%',)
            ).fetchall()
        html0 = ''
        if len(indexpage) == 1:
            html0 = indexpage[0]['html'] + '\n\n'

        item = dict()

        if request.query.get('empty',default=None) is not None:
            show_empty = request.query.get('empty',default='false').lower() == 'true'
        else:
            show_empty = NBCONFIG.show_empty
        item['html'] = html0 + dir_listings(parts.rootdirname,db,show_empty=show_empty,drafts=is_edit_user)
        item['rootbasename'] = parts.rootdirname # This will also allow for a breadcrumb
        item['rootname'] = item['rootbasename'] + ('' if item['rootbasename'].endswith('/') else '/')# For the path
        item['meta_title'] = os.path.split(parts.rootdirname)[-1]

        db.close()
        return fill_template(item,show_path=True,isdir=True)
    else:
        refresh = float( request.query.get('refresh',default=-1) )
        
        force = request.query.get('forcereload','false').lower() == 'true'
        item = parse_path(systemname,db,force=force)

        # drafts. Must be logged in as an edit_user
        if item['draft'] and not is_edit_user:
            abort(401)

        item['crossref'] = cross_ref(item,db)
        
        db.close()
        return fill_template(item,show_path=True,refresh=refresh)

@error(401)
@error(403)
@error(404)
@error(415)
@error(515) # This is my own unofficial code for unable to uniquely identify the file
@route('/_error')
@route('/_error/<code_or_text>')
def return_error(code_or_text=None):
    """
    Return error
    """
    if hasattr(code_or_text,'status'):
        code_or_text = code_or_text.status

    # additional text
    if code_or_text.strip().startswith('401'):
        code_or_text += '. Try logging in again or use an account with proper permissions'
    elif code_or_text.strip().startswith('415'):
        code_or_text += '. Cannot edit binary files'
    elif code_or_text.strip().startswith('515'):
        code_or_text = 'Unable to uniquely identify file'


    item = {'title':'ERROR'}
    item['html'] = "<p>Error: {}</p>\nMake sure you're logged in if needed".format(code_or_text)

    return fill_template(item,special=True)


################## Additional Helpers
# Helper functions that don't (directly) belong in utils (that use config)

def salthash(pw):
    pw = NBCONFIG.password_salt + ':' + pw
    hasher = hashlib.sha1()
    hasher.update(utils.to_unicode(pw).encode('utf8'))
    return hasher.hexdigest()
    


exclusion_check = functools.partial(utils.patterns_check,patterns=NBCONFIG.exclusions)

def get_systemname(*rootnames,**KW):
    """
    For a given rootname (with or without an extension), get the full system
    path. It will try to only match an extension and not the whole file.

    Edge Cases
        - A file and a directory have the same basename. Will retun the
          directory since it will first pass the exist test. Specify
          with a '.' at the end to make it continue

    Note:
        - Will ALWAYS return a directory with a trailing / so that can be used
          to save another query

    Options:
        check_rel  : [True] Make sure you are not above the source
        auto_abort : [False] Rather than raise errors, abort with the relevant
                      warning. Specify as either True or 'no_404' to do all but
                      404 errors

    Test Procedure:
        1: Exists as is
        2: Remove extension and test with ".*"

    """

    def _clean(res):
        res = res + '/' if os.path.isdir(res) and not res.endswith('/') else res

        if KW.get('check_rel',True) and '..' in os.path.relpath(res,NBCONFIG.source):
            if auto_abort:
                abort(403)
            raise ValueError('Cannot go above source path')
        return res

    auto_abort = KW.get('auto_abort',False)

    rootname = os.path.join(*rootnames).replace('//','/')
    # First try just to use the name given
    rootname = strip_leading(rootname)

    isdir = rootname.endswith('/')

    name = utils.join(NBCONFIG.source,rootname)

    # Is the full specified. This should also catch a dir with the same name
    if os.path.exists(name):
        return _clean(name)

    # try without the specific extension
    name = os.path.splitext(name)[0]
    res = glob.glob(name + '.*')
    if len(res) == 1:
       return _clean(res[0])
    elif len(res) > 1:
        if auto_abort:
            abort(515)
        raise IOError('Multiple files match. Be more specific')

    if auto_abort and not auto_abort == 'no_404':
        abort(404)
    return None # No matches


def get_rootname(*systempaths,**KW):
    """
    Return the rootname. Can specify any number of paths and it will join
    check_rel KW will check for relative paths

    Options:
        check_rel  : [True] Make sure you are not above the source
        auto_abort : [False] Rather than raise errors, abort with the relevant
                      warning
    """
    auto_abort = KW.get('auto_abort',False)

    systempath = utils.join(*systempaths)

    rootname = os.path.relpath(systempath,NBCONFIG.source)

    # check_rel is default
    if KW.get('check_rel',True) and '..' in rootname:
        if auto_abort:
            abort(403)
        raise ValueError('Cannot go above source path')

    if rootname.startswith('./'):
        rootname = rootname[2:]

    if rootname == '.':
        rootname = ''

    return '/' + rootname

def strip_leading(txt):
    while txt.startswith('/'):
        txt = txt[1:]
    return txt

re_template = re.compile('\{\{(.*?)\}\}')
def fill_template(item,refresh=None,show_path=False,special=False,isdir=False):
    """
    Inputs:
        KW: The input KW
    Options:
        Refresh
            Page refresh tome - [ ] To do

        show_path
            Whether or not to show the path to the page based on if 'rootname'
            is defined

        special
            If True, the scroll wheel will go to an absolute path
            otherwise will go to the current page. Used for non-standard
            pages

        isdir
            Additional things are added to the scroll wheel such as the "get latest"

    Fills in additional settings if they are not in KW. *optional
      | item                           | KW to fill   |
      |--------------------------------|--------------|
      | 'title' or 'meta_title'        | 'title'      |
      |                                | 'head'       |
      |                                | 'search'     |
    * | 'rootbasename' or 'breadcrumb' | 'breadcrumb' |
      |                                | 'date'       |
      | 'content' or 'html'            | 'content'    |
    * | 'crossref'                     | 'crossref'   |
    * | 'rootname'   (if show_path)    |              |

    Notes:
        * View last modified is only availible for logged in users
        * Refresh will only work for logged in users and will only be
          presented as an option for edit_users

    """

    if refresh is None:
        refresh = -1

    #### Search and scroll wheel (all under the 'search' keyword)
    item['search'] ="""\
        <form action="/_search">
        <input type="text" name="q" placeholder="Search (beta)">
        <input type="submit" name="" value="Search">
        </form>"""

    ### The scrollwheel goes with search
    logged_in,session = check_logged_in()

    scroll_items = [('','ACTIONS')] # (value="{}",txt) pairs
    new_form = '<span>&nbsp;</span>' # Empty needed b/c of span in scroll

    if logged_in and session.get('name','') in NBCONFIG.protected_users:
        if isdir:
            scroll_items.append( ('latest','Go to last-modified page'))
        scroll_items.append( ('logout','Logout') )

    elif logged_in and session.get('name','') in NBCONFIG.edit_users:
        if isdir:
            scroll_items.append( ('latest','Go to last-modified page'))
        if True or not special: # Keep as if True for now to easily undo
            # Set the new_form as buttons which will also execute a
            # "?nav=XYZ" in addition to the select. This is ok since it will
            # be appended to the end and Bottle handles multiple form values
            # as the latest. Just in case, this is considered in the "nav" 
            # routing of main_route.
            new_form = """\
            <br />
            {edit}
            New: 
            <button type="submit" name="nav" value="new">File</button>
            <button type="submit" name="nav" value="newdir">Directory</button>
            <button type="submit" name="nav" value="newphoto">Media Page</button>
            """.format(edit='<button type="submit" name="nav" value="edit">Edit</button> | ' if not special else "")
        scroll_items.append( ('manage','Manage (mv,rm)') )
        if not special: # Only want these extra on regular pages
            scroll_items.append( ('edit','Edit') )
            #scroll_items.append( ('upload','Upload (and view log)') )
            if not (refresh >1.5):
                scroll_items.append(('start_ref','Auto Refresh (10)') ) # Uses a route to send back here

        scroll_items.append( ('upload','Upload Media') )    # Upload regardless of special pages
        scroll_items.append( ('logout','Logout') )
    else:
        refresh = -1
        scroll_items.append( ('login','Login') )

    # Add the option to stop refresh in the scroll wheel
    if refresh >1.5:
        scroll_items.insert(1,('no_ref','Stop Auto Refresh') )

    wheel = '\n'.join('<option value="{0}">{1}</option>'.format(*ii) for ii in scroll_items)
    scroll = """\

        <form action="" method="GET">
            <select name="nav" id="nav" onchange="this.form.submit()">
                {wheel}
            </select><input type="submit" value="Go">
            {new_form}
        </form>
        """.format(wheel=wheel,new_form=new_form)

    item['search'] += '\n' + scroll

    item['search'] = '<!-- search -->\n' + item['search'] + '\n<!-- /search -->'

    ## Other items
    item['head'] = item.get('head','')
    item['head'] += '<link type="text/css" rel="stylesheet" href="/_resources/mult_img.css">'
        

    if refresh > 1.5: # Set a min
        item['head'] += '<meta http-equiv="refresh" content="{}" />'.format(refresh)
        # Add text. Use the 'search'
        item['search'] += """\
            \n<hr></hr>
            <p>Page set to auto refresh every {:0.2f} sec. <button onclick="location.href='?refresh=0'" type="button">Stop</button></p>
            <hr></hr>\n""".format(refresh)

    item['title'] = item.get('title',item.get('meta_title',''))
    if 'breadcrumb' not in item:
        if 'rootbasename' in item:
            item['breadcrumb'] = utils.bread_crumb(item['rootbasename'],item['title'])
        else:
            item['breadcrumb'] = '<a href="/">Home</a> &gt; '


    date = utils.parse_date(item.get('meta_date',''))
    if date is not None:
        item['date'] = date.strftime('%A, %B %d, %Y, %I:%M %p')
    else:
        item['date'] = ''

    item['content'] = item.get('content',item['html'])

    if show_path and 'rootname' in item:
        nametxt = '<p><code>{rootname}</code>\n'.format(**item)
        if item.get('meta_id') and NBCONFIG.display_page_id:
            nametxt += '<br><small><code>/_id/{meta_id}</code></small>'.format(**item)
        item['content'] =  nametxt + '</p>' + item['content']


    item['crossref'] = item.get('crossref','')
    text = template
    for key in re_template.findall(text):
        value = item.get(key,'')
        key = '{{' + key + '}}'
        if key in text:
            text = text.replace(key,unicode(value))
    return text


#################### Logging -- Useful when using CherryPy or something that
####################            doesn't emit logs
def log_to_logger(fn):
    '''
    Wrap a Bottle request so that a log line is emitted after it's handled.
    (This decorator can be extended to take the desired logger as a param.)
    
    https://stackoverflow.com/a/31093434/3633154
    '''
    @wraps(fn)
    def _log_to_logger(*args, **kwargs):
        actual_response = fn(*args, **kwargs)

        D = OrderedDict()
        D['ip']         = request.environ.get('REMOTE_ADDR',request.remote_addr)
        D['ip2']        = request.headers.get('X_FORWARDED_FOR','') # Sometimes behind CherryPy???
        D['time']       = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        D['method']     = request.environ.get('REQUEST_METHOD')
        D['uri']        = request.environ.get('REQUEST_URI',request.url)
        #D['protocol']   = request.environ.get('SERVER_PROTOCOL')
        D['status']     = response.status_code
        D['User-Agent'] = request.headers.get('User-Agent')


        #logger.info(json.dumps(D))
        logger.info(json.dumps(list(D.values()))) # Will be ordered as above but shorter

        return actual_response
    return _log_to_logger

def db_conn():
    ######## TEMP
    if NBCONFIG.DBpath.startswith('sqlite://'):
        NBCONFIG.DBpath = NBCONFIG.DBpath[9:] # Strip "sqlite://"
        if NBCONFIG.DBpath.startswith('//'):
            NBCONFIG.DBpath = NBCONFIG.DBpath[1:] # Absolute path
        elif NBCONFIG.DBpath.startswith('/'):
            NBCONFIG.DBpath = '.' + NBCONFIG.DBpath # Relative
    ######### /TEMP

    db = sqlite3.connect(NBCONFIG.DBpath)
    db.text_factory = unicode
    db.row_factory = utils.dict_factory
    return db

def init_db():
    """ Setup the schema """
    db = db_conn()
    cursor = db.cursor()

    sql = """CREATE TABLE IF NOT EXISTS file_db("""
    sql += ','.join(' '.join(s) for s in SCHEMA) + ')'

    cursor.execute(sql)
    db.commit()

#     cursor.execute("""\
#         CREATE UNIQUE INDEX IF NOT EXISTS
#         indx_rootname ON file_db (rootname)""")
#     db.commit()
    db.close()

def navwrapper(callback):
    """
    Handles ?nav= queries no matter where they are formed
    
    If the original destination starts with '/_ROUTE/path/...', it will
    strip off /_ROUTE
    
    """
    def wrapper(*args, **kwargs):
        if 'nav' in request.query:
            dest0 = request.fullpath
            if dest0.startswith('/'):
                dest0 = dest0[1:]
            
            dest = dest0.split('/') 
            if len(dest)>0 and dest[0].startswith('_'):
                del dest[0]  
            
            nav = request.query.pop('nav') # Only care about the last
            dest.insert(0,'_'+nav)
            
            # build back up.
            dest = '/'.join(dest)
            
            # rebuild the query string
            qstring = '?' + '&'.join('{}={}'.format(k,v) for k,v in request.query.allitems())
            dest += qstring
            return redirect(utils.join('/',dest))
        body = callback(*args, **kwargs)
        return body
    return wrapper
    
def start(garbage_collect=True):
    global app
    if garbage_collect:
        th = Thread(target=run_gc_thread)
        th.daemon = True # So that it will exit when we quit later
        th.start()

    app = bottle.app()
    app.install(log_to_logger)
    app.install(navwrapper)
    init_db()

    app.run(**NBCONFIG.web_server)


#     run(**NBCONFIG.web_server)


#print('-'*60);import traceback as __traceback;import sys as __sys;__traceback.print_stack();print('=+'*30);print('Embed:');from IPython import embed as __embed;__embed();__contt ='Do you want to continue? [Y]/N?\n';__v=__sys.version_info[0];__cont = input(__contt) if __v>2 else raw_input(__contt);_=__sys.exit() if __cont.lower()[0]=='n' else ''

























