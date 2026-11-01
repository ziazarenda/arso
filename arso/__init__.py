bl_info = {
    "name": "Apply Rotation, Scale, Origin",
    "author": "ziazarenda",
    "version": (1, 0, 1),
    "blender": (4, 0, 0),
    "location": "Object > Apply > Rotation, Scale, Origin",
    "description": "Apply rotation and scale, then center origins on the selected meshes and curves",
    "category": "Object",
}

import bpy


SUPPORTED_TYPES = {"MESH", "CURVE"}
_TRANSFORM_FIELDS = (
    "location", "rotation_euler", "rotation_quaternion", "rotation_axis_angle",
    "scale", "delta_location", "delta_rotation_euler",
    "delta_rotation_quaternion", "delta_scale", "matrix_parent_inverse",
)


def parent_depth(obj):
    """Process parents before their children."""
    depth = 0
    while obj.parent is not None:
        obj = obj.parent
        depth += 1
    return depth


def parents_first(objects):
    """Sort objects so parents come before their children."""
    return sorted(objects, key=lambda obj: (parent_depth(obj), obj.name))


def affected_objects(objects):
    """Include children whose transforms Blender may adjust."""
    found = set()
    pending = list(objects)
    while pending:
        obj = pending.pop()
        if obj not in found:
            found.add(obj)
            pending.extend(obj.children)
    return parents_first(found)


def object_problems(obj):
    """Check for problems before changing anything."""
    problems = []
    if obj.data.users - int(obj.data.use_fake_user) > 1:
        kind = "Mesh" if obj.type == "MESH" else "Curve"
        problems.append(f"{kind} data has multiple users. Make it single-user first to change this object separately")
    if not obj.is_editable:
        problems.append("This object cannot be edited. Make it local first")
    if obj.override_library is not None:
        problems.append("This object is a library override. Use a local copy")
    if obj.is_property_readonly("data"):
        problems.append("This object cannot use different data. Make a local copy first")
    if obj.parent is not None and obj.parent_type != "OBJECT":
        kind = {"BONE": "bone", "VERTEX": "vertex", "VERTEX_3": "three-vertex"}.get(obj.parent_type, obj.parent_type.lower())
        problems.append(f"This object uses {kind} parenting. Use object parenting")
    if obj.constraints:
        for constraint in obj.constraints:
            problems.append(f"This object has constraint '{constraint.name}'. Remove it or bake the object first")
    animation = obj.animation_data
    if animation is not None:
        if animation.action:
            problems.append(f"Animation '{animation.action.name}' is assigned. Use a static copy")
        if animation.nla_tracks:
            problems.append("NLA animation is present. Use a static copy")
        if animation.drivers:
            problems.append("Object drivers are present. Use a static copy")
    if obj.type == "MESH" and not obj.data.vertices:
        problems.append("The mesh has no vertices")
    if obj.type == "CURVE":
        if obj.data.dimensions == "2D":
            problems.append("Blender cannot apply rotation to a 2D curve. Change it to 3D first")
        if not any(spline.points or spline.bezier_points for spline in obj.data.splines):
            problems.append("The curve has no points")
    return problems


def transform_snapshot(obj):
    """Save the object's transform values for recovery."""
    values = {}
    for name in _TRANSFORM_FIELDS:
        value = getattr(obj, name)
        values[name] = value.copy() if hasattr(value, "copy") else tuple(value)
    return values


SAMPLE_LIMIT = 64


def sample_points(obj, include_axes):
    """World-space points that must not move.

    Geometry: mesh vertices and curve points, at most SAMPLE_LIMIT of them so a
    large mesh stays cheap to check. Axes: the four columns of the world matrix
    (position, rotation, scale and any shear). Axes are only meaningful for
    objects this command does not process, because applying rotation and scale
    changes the processed objects' own matrices on purpose.
    """
    matrix = obj.matrix_world
    points = [tuple(matrix.col[i])[:3] for i in range(4)] if include_axes else []
    if obj.type == "MESH":
        vertices = obj.data.vertices
        step = len(vertices) // SAMPLE_LIMIT + 1
        points.extend(tuple(matrix @ vertices[i].co) for i in range(0, len(vertices), step))
    elif obj.type == "CURVE":
        local = [p.co.xyz for spline in obj.data.splines for p in (*spline.points, *spline.bezier_points)]
        step = len(local) // SAMPLE_LIMIT + 1
        points.extend(tuple(matrix @ co) for co in local[::step])
    return points


POSITION_ABS_TOLERANCE = 1e-5
POSITION_REL_TOLERANCE = 2e-6  # about 17 steps of 32-bit float precision


def moved(before, after):
    """True if any sampled point ended up somewhere else.

    Each point is compared on its own: float error grows with how far the
    point is from the origin, so the allowance is relative to that point
    (never to the largest coordinate elsewhere in the scene).
    """
    if len(before) != len(after):
        return True
    for old, new in zip(before, after):
        size = max(abs(c) for c in (*old, *new))
        allowed = POSITION_ABS_TOLERANCE + POSITION_REL_TOLERANCE * size
        if any(abs(a - b) > allowed for a, b in zip(old, new)):
            return True
    return False


def has_moved(obj, before, selected):
    """True if the object's sampled points moved since `before` was taken.

    Selected objects are processed on purpose, so their own axes are not compared.
    """
    return moved(before, sample_points(obj, obj not in selected))


def remove_unused_data(data, object_type):
    """Remove temporary data only when nothing uses it."""
    if (data.users == 0 and not data.use_fake_user and data.library is None
            and not data.asset_data):
        collection = bpy.data.meshes if object_type == "MESH" else bpy.data.curves
        collection.remove(data)


def short_error(exc):
    """Remove Blender's repeated Error prefix."""
    message = str(exc).strip()
    return message[7:] if message.startswith("Error: ") else message


class OBJECT_OT_apply_rotation_scale_origin(bpy.types.Operator):
    """Apply rotation and scale, then center origins. Shared data is left unchanged. Supports Undo."""

    bl_idname = "object.apply_rotation_scale_origin"
    bl_label = "Apply Rotation, Scale, Origin"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and any(
            obj.type in SUPPORTED_TYPES for obj in context.selected_objects
        )

    def execute(self, context):
        objects = parents_first(obj for obj in context.selected_objects if obj.type in SUPPORTED_TYPES)
        if not objects:
            self.report({"WARNING"}, "Select a mesh or curve first")
            return {"CANCELLED"}

        try:
            affected = affected_objects(objects)
            problems = [(obj.name, message) for obj in objects for message in object_problems(obj)]
            problems.extend((obj.name, "This child cannot be edited. Make it local first")
                            for obj in affected if obj not in objects and not obj.is_editable)
            if problems:
                for name, message in problems:
                    self.report({"WARNING"}, f"'{name}': {message}. No objects changed")
                return {"CANCELLED"}
            context.view_layer.update()
            transforms = {obj: transform_snapshot(obj) for obj in affected}
            positions = {obj: sample_points(obj, obj not in objects) for obj in affected}
        except Exception as exc:
            self.report({"WARNING"}, f"Could not check the selection: {short_error(exc)}. No objects changed")
            return {"CANCELLED"}

        original_active = context.view_layer.objects.active
        originals = {obj: obj.data for obj in objects}
        working = []
        changed = False
        current = objects[0]
        step = "copy data"
        failure = None
        recovery_errors = []
        notices = []
        try:
            # Shared data was rejected before any edits. Stage independent
            # working data only to keep an untouched original for recovery.
            for current in objects:
                data = originals[current].copy()
                working.append((data, current.type))
                data.use_fake_user = False
                current.data = data
                changed = True

            for current in objects:
                context.view_layer.objects.active = current
                with context.temp_override(
                    object=current, active_object=current,
                    selected_objects=[current], selected_editable_objects=[current],
                ):
                    step = "apply rotation and scale"
                    result = bpy.ops.object.transform_apply(
                        location=False, rotation=True, scale=True, properties=True,
                    )
                    if "FINISHED" not in result:
                        raise RuntimeError("Blender did not finish applying rotation and scale")
                    context.view_layer.update()
                    step = "center the origin"
                    result = bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="MEDIAN")
                    if "FINISHED" not in result:
                        raise RuntimeError("Blender did not finish centering the origin")
                    context.view_layer.update()

            # Blender cannot hold some hierarchies in place (a parent with
            # non-uniform scale and a rotated child makes a shear). Its own
            # Apply moves them silently, so check and recover instead.
            step = "keep its position"
            for current in affected:
                if has_moved(current, positions[current], objects):
                    raise RuntimeError(
                        "Blender cannot hold this hierarchy in place. This happens with a parent that has "
                        "non-uniform scale and a rotated child, or with constraints or drivers on a child. "
                        "Make the parent's scale uniform, unparent, or remove those first")

        except Exception as exc:
            failure = f"'{current.name}': could not {step}: {short_error(exc)}"
            if changed:
                for obj, data in originals.items():
                    try:
                        obj.data = data
                    except Exception as recovery:
                        recovery_errors.append(f"'{obj.name}': could not restore data: {short_error(recovery)}")
                for obj, values in transforms.items():
                    for name, value in values.items():
                        try:
                            setattr(obj, name, value)
                        except Exception as recovery:
                            recovery_errors.append(f"'{obj.name}': could not restore {name}: {short_error(recovery)}")
                try:
                    context.view_layer.update()
                except Exception as recovery:
                    recovery_errors.append(f"Could not refresh restored objects: {short_error(recovery)}")
                # Do not assume the restore worked: check data and positions.
                for obj, data in originals.items():
                    if obj.data != data:
                        recovery_errors.append(f"'{obj.name}': original data was not restored")
                for obj in affected:
                    try:
                        if has_moved(obj, positions[obj], objects):
                            recovery_errors.append(f"'{obj.name}': could not be fully restored to its original position")
                    except Exception as recovery:
                        recovery_errors.append(f"'{obj.name}': could not verify the restore: {short_error(recovery)}")
            for data, object_type in working:
                try:
                    remove_unused_data(data, object_type)
                except Exception as cleanup:
                    notices.append(f"Could not remove unused temporary data: {short_error(cleanup)}")
        finally:
            try:
                context.view_layer.objects.active = original_active
            except Exception as exc:
                notices.append(f"Could not restore the active object: {short_error(exc)}")

        if failure:
            if recovery_errors:
                self.report({"ERROR"}, failure + ". Recovery failed. Use Undo")
                for message in recovery_errors:
                    self.report({"ERROR"}, message)
            else:
                self.report({"WARNING"}, failure + ". No objects changed")
            for message in notices:
                self.report({"WARNING"}, message)
            # FINISHED keeps an Undo step when recovery could not finish.
            return {"FINISHED"} if recovery_errors else {"CANCELLED"}

        for obj, data in originals.items():
            try:
                remove_unused_data(data, obj.type)
            except Exception as exc:
                notices.append(f"'{obj.name}': updated, but unused original data could not be removed: {short_error(exc)}")
        for message in notices:
            self.report({"WARNING"}, message)
        self.report({"INFO"}, f"Applied rotation and scale, centered origins on {len(objects)} object(s)")
        return {"FINISHED"}


def menu_func(self, context):
    self.layout.operator(OBJECT_OT_apply_rotation_scale_origin.bl_idname)
    self.layout.separator()


classes = (OBJECT_OT_apply_rotation_scale_origin,)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.VIEW3D_MT_object_apply.prepend(menu_func)


def unregister():
    bpy.types.VIEW3D_MT_object_apply.remove(menu_func)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
