#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals, absolute_import
from io import open

import sys
import os
import argparse

__version__  = '20180703.0'

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


def cli(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    description = ('dynamic, file-based, markdown notebook with full-text '
                   'search, cross-references, and many more features')
    epilog = "See readme.md for details"

    ## Parse arguments
    parser = argparse.ArgumentParser(description=description,epilog=epilog)

    # Positional
    parser.add_argument('source',action='store',help="['.'] Path to the notebook",default=".",nargs='?')

    # optional
    parser.add_argument('--init',action='store_true',
        help="Initialize the noteboook here if it doesn't exists")
    parser.add_argument('--todo',action='store_true',\
        help='Prints the todo page to stdout and exits. Note: if `--refresh`, counts are printed to stderr')
    parser.add_argument('--no-launch',action='store_true',\
        help='Do not launch the server. Useful to refresh before `--todo`')
    parser.add_argument('--open',action='store_true',
        help='Open a web browser window. Will wait a few seconds for Bottle to start')
    parser.add_argument('--password',action='store_true',help='Get the salted and hashed password for the user passwords')
    parser.add_argument('-r','--refresh',action='store_true',\
        help='Will refresh any modified files before launching')
    parser.add_argument('--reset',action='store_true',\
        help='Will remove the old DB and then refresh entire DB before launching')

    #parser.add_argument('--export',action='store',\
    #    help='Export a static copy to the specified directory')
    

    args = parser.parse_args()
    args.source = os.path.abspath(args.source)
    
    if args.init:
        dest = os.path.join(args.source,'_NBweb')
        if os.path.isdir(dest):
            sys.stdout.write('NBweb already initiated here\n')
            sys.exit(2)
        src = os.path.join(os.path.dirname(__file__),'_NBweb')
        src = os.path.abspath(src)
        
        import shutil
        shutil.copytree(src,dest)
        msg = "NBweb initiated. Modify `_NBweb/config` and run"
        print(msg)
        sys.exit()
    


    # Parse
    from .nbconfig import NBCONFIG
    
    # The file should be called 'config' but will accept NBCONFIG.py
    config_dir = os.path.join(args.source,'_NBweb')
    if os.path.exists(os.path.join(config_dir,'config')):
        NBCONFIG._parse(os.path.join(config_dir,'config'))
    elif os.path.exists(os.path.join(config_dir,'NBCONFIG.py')):
        sys.stderr.write('DEPRECATION. Change NBCONFIG.py --> config\n\n')
        NBCONFIG._parse(os.path.join(config_dir,'NBCONFIG.py'))
    else:
        sys.stderr.write('Cannot find config')
        sys.exit(2)

    # Start

    if args.reset:
        DBpath = os.path.join(NBCONFIG.scratch_path,'DB.sqlite')
        try:
            os.remove(DBpath)
        except OSError:
            pass
        args.refresh = True # Override
    
    from . import utils
    from . import main # Will then also parse the config


    if args.password:
        import getpass
        p = getpass.getpass()
        print(main.salthash(p))
        sys.exit()
    

    if args.refresh:
        main.init_db()
        main.parse_all()

#     if args.export is not None:
#         offline_copy.offline_copy(args.export)
#         sys.exit()

    if args.todo:
        sys.stdout.write(main.return_todo_txt()+'\n')
        sys.exit()

    if args.open:
        # The defaults come fromt bottle.run's defaults
        host = NBCONFIG.web_server.get('host','127.0.0.1')
        port = NBCONFIG.web_server.get('port',8080)
        url = 'http://{host}:{port}'.format(host=host,port=port)
        openbrowser(url)
    

    if not args.no_launch:
        main.start()
