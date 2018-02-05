This is my plan of modifications for the better new_system

* New pages must be created via `/_new/<path/to/dir>` root.
* Then `edit` route will send an error page if trying to edit what doesn't exist and not through the new route. This way, you cannot use edit to create a new page from the user standpoint.
* There will be some additional attributes if new where the user can specify a title. (not sure how to do it yet, but it is doable). The edit POST will handle that and create the page if it doesn't exist
    * If it does exist, it will be saved with a different name. This way, if you try to make a new page on top of an existing one, it won't be lost! (since we cannot check for this ahead of time! but we want to save it)
* Photos will have their own edit template which is the same as no-ace but no text inside and smaller. Will have to use a query on /_new/ and a keyword arg on edit. Or some kind of special thing for the newtxt keyword
* Directories will be handled  a popup. See `https://www.w3schools.com/js/js_popup.asp`



## Where I left off:

- [X] Integrate new photo sort. make sure it handles npn-jpeg and jpeg.

### 2017-11-09_104738

Mostly done

- [X] Consider sort order within pages

### 2017-11-08_20000

Finished the photo page add. Also added time zone localization.

Photo pages are only given one text field. If that it filled it, the file name is `YYYYMMDD_HHSSMM_<text>` and the content is

    title: Photo: <text>
    date:YYYYMMDD_HHSSMM

If it is not filled in, it is filename `YYYYMMDD_HHSSMM` with content

    title: Photo: YYYYMMDD_HHSSMM
    date:YYYYMMDD_HHSSMM

This took a LONG time to decide on

### 2017-11-08_120053

- [X] Clean up action items for Safari

### 2017-11-08_094731

New files seem to work including detection of existing name. Also handles some edge cases such as non-existant index pages.
- [X] New Folders???
- [X] Interface for new?
    * Need to be cleaned up. See above
- [X] Photo Pages?
- Update Manage
    - [X] Delete button for files
    - [X] Delete with confirm for directories ... or just do not allow?
    - [X] ?? Delete photo posts? -- Or just a "delete + content"
- [X] ??? Uploads into relative path? Is this needed?

### 2017-11-07_215600

Can handle the new  pages with titles.
- [X] Save pages and parse those names (Note I split out the parse part in utils) Need to parse out the name and/or default

### 2017-11-07_202108

I worked commented out the previos `_new` route and started a fresh one. It is calls the `edit` with some keywords. Previous editing works but not new.

- [X] Need to add the title for the form for new pages
- Need to handle photos
- [X] Update the documentation about the lack of quick add and note photo add
- [X] Add settings for default titles.
