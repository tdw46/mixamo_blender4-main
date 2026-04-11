from types import SimpleNamespace

import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix

# Import from definitions
from .definitions.naming import (
    arm_rig_names,
    c_prefix,
    leg_rig_names,
)

# Import from lib modules
from .lib.bones_pose import (
    get_pose_bone,
    get_selected_pbone_name,
    is_pose_bone_selected,
    set_pose_bone_selected,
    update_transform,
)
from .lib.maths_geo import (
    get_ik_pole_pos,
    get_pose_matrix_in_other_space,
)
from .lib.mixamo import get_bone_side, get_mixamo_prefix

fk_leg = [
    c_prefix + leg_rig_names["thigh_fk"],
    c_prefix + leg_rig_names["calf_fk"],
    c_prefix + leg_rig_names["foot_fk"],
    c_prefix + leg_rig_names["toes_fk"],
]
ik_leg = [
    leg_rig_names["thigh_ik"],
    leg_rig_names["calf_ik"],
    c_prefix + leg_rig_names["foot_ik"],
    c_prefix + leg_rig_names["pole_ik"],
    c_prefix + leg_rig_names["toes_ik"],
    c_prefix + leg_rig_names["foot_01"],
    c_prefix + leg_rig_names["foot_roll_cursor"],
    leg_rig_names["foot_snap"],
]
fk_arm = [
    c_prefix + arm_rig_names["arm_fk"],
    c_prefix + arm_rig_names["forearm_fk"],
    c_prefix + arm_rig_names["hand_fk"],
]
ik_arm = [
    arm_rig_names["arm_ik"],
    arm_rig_names["forearm_ik"],
    c_prefix + arm_rig_names["hand_ik"],
    c_prefix + arm_rig_names["pole_ik"],
]

AUTO_SNAP_SWITCH_THRESHOLD = 0.05
AUTO_SNAP_SWITCH_EPSILON = 0.0001
AUTO_SNAP_CTRL_NAMES = (
    ("LEG", "Left", c_prefix + leg_rig_names["foot_ik"] + "_Left"),
    ("LEG", "Right", c_prefix + leg_rig_names["foot_ik"] + "_Right"),
    ("ARM", "Left", c_prefix + arm_rig_names["hand_ik"] + "_Left"),
    ("ARM", "Right", c_prefix + arm_rig_names["hand_ik"] + "_Right"),
)
_auto_snap_state = {}
_auto_snap_running = False

################## OPERATOR CLASSES ###################


def ensure_legacy_fk_foot_setup(context, rig):
    from .mixamo_rig import (
        _control_rig_needs_fk_foot_fix,
        _repair_fk_foot_setup,
    )

    if _control_rig_needs_fk_foot_fix(rig):
        _repair_fk_foot_setup(context, rig)


class MR_OT_arm_bake_fk_to_ik(bpy.types.Operator):  # noqa: N801
    """Snaps and bake an FK to an IK arm over a specified frame range"""

    bl_idname = "pose.mr_bake_arm_fk_to_ik"
    bl_label = "Snap an FK to IK arm over a specified frame range"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")
    frame_start: bpy.props.IntProperty(name="Frame start", default=0)
    frame_end: bpy.props.IntProperty(name="Frame end", default=10)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_start", text="Frame Start")
        layout.prop(self, "frame_end", text="Frame End")

    def invoke(self, context, event):
        action = context.active_object.animation_data.action
        self.frame_start, self.frame_end = (
            int(action.frame_range[0]),
            int(action.frame_range[1]),
        )
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False
        # save current autokey state
        auto_key_state = context.scene.tool_settings.use_keyframe_insert_auto
        # set auto key to True
        context.scene.tool_settings.use_keyframe_insert_auto = True

        try:
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            bake_fk_to_ik_arm(self)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo
            # restore autokey state
            context.scene.tool_settings.use_keyframe_insert_auto = auto_key_state

        return {"FINISHED"}


class MR_OT_arm_fk_to_ik(bpy.types.Operator):  # noqa: N801
    """Snaps an FK arm to an IK arm"""

    bl_idname = "pose.mr_arm_fk_to_ik_"
    bl_label = "Snap FK arm to IK"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)

            fk_to_ik_arm(self)

        finally:
            context.preferences.edit.use_global_undo = use_global_undo

        return {"FINISHED"}


class MR_OT_arm_bake_ik_to_fk(bpy.types.Operator):  # noqa: N801
    """Snaps and bake an IK to an FK arm over a specified frame range"""

    bl_idname = "pose.mr_bake_arm_ik_to_fk"
    bl_label = "Snap an IK to FK arm over a specified frame range"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")
    frame_start: bpy.props.IntProperty(name="Frame start", default=0)
    frame_end: bpy.props.IntProperty(name="Frame end", default=10)

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_start", text="Frame Start")
        layout.prop(self, "frame_end", text="Frame End")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False
        # save current autokey state
        auto_key_state = context.scene.tool_settings.use_keyframe_insert_auto
        # set auto key to True
        context.scene.tool_settings.use_keyframe_insert_auto = True

        try:
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)

            bake_ik_to_fk_arm(self)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo
            # restore autokey state
            context.scene.tool_settings.use_keyframe_insert_auto = auto_key_state

        return {"FINISHED"}


class MR_OT_arm_ik_to_fk(bpy.types.Operator):  # noqa: N801
    """Snaps an IK arm to an FK arm"""

    bl_idname = "pose.mr_arm_ik_to_fk_"
    bl_label = "Snap IK arm to FK"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)

            ik_to_fk_arm(self)

        finally:
            context.preferences.edit.use_global_undo = use_global_undo
        return {"FINISHED"}


class MR_OT_switch_snap_anim(bpy.types.Operator):  # noqa: N801
    """Switch and snap IK-FK over multiple frames"""

    bl_idname = "pose.mr_switch_snap_anim"
    bl_label = "Switch and Snap IK FK anim"
    bl_options = {"UNDO"}

    rig = None
    side: bpy.props.StringProperty(name="bone side", default="")
    _side = ""
    prefix: bpy.props.StringProperty(name="", default="")
    type: bpy.props.StringProperty(name="type", default="")

    frame_start: bpy.props.IntProperty(name="Frame start", default=0)
    frame_end: bpy.props.IntProperty(name="Frame end", default=10)
    has_action = False

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def draw(self, context):
        layout = self.layout
        if self.has_action:
            layout.prop(self, "frame_start", text="Frame Start")
            layout.prop(self, "frame_end", text="Frame End")
        else:
            layout.label(text="This rig is not animated!")

    def invoke(self, context, event):
        try:
            action = context.active_object.animation_data.action
            if action:
                self.has_action = True
        except Exception:
            pass

        if self.has_action:
            self.frame_start, self.frame_end = (
                int(action.frame_range[0]),
                int(action.frame_range[1]),
            )

        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def execute(self, context):
        if not self.has_action:
            return {"FINISHED"}

        try:
            scn = context.scene
            # save current autokey state
            auto_key_state = scn.tool_settings.use_keyframe_insert_auto
            # set auto key to True
            scn.tool_settings.use_keyframe_insert_auto = True
            # save current frame
            cur_frame = scn.frame_current

            self.rig = context.active_object
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()

            if is_selected(fk_leg, bname) or is_selected(ik_leg, bname):
                self.type = "LEG"
            elif is_selected(fk_arm, bname) or is_selected(ik_arm, bname):
                self.type = "ARM"

            if self.type == "ARM":
                c_hand_ik = get_pose_bone(
                    c_prefix + arm_rig_names["hand_ik"] + self._side
                )  # self.prefix+self.side+'Hand')
                if c_hand_ik["ik_fk_switch"] < 0.5:
                    bake_fk_to_ik_arm(self)
                else:
                    bake_ik_to_fk_arm(self)

            elif self.type == "LEG":
                ensure_legacy_fk_foot_setup(context, self.rig)

                c_foot_ik = get_pose_bone(
                    c_prefix + leg_rig_names["foot_ik"] + self._side
                )  # get_pose_bone(self.prefix+self.side+'Foot')
                if c_foot_ik["ik_fk_switch"] < 0.5:
                    bake_fk_to_ik_leg(self)
                else:
                    print("Bake IK to FK leg")
                    bake_ik_to_fk_leg(self)

        finally:
            # restore autokey state
            scn.tool_settings.use_keyframe_insert_auto = auto_key_state
            # restore frame
            scn.frame_set(cur_frame)

        return {"FINISHED"}


class MR_OT_switch_snap(bpy.types.Operator):  # noqa: N801
    """Switch and snap IK-FK for the current frame"""

    bl_idname = "pose.mr_switch_snap"
    bl_label = "Switch and Snap IK FK"
    bl_options = {"UNDO"}

    rig = None
    side: bpy.props.StringProperty(name="bone side", default="")
    _side = ""
    prefix: bpy.props.StringProperty(name="", default="")
    type: bpy.props.StringProperty(name="type", default="")
    force_keyframes = False
    suppress_keyframes = False
    apply_switch = True
    update_selection = True

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            self.rig = context.active_object
            self.force_keyframes = True
            clear_auto_snap_rig_state(self.rig)
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()
            prev_frame = context.scene.frame_current - 1

            if is_selected(fk_leg, bname) or is_selected(ik_leg, bname):
                self.type = "LEG"
            elif is_selected(fk_arm, bname) or is_selected(ik_arm, bname):
                self.type = "ARM"

            if self.type == "ARM":
                c_hand_ik = get_pose_bone(
                    c_prefix + arm_rig_names["hand_ik"] + self._side
                )
                if c_hand_ik["ik_fk_switch"] < 0.5:
                    insert_arm_ik_keys(self._side, prev_frame)
                    fk_to_ik_arm(self)
                else:
                    insert_arm_fk_keys(self._side, prev_frame)
                    ik_to_fk_arm(self)

            elif self.type == "LEG":
                ensure_legacy_fk_foot_setup(context, self.rig)

                c_foot_ik = get_pose_bone(
                    c_prefix + leg_rig_names["foot_ik"] + self._side
                )
                if c_foot_ik["ik_fk_switch"] < 0.5:
                    insert_leg_ik_keys(self._side, prev_frame)
                    fk_to_ik_leg(self)
                else:
                    insert_leg_fk_keys(self._side, prev_frame)
                    ik_to_fk_leg(self)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo

        return {"FINISHED"}


class MR_OT_switch_snap_no_key(bpy.types.Operator):  # noqa: N801
    """Switch and snap IK-FK for the current frame without creating keys"""

    bl_idname = "pose.mr_switch_snap_no_key"
    bl_label = "Snap IK/FK"
    bl_options = {"UNDO"}

    rig = None
    side: bpy.props.StringProperty(name="bone side", default="")
    _side = ""
    prefix: bpy.props.StringProperty(name="", default="")
    type: bpy.props.StringProperty(name="type", default="")
    force_keyframes = False
    suppress_keyframes = True
    apply_switch = True
    update_selection = True

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            self.rig = context.active_object
            clear_auto_snap_rig_state(self.rig)
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()

            if is_selected(fk_leg, bname) or is_selected(ik_leg, bname):
                self.type = "LEG"
            elif is_selected(fk_arm, bname) or is_selected(ik_arm, bname):
                self.type = "ARM"

            if self.type == "ARM":
                c_hand_ik = get_pose_bone(
                    c_prefix + arm_rig_names["hand_ik"] + self._side
                )
                if c_hand_ik["ik_fk_switch"] < 0.5:
                    fk_to_ik_arm(self)
                else:
                    ik_to_fk_arm(self)

            elif self.type == "LEG":
                ensure_legacy_fk_foot_setup(context, self.rig)

                c_foot_ik = get_pose_bone(
                    c_prefix + leg_rig_names["foot_ik"] + self._side
                )
                if c_foot_ik["ik_fk_switch"] < 0.5:
                    fk_to_ik_leg(self)
                else:
                    ik_to_fk_leg(self)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo

        return {"FINISHED"}


class MR_OT_leg_bake_fk_to_ik(bpy.types.Operator):  # noqa: N801
    """Snaps and bake an FK leg to an IK leg over a specified frame range"""

    bl_idname = "pose.mr_bake_leg_fk_to_ik"
    bl_label = "Snap an FK to IK leg over a specified frame range"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")
    _side = ""
    prefix = ""
    frame_start: bpy.props.IntProperty(name="Frame start", default=0)
    frame_end: bpy.props.IntProperty(name="Frame end", default=10)
    rig = None

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_start", text="Frame Start")
        layout.prop(self, "frame_end", text="Frame End")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False
        # save current autokey state
        auto_key_state = context.scene.tool_settings.use_keyframe_insert_auto
        # set auto key to True
        context.scene.tool_settings.use_keyframe_insert_auto = True

        try:
            self.rig = context.active_object
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()

            bake_fk_to_ik_leg(self)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo
            # restore autokey state
            context.scene.tool_settings.use_keyframe_insert_auto = auto_key_state

        return {"FINISHED"}


class MR_OT_leg_fk_to_ik(bpy.types.Operator):  # noqa: N801
    """Snaps an FK leg to an IK leg"""

    bl_idname = "pose.mr_leg_fk_to_ik_"
    bl_label = "Snap FK leg to IK"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")
    rig = None
    _side = ""
    prefix = ""

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False

        try:
            self.rig = context.active_object
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()

            fk_to_ik_leg(self)

        finally:
            context.preferences.edit.use_global_undo = use_global_undo
        return {"FINISHED"}


class MR_OT_leg_bake_ik_to_fk(bpy.types.Operator):  # noqa: N801
    """Snaps and bake an IK leg to an FK leg over a specified frame range"""

    bl_idname = "pose.mr_bake_leg_ik_to_fk"
    bl_label = "Snap an IK to FK leg over a specified frame range"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")
    frame_start: bpy.props.IntProperty(name="Frame start", default=0)
    frame_end: bpy.props.IntProperty(name="Frame end", default=10)
    rig = None
    _side = ""
    prefix = ""

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "frame_start", text="Frame Start")
        layout.prop(self, "frame_end", text="Frame End")

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self, width=400)

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False
        # save current autokey state
        auto_key_state = context.scene.tool_settings.use_keyframe_insert_auto
        # set auto key to True
        context.scene.tool_settings.use_keyframe_insert_auto = True

        try:
            self.rig = context.active_object
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()

            bake_ik_to_fk_leg(self)

        finally:
            context.preferences.edit.use_global_undo = use_global_undo
            # restore autokey state
            context.scene.tool_settings.use_keyframe_insert_auto = auto_key_state

        return {"FINISHED"}


class MR_OT_leg_ik_to_fk(bpy.types.Operator):  # noqa: N801
    """Snaps an IK leg to an FK leg"""

    bl_idname = "pose.mr_leg_ik_to_fk_"
    bl_label = "Snap IK leg to FK"
    bl_options = {"UNDO"}

    side: bpy.props.StringProperty(name="bone side")
    rig = None
    _side = ""
    prefix = ""

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.mode == "POSE"

    def execute(self, context):
        use_global_undo = context.preferences.edit.use_global_undo
        context.preferences.edit.use_global_undo = False
        try:
            self.rig = context.active_object
            bname = get_selected_pbone_name()
            self.side = get_bone_side(bname)
            self._side = "_" + self.side
            self.prefix = get_mixamo_prefix()

            ik_to_fk_leg(self)
        finally:
            context.preferences.edit.use_global_undo = use_global_undo

        return {"FINISHED"}


################## FUNCTIONS ##################


def set_pose_rotation(pose_bone, mat):
    q = mat.to_quaternion()

    if pose_bone.rotation_mode == "QUATERNION":
        pose_bone.rotation_quaternion = q
    elif pose_bone.rotation_mode == "AXIS_ANGLE":
        pose_bone.rotation_axis_angle[0] = q.angle
        pose_bone.rotation_axis_angle[1] = q.axis[0]
        pose_bone.rotation_axis_angle[2] = q.axis[1]
        pose_bone.rotation_axis_angle[3] = q.axis[2]
    else:
        pose_bone.rotation_euler = q.to_euler(pose_bone.rotation_mode)


def snap_pos(pose_bone, target_bone):
    # Snap a bone to another bone. Supports child of constraints and parent.

    # if the pose_bone has direct parent
    if pose_bone.parent:
        # apply double time because of dependecy lag
        pose_bone.matrix = target_bone.matrix
        update_transform()
        # second apply
        pose_bone.matrix = target_bone.matrix
    else:
        # is there a child of constraint attached?
        child_of_cns = None
        if len(pose_bone.constraints) > 0:
            all_child_of_cns = [
                i
                for i in pose_bone.constraints
                if i.type == "CHILD_OF"
                and i.influence == 1.0
                and not i.mute
                and i.target
            ]
            if len(all_child_of_cns) > 0:
                child_of_cns = all_child_of_cns[
                    0
                ]  # in case of multiple child of constraints enabled, use only the first for now  # noqa: E501

        if child_of_cns is not None:
            if child_of_cns.subtarget != "" and get_pose_bone(child_of_cns.subtarget):
                # apply double time because of dependecy lag
                pose_bone.matrix = (
                    get_pose_bone(child_of_cns.subtarget).matrix_channel.inverted()
                    @ target_bone.matrix
                )
                update_transform()
                pose_bone.matrix = (
                    get_pose_bone(child_of_cns.subtarget).matrix_channel.inverted()
                    @ target_bone.matrix
                )
            else:
                pose_bone.matrix = target_bone.matrix

        else:
            pose_bone.matrix = target_bone.matrix


def snap_pos_matrix(pose_bone, target_bone_matrix):
    # Snap a bone to another bone. Supports child of constraints and parent.

    # if the pose_bone has direct parent
    if pose_bone.parent:
        pose_bone.matrix = target_bone_matrix.copy()
        update_transform()
    else:
        # is there a child of constraint attached?
        child_of_cns = None
        if len(pose_bone.constraints) > 0:
            all_child_of_cns = [
                i
                for i in pose_bone.constraints
                if i.type == "CHILD_OF"
                and i.influence == 1.0
                and not i.mute
                and i.target
            ]
            if len(all_child_of_cns) > 0:
                child_of_cns = all_child_of_cns[
                    0
                ]  # in case of multiple child of constraints enabled, use only the first for now  # noqa: E501

        if child_of_cns is not None:
            if child_of_cns.subtarget != "" and get_pose_bone(child_of_cns.subtarget):
                subtarget_inv = get_pose_bone(
                    child_of_cns.subtarget
                ).matrix_channel.inverted()
                pose_bone.matrix = subtarget_inv @ target_bone_matrix
                update_transform()
            else:
                pose_bone.matrix = target_bone_matrix.copy()

        else:
            pose_bone.matrix = target_bone_matrix.copy()


def snap_rot(pose_bone, target_bone):
    method = 1

    if method == 1:
        mat = get_pose_matrix_in_other_space(target_bone.matrix, pose_bone)
        set_pose_rotation(pose_bone, mat)
        # bpy.ops.object.mode_set(mode='OBJECT')
        # bpy.ops.object.mode_set(mode='POSE')
        bpy.context.view_layer.update()
    elif method == 2:
        loc, scale = pose_bone.location.copy(), pose_bone.scale.copy()
        pose_bone.matrix = target_bone.matrix
        pose_bone.location, pose_bone.scale = loc, scale
        bpy.context.view_layer.update()


def should_insert_switch_keys(operator=None):
    if operator is not None and getattr(operator, "suppress_keyframes", False):
        return False
    if operator is not None and getattr(operator, "force_keyframes", False):
        return True
    return bpy.context.scene.tool_settings.use_keyframe_insert_auto


def insert_bone_key(pose_bone, data_path, frame=None):
    if pose_bone is None:
        return

    kwargs = {}
    if frame is not None:
        kwargs["frame"] = frame
    pose_bone.keyframe_insert(data_path=data_path, **kwargs)


def insert_arm_ik_keys(_side, frame=None):
    c_hand_ik = get_pose_bone(c_prefix + arm_rig_names["hand_ik"] + _side)
    hand_ik = get_pose_bone(ik_arm[2] + _side)
    pole_ik = get_pose_bone(ik_arm[3] + _side)

    insert_bone_key(c_hand_ik, '["ik_fk_switch"]', frame)
    insert_bone_key(hand_ik, "location", frame)
    insert_bone_key(hand_ik, "rotation_euler", frame)
    insert_bone_key(hand_ik, "scale", frame)
    insert_bone_key(pole_ik, "location", frame)


def insert_arm_fk_keys(_side, frame=None):
    arm_fk = get_pose_bone(fk_arm[0] + _side)
    forearm_fk = get_pose_bone(fk_arm[1] + _side)
    hand_fk = get_pose_bone(fk_arm[2] + _side)
    c_hand_ik = get_pose_bone(c_prefix + arm_rig_names["hand_ik"] + _side)

    insert_bone_key(c_hand_ik, '["ik_fk_switch"]', frame)
    insert_bone_key(hand_fk, "location", frame)
    insert_bone_key(hand_fk, "rotation_euler", frame)
    insert_bone_key(hand_fk, "scale", frame)
    insert_bone_key(arm_fk, "rotation_euler", frame)
    insert_bone_key(forearm_fk, "rotation_euler", frame)


def insert_leg_ik_keys(_side, frame=None):
    c_foot_ik = get_pose_bone(c_prefix + leg_rig_names["foot_ik"] + _side)
    foot_ik = get_pose_bone(ik_leg[2] + _side)
    pole_ik = get_pose_bone(ik_leg[3] + _side)
    toes_ik = get_pose_bone(ik_leg[4] + _side)
    foot_01_ik = get_pose_bone(ik_leg[5] + _side)
    foot_roll_ik = get_pose_bone(ik_leg[6] + _side)

    insert_bone_key(c_foot_ik, '["ik_fk_switch"]', frame)
    insert_bone_key(foot_01_ik, "rotation_euler", frame)
    insert_bone_key(foot_roll_ik, "location", frame)
    insert_bone_key(foot_ik, "location", frame)
    insert_bone_key(foot_ik, "rotation_euler", frame)
    insert_bone_key(foot_ik, "scale", frame)
    insert_bone_key(toes_ik, "rotation_euler", frame)
    insert_bone_key(toes_ik, "scale", frame)
    insert_bone_key(pole_ik, "location", frame)


def insert_leg_fk_keys(_side, frame=None):
    thigh_fk = get_pose_bone(fk_leg[0] + _side)
    leg_fk = get_pose_bone(fk_leg[1] + _side)
    foot_fk = get_pose_bone(fk_leg[2] + _side)
    toes_fk = get_pose_bone(fk_leg[3] + _side)
    c_foot_ik = get_pose_bone(c_prefix + leg_rig_names["foot_ik"] + _side)

    insert_bone_key(c_foot_ik, '["ik_fk_switch"]', frame)
    insert_bone_key(thigh_fk, "rotation_euler", frame)
    insert_bone_key(leg_fk, "rotation_euler", frame)
    insert_bone_key(foot_fk, "rotation_euler", frame)
    insert_bone_key(foot_fk, "scale", frame)
    insert_bone_key(toes_fk, "rotation_euler", frame)
    insert_bone_key(toes_fk, "scale", frame)


def get_switch_behavior_flags(operator):
    return (
        getattr(operator, "apply_switch", True),
        getattr(operator, "update_selection", True),
    )


def build_snap_context(rig, side, *, apply_switch=True, update_selection=True):
    return SimpleNamespace(
        rig=rig,
        side=side,
        _side="_" + side,
        prefix=get_mixamo_prefix(),
        force_keyframes=False,
        suppress_keyframes=True,
        apply_switch=apply_switch,
        update_selection=update_selection,
    )


def auto_prepare_switch_target(rig, limb_type, side, target_mode):
    snap_ctx = build_snap_context(
        rig,
        side,
        apply_switch=False,
        update_selection=False,
    )

    if limb_type == "LEG":
        from .mixamo_rig import _control_rig_needs_fk_foot_fix, _repair_fk_foot_setup

        if _control_rig_needs_fk_foot_fix(rig):
            _repair_fk_foot_setup(bpy.context, rig)

        if target_mode == "FK":
            fk_to_ik_leg(snap_ctx)
        else:
            ik_to_fk_leg(snap_ctx)
    elif limb_type == "ARM":
        if target_mode == "FK":
            fk_to_ik_arm(snap_ctx)
        else:
            ik_to_fk_arm(snap_ctx)


def get_auto_snap_rig_state(rig):
    return _auto_snap_state.setdefault(rig.as_pointer(), {})


def clear_auto_snap_rig_state(rig):
    if rig is None:
        return
    _auto_snap_state.pop(rig.as_pointer(), None)


@persistent
def auto_snap_ik_fk_slider_handler(scene, depsgraph):
    del scene, depsgraph

    global _auto_snap_running

    if _auto_snap_running:
        return

    context = bpy.context
    rig = context.active_object
    if rig is None or rig.type != "ARMATURE":
        return
    if context.mode != "POSE":
        return
    if "mr_control_rig" not in rig.data.keys():
        return

    pose = getattr(rig, "pose", None)
    if pose is None:
        return

    rig_state = get_auto_snap_rig_state(rig)

    for limb_type, side, ctrl_name in AUTO_SNAP_CTRL_NAMES:
        ctrl = pose.bones.get(ctrl_name)
        if ctrl is None or "ik_fk_switch" not in ctrl.keys():
            continue

        current = float(ctrl["ik_fk_switch"])
        state = rig_state.setdefault(
            ctrl_name,
            {
                "last": current,
                "prepared_fk": False,
                "prepared_ik": False,
            },
        )
        last = float(state.get("last", current))

        if current <= AUTO_SNAP_SWITCH_THRESHOLD:
            state["prepared_fk"] = False
        if current >= 1.0 - AUTO_SNAP_SWITCH_THRESHOLD:
            state["prepared_ik"] = False

        moving_toward_fk = (
            last <= AUTO_SNAP_SWITCH_THRESHOLD
            and current > last + AUTO_SNAP_SWITCH_EPSILON
        )
        moving_toward_ik = (
            last >= 1.0 - AUTO_SNAP_SWITCH_THRESHOLD
            and current < last - AUTO_SNAP_SWITCH_EPSILON
        )

        if moving_toward_fk and not state["prepared_fk"]:
            _auto_snap_running = True
            try:
                auto_prepare_switch_target(rig, limb_type, side, "FK")
                state["prepared_fk"] = True
            finally:
                _auto_snap_running = False
        elif moving_toward_ik and not state["prepared_ik"]:
            _auto_snap_running = True
            try:
                auto_prepare_switch_target(rig, limb_type, side, "IK")
                state["prepared_ik"] = True
            finally:
                _auto_snap_running = False

        state["last"] = float(ctrl["ik_fk_switch"])


def bake_fk_to_ik_arm(self):
    for f in range(self.frame_start, self.frame_end + 1):
        bpy.context.scene.frame_set(f)
        print("baking frame", f)
        fk_to_ik_arm(self)


def fk_to_ik_arm(self):
    rig = self.rig
    _side = self._side
    apply_switch, update_selection = get_switch_behavior_flags(self)

    arm_fk = rig.pose.bones[fk_arm[0] + _side]
    forearm_fk = rig.pose.bones[fk_arm[1] + _side]
    hand_fk = rig.pose.bones[fk_arm[2] + _side]

    arm_ik = rig.pose.bones[ik_arm[0] + _side]
    forearm_ik = rig.pose.bones[ik_arm[1] + _side]
    hand_ik = rig.pose.bones[ik_arm[2] + _side]

    # Snap rot
    snap_rot(arm_fk, arm_ik)
    snap_rot(forearm_fk, forearm_ik)
    snap_rot(hand_fk, hand_ik)

    # Snap scale
    hand_fk.scale = hand_ik.scale

    # rot debug
    forearm_fk.rotation_euler[0] = 0
    forearm_fk.rotation_euler[1] = 0

    # switch
    # base_hand = get_pose_bone(prefix+side+'Hand')
    c_hand_ik = get_pose_bone(c_prefix + arm_rig_names["hand_ik"] + _side)
    if apply_switch:
        c_hand_ik["ik_fk_switch"] = 1.0

    # udpate view
    bpy.context.view_layer.update()

    # insert key if autokey enable
    if should_insert_switch_keys(self):
        insert_arm_fk_keys(_side)
        insert_arm_ik_keys(_side)

    # change FK to IK hand selection, if selected
    if update_selection and is_pose_bone_selected(hand_ik):
        set_pose_bone_selected(hand_fk, True)
        set_pose_bone_selected(hand_ik, False)


def bake_ik_to_fk_arm(self):
    for f in range(self.frame_start, self.frame_end + 1):
        bpy.context.scene.frame_set(f)
        print("baking frame", f)

        ik_to_fk_arm(self)


def ik_to_fk_arm(self):
    rig = self.rig
    side = self.side
    _side = self._side
    apply_switch, update_selection = get_switch_behavior_flags(self)

    arm_fk = rig.pose.bones[fk_arm[0] + _side]
    forearm_fk = rig.pose.bones[fk_arm[1] + _side]
    hand_fk = rig.pose.bones[fk_arm[2] + _side]
    hand_ik = rig.pose.bones[ik_arm[2] + _side]
    pole_ik = rig.pose.bones[ik_arm[3] + _side]

    # Snap
    # constraint support
    constraint = None
    bparent_name = ""
    parent_type = ""
    valid_constraint = True

    # Snap Hand
    if len(hand_ik.constraints) > 0:
        for c in hand_ik.constraints:
            if not c.mute and c.influence > 0.5 and c.type == "CHILD_OF":
                if c.target:
                    # if bone
                    if c.target.type == "ARMATURE":
                        bparent_name = c.subtarget
                        parent_type = "bone"
                        constraint = c
                    # if object
                    else:
                        bparent_name = c.target.name
                        parent_type = "object"
                        constraint = c

    if constraint is not None:
        if parent_type == "bone":
            if bparent_name == "":
                valid_constraint = False

    if constraint and valid_constraint:
        if parent_type == "bone":
            bone_parent = get_pose_bone(bparent_name)
            hand_ik.matrix = bone_parent.matrix_channel.inverted() @ hand_fk.matrix
        if parent_type == "object":
            bone_parent = bpy.data.objects[bparent_name]
            obj_par = bpy.data.objects[bparent_name]
            inv_constraint = constraint.inverse_matrix.inverted()
            inv_world = obj_par.matrix_world.inverted()
            hand_ik.matrix = inv_constraint @ inv_world @ hand_fk.matrix
    else:
        hand_ik.matrix = hand_fk.matrix

    # Snap Pole
    _axis = forearm_fk.x_axis if side == "Left" else -forearm_fk.x_axis
    pole_pos = get_ik_pole_pos(arm_fk, forearm_fk, method=2, axis=_axis)
    pole_mat = Matrix.Translation(pole_pos)
    snap_pos_matrix(pole_ik, pole_mat)

    # Switch
    c_hand_ik = get_pose_bone(c_prefix + arm_rig_names["hand_ik"] + _side)
    # base_hand = get_pose_bone(prefix+side+'Hand')
    if apply_switch:
        c_hand_ik["ik_fk_switch"] = 0.0

    # update
    update_transform()

    # insert key if autokey enable
    if should_insert_switch_keys(self):
        insert_arm_ik_keys(_side)
        insert_arm_fk_keys(_side)

    # change FK to IK hand selection, if selected
    if update_selection and is_pose_bone_selected(hand_fk):
        set_pose_bone_selected(hand_fk, False)
        set_pose_bone_selected(hand_ik, True)


def bake_fk_to_ik_leg(self):
    for f in range(self.frame_start, self.frame_end + 1):
        bpy.context.scene.frame_set(f)
        print("baking frame", f)

        fk_to_ik_leg(self)


def fk_to_ik_leg(self):
    rig = self.rig
    _side = self._side
    apply_switch, update_selection = get_switch_behavior_flags(self)

    thigh_fk = rig.pose.bones[fk_leg[0] + _side]
    leg_fk = rig.pose.bones[fk_leg[1] + _side]
    foot_fk = rig.pose.bones[fk_leg[2] + _side]
    toes_fk = rig.pose.bones[fk_leg[3] + _side]

    thigh_ik = rig.pose.bones[ik_leg[0] + _side]
    leg_ik = rig.pose.bones[ik_leg[1] + _side]
    foot_ik = rig.pose.bones[ik_leg[2] + _side]
    toes_ik = rig.pose.bones[ik_leg[4] + _side]
    foot_snap_ik = rig.pose.bones[ik_leg[7] + _side]

    # Thigh snap
    snap_rot(thigh_fk, thigh_ik)
    # thigh_fk.matrix = thigh_ik.matrix.copy()

    # Leg snap
    snap_rot(leg_fk, leg_ik)

    # Foot snap
    snap_rot(foot_fk, foot_snap_ik)
    foot_fk.scale = foot_ik.scale

    # Toes snap
    snap_rot(toes_fk, toes_ik)
    toes_fk.scale = toes_ik.scale

    # rotation fix
    leg_fk.rotation_euler[1] = 0.0
    leg_fk.rotation_euler[2] = 0.0

    # switch prop value
    c_foot_ik = get_pose_bone(c_prefix + leg_rig_names["foot_ik"] + _side)
    # base_foot = get_pose_bone(prefix+side+'Foot')
    if apply_switch:
        c_foot_ik["ik_fk_switch"] = 1.0

    # udpate hack
    bpy.context.view_layer.update()

    # if bpy.context.scene.frame_current == 2:
    #    print(br)

    # insert key if autokey enable
    if should_insert_switch_keys(self):
        insert_leg_fk_keys(_side)
        insert_leg_ik_keys(_side)

    # change IK to FK foot selection, if selected
    if update_selection and is_pose_bone_selected(foot_ik):
        set_pose_bone_selected(foot_fk, True)
        set_pose_bone_selected(foot_ik, False)


def bake_ik_to_fk_leg(self):
    for f in range(self.frame_start, self.frame_end + 1):
        bpy.context.scene.frame_set(f)
        print("baking frame", f)  # noqa: F401

        ik_to_fk_leg(self)


def ik_to_fk_leg(self):  # noqa: F841
    rig = self.rig
    side = self.side  # noqa: F841
    _side = self._side
    prefix = self.prefix  # noqa: F841
    apply_switch, update_selection = get_switch_behavior_flags(self)

    thigh_fk = rig.pose.bones[fk_leg[0] + _side]
    leg_fk = rig.pose.bones[fk_leg[1] + _side]
    foot_fk = rig.pose.bones[fk_leg[2] + _side]
    toes_fk = rig.pose.bones[fk_leg[3] + _side]

    thigh_ik = rig.pose.bones[ik_leg[0] + _side]  # noqa: F841
    calf_ik = rig.pose.bones[ik_leg[1] + _side]  # noqa: F841
    foot_ik = rig.pose.bones[ik_leg[2] + _side]
    pole_ik = rig.pose.bones[ik_leg[3] + _side]
    toes_ik = rig.pose.bones[ik_leg[4] + _side]
    foot_01_ik = rig.pose.bones[ik_leg[5] + _side]
    foot_roll_ik = rig.pose.bones[ik_leg[6] + _side]

    # reset IK foot_01 and foot_roll
    foot_01_ik.rotation_euler = [0, 0, 0]
    foot_roll_ik.location[0] = 0.0
    foot_roll_ik.location[2] = 0.0

    # Snap toes
    toes_ik.rotation_euler = toes_fk.rotation_euler.copy()
    toes_ik.scale = toes_fk.scale.copy()

    # Child Of constraint or parent cases
    constraint = None
    bparent_name = ""
    parent_type = ""
    valid_constraint = True

    if len(foot_ik.constraints) > 0:
        for c in foot_ik.constraints:
            if not c.mute and c.influence > 0.5 and c.type == "CHILD_OF":
                if c.target:
                    # if bone
                    if c.target.type == "ARMATURE":
                        bparent_name = c.subtarget
                        parent_type = "bone"
                        constraint = c
                    # if object
                    else:
                        bparent_name = c.target.name
                        parent_type = "object"
                        constraint = c

    if constraint is not None:
        if parent_type == "bone":
            if bparent_name == "":
                valid_constraint = False

    # Snap Foot
    if constraint and valid_constraint:
        if parent_type == "bone":
            bone_parent = rig.pose.bones[bparent_name]
            foot_ik.matrix = bone_parent.matrix_channel.inverted() @ foot_fk.matrix
        if parent_type == "object":
            ob = bpy.data.objects[bparent_name]
            inv_constraint = constraint.inverse_matrix.inverted()
            inv_world = ob.matrix_world.inverted()
            foot_ik.matrix = inv_constraint @ inv_world @ foot_fk.matrix

    else:
        foot_ik.matrix = foot_fk.matrix

    # update
    bpy.context.view_layer.update()

    # Snap Pole
    pole_pos = get_ik_pole_pos(thigh_fk, leg_fk, method=2, axis=leg_fk.z_axis)
    pole_mat = Matrix.Translation(pole_pos)
    snap_pos_matrix(pole_ik, pole_mat)

    update_transform()

    # switch
    c_foot_ik = get_pose_bone(c_prefix + leg_rig_names["foot_ik"] + _side)
    # base_foot = get_pose_bone(prefix+side+'Foot')
    if apply_switch:
        c_foot_ik["ik_fk_switch"] = 0.0

    update_transform()

    # insert key if autokey enable
    if should_insert_switch_keys(self):
        insert_leg_ik_keys(_side)
        insert_leg_fk_keys(_side)

    # change IK to FK foot selection, if selected
    if update_selection and is_pose_bone_selected(foot_fk):
        set_pose_bone_selected(foot_fk, False)
        set_pose_bone_selected(foot_ik, True)


def get_active_child_of_cns(bone):
    constraint = None
    bparent_name = ""
    parent_type = ""
    valid_constraint = True

    if len(bone.constraints) > 0:
        for c in bone.constraints:
            if not c.mute and c.influence > 0.5 and c.type == "CHILD_OF":
                if c.target:
                    if c.target.type == "ARMATURE":  # bone
                        bparent_name = c.subtarget
                        parent_type = "bone"
                        constraint = c
                    else:  # object
                        bparent_name = c.target.name
                        parent_type = "object"
                        constraint = c

    if constraint:
        if parent_type == "bone":
            if bparent_name == "":
                valid_constraint = False

    return constraint, bparent_name, parent_type, valid_constraint


def is_selected(names, selected_bone_name, startswith=False):
    side = ""
    if get_bone_side(selected_bone_name) is not None:
        side = get_bone_side(selected_bone_name)

    _side = "_" + side

    if not startswith:
        if isinstance(names, list):
            for name in names:
                if "." not in name[-2:]:
                    if name + _side == selected_bone_name:
                        return True
                else:
                    if name[-2:] == ".x":
                        if name[:-2] + _side == selected_bone_name:
                            return True
        elif names == selected_bone_name:
            return True
    else:  # startswith
        if isinstance(names, list):
            for name in names:
                if selected_bone_name.startswith(name):
                    return True
        else:
            return selected_bone_name.startswith(names)
    return False


def is_selected_prop(pbone, prop_name):
    if pbone.bone.keys():
        if prop_name in pbone.bone.keys():
            return True


################## User Interface ##################
class MR_PT_rig_ui(bpy.types.Panel):  # noqa: N801
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Tool"
    bl_label = "Mixamo Rig Settings"
    bl_idname = "MR_PT_rig_ui"

    @classmethod
    def poll(cls, context):
        if context.mode != "POSE":
            return False
        return True

    def draw(self, context):  # noqa: F841
        layout = self.layout
        rig = context.active_object

        if rig is None:
            return
        if rig.type != "ARMATURE":
            return

        # check if a Mixamo ctrl rig is selected
        if len(rig.data.keys()):
            if "mr_control_rig" not in rig.data.keys():
                return
        else:
            return

        pose_bones = rig.pose.bones  # noqa: F841

        try:
            active_bone = context.selected_pose_bones[0]  # context.active_pose_bone
            selected_bone_name = active_bone.name
        except Exception:
            return

        side = get_bone_side(selected_bone_name)  # noqa: F841

        # Leg
        is_leg = is_selected(fk_leg, selected_bone_name) or is_selected(
            ik_leg, selected_bone_name
        )
        if is_leg:
            # IK-FK Switch
            col = layout.column(align=True)
            # foot_base = get_pose_bone(prefix+side.title()+'Foot')
            foot_ik_name = c_prefix + leg_rig_names["foot_ik"] + "_" + side.title()
            c_foot_ik = get_pose_bone(foot_ik_name)
            col.prop(c_foot_ik, '["ik_fk_switch"]', text="IK-FK Switch", slider=True)
            col.operator(MR_OT_switch_snap_no_key.bl_idname, text="Snap IK/FK")
            col.operator(MR_OT_switch_snap.bl_idname, text="Snap Frame IK/FK")
            col.operator(MR_OT_switch_snap_anim.bl_idname, text="Snap Anim IK-FK")

        # Arm
        is_arm = is_selected(fk_arm, selected_bone_name) or is_selected(
            ik_arm, selected_bone_name
        )
        if is_arm:
            # IK-FK Switch
            col = layout.column(align=True)
            # hand_base = get_pose_bone(prefix+side.title()+'Hand')
            hand_ik_name = c_prefix + arm_rig_names["hand_ik"] + "_" + side.title()
            c_hand_ik = get_pose_bone(hand_ik_name)
            col.prop(c_hand_ik, '["ik_fk_switch"]', text="IK-FK Switch", slider=True)
            col.operator(MR_OT_switch_snap_no_key.bl_idname, text="Snap IK/FK")
            col.operator(MR_OT_switch_snap.bl_idname, text="Snap Frame IK-FK")
            col.operator(MR_OT_switch_snap_anim.bl_idname, text="Snap Anim IK-FK")


##################  REGISTER  ##################
classes = (
    MR_OT_arm_bake_fk_to_ik,
    MR_OT_arm_fk_to_ik,
    MR_OT_arm_bake_ik_to_fk,
    MR_OT_arm_ik_to_fk,
    MR_OT_switch_snap_no_key,
    MR_OT_switch_snap,
    MR_OT_leg_fk_to_ik,
    MR_OT_leg_bake_fk_to_ik,
    MR_OT_leg_ik_to_fk,
    MR_OT_leg_bake_ik_to_fk,
    MR_PT_rig_ui,
    MR_OT_switch_snap_anim,
)


def update_mixamo_tab():
    try:
        bpy.utils.unregister_class(MR_PT_rig_ui)
    except Exception:
        pass

    prefs = bpy.context.preferences.addons[__package__].preferences
    MR_PT_rig_ui.bl_category = prefs.mixamo_tab_name
    bpy.utils.register_class(MR_PT_rig_ui)


def register():
    from bpy.utils import register_class

    for cls in classes:
        register_class(cls)

    update_mixamo_tab()

    bpy.types.Scene.mix_show_ik_fk_advanced = bpy.props.BoolProperty(
        name="Show IK-FK operators",
        description="Show IK-FK manual operators",
        default=False,
    )

    if auto_snap_ik_fk_slider_handler not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(auto_snap_ik_fk_slider_handler)


def unregister():
    from bpy.utils import unregister_class

    if auto_snap_ik_fk_slider_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(auto_snap_ik_fk_slider_handler)

    _auto_snap_state.clear()

    for cls in classes:
        unregister_class(cls)

    del bpy.types.Scene.mix_show_ik_fk_advanced
