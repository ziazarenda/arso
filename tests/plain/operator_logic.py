"""Logic checks for the pure helpers in the add-on, with a stand-in for bpy.

    python tests/plain/operator_logic.py
"""
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]

bpy = types.ModuleType("bpy")
bpy.types = NS(Operator=type("Operator", (), {}))
bpy.data = NS(meshes=NS(removed=[], remove=lambda d: bpy.data.meshes.removed.append(d)),
              curves=NS(removed=[], remove=lambda d: bpy.data.curves.removed.append(d)))
sys.modules["bpy"] = bpy

spec = importlib.util.spec_from_file_location(
    "addon", ROOT / "arso" / "__init__.py")
addon = importlib.util.module_from_spec(spec)
spec.loader.exec_module(addon)

checks = 0


def check(name, condition):
    global checks
    assert condition, name
    checks += 1
    print("ok:", name)


class Fake(NS):
    """Objects are used in sets and dicts, like Blender's, so they must hash."""

    __hash__ = object.__hash__


def obj(name, parent=None, children=(), **extra):
    value = Fake(name=name, parent=parent, children=list(children), type="MESH",
               is_editable=True, override_library=None, parent_type="OBJECT",
               constraints=[], animation_data=None,
               data=NS(users=1, use_fake_user=False, vertices=[1], library=None, asset_data=None),
               is_property_readonly=lambda prop: False)
    value.__dict__.update(extra)
    return value


# depth and ordering
root = obj("root")
mid = obj("mid", parent=root)
leaf = obj("leaf", parent=mid)
root.children, mid.children = [mid], [leaf]
check("parent_depth", [addon.parent_depth(o) for o in (root, mid, leaf)] == [0, 1, 2])
check("affected_objects includes descendants, parents first",
      [o.name for o in addon.affected_objects([root])] == ["root", "mid", "leaf"])
check("affected_objects does not duplicate", len(addon.affected_objects([root, leaf])) == 3)

# preflight problems
check("clean object has no problems", addon.object_problems(obj("a")) == [])

shared = obj("s")
shared.data.users = 2
check("shared data blocks", any("multiple users" in p for p in addon.object_problems(shared)))

fake = obj("f")
fake.data.users, fake.data.use_fake_user = 2, True
check("a fake user alone does not block", addon.object_problems(fake) == [])

locked = obj("l", is_editable=False)
check("non-editable blocks", any("cannot be edited" in p for p in addon.object_problems(locked)))

override = obj("o", override_library=object())
check("library override blocks", any("override" in p for p in addon.object_problems(override)))

readonly = obj("r", is_property_readonly=lambda prop: prop == "data")
check("read-only data blocks", any("different data" in p for p in addon.object_problems(readonly)))

bone = obj("b", parent=root, parent_type="BONE")
check("bone parenting blocks", any("bone parenting" in p for p in addon.object_problems(bone)))

constrained = obj("c", constraints=[NS(name="Track To")])
check("constraint named in message", any("Track To" in p for p in addon.object_problems(constrained)))

animated = obj("an", animation_data=NS(action=NS(name="Walk"), nla_tracks=[1], drivers=[1]))
check("action, NLA and drivers each reported", len(addon.object_problems(animated)) == 3)

empty = obj("e")
empty.data.vertices = []
check("empty mesh blocks", any("no vertices" in p for p in addon.object_problems(empty)))

spline = NS(points=[], bezier_points=[])
curve = obj("cv", type="CURVE", data=NS(users=1, use_fake_user=False, dimensions="2D",
                                         splines=[spline]))
messages = addon.object_problems(curve)
check("2D curve blocks", any("2D" in p for p in messages))
check("curve without points blocks", any("no points" in p for p in messages))

# recovery data cleanup
def data(users=0, fake=False, library=None, asset=None):
    return NS(users=users, use_fake_user=fake, library=library, asset_data=asset)


removed = bpy.data.meshes.removed
unused = data()
addon.remove_unused_data(unused, "MESH")
check("unused data is removed", removed == [unused])

for label, kept in (("used", data(users=1)), ("fake user", data(fake=True)),
                    ("library", data(library=object())), ("asset", data(asset=object()))):
    before = len(removed)
    addon.remove_unused_data(kept, "MESH")
    check(f"{label} data is kept", len(removed) == before)

curve_data = data()
addon.remove_unused_data(curve_data, "CURVE")
check("curve data uses the curves collection", bpy.data.curves.removed == [curve_data])

# message cleanup
check("short_error strips the Error prefix", addon.short_error(RuntimeError("Error: nope ")) == "nope")
check("short_error keeps other text", addon.short_error(RuntimeError("fine")) == "fine")

# registration surface
operator = addon.OBJECT_OT_apply_rotation_scale_origin
check("operator id is unchanged", operator.bl_idname == "object.apply_rotation_scale_origin")
check("operator supports undo", "UNDO" in operator.bl_options)
check("bl_info has a version tuple", len(addon.bl_info["version"]) == 3)

print(f"\nAll {checks} checks passed")
