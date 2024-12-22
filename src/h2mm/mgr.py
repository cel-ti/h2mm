from dataclasses import dataclass, field, asdict
import json
import logging
import os
import shutil
import typing
import zipfile
import toml
from h2mm.model import H2MMCfg, H2ModRes, H2PathRef, H2Mod
from h2mm.utils import calculate_hash, get_all_eligible_pairs, smart_get_meta
import rarfile

@dataclass
class H2MM:
    cfg: H2MMCfg
    cfg_path: str
    # hash,
    mod_res_index: dict[str, typing.List[H2PathRef]] = field(default_factory=dict)
    mod_install_index: dict[str, str] = field(default_factory=dict)
    manifest_index: dict[str, H2Mod] = field(default_factory=dict)

    @classmethod
    def load(cls, cfg_path: typing.Optional[str] = None):
        if cfg_path is None:
            cfg_path = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "config.toml"
            )
        if not os.path.exists(cfg_path):
            raise RuntimeError(
                f"cfg file not found: {cfg_path}, use H2MMCfg.create to create a new one"
            )

        with open(cfg_path, "r", encoding="utf-8") as f:
            cfg = H2MMCfg(**toml.load(f))

        return cls(cfg=cfg, cfg_path=cfg_path)

    def __load_install_index(self):
        # get or create the installIndex.json at dir(game_path)
        if not os.path.exists(self.install_index_path):
            with open(self.install_index_path, "w", encoding="utf-8") as f:
                json.dump({}, f)
        else:
            with open(self.install_index_path, "r", encoding="utf-8") as f:
                self.mod_install_index = json.load(f)

    def __save_config(self):
        with open(self.cfg_path, "w", encoding="utf-8") as f:
            toml.dump(asdict(self.cfg), f)

    def __save_install_index(self):
        with open(self.install_index_path, "w", encoding="utf-8") as f:
            json.dump(self.mod_install_index, f, indent=2)

    def __post_init__(self):
        self.install_index_path = os.path.join(
            os.path.dirname(self.cfg_path), "installIndex.json"
        )
        self.mod_index_path = os.path.join(
            os.path.dirname(self.cfg_path), "modIndex.json"
        )
        self.manifest_index_path = os.path.join(
            os.path.dirname(self.cfg_path), "manifestCache.json"
        )

        # compare time for last_install_check and the game_path mdate
        if self.cfg.last_install_check < os.path.getmtime(self.cfg.game_path):
            self.reparse_installed_mods()
        else:
            self.__load_install_index()

        self.__load_mod_resource()

    def reparse_installed_mods(self):
        self.cfg.last_install_check = os.path.getmtime(self.cfg.game_path)
        self.__save_config()

        self.mod_install_index.clear()

        for file in os.listdir(os.path.join(self.cfg.game_path, "data")):
            if not os.path.isfile(os.path.join(self.cfg.game_path, "data", file)):
                continue

            if "patch_" not in file:
                continue

            ext = os.path.splitext(file)[1]
            if "patch_" not in ext:
                continue

            hash = calculate_hash(os.path.join(self.cfg.game_path, "data"), file)

            if hash in self.mod_install_index:
                raise RuntimeError(
                    f"mod hash conflict: {hash}, {file} with {self.mod_install_index[hash]}"
                )

            self.mod_install_index[hash] = file

        self.__save_install_index()

    def register_new_mod(self, path: str):
        # check which resource folder the mod is in
        for folder in self.cfg.resource_folders:
            if os.path.exists(os.path.join(folder, path)):
                break
            folder = None

        if folder is None:
            raise Exception(f"Mod {path} not found in any resource folder")

    def add_resource(self, path: str, toResource: str | None = None):
        if toResource is None:
            if len(self.cfg.resources) == 0:
                raise RuntimeError(
                    "No resource folder found", "use add_resource_folder to add one"
                )
            toResource = self.cfg.resources[0]["path"]

        toResource = os.path.abspath(toResource)

        if not os.path.exists(toResource):
            raise RuntimeError(f"Resource folder not found: {toResource}")

        if not os.path.exists(path):
            raise RuntimeError(f"Resource file not found: {path}")

        hash, pathref, manifest = smart_get_meta(path, toResource)

        shutil.copy(path, os.path.join(os.path.basename(toResource), hash))

        if hash not in self.mod_res_index:
            self.mod_res_index[hash] = []

        if manifest:
            self.manifest_index[hash] = manifest

        if pathref in self.mod_res_index[hash]:
            raise RuntimeError(f"Mod resource {path} already exists")

        self.mod_res_index[hash].append(pathref)

    def __load_mod_resource(self):
        if os.path.exists(self.mod_index_path):
            with open(self.mod_index_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
                self.mod_res_index = {
                    hash: [H2PathRef(**pathref) for pathref in pathrefs]
                    for hash, pathrefs in raw.items()
                }

        if os.path.exists(self.manifest_index_path):
            with open(self.manifest_index_path, "r", encoding="utf-8") as f:
                self.manifest_index = json.load(f)

        # compare to each modified in resource
        for resource in self.cfg.resources:
            if os.path.getmtime(resource["path"]) > resource["last_modified"]:
                self.reparse_resource_folder(resource["path"])

    def __save_mod_resource(self):
        with open(self.mod_index_path, "w", encoding="utf-8") as f:
            serialized = {
                hash: [asdict(pathref) for pathref in pathrefs]
                for hash, pathrefs in self.mod_res_index.items()
            }
            json.dump(serialized, f, indent=2, ensure_ascii=False)

        with open(self.manifest_index_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest_index, f, indent=2, ensure_ascii=False)

        self.__save_config()

    def prune_resource_folder(self, path: str):
        for hash, pathrefs in self.mod_res_index.items():
            for pathref in pathrefs:
                if pathref.resourceGroup == path:
                    self.mod_res_index[hash].remove(pathref)

        self.__save_mod_resource()

    def add_resource_folder(self, path: str, skip_existing: bool = False):
        assert os.path.exists(path), f"Resource folder not found: {path}"
        assert os.path.isdir(path), f"Resource folder is not a directory: {path}"

        path = os.path.abspath(path)
        try:
            assert not any(
                resource["path"] == path for resource in self.cfg.resources
            ), f"Resource folder {path} already exists"
        except Exception as e:
            if skip_existing:
                return
            raise e

        self.cfg.resources.append(
            {"path": path, "last_modified": os.path.getmtime(path)}
        )
        self.reparse_resource_folder(path)

    def reparse_resource_folder(self, path: str | int):
        if isinstance(path, int):
            path = self.cfg.resources[path]["path"]
        path = os.path.abspath(path)
        assert os.path.exists(path), f"Resource folder not found: {path}"
        assert any(
            resource["path"] == path for resource in self.cfg.resources
        ), f"Resource folder {path} not in config"

        

        # get resource
        resource: H2ModRes = next(
            resource for resource in self.cfg.resources if resource["path"] == path
        )
        resource["last_modified"] = os.path.getmtime(path)

        self.prune_resource_folder(resource["path"])

        # get all eligible pairs
        eligibles = get_all_eligible_pairs(path)

        # add to manifest
        for pair in eligibles:
            try:
                hash, pathref, manifest = smart_get_meta(pair, resourceGroup=resource["path"])
            except zipfile.BadZipFile:
                logging.warning(f"Bad zip file: {pair[0]}")
                continue
            except rarfile.BadRarFile:
                logging.warning(f"Bad rar file: {pair[0]}")
                continue
            except rarfile.PasswordRequired:
                logging.warning(f"Password required for {pair[0]}")
                continue
            except Exception as e:
                raise e
            if hash in self.manifest_index:
                raise RuntimeError(
                    f"Mod hash conflict: {hash}, {pair[0]} with {self.manifest_index[hash]}"
                )

            if manifest:
                self.manifest_index[hash] = manifest

            if hash not in self.mod_res_index:
                self.mod_res_index[hash] = []

            if pathref not in self.mod_res_index[hash]:
                self.mod_res_index[hash].append(pathref)

        self.__save_mod_resource()

    def list_installed_mods(self):
        table = []
        for hash, file in self.mod_install_index.items():
            manifest = self.manifest_index.get(hash, None)
            if manifest:
                name = manifest.name
                description = manifest.description
            else:
                name = self.mod_res_index[hash][0].name if hash in self.mod_res_index else "Unknown"
                description = "N/A"
            
            table.append(
                {
                    "hash" : hash,
                    "installed_file" : file,
                    "name" : name,
                    "description" : description,
                }
            )
        return table

