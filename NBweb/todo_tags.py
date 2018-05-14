#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import division, print_function, unicode_literals, absolute_import

import re
import os
import json
from collections import defaultdict
import math

## NBweb
from . import utils

def todos(db,loc=None):
    todo_DB = {}
    
    qmarks = []
    sql = """SELECT rootbasename,todo FROM file_db 
             WHERE (todo IS NOT NULL)"""
    
    if loc: # add location
        loc = utils.join('/',os.path.dirname(loc),'%') # So it is just the /dir + wildcard
        sql += ' AND (rootbasename LIKE ?)'
        qmarks.append(loc)
        
    for item in db.execute(sql,qmarks):
        todos = json.loads(item['todo'])
        if len(todos) == 0:
            continue
        
        todo_DB[item['rootbasename']] = todos

    re_priority = re.compile('^\(([A-Z])\) ')

    priorities = defaultdict(list) ; priorities_named = list()
    projects = defaultdict(list)
    contexts = defaultdict(list)

    # Assign priority, projects and contexts
    for page,todos in sorted(todo_DB.items(),key=lambda a:a[0].lower()):
        for todo in todos:
            todo['page'] = page 
            #todo['text'] = mmd(todo['text']).replace('<p>','').replace('</p>','')
            
            # Priority
            priority = [match.group(1).strip() for match in re_priority.finditer(todo['text'])]
            priority = priority[0] if len(priority)>0 else None
            priorities[priority].append(todo)

            # Contexts "@"
            for context in (c.lower() for c in todo['text'].split() if c.startswith('@')):
                contexts[context].append(todo)

            # Projects "+"
            for project in (p.lower() for p in todo['text'].split() if p.startswith('+')):
                projects[project].append(todo)

    ## Format
    todo_text = ['# ToDo Items\n']
    todo_html = ['<<<PLACEHOLDER>>>']

    # Priority
    todo_text.append('## All Items by priority\n')
    todo_html.append('<h3>All Items by priority</h3>\n')

    for priority in sorted(priorities.keys(),key=lambda a:a if a is not None else 'Z'*1000):

        todo_text.append('### {}\n'.format(priority))
        todo_html.append('<h4 id="pri_{p}">{p}</h4>\n\n<ul>'.format(p=priority))

        for todo in priorities[priority]:
            todo_text.append('* {page}:{line} - {text}'.format(**todo))
            todo_html.append('<li><a href="{page}.html"><code>{page}</code></a>:{line} - {text}'.format(**todo))

        todo_html.append('</ul>\n')
        todo_text.append('')
        priorities_named.append(priority) # Do separately so it is in order

    # Contexts
    todo_text.append('## @context\n')
    todo_html.append('<hr></hr><h3>@context</h3>\n')

    for context in sorted(contexts.keys()):
        if len(context.strip()) == 0:
            continue
        
        todo_text.append('### {}\n'.format(context[1:]))
        todo_html.append('<h4 id="context_{c}">{c}</h4>\n\n<ul>'.format(c=context[1:]))

        for todo in contexts[context]:
            todo_text.append('* {page}:{line} - {text}'.format(**todo))
            todo_html.append('<li><a href="{page}.html"><code>{page}</code></a>:{line} - {text}'.format(**todo))

        todo_html.append('</ul>\n')
        todo_text.append('')

    # Projects
    todo_text.append('## +project\n')
    todo_html.append('<hr></hr><h3>+project</h3>\n')

    for project in sorted(projects.keys()):
        if len(project[1:].strip()) == 0:
            continue
            
        todo_text.append('### {}\n'.format(project[1:]))
        todo_html.append('<h4 id="proj_{p}">{p}</h4>\n\n<ul>'.format(p=project[1:]))

        for todo in projects[project]:
            todo_text.append('* {page}:{line} - {text}'.format(**todo))
            todo_html.append('<li><a href="{page}.html"><code>{page}</code></a>:{line} - {text}'.format(**todo))

        todo_html.append('</ul>\n')
        todo_text.append('')

    # Create quick links at the top
    toptxt = ['<p>\n']
    
    toptxt.append('<strong>priorities</strong>: ')
    toptxt.append(', '.join('<a href="#pri_{p}">{p}</a>'.format(p=p) for p in priorities_named) + '<br>\n')

    toptxt.append('<strong>contexts</strong>: ')
    toptxt.append(', '.join('<a href="#context_{c}">{c}</a>'.format(c=c[1:]) for c in sorted(contexts.keys()) if len(c[1:].strip())>0 )+ '<br>\n')

    toptxt.append('<strong>projects</strong>: ')
    toptxt.append(', '.join('<a href="#proj_{p}">{p}</a>'.format(p=p[1:]) for p in sorted(projects.keys()) if len(p[1:].strip())>0) + '\n')

    toptxt = ''.join(toptxt) + '</p>\n'

    todo_html = '\n'.join(todo_html)
    todo_html = todo_html.replace('<<<PLACEHOLDER>>>',toptxt)

    todo_text = utils.to_unicode('\n'.join(todo_text))
    return todo_text,todo_html

def tags(db,loc=None):

    # Invert the tag database
    tag_DB_inv = defaultdict(list) # the incoming is all sets for no repeats
    
    qmarks = []
    sql = """SELECT rootbasename,tags,ref_name 
             FROM file_db WHERE  LENGTH(tags)>0"""
    
    if loc: # add location
        loc = utils.join('/',os.path.dirname(loc),'%') # So it is just the /dir + wildcard
        sql += ' AND (rootbasename LIKE ?)'
        qmarks.append(loc)
    
    for item in db.execute(sql,qmarks):
        page = {'path':item['rootbasename'],'ref_name':item['ref_name']}
        tags = item['tags']
        if len(tags) == 0:
            continue
        
        tags = (t.strip() for t in tags.split(',') )
        
        for tag in tags:
            if len(tag) == 0:
                continue
            tag_DB_inv[tag].append(page)

    if len(tag_DB_inv) == 0:
        return '<p>No tags found</p>'

    tag_page_txt = ['<h2>All Tags:</h2>\n']


    # Make the tag cloud
    tag_counts = {tag:len(pages) for tag,pages in tag_DB_inv.items()}

    tag_cloud = []
    min_fs = 10; max_fs = 25;

    # We want to scale all text to the 50-95 %ile
    count_min = percentile(tag_counts.values(),0.5,is_sorted=False)
    count_max = percentile(tag_counts.values(),0.95,is_sorted=False)

    for tag,count in sorted(tag_counts.items()):
        # map to font size
        if (count_max-count_min) >4:
            fs = 1.0*(count - count_min)/(count_max-count_min) # [0,1] if in bounds
            fs = max([fs,0.0]); fs = min([fs,1.0]) # Now in [0,1] for real
            fs = min_fs + fs * (max_fs-min_fs)
            fs = int(round(fs))
        else:
            fs = 12

        txt = '<a href="#tag_{tag}"><span style="font-size:{fs}px">{tag} ({N})</span></a>'.format( \
                    tag=tag,fs=fs,N=count)
        tag_cloud.append(txt)

    tag_page_txt.append( '<p>' + ', '.join(tag_cloud) + '</p>')



    for tag,pages in sorted(tag_DB_inv.items()):
        if len(pages) == 0:
            continue # Shouldn't happen but just in case

        pages.sort(key=lambda a:a['path'].lower())

        tag_page_txt.append('<h3 id="tag_{tag}">{tag} ({N})</h3>\n\n<ul>'.format(tag=tag,N=len(pages)))

        for page in pages:
            txt = '<li><a href="{path}.html">{ref_name}</a></li>'.format(**page)
            tag_page_txt.append(txt)

        tag_page_txt.append('</ul>\n')
    
    return '\n'.join(tag_page_txt)


def percentile(arr, P, is_sorted=False):
    """
    NOTE: Returns the first element that is GREATER than the percentile

    Inputs:
    -------

    arr:    Array to be sorted
    P:      Percentile desired [0,1]

    Options:
    -------

    is_sorted:  [False] Whether or not the list is already sorted. Saves time

    """
    if not is_sorted:
        arr = sorted(arr)

    return arr[int(math.ceil((len(arr)-1) * 1.0 * P))]















