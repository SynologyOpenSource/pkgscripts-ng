# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import subprocess
import sys
import shutil
sys.path.append(os.path.dirname(__file__))
import BuildEnv


class LinkProjectError(RuntimeError):
    pass


def get_project_source(project):
    if BuildEnv.VIRTUAL_PROJECT_SEPARATOR in project:
        project = project.split(BuildEnv.VIRTUAL_PROJECT_SEPARATOR)[0]
    return os.path.join(BuildEnv.SourceDir, project)


def link(source, dest, verbase=False):
    if not os.path.exists(source):
        raise LinkProjectError("%s not exist." % source)

    print("Link %s -> %s" % (source, dest))
    subprocess.check_call(['cp', '-al', source, dest])


def link_scripts(chroot):
    dest_path = os.path.join(chroot, os.path.basename(BuildEnv.ScriptDir))
    if os.path.isdir(dest_path):
        shutil.rmtree(dest_path)
    link(BuildEnv.ScriptDir, dest_path)


def link_projects(projects, dest):
    for proj in projects:
        dest_path = os.path.join(dest, 'source', proj)
        if os.path.isdir(dest_path):
            shutil.rmtree(dest_path)
        link(get_project_source(proj), os.path.join(dest, 'source', proj))


def link_platform(project, platform, version=None):
    source = get_project_source(project)
    chroot = BuildEnv.getChrootSynoBase(platform, version)
    dest = os.path.join(chroot, "source", project)

    if os.path.isdir(dest):
        shutil.rmtree(dest)

    link(source, dest)


