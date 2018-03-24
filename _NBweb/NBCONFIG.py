#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Configuration File
"""
from __future__ import division, print_function, unicode_literals, absolute_import

## Paths

## These setting can be changed but this is a usuall good choice
# Specify the source directory for the site. Default is to use this one
import os
source = os.path.normpath(os.path.join(os.path.split(os.path.abspath(__file__))[0],'../'))

# Specify a FULL scratch path
scratch_path = os.path.join(source,'_scratch')

try:
    os.makedirs(scratch_path)
except OSError:
    pass

# Set the DB. Note that the program uses `dataset` which uses SQLAlchemy. Use that system
# For this, set as this directory
DBpath = os.path.join(scratch_path,'DB.sqlite')
DBpath = 'sqlite:///' + DBpath

## Other settings

# Specify extensions to parse and allow. The first one is also the default
extensions = ['.md','.gallery']
title = 'Notebooks'

###############################################
## Users
###############################################
# Specify users as either protected (for anything in protected_dirs) or
# edit_users. edit_users can also view protected
# Also set a password hash that will be used. The password should be:
#    sha1('SALT:PASSWORD') # UTF8 encoded
# with the colon in between. Alternatively, you can do:
#   $ python NBweb.py --password SOURCE
# and it will prompt for a username and password (and use the salt set here)

password_salt = 'mysalt'

protected_users = {'guest':'saltedpasswordhash'}
edit_users = {'editor':'saltedpasswordhash'}

###############################################
## Special directories
###############################################

# Use wildcards for matching.
# Exclusions are checked against the full path starting with "/" and then
# just the basename.
# For example, to exclude all of the directory 'media', do:
#   exclusions = ['/media/*']
#
# Warning: if a directory is both blogged and protected, it will STILL show in
#          the blog pages. Be careful! Same for RSS pages
# Note that /_galleries is also a possible value. (and "*" will protect it)
blog_dirs = ['/posts/*']
protectect_dirs = ['/pages/protected/*']
exclusions = ['/media/*'] # just not shown
protected_comment = '\n<p>U: <code>USER</code>, P: hint hint</p>\n'


############################################
## Web Settings
############################################

# Specify the relative path to where uploads should be sorted. Specify as
# a relative or absolute path where it will be relative to the current page
# (if applicable)
# NOTE: It is highly suggested that this *also* be in the exclusions
# Also specify whether or not to sort by year and month (based on exif if 
# possible, otherwise, current time)
media_dir = '/media'
sort_year_month = True


# These settings get passed to Bottle's `run` command
web_server = { 'host':'localhost',
               'port':5050,
               'debug':True,
               'reloader':False}

# Specify whether or not you want to forward login pages to http rather than
# https. NOTE: this isn't perfect and could create a forward loop. Also, it
# will *not* return to http afterwards. It will stay in https until changed
https_login = False


############################################
## Edit Settings
############################################

# Tells NBweb whether or not to provide an ACE editing window. Options
# are True, False, or 'auto'. 'auto' will do its best to detect if using a
# mobile device and not use ACE.
# Note that regardless of the setting here, adding ?ace=true or ?ace=false
# will override
use_ace_editor = 'auto'

# Set the default text on a new page. The text here will be parsed by
# datetime.now().strftime so that dates may be included. Note that this
# setting does *not* apply to the "_quick_add" route
# Also the variables {numeric_id} is a suggested numeric id (based on the
# number of pages and the existence of an id)

# ID suggestions: Use either `id: {numeric_id}` or `id: %Y-%m-%d%H%M%S`

new_page_txt = """\
Title:
Date: %Y-%m-%d %H:%M:%S
id: {numeric_id}
Tags:
Draft: False

CONTENT

"""



# Define how to set the filename when it isn't provided. The format is
# based on the input metadata. The following keys are provided. Note that
# if the date is not provided, it will be evaluated to "" AND and leading
# non-alphanumeric will be stripped!
#  Keys:
#       {title}         -- Parsed title
#       {raw_date}      -- Datestring as provided in meta data
#       {short_date}    -- '%Y-%m-%d' format
#       {long_date}     -- '%Y-%m-%d_%H%M%S' format
#       {loc_long_date}  -- '%Y-%m-%d_%H%M%S' at current time locally (based on time_zone)
#       {loc_short_date} -- ''%Y-%m-%d' at current time locally

#auto_filename = '{title}'
auto_filemame = '{short_date}_{title}'


# Specify the local time zone. It MUST be in the format '+NNNN'
# such as '-0500'. Or set as None to use the local time of the server
time_zone = '-0700'


#############################################
## Appearance and Text
#############################################

# Specify how to reference a page 
# 'path' -- path to the file
# 'title' -- The file's title
# 'both' -- Include both
ref_type = 'title'

# Specify how to sort pages in a dir listing. (all lowercase)
# Sorting by path will be the same as the it appears in the directories
# 'path' -- Filename (just the final name)
# 'title' -- The file's title
# 'ref' -- The reference used above
# Directories are always sorted by their 'path'
sort_type = 'path'

# Specify if you want directories at the top or interwoven to within the rest
# of the listings
dirs_on_top = False

# Choose whether or not to annotate the links on the _all pages. Note that
# there is (intentionally) no option to do so on individual pages (at the
# moment). The annotations make it look a bit sloppier but they show a foot-note
# of sorts to the exact location of a link or image
# (which may be the same). This is good for printing and having a record
annotate_all_page = False

# Do you want to show "empty" folders where "empty" means they do not
# have any parsed content? Note that empty folders will not be shown even
# if they have content but it isn't in the DB. You can add "?empty=true"
# to override and show_empty no matter what
show_empty = False

# Markdown does treats line breaks as continuous text. This way, if the text
# is hard-wrapped, it shows as one paragraph. It treats TWO spaces at the end
# of a line as a line break. Set to True to override this and have line-breaks
# follow that of the content. False will treat as one
automatic_line_breaks = True

# If (and only if) a page has a set id, it can also be displayed under the 
# page path (always displayed when appropriate). This is useful if linking to
# page id's instead of full paths
display_page_id = False
 

############################################
## Photo Galleries
############################################
# If using the .gallery settings, specify a root location for the photos.
photo_root = '/path/to/photo/root'

# Specify whether or not to search for photos (based on the filtered name below)
# from the `photo_root`. Photos are always searched relative to the gallery's
# `root` setting, but this will ALSO search from `photo_root`. It may be slow
# since it has to find the photo in a larger directory
photo_search_from_root = False



#############################################
## Bash Management
#############################################
# Specify bash commands to run. Note that every command will
# automatically start with `cd /path/to/source`
#
# Specify as a list of (name,command) tuple. It is suggested you keep the
# git ones.
bashcmds = [
    ('git pull','git pull --no-edit'),
    ('git pull, add, commit, push',"""\
        git pull --no-edit
        git add .
        git commit -am"NBweb web commit"
        git push"""),
    ('git diff --name-only','git diff --name-only')
    ]





