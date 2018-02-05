#!/usr/bin/env python
from __future__ import division,print_function,unicode_literals,absolute_import

import os,shutil
import glob
import sys
import hashlib

import multiprocessing as mp ## Uses multi-processing to speed things up for the thumbnail creation

from NBweb import utils

maxDim=1000

def photo_link(block_path,return_paths=False):
    """
    Return the link and processess the photo
    
    Returns the full HTML to the file unless return_paths=True. In that
    case, will return text-like object if not a photo (video, file, etc) OR,
    it will return a tuple. (this difference can be used to ensure it's a photo)
    """
    global mp_queue
    
    # Process: First we determine the photo's equivalent scratch path
    # (sans extension). Then, if that exists, we continue. Otherwise, we
    # try to create a link to it.
    
    scratch_photo_path0 = os.path.join(NBCONFIG.scratch_path,'_galleries',root,block_path)
    scratch_photo_path = find_path(scratch_photo_path0)

    if scratch_photo_path is None: # It isn't already there!
    
        src_photo_path = os.path.join(NBCONFIG.photo_root,root,block_path)
        src_photo_path = find_path(src_photo_path)
        
        if src_photo_path is None:
            err = "Photo does not exists or couldn't find the extension\n"
            err += 'Photo:{:s}\nFull:{:s}'.format(block_path,src_photo_path)            
            for _ in range(100):
                mp_queue.put(None)
            raise ValueError(err)

        # Follow links
        while os.path.islink(src_photo_path):
            src_photo_path = os.readlink(src_photo_path)
            if not os.path.exists(src_photo_path):
                raise ValueError("Link to photo doesn't exist")


        
        # Get the relative path to check for securty and later define the full
        # This gets redone later but oh well.
        rel_scratch_photo_path = os.path.relpath(src_photo_path,NBCONFIG.photo_root)
        
        # Security
        if '..' in rel_scratch_photo_path:
            raise ValueError('Cannot specify any photos outside the photo_root: {}'.format(block_path))
        
        scratch_photo_path = os.path.join(NBCONFIG.scratch_path,'_galleries',rel_scratch_photo_path)
        
        # Make the link!
        try:
            os.makedirs(os.path.split(scratch_photo_path)[0])
        except OSError:
            pass
        
        try:
            os.symlink(src_photo_path,scratch_photo_path)
        except OSError:
            pass
    
    ext = os.path.splitext(scratch_photo_path)[-1]
    
    rel_scratch_photo_path = os.path.relpath(scratch_photo_path,NBCONFIG.scratch_path)
        
    ## Treat different formats (though focus on jpg)
    if ext.lower() in ['.mp4','.mov']:
        return '<video controls="true" width="100%" height="60%" preload="metadata"><source src="/{:s}" type="video/mp4"></video>'.format(rel_scratch_photo_path)
    
    elif ext.lower() in ['.jpg', '.jpeg', '.jp2', '.jpx', '.gif', '.png', '.tiff', '.tff', '.bmp']:
        
        make_thumb = lambda p:'{}.thumb{}'.format(*os.path.splitext(p))
        
        # Convert all of relevant paths
        scratch_thumb_path = make_thumb(scratch_photo_path)
        rel_scratch_thumb_path = make_thumb(rel_scratch_photo_path)
        
        
        # add to the processing queue. Make the thumb from the scratch version
        mp_queue.put( (scratch_photo_path,scratch_thumb_path) )
        
        if return_paths:
            return '/'+rel_scratch_photo_path,'/'+rel_scratch_thumb_path
        
        return '[![](/{rel_scratch_thumb_path})](/{rel_scratch_photo_path})'.format(**locals())
        
    else: # Cannot tell. Just link it
        return 'File: [`{block_path}`](/{rel_scratch_photo_path})'.format(**locals())


def find_path(path):
    """
    Tries to determine the path to a real file
    """
    if os.path.exists(path):
        return path

    if path.endswith('.'):
        path = path[:-1]  # remove the '.'
    
    try:
        path0 = path
        path = glob.glob(path + '.*')
        path = [p for p in path if not p.lower().endswith('.aae')] # Special case!
        path = [p for p in path if '.thumb.' not in p]
        
        if len(path)>1:
            print('WARNING: Multiple photos match for {}'.format(path))
        return path[0]
    except IndexError:
        pass

def thumb_img(src,thumb):
    """
    Makes a thumnail if it doesn't already exist
    """
    from PIL import Image # lazy imports
    if os.path.exists(thumb):
        return
    img = Image.open(src)
    img.thumbnail([maxDim,maxDim])
    img.save(thumb,quality=60,optimize=True)
    del img # maybe help free up memory. Shouldn't be needed though
 
def mp_worker(mp_queue):
    """
    mulit-processing worker to call thumb_img()
    """
    while True:
        info = mp_queue.get()
        if info is None: 
            break
        src,thumb = info
        thumb_img(src,thumb)  
        # No outgoing queue since we do not need the results

def photo_parse(filetext,meta,NBCONFIG_):
    """
    Usage:
        filetext = photo_parse(filetext,meta,NBCONFIG)
    """
    
    global NBCONFIG
    global root
    global mp_queue

    NBCONFIG = NBCONFIG_
    if 'root' not in meta:
        raise ValueError('Must specify a root in the metadata for galleries')
    root = meta['root']
    if root.startswith('/'):
        root = root[1:]
    
    out_txt = []

    ############ Get set up for multiprocessing the photos
    Nproc = int(mp.cpu_count())
    mp_queue = mp.Queue()
    
    workers = [mp.Process(target=mp_worker, args=(mp_queue,)) for _ in range(Nproc)]
    for worker in workers:
        worker.daemon = True
        worker.start()
    ###########
    # Recombine the in_text now for later splitting

    # Now, convert it into blocks and skip the first
    blocks = [block.split(']]',1) for block in ('\n' + filetext).split('\n[[')][1:]
    
    out_txt_list = []

    for block in blocks:
        try:
            block_path,description = block
        except ValueError:
            print('ERROR: Did you miss a closing ]')
            out_txt.append('<h1>ERROR: Did you miss a closing ]</h1>')
            continue
            
        # cut leading lines on the description and trailing spaces or \n. Also cut : from the start
        while description.startswith('\n') or description.startswith(' ') or description.startswith(':'):
            description = description[1:].lstrip()
        while description.endswith('\n') or description.endswith(' '): # Should be a single loop
            description = description[:-1].rstrip()

        # Deal with block types
        block_path = block_path.strip()
        block_path = block_path.replace('|',',')

        if block_path.startswith('#'):
            continue # This is a hidden comment

        if block_path.startswith('+') or len(block_path) == 0:
            # Comment
            block_path = block_path[1:].strip()
            
            if len(block_path) >0:
                if block_path.startswith('#'):
                    description = '{:s}\n\n'.format(block_path) + description
                else:
                    description = '**{:s}**\n\n'.format(block_path) + description
            out_txt_list.append(description)
            continue

        # Otherwise it is photo or media
        
        # Is it a multi-photo?
        if ',' in block_path:
            block_paths = [b.strip() for b in block_path.split(',')]
            
            # New titles as multi line
            title_tmp = ', '.join(['**`{:s}`**    '.format(t) for t in block_paths])
            
            all_paths = [photo_link(bp,return_paths=True) for bp in block_paths]
            
            # split into tuples (images) or text (media or files)
            all_img_paths = []
            all_other_paths = []
            for p in all_paths:
                if isinstance(p,tuple):
                    # Need  to add empty alt and descirption lines
                    p = list(p)
                    p.extend(['',''])
                    all_img_paths.append(p)
                else:
                    all_other_paths.append(p)
            
            txt_tmp  = utils.html_snippet('mult_photo.html',
                                           bottle_template={
                                            'all_img_paths':all_img_paths
                                            })
            if len(all_other_paths) >0:
                txt_tmp += '\n\n' + '\n'.join(all_other_paths)

            out_txt_list.append(title_tmp + '\n\n' + txt_tmp + '\n\n' + description)
        else:
            img = photo_link(block_path)
            out_txt_list.append('**`{:s}`**\n\n'.format(block_path) + img + '\n\n' + description)


    out_txt = '\n'.join(out_txt) + '\n\n' + '\n\n-----\n\n'.join(out_txt_list)
    
    out_txt = out_txt.replace('\n\[','\n[') # Fix escaped characters
    
    ############ Cleanup from multi-processing
    for _ in range(Nproc): # This sentinel kills the workers
        mp_queue.put(None)
    for worker in workers: # Let them all finish      
        worker.join()
    mp_queue.close()
    ###########
    
    return out_txt


























