import sys
import argparse
import os
import re

CURRENT_VERSION = 2
CLOUD_FORMAT_KEY = u"#CLOUD"
CLOUD_FORMAT_VERSION_KEY = "#CLOUD-VER:"
XL_FORMAT_KEY = u"#CLOUD-XL"
XL_SIZE_KEY = u"#CLOUD-XL-SIZE:"
XL_THRESHOLD_KEY = u"#CLOUD-XL-THRESHOLD:"
XL_SEGMENTS_KEY = u"#CLOUD-XL-SEGMENTS:"
XL_SEGMENT_NUMBER_KEY = u"#CLOUD-XL-SEGMENT:"
XL_SEGMENT_SIZE_KEY = u"#CLOUD-XL-SEGMENT-SIZE:"
XL_SEGMENT_HASH_KEY = u"#CLOUD-XL-SEGMENT-HASH:"

class Segment(object):
    def __init__(self, segment_number, segment_size, segment_hash):
        self.segment_number = segment_number
        self.segment_size = segment_size
        self.segment_hash = segment_hash

def parse_meta_file(meta_file_contents):
    try:
        if meta_file_contents and len(meta_file_contents) >= 8:
            cloud_format = meta_file_contents[0] == CLOUD_FORMAT_KEY
            cloud_format_version = int(meta_file_contents[1].split(u":")[-1]) if meta_file_contents[1].startswith(CLOUD_FORMAT_VERSION_KEY) else None
            xl_format = meta_file_contents[2] == XL_FORMAT_KEY
            xl_size = int(meta_file_contents[3].split(u":")[-1]) if meta_file_contents[3].startswith(XL_SIZE_KEY) else None
            xl_threshold = int(meta_file_contents[4].split(u":")[-1]) if meta_file_contents[4].startswith(XL_THRESHOLD_KEY) else None
            total_segments = int(meta_file_contents[5].split(u":")[-1]) if meta_file_contents[5].startswith(XL_SEGMENTS_KEY) else None
            segments = []
            for i in xrange(6, len(meta_file_contents)):
                if i < len(meta_file_contents)-2:
                    segment_number = int(meta_file_contents[i].split(u":")[-1]) if meta_file_contents[i].startswith(XL_SEGMENT_NUMBER_KEY) else None
                    segment_size = int(meta_file_contents[i+1].split(u":")[-1]) if XL_SEGMENT_SIZE_KEY in meta_file_contents[i + 1] else None
                    segment_hash = meta_file_contents[i+2].split(u":")[-1] if XL_SEGMENT_HASH_KEY in meta_file_contents[i + 2] else None
                    if segment_size and segment_hash and segment_number is not None:
                        segments.append(Segment(segment_number, segment_size, segment_hash))
            if cloud_format and (cloud_format_version in xrange(1, CURRENT_VERSION+1)) and xl_format and xl_size:
                if total_segments == len(segments):
                    return segments
    except Exception as e:
        print("Problem reading xl meta file contents: {}".format(e))

def get_out_file_name(xl_folder):
    return xl_folder[:-40]

def assemble_all_xl_files(folder):
    for root, dirs, files in os.walk(folder):
        for d in dirs:
            if d.endswith('.xlarge'):
                assemble_one_xl_file(os.path.join(root,d))

def assemble_one_xl_file(xl_folder):
    if ( not os.path.isdir(xl_folder)):
        print("Error: Folder {} not found".format(xl_folder))
    elif ( not os.path.isfile(os.path.join(xl_folder,".meta"))):
        print("Error: XL file is not complete!")
    else:
        out_file_name = get_out_file_name(xl_folder)
        if os.path.isfile(out_file_name):
            print out_file_name + " already exists!"
        else:
            with open(out_file_name, 'wb') as out_file:
                perform_xl_assembly(xl_folder, out_file)

def perform_xl_assembly(xl_folder, out_file):                
    with open(os.path.join(xl_folder, ".meta"), 'rb') as meta_file:
        meta_data = meta_file.read()
    meta_file_contents = []
    for line in meta_data.split(u"\n"):
        if line:
            meta_file_contents.append(line)
    xl_segments = parse_meta_file(meta_file_contents)
    for segment in xl_segments:
        segment_file_name = segment.segment_hash
        with open(os.path.join(os.path.abspath(xl_folder),segment_file_name), 'rb') as in_file:
            add_xl_file_part(in_file, out_file)
    print xl_folder + " reassembly complete! New file is " + out_file.name

def add_xl_file_part(in_file, out_file):
    in_file.seek(0)
    next_chunk = ''
    finished = False
    chunk_size = 4096 * 1024 #4MB
    
    while not finished:
        chunk, next_chunk = next_chunk, in_file.read(chunk_size)
        if len(next_chunk) == 0:
                finished = True
        out_file.write(chunk)

def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(u"--xlfolder", type=str, help=u"The xl folder to assemble", required=False)
    parser.add_argument(u"--folder", type=str, help=u"The folder to start recursive xl assembly", required=False)
    return parser.parse_args()

def main():
    args = get_arguments()
    recurse = 0
    if args.xlfolder is not None:
        folder_path = args.xlfolder
    elif args.folder is not None:
        folder_path = args.folder
        recurse = 1
    else:
        print("Nothing to do! Please use --help or -h for help.")
        return
    if sys.platform.startswith('win32'):
        folder_path = u"\\\\?\\" + folder_path
    
    if recurse:
        assemble_all_xl_files(folder_path)
    else:
        assemble_one_xl_file(folder_path)
    
if __name__ == "__main__":
    main()