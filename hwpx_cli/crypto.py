"""ODF AES-256-CBC HWPX protection, matching the pinned rhwp contract.

Reference: rhwp-password-crypto, commit 1a76570 (MIT).
The contract checksum is SHA-256 of the first 1024 plaintext bytes, not a MAC.
"""

import base64
from copy import deepcopy
import hashlib
import hmac
from io import BytesIO
import os
from zipfile import ZipFile, ZIP_STORED
import zlib

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from lxml import etree as E

from .editing import require
from .package import MAX_ENTRY, MAX_TOTAL, Package, HwpxError, safe_name, xml

OD = "urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
AES = "http://www.w3.org/2001/04/xmlenc#aes256-cbc"
START = "http://www.w3.org/2000/09/xmldsig#sha256"
MANIFEST = "META-INF/manifest.xml"


def tag(name):
    return f"{{{OD}}}{name}"


def attr(node,name):
    require(node is not None, "Incomplete encryption metadata")
    return node.get(tag(name),node.get(name))


def b64(value):
    try:
        return base64.b64decode(value,validate=True)
    except (ValueError,TypeError) as exc:
        raise HwpxError("Invalid encryption metadata encoding") from exc


def entries(raw):
    root = xml(raw.parts.get(MANIFEST,b"<manifest/>"))
    result = []
    seen = set()
    for entry in root.iter(tag("file-entry")):
        enc = entry.find(tag("encryption-data"))
        if enc is not None:
            name = attr(entry,"full-path")
            safe_name(name)
            require(name not in seen and name in raw.parts,"Duplicate or missing encrypted resource")
            seen.add(name)
            result.append((entry,enc,name))
    return root,result


def is_encrypted(data):
    return bool(entries(Package(data,raw_only=True))[1])


def rewrite(raw,parts,stored=()):
    out = BytesIO()
    with ZipFile(out,"w") as z:
        z.comment = raw.comment
        for original in raw.infos:
            info = deepcopy(original)
            if info.filename in stored:
                info.compress_type = ZIP_STORED
            z.writestr(info,parts[info.filename])
    return out.getvalue()


def decrypt(data,password):
    raw = Package(data,raw_only=True)
    root,protected = entries(raw)
    if not protected:
        return data
    require(isinstance(password,str) and bool(password),"Password is required")
    parts = dict(raw.parts)
    total = sum(len(v) for k,v in parts.items() if k not in {p[2] for p in protected})
    for entry,enc,name in protected:
        algorithm = enc.find(tag("algorithm"))
        derivation = enc.find(tag("key-derivation"))
        start = enc.find(tag("start-key-generation"))
        require(attr(algorithm,"algorithm-name") == AES and attr(start,"start-key-generation-name") == START
                and attr(derivation,"key-derivation-name") == OD+"#pbkdf2", "Unsupported HWPX encryption algorithm")
        iterations,keysize = int(attr(derivation,"iteration-count")),int(attr(derivation,"key-size"))
        iv,salt,checksum = b64(attr(algorithm,"initialisation-vector")),b64(attr(derivation,"salt")),b64(attr(enc,"checksum"))
        require(1 <= iterations <= 1000000 and keysize == 32 and len(iv) == 16 and 0 < len(salt) <= 1024
                and len(checksum) == 32 and str(attr(enc,"checksum-type")).endswith("#sha256-1k"),"Unsupported encryption parameters")
        ciphertext = parts[name]
        require(bool(ciphertext) and len(ciphertext)%16 == 0,"Wrong password or corrupt encrypted payload")
        plaintext = None
        for prf in ("sha1","sha256"):
            key = hashlib.pbkdf2_hmac(prf,hashlib.sha256(password.encode("utf-8")).digest(),salt,iterations,32)
            decoder = Cipher(algorithms.AES(key),modes.CBC(iv)).decryptor()
            compressed = decoder.update(ciphertext)+decoder.finalize()
            try:
                inflater = zlib.decompressobj(-15)
                candidate = inflater.decompress(compressed,MAX_ENTRY+1)
                require(len(candidate) <= MAX_ENTRY and not inflater.unconsumed_tail,"Decrypted entry exceeds size limit")
                if inflater.eof and hmac.compare_digest(hashlib.sha256(candidate[:1024]).digest(),checksum):
                    plaintext = candidate
                    break
            except zlib.error:
                pass
        require(plaintext is not None,"Wrong password or corrupt encrypted payload")
        declared = attr(entry,"size")
        require(declared is None or int(declared) == len(plaintext),"Decrypted size differs from manifest")
        parts[name] = plaintext
        total += len(plaintext)
        require(total <= MAX_TOTAL,"Total decrypted size limit exceeded")
        entry.remove(enc)
    parts[MANIFEST] = E.tostring(root,encoding="UTF-8",xml_declaration=True)
    result = rewrite(raw,parts)
    Package(result).validate()
    return result


def protected_path(name):
    return (name.startswith(("BinData/","Chart/","Preview/")) or name == "settings.xml"
            or name.startswith("Contents/") and name.endswith(".xml"))


def encrypt(data,password):
    pkg = Package(data)
    require(not pkg.signed,"Signed documents cannot be encrypted by this tool")
    require(isinstance(password,str) and bool(password),"New password cannot be empty")
    root,previous = entries(pkg)
    require(not previous,"Decrypt before changing encryption")
    parts = dict(pkg.parts)
    stored = set()
    for name,value in parts.items():
        if not protected_path(name) or name.endswith("/"):
            continue
        iv,salt = os.urandom(16),os.urandom(16)
        key = hashlib.pbkdf2_hmac("sha1",hashlib.sha256(password.encode("utf-8")).digest(),salt,1024,32)
        compressor = zlib.compressobj(wbits=-15)
        compressed = compressor.compress(value)+compressor.flush()
        compressed += bytes((-len(compressed))%16)
        encoder = Cipher(algorithms.AES(key),modes.CBC(iv)).encryptor()
        parts[name] = encoder.update(compressed)+encoder.finalize()
        stored.add(name)
        entry = next((e for e in root.findall(tag("file-entry")) if attr(e,"full-path") == name),None)
        if entry is None:
            entry = E.SubElement(root,tag("file-entry"))
        entry.set(tag("full-path"),name)
        entry.set(tag("size"),str(len(value)))
        entry.set(tag("media-type"),"application/xml" if name.endswith(".xml") else "application/octet-stream")
        enc = E.SubElement(entry,tag("encryption-data"))
        def attrs(node,**properties):
            for k,v in properties.items():
                node.set(tag(k.replace("_","-")),v)
        encode = lambda b:base64.b64encode(b).decode("ascii")
        attrs(enc,checksum_type=OD+"#sha256-1k",checksum=encode(hashlib.sha256(value[:1024]).digest()))
        attrs(E.SubElement(enc,tag("algorithm")),algorithm_name=AES,initialisation_vector=encode(iv))
        attrs(E.SubElement(enc,tag("key-derivation")),key_derivation_name=OD+"#pbkdf2",key_size="32",iteration_count="1024",salt=encode(salt))
        attrs(E.SubElement(enc,tag("start-key-generation")),start_key_generation_name=START,key_size="32")
    parts[MANIFEST] = E.tostring(root,encoding="UTF-8",xml_declaration=True)
    result = rewrite(pkg,parts,stored)
    check = Package(decrypt(result,password))
    for name in pkg.parts:
        if name != MANIFEST:
            require(pkg.parts[name] == check.parts[name],"Encryption verification failed")
    return result
