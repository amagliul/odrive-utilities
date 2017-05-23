#!/bin/bash
set -e
ODRIVE_PY="$HOME/temp/odrive python/odrive.py"
RECURSIVE="-maxdepth 1"
if [[ $1 == "-h" ]] || [[ $1 == "--help" ]] ; then
        echo "Usage: unsync_by [-e <extension>] [-s <size in kilobytes>] [-d <days>] [directory path] [-r]"
        echo "Help: Unsync files by extension, size, or days old for a given directory"
        echo "Options:"
        echo "-e --extension  Unsyncs files with the specified extension"
        echo "-s --size       Unsyncs files larger than the specified size in kilobytes"
        echo "-d --days       Unsyncs files older than the specified day"
 echo "-r --recursive  Unsyncs files recursively through the specified path"
        echo "-h --help       Help"
elif [[ $# -gt 2 ]] ; then
    key="$1"
    case $key in
        -e|--extension)
        EXTENSION="$2"
        ;;
        -s|--size)
        SIZE="$2"
        ;;
        -d|--days)
        DAYS="$2"
        ;;
        *)
        echo "Invalid arguments. Please consult help for usage details (-h, --help)."
        exit 1
        ;;
     esac
else
     echo "Invalid arguments. Please consult help for usage details (-h, --help)."
     exit 1
fi
DIRPATH="$3"
if [[ $4 == "-r" ]] || [[ $4 == "--recursive" ]] ; then
     RECURSIVE=""
fi
if [[ $EXTENSION ]] ; then
     echo unsyncing all files of "$EXTENSION" type in "$DIRPATH"
     find "$DIRPATH" $RECURSIVE -name "*$EXTENSION" -type f -exec python "$ODRIVE_PY" unsync {} \;
elif [[ $SIZE ]] ; then
     echo unsyncing all files larger than "$SIZE" kilobytes in "$DIRPATH"
     find "$DIRPATH" $RECURSIVE -size "+${SIZE}k" -type f -exec python "$ODRIVE_PY" unsync {} \;
elif [[ $DAYS ]] ; then
     echo unsyncing all files older than "$DAYS" days in "$DIRPATH"
     find "$DIRPATH" $RECURSIVE -mtime "+${DAYS}" -type f -exec python "$ODRIVE_PY" unsync {} \;
fi