#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Replacement for using a module as a config. This way, we do not have to mess
with the python path and any potential shortcommings of that approach
"""
from __future__ import division, print_function, unicode_literals, absolute_import
from io import open

import os
import types

# We want the parser to be a global object (without actually using globals)
# so that any module can interact with it.

class ConfigParser:
    # Variables to be ignored in the default parses
    _ignore_default = ['source','scratch_path']
        
    # Variables that must be a list
    _lists = ['blog_dirs','protectect_dirs','exclusions']
        
    def __init__(self,filename=None):
        self._parsed = False
        self.filename = filename

        self._parse_defaults()
        if filename is not None:
            self._parse()
    
    def _parse_defaults(self):
        """
        Parse the default NBconifg
        """
        default_path = os.path.join(os.path.dirname(__file__),'_NBweb','config')
        
        fd = self._parsefile(default_path)
        for key,val in fd.items():
            if key in self._ignore_default:
                continue
            
            setattr(self,key,val)
    
    def _parse(self,filename=None):
        if filename is None:
            filename = self.filename
        
        if filename is None:
            raise ValueError('Must specify a filename')
        
        fd = self._parsefile(filename)
        for key,val in fd.items():
            setattr(self,key,val)
        
        self._set_values()
        
    def _set_values(self):    
        self.extensions = [a.lower() for a in self.extensions]
        self.exclusions = list(set(self.exclusions + ['.git/','.svn/','.*','_*']))
        self.scratch_path = os.path.abspath(self.scratch_path)

        try:
            os.makedirs(self.scratch_path)
        except OSError:
            pass

        # Set the DB. Note that the program uses `dataset` which uses SQLAlchemy. Use that system
        # For this, set as this directory
        self.DBpath = os.path.join(NBCONFIG.scratch_path,'DB.sqlite')
    
    @classmethod
    def _parsefile(cls,filename):
        with open(filename,'rt',encoding='utf8') as F:
            code = F.read().strip()
        
        # Remove shebang and a few other things
        while code.startswith('#'):
            code = code.split('\n',1)[1].strip()
        
        filename = os.path.abspath(filename)
        filedict = {'__file__':filename,
                    'source':os.path.normpath(os.path.join(os.path.dirname(filename),'../'))
                    }
        exec(code,filedict)
        for key in list(filedict.keys()): # iterate over a copy
            if isinstance(filedict[key], types.ModuleType):
                del filedict[key]
            
            if key in cls._lists and not isinstance(filedict[key],list):
                if isinstance(filedict[key],(tuple,set)):
                    filedict[key] = list(filedict[key])
                else:
                    filedict[key] = [filedict[key]]
        
        return filedict

NBCONFIG = ConfigParser()
    
