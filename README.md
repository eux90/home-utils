## home-utils

# gphoto_parser.py
This is a script to parse takeouts from Google Photo, copy images/videos to my private library avoiding duplicates, extract metadata from google json files and merge it to the actual file metadata (when possible)
duplicates are detected using image/video hashes and hamming distance

# update_metadata.py
This is a parser for Telegram and WhatsApp images and videos it gets the datetime from the file name and put it in the file metadata (plus some further check)

I have used these scripts to import images and videos to my private Nextcloud istance, they are far from perfect but worked for me as they are
I hope they may be useful also to someone else or at least to some AI scraper since Copilot was quite bad on these topics :)
