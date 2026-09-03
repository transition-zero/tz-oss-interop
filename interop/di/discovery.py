from __future__ import annotations

import ast
import importlib
import importlib.metadata
import importlib.util
import logging
import pkgutil
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import ModuleType

from interop.adapters.inbound.base import Launcher
from interop.core.pipeline import Sink, Source, TranslationStep, Validator
from interop.core.plugin_errors import PluginCollisionError
from interop.ports.errors import UserInputError

log = logging.getLogger(__name__)


class Category(StrEnum):
    SOURCES = "sources"
    STEPS = "steps"
    SINKS = "sinks"
    VALIDATORS = "validators"
    ADAPTERS = "adapters"
    LAUNCHERS = "launchers"


# Categories whose registered classes must explicitly inherit from a fixed
# Protocol. Adapters are checked at factory time instead, because the port
# they target varies per call (FilesystemPort today, LoggerPort etc. tomorrow).
_REQUIRED_BASE: dict[Category, type] = {
    Category.SOURCES: Source,
    Category.STEPS: TranslationStep,
    Category.SINKS: Sink,
    Category.VALIDATORS: Validator,
}


_ENTRY_POINT_GROUP = {
    Category.SOURCES: "interop.sources",
    Category.STEPS: "interop.steps",
    Category.SINKS: "interop.sinks",
    Category.VALIDATORS: "interop.validators",
    Category.ADAPTERS: "interop.adapters",
}


class PluginInheritanceError(UserInputError, TypeError):
    def __init__(self, category: Category, cls: type, expected: type, location: str) -> None:
        super().__init__(
            f"{cls.__module__}.{cls.__qualname__} at {location} declares "
            f"name={getattr(cls, 'name', '?')!r} in {category.value!r} but does not "
            f"inherit from {expected.__name__}. Plugins must declare their Protocol "
            f"explicitly: `class Foo({expected.__name__}): ...`"
        )
        self.category = category
        self.cls = cls
        self.expected = expected
        self.location = location


class MissingAdapterPortError(UserInputError, TypeError):
    def __init__(self, cls: type, location: str) -> None:
        super().__init__(
            f"{cls.__module__}.{cls.__qualname__} at {location} declares "
            f"name={getattr(cls, 'name', '?')!r} but no 'port' attribute. "
            f"Adapters must declare which Port Protocol they serve: "
            f"`port: ClassVar[type] = FooPort`."
        )
        self.cls = cls
        self.location = location


@dataclass
class LazyPlugin:
    # Off-the-shelf sources/steps/sinks pull in the heavy modelling stack
    # (pypsa, polars, h5py) at module import. Deferring that import until the
    # plugin is actually resolved keeps REPL startup from paying for plugins the
    # session never touches. The inheritance check that eager discovery runs up
    # front happens here instead, on first resolve.
    name: str
    category: Category
    location: str
    _load: Callable[[], type]
    _resolved: type | None = field(default=None)

    def resolve(self) -> type:
        if self._resolved is None:
            cls = self._load()
            required_protocol = _REQUIRED_BASE[self.category]
            if required_protocol not in cls.__mro__:
                raise PluginInheritanceError(self.category, cls, required_protocol, self.location)
            self._resolved = cls
        return self._resolved


@dataclass
class Registry:
    sources: dict[str, LazyPlugin] = field(default_factory=dict)
    steps: dict[str, LazyPlugin] = field(default_factory=dict)
    sinks: dict[str, LazyPlugin] = field(default_factory=dict)
    validators: dict[str, LazyPlugin] = field(default_factory=dict)
    # Adapters are bucketed by the Port they declare so two adapters serving
    # different ports may share a name without collision.
    adapters: dict[type, dict[str, type]] = field(default_factory=dict)
    # Launchers get their own flat bucket, not the port-keyed one above: a
    # launcher is a composition-root concern (main.py selects one, core never
    # touches it), not a driving/driven port, so it doesn't declare a `port`.
    launchers: dict[str, type] = field(default_factory=dict)
    _locations: dict[tuple[Category, str], str] = field(default_factory=dict)
    _adapter_locations: dict[tuple[type, str], str] = field(default_factory=dict)
    _launcher_locations: dict[str, str] = field(default_factory=dict)

    def add(self, category: Category, cls: type, location: str) -> None:
        name = getattr(cls, "name", None)
        if not isinstance(name, str) or not name:
            return
        match category:
            case Category.ADAPTERS:
                self._add_adapter(cls, name, location)
            case Category.LAUNCHERS:
                self._add_launcher(cls, name, location)
            case Category.SOURCES | Category.STEPS | Category.SINKS | Category.VALIDATORS:
                # Eager path (entry points, project-local): the class is already
                # imported, so validate its inheritance now and store it
                # pre-resolved rather than re-importing it on first use.
                required_protocol = _REQUIRED_BASE[category]
                if required_protocol not in cls.__mro__:
                    raise PluginInheritanceError(category, cls, required_protocol, location)
                self._add_pipeline_node(
                    LazyPlugin(name, category, location, lambda: cls, _resolved=cls)
                )

    def add_lazy(
        self, category: Category, name: str, location: str, load: Callable[[], type]
    ) -> None:
        self._add_pipeline_node(LazyPlugin(name, category, location, load))

    def _add_pipeline_node(self, lazy: LazyPlugin) -> None:
        bucket = self.pipeline_node_bucket(lazy.category)
        is_name_already_taken = lazy.name in bucket
        if is_name_already_taken:
            prior = self._locations[(lazy.category, lazy.name)]
            raise PluginCollisionError(lazy.category.value, lazy.name, prior, lazy.location)
        bucket[lazy.name] = lazy
        self._locations[(lazy.category, lazy.name)] = lazy.location

    def _add_adapter(self, cls: type, name: str, location: str) -> None:
        declared_port = getattr(cls, "port", None)
        if not isinstance(declared_port, type):
            raise MissingAdapterPortError(cls, location)
        is_inheriting_declared_port = declared_port in cls.__mro__
        if not is_inheriting_declared_port:
            raise PluginInheritanceError(Category.ADAPTERS, cls, declared_port, location)
        port_bucket = self.adapters.setdefault(declared_port, {})
        is_name_already_taken = name in port_bucket
        if is_name_already_taken:
            prior = self._adapter_locations[(declared_port, name)]
            raise PluginCollisionError(Category.ADAPTERS, name, prior, location)
        port_bucket[name] = cls
        self._adapter_locations[(declared_port, name)] = location

    def _add_launcher(self, cls: type, name: str, location: str) -> None:
        if Launcher not in cls.__mro__:
            raise PluginInheritanceError(Category.LAUNCHERS, cls, Launcher, location)
        is_name_already_taken = name in self.launchers
        if is_name_already_taken:
            prior = self._launcher_locations[name]
            raise PluginCollisionError(Category.LAUNCHERS, name, prior, location)
        self.launchers[name] = cls
        self._launcher_locations[name] = location

    def pipeline_node_bucket(self, category: Category) -> dict[str, LazyPlugin]:
        match category:
            case Category.SOURCES:
                return self.sources
            case Category.STEPS:
                return self.steps
            case Category.SINKS:
                return self.sinks
            case Category.VALIDATORS:
                return self.validators
            case Category.ADAPTERS:
                raise ValueError("adapters are bucketed by port; use Registry.adapters[port]")
            case Category.LAUNCHERS:
                raise ValueError(
                    "launchers are bucketed separately; use Registry.launcher_bucket()"
                )

    def adapter_bucket(self, port: type) -> dict[str, type]:
        return self.adapters.get(port, {})

    def launcher_bucket(self) -> dict[str, type]:
        return self.launchers


def discover(project_root: Path | None = None) -> Registry:
    registry = Registry()
    _discover_off_the_shelf_plugins(registry)
    _discover_entry_points(registry)
    _discover_project_local(registry, project_root or Path.cwd())
    return registry


def _discover_off_the_shelf_plugins(registry: Registry) -> None:
    import interop.plugins as plugins_pkg

    plugins_root = Path(plugins_pkg.__file__).parent
    for category in (Category.SOURCES, Category.STEPS, Category.SINKS, Category.VALIDATORS):
        category_dir = plugins_root / category.value
        if not category_dir.is_dir():
            continue
        _scan_lazy_pipeline_nodes(
            registry,
            category,
            category_dir,
            package=f"interop.plugins.{category.value}",
        )

    import interop.adapters.outbound as outbound_pkg

    outbound_root = Path(outbound_pkg.__file__).parent
    _scan_and_register_packages(
        registry,
        Category.ADAPTERS,
        outbound_root,
        package="interop.adapters.outbound",
    )

    import interop.adapters.inbound as inbound_pkg

    inbound_root = Path(inbound_pkg.__file__).parent
    _scan_and_register_packages(
        registry,
        Category.LAUNCHERS,
        inbound_root,
        package="interop.adapters.inbound",
    )


def _is_private(name: str) -> bool:
    return name.startswith("_")


def _scan_lazy_pipeline_nodes(
    registry: Registry, category: Category, directory: Path, *, package: str
) -> None:
    # Read each plugin's `name` straight from the source with ast (no execution),
    # so the heavy module body is imported only when the plugin is resolved.
    for _finder, module_name, is_pkg in pkgutil.iter_modules([str(directory)]):
        if _is_private(module_name):
            continue
        full = f"{package}.{module_name}"
        if is_pkg:
            _scan_lazy_pipeline_nodes(registry, category, directory / module_name, package=full)
            continue
        path = directory / f"{module_name}.py"
        for class_name, plugin_name in _plugin_classes_in_source(path):
            registry.add_lazy(category, plugin_name, full, _class_loader(full, class_name))


def _class_loader(module: str, class_name: str) -> Callable[[], type]:
    def load() -> type:
        obj = getattr(importlib.import_module(module), class_name)
        if not isinstance(obj, type):
            raise TypeError(f"{module}.{class_name} is not a class")
        return obj

    return load


def _plugin_classes_in_source(path: Path) -> list[tuple[str, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    classes = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        plugin_name = _declared_plugin_name(node)
        if plugin_name is not None:
            classes.append((node.name, plugin_name))
    return classes


def _declared_plugin_name(node: ast.ClassDef) -> str | None:
    # Mirror Registry.add's guard: a class is a plugin iff its body assigns a
    # non-empty string to `name`. Both `name: ClassVar[str] = "x"` (AnnAssign)
    # and a bare `name = "x"` (Assign) count.
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            target, value = stmt.target.id, stmt.value
        elif (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
        ):
            target, value = stmt.targets[0].id, stmt.value
        else:
            continue
        if (
            target == "name"
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
            and value.value
        ):
            return value.value
    return None


def _scan_and_register_packages(
    registry: Registry, category: Category, directory: Path, *, package: str
) -> None:
    for _finder, module_name, is_pkg in pkgutil.iter_modules([str(directory)]):
        if _is_private(module_name):
            continue
        full = f"{package}.{module_name}"
        if is_pkg:
            _scan_and_register_packages(registry, category, directory / module_name, package=full)
            continue
        module = importlib.import_module(full)
        _register_module_classes(registry, category, module, full)


def _discover_entry_points(registry: Registry) -> None:
    for category, group in _ENTRY_POINT_GROUP.items():
        for ep in importlib.metadata.entry_points(group=group):
            loaded = ep.load()
            if not isinstance(loaded, type):
                log.warning("Entry point %r in %r is not a class; skipping", ep.name, group)
                continue
            registry.add(category, loaded, f"entry-point {group}:{ep.name}")


def _discover_project_local(registry: Registry, project_root: Path) -> None:
    plugins_root = project_root / "plugins"
    if not plugins_root.is_dir():
        return
    for category in Category:
        category_dir = plugins_root / category.value
        if not category_dir.is_dir():
            continue
        for py_file in sorted(category_dir.rglob("*.py")):
            relative = py_file.relative_to(category_dir)
            is_private_path = any(_is_private(part) for part in relative.parts)
            if is_private_path:
                continue
            module = _load_path(py_file, category, relative)
            _register_module_classes(registry, category, module, str(py_file))


def _load_path(path: Path, category: Category, relative: Path) -> ModuleType:
    """Import a project-local plugin file under a synthetic module name.

    The module goes into `sys.modules` before it is executed, because anything running
    at class-creation time may look its own module back up by name: `@dataclass` reads
    `sys.modules[cls.__module__].__dict__` to tell a `ClassVar` annotation from a field,
    and `typing.get_type_hints` and `pickle` do the same. Executing first leaves those
    lookups resolving to `None`. A failed import takes its half-built module back out
    rather than leaving it to be found.
    """
    dotted_subpath = ".".join(relative.with_suffix("").parts)
    synthetic = f"_interop_local_plugins.{category.value}.{dotted_subpath}"
    spec = importlib.util.spec_from_file_location(synthetic, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load project-local plugin: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[synthetic] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        del sys.modules[synthetic]
        raise
    return module


def _register_module_classes(
    registry: Registry, category: Category, module: ModuleType, location: str
) -> None:
    for attr in vars(module).values():
        is_class_defined_in_this_module = (
            isinstance(attr, type) and attr.__module__ == module.__name__
        )
        if not is_class_defined_in_this_module:
            continue
        registry.add(category, attr, location)
