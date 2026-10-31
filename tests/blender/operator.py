import math

import bpy
from mathutils import Matrix, Vector

OP = bpy.ops.object.apply_rotation_scale_origin
checks = 0


def check(name, condition):
    global checks
    assert condition, name
    checks += 1
    print("PASS:", name)


def refresh():
    """Blender keeps stale view-layer entries after objects are added or removed."""
    bpy.context.view_layer.update()


def clean_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)

    for collection in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras):
        for item in list(collection):
            collection.remove(item)

    refresh()


def make_mesh(name, size=(1, 1, 1), offset=(0, 0, 0)):
    """A box whose vertices are shifted away from the origin."""
    mesh = bpy.data.meshes.new(name)
    sx, sy, sz = size
    corners = [(x * sx + offset[0], y * sy + offset[1], z * sz + offset[2])
               for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    mesh.from_pydata(corners, [], [])
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    refresh()
    return obj


def select(*objects, active=None):
    refresh()

    for obj in bpy.context.scene.objects:
        obj.select_set(False)

    for obj in objects:
        obj.select_set(True)

    bpy.context.view_layer.objects.active = active or (objects[0] if objects else None)
    bpy.context.view_layer.update()


def world_points(obj):
    refresh()
    return [obj.matrix_world @ v.co for v in obj.data.vertices]


def same_points(a, b, tolerance=1e-4):
    return len(a) == len(b) and all((p - q).length < tolerance for p, q in zip(a, b))


def local_median(obj):
    points = [v.co for v in obj.data.vertices]
    return sum(points, Vector()) / len(points)


def run():
    return OP()


# --- 1. shared mesh: rejected with nothing changed, then works once single-user
clean_scene()
first = make_mesh("first", offset=(3, 0, 0))
second = bpy.data.objects.new("second", first.data)
bpy.context.scene.collection.objects.link(second)
first.rotation_euler = (0.3, 0.2, 0.1)
first.scale = (2, 1, 1)
select(first)
bpy.context.view_layer.update()
before_points = world_points(first)
before_rotation = tuple(first.rotation_euler)
result = run()
check("shared mesh is rejected", result == {"CANCELLED"})
check("shared mesh: object transform untouched", tuple(first.rotation_euler) == before_rotation)
check("shared mesh: both objects still share the mesh", first.data is second.data)
check("shared mesh: geometry untouched", same_points(world_points(first), before_points))

first.data = first.data.copy()
select(first)
check("single-user mesh is accepted", run() == {"FINISHED"})
check("after fixing, geometry stays in place", same_points(world_points(first), before_points))
check("after fixing, scale is applied", all(abs(c - 1) < 1e-5 for c in first.scale))
check("after fixing, rotation is applied", all(abs(c) < 1e-5 for c in first.rotation_euler))
check("after fixing, origin is centered", local_median(first).length < 1e-4)

# --- 2. parent and child with rotation and non-uniform scale
clean_scene()
parent = make_mesh("parent", size=(1, 2, 3), offset=(1, 1, 0))
child = make_mesh("child", size=(0.5, 0.5, 0.5), offset=(0, 0, 4))
child.parent = parent
parent.rotation_euler = (math.radians(30), math.radians(10), math.radians(45))
parent.scale = (1, 2, 3)
parent.location = (2, -1, 0.5)
bpy.context.view_layer.update()
parent_before, child_before = world_points(parent), world_points(child)
select(parent)
check("parent-only run finishes", run() == {"FINISHED"})
check("parent geometry stays in place", same_points(world_points(parent), parent_before))
check("child geometry stays in place", same_points(world_points(child), child_before))
check("parent origin is centered", local_median(parent).length < 1e-4)
check("parent rotation and scale are applied",
      all(abs(c) < 1e-5 for c in parent.rotation_euler) and all(abs(c - 1) < 1e-5 for c in parent.scale))

# both selected: three variations, so a failure shows WHICH ingredient breaks it


def deviation(a, b):
    return max((p - q).length for p, q in zip(a, b))


def parent_child(parent_scale, child_rotation, child_scale):
    clean_scene()
    parent = make_mesh("parent", size=(1, 2, 3), offset=(1, 1, 0))
    child = make_mesh("child", size=(0.5, 0.5, 0.5), offset=(0, 0, 4))
    child.parent = parent
    parent.rotation_euler = (0.4, 0.2, 0.9)
    parent.scale = parent_scale
    child.rotation_euler = child_rotation
    child.scale = child_scale
    refresh()
    return parent, child


def run_both(label, parent_scale, child_rotation, child_scale):
    parent, child = parent_child(parent_scale, child_rotation, child_scale)
    parent_before, child_before = world_points(parent), world_points(child)
    select(parent, child)
    result = run()
    off_parent = deviation(world_points(parent), parent_before)
    off_child = deviation(world_points(child), child_before)
    centered = local_median(parent).length < 1e-4 and local_median(child).length < 1e-4
    detail = f"parent off by {off_parent:.5f}, child off by {off_child:.5f}"

    check(f"{label}: run finishes", result == {"FINISHED"})
    check(f"{label}: geometry stays in place ({detail})", off_parent < 1e-4 and off_child < 1e-4)
    check(f"{label}: origins centered", centered)


run_both("both, uniform parent scale, rotated and scaled child", (2, 2, 2), (0.1, 0.7, 0.2), (2, 2, 1))
run_both("both, non-uniform parent scale, plain child", (1, 2, 3), (0, 0, 0), (1, 1, 1))


# Blender's own Apply moves this child 5.8 units (a shear cannot be held in
# location/rotation/scale). The add-on must notice, change nothing, and say so.
parent, child = parent_child((1, 2, 3), (0.1, 0.7, 0.2), (2, 2, 1))
parent_before, child_before = world_points(parent), world_points(child)
scales = (tuple(parent.scale), tuple(child.scale))
meshes = (parent.data, child.data)
select(parent, child)
check("sheared hierarchy is refused", run() == {"CANCELLED"})
check("sheared hierarchy: parent unchanged", deviation(world_points(parent), parent_before) < 1e-4)
check("sheared hierarchy: child unchanged", deviation(world_points(child), child_before) < 1e-4)
check("sheared hierarchy: transforms restored", (tuple(parent.scale), tuple(child.scale)) == scales)
check("sheared hierarchy: original mesh data restored", (parent.data, child.data) == meshes)
check("sheared hierarchy: no temporary mesh data left", len(bpy.data.meshes) == 2)

# Far from the origin float error is larger; valid work must not be refused there.
clean_scene()
far_object = make_mesh("far", size=(1, 2, 3), offset=(10000, 5000, 2000))
far_object.rotation_euler = (0.3, 0.2, 0.1)
far_object.scale = (2, 1, 1)
refresh()
far_before = world_points(far_object)
select(far_object)
check("object 10000 units from the origin is accepted", run() == {"FINISHED"})
check("object 10000 units from the origin stays in place",
      deviation(world_points(far_object), far_before) < 0.05)

# Children with constraints or drivers: Blender may or may not keep them in place.
# Whatever it does, the command must never leave anything moved.


def never_leaves_moved(label, setup):
    parent, child = parent_child((2, 2, 2), (0.1, 0.2, 0.3), (1, 1, 1))
    setup(child)
    refresh()
    parent_before, child_before = world_points(parent), world_points(child)
    select(parent)
    result = run()
    check(f"{label}: command ends cleanly ({sorted(result)})", result in ({"FINISHED"}, {"CANCELLED"}))
    check(f"{label}: parent geometry unchanged", deviation(world_points(parent), parent_before) < 1e-3)
    check(f"{label}: child geometry unchanged", deviation(world_points(child), child_before) < 1e-3)


def add_constraint(child):
    target = bpy.data.objects.new("target", None)
    bpy.context.scene.collection.objects.link(target)
    target.location = (3, 4, 5)
    constraint = child.constraints.new("COPY_LOCATION")
    constraint.target = target


def add_driver(child):
    curve = child.driver_add("location", 0)
    curve.driver.type = "SCRIPTED"
    curve.driver.expression = "2.5"


never_leaves_moved("child with a constraint", add_constraint)
never_leaves_moved("child with a driver", add_driver)

# --- 3. a curve and an unsupported object; selection and active object come back
clean_scene()
box = make_mesh("box", offset=(2, 0, 0))
curve_data = bpy.data.curves.new("curve", "CURVE")
curve_data.dimensions = "3D"
spline = curve_data.splines.new("POLY")
spline.points.add(2)

for point, co in zip(spline.points, [(0, 0, 0, 1), (4, 0, 0, 1), (4, 4, 2, 1)]):
    point.co = co

curve = bpy.data.objects.new("curve", curve_data)
bpy.context.scene.collection.objects.link(curve)
camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
bpy.context.scene.collection.objects.link(camera)
curve.rotation_euler = (0.2, 0.4, 0.6)
curve.scale = (2, 2, 2)
select(box, curve, camera, active=camera)
selected_before = {o.name for o in bpy.context.scene.objects if o.select_get()}
camera_before = tuple(camera.matrix_world.translation)
check("mixed selection runs", run() == {"FINISHED"})
check("selection is unchanged",
      {o.name for o in bpy.context.scene.objects if o.select_get()} == selected_before)
check("active object is restored", bpy.context.view_layer.objects.active is camera)
check("unsupported object is untouched", tuple(camera.matrix_world.translation) == camera_before)
check("curve scale is applied", all(abs(c - 1) < 1e-5 for c in curve.scale))

# --- 4. blocked objects stop the whole batch with no changes
clean_scene()
good = make_mesh("good", offset=(2, 0, 0))
blocked = make_mesh("blocked")
blocked.constraints.new("TRACK_TO")
good.scale = (2, 2, 2)
select(good, blocked)
good_before = world_points(good)
check("a constrained object blocks the batch", run() == {"CANCELLED"})
check("blocked batch changed nothing", abs(good.scale.x - 2) < 1e-6 and same_points(world_points(good), good_before))

clean_scene()
empty = bpy.data.objects.new("empty_mesh", bpy.data.meshes.new("empty_mesh"))
bpy.context.scene.collection.objects.link(empty)
select(empty)
check("an empty mesh is rejected", run() == {"CANCELLED"})

clean_scene()
flat_data = bpy.data.curves.new("flat", "CURVE")
flat_data.dimensions = "2D"
flat_data.splines.new("POLY").points.add(1)
flat = bpy.data.objects.new("flat", flat_data)
bpy.context.scene.collection.objects.link(flat)
select(flat)
check("a 2D curve is rejected", run() == {"CANCELLED"})

# --- no leftovers from recovery copies
clean_scene()
single = make_mesh("single", offset=(1, 1, 1))
select(single)
meshes_before = len(bpy.data.meshes)
check("plain run finishes", run() == {"FINISHED"})
check("no temporary mesh data is left behind", len(bpy.data.meshes) == meshes_before)

clean_scene()
print(f"\nALL {checks} CHECKS PASSED")
