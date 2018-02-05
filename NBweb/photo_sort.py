#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Tool to automatically sort photos (and other files)
based on their dates and apply jpeg rotation losslessly. Will rename to
<dest>/YYYY/YYYY-MM/YYYMMDD_HHSSMM unless otherwise specified
"""
from __future__ import division, print_function, unicode_literals, absolute_import

import os
import sys
from collections import namedtuple,OrderedDict
from datetime import datetime
import subprocess
import shlex
import shutil
import multiprocessing as mp
from functools import partial
import argparse

import piexif

if sys.version_info >= (3,):
    unicode = str
    xrange = range

def photo_sort(source_dir=None,
            dest_root='.',
            copy=False,
            fmt='%Y/%Y-%m/%Y-%m-%d_%H%M%S',
            progressive=False,
            recursive=False,
            rotate_only=False,
            thumb=None, 
            progress=True,
            group_files=False,
            **KW):
    """
    Main function. See help for more details
    group_files will group all files with the same no-extension name
    as one in the following order:
        ['.jpg','.jpeg','.png','.pdf','.tiff','.tif','.heic','.mov','.mpg','.mp4']
        
    Returns a tuple of new name and thumb name. If thumb is None, returns None.
    If creating the thumbnail failed, will return "**FAILED {error}"
    """
    assert source_dir is not None
    # Note **KW is to absorb other command line arguments
   
    mv = shutil.move if not copy else shutil.copy2 
    
    files = list_files(source_dir,recursive=recursive)
    
    if group_files: # Groups same named files by extension
        files = sort_by_ext(files)

    # Get the dates and apply rotation
    pool = mp.Pool()
    
    if progress:
        sys.stdout.write('Rotation:\n');sys.stdout.flush()
    rd = partial(rotate_date,fmt=fmt,progressive=progressive,progress=progress)
    src_rdest_groups = pool.map(rd,files)
    
    if rotate_only:
        pool.close()
        return
        
    # Apply the moves. But first make sure the file does not exist for ANY
    # of the names that may be moved
    all_dest = []
    for src_rdest_group in src_rdest_groups:
        destname0 = src_rdest_group['date']
        destname0 = destname0.strftime(fmt)
        destname = destname0
        
        safe_to_move = False
        count = 0
        while not safe_to_move:
            safe_to_move = True # Will get reset if not safe
            src_dests = []
            
            for src in src_rdest_group['source']:
                ext = fileparts(src).ext
                dest = os.path.join(dest_root,destname+ext)
                if os.path.exists(dest):
                    safe_to_move = False
                    break
                src_dests.append( [src,dest]) 
            
            # Add. Will only matter if going around again
            count += 1
            destname = destname0 + '.{}'.format(count)
        
        for src,dest in src_dests:
            try:
                os.makedirs(fileparts(dest).dirname)
            except OSError:
                pass
                
            mv(src,dest)
            all_dest.append(dest)
    
    if thumb is not None:
        thumb = int(thumb)
        if progress:
            sys.stdout.write('\nThumb:\n');sys.stdout.flush()
        mt = partial(make_thumb,size=thumb,progress=progress)
        all_thumb = pool.map(mt,all_dest)
    else:
        all_thumb = [None for _ in all_dest]
    
    pool.close()
    return [tuple(dt) for dt in zip(all_dest,all_thumb)]
            
    

def rotate_date(source,fmt='%Y/%Y-%m/%Y-%m-%d_%H%M%S',progressive=False,
                progress=False):
    """
    Apply rotatation and ascertain the new name for the item.
    
    Parameters:
    -----------
    source
        Either a source path OR a list/tuple of paths. If it is a list/tuple,
        the FIRST element is used to determine the new name and the rest are
        renamed accordingly (confilicts if the extensions aren't the same are
        handled later). Only the first element is rotated
    
    fmt ['%Y/%Y-%m/%Y-%m-%d_%H%M%S']
        The output nameing format. Conflicts are handled later
    
    progressive [False]:
        Apply jpegtran `-progressive -optimize`
    
    Returns:
    --------
    Dictionary of date and the original source files
    
    WARNINGS:
    ---------
    * If more than one file are sent but have the same extension, they will 
      over-write each other
    
    """
    source = source if isinstance(source,(list,tuple)) else [source]
    
    # Get only the first item for renames:
    source_parts = fileparts(source[0])
    
    ## dates:
    date = None
    try:
        exif = piexif.load(source_parts.absolute)
    except piexif.InvalidImageDataError:
        exif = None
    
    if exif is not None:
        try:
            date = exif['0th'][306]
            date = parse_date(date)
        except:
            pass
    
    # Date may still be string-type if it was parsed but not converted
    if not isinstance(date,datetime):
        date = None
    
    if date is None: # fallback or no exif
        stat = os.stat(source_parts.absolute)
        if hasattr(stat,'st_birthtime') and stat.st_birthtime > 0:
            date = datetime.fromtimestamp(stat.st_birthtime)
        elif hasattr(stat,'st_mtime'):
            date = datetime.fromtimestamp(stat.st_mtime)
    
    ## Apply rotation
    
    try:
        orientation = exif['0th'][274]
    except (KeyError,TypeError) as E:  
        orientation = 1
        
    new_path = os.path.join(source_parts.dirname,
                    source_parts.base_noext + '_rot' + source_parts.ext)    
    
    if progressive or not orientation == 1:
        rotation_dict = {  # These are actually flipped of what they should from trial and error
            1:'',
            6:'-rotate 90',
            3:'-rotate 180',
            8:'-rotate 270',
        }
        
        ## Apply rotatation with jpegtran.
        cmd = ['jpegtran']
        
        if progressive:
            cmd += ['-progressive','-optimize']
        
        cmd.append('-copy all')
        cmd.append(rotation_dict[orientation])
        cmd.append('-outfile')
        cmd.append(new_path)
        cmd.append(source_parts.absolute)
        cmd = shlex.split(' '.join(cmd)) # Resplit as needed
        subprocess.call(cmd) 

        # Move into the old one
        shutil.move(new_path,source_parts.absolute)
        
        if exif is not None:
            # Set tags
            exif['0th'][274] = 1
            piexif.insert(piexif.dump(exif),source_parts.absolute)
    
    ## Results!
    if progress:
        sys.stdout.write('.')
        sys.stdout.flush()
    

    return {'date':date,'source':source}


def make_thumb(src,size=1000,progress=False):
    try:
        from PIL import Image
        parts = fileparts(src)
        thumb_name = parts.abs_noext + '_sm' + parts.ext
        img = Image.open(src)
        img.thumbnail([size,size])
        try:
            img.save(thumb_name,quality=60,optimize=True)
        except IOError: # Bug in PIL
            img.save(thumb_name,quality=60)
        if progress:
            sys.stdout.write('.')
            sys.stdout.flush()
        return thumb_name
    except Exception as E:
        return "**FAILED: {}**".format(E)
        

def sort_by_ext(files,exts=['.jpg','.jpeg','.png','.pdf','.tiff','.tif','.heic','.mov','.mpg','.mp4']):
    """
    Go through all files and if there are any two files with the same
    basename they are sorted by the extensions
    """
    exts = [e.lower() for e in exts]
    def _sortkey(ext):
        ext = ext.lower()
        try:
            return exts.index(ext)
        except ValueError:
            return len(exts)   
    
    abs_exts = OrderedDefaultListDict()
    
    for file in files:
        parts = fileparts(file)
        abs_exts[parts.abs_noext].append(parts.ext)
    
    for abs_noext,extensions in abs_exts.items():
        extensions.sort(key=_sortkey)
        yield tuple(abs_noext + ext for ext in extensions)
        
    
    

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
    input = to_unicode(input)
    fmts = [ "%Y %m %d %H%M%S" , "%Y %m %d %H%M"     , "%y %m %d %H %M %S" 
             "%y%m%d%H%M%S"    , "%y%m%d %H %M"      , "%Y%m%d %H"         
             "%y%m%d %H%M"     , "%y%m%d%H%M"        , "%y%m%d"            
             "%Y%m%d %H %M %S" , "%Y %m %d %H"       , "%y %m %d"          
             "%Y%m%d %H %M"    , "%Y%m%d %H%M%S"     , "%y%m%d %H"         
             "%Y%m%d %H%M"     , "%y %m %d %H%M%S"   , "%Y%m%d%H%M"        
             "%Y%m%d"          , "%y%m%d %H %M %S"   , "%y %m %d %H"       
             "%Y %m %d"        , "%y%m%d %H%M%S"     , "%y %m %d %H %M"    
             "%y %m %d %H%M"   , "%Y %m %d %H %M %S" , "%Y%m%d%H%M%S"      
             "%Y %m %d %H %M"  ]

    if input is None:
        return None
        
    # Replace all punctuation with spaces
    for punc in ''',.:;"'!?[](){}-_@#$^&*''':
        input = input.replace(punc,' ')

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

def list_files(path,recursive=False):
    """ Generator to drill down if recursive"""
    for item in os.listdir(path):
        if item.startswith('.'):
            continue
            
        item = os.path.join(path,item)
        
        if os.path.isfile(item):
            yield item
        elif recursive:
            for subitem in list_files(item,recursive=True):
                yield subitem
                    
def fileparts(filepath):
    """
    Returns a namedtuple of:
        absolute    '/full/path/to/file.ext'
        abs_noext   '/full/path/to/file'
        dirname     '/full/path/to'
        basename    'file.ext'
        base_noext  'file'
        ext         '.ext'
        parts       ('/','full','path','to','file.ext')
    """
    FP = namedtuple('fileparts',['absolute','abs_noext','dirname','basename','base_noext',
                                 'ext','parts'])
    
    absolute = os.path.abspath(os.path.expanduser(filepath))
    if os.path.isdir(absolute):
        absolute += '/' # So the rest go as planned
    
    abs_noext,_ = os.path.splitext(absolute)
    
    dirname,basename = os.path.split(absolute)
    base_noext,ext = os.path.splitext(basename)
    
    parts = [os.path.sep] + absolute.split(os.path.sep)
    parts = tuple(p for p in parts if len(p.strip()) >0)
        
    return FP(absolute,abs_noext,dirname,basename,base_noext,ext,parts)

class OrderedDefaultListDict(OrderedDict): #name according to default
    """https://stackoverflow.com/a/43688805"""
    def __missing__(self, key):
        self[key] = value = [] #change to whatever default you want
        return value    
        
def to_unicode(txt):
    if not isinstance(txt,(unicode,str)):
        txt = txt.decode('utf8')
    return txt
    
if  __name__=='__main__':

    epilog="""\
Requirments:
    * Rotation requires jpegtran
        Should be installed by default on Linux. For macOS/BSD, see 
        http://www.phpied.com/installing-jpegtran-mac-unix-linux/
    * Exif read and write requires the 'piexif' python module
        * https://github.com/hMatoba/Piexif
        * pip install piexif
    * Thumbnail creation requires PIL or PILLOW (tested under PILLOW)

The date will be ascertained as follows:

1. Exif -- only on jpeg.
2. Createtime (if supported by file system)
3. Last modified time

All actions are use multiprocessing when appropriate to speed up.
"""

    parser = argparse.ArgumentParser(description=__doc__,epilog=epilog,formatter_class=argparse.RawDescriptionHelpFormatter)
    
    parser.add_argument('-c','--copy',action='store_true',
        help="copy files instead of move")
    parser.add_argument('-f','--fmt',default='%Y/%Y-%m/%Y-%m-%d_%H%M%S',
        help="['%(default)s'] Format to store images relative to the dest")
    parser.add_argument('-g','--group-files',action='store_true',
        help=("Will group files that have the same name but different extensions together. "
              "Note that names will be based on the first item sorted in the following order: "
              "['.jpg','.jpeg','.png','.pdf','.tiff','.tif','.heic','.mov','.mpg','.mp4']. "
              "Useful for iOS live images. Grouped files *must* be in the same directory."))
    parser.add_argument('-n','--name-only',action='store_true',
        help=r"shortcut for '-f %Y-%m-%d_%H%M%S'".replace('%','%%'))
    parser.add_argument('--progressive',action='store_true',
        help="Will run jpegtran with `-progressive -optimize` on all photos")
    parser.add_argument('-r','--recursive',action='store_true',
        help="recursivly find files at SRC")
    parser.add_argument('--rotate-only',action='store_true',
        help="Just apply exif rotation. Ignore everything else")
    parser.add_argument('-t','--thumb',metavar='size',default=None,
        help="If specified, make a thumbnail with _sm before extenion. Will use 60%% quality")
    
    parser.add_argument('source_dir',help='Source directory')
    parser.add_argument('dest_root',help="Root destination. Default 'source_dir'",nargs='?',default=None)
    
    args = parser.parse_args(args=sys.argv[1:])
    
    # Some manual tweaks
    if args.name_only:
        args.fmt = '%Y-%m-%d_%H%M%S'
    if args.dest_root is None:
        args.dest_root = args.source_dir
    
    photo_sort(**vars(args))
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    
    