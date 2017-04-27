import base64
import Crypto.Cipher.AES
import Crypto.Hash.HMAC
import Crypto.Hash.SHA256
import Crypto.Protocol.KDF
import hashlib
import sys
import argparse
import os
if sys.platform.startswith('win32'):
    import win32file

SALT_LENGTH = 8
VERSION_LENGTH = 1
CURRENT_VERSION = '1'
INVALID_NAME = 'invalid.name.000'

def hmac_sha_256(password, salt):
    return Crypto.Hash.HMAC.new(password, salt, Crypto.Hash.SHA256).digest()

def derive_key(salt, password):
    KEY_LENGTH = 16
    COST_FACTOR = 5000
    return Crypto.Protocol.KDF.PBKDF2(
        password=password.encode('utf-8'),
        salt=salt,
        dkLen=KEY_LENGTH,
        count=COST_FACTOR,
        prf=hmac_sha_256)

def unpad_pkcs7(s):
    return s[:-ord(s[len(s)-1:])]

def decrypt_name(ciphertext_name, password):
    try:
        ciphertext_bytes = ciphertext_name.encode('ascii')
    except UnicodeEncodeError as e:
        print ciphertext_name + " is an invalid filename (may not be encrypted) with exception: {}".format(e)
        return INVALID_NAME

    try:
        decoded_name = base64.urlsafe_b64decode(ciphertext_bytes)
    except TypeError as e:
       print ciphertext_name + " is an invalid filename (may not be encrypted) with exception: {}".format(e)
       return INVALID_NAME

    version_number = decoded_name[:VERSION_LENGTH]

    if version_number != CURRENT_VERSION:
        print "Encryption version: {} is not supported".format(version_number)
        return INVALID_NAME

    salt = decoded_name[VERSION_LENGTH:VERSION_LENGTH + SALT_LENGTH]
    iv = decoded_name[VERSION_LENGTH + SALT_LENGTH: VERSION_LENGTH + SALT_LENGTH + Crypto.Cipher.AES.block_size]
    key = derive_key(salt, password)
    ciphertext = decoded_name[VERSION_LENGTH + SALT_LENGTH + Crypto.Cipher.AES.block_size:]
    cipher = Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, iv)
    padded_plaintext = cipher.decrypt(ciphertext)

    if not padded_plaintext.startswith('\0\0\0\0'):
        print "Invalid Filename: {}".format(ciphertext_name)
        return INVALID_NAME

    prefixed_name = unpad_pkcs7(padded_plaintext).decode('utf-8')
    plaintext_name = prefixed_name[4:]

    return plaintext_name

def single_file(args,file_path):
    if sys.platform.startswith('win32'):
        #full_file_name = os.path.join(os.path.dirname(file_path), os.path.basename(win32file.GetLongPathName(file_path))) #in case we get a short path (8.3)
        full_file_name = win32file.GetLongPathName(file_path) #in case we get a short path (8.3)
    else:
        full_file_name = file_path
    #print full_file_name
    if (not os.path.isfile(full_file_name) and not os.path.isdir(full_file_name)):
        print "Error: File/Folder {} not found".format(full_file_name)
        return
    elif not full_file_name.endswith(('.cloud', '.cloudf')):
        decrypted_name = decrypt_name(os.path.basename(full_file_name),args.password) 
        if decrypted_name != INVALID_NAME:
            if args.nameonly is False:
                if (os.path.isdir(full_file_name)):
                    if args.renamefolder:
                        os.rename(full_file_name, os.path.join(os.path.dirname(full_file_name),decrypted_name))
                        print "'" + full_file_name + "' renamed to '" + decrypted_name + "'"
                    else:
                        print "'" + full_file_name + "' not renamed to '" + decrypted_name + "'"
                else:
                    with open(full_file_name, 'rb') as in_file, open(os.path.join(os.path.dirname(full_file_name),decrypted_name), 'wb') as out_file:
                        decrypt_file(in_file, out_file, args.password)
                    print "Decrypted file written to {}".format(os.path.abspath(out_file.name))
                    in_file.close()
                    out_file.close()
            else:
                #print "'" + os.path.basename(full_file_name) + "' decrypted to '" + decrypted_name + "'"
                print decrypted_name

def all_files(args, file_path):
    for root, dirs, files in os.walk(file_path):
        for f in files:
            if not f.endswith(('.cloud', '.cloudf')):
                if ((args.filter is None) or (args.filter is not None and args.filter in os.path.join(root,decrypt_name(f,args.password)))):
                    single_file(args,os.path.join(root,f))
        for d in dirs:
            if ((args.filter is None) or (args.filter is not None and args.filter in os.path.join(root,decrypt_name(d,args.password)))):
                single_file(args,os.path.join(root,d))

def decrypt_file(in_file, out_file, password):
    calcHash = hashlib.sha256()
    in_file.seek(0)
    versionNumber = in_file.read(VERSION_LENGTH)
    salt = in_file.read(SALT_LENGTH)      
    iv = in_file.read(Crypto.Cipher.AES.block_size)
    key = derive_key(salt, password)
    cipher = Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, iv)
    next_chunk = ''
    finished = False
    while not finished:
        chunk, next_chunk = next_chunk, cipher.decrypt(in_file.read(4096 * Crypto.Cipher.AES.block_size))
        if len(next_chunk) == 0:
            chunk = unpad_pkcs7(chunk)
            fileHash = chunk[-(calcHash.digest_size):]
            chunk = chunk[:-(calcHash.digest_size)]
            finished = True
        out_file.write(chunk)
        calcHash.update(chunk)

    print "Original Hash:   {}".format("".join("{:02x}".format(ord(c)) for c in fileHash))
    print "Calculated Hash: {}".format(calcHash.hexdigest())

def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument(u"--path", type=str, help=u"The file to decrypt or the folder to start from",required=True)
    parser.add_argument(u"--password", type=str, help=u"The passphrase",required=True)
    parser.add_argument(u"--nameonly", action="store_true", default=False, help=u"Print the decreypted name, only",required=False)
    parser.add_argument(u"--renamefolder", action="store_true", default=False, help=u"Rename if the target is a folder",required=False)
    parser.add_argument(u"--recursive", action="store_true", default=False, help=u"Recurse through given path",required=False)
    parser.add_argument(u"--filter", type=str, help=u"Only process files with this simple substring filter",required=False)
    return parser.parse_args()

def main():
    args = get_arguments()
    file_path = args.path
    if sys.platform.startswith('win32'):
        file_path = u"\\\\?\\" + file_path
    if (not os.path.isfile(file_path) and not os.path.isdir(file_path)):
        print "Error: File/Folder {} not found".format(full_file_name)
        return
    if args.recursive:
        all_files(args, file_path)
    else:
        single_file(args, file_path)
    
if __name__ == "__main__":
    main()
