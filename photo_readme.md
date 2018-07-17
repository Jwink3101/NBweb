# Photo Gallery Readme

You can make any page a gallery by using the extension `.gallery`. The page will be preprocessed into a photo gallery. The format is also conducive to comments, both in-line and not to be printed (but they *will* still be in the page source so it won't be completely private)

The input specification for galleries is made up of meta-data and then blocks. The only new addition to the metadata is the `root` key. 


## Block Types

Inputs are specified as blocks.  Blocks have a path (or title) in *double* - brackets and then, optionally, a comment/description.

A block start must be the very first thing on the line.

There are the following block types. `...` denotes any text. It will be ignored

* `[[path/to/photo.jpg]]`
    * Photo block. The path is relative to `root` specified in the metadata. Or, if `root` is not specified, it is assumed to be relative to the page
* `[[path/to/photo.jpg | path/to/photo2.jpg | path/to/photo3.jpg]]`
    * Multi-photo block. Everything else is the same as a photo block except it will display as a two-column table
* `[[# ... ]]`
    * Private comment block. Nothing until the next block will be printed but do note that this **will still be in the source**
* `[[+]]` or `[[+ Title]]` or `[[+ ## Heading 2]]`
    * Main comment block. If specified, will be printed with the title (unless done with heading noted below)
    * Another option is to do `[[+ # Heading 1]]`, `[[+ ## Heading 2]]`, etc
        * Note the `+` must be before otherwise it will be treated like a hidden comment
* `[[-path/to/photo.jpg]]` - Link block. A link block is like a comment and a photo block combined. The file name will be included and there will be a link to the thumb and full-size version of the photo. Note: these (and *only* these) can also be inline!

File extensions are used if they are given, but are not needed.

### Inline image links

There may be the case where there are photos you wish to include as a link only and not as a shown photo. To do this, use the `[[-path/to/photo.jpg]]` *inline*. 

## Photo Paths

In the main config file, the `photo_root` is specified. The gallery page *cannot link above this root*! Each gallery page **must** also specify a `root` metadata item. Finally, the photo item may contain an additional path (including `..`).

Given that, the following happens when searching for a photo

1. The extension is removed if it is specified
2. The name is filtered (see below) if applicable
3. The filesystem is searched in the following order (see "Internals & Remote Upload")
    1. The `photo_root` + `root` + `block path`
        * If the `block path` has a directory (e.g. `[[subdir/photo.jpg]]` will check `subdir`)
    2. The `photo_root` + `root`
    3. The `photo_root` alone. -- only if `photo_search_from_root = True` in `NBCONFIG`

## Filename Filters

Filters may be applied to file names to removed tags. The default filter will do the following all into `2018-01-01_073853.1`

    2018-01-01_073853.1.1
    2018-01-01_073853.1.1_[tag1,tag2]
    2018-01-01_073853.1.1_(tag1,tag2)

This filter is applied in matching file names and in block names


## Internals & Remote Upload

Since the galleries are likely a subset of a full photo collection and it is not ideal to have to upload an entire library. Internally, NBweb creates symlinks to the source and serves them. This means that on the remote site, you can simply `rsync` (with `--follow-links`) the photo directory inside the scratch folder. As long on on the main server, it is always able to find the photo there (and it will be a actual file and *not* the link).

Internally, when a photo is parsed, first the code looks to see if a file (symlink or direct) exists for the *filtered* name (see above). If the item is a file or an in-tact symlink, it will serve that file. Otherwise, it will search for the correct file (as noted above) and regenerate the symlink. 

Thumbnails are only regenerated if they do not exists.

As noted above, this process allows for certain name changes to not break the image gallery so long as the *filtered* name is the same.

**NOTE**: The scratch space will *not* exactly mirror the original source structure. Items will be placed based on where the gallery file is located and then the path specified within the block.

**KNOWN ISSUES**:  
Due to the above note, it is possible for two files with the same exact name to cause issues if there is ambiguity.


### File Extension

If there is no file-extension specified, the code will search for the file with a `*` glob in that folder ONLY. Any other kind of incomplete path will raise an error if it can't find the photo.

## Photo Types:

The code will recognize the following types: (case INsensitive)

* photos (displayed with an `<img>` type tag).
    * Displays a thumbnail with a link to the original
    * `.jpg`, `.jpeg`, `.jp2`, `.jpx`, `.gif`, `.png`, `.tiff`, `.tff`, `.bmp`
* video (uses a `<video>` tag).
    * Embeds the original. It is suggested to make a smaller version manually first if that matters
    * `.mp4`,`.mov`
* Anything else:
    * Creates a link

## Symlinks

If there are symlinks as any photo specifier, whether they are relative or absolute, the code **will follow them** however, the source must still be above the configured global `photo_root`.

## Example Input 

    Title: Title of the gallery
    Date: 2016-05-07
    root: to/root/ 
    # root is combined with `photo_root` if specified in the config

    [[+ ## Description]]
    Put your description here for the entire gallery if you want it at the top. Notice the comment block. But the comment block will have the title "Description"

    Multi-line is fine. You can even include a Table of Contents. But everything must be within a block!
    
    [TOC]

    [[rel/path/to/photo1]]
    This is a photo/caption block. It can have any *markdown* in it

    And can even have multi-line or

    * Bullets
    * like this

    Even [reference][links] work!
    
    [links]:http://google.com

    Also, beginning or trailing line breaks will be cut.

    [[rel/path/to/photo2]]
    Paths are relative to the root as specified above. They can have `../` in them if you wish.

    [[#]]
    Any block that starts with `[[#` is a comment block. No need to add `#` again until you get to the next block. This will not show in the output

    [[# rel/path/photo4.jpg]]
    Just an example on how one may use a comment block on a photos. This too will not show in the output

    [[photo5.jpg]]
    [[photo6.jpg]] 
    Photos do not need captions

    [[+ photo7.jpg]]
    This will appear as a comment w/o showing photo7 (but with the title)
    
    [[photo8.jpg|photo9.jpg]]
    Multi-photo block
    
    [[photo10.jpg]]
    This is a photo and see also the linked-but-not-show [[-photo11.jpg]]
    
    [[-photo12.jpg]]
    This, like the one above inline, will also just be a link to the photo thumbnail with the full-size one noted

## Photo names

Photos are stored in the root of the notebook in the `_photos` folder and are considered from the root as specified in `root_dir`. This means that if the `root_dir` is set to `/`, the entire path will be be present. It will still work, but if you compile on different machines, it may not be the same on both.

## Updated Images

On the *local* side, large images are just sym-links to their original location so updates to them are, in essence automatic. However, thumbnails are not regenerated if the image's thumbnails already exist. Deleting the thumbnail will cause the thumbnail to be regenerated (and, if applicable, the image to be re-linked)

## Thumbnail Conversion

Thumbnail conversion uses PIL and runs on multiple cores (processes) to speed things up. There is actually a performance hit if very few photos are to be processed but that is worth the benefits when using many photos.

## Remote Site Uploads

Since the system in dynamic but you may not want to store your entire photo library, it works as follows:

Inside of the scratch directory, a directory for photos and thumbnails are created. The first thing the code will do is see if the photo is in the scratch directory, If it is not, it will create a *symlink* to the original photo in the scratch directory. Photos are served from the scratch directory. The server *should* follow the symlinks fine 

It will then make a thumbnail of the photo *if it doesn't exist*.

This means that on the remote site, you can simply `rsync` (with `--follow-links`) the photo directory inside the scratch folder. As long on on the main server, it is always able to find the photo there (and it will be a actual file and *not* the link),



