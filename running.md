This is a brief description of how to run NBweb. It does not cover every detail but should get you started. 

One of the most important things is to have *some* content already.

    mynotebook/
    ├── hello.md
    └── page1.md

In the folder, run 

    $ python /path/to/NBweb.py --init
    
It will create a folder structure like

    mynotebook/
    ├── _NBweb
    │   ├── config
    │   ├── style.css
    │   └── template.html
    ├── hello.md
    └── page1.md

Now, go through all options in `config` and set them accordingly. For the most part, you can keep them exactly as is except the following (this is actually a bug...):

* Change `blog_dirs = ['/posts/*']` to `blog_dirs = []` unless you have content. If there is nothing in a `blog_dirs`, it fails

You will likely want to change the users. Set the salt and come back later to set the passwords

At this point, you should be able to run it. Note that right now, the design is a bit strange as there is a `NBweb.py` file and a `NBweb/main.py` directory/package. This will be cleaned in the future. But for now, **ignore the package** version. (via an entry point)

You should be able to run it now. Assuming you're in the directory (otherwise, you need to specify the path as the first positional argument)

    $ python /path/to/NBweb.py

You're done!

However, if you want to set a user, you should do

    $ python /path/to/NBweb.py --password 
    # Enter your password. Say '123'

And it will spit out a password. (for the default salt, it is `5c3c858f4be8cdd0d2daa7fd76e5977ffeb68269`)

Change the config to, for example, to:

    edit_users = {'myname':'5c3c858f4be8cdd0d2daa7fd76e5977ffeb68269'}

And then you should be able to log in

**NOTE**: Any changes to the config, including users and passwords, require that you restart the software!!! (This may change)

