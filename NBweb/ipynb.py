#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals, absolute_import
from io import open

import subprocess
import shlex
import os

from . import utils

def convert(systempath):
    cmd = 'jupyster nbconvert --stdout --to html --template basic {}'.format(systempath)
    
    try:
        #import ipdb;ipdb.set_trace()
        print('a')
        proc = subprocess.Popen(shlex.split(cmd),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        print('b')
        filetext,err = proc.communicate()
    except Exception:
        return  utils.parse_file(systempath)
    filetext = utils.to_unicode(filetext)
    filetext = '<htmlblock>\n' + filetext + '\n</htmlblock>'
    meta = {'title':os.path.basename(systempath)}
    return filetext,meta
