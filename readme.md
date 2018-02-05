# NBWeb

## Warning: BETA software

**WARNING**: This software is in beta! Nothing should be considered finalized and the overall design is still subject to change.

A _very **non-exhaustive**_ list of improvements to be done are:

* Remove remaining cruft from dataset to pure sqlite3 switch
* Improve templating to *just* use Bottle templates as needed
* Refactor code to reduce mess of NBweb.py
* fix/update call method of NBweb.py outside the module and also inside.
* Add `setup.py` and associated PyPI stuff.

## About

Version 3.5 of my notebook software. Turn a folder of markdown into a notebook with extra features.

This is not designed for the general public but certainly *can* be if someone wishes. It is specially designed for my uses (a public blog/notebook, a private notebook, and photo gallery)

## Links

One of the major features is that any internal link is noted at the bottom of each page so you can see what links to this page or from.

Links can either be relative (e.g. `[file](file.md)`) or absolute with a leading `/` (e.g `[file](/path/to/file.md)`). Same goes for media, etc

## Special Markdown Additions

In general, this implements [Python Markdown](https://pypi.python.org/pypi/Markdown) syntax with `extra`, `toc`, and `sane_lists` plugins. In addition, it also implements a few new syntaxes.

### Images with links

Rather than:
    
    [![alt_txt](img.jpg)](img.jpg)

you can simply do:

    !{alt_text}(img.jpg)

### Exclude HTML blocks    

There is also the option to include HTML directly so that it won't be parsed out. Markdown is designed to allow HTML and it works well *most* of the time. This adds another layer to it by truly cutting it all out

This is parsed by `<htmlblock>` and `</htmlblock>` where they must be the only non-white space on a line and be within the first 3 characters. They will be cut out and then replaced later. 

Note that this isn't a *perfect* parsing. It will not look to make sure the block is not in a code block, etc.

### Image Galleries

There is also the option to have image galleries within the post. They are delineated with `<gallery>` and `</gallery>` tags being the only non-white space on a line and within the first three characters. Like `<htmlblock>`, they are *not perfect*, but work most of the time

Galleries are in the following format. This is done this way to match the automatic inclusion of media when uploading

The form should be any of the following:

    <gallery>
    [![alt_txt](/path/to/thumb.jpg)](/path/to/img.jpg)
    optional caption that must be just a single line
        
    ![alt_txt](/path/to/img.jpg)
    
    !{alt_txt}(/path/to/img.jpg)
    </gallery>

Note that the last of those is the Image with Links format noted above.

## Database and Index

The sqlite database is used for caching, search, cross-reference tracking, and a few other minor features. However, the pages are considered "truth" at all times. The database can be rebuilt from all pages with `--reset`

Every time a page is viewed the `mtime` of the markdown file is compared to the database version the database is updated if needed. Therefore, changes to an article are not propagated until the page has been viewed. Alternatively, there is a tool to recache all pages. It can also be configured to do this automatically.

## Search

The built in search engine is experimental but seems to work well enough. It accounts for the ordering of the search term as well as the scores of the pages that link back to any given page.

It does *not* have any advanced settings or controls (yet). 

Pages are searched if they are in the database. Therefore, they must be viewed and/or indexed to be up to date

## Settings

Settings are set via the `NBSETTINGS.py` file. All settings are fully documented there. That also explains additional functionality such as how media is sorted, how new pages are names, the default templates, etc

## Special Pages

There are a few special pages:

* `/_all/path/to/dir` Will show every page in that directory
* `/_todo` Show all todo items
    * `/_todo/txt` shows them in text format
* `/_tags` Show all tags (either in `tags:` metadata or `tt_tag` inline)
* `/_random` Randomly go to a folder

There are others that will depend on the login status and will be in the dropdown

## Other notes:

* Extensions in links do not matter! Every link is converted to `.html` but vising a page with or without an extension will return it to `.html` (unless it is a folder)
* Folders only show if they have parsable items in them. One way to work around this and show empty folders is to include a completely empty `index.md` page
    * When creating new folders via the web app, this is what is done

## New "Media Page"

This option is the same as creating a new page but tries to be simpler. It just presents a single (optional) description box and a place to upload pictures. The title and date are automatically set based on the description (if present), regardless of the auto-title settings.

## Index pages

If there is an `index.md` (or other acceptable extension) in a directory, that will be shown above the directory listings.

The only issue is that these pages cannot be deleted via the web interface. Just delete them manually (or clear their content)

## Known Issues:

- Even if a page is restricted, a non-registered user may still be able to view the title if it has any tags and may be able to view any todo items from that page
    - [ ] Investigate using a hook to fix this
    - Even if/when this is fixed, the template will still be visible

- [ ] Media Viewer? Certain directories?
- Cannot delete `indexm.md` pages

## Draft Pages

A draft page will *only* show for an `edit` user and will show with "`[DRAFT]`" surrounding the text. To make a draft page, it **must** be a page with meta-data and have the metadata:

    draft: true

set.

## Exclusions

All pages may be viewed but if they are excluded, they will not show in the automatic listing. Viewing a directory in an excluded root will not work but pages are viewable if the direct path is known.

Exclusions compare against the following.

- Full path (with leading `/`)
- file/directory name
- directory name with a trailing `/`

For example, `/path/to/file1.md` will compare:

- `/path/to/file1.md`
- `file1.md`

And `/path/to/subdir1` will compare:

- `/path/to/subdir1`
- `/path/to/subdir1/`
- `subdir1`
- `subdir1/`

## Protected Pages, Users, Etc

There is a **very crude** user management.

* Public
    * Can view all pages not password protected
    * No management or editing
* Protected
    * Can view all pages regardless of password protection
    * No management or editing
* Edit
    * Can view all pages
    * Can edit, manage, upload, delete, etc

## Scratch Space

A small amount of scratch space is needed to store sessions, and the DB (by default. That can be changed in the config).


