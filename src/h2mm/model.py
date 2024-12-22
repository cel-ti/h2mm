from dataclasses import asdict, dataclass, field
from datetime import datetime
import os
import typing
import toml


@dataclass(slots=True)
class H2PathRef:
    resourceGroup: str
    path: str
    subpath: str

    def __post_init__(self):
        self.resourceGroup = self.resourceGroup.replace("\\", "/")
        self.path = self.path.replace("\\", "/")
        self.subpath = self.subpath.replace("\\", "/")

    @property
    def name(self):
        return os.path.splitext(os.path.basename(self.path))[0]


@dataclass(slots=True)
class H2Mod:
    name : str
    description : str


class H2ModRes(typing.TypedDict):
    path: str
    last_modified: float


@dataclass(slots=True)
class H2MMCfg:
    game_path: str
    resources: typing.List[H2ModRes] = field(default_factory=list)
    last_install_check: float = field(
        default_factory=lambda: int(datetime.datetime.now().timestamp())
    )

    @classmethod
    def exists(cls, cfgPath: typing.Optional[str] = None):
        if cfgPath is None:
            cfgPath = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "config.toml"
            )
        return os.path.exists(cfgPath)

    @classmethod
    def create(
        cls,
        game_path: str,
        resources: typing.List[H2ModRes] = [],
        ignoreExists: bool = True,
        cfgPath: typing.Optional[str] = None,
    ):
        if cfgPath is None:
            cfgPath = os.path.join(
                os.path.dirname(os.path.realpath(__file__)), "config.toml"
            )

        if ignoreExists and os.path.exists(cfgPath):
            return

        cfg = H2MMCfg(game_path=game_path, resources=resources)
        with open(cfgPath, "w", encoding="utf-8") as f:
            toml.dump(asdict(cfg), f)
        return cfg
