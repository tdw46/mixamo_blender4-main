"""
Convenience module for re-exporting commonly used functions and constants.
This module uses star imports intentionally for backward compatibility.
"""

from math import *  # noqa: F403, F401

from mathutils import *  # noqa: F403, F401

from .lib.addon import *  # noqa: F403, F401
from .lib.animation import *  # noqa: F403, F401
from .lib.armature import *  # noqa: F403, F401
from .lib.bones_data import *  # noqa: F403, F401
from .lib.bones_edit import *  # noqa: F403, F401
from .lib.bones_pose import *  # noqa: F403, F401
from .lib.constraints import *  # noqa: F403, F401
from .lib.context import *  # noqa: F403, F401
from .lib.custom_props import *  # noqa: F403, F401
from .lib.drivers import *  # noqa: F403, F401
from .lib.maths_geo import *  # noqa: F403, F401
from .lib.mixamo import *  # noqa: F403, F401
from .lib.objects import *  # noqa: F403, F401
from .lib.version import *  # noqa: F403, F401
