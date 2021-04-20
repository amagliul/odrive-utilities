# odrive-utilities
This repository contains a few odrive utilities.

# Prerequisites / setup

```
git clone https://github.com/amagliul/odrive-utilities.git
virtualenv od_venv
source od_venv/bin/activate
# need these packages.
pip install wheel
pip install pycrypto  
python decrypt_odrive_file.py --help
```

# Synopsis

assemble_xl_file.py - A command-line utility to assemble odrive IFS files (also known as split files or XL files).

```
usage: assemble_xl_file.py [-h] --path PATH [--recursive]
```

```optional arguments:
  -h, --help   show this help message and exit
  --path PATH  The path to process for xl files
  --recursive  Recursive xl assembly for the specified path
```
decrypt_odrive_file.py - A command-line utility to decrypt odrive-encrypted files and folders.

```
usage: decrypt_odrive_file.py [-h] --path PATH --password PASSWORD [--nameonly] [--renamefolder] [--recursive] [--filter FILTER]
```
```
optional arguments:
  -h, --help           show this help message and exit
  --path PATH          The file to decrypt or the folder to start from. **Will not decrypt placeholder files**
  --password PASSWORD  The passphrase
  --nameonly           Print the decrypted name, only
  --renamefolder       Rename if the target is a folder
  --recursive          Recurse through given path
  --filter FILTER      Only process files/folders with this simple substring path filter (ex: 'xlarge')
```                     
odrivecli.py - A branch of the official odrive CLI with recursive sync added

```
usage: 
odrivecli.py [-h] {authenticate,mount,unmount,backup,removebackup,sync,stream,
refresh,unsync,xlthreshold,syncstate,status,deauthorize,emptytrash,shutdown}
```
```
positional arguments:
{authenticate,mount,unmount,backup,removebackup,sync,stream,refresh,
unsync,xlthreshold,syncstate,status,deauthorize,emptytrash,shutdown}
```
```
commands
authenticate        authenticate odrive with an auth key
mount               mount remote odrive path to a local folder
unmount             remove a mount
backup              backup a local folder to a remote odrive path
removebackup        remove a backup job
sync                sync a placeholder
stream              stream placholder/remote file eg. stream path | app - or stream to a file eg. stream path > file.ext
refresh             refresh a folder
unsync              unsync a file or a folder
xlthreshold         split files larger than this threshold
syncstate           get sync status info
status              get status info
deauthorize         deauthorize odrive to unlink the current user and exit
emptytrash          empty odrive trash
shutdown            shutdown odrive
```

odrivecli.py sync -h
```
usage: odrivecli.py sync [-h] [--recursive] [--nodownload] placeholderPath
```

```
positional arguments:
  placeholderPath  the path to the placeholder file
  ```

```
optional arguments:
  -h, --help       show this help message and exit
  --recursive      recursively sync
  --nodownload     do not download (used with --recursive)
  ```
