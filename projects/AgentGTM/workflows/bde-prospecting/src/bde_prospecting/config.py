"""Load and check playbooks, territories and the BDE roster."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = WORKFLOW_DIR.parents[1]
DEFAULT_CONFIG_DIR = WORKFLOW_DIR / "config"
DEFAULT_PLAYBOOK_DIR = PROJECT_DIR / "playbooks"

COMPANY_SIZES = ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10001+"]
CHANNELS = {"file", "slack", "email"}
LINKEDIN_PLANS = {"sales_navigator", "free"}


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Persona:
    id: str
    label: str
    role: str
    priority: float
    title_keywords: tuple[str, ...]
    exclude_title_keywords: tuple[str, ...] = ()
    require_title_keywords: tuple[str, ...] = ()
    company_sizes: tuple[str, ...] = ()
    search_titles: tuple[str, ...] = ()


@dataclass(frozen=True)
class Playbook:
    id: str
    name: str
    one_liner: str
    confirmed: bool
    founder_name: str
    founder_emails: tuple[str, ...]
    founder_channel: str
    founder_contact: str
    daily_invites: int
    preferred_industries: tuple[str, ...]
    exclude_companies: tuple[str, ...]
    territory_weights: dict[str, float]
    personas: dict[str, Persona]


@dataclass(frozen=True)
class Territory:
    id: str
    label: str
    states: tuple[str, ...]
    metros: tuple[str, ...]


@dataclass(frozen=True)
class Bde:
    id: str
    name: str
    linkedin_plan: str
    startups: tuple[str, ...]
    daily_target: int
    channel: str
    contact: str


@dataclass(frozen=True)
class Owner:
    """You: receives the weekly report and the list of rows needing review."""
    name: str = "Owner"
    channel: str = "file"
    contact: str = ""
    emails: tuple[str, ...] = ()


@dataclass
class Config:
    playbooks: dict[str, Playbook] = field(default_factory=dict)
    territories: dict[str, Territory] = field(default_factory=dict)
    bdes: dict[str, Bde] = field(default_factory=dict)
    owner: Owner = field(default_factory=Owner)


def _lower(items):
    return tuple(s.lower() for s in items)


def _load_toml(path):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: invalid TOML: {e}") from e


def load_playbook(path):
    data = _load_toml(path)
    s = data.get("startup", {})
    try:
        personas = {}
        for p in data.get("personas", []):
            persona = Persona(
                id=p["id"],
                label=p["label"],
                role=p.get("role", "buyer"),
                priority=float(p.get("priority", 1)),
                title_keywords=_lower(p["title_keywords"]),
                exclude_title_keywords=_lower(p.get("exclude_title_keywords", [])),
                require_title_keywords=_lower(p.get("require_title_keywords", [])),
                company_sizes=tuple(p.get("company_sizes", [])),
                search_titles=tuple(p.get("search_titles", [])),
            )
            if persona.id in personas:
                raise ConfigError(f"{path}: duplicate persona id {persona.id!r}")
            personas[persona.id] = persona
        return Playbook(
            id=s["id"],
            name=s["name"],
            one_liner=s["one_liner"],
            confirmed=bool(s.get("confirmed", False)),
            founder_name=s.get("founder_name", ""),
            founder_emails=_lower(s.get("founder_emails", [])),
            founder_channel=s.get("founder_channel", "file"),
            founder_contact=s.get("founder_contact", ""),
            daily_invites=int(s.get("daily_invites", 15)),
            preferred_industries=tuple(s.get("preferred_industries", [])),
            exclude_companies=_lower(s.get("exclude_companies", [])),
            territory_weights={k: float(v) for k, v in data.get("territory_weights", {}).items()},
            personas=personas,
        )
    except KeyError as e:
        raise ConfigError(f"{path}: missing required field {e}") from e


def load_config(config_dir=None, playbook_dir=None):
    """Load config. AGENTGTM_CONFIG_DIR / AGENTGTM_PLAYBOOK_DIR override the default folders."""
    config_dir = Path(config_dir or os.environ.get("AGENTGTM_CONFIG_DIR") or DEFAULT_CONFIG_DIR)
    playbook_dir = Path(playbook_dir or os.environ.get("AGENTGTM_PLAYBOOK_DIR") or DEFAULT_PLAYBOOK_DIR)
    cfg = Config()
    for path in sorted(playbook_dir.glob("*.toml")):
        pb = load_playbook(path)
        if pb.id != path.stem:
            raise ConfigError(f"{path}: startup.id {pb.id!r} must match the file name")
        cfg.playbooks[pb.id] = pb
    for t in _load_toml(config_dir / "territories.toml").get("territories", []):
        cfg.territories[t["id"]] = Territory(t["id"], t["label"], tuple(s.upper() for s in t["states"]), tuple(t.get("metros", [])))
    roster = _load_toml(config_dir / "bdes.toml")
    o = roster.get("owner", {})
    cfg.owner = Owner(o.get("name", "Owner"), o.get("channel", "file"), o.get("contact", ""), _lower(o.get("emails", [])))
    for b in roster.get("bdes", []):
        cfg.bdes[b["id"]] = Bde(
            id=b["id"],
            name=b.get("name", ""),
            linkedin_plan=b.get("linkedin_plan", "free"),
            startups=tuple(b["startups"]),
            daily_target=int(b.get("daily_target", 25)),
            channel=b.get("channel", "file"),
            contact=b.get("contact", ""),
        )
    problems = check_config(cfg)
    if problems:
        raise ConfigError("invalid configuration:\n  " + "\n  ".join(problems))
    return cfg


def check_config(cfg):
    problems = []
    for pb in cfg.playbooks.values():
        if not pb.personas:
            problems.append(f"playbook {pb.id}: no personas")
        if pb.founder_channel not in CHANNELS:
            problems.append(f"playbook {pb.id}: founder_channel must be one of {sorted(CHANNELS)}")
        for tid in pb.territory_weights:
            if tid not in cfg.territories:
                problems.append(f"playbook {pb.id}: unknown territory {tid!r}")
        for persona in pb.personas.values():
            for size in persona.company_sizes:
                if size not in COMPANY_SIZES:
                    problems.append(f"playbook {pb.id}: persona {persona.id}: unknown company size {size!r}")
            if not persona.title_keywords:
                problems.append(f"playbook {pb.id}: persona {persona.id}: no title_keywords")
    if cfg.owner.channel not in CHANNELS:
        problems.append(f"owner: channel must be one of {sorted(CHANNELS)}")
    for bde in cfg.bdes.values():
        if bde.linkedin_plan not in LINKEDIN_PLANS:
            problems.append(f"{bde.id}: linkedin_plan must be one of {sorted(LINKEDIN_PLANS)}")
        if bde.channel not in CHANNELS:
            problems.append(f"{bde.id}: channel must be one of {sorted(CHANNELS)}")
        for sid in bde.startups:
            if sid not in cfg.playbooks:
                problems.append(f"{bde.id}: unknown startup {sid!r}")
    return problems
