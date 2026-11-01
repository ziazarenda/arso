# Apply Rotation, Scale, Origin

One menu entry that does three things you normally do by hand on every imported or modelled asset: **apply rotation**, **apply scale**, and **move the origin to the centre of the geometry**. It does this safely: it checks the selection first, keeps children and everything else in place, and puts everything back if something goes wrong.

> **Blender 4.0 or newer.** Works on **meshes and curves** in Object Mode.

[image or gif: before and after, objects with rotated and scaled transforms and off-centre origins]

---

## Contents

- [Why](#why)
- [Installation](#installation)
- [Usage](#usage)
- [What exactly happens](#what-exactly-happens)
- [Safety checks](#safety-checks)
- [When it refuses to run](#when-it-refuses-to-run)
- [Folder structure](#folder-structure)
- [Licence](#licence)

---

## Why

Game engines and many other tools expect clean transforms: rotation at 0, scale at 1, and an origin that sits on the object. In Blender that normally means:

1. `Ctrl+A` → Rotation & Scale
2. Right-click → Set Origin → Origin to Geometry

...for every object, while watching out for children that jump, shared mesh data that changes other objects, and animation that breaks. This add-on does both steps in one click and checks for those problems before it touches anything.

---

## Installation

1. Download `arso.zip` from the [Releases](../../releases) page (or use **Code → Download ZIP**).
2. In Blender open **Edit → Preferences → Add-ons**.
3. Open the drop-down in the top right, choose **Install from Disk…** and pick the zip.
4. Enable **Apply Rotation, Scale, Origin**.

[image of the Install from Disk menu]

---

## Usage

1. Switch to **Object Mode** and select one or more meshes or curves.
2. Open **Object → Apply → Rotation, Scale, Origin** (the same menu as `Ctrl+A` in the viewport).
3. The result is reported in the status bar, for example *Applied rotation and scale, centered origins on 3 object(s)*.

You can also search for **Apply Rotation, Scale, Origin** with `F3`. The operator id is `object.apply_rotation_scale_origin`, so you can assign it a shortcut.

[image of the Object → Apply menu with the new entry at the top]

The command supports **Undo**.

---

## What exactly happens

For each selected mesh or curve, parents first, then children:

1. **Apply rotation and scale.** Location is left alone.
2. **Origin to Geometry** (median centre), so the origin ends up in the middle of the object.
3. **Children and everything else stay put.** Children of the selected objects keep their world position, and the result is verified.

Only meshes and curves are processed. Other selected objects are ignored.

[image of an object with children before and after]

---

## Safety checks

Applying a transform in Blender can quietly move things or change other objects. This add-on checks first and verifies afterwards:

- **Nothing is changed unless every selected object passes the checks.** If one object has a problem, you get a message for each problem and no object changes.
- **Work happens on a copy of the mesh or curve data.** The untouched original is kept until the end. If anything fails along the way, the original data and every transform value are put back.
- **Positions are verified.** Sample points of every affected object (vertices or curve points, up to 64 each, plus the object axes for children) are compared before and after. If anything moved, the operation is rolled back.
- **The restore is verified too.** If something could not be restored, the message says so and tells you to use **Undo**.
- **Selection is restored.** The active object stays the active object.
- **Temporary data is cleaned up.** Unused leftovers are removed, and data that is used elsewhere, has a fake user, is linked from a library or is marked as an asset is never deleted.

---

## When it refuses to run

The add-on stops without changing anything, and says why, when an object:

| Problem | What to do |
|---------|------------|
| Its mesh or curve data is shared with other objects | Make it single-user first |
| Is not editable, or is a library override | Make a local copy |
| Has constraints | Remove them or bake the object |
| Has an action, NLA tracks or drivers | Use a static copy |
| Uses bone, vertex or three-vertex parenting | Use object parenting |
| Is a 2D curve | Change it to 3D first |
| Has no vertices, or a curve has no points | Nothing to apply |
| Has a child that cannot be edited | Make the child local |

It also stops, and restores everything, if Blender cannot hold a hierarchy in place. That happens with a parent that has non-uniform scale and a rotated child, because the result would need a shear. Make the parent's scale uniform or unparent first.

[image of a warning message in the status bar]

---

## Folder structure

```text
arso/
└── __init__.py     the whole add-on: the operator, the safety checks and the menu entry
```

The add-on is a single file on purpose, since it only adds one command. Inside it:

| Part | Purpose |
|------|---------|
| `object_problems` | Checks one object before anything is changed |
| `transform_snapshot` | Saves transform values so they can be restored |
| `sample_points` / `moved` | Measures whether anything changed position |
| `OBJECT_OT_apply_rotation_scale_origin` | The operator: check, work on copies, verify, recover |
| `menu_func` / `register` | Adds the entry to **Object → Apply** |

---

## Licence

See the `LICENSE` file.
