from functools import cache
from hashlib import sha256
import json
import os
import typing
import zipfile
import rarfile
from h2mm.etc import CacheOnModifiedDate
from h2mm.model import H2PathRef


def calculate_hash(path: str, name: str):
    hash = sha256()
    with open(os.path.join(path, name), "rb") as f:
        while chunk := f.read(8192):
            hash.update(chunk)

    if os.path.exists(os.path.join(path, name + ".gpu_resources")):
        with open(os.path.join(path, name + ".gpu_resources"), "rb") as f:
            while chunk := f.read(8192):
                hash.update(chunk)

    if os.path.exists(os.path.join(path, name + ".stream")):
        with open(os.path.join(path, name + ".stream"), "rb") as f:
            while chunk := f.read(8192):
                hash.update(chunk)

    return hash.hexdigest()


def verify_and_get_target_file(filelist: list[str]):
    target_files = []
    for file in filelist:
        ext = os.path.splitext(file)[1]
        if not ext or ext.startswith(".patch_"):
            target_files.append(file)

    if len(target_files) != 1:
        raise ValueError(f"Expected exactly one target file, found {len(target_files)}")

    return target_files[0]

def filter_filelist(filelist: list[str], folder: str):
    if folder == "":
        return filelist
    folderDepth = len(os.path.normpath(folder).split(os.sep))
    files = []
    
    for file in filelist:
        if file.startswith(folder) and not file.endswith("/") and len(file.split("/")) -1 == folderDepth:
            files.append(file)
    return files


@cache
def generate_zip_meta(zip_file: str, folder: str = ""):
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        filelist = zip_ref.namelist()
        filteredList = filter_filelist(filelist, folder)
        file = verify_and_get_target_file(filteredList)

        filehash = sha256()
        with zip_ref.open(file) as f:
            while chunk := f.read(8192):
                filehash.update(chunk)

        if file + ".gpu_resources" in filelist:
            with zip_ref.open(file + ".gpu_resources") as f:
                while chunk := f.read(8192):
                    filehash.update(chunk)

        if file + ".stream" in filelist:
            with zip_ref.open(file + ".stream") as f:
                while chunk := f.read(8192):
                    filehash.update(chunk)

        if folder + "manifest.json" in filelist:
            with zip_ref.open("manifest.json") as f:
                manifest = json.load(f)
        else:
            manifest = None

        return filehash.hexdigest(), manifest


def calculate_zip_hash(zip_file: str, folder: str = ""):
    return generate_zip_meta(zip_file, folder)[0]


@CacheOnModifiedDate()
def generate_folder_meta(path: str):
    filelist = os.listdir(path)
    filelist = [file for file in filelist if os.path.isfile(os.path.join(path, file))]
    if "manifest.json" in filelist:
        with open(os.path.join(path, "manifest.json"), "r") as f:
            manifest = json.load(f)
    else:
        manifest = None

    target_file = verify_and_get_target_file(filelist)
    return calculate_hash(path, target_file), manifest


def calculate_folder_hash(path: str):
    return generate_folder_meta(path)[0]


@cache
def generate_rar_meta(path: str, folder: str = ""):
    with rarfile.RarFile(path, "r") as rar_ref:
        filelist = rar_ref.namelist()
        filteredList = filter_filelist(filelist, folder)
        file = verify_and_get_target_file(filteredList)

        filehash = sha256()
        with rar_ref.open(file) as f:
            while chunk := f.read(8192):
                filehash.update(chunk)

        if file + ".gpu_resources" in filelist:
            with rar_ref.open(file + ".gpu_resources") as f:
                while chunk := f.read(8192):
                    filehash.update(chunk)

        if file + ".stream" in filelist:
            with rar_ref.open(file + ".stream") as f:
                while chunk := f.read(8192):
                    filehash.update(chunk)

        if folder + "manifest.json" in filelist:
            with rar_ref.open("manifest.json") as f:
                manifest = json.load(f)
        else:
            manifest = None

        return filehash.hexdigest(), manifest


def calculate_rar_hash(path: str, folder: str = ""):
    return generate_rar_meta(path, folder)[0]


def smart_get_meta(path: str | typing.Tuple[str, ...], resourceGroup: str):
    if isinstance(path, str) and not os.path.isfile(path) or (isinstance(path, tuple) and len(path) ==1 and (path:= path[0])):
        hvalue, manifest = generate_folder_meta(path)
        return (
            hvalue,
            H2PathRef(
                path=os.path.relpath(path, resourceGroup),
                subpath="",
                resourceGroup=resourceGroup,
            ),
            manifest,
        )
    elif (isinstance(path, tuple) and len(path) == 2 and path[0].endswith(".zip")):
        hvalue, manifest = generate_zip_meta(path[0], path[1])
        return (
            hvalue,
            H2PathRef(path=os.path.relpath(path[0], resourceGroup), subpath=path[1], resourceGroup=resourceGroup),
            manifest,
        )
    elif (isinstance(path, tuple) and len(path) == 2 and path[0].endswith(".rar")):
        hvalue, manifest = generate_rar_meta(path[0], path[1])
        return (
            hvalue,
            H2PathRef(path=os.path.relpath(path[0], resourceGroup), subpath=path[1], resourceGroup=resourceGroup),
            manifest,
        )
    elif path.endswith(".zip"):
        hvalue, manifest = generate_zip_meta(path)
        return (
            hvalue,
            H2PathRef(path=os.path.relpath(path, resourceGroup), subpath="", resourceGroup=resourceGroup),
            manifest,
        )
    elif path.endswith(".rar"):
        hvalue, manifest = generate_rar_meta(path)
        return (
            hvalue,
            H2PathRef(path=os.path.relpath(path, resourceGroup), subpath="", resourceGroup=resourceGroup),
            manifest,
        )
    else:
        raise ValueError(f"Unsupported file type: {path}")


def _recursive_get_eligible_for_zip(zip_file: zipfile.ZipFile | rarfile.RarFile):
    eligibles = []
    filelist = []
    folders = [""]
    for file in zip_file.namelist():
        if os.path.isdir(file) or file.endswith("/"):
            folders.append(file)
        else:
            filelist.append(file)

    for folder in folders:
        filteredFileList = [
            os.path.basename(file)
            for file in filelist
            if os.path.dirname(file) == folder or os.path.dirname(file) + "/" == folder
        ]
        if not filteredFileList:
            continue
        try:
            target_file = verify_and_get_target_file(filteredFileList)
        except ValueError:
            continue
        if target_file:
            if isinstance(zip_file, zipfile.ZipFile):
                name = zip_file.fp.name
            elif isinstance(zip_file, rarfile.RarFile):
                name = zip_file.filename
            eligibles.append((name.replace("\\", "/"), folder.replace("\\", "/")))

    return eligibles


def get_all_eligible_pairs(path: str) -> typing.List[str]:
    eligibles = []
    namelist = os.listdir(path)
    compressed_files = [
        file for file in namelist if file.endswith(".zip") or file.endswith(".rar")
    ]
    folders = [file for file in namelist if os.path.isdir(os.path.join(path, file))]
    remaining = [
        file
        for file in namelist
        if file not in compressed_files and file not in folders
    ]
    try:
        target_file = verify_and_get_target_file(remaining)
        if target_file:
            eligibles.append((path.replace("\\", "/"),))
    except ValueError:
        pass

    for folder in folders:
        if folder.startswith(".") or folder.startswith("_"):
            continue
        eligibles.extend(get_all_eligible_pairs(os.path.join(path, folder)))

    for compressed_file in compressed_files:
        if compressed_file.endswith(".zip"):
            with zipfile.ZipFile(os.path.join(path, compressed_file), "r") as zip_ref:
                eligibles.extend(_recursive_get_eligible_for_zip(zip_ref))
        elif compressed_file.endswith(".rar"):
            with rarfile.RarFile(os.path.join(path, compressed_file), "r") as rar_ref:
                eligibles.extend(_recursive_get_eligible_for_zip(rar_ref))

    return eligibles


import wcwidth  # noqa

def get_string_width(s):
    """Get the display width of a string, accounting for CJK characters"""
    return sum(wcwidth.wcwidth(c) for c in s)

def wrap_text(text, width):
    """Wrap text accounting for CJK character widths"""
    text = str(text).strip()
    lines = []
    current_line = []
    current_width = 0
    
    for char in text:
        char_width = wcwidth.wcwidth(char)
        if current_width + char_width > width:
            lines.append(''.join(current_line))
            current_line = [char]
            current_width = char_width
        else:
            current_line.append(char)
            current_width += char_width
    
    if current_line:
        lines.append(''.join(current_line))
    
    return '\n'.join(lines)
