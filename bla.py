def url_fix(m):
    """
    heuristic function to determine if the included is a real URL or not.
    
    Note: if the returned text looks like "[link](<http://bla.com>)", it will
    still properly render
    
    May not be perfect and the goal isn't to capture every single one...
    """
    alphanumeric = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    url0 = url = m.group()
    urll = url.lower()
    
    # Is it just a vanilla URL with *nothing* around it and only http[s] once?
    if len(re.findall('https?://',urll)) == 1 and \
         urll.startswith('http') and \
         urll[-1] in alphanumeric:
       return '<' + url0 + '>'
    
    # Handle "(http://url.com)" and [http://url.com] but not "[link](http://url.com)"
    for s,e in ['[]','()']:
        if url.startswith(a) and url.endswith(e):
            return s + '<' + url + '>' + e
    
    # Already a URL
    if url.startswith('<') and url.endswith('>'):
        return url
    
    # At this point, it is not a detectable URL. Skip
    return url
