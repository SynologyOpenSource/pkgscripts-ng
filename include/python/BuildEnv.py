#!/usr/bin/python3

import os
import subprocess

ScriptDir = os.path.realpath(os.path.dirname(__file__) + '/../../')
SynoBase = os.path.dirname(ScriptDir)
Prefix = os.path.dirname(SynoBase)
SourceDir = SynoBase + "/source"

if 'lnxscripts' in os.path.basename(ScriptDir):
    __IsPkgEnv = False
else:
    __IsPkgEnv = True

VIRTUAL_PROJECT_SEPARATOR = "-virtual-"
ConfDir = 'SynoBuildConf'
ProjectDependsName = "ProjectDepends.py"
__PkgEnvVersion = None


def setEnvironmentVersion(version):
    global __PkgEnvVersion
    __PkgEnvVersion = version


def inChroot():
    return os.path.isfile('/root/.chroot')


class Project:
    def __init__(self, proj, allow_missing=False):
        self.proj = proj
        self.allow_missing = allow_missing

        if not inChroot():
            project_src = deVirtual(self.proj)

        self.__project_dir = os.path.join(SourceDir, project_src)

    @property
    def build_script(self):
        return self.__find_script('build')

    @property
    def install_script(self):
        return self.__find_script('install')

    @property
    def installdev_script(self):
        return self.__find_script('install-dev')

    @property
    def error_script(self):
        return self.__find_script('error')

    @property
    def depends_script(self):
        return self.__find_script('depends')

    def settings(self, chroot=None):
        return self.__find_script('settings', chroot)

    def collect(self, chroot=None):
        return self.__find_script('collect', chroot)

    def selfcheck(self, chroot=None):
        return self.__find_script('selfcheck', chroot)

    def info(self, chroot=None):
        return os.path.join(self.project_dir(chroot), 'INFO')

    def project_dir(self, chroot=None):
        project_dir = self.__project_dir
        if chroot:
            project_dir = os.path.join(chroot, os.path.basename(SourceDir), self.proj)
        return project_dir

    def __find_script(self, script_type, chroot=None):
        for proj_name in [self.proj, self.proj.split("-32")[0], self.proj.split("-virtual-32")[0]]:
            virtual_name = getVirtualProjectExtension(proj_name)

            script = os.path.join(self.project_dir(chroot), ConfDir, script_type + virtual_name)
            if os.path.isfile(script) or os.path.islink(script):
                return script

        if self.allow_missing:
            return os.path.join(self.project_dir(chroot), ConfDir, script_type)
        else:
            return ""


class DpkgNotFoundError(RuntimeError):
    def __init__(self, deb_name):
        print("Deb %s not found" % deb_name)


def getIncludeVariable(include_file, variable):
    return subprocess.check_output('source %s/include/%s; echo $%s' % (ScriptDir, include_file, variable),
                                   shell=True, executable='/bin/bash').decode().strip()


def getChrootSynoBase(platform, version=None, suffix=None):
    if __IsPkgEnv:
        env = 'build_env'
        if suffix:
            env += "-" + suffix
        if version is None:
            version = __PkgEnvVersion
        return os.path.join(SynoBase, env, 'ds.'+platform+'-'+version)
    return Prefix + '/ds.' + platform


def getList(listName):
    ret = []
    for config in ["projects", "config"]:
        if os.path.exists(os.path.join(ScriptDir, 'include', config)):
            ret = getIncludeVariable(config, listName).split()

            if ret:
                return ret

    return None


def isVirtualProject(proj):
    return VIRTUAL_PROJECT_SEPARATOR in proj


def deVirtual(proj):
    return proj.split(VIRTUAL_PROJECT_SEPARATOR)[0]


def getVirtualName(proj):
    if isVirtualProject(proj):
        return proj.split(VIRTUAL_PROJECT_SEPARATOR)[1]
    else:
        return ""


def getVirtualProjectExtension(proj):
    if isVirtualProject(proj):
        return VIRTUAL_PROJECT_SEPARATOR + getVirtualName(proj)

    return ""


def IsPackageEnvironment():
    return __IsPkgEnv
