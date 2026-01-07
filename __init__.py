# ***** BEGIN GPL LICENSE BLOCK *****
#
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ***** END GPL LICENCE BLOCK *****


# bl_info = {
#     "name": "Mixamo Rig",
#     "author": "Mixamo - Xin + BeyondDev",
#     "version": (1, 1, 8),
#     "blender": (4, 2, 0),
#     "location": "3D View > Mixamo> Control Rig",
#     "description": "Generate a control rig from the selected Mixamo Fbx skeleton",
#     "category": "Animation",
#     "doc_url": "https://github.com/tdw46/mixamo_blender4-main/tree/main",
#     "tracker_url": "https://github.com/tdw46/mixamo_blender4-main/tree/main",
# }


if "bpy" in locals():
    import importlib

    if "mixamo_rig_prefs" in locals():
        importlib.reload(mixamo_rig_prefs)  # noqa: F821
    if "mixamo_rig" in locals():
        importlib.reload(mixamo_rig)  # noqa: F821
    if "mixamo_rig_functions" in locals():
        importlib.reload(mixamo_rig_functions)  # noqa: F821
    if "utils" in locals():
        importlib.reload(utils)  # noqa: F821


import bpy  # noqa: F401

from . import mixamo_rig, mixamo_rig_functions, mixamo_rig_prefs, utils  # noqa: F401


def register():
    mixamo_rig_prefs.register()
    mixamo_rig.register()
    mixamo_rig_functions.register()


def unregister():
    mixamo_rig_prefs.unregister()
    mixamo_rig.unregister()
    mixamo_rig_functions.unregister()


if __name__ == "__main__":
    register()
