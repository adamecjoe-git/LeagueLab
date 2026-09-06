from typing import Dict, List, Type

from .base import Challenge


_REGISTRY = {}


def register_challenge(cls):
    type_name = getattr(cls, "type_name", None)

    if not type_name or type_name == "base":
        raise ValueError(
            "{} must define a unique type_name.".format(cls.__name__)
        )

    if type_name in _REGISTRY:
        raise ValueError(
            "Challenge type already registered: {}".format(type_name)
        )

    _REGISTRY[type_name] = cls
    return cls


def get_challenge_class(type_name):
    try:
        return _REGISTRY[type_name]
    except KeyError as exc:
        available = ", ".join(sorted(_REGISTRY))
        raise KeyError(
            "Unknown challenge type '{}'. Available: {}".format(
                type_name,
                available,
            )
        ) from exc


def registered_types():
    return sorted(_REGISTRY)
