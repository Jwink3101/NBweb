#!/usr/bin/env python
from __future__ import division,print_function,unicode_literals,absolute_import
import json
import os
import io
import itertools
from collections import defaultdict

from sqlite3 import OperationalError

# import utils
from . import utils
join = utils.join

"""
Algorthithm and scoring as of 2017-03-19
Example: "Costco's rottisserie chicken salad"

* The query is cleaned same as the main DB (spaces, puctuation, etc)
    * "costco rottisserie chicken salad"
* It is broken into windows of the text. Each window should be no longer than
  four words EXCEPT the full is added. In this case, the search is len 4 so it
  doesn't matter
    [('costco',),('rottisserie',),('chicken',),('salad',),('costco', 'rottisserie'),('rottisserie', 'chicken'),('chicken', 'salad'),('costco', 'rottisserie', 'chicken'),('rottisserie', 'chicken', 'salad'),('costco', 'rottisserie', 'chicken', 'salad')]
* Each window is given a multiplier of `wind_mult_fcn` the square root of the
  length. So matching "rottisserie chicken" is 1.41 points, but really, it is:
        'rottisserie'           1
        'chicken'               1
        'rottisserie chicken'   1.41
        -----------------------------
                                3.41 (assuming nothing else matches)
* loop through all pages [O(N)] and each window and find the count of the matches
    * cube root the count. For example, if 'chicken' is in a document 4 times, 
      it gets a score for that match of 1.587
* Loop through again and assign additional score for each page that links to
  the current one. For example, if 3 pages link to the current one with scores:
        page 1:     1
        page 2:     3.41
        page 3:     2
  the page gets a boost from these of link_mult_fcn (1/4 root) * each page
        6.41 * (3**1/4 == 1.316) ==> 8.436
* The scores are combined based on combine_score.
    direct + 1/3 * sqrt(link)  if direct >0
    3.41 + 0.333 * sqrt(8.436) == 4.377


"""

## Settings
# Weights and manipulations
wind_mult_fcn = lambda n: root(n,2)
link_mult_fcn = lambda n: root(n,4) # ^1/4 root. More linked pages means better results
def combine_score(direct,link):
    if direct == 0:
        return 0.0
    return direct + 0.33*root(link,pow=2)

# Format
FMT =  '<p><a href="{path}.html">{name}</a>'
FMT += '<br>{path} <small>({score:0.2f})</small></p>'

def search(query,db):
    incoming_count = defaultdict(lambda: {'count':0,'score':0}) 
    
    Nmax = 4 # largest window (plus the original)

    # Remove stop words etc:
    query0 = query
    query = utils.clean_for_search(query)
    
    if len(query.split()) == 0:
        return 'Error: Non-sufficient search query: "{}"'.format(query0)

    # In this algorithm, order does matter to increase score. But, we limit the search
    query_windows = set(' '.join(wind) for wind in all_window(query.split(),Nmax=Nmax) )

    # Add back the original
    query_windows.add(query)

    # Make it a list with the multiplier (sqrt(N))
    query_windows = [(window,wind_mult_fcn(len(window.split())) ) for window in query_windows]

    page_scores_direct = {}

    # We could just do `for page in db.execute('SELECT * FROM file_db'):`
    # and run this. But we will at least drop down the number of 
    # pages with some SQL 'like' queries. This is not perfect since
    # it may, for example, return pages with "costco" when searching for "cost" 
    # but it is still greatly reduces the number of pages

    # Build the SQL part. Search for the title or the stext
    # .. WHERE stext LIKE %word1% OR stext LIKE %word2%  OR stext LIKE %word3% ...
    #        OR lower(meta_title) LIKE %word1%
    # but use "?" to ensure no SQL injection
    
    query_wild_cards = query.split()
    query_wild_cards = ['%{}%'.format(a) for a in query_wild_cards]
    sql = 'SELECT * FROM file_db WHERE '
    # Add `stext LIKE ? `
    sql +=  ' OR '.join(['stext LIKE ?']*len(query_wild_cards)) \
         +  ' OR ' \
         +  ' OR '.join(['lower(meta_title) LIKE ?']*len(query_wild_cards))
    
    for page in db.execute(sql,query_wild_cards*2):
        name = page['rootbasename']
        text = page['stext']
        #title = utils.clean_for_search(page.get('meta_title','')) # SLOW. Just use regular
        title = page.get('meta_title','').lower()
        
        # Add the title the the text twice to count extra
        text = ' '.join([title]*2) + ' ' + text
        
        # Scores are based on the length of the match. But do recall that
        # matching 'A B' means you also matches 'A' and 'B'
        score = 0
        for window in query_windows:
            qtext = window[0]
            mult = window[1]
            
            ## Old system: One match
            #score += (text.find(qtext)>=0) * mult
            
            ## New, Count number of matches
            score += root(text.count(qtext),3) * mult

        page_scores_direct[name] = score
        
        # Add this score to each outgoing link
        outs = [os.path.splitext(it)[0] for it in page['outgoing_links'].split(',')]
        for out in outs:
            incoming_count[out]['count'] += 1
            incoming_count[out]['score'] += score
        
    page_scores = []
    for name in page_scores_direct.keys():
        direct = page_scores_direct[name]
        incoming = link_mult_fcn(incoming_count[name]['count']) * incoming_count[name]['score']
        page_score = {  'name':name,
                        'direct':direct,
                        'incoming':incoming,
                        'score':combine_score(direct,incoming)} 
        page_scores.append(page_score)
        
    page_scores.sort(reverse=True,key=lambda a:(a['score'],a['direct'])) # Sort by overall score then direct score

    out = []
    for page_score in page_scores[:20]:
        score = page_score['score']
        path = page_score['name']
        # name = file_db.find_one(rootbasename=page_score['name'])['ref_name']
        
        name = db.execute("""SELECT meta_title 
                             FROM file_db
                             WHERE rootbasename=?""",[page_score['name']])\
                             .fetchone()['meta_title']
        
        if score ==0:
            break
        out.append(FMT.format(path=path,name=name,score=score))

    if len(out) == 0:
        return 'No results for "{}"'.format(query0)

    return '\n'.join(out)
#     return page_scores

def all_window(seq,Nmin=1,Nmax=None):
    """
    Yield a sliding window up to the entire thing!

    Inputs:
        seq: sequence
        Nmin : [1] Limit on the smallest size of the windows
        Nmax : [None] Option limit on the length. None means it goes to the max

    WARNING: This scales as len(seq)^3. Actually, it is

    N = len(seq)
    sum_n=1^N n*(N-n+1) <==> 1/6 N (1 + N) (2 + N)

    """
    def _window(seq,n): # http://stackoverflow.com/a/6822773
        "Returns a sliding window (of width n) over data from the iterable"
        "   s -> (s0,s1,...s[n-1]), (s1,s2,...,sn), ...                   "
        it = iter(seq)
        result = tuple(itertools.islice(it, n))
        if len(result) == n:
            yield result
        for elem in it:
            result = result[1:] + (elem,)
            yield result

    if Nmax is None:
        Nmax = len(seq)
    for n in range(Nmin,Nmax+1):
        for window in _window(seq,n):
            yield window


def root(num,pow):
    """
    Do the roots
    """
    return 1.0*num**(1.0/pow)





