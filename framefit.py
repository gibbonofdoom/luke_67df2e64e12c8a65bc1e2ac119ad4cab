import traceback
from typing import List, Optional
import numpy

import maya.OpenMaya as om
from maya import cmds, mel

"""

see framefit_animrig_current_panel_to_selected() function at the bottom of the file

# from Rigging.rAnimation import GetRig
    - I've not included our GetRig.get_all_rig_controls for this sample as your rigs
    - won't have the same embedded data that we use for this call to work
    - I've replaced with a very basic ls name filter below for this script
"""


def get_all_rig_controls() -> List[str]:
    """
    LOCAL_REPLACEMENT_FOR_THIS_FILE_ONLY

    EDIT THIS WITH YOUR RIG_CONTROL_NAME_STUFF IF YA LIKE

    Returns: List of controls

    """

    rig_control_suffixes = ['*_anim', '*_control']

    return cmds.ls(
        rig_control_suffixes,
        type=['transform', 'joint'],
        r=True
    )


def get_bounds_of_anim_control_shapes(
        control: str
) -> List[float]:
    """
    Get the worldspace bounds of the control without considering child objects

    Args:
        control:

    Returns: bounds [x_min, y_min, z_min, x_max, y_max, z_max]

    """

    shapes = cmds.listRelatives(control, shapes=True, ad=False)
    assert shapes, f'No shapes on control {control}'

    # massive initial bound volume
    min_x = 9999999
    max_x = -9999999
    min_y = 9999999
    max_y = -9999999
    min_z = 9999999
    max_z = -9999999

    # for shape in shapes:
    cmds.select(shapes)
    selection_list = om.MSelectionList()
    om.MGlobal.getActiveSelectionList(selection_list)

    selected_path = om.MDagPath()
    for i in range(len(shapes)):
        selection_list.getDagPath(i, selected_path)

        try:
            curve = om.MFnNurbsCurve(selected_path)
        except RuntimeError as e:
            # animation control shapes are expected to be a nurbs-curve, skip no biggy
            continue

        point_list = om.MPointArray()
        curve.getCVs(point_list, om.MSpace.kWorld)

        for j in range(point_list.length()):
            p = point_list[j]  # type: om.MPoint

            min_x = min(p.x, min_x)
            min_y = min(p.y, min_y)
            min_z = min(p.z, min_z)
            max_x = max(p.x, max_x)
            max_y = max(p.y, max_y)
            max_z = max(p.z, max_z)

    return [min_x, min_y, min_z, max_x, max_y, max_z]


def get_centre_in_bounds(
        min_x, min_y, min_z, max_x, max_y, max_z
) -> numpy.array:
    """ Return the centre of the bounding box """
    min_bounds = numpy.array([min_x, min_y, min_z])
    max_bounds = numpy.array([max_x, max_y, max_z])
    vector = min_bounds - max_bounds
    centre_pos = max_bounds + vector * 0.5
    return centre_pos


def framefit_animrig(
        target_camera: str,
        targets: List[str],
        zoom_amount: float = 0.25
) -> None:
    """
    Ever pressed F and your whole scene just zooms to infinity? Stop that now and rebind your key.

    This is a Better Frame-Fit for setting the camera properly. Built for icon generation,
    but useful replacement for animators and the default Maya (F)rame-fit

    Technical walkthrough:
        Frame-Fit to animation controls _only_
        Collect the mean bounding-box centres of animation control shape nodes using the CV points,
         _instead of_ the xform-bounding box data.
        Position the camera along the camera / bounds-centre vector * the zoom_amount

    Args:
        target_camera: target camera
        targets: items to focus on
        zoom_amount: increased zoom amount

    """

    # clean our target list to ensure they have a shape
    # collect our shapes as we need to select that for cmds.viewFit to ignore children
    shapes = []
    targets_ = []
    for i in targets:
        s = cmds.listRelatives(i, shapes=True)
        if not s:
            continue
        shapes.extend(s)
        targets_.append(i)

    if not targets_:
        # if there's no target objects to frame, then there's nothing left to work out
        return
    else:
        targets = targets_

    cmds.select(shapes)

    # run an initial fitPanel to get an approximate zoom-level (sometimes)
    # and free camera orientation
    # mel.eval('fitPanel -selectedNoChildren;')
    cmds.viewFit(target_camera, allObjects=False, fitFactor=0.8)

    invisible = cmds.ls(invisible=True, dag=True)

    # Get the centre points invididually for each shape for each control
    # normal frame fit will take into account the bounding box of the items and this
    # can cause some chaotic results
    centre_points = []
    for i in set(targets).difference(set(invisible)):

        try:
            target_local_bounds = get_bounds_of_anim_control_shapes(i)
        except AssertionError as e:
            # no shape, skip this target
            continue

        bounds_centre = get_centre_in_bounds(*target_local_bounds)
        centre_points.append(bounds_centre)

    centre_pos = numpy.mean(
        centre_points,
        axis=0
    )

    if zoom_amount == 0.0:
        return

    # calculate our current camera vector to selected
    camera_pos = numpy.array(cmds.xform(target_camera, q=True, ws=True, t=True))
    vector = centre_pos - camera_pos

    # maximum amount is "at the center pos"
    # minimum amount is "at the camera pos"
    delta = max(0.0, min(zoom_amount, 1.0))
    moveto_pos = camera_pos + vector * delta

    cmds.xform(target_camera, ws=True, t=list(moveto_pos))

    # update our camera centre-of-interest for orbit
    _coi_attr = f'{target_camera}.centerOfInterest'
    cmds.setAttr(_coi_attr, int(cmds.getAttr(_coi_attr) * (1 - delta)))


def framefit_animrig_current_panel_to_selected(
        target_camera: Optional[str] = None
) -> None:
    """
    Frame Fit User-Command for selected objects for current active modelPanel

    Args:
        target_camera: use this camera? if not, query current panel

    Returns:

    """

    if not target_camera:
        try:
            target_camera = cmds.modelEditor(
                cmds.getPanel(wf=True),
                q=True,
                camera=True
            )
        except RuntimeError as e:
            # this can fail if run from the script window, as that's not a valid thing with a camera
            # so fall-back to the default perspective
            target_camera = 'persp'

    # store current selection
    sel = cmds.ls(sl=True)

    try:
        cmds.undoInfo(openChunk=True)

        framefit_animrig(
            target_camera,
            # cmds.ls(sl=True, type=['transform', 'joint']) or GetRig.get_all_rig_controls()
            cmds.ls(sl=True, type=['transform', 'joint']) or get_all_rig_controls(),
            zoom_amount=0.25  # todo: send this via a user-setting query for customisation?
        )

    except Exception as e:
        # just catch exceptions and swallow them,
        # this is a non-destructive script
        traceback.print_exc()
        pass

    finally:
        cmds.undoInfo(closeChunk=True)

        # reselect user selection
        cmds.select(sel)


if __name__ == '__main__':
    framefit_animrig_current_panel_to_selected()
