# Apply Rotation, Scale, Origin

Author: ziazarenda. Blender 5.2 or newer.

Apply rotation and scale, then move each selected mesh or curve's origin to its geometry center. The origin uses Blender's **Median** method, as in the original addon.

## Install and use

1. Disable and remove any earlier version (the add-on folder is now called `arso`).
2. Install `arso-<version>.zip` from the Releases page (Edit > Preferences > Add-ons > Install from Disk) and enable it.
3. Select meshes or curves in Object Mode.
4. Run **Object > Apply > Rotation, Scale, Origin**.

The operator ID is unchanged: `object.apply_rotation_scale_origin`. Existing assigned shortcuts should continue to work. No shortcut is assigned automatically.

## What changed

- Shared mesh and curve data is left linked. If a selected object has multiple real data users, the whole batch stops before any changes. Make that data single-user manually if you want to process it separately. There is no extra checkbox.
- Apply Rotation & Scale explicitly leaves location unapplied. Centering the origin can still change the object's Location values while keeping its geometry in place.
- Unsupported selected types, such as cameras, lights and Empties, are ignored.
- Selection stays unchanged, and the original active object is restored.
- Errors name the object and failed step. Blender operator cancellations are checked too.
- If either step fails, the selected batch's original data and the affected objects' transforms are restored. A successful recovery reports **No objects changed**.
- If recovery cannot finish, the message says **Use Undo** and keeps an undoable operation.
- A successful operation can be undone as one step with Ctrl+Z.

Single-user objects use independent working data as a recovery copy. This never silently breaks existing links: shared data is rejected first. The addon removes unused temporary data after recovery and unused original data after success. Data with another user, a fake user, library ownership or asset status is preserved.

## Cases that stop before changes

The error identifies the affected object. Fix it and run the command again.

- Mesh or curve data has multiple real users. A fake user alone does not block the operation.
- Object cannot be edited, is a library override, or cannot use different data.
- Object uses bone or vertex parenting.
- Selected object has constraints, an animation action, NLA tracks or drivers. Use a static copy for this operation.
- Mesh has no vertices, or curve has no points.
- Curve is 2D: Blender's Apply Rotation operation requires changing it to 3D first.
- A child whose transforms may need adjustment cannot be edited.

One blocked object stops the selected batch before any changes. Other native Blender restrictions are caught during the operation and trigger recovery.

Modifiers are kept. Applying transforms or moving the origin can affect modifiers that depend on local coordinates or the origin, just as with Blender's own commands. Review the result before continuing.

## Tests and building

    python build.py                 plain tests, Blender tests, then dist/arso-<version>.zip
    python build.py --headless      same, without a Blender window
    python build.py --tests-only    run the tests, build nothing

- `tests/plain/` checks the add-on's logic with stand-ins for `bpy`. No Blender needed.
- `tests/blender/operator.py` runs the operator in a real Blender on the built zip, in an isolated settings folder: shared data is rejected without changes, parent/child geometry stays in place, origins end up centered, selection and the active object are restored, and blocked objects (constraints, 2D curves, empty meshes) stop the batch.
- **Undo (Ctrl+Z) is checked by hand.** Run the command on a copy of your project and confirm one Ctrl+Z undoes the whole operation.

`build.py`, `tests/plain/_run_all.py` and `tests/blender/_run_in_blender.py` come from [blender-addon-kit](https://github.com/ziazarenda/blender-addon-kit). Update them with `python sync_kit.py <this repo>` from the kit, not by hand.

License: MIT, as declared in the original project README.
