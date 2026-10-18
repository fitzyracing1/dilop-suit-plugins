"""Dilop: a modular plugin computer for suits.

The suit is a host platform with a standardized plugin bus. Each plugin declares
its capabilities, resource needs and safety envelope; the plugin manager loads,
prioritizes and arbitrates them, and the safety layer can always veto.
"""
from .state import SuitState, Command
from .plugin import Plugin, PluginContract, Resources
from .bus import Bus
from .plugin_manager import PluginManager, MODES
from .power import PowerDecision, decide_power

__all__ = ["SuitState", "Command", "Plugin", "PluginContract", "Resources", "Bus",
           "PluginManager", "MODES", "PowerDecision", "decide_power"]
__version__ = "1.0.0"
