#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals, absolute_import

import sys

from NBweb import cli

if not __name__ == '__main__':
    raise ValueError('Not made to be imported')
    
sys.dont_write_bytecode = True


if __name__ == '__main__':
    argv = sys.argv[1:] # Argument besides function name
    cli(argv)
















