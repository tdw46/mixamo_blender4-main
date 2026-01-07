import bpy

from .objects import append_cs, get_object
from .version import blender_version


def get_custom_shape_scale(pbone, uniform=True):
    if blender_version._float >= 300:
        if uniform:
            # uniform scale
            val = 0
            for i in range(0, 3):
                val += pbone.custom_shape_scale_xyz[i]
            return val / 3
        # array scale
        else:
            return pbone.custom_shape_scale_xyz
    # pre-Blender 3.0
    else:
        return pbone.custom_shape_scale


def get_selected_pbone_name():
    try:
        return bpy.context.selected_pose_bones[0].name  # .active_pose_bone.name
    except Exception:
        return


def get_pose_bone(name):
    return bpy.context.active_object.pose.bones.get(name)


def set_pose_bone_selected(pbone, state=True):
    if pbone is None:
        return

    try:
        if hasattr(pbone, "bone") and pbone.bone is not None and hasattr(
            pbone.bone, "select"
        ):
            pbone.bone.select = state
            return
        if hasattr(pbone, "select"):
            pbone.select = state
            return
        arm_obj = getattr(pbone, "id_data", None)
        arm_data = getattr(arm_obj, "data", None)
        if arm_data is not None and hasattr(arm_data, "bones"):
            b = arm_data.bones.get(pbone.name)
            if b is not None and hasattr(b, "select"):
                b.select = state
    except Exception:
        return


def is_pose_bone_selected(pbone):
    if pbone is None:
        return False

    try:
        if hasattr(pbone, "bone") and pbone.bone is not None and hasattr(
            pbone.bone, "select"
        ):
            return bool(pbone.bone.select)
        if hasattr(pbone, "select"):
            return bool(pbone.select)
        arm_obj = getattr(pbone, "id_data", None)
        arm_data = getattr(arm_obj, "data", None)
        if arm_data is not None and hasattr(arm_data, "bones"):
            b = arm_data.bones.get(pbone.name)
            if b is not None and hasattr(b, "select"):
                return bool(b.select)
    except Exception:
        return False

    return False


def lock_pbone_transform(pbone, type, list):
    for i in list:
        if type == "location":
            pbone.lock_location[i] = True
        elif type == "rotation":
            pbone.lock_rotation[i] = True
        elif type == "scale":
            pbone.lock_scale[i] = True


def set_bone_custom_shape(pbone, cs_name):
    cs = get_object(cs_name)
    if cs is None:
        append_cs(cs_name)
        cs = get_object(cs_name)
        if cs is None:
            # try to find a suffixed name like cs_name.001 if Blender renamed on link
            for obj in bpy.data.objects:
                if obj.name == cs_name or obj.name.startswith(cs_name + "."):
                    cs = obj
                    break

    pbone.custom_shape = cs


def set_bone_color_group(obj, pb, grp_name):
    # mixamo required color
    orange = (0.969, 0.565, 0.208)
    orange_light = (0.957, 0.659, 0.416)
    blue_dark = (0.447, 0.682, 1.0)
    blue_light = (0.365, 0.851, 1.0)

    # base color
    green = (0.0, 1.0, 0.0)  # noqa: F841
    red = (1.0, 0.0, 0.0)  # noqa: F841
    blue = (0.0, 0.9, 1.0)  # noqa: F841

    grp_color_master = orange_light
    grp_color_neck = orange_light
    grp_color_root_master = orange
    grp_color_head = orange
    grp_color_body_mid = green
    grp_color_body_left = blue_dark
    grp_color_body_right = blue_light

    # ~ grp = obj.data.collections.get(grp_name)
    # ~ grp = obj.pose.bone_groups.get(grp_name)
    # ~ if grp == None:
    # ~ grp = obj.data.collections.new(grp_name)
    # ~ grp = obj.pose.bone_groups.new(name=grp_name)
    # ~ grp.color_set = 'CUSTOM'

    grp_color = None
    if grp_name == "body_mid":
        grp_color = grp_color_body_mid
    elif grp_name == "body_left":
        grp_color = grp_color_body_left
    elif grp_name == "body_right":
        grp_color = grp_color_body_right
    elif grp_name == "master":
        grp_color = grp_color_master
    elif grp_name == "neck":
        grp_color = grp_color_head
    elif grp_name == "head":
        grp_color = grp_color_neck
    elif grp_name == "root_master":
        grp_color = grp_color_root_master

    # set normal color
    # ~ grp.colors.normal = grp_color

    # set select color/active color
    # ~ for col_idx in range(0,3):
    # ~ grp.colors.select[col_idx] = grp_color[col_idx] + 0.2
    # ~ grp.colors.active[col_idx] = grp_color[col_idx] + 0.4

    # ~ r = grp.assign(pb)
    # ~ pb.bone_group = grp

    pb.color.palette = "CUSTOM"
    pb.color.custom.normal = grp_color
    for col_idx in range(0, 3):
        pb.color.custom.select[col_idx] = grp_color[col_idx] + 0.2
        pb.color.custom.active[col_idx] = grp_color[col_idx] + 0.4


def update_transform():
    bpy.ops.transform.rotate(
        value=0,
        orient_axis="Z",
        orient_type="VIEW",
        orient_matrix=((0.0, 0.0, 0), (0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        orient_matrix_type="VIEW",
        mirror=False,
    )
