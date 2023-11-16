from typing import Optional, List

import sys
import os
import shutil
import subprocess
import threading
import pathlib

import pymel.core as pm
from maya import cmds


"""
########################################################################################################################

Bit of example script for a threaded headless maya execution as part of one of our export jobs to generate
animator-friendly animation rigs (instead of full blown master rigs with all our physics, lods etc)

This script scans the current file, collects the data, and spins up a headless maya for each _Anim.mb we want to build
and runs our cleanup script for each version in paralell, rather than step through the same scene multiple times.

########################################################################################################################
"""


def anim_rig_generator(
        target_anim_sets: Optional[List] = None,
        pre_export_script_path: Optional[str] = None,
        extension: Optional[str] = 'mb'
) -> None:
    """
    Run AnimRigHeadless on this entire scene, creating an _Anim.mb file for each _Anim animation set.
    Will create a temporary copy of this scene, and then spin up an external maya to output each _Anim file

    Args:
        target_anim_sets: specified animation sets
        pre_export_script_path: script to run before the scenes are geneated - sent from the batch job
        extension: file extension
    """

    # get our mayapy for headless maya
    py_exe = pathlib.Path(sys.executable)
    py_exe = pathlib.Path(f'{py_exe.parent}/mayapy.exe')

    assert py_exe.exists(), f'mayapy.exe cannot be found {py_exe}'

    # get our animation set data for processing
    file_path = pm.sceneName()  # type: pathlib.Path
    anim_set_data = {
        anim_set: {
            'target_path': AnimRigFunctions.get_target_path_from_set(anim_set, extension)
        }
        for anim_set in cmds.ls('*_Anim', type='objectSet', r=True)
    }

    # user-defined specific items only? cleanup
    if target_anim_sets:
        anim_set_data = {
            i: j for i, j in anim_set_data.items()
            if i in target_anim_sets
        }

    checkout_target_files_from_p4v(anim_set_data)

    print('Saving this scene.')
    try:
        cmds.file(save=True, force=True, prompt=False)
    except Exception as e:
        pass

    # clone this scene to a temp file
    temp_file = pathlib.Path(f'C:/Temp/Maya/CreateAnimRig_Temp_{file_path.name}')
    if not temp_file.parent.exists():
        os.makedirs(temp_file.parent)
    if temp_file.exists():
        os.remove(str(temp_file))

    print(f'Cloning to temporary path:\n\t{temp_file}')
    shutil.copyfile(
        str(file_path),
        str(temp_file)
    )

    headless_script = f'{os.path.dirname(__file__)}/AnimRigRunHeadless.py'

    # Collect our processes
    processes = []
    for anim_set, data in anim_set_data.items():

        target_path = data.get('target_path')

        print(f'Creating {anim_set} to {target_path}')

        command = f'"{py_exe}" {headless_script} {temp_file} {anim_set} {target_path} {pre_export_script_path}'
        proc = subprocess.Popen(
            command,
            stderr=subprocess.PIPE,
            stdout=subprocess.PIPE,
            shell=False,
            universal_newlines=True
        )
        processes.append((proc, target_path))

    success = []
    errors = []

    def run_create_anim_threaded(_p, _t) -> None:
        """ Thread holding command for the subprocess communicate """
        out, err = _p.communicate()
        if _p.returncode != 0:
            errors.append((err, _t))
        else:
            success.append(('Success', _t))

    # Spin up our threads
    threads = []
    for i in processes:
        proc, target_path = i
        t = threading.Thread(target=run_create_anim_threaded, args=[proc, target_path])
        t.start()
        threads.append(t)

    # Wait for them all to complete
    for t in threads:
        t.join()

    for i in success:
        print(f'CreateAnim: {i[1]}')
    for e in errors:
        e, target_path = e
        print(e)

    if errors:
        failed_paths = ', '.join([i[1].name for i in errors])
        raise AssertionError(f'Failed Files: {failed_paths}')

    # fin
