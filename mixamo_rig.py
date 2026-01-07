import math
from math import degrees, pi, radians

import bpy
from bpy.types import Panel
from mathutils import Matrix, Vector

# Import naming constants
from .definitions.naming import (
    arm_names,
    arm_rig_names,
    c_prefix,
    fingers_type,
    head_names,
    head_rig_names,
    leg_names,
    leg_rig_names,
    master_rig_names,
    spine_names,
    spine_rig_names,
)

# Import lib functions
from .lib import animation_compat
from .lib.animation import bake_anim
from .lib.armature import (
    enable_all_armature_layers,
    restore_armature_layers,
)
from .lib.bones_data import set_bone_collection
from .lib.bones_edit import copy_bone_transforms, create_edit_bone, get_edit_bone
from .lib.bones_pose import (
    get_custom_shape_scale,
    get_pose_bone,
    set_pose_bone_selected,
    lock_pbone_transform,
    set_bone_color_group,
    set_bone_custom_shape,
)
from .lib.constraints import (
    add_copy_transf,
    set_constraint_inverse_matrix,
)
from .lib.custom_props import create_custom_prop
from .lib.drivers import add_driver_to_prop
from .lib.maths_geo import (
    align_bone_x_axis,
    align_bone_z_axis,
    get_pole_angle,
    mat3_to_vec_roll,
    project_point_onto_plane,
    project_vector_onto_plane,
    rotate_point,
    signed_angle,
    vec_roll_to_mat3,
)
from .lib.mixamo import get_mix_name
from .lib.objects import (
    append_cs,
    delete_object,
    duplicate_object,
    get_object,
    hide_object,
    set_active_object,
)
from .lib.version import (
    blender_version,
    convert_drivers_cs_to_xyz,
    get_custom_shape_scale_prop_name,
)


# UTILITY FUNCTIONS
####################
def _deselect_all_objects():
    """
    Safely deselect all objects, handling context issues.
    Falls back to manual deselection if operator fails.
    """
    try:
        # Try to ensure OBJECT mode first if we have an active object
        if bpy.context.active_object and bpy.context.active_object.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass
        bpy.ops.object.select_all(action="DESELECT")
    except Exception:
        # Fallback: manually deselect all objects
        for obj in bpy.context.view_layer.objects:
            try:
                obj.select_set(False)
            except Exception:
                pass


def search_layer_collection(layer_collection, collection_name):
    """Recursively search for a layer collection by name."""
    if layer_collection.name == collection_name:
        return layer_collection
    for child in layer_collection.children:
        result = search_layer_collection(child, collection_name)
        if result:
            return result
    return None


# OPERATOR CLASSES
##################
class MR_OT_update(bpy.types.Operator):  # noqa: N801
    """Update old control rig to Blender 3.0"""

    bl_idname = "mr.update"
    bl_label = "update"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.active_object:
            if context.active_object.type == "ARMATURE":
                return "mr_control_rig" in context.active_object.data.keys()

    def execute(self, context):
        try:
            _update(self, context)
        finally:
            pass

        return {"FINISHED"}


class MR_OT_reconnect_rig(bpy.types.Operator):  # noqa: N801
    """Rebuild all constraints for the existing Mixamo control rig"""

    bl_idname = "mr.reconnect_rig"
    bl_label = "reconnect_rig"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if obj and obj.type == "ARMATURE":
            return "mr_control_rig" in obj.data.keys()
        return False

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            _reconnect_rig_constraints(context)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo

        return {"FINISHED"}


class MR_OT_exportGLTF(bpy.types.Operator):  # noqa: N801
    """Export to GLTF format"""

    bl_idname = "mr.export_gltf"
    bl_label = "export_gltf"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.active_object:
            if context.active_object.type == "ARMATURE":
                return True

    def execute(self, context):
        try:
            bpy.ops.export_scene.gltf()
        finally:
            pass

        return {"FINISHED"}


class MR_OT_apply_shape(bpy.types.Operator):  # noqa: N801
    """Apply the selected shape"""

    bl_idname = "mr.apply_shape"
    bl_label = "apply_shape"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.active_object:
            if context.mode == "EDIT_MESH":
                if "cs_user" in context.active_object.name:
                    return True

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            _apply_shape()
        finally:
            context.preferences.edit.use_global_undo = use_global_undo
        return {"FINISHED"}


class MR_OT_edit_custom_shape(bpy.types.Operator):  # noqa: N801
    """Edit the selected bone shape"""

    bl_idname = "mr.edit_custom_shape"
    bl_label = "edit_custom_shape"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.mode == "POSE":
            if context.active_pose_bone:
                return True

    def execute(self, context):
        try:
            cs = context.active_pose_bone.custom_shape
            if cs:
                _edit_custom_shape()
            else:
                self.report({"ERROR"}, "No custom shapes set for this bone.")

        finally:
            pass

        return {"FINISHED"}


class MR_OT_make_rig(bpy.types.Operator):  # noqa: N801
    """Generate a control rig from the selected Mixamo skeleton"""

    bl_idname = "mr.make_rig"
    bl_label = "Create control rig from selected armature"
    bl_options = {"UNDO"}

    bake_anim: bpy.props.BoolProperty(
        name="Bake Anim",
        description="Bake animation to the control bones",
        default=True,
    )
    ik_arms: bpy.props.BoolProperty(
        name="IK Hands",
        description=(
            "Use IK for arm bones, otherwise use FK "
            "(can be toggled later using the rig properties)"
        ),
        default=True,
    )
    ik_legs: bpy.props.BoolProperty(
        name="IK Legs",
        description=(
            "Use IK for leg bones, otherwise use FK "
            "(can be toggled later using the rig properties)"
        ),
        default=True,
    )
    animated_armature = None

    @classmethod
    def poll(cls, context):
        if context.active_object:
            if context.active_object.type == "ARMATURE":
                if "mr_control_rig" not in context.active_object.data.keys():
                    return True
        return False

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "bake_anim", text="Apply Animation")
        layout.prop(self, "ik_arms", text="IK Arms")
        layout.prop(self, "ik_legs", text="IK Legs")

    def execute(self, context):
        debug = False
        # ~ layer_select = []
        original_mode = "OBJECT"  # Safe default in case mode detection fails

        try:
            # only select the armature
            # FIRST THING: Store original mode and switch to OBJECT mode immediately
            if not context.active_object or context.active_object.type != "ARMATURE":
                self.report({"ERROR"}, "No armature selected")
                return {"CANCELLED"}

            original_mode = context.active_object.mode

            # Validate the mode is a valid string
            valid_modes = [
                "OBJECT",
                "EDIT",
                "POSE",
                "SCULPT",
                "VERTEX_PAINT",
                "WEIGHT_PAINT",
                "TEXTURE_PAINT",
                "PARTICLE_EDIT",
                "EDIT_GPENCIL",
                "SCULPT_GPENCIL",
                "PAINT_GPENCIL",
                "WEIGHT_GPENCIL",
                "VERTEX_GPENCIL",
            ]
            if not isinstance(original_mode, str) or original_mode not in valid_modes:
                print(f"WARNING: Invalid mode '{original_mode}', defaulting to OBJECT")
                original_mode = "OBJECT"

            # Switch to OBJECT mode IMMEDIATELY as first operation
            if original_mode != "OBJECT":
                try:
                    bpy.ops.object.mode_set(mode="OBJECT")
                except Exception as e:
                    self.report({"ERROR"}, f"Could not switch to OBJECT mode: {e}")
                    return {"CANCELLED"}

            arm = get_object(context.active_object.name)
            _deselect_all_objects()
            set_active_object(arm.name)

            # enable all armature layers
            layer_select = enable_all_armature_layers()

            # animation import: initial steps
            if self.bake_anim:
                if (
                    "mr_control_rig" not in arm.data.keys()
                ):  # only if the control rig is not already built
                    # duplicate current skeleton
                    duplicate_object()
                    copy_name = arm.name + "_TEMPANIM"
                    self.animated_armature = get_object(context.active_object.name)
                    self.animated_armature.name = copy_name
                    self.animated_armature["mix_to_del"] = True

                    bpy.ops.object.mode_set(mode="OBJECT")
                    _deselect_all_objects()
                    set_active_object(arm.name)

            # set to rest pose, clear animation
            _zero_out(context)

            # build control rig
            _make_rig(self, context)

            if blender_version._float < 291:
                # Child Of constraints inverse matrix must be set manually
                # in Blender versions < 2.91
                print("Set inverse ChildOf")
                _reset_inverse_constraints()

            # animation import: retarget
            if self.bake_anim and self.animated_armature:
                _import_anim(self.animated_armature, arm)

            # set KeyingSet
            ks = context.scene.keying_sets_all
            try:
                ks.active = ks["Location & Rotation"]
            except (KeyError, AttributeError):
                # doesn't exist in older Blender versions
                pass

        finally:
            bpy.ops.object.mode_set(mode="OBJECT")
            _deselect_all_objects()
            set_active_object(arm.name)

            if not debug:
                restore_armature_layers(layer_select)
                remove_retarget_cns(context.active_object)
                remove_temp_objects()
                clean_scene()

            self.report({"INFO"}, "Control Rig Done!")

        # LAST THING: Restore original mode after ALL operations complete
        try:
            mode_type = type(original_mode)
            print(f"DEBUG: Restoring mode to: '{original_mode}' (type: {mode_type})")
            if original_mode != "OBJECT":
                bpy.ops.object.mode_set(mode=original_mode)
        except Exception as e:
            print(f"Warning: Could not restore original mode '{original_mode}': {e}")

        return {"FINISHED"}


class MR_OT_zero_out(bpy.types.Operator):  # noqa: N801
    """Delete all keys and set every bones to (0,0,0) rotation"""

    bl_idname = "mr.zero_out"
    bl_label = "zero_out"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.active_object:
            return context.active_object.type == "ARMATURE"
        return False

    def execute(self, context):
        try:
            _zero_out(context)

        finally:
            print("")

        return {"FINISHED"}


class MR_OT_bake_anim(bpy.types.Operator):  # noqa: N801
    """Merge all animation layers (see NLA editor) into a single layer"""

    bl_idname = "mr.bake_anim"
    bl_label = "bake_anim"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.active_object:
            return context.active_object.type == "ARMATURE"
        return False

    def execute(self, context):
        try:
            _bake_anim(self, context)

        finally:
            pass

        return {"FINISHED"}


class MR_OT_import_anim(bpy.types.Operator):  # noqa: N801
    """Import an animation file (FBX) of the same character to the control rig"""

    bl_idname = "mr.import_anim_to_rig"
    bl_label = "import_anim_to_rig"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        if context.active_object:
            if context.active_object.type == "ARMATURE":
                if "mr_control_rig" in context.active_object.data.keys():
                    return True
        return False

    def execute(self, context):
        scn = context.scene
        debug = False
        error = False
        layer_select = []

        if scn.mix_source_armature is None:
            self.report({"ERROR"}, "Source armature must be set")
            return {"FINISHED"}

        try:
            layer_select = enable_all_armature_layers()
            # tar_arm = scn.mix_target_armature
            tar_arm = get_object(context.active_object.name)
            # src_arm = [i for i in context.selected_objects if i != tar_arm][0]
            src_arm = scn.mix_source_armature
            print("Source", src_arm.name)
            print("Target", tar_arm.name)

            _import_anim(src_arm, tar_arm, import_only=True)

        # except:
        #    error = True
        #    print("Error")

        finally:
            if not debug:
                # Ensure the control rig is active before restoring layers
                try:
                    _deselect_all_objects()
                    if "tar_arm" in locals() and tar_arm:
                        set_active_object(tar_arm.name)
                except Exception:
                    pass
                restore_armature_layers(layer_select)
                remove_retarget_cns(context.active_object)

                if scn.mix_source_armature:
                    try:
                        remove_retarget_cns(scn.mix_source_armature)
                    except Exception:
                        pass

                remove_temp_objects()

            self.report({"INFO"}, "Animation imported")

        return {"FINISHED"}


# OPERATOR FUNCTIONS
#####################


def _apply_shape():
    bpy.ops.object.mode_set(mode="OBJECT")
    obj = bpy.context.active_object
    obj_name = obj.name
    shape = bpy.data.objects.get(obj_name)
    delete_obj = False

    cs_grp = get_object("cs_grp")
    if cs_grp:
        shape.parent = bpy.data.objects["cs_grp"]

    mr_armature_name = None
    mr_armature = None

    if len(shape.keys()) > 0:
        for key in shape.keys():
            if "delete" in shape.keys():
                delete_obj = True
            if "mr_armature" in key:
                mr_armature_name = shape["mr_armature"]
                mr_armature = bpy.data.objects.get(mr_armature_name)

    if delete_obj:
        bpy.ops.object.delete(use_global=False)
    else:
        # assign to collection
        if mr_armature:
            if len(mr_armature.users_collection) > 0:
                for collec in mr_armature.users_collection:
                    if len(collec.name.split("_")) == 1:
                        continue
                    if (
                        collec.name.split("_")[1] == "rig"
                        or collec.name.split("_")[1] == "grp"
                    ):
                        cs_collec = bpy.data.collections.get(
                            collec.name.split("_")[0] + "_cs"
                        )
                        if cs_collec:
                            # remove from root collection
                            if bpy.context.scene.collection.objects.get(shape.name):
                                bpy.context.scene.collection.objects.unlink(shape)
                            # remove from other collections
                            for other_collec in shape.users_collection:
                                other_collec.objects.unlink(shape)
                            # assign to cs collection
                            cs_collec.objects.link(shape)
                            print("assigned to collec", cs_collec.name)
                        else:
                            print("cs collec not found")
                    else:
                        print("rig collec not found")

            else:
                print("Armature has no collection")
        else:
            print("Armature not set")

    # hide shape
    try:
        hide_object(shape)
    except Exception:  # weird error 'StructRNA of type Object has been removed'
        print("Error, could not hide shape")
        pass

    if mr_armature:
        set_active_object(mr_armature.name)
        bpy.ops.object.mode_set(mode="POSE")


def _edit_custom_shape():
    bone = bpy.context.active_pose_bone
    rig_name = bpy.context.active_object.name
    rig = get_object(rig_name)

    cs = bone.custom_shape
    cs_mesh = cs.data

    bpy.ops.object.mode_set(mode="OBJECT")

    # make sure the active collection is not hidden,
    # otherwise we can't access the newly created object data
    active_collec = bpy.context.layer_collection
    if not active_collec.is_visible:
        for col in rig.users_collection:
            layer_col = search_layer_collection(
                bpy.context.view_layer.layer_collection, col.name
            )
            if not layer_col.hide_viewport and not col.hide_viewport:
                bpy.context.view_layer.active_layer_collection = layer_col
                break

    # create new mesh data
    bpy.ops.mesh.primitive_plane_add(
        size=1, enter_editmode=False, location=(-0, 0, 0.0), rotation=(0.0, 0.0, 0.0)
    )

    mesh_obj = bpy.context.active_object
    mesh_obj.name = "cs_user_" + bone.name

    if (
        cs.name == "cs_user_" + bone.name
    ):  # make a mesh instance if it's a already edited
        mesh_obj.data = cs_mesh
        mesh_obj["delete"] = 1.0
    else:  # else create new object data
        mesh_obj.data = cs_mesh.copy()
        mesh_obj.data.name = mesh_obj.name
        bone.custom_shape = mesh_obj

    # store the current armature name in a custom prop
    mesh_obj["mr_armature"] = rig_name

    if bone.custom_shape_transform:
        bone_transf = bone.custom_shape_transform
        mesh_obj.matrix_world = rig.matrix_world @ bone_transf.matrix
    else:
        mesh_obj.matrix_world = rig.matrix_world @ bone.matrix

    mesh_obj.scale *= get_custom_shape_scale(bone)
    mesh_obj.scale *= bone.length

    bpy.ops.object.mode_set(mode="EDIT")


def clean_scene():
    # hide cs_grp
    cs_grp = get_object("cs_grp")
    if cs_grp:
        for c in cs_grp.children:
            if c.name in bpy.context.view_layer.objects:
                hide_object(c)
            else:
                print(f"Warning: Object '{c.name}' is not in the current View Layer.")

        if cs_grp.name in bpy.context.view_layer.objects:
            hide_object(cs_grp)
        else:
            print("Warning: Object 'cs_grp' is not in the current View Layer.")

    # Always show custom shapes and set collection visibility
    if bpy.context.object and bpy.context.object.type == "ARMATURE":
        bpy.context.object.data.show_bone_custom_shapes = True

        # Set bone collection visibility - only CTRL visible
        # Use .collections instead of .collections_all for safe property assignment
        for coll in bpy.context.object.data.collections:
            if coll.name == "DEF":
                coll.is_visible = False
            elif coll.name == "MCH":
                coll.is_visible = False
            elif coll.name == "CTRL":
                coll.is_visible = True


def init_armature_transforms(rig):
    bpy.ops.object.mode_set(mode="OBJECT")
    _deselect_all_objects()
    set_active_object(rig.name)
    bpy.ops.object.mode_set(mode="OBJECT")

    # first unparent children meshes
    # (init scale messed up children scale in Blender 2.8)
    child_par_dict = {}
    for child in bpy.data.objects[rig.name].children:
        bone_parent = None
        if child.parent_type == "BONE":
            bone_parent = child.parent_bone
        child_par_dict[child.name] = bone_parent
        child_mat = child.matrix_world.copy()
        child.parent = None
        bpy.context.evaluated_depsgraph_get().update()
        child.matrix_world = child_mat

    # apply armature transforms
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    bpy.context.evaluated_depsgraph_get().update()

    # restore armature children
    for child_name in child_par_dict:
        child = bpy.data.objects.get(child_name)
        child_mat = child.matrix_world.copy()
        child.parent = bpy.data.objects[rig.name]
        if child_par_dict[child_name] is not None:  # bone parent
            child.parent_type = "BONE"
            child.parent_bone = child_par_dict[child_name]

        bpy.context.evaluated_depsgraph_get().update()
        child.matrix_world = child_mat


def _reset_inverse_constraints():
    bpy.ops.object.mode_set(mode="POSE")

    rig_name = bpy.context.active_object.name
    rig = get_object(rig_name)

    for pb in rig.pose.bones:
        if len(pb.constraints):
            for cns in pb.constraints:
                if cns.type == "CHILD_OF":
                    set_constraint_inverse_matrix(cns)

    bpy.ops.object.mode_set(mode="OBJECT")


def _reconnect_rig_constraints(context):
    obj = context.active_object
    if not obj or obj.type != "ARMATURE":
        return

    rig = obj

    if "mr_control_rig" not in rig.data.keys():
        return

    try:
        bpy.ops.object.mode_set(mode="POSE")
    except Exception:
        return

    for pb in rig.pose.bones:
        while pb.constraints:
            pb.constraints.remove(pb.constraints[0])

    _build_constraints_for_rig(rig)


def _build_constraints_for_rig(rig):
    detected_prefix = ""
    try:
        for bone in rig.data.bones:
            if bone.name.startswith("mixamorig") and ":" in bone.name:
                detected_prefix = bone.name.split(":")[0] + ":"
                break
    except Exception:
        pass

    def get_src_bone_name(base_name):
        if detected_prefix:
            return detected_prefix + base_name
        return base_name

    bpy.ops.object.mode_set(mode="POSE")

    c_master_name = c_prefix + master_rig_names["master"]

    if get_pose_bone(c_master_name) is None:
        return

    if get_pose_bone(c_master_name) is not None:
        c_master_pb = get_pose_bone(c_master_name)
        c_master_pb.bone["mixamo_ctrl"] = 1
        set_bone_custom_shape(c_master_pb, "cs_master")
        c_master_pb.rotation_mode = "XYZ"
        set_bone_color_group(rig, c_master_pb, "master")

    hips_name = get_src_bone_name(spine_names["pelvis"])
    c_hips_name = c_prefix + spine_rig_names["pelvis"]
    hips_free_h_name = spine_rig_names["hips_free_helper"]
    c_hips_free_name = c_prefix + spine_rig_names["hips_free"]
    c_spine_name = c_prefix + spine_rig_names["spine1"]
    c_spine1_name = c_prefix + spine_rig_names["spine2"]
    c_spine2_name = c_prefix + spine_rig_names["spine3"]

    mixamo_spine_pb = get_pose_bone(hips_name)
    c_hips_pb = get_pose_bone(c_hips_name)
    hips_free_h_pb = get_pose_bone(hips_free_h_name)
    c_hips_free_pb = get_pose_bone(c_hips_free_name)
    c_spine_pb = get_pose_bone(c_spine_name)
    c_spine1_pb = get_pose_bone(c_spine1_name)
    c_spine2_pb = get_pose_bone(c_spine2_name)

    if mixamo_spine_pb and hips_free_h_pb:
        cns = mixamo_spine_pb.constraints.get("Copy Transforms")
        if cns is None:
            cns = mixamo_spine_pb.constraints.new("COPY_TRANSFORMS")
            cns.name = "Copy Transforms"
        cns.target = rig
        cns.subtarget = hips_free_h_name

    if c_hips_pb and c_hips_free_pb and c_spine_pb and c_spine1_pb and c_spine2_pb:
        for pb in [c_hips_pb, c_hips_free_pb, c_spine_pb, c_spine1_pb, c_spine2_pb]:
            pb.bone["mixamo_ctrl"] = 1

        set_bone_custom_shape(c_hips_pb, "cs_square_2")
        set_bone_custom_shape(c_hips_free_pb, "cs_hips")
        set_bone_custom_shape(c_spine_pb, "cs_circle")
        set_bone_custom_shape(c_spine1_pb, "cs_circle")
        set_bone_custom_shape(c_spine2_pb, "cs_circle")

        c_hips_pb.rotation_mode = "XYZ"
        c_hips_free_pb.rotation_mode = "XYZ"
        c_spine_pb.rotation_mode = "XYZ"
        c_spine1_pb.rotation_mode = "XYZ"
        c_spine2_pb.rotation_mode = "XYZ"

        set_bone_color_group(rig, c_hips_pb, "root_master")
        set_bone_color_group(rig, c_hips_free_pb, "body_mid")
        set_bone_color_group(rig, c_spine_pb, "body_mid")
        set_bone_color_group(rig, c_spine1_pb, "body_mid")
        set_bone_color_group(rig, c_spine2_pb, "body_mid")

        spine_bone_matches = {
            "1": c_spine_name,
            "2": c_spine1_name,
            "3": c_spine2_name,
        }
        for str_idx in spine_bone_matches:
            c_name = spine_bone_matches[str_idx]
            mixamo_bname = get_src_bone_name(spine_names["spine" + str_idx])
            mixamo_spine_pb = get_pose_bone(mixamo_bname)
            if mixamo_spine_pb is None:
                continue
            cns = mixamo_spine_pb.constraints.get("Copy Transforms")
            if cns is None:
                cns = mixamo_spine_pb.constraints.new("COPY_TRANSFORMS")
                cns.name = "Copy Transforms"
            cns.target = rig
            cns.subtarget = c_name

    neck_name = get_src_bone_name(head_names["neck"])
    head_name = get_src_bone_name(head_names["head"])
    c_neck_name = c_prefix + head_rig_names["neck"]
    c_head_name = c_prefix + head_rig_names["head"]

    neck_pb = get_pose_bone(neck_name)
    head_pb = get_pose_bone(head_name)
    c_neck_pb = get_pose_bone(c_neck_name)
    c_head_pb = get_pose_bone(c_head_name)

    if c_neck_pb and c_head_pb:
        c_neck_pb.bone["mixamo_ctrl"] = 1
        c_head_pb.bone["mixamo_ctrl"] = 1

        set_bone_custom_shape(c_neck_pb, "cs_neck")
        set_bone_custom_shape(c_head_pb, "cs_head")

        c_head_pb.custom_shape_scale_xyz[0] = 1.9
        c_head_pb.custom_shape_scale_xyz[1] = 1.9
        c_head_pb.custom_shape_scale_xyz[2] = 1.9

        c_neck_pb.rotation_mode = "XYZ"
        c_head_pb.rotation_mode = "XYZ"

        set_bone_color_group(rig, c_neck_pb, "neck")
        set_bone_color_group(rig, c_head_pb, "head")

    if neck_pb and c_neck_pb:
        add_copy_transf(neck_pb, rig, c_neck_name)
    if head_pb and c_head_pb:
        add_copy_transf(head_pb, rig, c_head_name)

    for side in ["Left", "Right"]:
        _side = "_" + side

        thigh_name = get_src_bone_name(side + leg_names["thigh"])
        calf_name = get_src_bone_name(side + leg_names["calf"])
        foot_name = get_src_bone_name(side + leg_names["foot"])
        toe_name = get_src_bone_name(side + leg_names["toes"])

        thigh_pb = get_pose_bone(thigh_name)
        calf_pb = get_pose_bone(calf_name)
        foot_pb = get_pose_bone(foot_name)
        toe_pb = get_pose_bone(toe_name)

        calf_ik_name = leg_rig_names["calf_ik"] + _side
        foot_ik_name = leg_rig_names["foot_ik"] + _side
        c_foot_ik_name = c_prefix + leg_rig_names["foot_ik"] + _side
        c_pole_ik_name = c_prefix + leg_rig_names["pole_ik"] + _side
        toes_end_name = leg_rig_names["toes_end"] + _side
        toe_01_ik_name = leg_rig_names["toes_01_ik"] + _side
        toe_02_name = leg_rig_names["toes_02"] + _side
        toe_track_name = leg_rig_names["toes_track"] + _side
        heel_mid_name = leg_rig_names["heel_mid"] + _side
        heel_in_name = leg_rig_names["heel_in"] + _side
        heel_out_name = leg_rig_names["heel_out"] + _side
        c_foot_01_name = c_prefix + leg_rig_names["foot_01"] + _side
        c_foot_roll_cursor_name = c_prefix + leg_rig_names["foot_roll_cursor"] + _side
        foot_ik_target_name = leg_rig_names["foot_ik_target"] + _side
        foot_01_pole_name = leg_rig_names["foot_01_pole"] + _side
        c_thigh_fk_name = c_prefix + leg_rig_names["thigh_fk"] + _side
        c_calf_fk_name = c_prefix + leg_rig_names["calf_fk"] + _side
        c_foot_fk_name = c_prefix + leg_rig_names["foot_fk"] + _side
        c_toe_ik_name = c_prefix + leg_rig_names["toes_ik"] + _side
        c_toe_fk_name = c_prefix + leg_rig_names["toes_fk"] + _side
        foot_fk_name = leg_rig_names["foot_fk"] + _side

        calf_ik_pb = get_pose_bone(calf_ik_name)
        foot_ik_pb = get_pose_bone(foot_ik_name)
        c_foot_ik_pb = get_pose_bone(c_foot_ik_name)
        c_pole_ik_pb = get_pose_bone(c_pole_ik_name)
        toes_end_pb = get_pose_bone(toes_end_name)
        toe_01_ik_pb = get_pose_bone(toe_01_ik_name)
        toe_02_pb = get_pose_bone(toe_02_name)
        toe_track_pb = get_pose_bone(toe_track_name)
        heel_mid_pb = get_pose_bone(heel_mid_name)
        heel_in_pb = get_pose_bone(heel_in_name)
        heel_out_pb = get_pose_bone(heel_out_name)
        c_foot_01_pb = get_pose_bone(c_foot_01_name)
        c_foot_roll_cursor_pb = get_pose_bone(c_foot_roll_cursor_name)
        c_thigh_fk_pb = get_pose_bone(c_thigh_fk_name)
        c_calf_fk_pb = get_pose_bone(c_calf_fk_name)
        c_foot_fk_pb = get_pose_bone(c_foot_fk_name)
        c_toe_ik_pb = get_pose_bone(c_toe_ik_name)
        c_toe_fk_pb = get_pose_bone(c_toe_fk_name)

        if not (
            calf_ik_pb
            and foot_ik_pb
            and c_foot_ik_pb
            and c_pole_ik_pb
            and toes_end_pb
            and toe_01_ik_pb
            and toe_02_pb
            and toe_track_pb
            and heel_mid_pb
            and heel_in_pb
            and heel_out_pb
            and foot_pb
            and thigh_pb
            and calf_pb
            and toe_pb
            and c_foot_01_pb
            and c_foot_roll_cursor_pb
            and c_thigh_fk_pb
            and c_calf_fk_pb
            and c_foot_fk_pb
            and c_toe_ik_pb
            and c_toe_fk_pb
        ):
            continue

        cns_name = "IK"
        ik_cns = calf_ik_pb.constraints.get(cns_name)
        if ik_cns is None:
            ik_cns = calf_ik_pb.constraints.new("IK")
            ik_cns.name = cns_name
        ik_cns.target = rig
        ik_cns.subtarget = foot_ik_target_name
        ik_cns.pole_target = rig
        ik_cns.pole_subtarget = c_pole_ik_name
        try:
            thigh_ik_pb = get_pose_bone(leg_rig_names["thigh_ik"] + _side)
            if thigh_ik_pb is not None:
                ik_cns.pole_angle = get_pole_angle(
                    thigh_ik_pb,
                    calf_ik_pb,
                    c_pole_ik_pb.head,
                )
        except Exception:
            pass
        ik_cns.chain_count = 2
        ik_cns.use_tail = True
        ik_cns.use_stretch = False

        calf_ik_pb.lock_ik_y = True
        calf_ik_pb.lock_ik_z = True

        cns_name = "Copy Location"
        copy_loc_cns = foot_ik_pb.constraints.get(cns_name)
        if copy_loc_cns is None:
            copy_loc_cns = foot_ik_pb.constraints.new("COPY_LOCATION")
            copy_loc_cns.name = cns_name
        copy_loc_cns.target = rig
        copy_loc_cns.subtarget = calf_ik_name
        copy_loc_cns.head_tail = 1.0

        cns_name = "TrackTo"
        cns = foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = foot_ik_pb.constraints.new("TRACK_TO")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_foot_01_name
        cns.head_tail = 0.0
        cns.track_axis = "TRACK_Y"
        cns.up_axis = "UP_Z"
        cns.use_target_z = True

        cns_name = "Locked Track"
        cns = foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = foot_ik_pb.constraints.new("LOCKED_TRACK")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = foot_01_pole_name
        cns.head_tail = 0.0
        cns.track_axis = "TRACK_Z"
        cns.lock_axis = "LOCK_Y"

        cns_name = "Copy Scale"
        cns = foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = foot_ik_pb.constraints.new("COPY_SCALE")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_foot_ik_name

        cns_name = "Child Of"
        cns = c_foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_foot_ik_pb.constraints.new("CHILD_OF")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_master_name

        cns_name = "Child Of"
        child_cns = c_pole_ik_pb.constraints.get(cns_name)
        if child_cns is None:
            child_cns = c_pole_ik_pb.constraints.new("CHILD_OF")
            child_cns.name = cns_name
        child_cns.target = rig
        child_cns.subtarget = c_foot_ik_name

        cns_power = 8

        length_toes_end = toes_end_pb.length * cns_power

        cns_name = "Transformation"
        cns = toes_end_pb.constraints.get(cns_name)
        if cns is None:
            cns = toes_end_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_foot_roll_cursor_name
        cns.use_motion_extrapolate = True
        cns.target_space = cns.owner_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_z = 0.5 * length_toes_end
        cns.from_max_z = -0.5 * length_toes_end
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_z_from = "X"
        cns.to_min_x_rot = -2.61
        cns.to_max_x_rot = 2.61
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = toes_end_pb.constraints.get(cns_name)
        if cns is None:
            cns = toes_end_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.owner_space = "LOCAL"
        cns.use_limit_x = True
        cns.min_x = -2 * pi
        cns.max_x = 0.0

        cns_name = "Copy Transforms"
        cns = toe_01_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = toe_01_ik_pb.constraints.new("COPY_TRANSFORMS")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_toe_ik_name
        cns.mix_mode = "REPLACE"
        cns.target_space = cns.owner_space = "WORLD"

        cns_name_fk_rot = "FK_Rot_follow"
        cns_fk_rot = toe_02_pb.constraints.get(cns_name_fk_rot)
        if cns_fk_rot is None:
            cns_fk_rot = toe_02_pb.constraints.new("COPY_ROTATION")
            cns_fk_rot.name = cns_name_fk_rot
        cns_fk_rot.target = rig
        cns_fk_rot.subtarget = c_toe_ik_name
        cns_fk_rot.mix_mode = "REPLACE"
        cns_fk_rot.target_space = cns.owner_space = "WORLD"

        cns_name = "TrackTo"
        cns = toe_track_pb.constraints.get(cns_name)
        if cns is None:
            cns = toe_track_pb.constraints.new("TRACK_TO")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_rig_names["toes_end_01"] + _side
        cns.head_tail = 0.0
        cns.track_axis = "TRACK_Y"
        cns.up_axis = "UP_Z"
        cns.use_target_z = True

        length_heel_mid = heel_mid_pb.length * cns_power

        cns_name = "Transformation"
        cns = heel_mid_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_mid_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_foot_roll_cursor_name
        cns.owner_space = cns.target_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_z = -0.25 * length_heel_mid
        cns.from_max_z = 0.25 * length_heel_mid
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_y_from = "X"
        cns.map_to_z_from = "Y"
        cns.to_min_x_rot = radians(100)
        cns.to_max_x_rot = -radians(100)
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = heel_mid_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_mid_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.use_limit_x = True
        cns.min_x = radians(0)
        cns.max_x = radians(360)
        cns.owner_space = "LOCAL"

        length_heel_in = heel_in_pb.length * cns_power

        cns_name = "Transformation"
        cns = heel_in_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_in_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_foot_roll_cursor_name
        cns.owner_space = cns.target_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_x = -0.25 * length_heel_in
        cns.from_max_x = 0.25 * length_heel_in
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_y_from = "X"
        cns.map_to_z_from = "Y"
        cns.to_min_y_rot = -radians(100)
        cns.to_max_y_rot = radians(100)
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = heel_in_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_in_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.use_limit_y = True
        if side == "Left":
            cns.min_y = 0.0
            cns.max_y = radians(90)
        else:
            cns.min_y = radians(-90)
            cns.max_y = 0.0
        cns.owner_space = "LOCAL"

        length_heel_out = heel_out_pb.length * cns_power

        cns_name = "Transformation"
        cns = heel_out_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_out_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_foot_roll_cursor_name
        cns.owner_space = cns.target_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_x = -0.25 * length_heel_out
        cns.from_max_x = 0.25 * length_heel_out
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_y_from = "X"
        cns.map_to_z_from = "Y"
        cns.to_min_y_rot = -radians(100)
        cns.to_max_y_rot = radians(100)
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = heel_out_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_out_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.use_limit_y = True
        if side == "Left":
            cns.min_y = radians(-90)
            cns.max_y = 0.0
        else:
            cns.min_y = 0.0
            cns.max_y = radians(90)
        cns.owner_space = "LOCAL"

        if "ik_fk_switch" not in c_foot_ik_pb.keys():
            create_custom_prop(
                node=c_foot_ik_pb,
                prop_name="ik_fk_switch",
                prop_val=0.0,
                prop_min=0.0,
                prop_max=1.0,
                prop_description="IK-FK switch value",
            )

        cns_name = "IK_follow"
        cns_ik = thigh_pb.constraints.get(cns_name)
        if cns_ik is None:
            cns_ik = thigh_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_name
        cns_ik.target = rig
        cns_ik.subtarget = leg_rig_names["thigh_ik"] + _side
        cns_ik.influence = 1.0

        cns_name = "FK_follow"
        cns_fk = thigh_pb.constraints.get(cns_name)
        if cns_fk is None:
            cns_fk = thigh_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_name
        cns_fk.target = rig
        cns_fk.subtarget = c_thigh_fk_name
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + thigh_name
            + '"].constraints["'
            + cns_name
            + '"].influence',
            'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        cns_name = "IK_follow"
        cns_ik = calf_pb.constraints.get(cns_name)
        if cns_ik is None:
            cns_ik = calf_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_name
        cns_ik.target = rig
        cns_ik.subtarget = calf_ik_name
        cns_ik.influence = 1.0

        cns_name = "FK_follow"
        cns_fk = calf_pb.constraints.get(cns_name)
        if cns_fk is None:
            cns_fk = calf_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_name
        cns_fk.target = rig
        cns_fk.subtarget = c_calf_fk_name
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            f'pose.bones["{calf_name}"].constraints["{cns_name}"].influence',
            'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        cns_name = "IK_follow"
        cns_ik = foot_pb.constraints.get(cns_name)
        if cns_ik is None:
            cns_ik = foot_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_name
        cns_ik.target = rig
        cns_ik.subtarget = foot_ik_name
        cns_ik.influence = 1.0

        cns_name = "FK_follow"
        cns_fk = foot_pb.constraints.get(cns_name)
        if cns_fk is None:
            cns_fk = foot_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_name
        cns_fk.target = rig
        cns_fk.subtarget = foot_fk_name
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            f'pose.bones["{foot_name}"].constraints["{cns_name}"].influence',
            'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        cns_name = "IK_Rot_follow"
        cns_ik_rot = toe_pb.constraints.get(cns_name)
        if cns_ik_rot is None:
            cns_ik_rot = toe_pb.constraints.new("COPY_ROTATION")
            cns_ik_rot.name = cns_name
        cns_ik_rot.target = rig
        cns_ik_rot.subtarget = c_toe_ik_name
        cns_ik_rot.influence = 1.0

        cns_name = "IK_Scale_follow"
        cns_ik_scale = toe_pb.constraints.get(cns_name)
        if cns_ik_scale is None:
            cns_ik_scale = toe_pb.constraints.new("COPY_SCALE")
            cns_ik_scale.name = cns_name
        cns_ik_scale.target = rig
        cns_ik_scale.subtarget = c_toe_ik_name
        cns_ik_scale.influence = 1.0

        cns_name_fk_rot = "FK_Rot_follow"
        cns_fk_rot = toe_pb.constraints.get(cns_name_fk_rot)
        if cns_fk_rot is None:
            cns_fk_rot = toe_pb.constraints.new("COPY_ROTATION")
            cns_fk_rot.name = cns_name_fk_rot
        cns_fk_rot.target = rig
        cns_fk_rot.subtarget = c_toe_fk_name
        cns_fk_rot.influence = 1.0

        cns_name_fk_scale = "FK_Scale_follow"
        cns_fk_scale = toe_pb.constraints.get(cns_name_fk_scale)
        if cns_fk_scale is None:
            cns_fk_scale = toe_pb.constraints.new("COPY_SCALE")
            cns_fk_scale.name = cns_name_fk_scale
        cns_fk_scale.target = rig
        cns_fk_scale.subtarget = c_toe_fk_name
        cns_fk_scale.influence = 1.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + toe_name
            + '"].constraints["'
            + cns_name_fk_rot
            + '"].influence',
            'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )
        add_driver_to_prop(
            rig,
            'pose.bones["'
            + toe_name
            + '"].constraints["'
            + cns_name_fk_scale
            + '"].influence',
            'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        lock_pbone_transform(c_foot_roll_cursor_pb, "location", [1])
        lock_pbone_transform(c_foot_roll_cursor_pb, "rotation", [0, 1, 2])
        lock_pbone_transform(c_foot_roll_cursor_pb, "scale", [0, 1, 2])

        lock_pbone_transform(c_foot_01_pb, "location", [0, 1, 2])
        lock_pbone_transform(c_foot_01_pb, "rotation", [1, 2])
        lock_pbone_transform(c_foot_01_pb, "scale", [0, 1, 2])

        lock_pbone_transform(c_foot_fk_pb, "location", [0, 1, 2])

        lock_pbone_transform(c_pole_ik_pb, "rotation", [0, 1, 2])
        lock_pbone_transform(c_pole_ik_pb, "scale", [0, 1, 2])

        lock_pbone_transform(c_thigh_fk_pb, "location", [0, 1, 2])
        lock_pbone_transform(c_calf_fk_pb, "location", [0, 1, 2])

        c_pbones_list = [
            c_foot_ik_pb,
            c_pole_ik_pb,
            c_foot_01_pb,
            c_foot_roll_cursor_pb,
            c_thigh_fk_pb,
            c_calf_fk_pb,
            c_foot_fk_pb,
            c_toe_fk_pb,
            c_toe_ik_pb,
        ]

        for pb in c_pbones_list:
            pb.bone["mixamo_ctrl"] = 1

        set_bone_custom_shape(c_thigh_fk_pb, "cs_thigh_fk")
        set_bone_custom_shape(c_calf_fk_pb, "cs_calf_fk")
        set_bone_custom_shape(c_foot_ik_pb, "cs_foot")
        set_bone_custom_shape(c_foot_fk_pb, "cs_foot")
        set_bone_custom_shape(c_pole_ik_pb, "cs_sphere_012")
        set_bone_custom_shape(c_foot_roll_cursor_pb, "cs_foot_roll")
        set_bone_custom_shape(c_foot_01_pb, "cs_foot_01")
        set_bone_custom_shape(c_toe_fk_pb, "cs_toe")
        set_bone_custom_shape(c_toe_ik_pb, "cs_toe")

        ik_controls_names = [
            c_foot_ik_name,
            c_foot_01_name,
            c_toe_ik_name,
            c_foot_roll_cursor_name,
            c_pole_ik_name,
        ]

        arr_ids = [-1]
        if blender_version._float >= 300:
            arr_ids = [0, 1, 2]

        for n in ik_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="1-var")

        fk_controls_names = [
            c_foot_fk_name,
            c_thigh_fk_name,
            c_calf_fk_name,
            c_toe_fk_name,
        ]

        for n in fk_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + c_foot_ik_name + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="var")

        for pb in c_pbones_list:
            pb.rotation_mode = "XYZ"
            set_bone_color_group(rig, pb, "body" + _side.lower())

    for side in ["Left", "Right"]:
        _side = "_" + side

        shoulder_name = get_src_bone_name(side + arm_names["shoulder"])
        arm_name = get_src_bone_name(side + arm_names["arm"])
        forearm_name = get_src_bone_name(side + arm_names["forearm"])
        hand_name = get_src_bone_name(side + arm_names["hand"])

        c_shoulder_name = c_prefix + arm_rig_names["shoulder"] + _side
        arm_ik_name = arm_rig_names["arm_ik"] + _side
        forearm_ik_name = arm_rig_names["forearm_ik"] + _side
        c_arm_fk_name = c_prefix + arm_rig_names["arm_fk"] + _side
        c_forearm_fk_name = c_prefix + arm_rig_names["forearm_fk"] + _side
        c_pole_ik_name = c_prefix + arm_rig_names["pole_ik"] + _side
        c_hand_ik_name = c_prefix + arm_rig_names["hand_ik"] + _side
        c_hand_fk_name = c_prefix + arm_rig_names["hand_fk"] + _side

        c_shoulder_pb = get_pose_bone(c_shoulder_name)
        shoulder_pb = get_pose_bone(shoulder_name)
        c_arm_fk_pb = get_pose_bone(c_arm_fk_name)
        forearm_ik_pb = get_pose_bone(forearm_ik_name)
        c_pole_ik_pb = get_pose_bone(c_pole_ik_name)
        c_hand_ik_pb = get_pose_bone(c_hand_ik_name)
        hand_pb = get_pose_bone(hand_name)
        arm_pb = get_pose_bone(arm_name)
        forearm_pb = get_pose_bone(forearm_name)
        c_forearm_fk_pb = get_pose_bone(c_forearm_fk_name)
        c_hand_fk_pb = get_pose_bone(c_hand_fk_name)

        if not (
            c_shoulder_pb
            and shoulder_pb
            and c_arm_fk_pb
            and forearm_ik_pb
            and c_pole_ik_pb
            and c_hand_ik_pb
            and hand_pb
            and arm_pb
            and forearm_pb
            and c_forearm_fk_pb
            and c_hand_fk_pb
        ):
            continue

        cns_name = "Copy Location"
        cns = c_arm_fk_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_arm_fk_pb.constraints.new("COPY_LOCATION")
            cns.name = cns_name
        cns.head_tail = 1.0
        cns.target = rig
        cns.subtarget = c_shoulder_name

        cns_name = "IK"
        ik_cns = forearm_ik_pb.constraints.get(cns_name)
        if ik_cns is None:
            ik_cns = forearm_ik_pb.constraints.new("IK")
            ik_cns.name = cns_name
        ik_cns.target = rig
        ik_cns.subtarget = c_hand_ik_name
        ik_cns.pole_target = rig
        ik_cns.pole_subtarget = c_pole_ik_name
        ik_cns.pole_angle = 0.0
        if side == "Right":
            ik_cns.pole_angle = radians(180)
        ik_cns.chain_count = 2
        ik_cns.use_tail = True
        ik_cns.use_stretch = False

        forearm_ik_pb.lock_ik_y = True
        forearm_ik_pb.lock_ik_x = True

        cns_name = "Child Of"
        cns = c_pole_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_pole_ik_pb.constraints.new("CHILD_OF")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_prefix + spine_rig_names["pelvis"]

        cns_name = "Child Of"
        cns = c_hand_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_hand_ik_pb.constraints.new("CHILD_OF")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_master_name

        fingers_names = []
        c_fingers_names = []
        for fname in fingers_type:
            for i in range(1, 4):
                finger_name = get_mix_name(side + "Hand" + fname + str(i), True)
                finger_pb = get_pose_bone(finger_name)
                if finger_pb is None:
                    continue
                fingers_names.append(finger_name)
                c_finger_name = c_prefix + fname + str(i) + _side
                c_fingers_names.append(c_finger_name)
                c_finger_pb = get_pose_bone(c_finger_name)
                if c_finger_pb is None:
                    continue
                add_copy_transf(finger_pb, rig, c_finger_pb.name)

        if shoulder_pb and c_shoulder_pb:
            add_copy_transf(shoulder_pb, rig, c_shoulder_name)

        if "ik_fk_switch" not in c_hand_ik_pb.keys():
            create_custom_prop(
                node=c_hand_ik_pb,
                prop_name="ik_fk_switch",
                prop_val=0.0,
                prop_min=0.0,
                prop_max=1.0,
                prop_description="IK-FK switch value",
            )

        cns_ik_name = "IK_follow"
        cns_ik = arm_pb.constraints.get(cns_ik_name)
        if cns_ik is None:
            cns_ik = arm_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_ik_name
        cns_ik.target = rig
        cns_ik.subtarget = arm_ik_name
        cns_ik.influence = 1.0

        cns_fk_name = "FK_Follow"
        cns_fk = arm_pb.constraints.get(cns_fk_name)
        if cns_fk is None:
            cns_fk = arm_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_fk_name
        cns_fk.target = rig
        cns_fk.subtarget = c_arm_fk_name
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + arm_name
            + '"].constraints["'
            + cns_fk_name
            + '"].influence',
            'pose.bones["' + c_hand_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        cns_ik_name = "IK_follow"
        cns_ik = forearm_pb.constraints.get(cns_ik_name)
        if cns_ik is None:
            cns_ik = forearm_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_ik_name
        cns_ik.target = rig
        cns_ik.subtarget = forearm_ik_name
        cns_ik.influence = 1.0

        cns_fk_name = "FK_Follow"
        cns_fk = forearm_pb.constraints.get(cns_fk_name)
        if cns_fk is None:
            cns_fk = forearm_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_fk_name
        cns_fk.target = rig
        cns_fk.subtarget = c_forearm_fk_name
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + forearm_name
            + '"].constraints["'
            + cns_fk_name
            + '"].influence',
            'pose.bones["' + c_hand_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        lock_pbone_transform(c_forearm_fk_pb, "location", [0, 1, 2])

        cns_ik_name = "IK_follow"
        cns_ik = hand_pb.constraints.get(cns_ik_name)
        if cns_ik is None:
            cns_ik = hand_pb.constraints.new("COPY_ROTATION")
            cns_ik.name = cns_ik_name
        cns_ik.target = rig
        cns_ik.subtarget = c_hand_ik_name
        cns_ik.influence = 1.0

        cns_fk_name = "FK_Follow"
        cns_fk = hand_pb.constraints.get(cns_fk_name)
        if cns_fk is None:
            cns_fk = hand_pb.constraints.new("COPY_ROTATION")
            cns_fk.name = cns_fk_name
        cns_fk.target = rig
        cns_fk.subtarget = c_hand_fk_name
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + hand_name
            + '"].constraints["'
            + cns_fk_name
            + '"].influence',
            'pose.bones["' + c_hand_ik_name + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        lock_pbone_transform(c_hand_fk_pb, "location", [0, 1, 2])

        set_bone_custom_shape(c_shoulder_pb, "cs_shoulder_" + side.lower())
        set_bone_custom_shape(c_arm_fk_pb, "cs_arm_fk")
        set_bone_custom_shape(c_forearm_fk_pb, "cs_forearm_fk")
        set_bone_custom_shape(c_pole_ik_pb, "cs_sphere_012")
        set_bone_custom_shape(c_hand_fk_pb, "cs_circle")
        set_bone_custom_shape(c_hand_ik_pb, "cs_circle")

        c_fingers_pb = []
        for fname in fingers_type:
            for i in range(1, 4):
                c_finger_name = c_prefix + fname + str(i) + _side
                finger_pb = get_pose_bone(c_finger_name)
                if finger_pb is None:
                    continue
                c_fingers_pb.append(finger_pb)
                set_bone_custom_shape(finger_pb, "cs_circle_025")

        c_pbones_list = [
            c_shoulder_pb,
            c_arm_fk_pb,
            c_forearm_fk_pb,
            c_pole_ik_pb,
            c_hand_fk_pb,
            c_hand_ik_pb,
        ] + c_fingers_pb

        for pb in c_pbones_list:
            pb.bone["mixamo_ctrl"] = 1

        ik_controls_names = [c_pole_ik_name, c_hand_ik_name]

        arr_ids = [-1]
        if blender_version._float >= 300:
            arr_ids = [0, 1, 2]

        for n in ik_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + c_hand_ik_name + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="1-var")

        fk_controls_names = [
            c_arm_fk_name,
            c_forearm_fk_name,
            c_hand_fk_name,
        ]

        for n in fk_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + c_hand_ik_name + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="var")

        for pb in c_pbones_list:
            pb.rotation_mode = "XYZ"
            set_bone_color_group(rig, pb, "body" + _side.lower())

    coll_ctrl_name = "CTRL"
    ctrl_collection = rig.data.collections.get(coll_ctrl_name)
    if ctrl_collection:
        for bone in ctrl_collection.bones:
            pose_bone = rig.pose.bones.get(bone.name)
            if pose_bone:
                pose_bone.custom_shape_wire_width = 3.0

    rig.show_in_front = False


def _update(self, context):
    if blender_version._float >= 300:
        convert_drivers_cs_to_xyz(context.active_object)


def _make_rig(self, context):
    print("\nBuilding control rig...")

    rig_name = context.active_object.name
    rig = get_object(rig_name)

    # Ensure we're in OBJECT mode - do NOT force dependency graph update here
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception as e:
        print(f"  Warning: Could not set initial mode: {e}")

    # Preload all custom shape objects in a single, safe place to avoid appending
    # while rapidly switching modes during rig construction.
    try:
        shape_names = [
            "cs_master",
            "cs_circle",
            "cs_square_2",
            "cs_hips",
            "cs_neck",
            "cs_head",
            "cs_thigh_fk",
            "cs_calf_fk",
            "cs_foot",
            "cs_sphere_012",
            "cs_foot_roll",
            "cs_foot_01",
            "cs_toe",
            "cs_shoulder_left",
            "cs_shoulder_right",
            "cs_arm_fk",
            "cs_forearm_fk",
            "cs_hand",
            "cs_circle_025",
        ]
        append_cs(shape_names)
    except Exception:
        # Fallback silently; set_bone_custom_shape will try best-effort lookups
        pass

    coll_mix_name = "DEF"
    coll_ctrl_name = "CTRL"
    coll_intern_name = "MCH"

    # Create collections if they don't exist
    for coll_name in [coll_mix_name, coll_ctrl_name, coll_intern_name]:
        if not rig.data.collections.get(coll_name):
            rig.data.collections.new(coll_name)

    use_name_prefix = True

    c_master_name = c_prefix + master_rig_names["master"]

    # Init transforms
    init_armature_transforms(rig)

    # Detect if source armature uses mixamorig: prefix
    detected_prefix = ""
    try:
        for bone in rig.data.bones:
            if bone.name.startswith("mixamorig") and ":" in bone.name:
                detected_prefix = bone.name.split(":")[0] + ":"
                print(f"  Detected Mixamo prefix: {detected_prefix}")
                break
    except Exception as e:
        print(f"  Warning: Could not detect prefix: {e}")

    if not detected_prefix:
        print("  No Mixamo prefix detected, using plain bone names")

    # Helper function to construct source bone names with the correct prefix
    def get_src_bone_name(base_name):
        result = (detected_prefix + base_name) if detected_prefix else base_name
        return result

    # ==========================================
    # PHASE 1: ALL EDIT MODE OPERATIONS
    # ==========================================
    print("  Phase 1: Creating all edit bones...")
    bpy.ops.object.mode_set(mode="EDIT")

    # Data structures to store information needed for pose mode
    edit_data = {
        "master": {},
        "spine": {},
        "head": {},
        "leg_left": {},
        "leg_right": {},
        "arm_left": {},
        "arm_right": {},
    }

    # Master bones
    print("    Creating Master bones...")
    c_master = create_edit_bone(c_master_name)
    c_master.head = [0, 0, 0]
    c_master.tail = [0, 0, 0.05 * rig.dimensions[2]]
    c_master.roll = 0.01
    ctrl_collection = rig.data.collections.get(coll_ctrl_name)
    if not ctrl_collection:
        ctrl_collection = rig.data.collections.new(coll_ctrl_name)
    ctrl_collection.assign(c_master)

    # Spine bones
    print("    Creating Spine bones...")
    hips_name = get_src_bone_name(spine_names["pelvis"])
    spine_name = get_src_bone_name(spine_names["spine1"])
    spine1_name = get_src_bone_name(spine_names["spine2"])
    spine2_name = get_src_bone_name(spine_names["spine3"])

    hips = get_edit_bone(hips_name)
    spine = get_edit_bone(spine_name)
    spine1 = get_edit_bone(spine1_name)
    spine2 = get_edit_bone(spine2_name)

    if hips and spine and spine1 and spine2:
        for b in [hips, spine, spine1, spine2]:
            set_bone_collection(rig, b, coll_mix_name)

        # Hips Ctrl
        c_hips_name = c_prefix + spine_rig_names["pelvis"]
        c_hips = create_edit_bone(c_hips_name)
        copy_bone_transforms(hips, c_hips)
        c_hips.parent = get_edit_bone(c_prefix + master_rig_names["master"])
        set_bone_collection(rig, c_hips, coll_ctrl_name)

        # Free Hips Ctrl
        c_hips_free_name = c_prefix + spine_rig_names["hips_free"]
        c_hips_free = create_edit_bone(c_hips_free_name)
        try:
            c_hips_free.head = hips.tail.copy()
            c_hips_free.tail = hips.head.copy()
            align_bone_x_axis(c_hips_free, hips.x_axis)
        except Exception as e:
            print(f"    Warning: Error setting hips_free transforms: {e}")
            copy_bone_transforms(hips, c_hips_free)

        c_hips_free.parent = c_hips
        set_bone_collection(rig, c_hips_free, coll_ctrl_name)

        # Free Hips helper
        hips_free_h_name = spine_rig_names["hips_free_helper"]
        hips_free_helper = create_edit_bone(hips_free_h_name)
        copy_bone_transforms(hips, hips_free_helper)
        hips_free_helper.parent = c_hips_free
        set_bone_collection(rig, hips_free_helper, coll_intern_name)

        # Spine Ctrl
        c_spine_name = c_prefix + spine_rig_names["spine1"]
        c_spine = create_edit_bone(c_spine_name)
        copy_bone_transforms(spine, c_spine)
        c_spine.parent = c_hips
        set_bone_collection(rig, c_spine, coll_ctrl_name)

        # Spine1 Ctrl
        c_spine1_name = c_prefix + spine_rig_names["spine2"]
        c_spine1 = create_edit_bone(c_spine1_name)
        copy_bone_transforms(spine1, c_spine1)
        c_spine1.parent = c_spine
        set_bone_collection(rig, c_spine1, coll_ctrl_name)

        # Spine2 Ctrl
        c_spine2_name = c_prefix + spine_rig_names["spine3"]
        c_spine2 = create_edit_bone(c_spine2_name)
        copy_bone_transforms(spine2, c_spine2)
        c_spine2.parent = c_spine1
        set_bone_collection(rig, c_spine2, coll_ctrl_name)

        # Store data for pose mode
        edit_data["spine"] = {
            "exists": True,
            "hips_name": hips_name,
            "c_hips_name": c_hips_name,
            "hips_free_h_name": hips_free_h_name,
            "c_hips_free_name": c_hips_free_name,
            "c_spine_name": c_spine_name,
            "c_spine1_name": c_spine1_name,
            "c_spine2_name": c_spine2_name,
            "spine_name": spine_name,
            "spine1_name": spine1_name,
            "spine2_name": spine2_name,
        }
    else:
        print("    Spine bones are missing, skip spine")
        edit_data["spine"]["exists"] = False

    # Head bones
    print("    Creating Head bones...")
    neck_name = get_src_bone_name(head_names["neck"])
    head_name = get_src_bone_name(head_names["head"])
    head_end_name = get_src_bone_name(head_names["head_end"])

    neck = get_edit_bone(neck_name)
    head = get_edit_bone(head_name)
    head_end = get_edit_bone(head_end_name)

    if neck and head:
        for b in [neck, head, head_end]:
            set_bone_collection(rig, b, coll_mix_name)

        # Neck Ctrl
        c_neck_name = c_prefix + head_rig_names["neck"]
        c_neck = create_edit_bone(c_neck_name)
        copy_bone_transforms(neck, c_neck)
        c_neck.parent = get_edit_bone(c_prefix + spine_rig_names["spine3"])
        set_bone_collection(rig, c_neck, coll_ctrl_name)

        # Head Ctrl
        c_head_name = c_prefix + head_rig_names["head"]
        c_head = create_edit_bone(c_head_name)
        copy_bone_transforms(head, c_head)
        c_head.parent = c_neck
        set_bone_collection(rig, c_head, coll_ctrl_name)

        edit_data["head"] = {
            "exists": True,
            "neck_name": neck_name,
            "head_name": head_name,
            "c_neck_name": c_neck_name,
            "c_head_name": c_head_name,
        }
    else:
        print("    Head or neck bones are missing, skip head")
        edit_data["head"]["exists"] = False

    # Leg bones for both sides
    for side in ["Left", "Right"]:
        print(f"    Creating Leg bones for {side}...")
        _side = "_" + side
        thigh_name = get_src_bone_name(side + leg_names["thigh"])
        calf_name = get_src_bone_name(side + leg_names["calf"])
        foot_name = get_src_bone_name(side + leg_names["foot"])
        toe_name = get_src_bone_name(side + leg_names["toes"])
        toe_end_name = get_src_bone_name(side + leg_names["toes_end"])

        thigh = get_edit_bone(thigh_name)
        calf = get_edit_bone(calf_name)
        foot = get_edit_bone(foot_name)
        toe = get_edit_bone(toe_name)
        toe_end = get_edit_bone(toe_end_name)

        hips = get_edit_bone(get_src_bone_name(spine_names["pelvis"]))
        c_hips_free_name = c_prefix + spine_rig_names["hips_free"]
        c_hips_free = get_edit_bone(c_hips_free_name)

        if not thigh or not calf or not foot or not toe:
            print(f"    Leg bones are missing, skip leg: {side}")
            edit_data[f"leg_{side.lower()}"]["exists"] = False
            continue

        # Set Mixamo bones in layer
        for b in [thigh, calf, foot, toe, toe_end]:
            set_bone_collection(rig, b, coll_mix_name)

        # Create bones
        # correct straight leg angle
        def get_leg_angle(thigh=thigh, calf=calf, foot=foot):  # noqa: B023
            vec1 = calf.head - thigh.head
            vec2 = foot.head - calf.head
            return degrees(vec1.angle(vec2))

        leg_angle = get_leg_angle()

        if leg_angle < 0.1:
            print(f"    ! Straight leg bones, angle = {leg_angle}")
            max_iter = 10000
            i = 0

            while leg_angle < 0.1 and i < max_iter:
                dir = ((thigh.z_axis + calf.z_axis) * 0.5).normalized()
                calf.head += dir * (calf.tail - calf.head).magnitude * 0.0001
                leg_angle = get_leg_angle()
                i += 1

            print(f"      corrected leg angle: {leg_angle}")

        # Thigh IK
        thigh_ik_name = leg_rig_names["thigh_ik"] + _side
        thigh_ik = create_edit_bone(thigh_ik_name)
        copy_bone_transforms(thigh, thigh_ik)

        # auto-align knee position
        leg_axis = calf.tail - thigh.head
        leg_midpoint = (thigh.head + calf.tail) * 0.5

        dir = calf.head - leg_midpoint
        cur_vec = project_vector_onto_plane(dir, leg_axis)
        global_y_vec = project_vector_onto_plane(Vector((0, -1, 0)), leg_axis)

        signed_cur_angle = signed_angle(cur_vec, global_y_vec, leg_axis)

        # rotate
        rotated_point = rotate_point(
            calf.head.copy(), -signed_cur_angle, leg_midpoint, leg_axis
        )

        thigh_ik.tail = rotated_point
        thigh_ik.parent = c_hips_free
        set_bone_collection(rig, thigh_ik, coll_intern_name)

        # Thigh FK Ctrl
        c_thigh_fk_name = c_prefix + leg_rig_names["thigh_fk"] + _side
        c_thigh_fk = create_edit_bone(c_thigh_fk_name)
        copy_bone_transforms(thigh_ik, c_thigh_fk)
        c_thigh_fk.parent = c_hips_free
        set_bone_collection(rig, c_thigh_fk, coll_ctrl_name)

        # Calf IK
        calf_ik_name = leg_rig_names["calf_ik"] + _side
        calf_ik_exist = get_edit_bone(calf_ik_name)

        calf_ik = create_edit_bone(calf_ik_name)
        if calf_ik_exist is None:
            copy_bone_transforms(calf, calf_ik)
        calf_ik.head = thigh_ik.tail.copy()
        calf_ik.tail = foot.head.copy()
        calf_ik.parent = thigh_ik
        calf_ik.use_connect = True
        set_bone_collection(rig, calf_ik, coll_intern_name)

        # align thigh and calf IK roll
        align_bone_z_axis(calf_ik, (calf_ik.head - leg_midpoint))
        align_bone_z_axis(thigh_ik, calf_ik.z_axis)
        copy_bone_transforms(thigh_ik, c_thigh_fk)

        # Calf FK Ctrl
        c_calf_fk_name = c_prefix + leg_rig_names["calf_fk"] + _side
        c_calf_fk = create_edit_bone(c_calf_fk_name)
        copy_bone_transforms(calf_ik, c_calf_fk)
        c_calf_fk.parent = c_thigh_fk
        set_bone_collection(rig, c_calf_fk, coll_ctrl_name)

        # Foot FK Ctrl
        c_foot_fk_name = c_prefix + leg_rig_names["foot_fk"] + _side
        c_foot_fk = create_edit_bone(c_foot_fk_name)
        copy_bone_transforms(foot, c_foot_fk)
        c_foot_fk.tail[2] = foot.head[2]
        align_bone_z_axis(c_foot_fk, Vector((0, 0, 1)))
        c_foot_fk.parent = c_calf_fk
        set_bone_collection(rig, c_foot_fk, coll_ctrl_name)

        # Foot FK
        foot_fk_name = leg_rig_names["foot_fk"] + _side
        foot_fk = create_edit_bone(foot_fk_name)
        copy_bone_transforms(foot, foot_fk)
        foot_fk.parent = c_foot_fk
        set_bone_collection(rig, foot_fk, coll_intern_name)

        # Foot IK Ctrl
        c_foot_ik_name = c_prefix + leg_rig_names["foot_ik"] + _side
        c_foot_ik = create_edit_bone(c_foot_ik_name)
        copy_bone_transforms(foot, c_foot_ik)
        c_foot_ik.tail[2] = foot.head[2]
        align_bone_z_axis(c_foot_ik, Vector((0, 0, 1)))
        set_bone_collection(rig, c_foot_ik, coll_ctrl_name)

        # Foot IK
        foot_ik_name = leg_rig_names["foot_ik"] + _side
        foot_ik = create_edit_bone(foot_ik_name)
        copy_bone_transforms(foot, foot_ik)
        foot_ik.parent = c_foot_ik
        set_bone_collection(rig, foot_ik, coll_intern_name)

        # Foot Snap
        foot_snap_name = leg_rig_names["foot_snap"] + _side
        foot_snap = create_edit_bone(foot_snap_name)
        copy_bone_transforms(c_foot_ik, foot_snap)
        foot_snap.parent = foot_ik
        set_bone_collection(rig, foot_snap, coll_intern_name)

        # Foot IK target
        foot_ik_target_name = leg_rig_names["foot_ik_target"] + _side
        foot_ik_target = create_edit_bone(foot_ik_target_name)
        foot_ik_target.head = foot_ik.head.copy()
        foot_vec = foot.tail - foot.head
        foot_ik_target.tail = foot_ik_target.head - (foot_vec * 0.25)
        align_bone_z_axis(foot_ik_target, Vector((0, 0, 1)))
        set_bone_collection(rig, foot_ik_target, coll_intern_name)

        # Foot Heel Out
        heel_out_name = leg_rig_names["heel_out"] + _side
        heel_out = create_edit_bone(heel_out_name)
        heel_out.head, heel_out.tail = Vector((0, 0, 0)), Vector((0, 0, 1))
        heel_out.parent = c_foot_ik
        set_bone_collection(rig, heel_out, coll_intern_name)

        # Foot Heel In
        heel_in_name = leg_rig_names["heel_in"] + _side
        heel_in = create_edit_bone(heel_in_name)
        heel_in.head, heel_in.tail = Vector((0, 0, 0)), Vector((0, 0, 1))
        heel_in.parent = heel_out
        set_bone_collection(rig, heel_in, coll_intern_name)

        # Foot Heel Mid
        heel_mid_name = leg_rig_names["heel_mid"] + _side
        heel_mid = create_edit_bone(heel_mid_name)
        heel_mid.head, heel_mid.tail = Vector((0, 0, 0)), Vector((0, 0, 1))
        heel_mid.parent = heel_in
        set_bone_collection(rig, heel_mid, coll_intern_name)

        heel_mid.head[0], heel_mid.head[1], heel_mid.head[2] = (
            foot.head[0],
            foot.head[1],
            foot.tail[2],
        )
        heel_mid.tail = foot.tail.copy()
        heel_mid.tail[2] = heel_mid.head[2]
        heel_mid.tail = heel_mid.head + (heel_mid.tail - heel_mid.head) * 0.5
        align_bone_x_axis(heel_mid, foot.x_axis)

        copy_bone_transforms(heel_mid, heel_in)
        fac = 1
        if side == "Right":
            fac = -1

        heel_in.head += foot.x_axis.normalized() * foot.length * 0.3 * fac
        heel_in.tail += foot.x_axis.normalized() * foot.length * 0.3 * fac

        copy_bone_transforms(heel_mid, heel_out)
        heel_out.head += foot.x_axis.normalized() * foot.length * 0.3 * -fac
        heel_out.tail += foot.x_axis.normalized() * foot.length * 0.3 * -fac

        # Toe End
        toes_end_name = leg_rig_names["toes_end"] + _side
        toes_end = create_edit_bone(toes_end_name)
        copy_bone_transforms(toe, toes_end)
        toe_vec = toes_end.tail - toes_end.head
        toes_end.tail += toe_vec
        toes_end.head += toe_vec
        toes_end.parent = heel_mid
        set_bone_collection(rig, toes_end, coll_intern_name)

        # Toe End 01
        toes_end_01_name = leg_rig_names["toes_end_01"] + _side
        toes_end_01 = create_edit_bone(toes_end_01_name)
        copy_bone_transforms(toes_end, toes_end_01)
        vec = toes_end_01.tail - toes_end_01.head
        toes_end_01.tail = toes_end_01.head + (vec * 0.5)
        toes_end_01.parent = toes_end
        set_bone_collection(rig, toes_end_01, coll_intern_name)

        # Foot 01 Ctrl
        c_foot_01_name = c_prefix + leg_rig_names["foot_01"] + _side
        c_foot_01 = create_edit_bone(c_foot_01_name)
        copy_bone_transforms(foot, c_foot_01)
        c_foot_01_vec = c_foot_01.tail - c_foot_01.head
        c_foot_01.tail += c_foot_01_vec
        c_foot_01.head += c_foot_01_vec
        c_foot_01.parent = toes_end
        set_bone_collection(rig, c_foot_01, coll_ctrl_name)

        # Foot_ik_target parent
        foot_ik_target.parent = c_foot_01

        # Foot 01 Pole
        foot_01_pole_name = leg_rig_names["foot_01_pole"] + _side
        foot_01_pole = create_edit_bone(foot_01_pole_name)
        foot_01_pole.head = c_foot_01.head + (
            c_foot_01.z_axis * 0.05 * c_foot_01.length * 40
        )
        foot_01_pole.tail = foot_01_pole.head + (
            c_foot_01.z_axis * 0.05 * c_foot_01.length * 40
        )
        foot_01_pole.roll = radians(180)
        foot_01_pole.parent = c_foot_01
        set_bone_collection(rig, foot_01_pole, coll_intern_name)

        # Toe IK Ctrl
        c_toe_ik_name = c_prefix + leg_rig_names["toes_ik"] + _side
        c_toe_ik = create_edit_bone(c_toe_ik_name)
        copy_bone_transforms(toe, c_toe_ik)
        c_toe_ik.parent = toes_end
        set_bone_collection(rig, c_toe_ik, coll_ctrl_name)

        # Toe FK Ctrl
        c_toe_fk_name = c_prefix + leg_rig_names["toes_fk"] + _side
        c_toe_fk = create_edit_bone(c_toe_fk_name)
        copy_bone_transforms(toe, c_toe_fk)
        c_toe_fk.parent = c_foot_fk
        set_bone_collection(rig, c_toe_fk, coll_ctrl_name)

        # Toe Track
        toe_track_name = leg_rig_names["toes_track"] + _side
        toe_track = create_edit_bone(toe_track_name)
        copy_bone_transforms(toe, toe_track)
        toe_track.parent = foot_ik
        set_bone_collection(rig, toe_track, coll_intern_name)

        # Toe_01 IK
        toe_01_ik_name = leg_rig_names["toes_01_ik"] + _side
        toe_01_ik = create_edit_bone(toe_01_ik_name)
        copy_bone_transforms(toe, toe_01_ik)
        toe_01_ik.tail = toe_01_ik.head + (toe_01_ik.tail - toe_01_ik.head) * 0.5
        toe_01_ik.parent = toe_track
        set_bone_collection(rig, toe_01_ik, coll_intern_name)

        # Toe_02
        toe_02_name = leg_rig_names["toes_02"] + _side
        toe_02 = create_edit_bone(toe_02_name)
        copy_bone_transforms(toe, toe_02)
        toe_02.head = toe_02.head + (toe_02.tail - toe_02.head) * 0.5
        toe_02.parent = toe_01_ik
        set_bone_collection(rig, toe_02, coll_intern_name)

        # Foot FK Ctrl
        c_foot_fk_name = c_prefix + leg_rig_names["foot_fk"] + _side
        c_foot_fk = create_edit_bone(c_foot_fk_name)
        copy_bone_transforms(foot, c_foot_fk)
        c_foot_fk.parent = c_calf_fk
        set_bone_collection(rig, c_foot_fk, coll_ctrl_name)

        # Foot Roll Cursor Ctrl
        c_foot_roll_cursor_name = c_prefix + leg_rig_names["foot_roll_cursor"] + _side
        c_foot_roll_cursor = create_edit_bone(c_foot_roll_cursor_name)
        copy_bone_transforms(c_foot_ik, c_foot_roll_cursor)
        vec = c_foot_roll_cursor.tail - c_foot_roll_cursor.head
        dist = 1.2
        c_foot_roll_cursor.head -= vec * dist
        c_foot_roll_cursor.tail -= vec * dist
        c_foot_roll_cursor.parent = c_foot_ik
        set_bone_collection(rig, c_foot_roll_cursor, coll_ctrl_name)

        # Pole IK Ctrl
        c_pole_ik_name = c_prefix + leg_rig_names["pole_ik"] + _side
        c_pole_ik = create_edit_bone(c_pole_ik_name)
        set_bone_collection(rig, c_pole_ik, coll_ctrl_name)

        plane_normal = thigh_ik.head - calf_ik.tail
        prepole_dir = calf_ik.head - leg_midpoint
        pole_pos = calf_ik.head + prepole_dir.normalized()
        pole_pos = project_point_onto_plane(pole_pos, calf_ik.head, plane_normal)
        pole_pos = calf_ik.head + (
            (pole_pos - calf_ik.head).normalized()
            * (calf_ik.head - thigh.head).magnitude
            * 1.7
        )

        c_pole_ik.head = pole_pos
        c_pole_ik.tail = [
            c_pole_ik.head[0],
            c_pole_ik.head[1],
            c_pole_ik.head[2] + (0.165 * thigh_ik.length * 2),
        ]

        ik_pole_angle = get_pole_angle(thigh_ik, calf_ik, c_pole_ik.head)

        # Add slight bend to avoid singularities
        add_slight_bend(calf_ik, Vector((1, 0, 0)))  # +X axis for both legs

        # Store data for pose mode
        edit_data[f"leg_{side.lower()}"] = {
            "exists": True,
            "side": side,
            "thigh_name": thigh_name,
            "calf_name": calf_name,
            "foot_name": foot_name,
            "toe_name": toe_name,
            "thigh_ik_name": thigh_ik_name,
            "calf_ik_name": calf_ik_name,
            "foot_ik_name": foot_ik_name,
            "foot_ik_target_name": foot_ik_target_name,
            "c_foot_ik_name": c_foot_ik_name,
            "c_pole_ik_name": c_pole_ik_name,
            "c_thigh_fk_name": c_thigh_fk_name,
            "c_calf_fk_name": c_calf_fk_name,
            "c_foot_fk_name": c_foot_fk_name,
            "foot_fk_name": foot_fk_name,
            "c_toe_ik_name": c_toe_ik_name,
            "c_toe_fk_name": c_toe_fk_name,
            "c_foot_01_name": c_foot_01_name,
            "c_foot_roll_cursor_name": c_foot_roll_cursor_name,
            "toes_end_name": toes_end_name,
            "toes_end_01_name": toes_end_01_name,
            "toe_01_ik_name": toe_01_ik_name,
            "toe_02_name": toe_02_name,
            "toe_track_name": toe_track_name,
            "heel_mid_name": heel_mid_name,
            "heel_in_name": heel_in_name,
            "heel_out_name": heel_out_name,
            "foot_01_pole_name": foot_01_pole_name,
            "ik_pole_angle": ik_pole_angle,
        }

    # Arm bones for both sides
    for side in ["Left", "Right"]:
        print(f"    Creating Arm bones for {side}...")
        _side = "_" + side
        shoulder_name = get_src_bone_name(side + arm_names["shoulder"])
        arm_name = get_src_bone_name(side + arm_names["arm"])
        forearm_name = get_src_bone_name(side + arm_names["forearm"])
        hand_name = get_src_bone_name(side + arm_names["hand"])

        shoulder = get_edit_bone(shoulder_name)
        arm = get_edit_bone(arm_name)
        forearm = get_edit_bone(forearm_name)
        hand = get_edit_bone(hand_name)

        if not shoulder or not arm or not forearm or not hand:
            print(f"    Arm bones are missing, skip arm: {side}")
            edit_data[f"arm_{side.lower()}"]["exists"] = False
            continue

        # Create bones
        # Fingers
        fingers_names = []
        c_fingers_names = []
        fingers = []
        finger_leaves = []

        for fname in fingers_type:
            for i in range(1, 4):
                finger_name = get_mix_name(
                    side + "Hand" + fname + str(i), use_name_prefix
                )
                finger = get_edit_bone(finger_name)
                if finger is None:
                    continue

                fingers_names.append(finger_name)
                fingers.append(finger)
                c_finger_name = c_prefix + fname + str(i) + _side
                c_fingers_names.append(c_finger_name)
                c_finger = create_edit_bone(c_finger_name)
                copy_bone_transforms(finger, c_finger)
                set_bone_collection(rig, c_finger, coll_ctrl_name)

                if i == 1:
                    c_finger.parent = hand
                else:
                    prev_finger_name = c_prefix + fname + str(i - 1) + _side
                    prev_finger = get_edit_bone(prev_finger_name)
                    c_finger.parent = prev_finger

        # fingers "leaves"/tip bones
        for fname in fingers_type:
            finger_name = get_src_bone_name(side + "Hand" + fname + "4")
            finger_leaf = get_edit_bone(finger_name)
            finger_leaves.append(finger_leaf)

        # Set Mixamo bones in layer
        for b in [shoulder, arm, forearm, hand] + fingers + finger_leaves:
            set_bone_collection(rig, b, coll_mix_name)

        # Shoulder Ctrl
        c_shoulder_name = c_prefix + arm_rig_names["shoulder"] + _side
        c_shoulder = create_edit_bone(c_shoulder_name)
        copy_bone_transforms(shoulder, c_shoulder)
        c_shoulder.parent = get_edit_bone(c_prefix + spine_rig_names["spine3"])
        set_bone_collection(rig, c_shoulder, coll_ctrl_name)

        # Arm IK
        arm_ik_name = arm_rig_names["arm_ik"] + _side
        arm_ik = create_edit_bone(arm_ik_name)
        copy_bone_transforms(arm, arm_ik)

        # correct straight arms angle
        angle_min = 0.1

        def get_arm_angle(arm=arm, forearm=forearm, hand=hand):  # noqa: B023
            vec1 = forearm.head - arm.head
            vec2 = hand.head - forearm.head
            return degrees(vec1.angle(vec2))

        arm_angle = get_arm_angle()

        if arm_angle < angle_min:
            print(f"    ! Straight arm bones, angle = {arm_angle}")

            max_iter = 10000
            i = 0

            while arm_angle < angle_min and i < max_iter:
                dir = ((arm.x_axis + forearm.x_axis) * 0.5).normalized()
                if side == "Right":
                    dir *= -1

                forearm.head += dir * (forearm.tail - forearm.head).magnitude * 0.0001
                arm_angle = get_arm_angle()
                i += 1

            print(f"      corrected arm angle: {arm_angle}")

        # auto-align elbow position
        arm_axis = forearm.tail - arm.head
        arm_midpoint = (arm.head + forearm.tail) * 0.5

        dir = forearm.head - arm_midpoint
        cur_vec = project_vector_onto_plane(dir, arm_axis)
        global_y_vec = project_vector_onto_plane(Vector((0, 1, 0)), arm_axis)
        signed_cur_angle = signed_angle(cur_vec, global_y_vec, arm_axis)

        # rotate
        rotated_point = rotate_point(
            forearm.head.copy(), -signed_cur_angle, arm_midpoint, arm_axis
        )

        arm_ik.tail = rotated_point
        arm_ik.parent = c_shoulder
        set_bone_collection(rig, arm_ik, coll_intern_name)

        # Arm FK Ctrl
        c_arm_fk_name = c_prefix + arm_rig_names["arm_fk"] + _side
        c_arm_fk = create_edit_bone(c_arm_fk_name)
        c_arm_fk.parent = get_edit_bone(c_prefix + spine_rig_names["spine3"])
        copy_bone_transforms(arm_ik, c_arm_fk)
        set_bone_collection(rig, c_arm_fk, coll_ctrl_name)

        # ForeArm IK
        forearm_ik_name = arm_rig_names["forearm_ik"] + _side
        forearm_ik = create_edit_bone(forearm_ik_name)
        copy_bone_transforms(forearm, forearm_ik)
        forearm_ik.head = arm_ik.tail.copy()
        forearm_ik.tail = hand.head.copy()
        forearm_ik.parent = arm_ik
        set_bone_collection(rig, forearm_ik, coll_intern_name)

        # align arm and forearm IK roll
        align_bone_x_axis(forearm_ik, (forearm_ik.head - arm_midpoint))
        align_bone_x_axis(arm_ik, forearm_ik.x_axis)
        copy_bone_transforms(arm_ik, c_arm_fk)

        if side == "Right":
            forearm_ik.roll += radians(180)
            arm_ik.roll += radians(180)
            c_arm_fk.roll += radians(180)

        # Forearm FK Ctrl
        c_forearm_fk_name = c_prefix + arm_rig_names["forearm_fk"] + _side
        c_forearm_fk = create_edit_bone(c_forearm_fk_name)
        copy_bone_transforms(forearm_ik, c_forearm_fk)
        c_forearm_fk.parent = c_arm_fk
        set_bone_collection(rig, c_forearm_fk, coll_ctrl_name)

        # Pole IK Ctrl
        c_pole_ik_name = c_prefix + arm_rig_names["pole_ik"] + _side
        c_pole_ik = create_edit_bone(c_pole_ik_name)
        set_bone_collection(rig, c_pole_ik, coll_ctrl_name)

        arm_midpoint = (arm_ik.head + forearm_ik.tail) * 0.5

        plane_normal = arm_ik.head - forearm_ik.tail
        prepole_dir = forearm_ik.head - arm_midpoint
        pole_pos = forearm_ik.head + prepole_dir.normalized()
        pole_pos = project_point_onto_plane(pole_pos, forearm_ik.head, plane_normal)
        pole_pos = forearm_ik.head + (
            (pole_pos - forearm_ik.head).normalized()
            * (forearm_ik.head - arm.head).magnitude
            * 1.0
        )

        c_pole_ik.head = pole_pos
        c_pole_ik.tail = [
            c_pole_ik.head[0],
            c_pole_ik.head[1],
            c_pole_ik.head[2] + (0.165 * arm_ik.length * 4),
        ]

        ik_pole_angle = get_pole_angle(arm_ik, forearm_ik, c_pole_ik.head)

        # Hand IK Ctrl
        c_hand_ik_name = c_prefix + arm_rig_names["hand_ik"] + _side
        c_hand_ik = create_edit_bone(c_hand_ik_name)
        set_bone_collection(rig, c_hand_ik, coll_ctrl_name)
        copy_bone_transforms(hand, c_hand_ik)

        # Hand FK Ctrl
        c_hand_fk_name = c_prefix + arm_rig_names["hand_fk"] + _side
        c_hand_fk = create_edit_bone(c_hand_fk_name)
        copy_bone_transforms(hand, c_hand_fk)
        c_hand_fk.parent = c_forearm_fk
        set_bone_collection(rig, c_hand_fk, coll_ctrl_name)

        # Add Slight bend to arms to avoid singularity
        if side == "Left":
            add_slight_bend(forearm_ik, Vector((0, 0, -1)))  # -Z axis for left
        else:  # Right
            add_slight_bend(forearm_ik, Vector((0, 0, 1)))  # +Z axis for right

        # Store data for pose mode
        edit_data[f"arm_{side.lower()}"] = {
            "exists": True,
            "side": side,
            "shoulder_name": shoulder_name,
            "arm_name": arm_name,
            "forearm_name": forearm_name,
            "hand_name": hand_name,
            "c_shoulder_name": c_shoulder_name,
            "arm_ik_name": arm_ik_name,
            "forearm_ik_name": forearm_ik_name,
            "c_arm_fk_name": c_arm_fk_name,
            "c_forearm_fk_name": c_forearm_fk_name,
            "c_pole_ik_name": c_pole_ik_name,
            "c_hand_ik_name": c_hand_ik_name,
            "c_hand_fk_name": c_hand_fk_name,
            "fingers_names": fingers_names,
            "c_fingers_names": c_fingers_names,
            "ik_pole_angle": ik_pole_angle,
        }

    # Ensure eye bones are in DEF collection
    eye_bone_names = ["RightEye", "LeftEye"]
    for eye_name in eye_bone_names:
        eye_bone = rig.data.edit_bones.get(eye_name)
        if eye_bone:
            set_bone_collection(rig, eye_bone, coll_mix_name)

    # ==========================================
    # PHASE 2: ALL POSE MODE OPERATIONS
    # ==========================================
    print("  Phase 2: Setting up all pose bones...")
    bpy.ops.object.mode_set(mode="POSE")

    # Master pose setup
    print("    Setting up Master pose...")
    c_master_pb = get_pose_bone(c_master_name)
    c_master_pb.bone["mixamo_ctrl"] = 1
    set_bone_custom_shape(c_master_pb, "cs_master")
    c_master_pb.rotation_mode = "XYZ"
    set_bone_color_group(rig, c_master_pb, "master")

    # Spine pose setup
    if edit_data["spine"].get("exists"):
        print("    Setting up Spine pose...")
        spine_data = edit_data["spine"]

        c_hips_pb = get_pose_bone(spine_data["c_hips_name"])
        get_pose_bone(spine_data["hips_free_h_name"])
        c_hips_free_pb = get_pose_bone(spine_data["c_hips_free_name"])
        c_spine_pb = get_pose_bone(spine_data["c_spine_name"])
        c_spine1_pb = get_pose_bone(spine_data["c_spine1_name"])
        c_spine2_pb = get_pose_bone(spine_data["c_spine2_name"])

        # tag controller bones
        for pb in [c_hips_pb, c_hips_free_pb, c_spine_pb, c_spine1_pb, c_spine2_pb]:
            pb.bone["mixamo_ctrl"] = 1

        # set custom shapes
        set_bone_custom_shape(c_hips_pb, "cs_square_2")
        set_bone_custom_shape(c_hips_free_pb, "cs_hips")
        set_bone_custom_shape(c_spine_pb, "cs_circle")
        set_bone_custom_shape(c_spine1_pb, "cs_circle")
        set_bone_custom_shape(c_spine2_pb, "cs_circle")

        # set rotation mode
        c_hips_pb.rotation_mode = "XYZ"
        c_hips_free_pb.rotation_mode = "XYZ"
        c_spine_pb.rotation_mode = "XYZ"
        c_spine1_pb.rotation_mode = "XYZ"
        c_spine2_pb.rotation_mode = "XYZ"

        # set color group
        set_bone_color_group(rig, c_hips_pb, "root_master")
        set_bone_color_group(rig, c_hips_free_pb, "body_mid")
        set_bone_color_group(rig, c_spine_pb, "body_mid")
        set_bone_color_group(rig, c_spine1_pb, "body_mid")
        set_bone_color_group(rig, c_spine2_pb, "body_mid")

        # constraints
        mixamo_spine_pb = get_pose_bone(spine_data["hips_name"])
        cns = mixamo_spine_pb.constraints.get("Copy Transforms")
        if cns is None:
            cns = mixamo_spine_pb.constraints.new("COPY_TRANSFORMS")
            cns.name = "Copy Transforms"
        cns.target = rig
        cns.subtarget = spine_data["hips_free_h_name"]

        # Spine
        spine_bone_matches = {
            "1": spine_data["c_spine_name"],
            "2": spine_data["c_spine1_name"],
            "3": spine_data["c_spine2_name"],
        }
        for str_idx in spine_bone_matches:
            c_name = spine_bone_matches[str_idx]
            mixamo_bname = get_src_bone_name(spine_names["spine" + str_idx])
            mixamo_spine_pb = get_pose_bone(mixamo_bname)
            cns = mixamo_spine_pb.constraints.get("Copy Transforms")
            if cns is None:
                cns = mixamo_spine_pb.constraints.new("COPY_TRANSFORMS")
                cns.name = "Copy Transforms"
            cns.target = rig
            cns.subtarget = c_name

    # Head pose setup
    if edit_data["head"].get("exists"):
        print("    Setting up Head pose...")
        head_data = edit_data["head"]

        c_neck_pb = get_pose_bone(head_data["c_neck_name"])
        c_head_pb = get_pose_bone(head_data["c_head_name"])

        # tag controller bones
        c_neck_pb.bone["mixamo_ctrl"] = 1
        c_head_pb.bone["mixamo_ctrl"] = 1

        # set custom shapes
        set_bone_custom_shape(c_neck_pb, "cs_neck")
        set_bone_custom_shape(c_head_pb, "cs_head")

        # set custom shape scale for head controller
        c_head_pb.custom_shape_scale_xyz[0] = 1.9
        c_head_pb.custom_shape_scale_xyz[1] = 1.9
        c_head_pb.custom_shape_scale_xyz[2] = 1.9

        # set rotation mode
        c_neck_pb.rotation_mode = "XYZ"
        c_head_pb.rotation_mode = "XYZ"

        # set color group
        set_bone_color_group(rig, c_neck_pb, "neck")
        set_bone_color_group(rig, c_head_pb, "head")

        # constraints
        neck_pb = get_pose_bone(head_data["neck_name"])
        head_pb = get_pose_bone(head_data["head_name"])

        add_copy_transf(neck_pb, rig, head_data["c_neck_name"])
        add_copy_transf(head_pb, rig, head_data["c_head_name"])

    # Leg pose setup for both sides
    for side in ["left", "right"]:
        if not edit_data[f"leg_{side}"].get("exists"):
            continue

        print(f"    Setting up Leg pose for {side}...")
        leg_data = edit_data[f"leg_{side}"]
        _side = "_" + leg_data["side"]

        # Get pose bones
        calf_ik_pb = get_pose_bone(leg_data["calf_ik_name"])
        foot_ik_pb = get_pose_bone(leg_data["foot_ik_name"])
        c_foot_ik_pb = get_pose_bone(leg_data["c_foot_ik_name"])
        c_pole_ik_pb = get_pose_bone(leg_data["c_pole_ik_name"])
        toes_end_pb = get_pose_bone(leg_data["toes_end_name"])
        toe_01_ik_pb = get_pose_bone(leg_data["toe_01_ik_name"])
        toe_02_pb = get_pose_bone(leg_data["toe_02_name"])
        toe_track_pb = get_pose_bone(leg_data["toe_track_name"])
        heel_mid_pb = get_pose_bone(leg_data["heel_mid_name"])
        heel_in_pb = get_pose_bone(leg_data["heel_in_name"])
        heel_out_pb = get_pose_bone(leg_data["heel_out_name"])
        foot_pb = get_pose_bone(leg_data["foot_name"])
        thigh_pb = get_pose_bone(leg_data["thigh_name"])
        calf_pb = get_pose_bone(leg_data["calf_name"])
        toe_pb = get_pose_bone(leg_data["toe_name"])
        c_foot_01_pb = get_pose_bone(leg_data["c_foot_01_name"])
        c_foot_roll_cursor_pb = get_pose_bone(leg_data["c_foot_roll_cursor_name"])
        c_thigh_fk_pb = get_pose_bone(leg_data["c_thigh_fk_name"])
        c_calf_fk_pb = get_pose_bone(leg_data["c_calf_fk_name"])
        c_foot_fk_pb = get_pose_bone(leg_data["c_foot_fk_name"])
        c_toe_ik_pb = get_pose_bone(leg_data["c_toe_ik_name"])
        c_toe_fk_pb = get_pose_bone(leg_data["c_toe_fk_name"])

        # Calf IK constraint
        cns_name = "IK"
        ik_cns = calf_ik_pb.constraints.get(cns_name)
        if ik_cns is None:
            ik_cns = calf_ik_pb.constraints.new("IK")
            ik_cns.name = cns_name
        ik_cns.target = rig
        ik_cns.subtarget = leg_data["foot_ik_target_name"]
        ik_cns.pole_target = rig
        ik_cns.pole_subtarget = leg_data["c_pole_ik_name"]
        ik_cns.pole_angle = leg_data["ik_pole_angle"]
        ik_cns.chain_count = 2
        ik_cns.use_tail = True
        ik_cns.use_stretch = False

        calf_ik_pb.lock_ik_y = True
        calf_ik_pb.lock_ik_z = True

        # Foot IK constraints
        cns_name = "Copy Location"
        copy_loc_cns = foot_ik_pb.constraints.get(cns_name)
        if copy_loc_cns is None:
            copy_loc_cns = foot_ik_pb.constraints.new("COPY_LOCATION")
            copy_loc_cns.name = cns_name
        copy_loc_cns.target = rig
        copy_loc_cns.subtarget = leg_data["calf_ik_name"]
        copy_loc_cns.head_tail = 1.0

        cns_name = "TrackTo"
        cns = foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = foot_ik_pb.constraints.new("TRACK_TO")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_foot_01_name"]
        cns.head_tail = 0.0
        cns.track_axis = "TRACK_Y"
        cns.up_axis = "UP_Z"
        cns.use_target_z = True

        cns_name = "Locked Track"
        cns = foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = foot_ik_pb.constraints.new("LOCKED_TRACK")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["foot_01_pole_name"]
        cns.head_tail = 0.0
        cns.track_axis = "TRACK_Z"
        cns.lock_axis = "LOCK_Y"

        cns_name = "Copy Scale"
        cns = foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = foot_ik_pb.constraints.new("COPY_SCALE")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_foot_ik_name"]

        # Foot Ctrl IK
        cns_name = "Child Of"
        cns = c_foot_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_foot_ik_pb.constraints.new("CHILD_OF")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = "Ctrl_Master"

        # Pole IK
        cns_name = "Child Of"
        child_cns = c_pole_ik_pb.constraints.get(cns_name)
        if child_cns is None:
            child_cns = c_pole_ik_pb.constraints.new("CHILD_OF")
            child_cns.name = cns_name
        child_cns.target = rig
        child_cns.subtarget = leg_data["c_foot_ik_name"]

        cns_power = 8

        # Toe End
        len = toes_end_pb.length * cns_power

        cns_name = "Transformation"
        cns = toes_end_pb.constraints.get(cns_name)
        if cns is None:
            cns = toes_end_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_foot_roll_cursor_name"]
        cns.use_motion_extrapolate = True
        cns.target_space = cns.owner_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_z = 0.5 * len
        cns.from_max_z = -0.5 * len
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_z_from = "X"
        cns.to_min_x_rot = -2.61
        cns.to_max_x_rot = 2.61
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = toes_end_pb.constraints.get(cns_name)
        if cns is None:
            cns = toes_end_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.owner_space = "LOCAL"
        cns.use_limit_x = True
        cns.min_x = -2 * pi
        cns.max_x = 0.0

        # Toe 01 ik
        cns_name = "Copy Transforms"
        cns = toe_01_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = toe_01_ik_pb.constraints.new("COPY_TRANSFORMS")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_toe_ik_name"]
        cns.mix_mode = "REPLACE"
        cns.target_space = cns.owner_space = "WORLD"

        # Toe 02
        cns_name = "Copy CopyRotation"
        cns = toe_02_pb.constraints.get(cns_name)
        if cns is None:
            cns = toe_02_pb.constraints.new("COPY_ROTATION")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_toe_ik_name"]
        cns.mix_mode = "REPLACE"
        cns.target_space = cns.owner_space = "WORLD"

        # Toe Track
        cns_name = "TrackTo"
        cns = toe_track_pb.constraints.get(cns_name)
        if cns is None:
            cns = toe_track_pb.constraints.new("TRACK_TO")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["toes_end_01_name"]
        cns.head_tail = 0.0
        cns.track_axis = "TRACK_Y"
        cns.up_axis = "UP_Z"
        cns.use_target_z = True

        # Heel Mid
        len = heel_mid_pb.length * cns_power

        cns_name = "Transformation"
        cns = heel_mid_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_mid_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_foot_roll_cursor_name"]
        cns.owner_space = cns.target_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_z = -0.25 * len
        cns.from_max_z = 0.25 * len
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_y_from = "X"
        cns.map_to_z_from = "Y"
        cns.to_min_x_rot = radians(100)
        cns.to_max_x_rot = -radians(100)
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = heel_mid_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_mid_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.use_limit_x = True
        cns.min_x = radians(0)
        cns.max_x = radians(360)
        cns.owner_space = "LOCAL"

        # Heel In
        len = heel_in_pb.length * cns_power

        cns_name = "Transformation"
        cns = heel_in_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_in_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_foot_roll_cursor_name"]
        cns.owner_space = cns.target_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_x = -0.25 * len
        cns.from_max_x = 0.25 * len
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_y_from = "X"
        cns.map_to_z_from = "Y"
        cns.to_min_y_rot = -radians(100)
        cns.to_max_y_rot = radians(100)
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = heel_in_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_in_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.use_limit_y = True

        if leg_data["side"] == "Left":
            cns.min_y = 0.0
            cns.max_y = radians(90)
        elif leg_data["side"] == "Right":
            cns.min_y = radians(-90)
            cns.max_y = radians(0.0)

        cns.owner_space = "LOCAL"

        # Heel Out
        len = heel_out_pb.length * cns_power

        cns_name = "Transformation"
        cns = heel_out_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_out_pb.constraints.new("TRANSFORM")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = leg_data["c_foot_roll_cursor_name"]
        cns.owner_space = cns.target_space = "LOCAL"
        cns.map_from = "LOCATION"
        cns.from_min_x = -0.25 * len
        cns.from_max_x = 0.25 * len
        cns.map_to = "ROTATION"
        cns.map_to_x_from = "Z"
        cns.map_to_y_from = "X"
        cns.map_to_z_from = "Y"
        cns.to_min_y_rot = -radians(100)
        cns.to_max_y_rot = radians(100)
        cns.mix_mode_rot = "ADD"

        cns_name = "Limit Rotation"
        cns = heel_out_pb.constraints.get(cns_name)
        if cns is None:
            cns = heel_out_pb.constraints.new("LIMIT_ROTATION")
            cns.name = cns_name
        cns.use_limit_y = True

        if leg_data["side"] == "Left":
            cns.min_y = radians(-90)
            cns.max_y = radians(0.0)
        elif leg_data["side"] == "Right":
            cns.min_y = radians(0.0)
            cns.max_y = radians(90)

        cns.owner_space = "LOCAL"

        # IK-FK switch property
        if "ik_fk_switch" not in c_foot_ik_pb.keys():
            create_custom_prop(
                node=c_foot_ik_pb,
                prop_name="ik_fk_switch",
                prop_val=0.0,
                prop_min=0.0,
                prop_max=1.0,
                prop_description="IK-FK switch value",
            )

        c_foot_ik_pb["ik_fk_switch"] = 0.0 if self.ik_legs else 1.0

        # Thigh
        cns_name = "IK_follow"
        cns_ik = thigh_pb.constraints.get(cns_name)
        if cns_ik is None:
            cns_ik = thigh_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_name
        cns_ik.target = rig
        cns_ik.subtarget = leg_data["thigh_ik_name"]
        cns_ik.influence = 1.0

        cns_name = "FK_follow"
        cns_fk = thigh_pb.constraints.get(cns_name)
        if cns_fk is None:
            cns_fk = thigh_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_name
        cns_fk.target = rig
        cns_fk.subtarget = leg_data["c_thigh_fk_name"]
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + leg_data["thigh_name"]
            + '"].constraints["'
            + cns_name
            + '"].influence',
            'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        # Calf
        cns_name = "IK_follow"
        cns_ik = calf_pb.constraints.get(cns_name)
        if cns_ik is None:
            cns_ik = calf_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_name
        cns_ik.target = rig
        cns_ik.subtarget = leg_data["calf_ik_name"]
        cns_ik.influence = 1.0

        cns_name = "FK_follow"
        cns_fk = calf_pb.constraints.get(cns_name)
        if cns_fk is None:
            cns_fk = calf_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_name
        cns_fk.target = rig
        cns_fk.subtarget = leg_data["c_calf_fk_name"]
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            f'pose.bones["{leg_data["calf_name"]}"].constraints["{cns_name}"].influence',
            'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        # Foot
        cns_name = "IK_follow"
        cns_ik = foot_pb.constraints.get(cns_name)
        if cns_ik is None:
            cns_ik = foot_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_name
        cns_ik.target = rig
        cns_ik.subtarget = leg_data["foot_ik_name"]
        cns_ik.influence = 1.0

        cns_name = "FK_follow"
        cns_fk = foot_pb.constraints.get(cns_name)
        if cns_fk is None:
            cns_fk = foot_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_name
        cns_fk.target = rig
        cns_fk.subtarget = leg_data["foot_fk_name"]
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            f'pose.bones["{leg_data["foot_name"]}"].constraints["{cns_name}"].influence',
            'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        # Toe
        cns_name = "IK_Rot_follow"
        cns_ik_rot = toe_pb.constraints.get(cns_name)
        if cns_ik_rot is None:
            cns_ik_rot = toe_pb.constraints.new("COPY_ROTATION")
            cns_ik_rot.name = cns_name
        cns_ik_rot.target = rig
        cns_ik_rot.subtarget = leg_data["c_toe_ik_name"]
        cns_ik_rot.influence = 1.0

        cns_name = "IK_Scale_follow"
        cns_ik_scale = toe_pb.constraints.get(cns_name)
        if cns_ik_scale is None:
            cns_ik_scale = toe_pb.constraints.new("COPY_SCALE")
            cns_ik_scale.name = cns_name
        cns_ik_scale.target = rig
        cns_ik_scale.subtarget = leg_data["c_toe_ik_name"]
        cns_ik_scale.influence = 1.0

        cns_name_fk_rot = "FK_Rot_follow"
        cns_fk_rot = toe_pb.constraints.get(cns_name_fk_rot)
        if cns_fk_rot is None:
            cns_fk_rot = toe_pb.constraints.new("COPY_ROTATION")
            cns_fk_rot.name = cns_name_fk_rot
        cns_fk_rot.target = rig
        cns_fk_rot.subtarget = leg_data["c_toe_fk_name"]
        cns_fk_rot.influence = 1.0

        cns_name_fk_scale = "FK_Scale_follow"
        cns_fk_scale = toe_pb.constraints.get(cns_name_fk_scale)
        if cns_fk_scale is None:
            cns_fk_scale = toe_pb.constraints.new("COPY_SCALE")
            cns_fk_scale.name = cns_name_fk_scale
        cns_fk_scale.target = rig
        cns_fk_scale.subtarget = leg_data["c_toe_fk_name"]
        cns_fk_scale.influence = 1.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + leg_data["toe_name"]
            + '"].constraints["'
            + cns_name_fk_rot
            + '"].influence',
            'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )
        add_driver_to_prop(
            rig,
            'pose.bones["'
            + leg_data["toe_name"]
            + '"].constraints["'
            + cns_name_fk_scale
            + '"].influence',
            'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        # Set transforms locks
        lock_pbone_transform(c_foot_roll_cursor_pb, "location", [1])
        lock_pbone_transform(c_foot_roll_cursor_pb, "rotation", [0, 1, 2])
        lock_pbone_transform(c_foot_roll_cursor_pb, "scale", [0, 1, 2])

        lock_pbone_transform(c_foot_01_pb, "location", [0, 1, 2])
        lock_pbone_transform(c_foot_01_pb, "rotation", [1, 2])
        lock_pbone_transform(c_foot_01_pb, "scale", [0, 1, 2])

        lock_pbone_transform(c_foot_fk_pb, "location", [0, 1, 2])

        lock_pbone_transform(c_pole_ik_pb, "rotation", [0, 1, 2])
        lock_pbone_transform(c_pole_ik_pb, "scale", [0, 1, 2])

        lock_pbone_transform(c_thigh_fk_pb, "location", [0, 1, 2])
        lock_pbone_transform(c_calf_fk_pb, "location", [0, 1, 2])

        c_pbones_list = [
            c_foot_ik_pb,
            c_pole_ik_pb,
            c_foot_01_pb,
            c_foot_roll_cursor_pb,
            c_thigh_fk_pb,
            c_calf_fk_pb,
            c_foot_fk_pb,
            c_toe_fk_pb,
            c_toe_ik_pb,
        ]

        # tag controller bones
        for pb in c_pbones_list:
            pb.bone["mixamo_ctrl"] = 1

        # Set custom shapes
        set_bone_custom_shape(c_thigh_fk_pb, "cs_thigh_fk")
        set_bone_custom_shape(c_calf_fk_pb, "cs_calf_fk")
        set_bone_custom_shape(c_foot_ik_pb, "cs_foot")
        set_bone_custom_shape(c_foot_fk_pb, "cs_foot")
        set_bone_custom_shape(c_pole_ik_pb, "cs_sphere_012")
        set_bone_custom_shape(c_foot_roll_cursor_pb, "cs_foot_roll")
        set_bone_custom_shape(c_foot_01_pb, "cs_foot_01")
        set_bone_custom_shape(c_toe_fk_pb, "cs_toe")
        set_bone_custom_shape(c_toe_ik_pb, "cs_toe")

        # set custom shape drivers
        ik_controls_names = [
            leg_data["c_foot_ik_name"],
            leg_data["c_foot_01_name"],
            leg_data["c_toe_ik_name"],
            leg_data["c_foot_roll_cursor_name"],
            leg_data["c_pole_ik_name"],
        ]

        arr_ids = [-1]
        if blender_version._float >= 300:
            arr_ids = [0, 1, 2]

        for n in ik_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="1-var")

        fk_controls_names = [
            leg_data["c_foot_fk_name"],
            leg_data["c_thigh_fk_name"],
            leg_data["c_calf_fk_name"],
            leg_data["c_toe_fk_name"],
        ]

        for n in fk_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + leg_data["c_foot_ik_name"] + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="var")

        for pb in c_pbones_list:
            # set rotation euler
            pb.rotation_mode = "XYZ"
            # set color group
            set_bone_color_group(rig, pb, "body" + _side.lower())

    # Arm pose setup for both sides
    for side in ["left", "right"]:
        if not edit_data[f"arm_{side}"].get("exists"):
            continue

        print(f"    Setting up Arm pose for {side}...")
        arm_data = edit_data[f"arm_{side}"]
        _side = "_" + arm_data["side"]

        # Get pose bones
        c_shoulder_pb = get_pose_bone(arm_data["c_shoulder_name"])
        shoulder_pb = get_pose_bone(arm_data["shoulder_name"])
        c_arm_fk_pb = get_pose_bone(arm_data["c_arm_fk_name"])
        forearm_ik_pb = get_pose_bone(arm_data["forearm_ik_name"])
        c_pole_ik_pb = get_pose_bone(arm_data["c_pole_ik_name"])
        c_hand_ik_pb = get_pose_bone(arm_data["c_hand_ik_name"])
        hand_pb = get_pose_bone(arm_data["hand_name"])
        arm_pb = get_pose_bone(arm_data["arm_name"])
        forearm_pb = get_pose_bone(arm_data["forearm_name"])
        c_forearm_fk_pb = get_pose_bone(arm_data["c_forearm_fk_name"])
        c_hand_fk_pb = get_pose_bone(arm_data["c_hand_fk_name"])

        # Arm FK Ctrl
        cns_name = "Copy Location"
        cns = c_arm_fk_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_arm_fk_pb.constraints.new("COPY_LOCATION")
            cns.name = cns_name
        cns.head_tail = 1.0
        cns.target = rig
        cns.subtarget = arm_data["c_shoulder_name"]

        # Forearm IK
        cns_name = "IK"
        ik_cns = forearm_ik_pb.constraints.get(cns_name)
        if ik_cns is None:
            ik_cns = forearm_ik_pb.constraints.new("IK")
            ik_cns.name = cns_name
        ik_cns.target = rig
        ik_cns.subtarget = arm_data["c_hand_ik_name"]
        ik_cns.pole_target = rig
        ik_cns.pole_subtarget = arm_data["c_pole_ik_name"]
        ik_cns.pole_angle = 0.0
        if arm_data["side"] == "Right":
            ik_cns.pole_angle = radians(180)
        ik_cns.chain_count = 2
        ik_cns.use_tail = True
        ik_cns.use_stretch = False

        forearm_ik_pb.lock_ik_y = True
        forearm_ik_pb.lock_ik_x = True

        # Pole IK Ctrl
        cns_name = "Child Of"
        cns = c_pole_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_pole_ik_pb.constraints.new("CHILD_OF")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_prefix + spine_rig_names["pelvis"]

        # Hand IK Ctrl
        cns_name = "Child Of"
        cns = c_hand_ik_pb.constraints.get(cns_name)
        if cns is None:
            cns = c_hand_ik_pb.constraints.new("CHILD_OF")
            cns.name = cns_name
        cns.target = rig
        cns.subtarget = c_master_name

        # Fingers
        for i, fname in enumerate(arm_data["c_fingers_names"]):
            c_finger_pb = get_pose_bone(fname)
            finger_pb = get_pose_bone(arm_data["fingers_names"][i])
            add_copy_transf(finger_pb, rig, c_finger_pb.name)

        # Shoulder
        add_copy_transf(shoulder_pb, rig, c_shoulder_pb.name)

        # IK-FK switch property
        if "ik_fk_switch" not in c_hand_ik_pb.keys():
            create_custom_prop(
                node=c_hand_ik_pb,
                prop_name="ik_fk_switch",
                prop_val=0.0,
                prop_min=0.0,
                prop_max=1.0,
                prop_description="IK-FK switch value",
            )

        c_hand_ik_pb["ik_fk_switch"] = 0.0 if self.ik_arms else 1.0

        # Arm
        cns_ik_name = "IK_follow"
        cns_ik = arm_pb.constraints.get(cns_ik_name)
        if cns_ik is None:
            cns_ik = arm_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_ik_name
        cns_ik.target = rig
        cns_ik.subtarget = arm_data["arm_ik_name"]
        cns_ik.influence = 1.0

        cns_fk_name = "FK_Follow"
        cns_fk = arm_pb.constraints.get(cns_fk_name)
        if cns_fk is None:
            cns_fk = arm_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_fk_name
        cns_fk.target = rig
        cns_fk.subtarget = arm_data["c_arm_fk_name"]
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + arm_data["arm_name"]
            + '"].constraints["'
            + cns_fk_name
            + '"].influence',
            'pose.bones["' + arm_data["c_hand_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        # ForeArm
        cns_ik_name = "IK_follow"
        cns_ik = forearm_pb.constraints.get(cns_ik_name)
        if cns_ik is None:
            cns_ik = forearm_pb.constraints.new("COPY_TRANSFORMS")
            cns_ik.name = cns_ik_name
        cns_ik.target = rig
        cns_ik.subtarget = arm_data["forearm_ik_name"]
        cns_ik.influence = 1.0

        cns_fk_name = "FK_Follow"
        cns_fk = forearm_pb.constraints.get(cns_fk_name)
        if cns_fk is None:
            cns_fk = forearm_pb.constraints.new("COPY_TRANSFORMS")
            cns_fk.name = cns_fk_name
        cns_fk.target = rig
        cns_fk.subtarget = arm_data["c_forearm_fk_name"]
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + arm_data["forearm_name"]
            + '"].constraints["'
            + cns_fk_name
            + '"].influence',
            'pose.bones["' + arm_data["c_hand_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        lock_pbone_transform(c_forearm_fk_pb, "location", [0, 1, 2])

        # Hand
        cns_ik_name = "IK_follow"
        cns_ik = hand_pb.constraints.get(cns_ik_name)
        if cns_ik is None:
            cns_ik = hand_pb.constraints.new("COPY_ROTATION")
            cns_ik.name = cns_ik_name
        cns_ik.target = rig
        cns_ik.subtarget = arm_data["c_hand_ik_name"]
        cns_ik.influence = 1.0

        cns_fk_name = "FK_Follow"
        cns_fk = hand_pb.constraints.get(cns_fk_name)
        if cns_fk is None:
            cns_fk = hand_pb.constraints.new("COPY_ROTATION")
            cns_fk.name = cns_fk_name
        cns_fk.target = rig
        cns_fk.subtarget = arm_data["c_hand_fk_name"]
        cns_fk.influence = 0.0

        add_driver_to_prop(
            rig,
            'pose.bones["'
            + arm_data["hand_name"]
            + '"].constraints["'
            + cns_fk_name
            + '"].influence',
            'pose.bones["' + arm_data["c_hand_ik_name"] + '"]["ik_fk_switch"]',
            array_idx=-1,
            exp="var",
        )

        lock_pbone_transform(c_hand_fk_pb, "location", [0, 1, 2])

        # Set custom shapes
        set_bone_custom_shape(c_shoulder_pb, "cs_shoulder_" + arm_data["side"].lower())
        set_bone_custom_shape(c_arm_fk_pb, "cs_arm_fk")
        set_bone_custom_shape(c_forearm_fk_pb, "cs_forearm_fk")
        set_bone_custom_shape(c_pole_ik_pb, "cs_sphere_012")
        set_bone_custom_shape(c_hand_fk_pb, "cs_circle")
        set_bone_custom_shape(c_hand_ik_pb, "cs_circle")

        c_fingers_pb = []

        for fname in arm_data["c_fingers_names"]:
            finger_pb = get_pose_bone(fname)
            c_fingers_pb.append(finger_pb)
            set_bone_custom_shape(finger_pb, "cs_circle_025")

        c_pbones_list = [
            c_shoulder_pb,
            c_arm_fk_pb,
            c_forearm_fk_pb,
            c_pole_ik_pb,
            c_hand_fk_pb,
            c_hand_ik_pb,
        ] + c_fingers_pb

        # tag controller bones
        for pb in c_pbones_list:
            pb.bone["mixamo_ctrl"] = 1

        # set custom shape drivers
        ik_controls_names = [arm_data["c_pole_ik_name"], arm_data["c_hand_ik_name"]]

        arr_ids = [-1]
        if blender_version._float >= 300:
            arr_ids = [0, 1, 2]

        for n in ik_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + arm_data["c_hand_ik_name"] + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="1-var")

        fk_controls_names = [
            arm_data["c_arm_fk_name"],
            arm_data["c_forearm_fk_name"],
            arm_data["c_hand_fk_name"],
        ]

        for n in fk_controls_names:
            dr_dp = 'pose.bones["' + n + '"].' + get_custom_shape_scale_prop_name()
            tar_dp = 'pose.bones["' + arm_data["c_hand_ik_name"] + '"]["ik_fk_switch"]'
            for arr_id in arr_ids:
                add_driver_to_prop(rig, dr_dp, tar_dp, array_idx=arr_id, exp="var")

        for pb in c_pbones_list:
            # set rotation euler
            pb.rotation_mode = "XYZ"
            # set color group
            set_bone_color_group(rig, pb, "body" + _side.lower())

    # Set custom_shape_wire_width for all control bones
    print("  Setting wire width for control bones...")
    ctrl_collection = rig.data.collections.get(coll_ctrl_name)
    if ctrl_collection:
        for bone in ctrl_collection.bones:
            pose_bone = rig.pose.bones.get(bone.name)
            if pose_bone:
                pose_bone.custom_shape_wire_width = 3.0

    # Set rig to not show in front
    rig.show_in_front = False

    # tag the armature with a custom prop to specify the control rig is built
    rig.data["mr_control_rig"] = True

    print("  Control rig build complete!")


def _zero_out(context):
    print("\nZeroing out...")
    arm = context.object

    print("  Clear anim")
    # Store the action for later if needed, then completely clear animation_data
    # This is the most reliable way to avoid dependency graph crashes in Blender 4.5+
    stored_action = None
    if arm.animation_data:
        try:
            stored_action = animation_compat.get_action_from_animdata(
                arm.animation_data
            )
            # Completely clear animation_data to avoid any dependency graph issues
            arm.animation_data_clear()
            action_name = stored_action.name if stored_action else "None"
            print(f"  Animation data cleared (action was: {action_name})")
        except Exception as e:
            print(f"  Warning: Could not clear animation data: {e}")
            # Fallback: just unlink
            try:
                arm.animation_data.action = None
                has_slots = animation_compat.has_slotted_actions()
                if has_slots and hasattr(arm.animation_data, "action_slot"):
                    arm.animation_data.action_slot = None
            except Exception:
                pass

    print("  Clear pose")
    # Reset pose
    bpy.ops.object.mode_set(mode="POSE")

    for b in arm.pose.bones:
        b.location = [0, 0, 0]
        b.rotation_euler = [0, 0, 0]
        b.rotation_quaternion = [1, 0, 0, 0]
        b.scale = [1, 1, 1]

    print("Zeroed out.")


def _bake_anim(self, context):
    scn = context.scene

    # get min-max frame range
    rig = context.object

    if rig.animation_data is None:
        print("No animation data, exit bake")
        return

    if rig.animation_data.nla_tracks is None:
        print("No NLA tracks found, exit bake")
        return

    tracks = rig.animation_data.nla_tracks

    fs = None
    fe = None

    # from NLA tracks
    for track in tracks:
        for strip in track.strips:
            if fs is None:
                fs = strip.frame_start
            if fe is None:
                fe = strip.frame_end

            if strip.frame_start < fs:
                fs = strip.frame_start
            if strip.frame_end > fe:
                fe = strip.frame_end

    if fs is None or fe is None:
        print("No NLA tracks found, exit")
        return

    # get active action frame range (compatible with both legacy and slotted actions)
    act = (
        animation_compat.get_action_from_animdata(rig.animation_data)
        if rig.animation_data
        else None
    )
    if act is not None:
        frame_range = animation_compat.get_action_frame_range(act)
        if frame_range[0] < fs:
            fs = frame_range[0]
        if frame_range[1] > fe:
            fe = frame_range[1]

    # select only controllers bones
    bpy.ops.object.mode_set(mode="POSE")
    bpy.ops.pose.select_all(action="DESELECT")

    found_ctrl = False
    for pbone in rig.pose.bones:
        if "mixamo_ctrl" in pbone.bone.keys():
            rig.data.bones.active = pbone.bone
            set_pose_bone_selected(pbone, True)
            found_ctrl = True

    if not found_ctrl:  # backward compatibility, use layer 0 instead
        print("Ctrl bones not tagged, search in layer 0 instead...")
        c0 = rig.data.collections.get("CTRL")
        if c0 is not None:
            for b in c0.bones:
                pb = rig.pose.bones.get(b.name)
                if pb is not None:
                    rig.data.bones.active = pb.bone
                    set_pose_bone_selected(pb, True)

        # ~ for pbone in rig.pose.bones:
        # ~ if pbone.bone.layers[0]:
        # ~ rig.data.bones.active = pbone.bone
        # ~ pbone.select = True

    fs, fe = int(fs), int(fe)

    scn.frame_set(fs)
    bpy.context.view_layer.update()

    # bake NLA strips
    print("Baking, frame start:", fs, ",frame end", fe)
    bpy.ops.nla.bake(
        frame_start=fs,
        frame_end=fe,
        step=1,
        only_selected=True,
        visual_keying=False,
        clear_constraints=False,
        clear_parents=False,
        use_current_action=False,
        clean_curves=False,
        bake_types={"POSE"},
    )

    # remove tracks
    while len(tracks):
        rig.animation_data.nla_tracks.remove(tracks[0])


def redefine_source_rest_pose(src_arm, tar_arm):
    """
    Redefine the source armature's rest pose to match the target's rest pose.
    This modifies src_arm directly (like 3.6 version)
    to ensure proper helper bone creation.
    """
    print("  Redefining source rest pose...")

    # Get frame range using compatibility function
    src_action = animation_compat.get_action_from_animdata(src_arm.animation_data)
    fr_range = animation_compat.get_action_frame_range(src_action)
    fr_start = int(fr_range[0])
    fr_end = int(fr_range[1])

    # Save source location
    src_arm_loc = src_arm.location.copy()
    src_arm.location = [0, 0, 0]

    # Duplicate source armature to preserve animation
    _deselect_all_objects()
    set_active_object(src_arm.name)
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass
    duplicate_object()
    src_arm_dupli = get_object(bpy.context.active_object.name)
    src_arm_dupli["mix_to_del"] = True

    """
    # Store bone matrices
    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    set_active_object(src_arm.name)
    bpy.ops.object.mode_set(mode='POSE')

    bones_data = []

    for f in range(fr_start, fr_end+1):
        print("Frame", f)
        scn.frame_set(f)
        bpy.context.view_layer.update()

        bones_matrices = {}

        for pbone in src_arm.pose.bones:
            bones_matrices[pbone.name] = pbone.matrix.copy()
            # bones_matrices[pbone.name] = src_arm.convert_space(
            #     pose_bone=pbone, matrix=pbone.matrix,
            #     from_space="POSE", to_space="LOCAL"
            # )


        bones_data.append((f, bones_matrices))
    """

    # Store target bones rest transforms
    _deselect_all_objects()
    set_active_object(tar_arm.name)
    try:
        bpy.ops.object.mode_set(mode="EDIT")
    except Exception:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")
        except Exception:
            pass

    rest_bones = {}

    for ebone in tar_arm.data.edit_bones:
        rest_bones[ebone.name] = (
            ebone.head.copy(),
            ebone.tail.copy(),
            vec_roll_to_mat3(ebone.y_axis, ebone.roll),
        )

    # Apply target rest pose to the ORIGINAL src_arm (like 3.6 version)
    print("  Set rest pose...")
    _deselect_all_objects()
    set_active_object(src_arm.name)
    try:
        bpy.ops.object.mode_set(mode="EDIT")
    except Exception:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")
        except Exception:
            pass

    for bname in rest_bones:
        ebone = src_arm.data.edit_bones.get(bname)

        if ebone is None:
            # print("Warning, bone not found on source armature:", bname)
            continue

        head, tail, mat3 = rest_bones[bname]
        ebone.head, ebone.tail, ebone.roll = (
            src_arm.matrix_world.inverted() @ head,
            src_arm.matrix_world.inverted() @ tail,
            mat3_to_vec_roll(src_arm.matrix_world.inverted().to_3x3() @ mat3),
        )

    # Add constraints to src_arm to follow duplicate's animation
    _deselect_all_objects()
    set_active_object(src_arm.name)
    try:
        bpy.ops.object.mode_set(mode="POSE")
    except Exception:
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="POSE")
        except Exception:
            pass

    for pb in src_arm.pose.bones:
        cns = pb.constraints.new("COPY_TRANSFORMS")
        cns.name = "temp"
        cns.target = src_arm_dupli
        cns.subtarget = pb.name

    # Restore animation
    print("Restore animation...")
    bake_anim(
        frame_start=fr_start,
        frame_end=fr_end,
        only_selected=False,
        bake_bones=True,
        bake_object=False,
    )

    # Restore location
    src_arm.location = src_arm_loc

    # Delete temp constraints
    for pb in src_arm.pose.bones:
        if len(pb.constraints):
            cns = pb.constraints.get("temp")
            if cns:
                pb.constraints.remove(cns)

    # Delete the duplicate
    delete_object(src_arm_dupli)

    print("  Source armature rest pose redefined.")


def add_slight_bend(bone, axis, angle=0.01):
    # Convert degrees to radians
    angle_rad = math.radians(angle)

    # Create a rotation matrix for a slight rotation around the specified axis
    rot_mat = Matrix.Rotation(angle_rad, 4, axis)

    # Apply the rotation to the bone's matrix
    bone.matrix = bone.matrix @ rot_mat


def _import_anim(src_arm, tar_arm, import_only=False):
    print("\nImporting animation...")

    if src_arm.animation_data is None:
        print("  No action found on the source armature")
        return

    src_action_check = animation_compat.get_action_from_animdata(src_arm.animation_data)
    if src_action_check is None:
        print("  No action found on the source armature")
        return

    src_fcurves = animation_compat.get_action_fcurves(src_action_check)
    if len(src_fcurves) == 0:
        print("  No keyframes to import")
        return

    # CRITICAL FIX: Work on a duplicate, then reassign src_arm like 3.6 does
    _deselect_all_objects()
    set_active_object(src_arm.name)

    # Detect if source armature uses mixamorig: prefix
    use_name_prefix = False
    detected_prefix = ""
    for bone in src_arm.data.bones:
        if bone.name.startswith("mixamorig") and ":" in bone.name:
            use_name_prefix = True
            detected_prefix = bone.name.split(":")[0] + ":"
            print(f"  Detected Mixamo prefix: {detected_prefix}")
            break
    if not use_name_prefix:
        print("  No Mixamo prefix detected, using plain bone names")
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    duplicate_object()
    src_arm_copy_name = src_arm.name + "_COPY"
    bpy.context.active_object.name = src_arm_copy_name

    # CRITICAL: Reassign src_arm to the copy, like 3.6 line 2465
    src_arm = get_object(src_arm_copy_name)
    src_arm["mix_to_del"] = True

    # Store the detected prefix on the source armature data
    # so get_mixamo_prefix() can find it
    # This is critical because get_mixamo_prefix() reads from active_object,
    # but we'll be
    # working with the target armature active when creating constraints
    src_arm.data["mixamo_prefix"] = detected_prefix

    # Helper function to construct source bone names with the correct prefix
    def get_src_bone_name(base_name):
        if use_name_prefix:
            return detected_prefix + base_name
        else:
            return base_name

    # Redefine source armature rest pose if importing only animation
    if import_only:
        redefine_source_rest_pose(src_arm, tar_arm)

    # Get anim data - AFTER redefine_source_rest_pose
    if src_arm.animation_data:
        action_src_anim_data = src_arm.animation_data
        action = animation_compat.get_action_from_animdata(action_src_anim_data)
    else:
        print("  ERROR: No animation data after rest pose redefine")
        return

    if action is None:
        print("  ERROR: No action found")
        return

    # Ensure proper slot assignment (4.4+)
    try:
        src_anim_data = src_arm.animation_data_create()
        animation_compat.assign_action_to_animdata(src_anim_data, action, src_arm)
    except Exception:
        pass

    frame_range = animation_compat.get_action_frame_range(action)
    fr_start = int(frame_range[0])
    fr_end = int(frame_range[1])

    # Ensure target is active for bone data collection
    _deselect_all_objects()
    set_active_object(tar_arm.name)
    try:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="POSE")
    except Exception:
        pass

    hand_left_name = get_src_bone_name("LeftHand")
    hand_right_name = get_src_bone_name("RightHand")
    foot_left_name = get_src_bone_name("LeftFoot")
    foot_right_name = get_src_bone_name("RightFoot")

    get_pose_bone(hand_left_name)
    c_hand_ik_left_pb = get_pose_bone(c_prefix + arm_rig_names["hand_ik"] + "_Left")
    get_pose_bone(hand_right_name)
    c_hand_ik_right_pb = get_pose_bone(c_prefix + arm_rig_names["hand_ik"] + "_Right")
    get_pose_bone(foot_left_name)
    c_foot_ik_left_pb = get_pose_bone(c_prefix + leg_rig_names["foot_ik"] + "_Left")
    get_pose_bone(foot_right_name)
    c_foot_ik_right_pb = get_pose_bone(c_prefix + leg_rig_names["foot_ik"] + "_Right")

    arm_left_kinematic = "IK" if c_hand_ik_left_pb["ik_fk_switch"] < 0.5 else "FK"
    arm_right_kinematic = "IK" if c_hand_ik_right_pb["ik_fk_switch"] < 0.5 else "FK"
    leg_left_kinematic = "IK" if c_foot_ik_left_pb["ik_fk_switch"] < 0.5 else "FK"
    leg_right_kinematic = "IK" if c_foot_ik_right_pb["ik_fk_switch"] < 0.5 else "FK"

    # Set bones mapping for retargetting
    bones_map = {}

    bones_map[get_src_bone_name("Hips")] = c_prefix + "Hips"
    bones_map[get_src_bone_name("Spine")] = c_prefix + "Spine"
    bones_map[get_src_bone_name("Spine1")] = c_prefix + "Spine1"
    bones_map[get_src_bone_name("Spine2")] = c_prefix + "Spine2"
    bones_map[get_src_bone_name("Neck")] = c_prefix + "Neck"
    bones_map[get_src_bone_name("Head")] = c_prefix + "Head"
    bones_map[get_src_bone_name("LeftShoulder")] = c_prefix + "Shoulder_Left"
    bones_map[get_src_bone_name("RightShoulder")] = c_prefix + "Shoulder_Right"

    # Arm
    if arm_left_kinematic == "FK":
        bones_map[get_src_bone_name("LeftArm")] = c_prefix + "Arm_FK_Left"
        bones_map[get_src_bone_name("LeftForeArm")] = c_prefix + "ForeArm_FK_Left"
        bones_map[get_src_bone_name("LeftHand")] = c_prefix + "Hand_FK_Left"
    elif arm_left_kinematic == "IK":
        bones_map[c_prefix + "Hand_IK_Left"] = c_prefix + "Hand_IK_Left"

    if arm_right_kinematic == "FK":
        bones_map[get_src_bone_name("RightArm")] = c_prefix + "Arm_FK_Right"
        bones_map[get_src_bone_name("RightForeArm")] = c_prefix + "ForeArm_FK_Right"
        bones_map[get_src_bone_name("RightHand")] = c_prefix + "Hand_FK_Right"
    elif arm_right_kinematic == "IK":
        bones_map[c_prefix + "Hand_IK_Right"] = c_prefix + "Hand_IK_Right"

    # Fingers
    bones_map[get_src_bone_name("LeftHandThumb1")] = c_prefix + "Thumb1_Left"
    bones_map[get_src_bone_name("LeftHandThumb2")] = c_prefix + "Thumb2_Left"
    bones_map[get_src_bone_name("LeftHandThumb3")] = c_prefix + "Thumb3_Left"
    bones_map[get_src_bone_name("LeftHandIndex1")] = c_prefix + "Index1_Left"
    bones_map[get_src_bone_name("LeftHandIndex2")] = c_prefix + "Index2_Left"
    bones_map[get_src_bone_name("LeftHandIndex3")] = c_prefix + "Index3_Left"
    bones_map[get_src_bone_name("LeftHandMiddle1")] = c_prefix + "Middle1_Left"
    bones_map[get_src_bone_name("LeftHandMiddle2")] = c_prefix + "Middle2_Left"
    bones_map[get_src_bone_name("LeftHandMiddle3")] = c_prefix + "Middle3_Left"
    bones_map[get_src_bone_name("LeftHandRing1")] = c_prefix + "Ring1_Left"
    bones_map[get_src_bone_name("LeftHandRing2")] = c_prefix + "Ring2_Left"
    bones_map[get_src_bone_name("LeftHandRing3")] = c_prefix + "Ring3_Left"
    bones_map[get_src_bone_name("LeftHandPinky1")] = c_prefix + "Pinky1_Left"
    bones_map[get_src_bone_name("LeftHandPinky2")] = c_prefix + "Pinky2_Left"
    bones_map[get_src_bone_name("LeftHandPinky3")] = c_prefix + "Pinky3_Left"
    bones_map[get_src_bone_name("RightHandThumb1")] = c_prefix + "Thumb1_Right"
    bones_map[get_src_bone_name("RightHandThumb2")] = c_prefix + "Thumb2_Right"
    bones_map[get_src_bone_name("RightHandThumb3")] = c_prefix + "Thumb3_Right"
    bones_map[get_src_bone_name("RightHandIndex1")] = c_prefix + "Index1_Right"
    bones_map[get_src_bone_name("RightHandIndex2")] = c_prefix + "Index2_Right"
    bones_map[get_src_bone_name("RightHandIndex3")] = c_prefix + "Index3_Right"
    bones_map[get_src_bone_name("RightHandMiddle1")] = c_prefix + "Middle1_Right"
    bones_map[get_src_bone_name("RightHandMiddle2")] = c_prefix + "Middle2_Right"
    bones_map[get_src_bone_name("RightHandMiddle3")] = c_prefix + "Middle3_Right"
    bones_map[get_src_bone_name("RightHandRing1")] = c_prefix + "Ring1_Right"
    bones_map[get_src_bone_name("RightHandRing2")] = c_prefix + "Ring2_Right"
    bones_map[get_src_bone_name("RightHandRing3")] = c_prefix + "Ring3_Right"
    bones_map[get_src_bone_name("RightHandPinky1")] = c_prefix + "Pinky1_Right"
    bones_map[get_src_bone_name("RightHandPinky2")] = c_prefix + "Pinky2_Right"
    bones_map[get_src_bone_name("RightHandPinky3")] = c_prefix + "Pinky3_Right"

    if leg_left_kinematic == "FK":
        bones_map[get_src_bone_name("LeftUpLeg")] = c_prefix + "UpLeg_FK_Left"
        bones_map[get_src_bone_name("LeftLeg")] = c_prefix + "Leg_FK_Left"
        bones_map[c_prefix + "Foot_FK_Left"] = c_prefix + "Foot_FK_Left"
        bones_map[get_src_bone_name("LeftToeBase")] = c_prefix + "Toe_FK_Left"
    elif leg_left_kinematic == "IK":
        bones_map[c_prefix + "Foot_IK_Left"] = c_prefix + "Foot_IK_Left"
        bones_map[get_src_bone_name("LeftToeBase")] = c_prefix + "Toe_IK_Left"

    if leg_right_kinematic == "FK":
        bones_map[get_src_bone_name("RightUpLeg")] = c_prefix + "UpLeg_FK_Right"
        bones_map[get_src_bone_name("RightLeg")] = c_prefix + "Leg_FK_Right"
        bones_map[c_prefix + "Foot_FK_Right"] = c_prefix + "Foot_FK_Right"
        bones_map[get_src_bone_name("RightToeBase")] = c_prefix + "Toe_FK_Right"
    elif leg_right_kinematic == "IK":
        bones_map[c_prefix + "Foot_IK_Right"] = c_prefix + "Foot_IK_Right"
        bones_map[get_src_bone_name("RightToeBase")] = c_prefix + "Toe_IK_Right"

    # Store bones data from target armature
    try:
        bpy.ops.object.mode_set(mode="EDIT")
    except Exception:
        pass

    ctrl_matrices = {}
    ik_bones_data = {}

    kinematics = {
        "HandLeft": ["Hand", arm_left_kinematic, "Left"],
        "HandRight": ["Hand", arm_right_kinematic, "Right"],
        "FootLeft": ["Foot", leg_left_kinematic, "Left"],
        "FootRight": ["Foot", leg_right_kinematic, "Right"],
    }
    for b in kinematics:
        type, kin_mode, side = kinematics[b]
        ctrl_name = c_prefix + type + "_" + kin_mode + "_" + side
        ctrl_ebone = get_edit_bone(ctrl_name)
        mix_bone_name = get_src_bone_name(side + type)

        ctrl_matrices[ctrl_name] = ctrl_ebone.matrix.copy(), mix_bone_name

        # store corrected ik bones
        if kin_mode == "IK":
            ik_bones = {}
            ik_chain = []

            if type == "Foot":
                ik_chain = ["UpLeg_IK_" + side, "Leg_IK_" + side]
            elif type == "Hand":
                ik_chain = ["Arm_IK_" + side, "ForeArm_IK_" + side]

            ik1 = get_edit_bone(ik_chain[0])
            ik2 = get_edit_bone(ik_chain[1])

            ik_bones["ik1"] = ik1.name, ik1.head.copy(), ik1.tail.copy(), ik1.roll
            ik_bones["ik2"] = ik2.name, ik2.head.copy(), ik2.tail.copy(), ik2.roll
            ik_bones_data[b] = type, side, ik_bones

    # Init source armature rotation and scale
    _deselect_all_objects()
    set_active_object(src_arm.name)

    try:
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    bpy.context.view_layer.update()

    scale_fac = src_arm.scale[0]
    print(f"  Source scale factor: {scale_fac}")

    try:
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        bpy.context.evaluated_depsgraph_get().update()
    except Exception as e:
        print(f"  Warning: Could not apply transforms: {e}")

    # Get F-Curves and scale location keyframes
    action_fcurves = animation_compat.get_action_fcurves(action)
    print(f"  Scaling {len(action_fcurves)} fcurves")
    for fc in action_fcurves:
        dp = fc.data_path
        if dp.startswith("pose.bones") and dp.endswith(".location"):
            for k in fc.keyframe_points:
                k.co[1] *= scale_fac

    # CRITICAL: Re-establish src_arm as active in EDIT mode for helper bone creation
    _deselect_all_objects()
    set_active_object(src_arm.name)
    bpy.context.view_layer.update()

    try:
        bpy.ops.object.mode_set(mode="EDIT")
    except Exception as e:
        print(f"  ERROR: Could not switch to EDIT mode: {e}")
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
            bpy.ops.object.mode_set(mode="EDIT")
        except Exception as e2:
            print(f"  CRITICAL: Mode switch failed: {e2}")
            return

    print(f"  Creating helper bones on {src_arm.name}")

    # Add helper source bones
    # add feet/hand bones helpers
    for name in ctrl_matrices:
        foot_ebone = create_edit_bone(name)
        foot_ebone.head, foot_ebone.tail = [0, 0, 0], [0, 0, 0.1]
        foot_ebone.matrix = ctrl_matrices[name][0]
        foot_ebone.parent = get_edit_bone(ctrl_matrices[name][1])
        print(f"    Created helper bone: {name}")

    # add IK bones helpers
    for b in ik_bones_data:
        type, side, ik_bones = ik_bones_data[b]
        for bone_type in ik_bones:
            bname, bhead, btail, broll = ik_bones[bone_type]
            ebone = create_edit_bone(bname)
            ebone.head, ebone.tail, ebone.roll = bhead, btail, broll
            print(f"    Created IK helper bone: {bname}")

    # set constraints in POSE mode
    try:
        bpy.ops.object.mode_set(mode="POSE")
    except Exception:
        pass

    bake_ik_data = {"src_arm": src_arm}

    for b in ik_bones_data:
        type, side, ik_bones = ik_bones_data[b]
        b1_name = ik_bones["ik1"][0]
        b2_name = ik_bones["ik2"][0]
        b1_pb = get_pose_bone(b1_name)
        b2_pb = get_pose_bone(b2_name)

        chain = []
        if type == "Foot":
            chain = [
                get_src_bone_name(side + "UpLeg"),
                get_src_bone_name(side + "Leg"),
            ]
            bake_ik_data["Leg" + side] = chain

        elif type == "Hand":
            chain = [
                get_src_bone_name(side + "Arm"),
                get_src_bone_name(side + "ForeArm"),
            ]
            bake_ik_data["Arm" + side] = chain

        cns = b1_pb.constraints.new("COPY_TRANSFORMS")
        cns.name = "Copy Transforms"
        cns.target = src_arm
        cns.subtarget = chain[0]

        cns = b2_pb.constraints.new("COPY_TRANSFORMS")
        cns.name = "Copy Transforms"
        cns.target = src_arm
        cns.subtarget = chain[1]

    # Retarget - Method 2: Constrained retargetting
    _deselect_all_objects()
    set_active_object(tar_arm.name)

    try:
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.mode_set(mode="POSE")
    except Exception as e:
        print(f"  ERROR switching to POSE: {e}")
        return

    bpy.ops.pose.select_all(action="DESELECT")
    bpy.context.view_layer.update()

    print("  Adding retarget constraints...")

    # add constraints
    for src_name in bones_map:
        tar_name = bones_map[src_name]
        src_bone = src_arm.pose.bones.get(src_name)
        tar_bone = tar_arm.pose.bones.get(tar_name)

        if src_bone is None:
            print(f"    SKIP: Source bone not found: {src_name}")
            continue
        if tar_bone is None:
            print(f"    SKIP: Target bone not found: {tar_name}")
            continue

        # All bones get COPY_ROTATION first
        cns_name = "Copy Rotation_retarget"
        cns = tar_bone.constraints.new("COPY_ROTATION")
        cns.name = cns_name
        cns.target = src_arm
        cns.subtarget = src_name

        # Hips gets COPY_LOCATION in LOCAL space
        if "Hips" in src_name:
            cns_name = "Copy Location_retarget"
            cns = tar_bone.constraints.new("COPY_LOCATION")
            cns.name = cns_name
            cns.target = src_arm
            cns.subtarget = src_name
            cns.owner_space = cns.target_space = "LOCAL"
            print(f"    Added Hips constraints: {src_name} -> {tar_name}")

        # Foot IK, Hand IK get COPY_LOCATION in POSE space
        if (
            (leg_left_kinematic == "IK" and "Foot_IK_Left" in src_name)
            or (leg_right_kinematic == "IK" and "Foot_IK_Right" in src_name)
            or (arm_left_kinematic == "IK" and "Hand_IK_Left" in src_name)
            or (arm_right_kinematic == "IK" and "Hand_IK_Right" in src_name)
        ):
            cns_name = "Copy Location_retarget"
            cns = tar_bone.constraints.new("COPY_LOCATION")
            cns.name = cns_name
            cns.target = src_arm
            cns.subtarget = src_name
            cns.target_space = cns.owner_space = "POSE"
            print(f"    Added IK constraints: {src_name} -> {tar_name}")

            # select IK poles
            _side = "_Left" if "Left" in src_name else "_Right"
            ik_pole_name = ""
            if "Hand" in src_name:
                ik_pole_name = c_prefix + arm_rig_names["pole_ik"] + _side
            elif "Foot" in src_name:
                ik_pole_name = c_prefix + leg_rig_names["pole_ik"] + _side

            ik_pole_ctrl = get_pose_bone(ik_pole_name)
            tar_arm.data.bones.active = ik_pole_ctrl.bone
            set_pose_bone_selected(ik_pole_ctrl, True)

        # select
        tar_arm.data.bones.active = tar_bone.bone
        set_pose_bone_selected(tar_bone, True)

    bpy.context.view_layer.update()

    # bake
    print(f"  Baking animation frames {fr_start} to {fr_end}...")
    bake_anim(
        frame_start=fr_start,
        frame_end=fr_end,
        only_selected=True,
        bake_bones=True,
        bake_object=False,
        ik_data=bake_ik_data,
    )

    # Cleanup
    try:
        _deselect_all_objects()
        set_active_object(tar_arm.name)
        bpy.ops.object.mode_set(mode="OBJECT")
    except Exception:
        pass

    print("Animation imported.")

    # Ensure target has proper action slot (4.4+)
    try:
        if tar_arm.animation_data and tar_arm.animation_data.action:
            animation_compat.assign_action_to_animdata(
                tar_arm.animation_data, tar_arm.animation_data.action, tar_arm
            )
    except Exception:
        pass


def remove_retarget_cns(armature):
    # print("Removing constraints...")
    for pb in armature.pose.bones:
        if len(pb.constraints):
            for cns in pb.constraints:
                if cns.name.endswith("_retarget") or cns.name == "temp":
                    pb.constraints.remove(cns)


def remove_temp_objects():
    for obj in bpy.data.objects:
        if "mix_to_del" in obj.keys():
            delete_object(obj)


def update_mixamo_tab():
    try:
        bpy.utils.unregister_class(MR_PT_MenuMain)
        bpy.utils.unregister_class(MR_PT_MenuRig)
        bpy.utils.unregister_class(MR_PT_MenuAnim)
        bpy.utils.unregister_class(MR_PT_MenuExport)
        bpy.utils.unregister_class(MR_PT_MenuUpdate)
    except Exception:
        pass

    MixamoRigPanel.bl_category = bpy.context.preferences.addons[
        __package__
    ].preferences.mixamo_tab_name
    bpy.utils.register_class(MR_PT_MenuMain)
    bpy.utils.register_class(MR_PT_MenuRig)
    bpy.utils.register_class(MR_PT_MenuAnim)
    bpy.utils.register_class(MR_PT_MenuExport)
    bpy.utils.register_class(MR_PT_MenuUpdate)


###########  UI PANELS  ###################
class MixamoRigPanel:
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mixamo"


class MR_PT_MenuMain(Panel, MixamoRigPanel):  # noqa: N801
    bl_label = "Mixamo Control Rig"

    def draw(self, context):
        layt = self.layout
        layt.use_property_split = True
        layt.use_property_decorate = False

        # col = layt.column(align=True)
        # col.scale_y = 1.3
        # col.prop_search(scn, "mix_source_armature", scn, "objects", text="Skeleton")
        arm_name = "None"

        if context.active_object is not None:
            if context.active_object.type == "ARMATURE":
                arm_name = context.active_object.name

        layt.label(text="Character: " + arm_name)


class MR_PT_MenuRig(Panel, MixamoRigPanel):  # noqa: N801
    bl_label = "Control Rig"
    bl_parent_id = "MR_PT_MenuMain"

    def draw(self, context):
        layt = self.layout
        layt.use_property_split = True
        layt.use_property_decorate = False

        """
        has_rigged = False
        if obj:
            if obj.type == "ARMATURE":
                if len(obj.data.keys()):
                    if "mr_data" in obj.data.keys():
                        has_rigged = True
        """

        col = layt.column(align=True)
        col.scale_y = 1.3

        col.operator(MR_OT_make_rig.bl_idname, text="Create Control Rig")
        col.operator(MR_OT_zero_out.bl_idname, text="Zero Out Rig")

        col = layt.column(align=True)
        col.separator()

        if context.mode != "EDIT_MESH":
            col.operator(MR_OT_edit_custom_shape.bl_idname, text="Edit Control Shape")
            col.operator(MR_OT_reconnect_rig.bl_idname, text="Reconnect Rig")
        else:
            col.operator(MR_OT_apply_shape.bl_idname, text="Apply Control Shape")


class MR_PT_MenuAnim(Panel, MixamoRigPanel):  # noqa: N801
    bl_label = "Animation"
    bl_parent_id = "MR_PT_MenuMain"

    def draw(self, context):
        layt = self.layout
        layt.use_property_split = True
        layt.use_property_decorate = False  # No animation.
        scn = context.scene
        layt.use_property_split = True
        layt.use_property_decorate = False

        col = layt.column(align=True)
        col.scale_y = 1
        # col.prop_search(
        #     scn, "mix_target_armature", scn, "objects", text="Control Rig"
        # )
        col.label(text="Source Skeleton:")
        col.prop_search(scn, "mix_source_armature", scn, "objects", text="")
        col.separator()

        col = layt.column(align=True)
        col.scale_y = 1.3
        col.operator(MR_OT_import_anim.bl_idname, text="Apply Animation to Control Rig")

        col = layt.column(align=True)
        col.scale_y = 1.3
        col.operator(MR_OT_bake_anim.bl_idname, text="Bake Animation")


class MR_PT_MenuUpdate(Panel, MixamoRigPanel):  # noqa: N801
    bl_label = "Update"
    bl_parent_id = "MR_PT_MenuMain"

    def draw(self, context):
        layt = self.layout
        layt.operator(MR_OT_update.bl_idname, text="Update Control Rig")


class MR_PT_MenuExport(Panel, MixamoRigPanel):  # noqa: N801
    bl_label = "Export"
    bl_parent_id = "MR_PT_MenuMain"

    def draw(self, context):
        layt = self.layout
        layt.operator(
            "export_scene.gltf", text="GLTF Export..."
        )  # MR_OT_exportGLTF.bl_idname


###########  REGISTER  ##################
classes = (
    MR_PT_MenuMain,
    MR_PT_MenuRig,
    MR_PT_MenuAnim,
    MR_PT_MenuExport,
    MR_PT_MenuUpdate,
    MR_OT_make_rig,
    MR_OT_zero_out,
    MR_OT_bake_anim,
    MR_OT_import_anim,
    MR_OT_reconnect_rig,
    MR_OT_edit_custom_shape,
    MR_OT_apply_shape,
    MR_OT_exportGLTF,
    MR_OT_update,
)


def register():
    from bpy.utils import register_class

    for cls in classes:
        register_class(cls)

    update_mixamo_tab()

    bpy.types.Scene.mix_source_armature = bpy.props.PointerProperty(
        type=bpy.types.Object
    )
    bpy.types.Scene.mix_target_armature = bpy.props.PointerProperty(
        type=bpy.types.Object
    )


def unregister():
    from bpy.utils import unregister_class

    for cls in reversed(classes):
        unregister_class(cls)

    del bpy.types.Scene.mix_source_armature
    del bpy.types.Scene.mix_target_armature


if __name__ == "__main__":
    register()
