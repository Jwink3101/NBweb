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
import glob
import sys
import re
import glob
import multiprocessing as mp ## Uses multi-processing to speed things up for the thumbnail creation
from functools import partial

if sys.version_info > (2,):
    unicode = str
    xrange = range



from NBweb import utils
import NBCONFIG

maxDim=1000

def filter_basenames(base):
    base = re.split('\(|\[',base)[0]
    while any(base.endswith(a) for a in ',._-'):
        base = base[:-1].strip()
    return base.lower()

if not hasattr(NBCONFIG,'filter_basenames') or NBCONFIG.filter_basenames is None:
    NBCONFIG.filter_basenames = filter_basenames

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
        dirname,base,ext = fileparts(blockpath) # split
        base = NBCONFIG.filter_basenames(base)  # filter the base name
        blockpath = os.path.join(dirname,base + ext) # Recombine
        
        # These are the final paths but they may not have an extension
        _ = os.path.join('/_galleries',self.root,blockpath)
        main = os.path.normpath(_)
        thumb = '{}.thumb{}'.format(*os.path.splitext(main))

        # fs -- filesystem paths. Actual paths on the system
        main_fs = os.path.normpath(os.path.join(NBCONFIG.scratch_path,main[1:]))
        thumb_fs = os.path.normpath(os.path.join(NBCONFIG.scratch_path,thumb[1:]))
        
        # Security check (will check again if needed). Make sure cannot be above photo_root
        if not main_fs.startswith(os.path.join(NBCONFIG.scratch_path,'_galleries')):
            raise ValueError('Cannot go above the photo_root')
        
        # Make sure there is the symlinked file at main_fs AND
        # it is valid
        new_ext = self.make_filelink(main_fs,blockpath)
        
        if ext == '': # reset all extensions
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
        
        if not ext == '' and os.path.exists(main_fs): # Will also check if broken symlink
            return ext 
        else:
            all_matches = glob.glob(main_fs+'.*')
            for m in all_matches[:]:
                if not os.path.exists(m): # broken link
                    all_matches.remove(m)
                    try:
                        os.remove(m)
                    except OSError:
                        pass
                if os.path.splitext(m)[0].endswith('.thumb'):
                    all_matches.remove(m)
            all_matches.sort(key=ext_priority)
            if len(all_matches)>0:
                return os.path.splitext(all_matches[0])[-1]
                
        # Make the directory
        try:
            os.makedirs(os.path.dirname(main_fs))
        except OSError:
            pass
        
        ## Now we have to try to find the file!
        searchpaths = []
        head,base,_ = fileparts(blockpath)  # bp,photo.jpg
        
        # The specified locations (including if given a relative path in the block)
        if len(head)>0:
            searchpaths.append( os.path.join(NBCONFIG.photo_root,self.root,head))  
        searchpaths.append( os.path.join(NBCONFIG.photo_root,self.root))
        
        # If not there, search the entire photo_root. This is slow so hopefully it isn't done often
        if NBCONFIG.photo_search_from_root:
            searchpaths.append(NBCONFIG.photo_root)


        for searchpath in searchpaths:
            match =  find_filtered(searchpath,base,ext)
            if match is not None:
                break
        
        if match is None:
            raise ValueError('Could not find file: %s' % blockpath)
        
        match = os.path.normpath(match)
        
        new_ext = os.path.splitext(match)[-1].lower()
        
        # Add the extension
        if ext == '':
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
           
        
    
def find_filtered(startpath,filtered_basename,ext):
    """
    Look for the file with the same FILTERED basename and return the full
    path. If more than one match, assign priority by the ext
    """
    matched = []
    for dirpath, dirnames, filenames in os.walk(startpath):
        for dirname in dirnames[:]: # a copy
            if dirname.startswith('.'):
                dirnames.remove(dirname)
        
        # See if there are any matches in the filenames. 
        # If there are, break. No need to go further
        for filename in filenames:
            base,_ = os.path.splitext(filename)
            base = NBCONFIG.filter_basenames(base)
            if base == filtered_basename:
                
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
        
        if len(matched) > 0:
            break
        
    # Now sort by extension priority
    matched.sort(key=partial(ext_priority,add_ext=ext))
    
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
# def photo_link(block_path,return_paths=False):
#     """
#     Return the link and processess the photo
#     
#     Will return text-like object if not a photo (video, file, etc) OR,
#     it will return a tuple. (this difference can be used to ensure it's a photo)
#     """
#     global mp_queue
#     
#     # Process: First we determine the photo's equivalent scratch path
#     # (sans extension). Then, if that exists, we continue. Otherwise, we
#     # try to create a link to it.
#     
#     scratch_photo_path0 = os.path.join(NBCONFIG.scratch_path,'_galleries',root,block_path)
#     scratch_photo_path = find_path(scratch_photo_path0)
# 
#     if scratch_photo_path is None: # It isn't already there!
#     
#         src_photo_path = os.path.join(NBCONFIG.photo_root,root,block_path)
#         src_photo_path = find_path(src_photo_path)
#         
#         if src_photo_path is None:
#             err = "Photo does not exists or couldn't find the extension\n"
#             err += 'Photo:{:s}\nFull:{:s}'.format(block_path,src_photo_path)            
#             for _ in range(100):
#                 mp_queue.put(None)
#             raise ValueError(err)
# 
#         # Follow links
#         while os.path.islink(src_photo_path):
#             src_photo_path = os.readlink(src_photo_path)
#             if not os.path.exists(src_photo_path):
#                 raise ValueError("Link to photo doesn't exist")
# 
#         # Get the relative path to check for securty and later define the full
#         # This gets redone later but oh well.
#         rel_scratch_photo_path = os.path.relpath(src_photo_path,NBCONFIG.photo_root)
#         
#         # Security
#         if '..' in rel_scratch_photo_path:
#             raise ValueError('Cannot specify any photos outside the photo_root: {}'.format(block_path))
#         
#         scratch_photo_path = os.path.join(NBCONFIG.scratch_path,'_galleries',rel_scratch_photo_path)
#         
#         # Make the link!
#         try:
#             os.makedirs(os.path.split(scratch_photo_path)[0])
#         except OSError:
#             pass
#         
#         try:
#             os.symlink(src_photo_path,scratch_photo_path)
#         except OSError:
#             pass
#     
#     ext = os.path.splitext(scratch_photo_path)[-1]
#     
#     rel_scratch_photo_path = os.path.relpath(scratch_photo_path,NBCONFIG.scratch_path)
#         
#     ## Treat different formats (though focus on jpg)
#     if ext.lower() in ['.mp4','.mov']:
#         return '<video controls="true" width="100%" height="60%" preload="metadata"><source src="/{:s}" type="video/mp4"></video>'.format(rel_scratch_photo_path)
#     
#     elif ext.lower() in ['.jpg', '.jpeg', '.jp2', '.jpx', '.gif', '.png', '.tiff', '.tff', '.bmp']:
#         
#         make_thumb = lambda p:'{}.thumb{}'.format(*os.path.splitext(p))
#         
#         # Convert all of relevant paths
#         scratch_thumb_path = make_thumb(scratch_photo_path)
#         rel_scratch_thumb_path = make_thumb(rel_scratch_photo_path)
#         
#         # add to the processing queue. Make the thumb from the scratch version
#         mp_queue.put( (scratch_photo_path,scratch_thumb_path) )
#         
#         return '/'+rel_scratch_photo_path,'/'+rel_scratch_thumb_path
#         
#     else: # Cannot tell. Just link it and return text
#         return 'File: [`{block_path}`](/{rel_scratch_photo_path})'.format(**locals())
# 
# 
# def find_path(path):
#     """
#     Tries to determine the path to a real file
#     """
#     if os.path.exists(path):
#         return path
# 
#     if path.endswith('.'):
#         path = path[:-1]  # remove the '.'
#     
#     try:
#         path0 = path
#         path = glob.glob(path + '.*')
#         path = [p for p in path if not p.lower().endswith('.aae')] # Special case!
#         path = [p for p in path if '.thumb.' not in p]
#         
#         if len(path)>1:
#             print('WARNING: Multiple photos match for {}'.format(path))
#         return path[0]
#     except IndexError:
#         pass
# 

#  
# 
# def photo_parse(filetext,meta,NBCONFIG_):
#     """
#     Usage:
#         filetext = photo_parse(filetext,meta,NBCONFIG)
#     """
#     
#     global NBCONFIG
#     global root
#     global mp_queue
# 
#     NBCONFIG = NBCONFIG_
#     if 'root' not in meta:
#         raise ValueError('Must specify a root in the metadata for galleries')
#     root = meta['root']
#     if root.startswith('/'):
#         root = root[1:]
#     
#     out_txt = []
# 
#     ############ Get set up for multiprocessing the photos
#     Nproc = int(mp.cpu_count())
#     mp_queue = mp.Queue()
#     
#     workers = [mp.Process(target=mp_worker, args=(mp_queue,)) for _ in range(Nproc)]
#     for worker in workers:
#         worker.daemon = True
#         worker.start()
#     ###########
#     # Recombine the in_text now for later splitting
# 
#     # Now, convert it into blocks and skip the first
#     blocks = [block.split(']]',1) for block in ('\n' + filetext).split('\n[[')][1:]
#     
#     out_txt_list = []
# 
#     for block in blocks:
#         try:
#             block_path,description = block
#         except ValueError:
#             print('ERROR: Did you miss a closing ]')
#             out_txt.append('<h1>ERROR: Did you miss a closing ]</h1>')
#             continue
#         
#         # Special case for [[photo_names[tag]]]
#         if description.startswith(']'):
#             block_path += ']'
#             description = description[1:]
#         
#         # cut leading lines on the description and trailing spaces or \n. Also cut : from the start
#         while description.startswith('\n') or description.startswith(' ') or description.startswith(':'):
#             description = description[1:].lstrip()
#         while description.endswith('\n') or description.endswith(' '): # Should be a single loop
#             description = description[:-1].rstrip()
# 
#         # Deal with block types
#         block_path = block_path.strip()
#         block_path = block_path.replace('|',',')
# 
#         if block_path.startswith('#'):
#             continue # This is a hidden comment
# 
#         if block_path.startswith('+') or len(block_path) == 0:
#             # Comment
#             block_path = block_path[1:].strip()
#             
#             if len(block_path) >0:
#                 if block_path.startswith('#'):
#                     description = '{:s}\n\n'.format(block_path) + description
#                 else:
#                     description = '**{:s}**\n\n'.format(block_path) + description
#             out_txt_list.append(description)
#             continue
# 
#         # Otherwise it is photo or media
#         
#         # Handle the same way for multiphoto or regular
#         
#         # Split it up on commas but handle if inside of a "[tag,tag]" (https://stackoverflow.com/a/38748250)
#         block_paths = [b.strip() for b in re.split(',(?![^\(\[]*[\]\)])',block_paths) if len b.strip()>0]
#         
#         # New titles as multi line
#         title_tmp = ', '.join(['**`{:s}`**    '.format(t) for t in block_paths])
#         
#         all_paths = [photo_link(bp) for bp in block_paths]
#         
#         # split into tuples (images) or text (media or files)
#         all_img_paths = []
#         all_other_paths = []
#         for p in all_paths:
#             if isinstance(p,tuple):
#                 # Need  to add empty alt and descirption lines
#                 p = list(p)
#                 p.extend(['',''])
#                 all_img_paths.append(p)
#             else:
#                 all_other_paths.append(p)
#         
#         txt_tmp  = utils.html_snippet('mult_photo.html',
#                                        bottle_template={
#                                         'all_img_paths':all_img_paths
#                                         })
#         if len(all_other_paths) >0:
#             txt_tmp += '\n\n' + '\n'.join(all_other_paths)
# 
#         out_txt_list.append(title_tmp + '\n\n' + txt_tmp + '\n\n' + description)
# 
# 
#     out_txt = '\n'.join(out_txt) + '\n\n' + '\n\n-----\n\n'.join(out_txt_list)
#     
#     out_txt = out_txt.replace('\n\[','\n[') # Fix escaped characters
#     
#     ############ Cleanup from multi-processing
#     for _ in range(Nproc): # This sentinel kills the workers
#         mp_queue.put(None)
#     for worker in workers: # Let them all finish      
#         worker.join()
#     mp_queue.close()
#     ###########
#     
#     return out_txt


























