"""YAML documents as the file writes them: one loader for the package's areas (structured, text).

PyYAML's safe loader (libyaml's where the wheel has it; never the full loader),
changed where YAML 1.1's reading of a plain value is not what the file says
(spec formats/structured, "Values as the file writes them"):

- a scalar keeps its written text where the parsed value prints differently:
  `10:30` (630), `1.10` (1.1), `012` (10), `0x1F` (31), `0.00001` (1e-05),
  `NO` (False), `~` (None), `.inf`; `12`, `1.5`, `true` and `null` stay a
  number, a boolean and null;
- a timestamp is its text, never a date converted to another zone;
- a key is its text (`on:` is not True);
- a value of an application's own tag (`!override`, `!Ref`) is the plain
  text, list or mapping it tags, without the tag, instead of failing the
  document;
- merge keys (`<<:`) are refused above MAX_PAIRS pairs (a merge-key bomb).
"""

import json

import yaml
from yaml.constructor import ConstructorError, SafeConstructor

MAX_PAIRS = 10_000  # a mapping's pairs after merge keys


class Loader(getattr(yaml, "CSafeLoader", yaml.SafeLoader)):
    """PyYAML's safe loader with the changes of this module."""

    def construct_mapping(self, node, deep=False):
        """A mapping with its keys as the file writes them."""
        self.flatten_mapping(node)
        mapping = {}
        for key, value in node.value:
            name = (
                key.value
                if isinstance(key, yaml.ScalarNode)
                else self.construct_object(key, deep=True)
            )
            mapping[name] = self.construct_object(value, deep=deep)
        return mapping

    def flatten_mapping(self, node):
        """Merge keys as the safe loader merges them, refused above MAX_PAIRS pairs:
        nested merges multiply them."""
        super().flatten_mapping(node)
        if len(node.value) > MAX_PAIRS:
            raise ConstructorError(
                None,
                None,
                f"merge keys give more than {MAX_PAIRS} pairs",
                node.start_mark,
            )


def as_written(construct):
    """A constructor of a plain value that gives the written text where the value prints differently (JSON's spelling)."""

    def constructor(loader: Loader, node: yaml.ScalarNode):
        value = construct(loader, node)
        return value if json.dumps(value) == node.value else node.value

    return constructor


def untagged(loader: Loader, node: yaml.Node):
    """A node of a tag no constructor knows as its plain text, list or mapping; the tag is not kept."""
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


for _tag, _construct in (
    ("int", SafeConstructor.construct_yaml_int),
    ("float", SafeConstructor.construct_yaml_float),
    ("bool", SafeConstructor.construct_yaml_bool),
    ("null", SafeConstructor.construct_yaml_null),
):
    Loader.add_constructor(f"tag:yaml.org,2002:{_tag}", as_written(_construct))
Loader.add_constructor("tag:yaml.org,2002:timestamp", SafeConstructor.construct_scalar)
Loader.add_constructor(None, untagged)


def documents(data: bytes | str) -> list:
    """Every document of a YAML stream, as this module reads them."""
    return list(yaml.load_all(data, Loader=Loader))
