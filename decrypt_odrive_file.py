import base64
import Crypto.Cipher.AES
import Crypto.Hash.HMAC
import Crypto.Hash.SHA256
import Crypto.Protocol.KDF
import hashlib
import sys
import argparse
import os

SALT_LENGTH = 8
VERSION_LENGTH = 1
CURRENT_VERSION = '1'

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

def decrypt_name(ciphertextName, password):
    try:
        ciphertextBytes = ciphertextName.encode('ascii')
    except UnicodeEncodeError as e:
        print "Invalid filename with exception: {}".format(e)
        sys.exit(1)

    try:
        decodedName = base64.urlsafe_b64decode(ciphertextBytes)
    except TypeError as e:
       print "Invalid filename with exception: {}".format(e)
       sys.exit(1)

    versionNumber = decodedName[:VERSION_LENGTH]

    if versionNumber != CURRENT_VERSION:
        raise ValueError("Encryption version: {} is not supported".format(versionNumber))

    salt = decodedName[VERSION_LENGTH:VERSION_LENGTH + SALT_LENGTH]
    iv = decodedName[VERSION_LENGTH + SALT_LENGTH: VERSION_LENGTH + SALT_LENGTH + Crypto.Cipher.AES.block_size]
    key = derive_key(salt, password)
    ciphertext = decodedName[VERSION_LENGTH + SALT_LENGTH + Crypto.Cipher.AES.block_size:]
    cipher = Crypto.Cipher.AES.new(key, Crypto.Cipher.AES.MODE_CBC, iv)
    paddedPlaintext = cipher.decrypt(ciphertext)

    if not paddedPlaintext.startswith('\0\0\0\0'):
        raise ValueError("Invalid Filename: {}".format(ciphertextName))

    prefixedName = unpad_pkcs7(paddedPlaintext).decode('utf-8')
    plaintextName = prefixedName[4:]

    return plaintextName

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
    parser.add_argument(u"file", type=str, help=u"The file to decrypt")
    parser.add_argument(u"password", type=str, help=u"The passphrase")
    
    return parser.parse_args()

def main():
    args = get_arguments()
    if ( not os.path.isfile(args.file)):
        print "Error: File {} not found".format(args.file)
    else:
        decryptedName = decrypt_name(os.path.basename(args.file),args.password)
        with open(args.file, 'rb') as in_file, open(os.path.join(os.path.dirname(args.file),decryptedName), 'wb') as out_file:
           decrypt_file(in_file, out_file, args.password)
        print "Decrypted file written to {}".format(os.path.abspath(out_file.name))
        in_file.close()
        out_file.close()    

if __name__ == "__main__":
    main()
