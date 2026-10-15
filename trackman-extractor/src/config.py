"""Load and validate config.yaml.

Everything tunable lives in config.yaml. This module turns it into a Config
object and rejects typos and out-of-range values up front, so a bad setting
fails before any mouse movement instead of halfway through a capture.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

from src.steps import Step, StepError, parse_flow
from src.ui import Area, Point

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"


class ConfigError(Exception):
    pass


@dataclass
class AppConfig:
    name: str = "TrackMan Baseball Pro"
    bundle_id: str = "dk.trackman.baseball-practice"


@dataclass
class OutputConfig:
    captures_dir: str = "captures"
    logs_dir: str = "logs"
    rosters_dir: str = "rosters"
    image_format: str = "png"


@dataclass
class CaptureConfig:
    view: str = "Hit"
    max_pages_per_player: int = 100
    start_from_top: bool = True


@dataclass
class RegionConfig:
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    window_width: float = 0.0
    window_height: float = 0.0

    @property
    def is_set(self) -> bool:
        return self.width > 0 and self.height > 0


@dataclass
class ScrollConfig:
    unit: str = "pixel"
    amount: object = "auto"  # "auto" or a number
    target_fraction: float = 0.70
    invert: bool = False


@dataclass
class TimingConfig:
    start_delay: float = 3.0
    wait_after_activate: float = 1.0
    wait_after_scroll: float = 0.8
    wait_after_click: float = 0.5
    wait_after_player_load: float = 2.0
    #: Seconds between characters when typing into TrackMan's search box.
    #: Typing faster than it filters can truncate the query.
    type_interval: float = 0.05
    #: How long a `wait_for_text` step waits before giving up.
    wait_for_text_timeout: float = 15.0
    #: How often it re-reads the screen while waiting.
    ocr_poll_interval: float = 0.4


@dataclass
class DetectionConfig:
    pixel_tolerance: int = 24
    unchanged_threshold: float = 0.003
    unchanged_frames_required: int = 2
    overlap_mismatch_threshold: float = 0.005


@dataclass
class HistoryConfig:
    """Reading the History list."""

    #: Safety limit on how far the list is scrolled while discovering athletes.
    max_list_pages: int = 40
    #: Points to scroll the list between reads. Smaller means more overlap and
    #: less chance of stepping over a row.
    scroll_amount: float = 300.0
    #: Consecutive reads with no new row before the list is considered ended.
    unchanged_pages_required: int = 2
    #: What counts as an athlete's name. Strict by default: a loose pattern
    #: turns column headings into athletes, and an invented athlete is much
    #: harder to notice than a missing one.
    name_pattern: str = r"^[A-Z][A-Za-z'\u2019-]+(?:\s+[A-Z][A-Za-z'\u2019.-]+)+$"
    #: An athlete id. A row with one of these but no readable name means OCR
    #: dropped somebody, which is reported rather than passed over.
    id_pattern: str = r"TMBB[-\s]?\d{4,}"


@dataclass
class UIConfig:
    """Click points and readable areas, calibrated with --pick-ui."""

    targets: dict = field(default_factory=dict)
    areas: dict = field(default_factory=dict)


@dataclass
class FlowsConfig:
    """Click sequences for navigating TrackMan, as steps (see src/steps.py)."""

    open_history: list = field(default_factory=list)
    select_player: list = field(default_factory=list)
    open_hit_table: list = field(default_factory=list)
    reset: list = field(default_factory=list)


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    region: RegionConfig = field(default_factory=RegionConfig)
    scroll: ScrollConfig = field(default_factory=ScrollConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    detection: DetectionConfig = field(default_factory=DetectionConfig)
    history: HistoryConfig = field(default_factory=HistoryConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    flows: FlowsConfig = field(default_factory=FlowsConfig)
    path: Path = DEFAULT_CONFIG_PATH

    @property
    def scroll_amount(self) -> float:
        """Pixels (points) or lines to scroll per page."""
        if self.scroll.amount == "auto":
            return round(self.region.height * self.scroll.target_fraction)
        return float(self.scroll.amount)

    @property
    def captures_path(self) -> Path:
        return PROJECT_ROOT / self.output.captures_dir

    @property
    def logs_path(self) -> Path:
        return PROJECT_ROOT / self.output.logs_dir

    @property
    def rosters_path(self) -> Path:
        path = PROJECT_ROOT / self.output.rosters_dir
        path.mkdir(parents=True, exist_ok=True)
        return path


#: Sections built by the generic field-by-field loader. `ui` and `flows` have
#: their own shapes and are handled separately.
SECTIONS = {
    "app": AppConfig,
    "output": OutputConfig,
    "capture": CaptureConfig,
    "region": RegionConfig,
    "scroll": ScrollConfig,
    "timing": TimingConfig,
    "detection": DetectionConfig,
    "history": HistoryConfig,
}


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    path = Path(path)
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except FileNotFoundError:
        raise ConfigError(f"Config file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path} is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain YAML sections like 'scroll:' and 'timing:'")

    unknown = set(data) - set(SECTIONS) - {"ui", "flows"}
    if unknown:
        raise ConfigError(f"Unknown section(s) in config: {', '.join(sorted(unknown))}")

    sections = {name: _build(cls, data.get(name), name) for name, cls in SECTIONS.items()}
    cfg = Config(
        **sections,
        ui=_build_ui(data.get("ui")),
        flows=_build_flows(data.get("flows")),
        path=path,
    )
    _validate(cfg)
    return cfg


def _build_ui(data) -> UIConfig:
    if data is None:
        return UIConfig()
    if not isinstance(data, dict):
        raise ConfigError("'ui' must contain 'targets:' and 'areas:'")
    unknown = set(data) - {"targets", "areas"}
    if unknown:
        raise ConfigError(f"Unknown key(s) in 'ui': {', '.join(sorted(unknown))}")

    targets = {}
    for name, value in (data.get("targets") or {}).items():
        if not isinstance(value, dict) or set(value) - {"x", "y"}:
            raise ConfigError(f"ui.targets.{name} must be 'x:' and 'y:' only")
        targets[name] = Point(float(value.get("x", 0)), float(value.get("y", 0)))

    areas = {}
    for name, value in (data.get("areas") or {}).items():
        allowed = {"x", "y", "width", "height"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise ConfigError(f"ui.areas.{name} must be x/y/width/height only")
        areas[name] = Area(**{key: float(value.get(key, 0)) for key in allowed})
    return UIConfig(targets=targets, areas=areas)


def _build_flows(data) -> FlowsConfig:
    if data is None:
        return FlowsConfig()
    if not isinstance(data, dict):
        raise ConfigError("'flows' must be a section of named step lists")
    known = {f.name for f in fields(FlowsConfig)}
    unknown = set(data) - known
    if unknown:
        raise ConfigError(
            f"Unknown flow(s): {', '.join(sorted(unknown))}. Known: {', '.join(sorted(known))}"
        )
    try:
        return FlowsConfig(**{name: parse_flow(name, data.get(name)) for name in known})
    except StepError as exc:
        raise ConfigError(str(exc)) from None


def _build(cls, data, section):
    if data is None:
        return cls()
    if not isinstance(data, dict):
        raise ConfigError(f"'{section}' must be a section of key: value settings")
    known = {f.name: f.default for f in fields(cls)}
    unknown = set(data) - set(known)
    if unknown:
        raise ConfigError(f"Unknown setting(s) in '{section}': {', '.join(sorted(unknown))}")
    return cls(**{key: _coerce(value, known[key], f"{section}.{key}") for key, value in data.items()})


def _coerce(value, default, key):
    if key == "scroll.amount" and value == "auto":
        return value
    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if isinstance(default, bool):
        if isinstance(value, bool):
            return value
        raise ConfigError(f"{key} must be true or false, got {value!r}")
    if isinstance(default, int) and key != "scroll.amount":
        if is_number and float(value).is_integer():
            return int(value)
        raise ConfigError(f"{key} must be a whole number, got {value!r}")
    if isinstance(default, float) or key == "scroll.amount":
        if is_number:
            return float(value)
        hint = " or 'auto'" if key == "scroll.amount" else ""
        raise ConfigError(f"{key} must be a number{hint}, got {value!r}")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ConfigError(f"{key} must be text, got {value!r}")


def _validate(cfg: Config) -> None:
    def require(ok: bool, message: str) -> None:
        if not ok:
            raise ConfigError(message)

    require(cfg.output.image_format in ("png", "jpg"), "output.image_format must be png or jpg")
    require(cfg.capture.max_pages_per_player >= 1, "capture.max_pages_per_player must be at least 1")
    require(cfg.scroll.unit in ("pixel", "line"), "scroll.unit must be pixel or line")
    require(0.2 <= cfg.scroll.target_fraction <= 0.9, "scroll.target_fraction must be between 0.2 and 0.9")
    if cfg.scroll.amount == "auto":
        require(cfg.scroll.unit == "pixel", "scroll.amount: auto only works with unit: pixel; set a number of lines")
    else:
        require(cfg.scroll.amount > 0, "scroll.amount must be greater than 0")
    for name in ("width", "height", "window_width", "window_height"):
        require(getattr(cfg.region, name) >= 0, f"region.{name} cannot be negative")
    for f in fields(TimingConfig):
        require(getattr(cfg.timing, f.name) >= 0, f"timing.{f.name} cannot be negative")
    d = cfg.detection
    require(1 <= d.pixel_tolerance <= 254, "detection.pixel_tolerance must be between 1 and 254")
    require(0 <= d.unchanged_threshold < 1, "detection.unchanged_threshold must be between 0 and 1")
    require(0 <= d.overlap_mismatch_threshold < 1, "detection.overlap_mismatch_threshold must be between 0 and 1")
    require(d.unchanged_frames_required >= 1, "detection.unchanged_frames_required must be at least 1")
    h = cfg.history
    require(h.max_list_pages >= 1, "history.max_list_pages must be at least 1")
    require(h.scroll_amount > 0, "history.scroll_amount must be greater than 0")
    require(h.unchanged_pages_required >= 1, "history.unchanged_pages_required must be at least 1")
    try:
        re.compile(h.name_pattern)
    except re.error as exc:
        raise ConfigError(f"history.name_pattern is not a valid regular expression: {exc}") from None
    _validate_flow_targets(cfg)


def _validate_flow_targets(cfg: Config) -> None:
    """Catch a flow naming a target that does not exist, before anything clicks."""
    for flow in fields(FlowsConfig):
        for index, step in enumerate(getattr(cfg.flows, flow.name), start=1):
            where = f"flows.{flow.name}[{index}]"
            if step.action == "click" and str(step.value) not in cfg.ui.targets:
                raise ConfigError(
                    f"{where} clicks '{step.value}', which is not in ui.targets. "
                    f"Known: {', '.join(sorted(cfg.ui.targets)) or 'none'}"
                )
            if step.action == "scroll":
                area = str(step.value["area"])  # type: ignore[index]
                if area not in cfg.ui.areas:
                    raise ConfigError(
                        f"{where} scrolls '{area}', which is not in ui.areas. "
                        f"Known: {', '.join(sorted(cfg.ui.areas)) or 'none'}"
                    )
