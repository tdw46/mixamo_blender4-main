import bpy, os
from math import *
from mathutils import *
from bpy.types import Panel, UIList
from .lib.objects import *
from .lib.bones_data import *
from .lib.bones_edit import *
from .lib.bones_pose import *
from .lib.context import *
from .lib.addon import *
from .lib.mixamo import *
from .lib.armature import *
from .lib.constraints import *
from .lib.animation import *
from .lib.maths_geo import *
from .lib.drivers import *
from .lib.custom_props import *
from .lib.version import *

def calculate_roll_difference(bone1, bone2):
    """Calculate the difference in roll between two bones."""
    roll1 = bone1.roll
    roll2 = bone2.roll
    diff = (roll2 - roll1 + pi) % (2 * pi) - pi
    return diff

def align_bone_to_axes(bone, x_axis, y_axis):
    """Align a bone to the given X and Y axes."""
    z_axis = x_axis.cross(y_axis)
    
    bone.x_axis = x_axis.normalized()
    bone.y_axis = y_axis.normalized()
    bone.z_axis = z_axis.normalized()