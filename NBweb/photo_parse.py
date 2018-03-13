#!/usr/bin/env python
from __future__ import division,print_function,unicode_literals,absolute_import

# To Test
# X Photo
# X Photo with tags
# X Photo with tags renamed
# X video
# X video with tags
# X video with tags renamed
# X Direct block link to above photo_root
# X Direct block to symlinked above photo root

import os,shutil
import sys
import re
import fnmatch
import multiprocessing as mp ## Uses multi-processing to speed things up for the thumbnail creation
from functools import partial

if sys.version_info > (2,):
    unicode = str
    xrange = range



from . import utils
import NBCONFIG

maxDim=1000

re_tagbrackets = re.compile('\_\[.*?\](?:\.|$)')

def remove_tags(name):
    """
    Remove tags from a file name INCLUDING extension
    
    It's not perfect but it just removes any time there is a _[tag] followed
    by either a period or the end of a string. It also then make sure that
    there are NO MORE periods (to *not* capture 
    "file.name_[nontag].more_name.ext" for example)
    
    Note: also must assume the "extension" could have a tag since it may not
    be the real extension
    """        
    # Get all found tag elements
    found = re_tagbrackets.findall(name)
    
    if len(found) == 0: # None found
        return name
    
    # Only keep the *last* one (which may be the only). This allows brackets
    # in the name besides the tags
    tagtxt = found[-1]
    
    # Split it at `tagtxt` and then make sure the right does not have any
    # periods. Just to be 100% certain (repeated tags), split at the last
    a,b = name.rsplit(tagtxt,1) # ^^^ rsplit
    if any(c in b for c in ['./']):
        return name # More than just an extension follows
    
    # Recombine but we have to see if tagtxt actually ended is a "."
    if tagtxt.endswith('.'):
        a += '.'
    return a + b

    
if not hasattr(NBCONFIG,'remove_tags') or NBCONFIG.remove_tags is None:
    NBCONFIG.remove_tags = remove_tags

def photo_parse(filetext,metadata,*A):
    return PhotoGallery(filetext,metadata).out_txt

class PhotoGallery:
    def __init__(self,filetext,metadata):
        """
        Main function to create the gallery
        """
        self.metadata = metadata
        
        if 'root' not in metadata:
            raise ValueError('Must specify a root in the metadata for galleries')
        self.root = metadata['root']
        if self.root.startswith('/'):
            self.root = self.root[1:]
    
        self.out_txt = []
        self.blocks_raw = [block.split(']]',1) for block in ('\n' + filetext).split('\n[[')][1:]
        
        self.blocks_processed = []
        self.thumb_queue = [] # will be populated later

        self.proc_blocks() # will populate blocks_processed
    
        if len(self.thumb_queue) > 0:
            N = len(self.thumb_queue)
            pool = mp.Pool(  min(N,mp.cpu_count(),16) )
            
            chunksize = max(N//(5*pool._processes),1) 
            for n,_ in enumerate(pool.imap_unordered(thumb_img,self.thumb_queue,chunksize=chunksize)):
                sys.stdout.write('\r{:10d}/{:d}'.format(n+1,N))
                sys.stdout.flush()
            print('')
            
            pool.close()
        
        self.out_txt =  '\n\n-----\n\n'.join(self.blocks_processed)
        self.out_txt = self.out_txt.replace('\n\[','\n[') # Fix escaped characters
    
    def proc_blocks(self):
        for block in self.blocks_raw:
            try:
                block_path,description = block
            except ValueError:
                print('ERROR: Did you miss a closing ]')
                out_txt.append('<h1>ERROR: Did you miss a closing ]</h1>')
                continue
        
            # Special case for [[photo_names[tag]]]
            if description.startswith(']'):
                block_path += ']'
                description = description[1:]
        
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
                self.blocks_processed.append(description)
                continue

            # Otherwise it is photo or media
        
            # Handle the same way for multiphoto or regular
        
            # Split it up on commas but handle if inside of a "[tag,tag]" (https://stackoverflow.com/a/38748250)
            block_paths = [b.strip() for b in re.split(',(?![^\(\[]*[\]\)])',block_path) if len(b.strip())>0]
        
            # New titles as multi line
            title_tmp = ', '.join(['**`{:s}`**    '.format(t) for t in block_paths])
        
            all_paths = [self.photo_link(bp) for bp in block_paths]
        
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

            self.blocks_processed.append(title_tmp + '\n\n' + txt_tmp + '\n\n' + description)


    def photo_link(self,blockpath):
        """
        Creates the link for a given block path and returns:
            * string with html for files and/or media
            * (main,thumb) tuples 
        where all links are the final link paths (start with /_galleries)
        """
        # Consider:
        #   photo_root = '/fs/path/to/photoroot'
        #   gallery_root (root) = 'p2/gallery
        #   blockpath = 'bp/photo_[tag1,tag2].jpg'
        # We want to return the following:
        #   main  = '/_galleries/p2/gallery/bp/photo.jpg
        #   thumb = '/_galleries/p2/gallery/bp/photo.thumb.jpg
        # and will also have:
        #   main_fs  = '/fs/path/to/photoroot/_galleries/p2/gallery/bp/photo.jpg
        #   thumb_fs = '/fs/path/to/photoroot/_galleries/p2/gallery/bp/photo.thumb.jpg   
        
        ## Filter the blockpath
        blockpath0 = blockpath
        blockpath = NBCONFIG.remove_tags(blockpath).lower()  # filter the tag name
        dirname,base,ext = fileparts(blockpath) # split
        
        # These are the final paths but they may not have an extension
        _ = os.path.join('/_galleries',self.root,blockpath)
        main = os.path.normpath(_).lower()
        thumb = '{}.thumb{}'.format(*os.path.splitext(main)).lower()

        # fs -- filesystem paths. Actual paths on the system
        main_fs = os.path.normpath(os.path.join(NBCONFIG.scratch_path,main[1:]))
        thumb_fs = os.path.normpath(os.path.join(NBCONFIG.scratch_path,thumb[1:]))
        
        
        # Security check (will check again if needed). Make sure cannot be above photo_root
        if not main_fs.startswith(os.path.join(NBCONFIG.scratch_path,'_galleries')):
            raise ValueError('Cannot go above the photo_root')
        
        # Make sure there is the symlinked file at main_fs AND
        # it is valid
        new_ext = self.make_filelink(main_fs,blockpath)
        
        if ext != new_ext : 
            # Edge case: Could have been name.ext --> name.ext.ext but
            # this will not really make a difference since the file will
            # just be stored by the new name
            ext = new_ext
            main_fs += new_ext
            main += new_ext
            thumb_fs += new_ext
            thumb += new_ext
        
        if ext.lower() in ['.mp4','.mov']:
            return '<video controls="true" width="100%" height="60%" preload="metadata"><source src="{:s}" type="video/mp4"></video>'.format(main)
    
        elif ext.lower() in ['.jpg', '.jpeg', '.jp2', '.jpx', '.gif', '.png', '.tiff', '.tff', '.bmp']:
        
            if not os.path.exists(thumb_fs):
                self.thumb_queue.append( (main_fs,thumb_fs) )
            
            return main,thumb
            
        else: # Cannot tell. Just link it and return text
            return 'File: [`{}`]({})'.format(blockpath0,main)
        

    def make_filelink(self,main_fs,blockpath):
        """
        Make sure there is the symlinked file where it is supposed to be
        
        Return the extension of the file
        """
        # See if the linked file exists (and is not broken)
        base,ext = os.path.splitext(main_fs)
        
        
        # This block looks to see if the file is already there.
        # First, it checks if the block path file exists. 
        # (note: os.path.exists returns False on broken links).
        # Otherwise looks to see if *any* file starting with main_fs exists
        # (and is not a thumb). If it does, it keeps that
        if os.path.exists(main_fs): #
            return ext # Nothing to do
            # The file could just be a broken link. That will get captured below
        else: 
            # The block may not have had an extension. 
            all_matches = wild_ext(main_fs)
            for m in all_matches[:]:
                if not os.path.exists(m): # broken link. Delete the link and remove from the list
                    all_matches.remove(m)
                    try:
                        os.remove(m)       
                    except OSError:
                        pass
                if os.path.splitext(m)[0].endswith('.thumb'): # Remove the thumb too
                    all_matches.remove(m)
            all_matches.sort(key=ext_priority) # There may be more than one match
            if len(all_matches)>0: # There is still a matching file name. Use this
                return os.path.splitext(all_matches[0])[-1]
        
        # Could not be found already (or the link is broken).
                
        # Make the directory
        try:
            os.makedirs(os.path.dirname(main_fs))
        except OSError:
            pass
        
        ## Now we have to try to find the file!
        searchpaths = []
        head,baseext = os.path.split(blockpath)  # (may be [[path/photo.jpg]] or [[../photo.jpg]]
        
        # The specified locations (including if given a relative path in the block)
        if len(head)>0:
            searchpaths.append( os.path.normpath(os.path.join(NBCONFIG.photo_root,self.root,head))  )
            blockpath = baseext # Reset to remove the head material
        
        searchpaths.append( os.path.join(NBCONFIG.photo_root,self.root))
        
        # If not there, search the entire photo_root. This is slow so hopefully it isn't done often
        if NBCONFIG.photo_search_from_root:
            searchpaths.append(NBCONFIG.photo_root)

        for searchpath in searchpaths:
            match =  find_notags(searchpath,blockpath)
            if match is not None: # Do not continue
                break
        if match is None:
            raise ValueError('Could not find file: %s' % blockpath)
        
        match = os.path.normpath(match)
        new_ext = os.path.splitext(match)[-1].lower()
        
        # Add the extension
        if ext != new_ext: # See photo_link for disc. of this edge case
            main_fs += new_ext
        
        # Security check again to make sure not going to a symlink
        # above the photo root
        # - [ ] Consider removing this
        if not match.startswith(NBCONFIG.photo_root):
            raise ValueError('Cannot use item above photo_root (or linked to one)')
        
        # create the symlink. Try to delete it in case of broken
        try:
            os.remove(main_fs)
        except OSError:
            pass
    
        os.symlink(match,main_fs)
        return new_ext
           
        
    
def find_notags(startpath,blockpath):
    """
    Find files with the same non-tags blockpath and any extensions.
    """
    blockpath = remove_tags(blockpath)
    namequery = (blockpath + '*').lower() # Can follow with anything
    matched = []
    for dirpath, dirnames, filenames in os.walk(startpath):
        for dirname in dirnames[:]: # Remove hidden dirs
            if dirname.startswith('.'):
                dirnames.remove(dirname)
        
        for filename in filenames:
            # Check if there is a match. Note that if the block was specified
            # with an extension, that must also match
            if not fnmatch.fnmatch(remove_tags(filename).lower(),namequery):
                continue
            
            full_file = os.path.join(dirpath,filename)
            # Follow links
            while os.path.islink(full_file):
                linked_file = os.readlink(full_file) 
                
                # May be a relative link
                full_file = os.path.abspath(os.path.join(os.path.dirname(full_file),linked_file))

                if not os.path.exists(full_file):
                    full_file = None
                    break
                    
            if full_file is not None:
                matched.append(full_file)
        
        # Found at least one match. No need to keep searching
        if len(matched) > 0:
            break
        
    # Now sort by extension priority
    matched.sort(key=ext_priority)
    
    if len(matched) == 0:
        return None
    return matched[0]
                    

def fileparts(filepath):
    """
    Splits into dirname,base,ext
    """
    dirname,baseall = os.path.split(filepath)
    base,ext = os.path.splitext(baseall)
    return dirname,base,ext



def ext_priority(filename,add_ext=None):
    exts = ['.jpeg','.jpg','.png','.tif','.tiff','.gif','.mp4','.mov','.pdf']
    if add_ext is not None and len(add_ext.strip())>0:
        exts.insert(0,add_ext.lower()) # Add the ext to the top of the list
    ext = os.path.splitext(filename)[-1]
    ext = ext.lower()
    try:
        p = exts.index(ext)
    except ValueError:
        p = 9999999999
    return p

def thumb_img(srcthumb):
    """
    Makes a thumnail if it doesn't already exist
    """
    src,thumb = srcthumb
    from PIL import Image # lazy imports
    if os.path.exists(thumb):
        return
    img = Image.open(src)
    img.thumbnail([maxDim,maxDim])
    img.save(thumb,quality=60,optimize=True)
    del img # maybe help free up memory. Shouldn't be needed though

#
def wild_ext(pathname):
    """
    Same as glob.glob(pathname+'*') but CASE INSENSITIVE
    """
    rem = re.compile(fnmatch.translate(pathname + '*'),flags=re.IGNORECASE)
    dirname,basename = os.path.split(pathname)
    try:
        files = [dirname + '/' + f for f in os.listdir(dirname)]
    except OSError:
        return []
    return [f for f in files if rem.match(f)]

















