"""Built-in plugins."""
from .safety import SafetyPlugin
from .distance import DistancePlugin
from .comfort import ComfortPlugin
from .social import SocialPlugin

BUILTIN = {p.contract.name: p for p in (SafetyPlugin, DistancePlugin, ComfortPlugin, SocialPlugin)}

__all__ = ["SafetyPlugin", "DistancePlugin", "ComfortPlugin", "SocialPlugin", "BUILTIN"]
