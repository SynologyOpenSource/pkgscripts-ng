#! /usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
from subprocess import check_call, STDOUT
from pkgcommon import PkgScripts, ScriptDir, logger
from pkgerror import BuildPackageError, InstallPacageError, LinkPackageError
from pkguniform import ProjectLinker, PackageBuilder, PackageInstaller, PackageCollecter
from parallel import doParallel
from link_project import link_projects, LinkProjectError
import BuildEnv


def get_customized_file(package, need_de_virtual_pkg=False):
    if need_de_virtual_pkg:
        pkg_name = BuildEnv.deVirtual(package)
    else:
        pkg_name = package
    customized = "source/{}/SynoBuildConf/customized".format(pkg_name)
    if '-virtual-' in package:
        customized = "{}-virtual-{}".format(customized,
                                            package.split('-virtual-')[1])
    return customized


def get_customize_cmd(script_dir, package, title):
    script = os.path.join(script_dir, 'SynoCustomize')
    need_de_virtual_pkg = False
    source_dirname = ""

    if script_dir == ScriptDir:
        source_dirname = os.path.dirname(ScriptDir)
        need_de_virtual_pkg = True

    customize_file = "{}/{}".format(source_dirname,
                                    get_customized_file(package, need_de_virtual_pkg))
    return ['env'] + [script, '-e', customize_file, title]

class PreBuilder(PackageBuilder):
    title = "PreBuilder"
    log = "logs.prebuild"
    __error_msg__ = "Failed to prebuild package."
    __failed_exception__ = BuildPackageError

    def _get_command(self, platform):
        return get_customize_cmd(PkgScripts, self.package.name, self.title)


class PostBuilder(PackageBuilder):
    title = "PostBuilder"
    log = "logs.postbuild"
    __error_msg__ = "Failed to postbuild package."
    __failed_exception__ = BuildPackageError

    def _get_command(self, platform):
        return get_customize_cmd(PkgScripts, self.package.name, self.title)


class PreInstaller(PackageInstaller):
    title = "PreInstaller"
    log = "logs.preinstall"
    __error_msg__ = "Failed to preinstall package."
    __failed_exception__ = InstallPacageError

    def _get_command(self, platform):
        return get_customize_cmd(PkgScripts, self.package.name, self.title)


class PostInstaller(PackageInstaller):
    title = "PostInstaller"
    log = "logs.postinstall"
    __error_msg__ = "Failed to postinstall package."
    __failed_exception__ = InstallPacageError

    def _get_command(self, platform):
        return get_customize_cmd(PkgScripts, self.package.name, self.title)


class PreCollecter(PackageCollecter):
    title = "PreCollecter"
    log = "logs.precollecter"

    def _run(self):
        cmd = ' '.join(get_customize_cmd(
            ScriptDir, self.package.name, self.title))
        logger.info(cmd)
        return check_call(cmd, shell=True, stderr=STDOUT, executable="/bin/bash")


class PostCollecter(PackageCollecter):
    title = "PostCollecter"
    log = "logs.postcollecter"

    def _run(self):
        cmd = ' '.join(get_customize_cmd(
            ScriptDir, self.package.name, self.title))
        logger.info(cmd)
        return check_call(cmd, shell=True, stderr=STDOUT, executable="/bin/bash")
