#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals, absolute_import

import sys
import os
import argparse

if not __name__ == '__main__':
    raise ValueError('Not made to be imported')

def openbrowser(url):
    import webbrowser
    from threading import Thread
    import time
    
    def _open():
        tt = 1.0;
        ntt = 4
        for i in range(ntt):
            print('== Browser will open {} in {} s =='.format(url,tt*(1.0-1.0*i/ntt)))
            time.sleep(1.0*tt/ntt)
        webbrowser.open(url)

    thread = Thread(target=_open)
    thread.daemon = True # break if something goes wrong later
    thread.start()


description = """\
dynamic, file-based, markdown notebook with full-text search, cross-references, and many more features"""
epilog = """\
See readme.md for details
"""

## Parse arguments
parser = argparse.ArgumentParser(description=description,epilog=epilog)

# Required
parser.add_argument('source',action='store',help='Full systempath to directory')

# optional
parser.add_argument('-r','--refresh',action='store_true',\
    help='Will refresh any modified files before launching')
parser.add_argument('--reset',action='store_true',\
    help='Will remove the old DB and then refresh entire DB before launching')
parser.add_argument('--export',action='store',\
    help='Export a static copy to the specified directory')
parser.add_argument('--todo',action='store_true',\
    help='Prints the todo page to stdout and exits. Note: if `--refresh`, counts are printed to stderr')
parser.add_argument('--no-launch',action='store_true',\
    help='Do not launch the server. Useful to refresh before `--todo`')
parser.add_argument('--open',action='store_true',
    help='Open a web browser window. Will wait a few seconds for Bottle to start')
parser.add_argument('--password',action='store_true',help='Get the salted and hashed password for the user passwords')

## Undocumented arguments. 
# for running interactively and debugging
parser.add_argument('--interactive',action='store_true',help=argparse.SUPPRESS)

# do not start the server.

args = parser.parse_args()

# Add the source + _NBweb to the path
config_dir = os.path.join(args.source,'_NBweb')

# add to the PYTHONPATH for the config file
if config_dir not in sys.path:
    sys.path.append(config_dir) 

# Start
import NBCONFIG
if args.reset:
    DBpath = os.path.join(NBCONFIG.scratch_path,'DB.sqlite')
    try:
        os.remove(DBpath)
    except OSError:
        pass
    args.refresh = True # Override
    
from NBweb import utils
from NBweb import offline_copy
from NBweb import NBweb # Will then also parse the config

if args.interactive:
    from NBweb import todo_tags
    from NBweb import search
    from NBweb import bottlesession
    from NBweb import offline_copy
    from NBweb.photo_sort import photo_sort
    from NBweb.photo_parse import photo_parse
    from NBweb import NBweb

    if args.refresh:
        NBweb.parse_all() 

    db = NBweb.db_conn()
    sys.exit()

if args.password:
    import getpass
    p = getpass.getpass()
    print(NBweb.salthash(p))
    sys.exit()
    

if args.refresh:
    NBweb.init_db()
    NBweb.parse_all()

if args.export is not None:
    offline_copy.offline_copy(args.export)
    sys.exit()

if args.todo:
    sys.stdout.write(NBweb.return_todo_txt()+'\n')
    sys.exit()

if args.open:
    # The defaults come fromt bottle.run's defaults
    host = NBCONFIG.web_server.get('host','127.0.0.1')
    port = NBCONFIG.web_server.get('port',8080)
    url = 'http://{host}:{port}'.format(host=host,port=port)
    openbrowser(url)
    

if not args.no_launch:
    NBweb.start()

















