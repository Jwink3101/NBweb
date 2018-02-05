#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Playing with authentication
"""
from __future__ import division,print_function,unicode_literals,absolute_import

# standard lib
import sys
import os
import hashlib
import time

# Project
import utils

# Bottle
from bottle import route,run,static_file,request,redirect,response
import bottlesession

USERS = {'test':'testpassword'}
REQUIRELOGIN = False

session_manager = bottlesession.JSONSession()

if REQUIRELOGIN:
    authenticate = bottlesession.authenticator(session_manager,login_url='/_login')
else:
    authenticate = lambda:lambda b:b # Wrapper that does nothing


@route('/_login',method=['get','post'])
@route('/_login/<path:path>',method=['get','post'])
def login(path=None):
    """
    Login. Use  @authenticate decorator for a given path
    or call this function with a path to redirect to that path
    """
    if path is None: # for @authenticate decorator
        path = request.get_cookie('validuserloginredirect', '/')
    
    print('PATH',path)
    
    # Check if already logged in and valled
    logged,session = check_logged_in()
    if logged:
        raw_input('logged')
        redirect(utils.join('/',path)) # SUCCESS!
    
    if request.method == 'GET':
            toptxt = "<p>Login:</p>"
            if request.query.get('failed',default='false').lower() == 'true':
                toptxt = "<p>Login Failed. Try again</p>"
            return '''{toptxt}
        <form action="/_login/{path}" method="post">
            Username: <input name="username" type="text" />
            Password: <input name="password" type="password" />
            <input value="Login" type="submit" />
        </form>
        '''.format(toptxt=toptxt,path=path)
    else: 
        username = request.forms.get('username').lower()
        password = request.forms.get('password')
        print("USERS.get(username,'_')",USERS.get(username,'_'))
        if USERS.get(username,'_') ==  password:
            session['valid'] = True
            session['name'] = username
            session_manager.save(session)
            print('PASS',session,path)
            redirect(utils.join('/',path)) # SUCCESS!
        else:
            session['valid'] = False
            session_manager.save(session)
            print('FAIL',session)
            np = utils.join('/_login',path + '?failed=true')
            print('np',np)
            redirect(np) # Fail!

def check_logged_in():
    """
    Use this to check if already logged in
    """
    session = session_manager.get_session()
    
    # Check if it is a valid session. Sessions are stored locally so this
    # shouldn't be something a user could fake.
    print('session',session)
    
    if not REQUIRELOGIN:
        return (True,dict())
    
    if session['valid']:        
        return (True,session)
    return (False,session)
            
@route('/_logout')
@route('/_logout/')
def logout():
    session = session_manager.get_session()
    session['valid'] = False
    session_manager.save(session)
    redirect('/')
    
@route('/other/<path:path>')
def other(path=''):
    """a test one with the other login type"""
    logged,session = check_logged_in()
    print('logged',logged)
    print('session',session)
    if not logged:
        redirect(utils.join('/_login/other',path)) 
        # NOTE: You need to set the redirect to /_login/<route>/ to work around
        # the forwarding

    name = session.get('name')
    return 'other {} {}'.format(name,path)
    


@route('/')
@route('/<path:path>')
@route('')
@authenticate()
def home(path='/'):
    text = 'home'
    session = session_manager.get_session()
    name = session.get('name')
    return 'home {} {}'.format(name,path)


def sha1(*txt):
    hasher = hashlib.sha1()
    hasher.update(''.join(txt))
    return hasher.hexdigest()





if __name__=='__main__':
    run(host='localhost', port=5050, debug=True,reloader=False)
