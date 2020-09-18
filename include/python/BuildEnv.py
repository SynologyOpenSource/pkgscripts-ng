#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import glob
import subprocess
import tempfile
import shutil
import re
from subprocess import CalledProcessError

ScriptDir = os.path.realpath(os.path.dirname(__file__) + '/../../')
ScriptDirName = os.path.basename(ScriptDir)
SynoBase = os.path.dirname(ScriptDir)
SourceDir = SynoBase + "/source"

__IsPkgEnv = True

VIRTUAL_PROJECT_SEPARATOR = "-virtual-"
VIRINST_PROJECT_SEPARATOR = "-virinst-"
ConfDir = 'SynoBuildConf'
ProjectDependsName = "ProjectDepends.py"

__PkgEnvVersion = None

Prefix = SynoBase


def setEnvironmentVersion(version):
    global __PkgEnvVersion
    __PkgEnvVersion = version


def inChroot():
    return os.path.isfile('/root/.chroot')


class Project:
    def __init__(self, proj, allow_missing=False):
        self.proj = proj
        self.allow_missing = allow_missing

        if inChroot():
            project_src = deVirInst(self.proj)
        else:
            project_src = deVirtual(deVirInst(self.proj))

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


class Chroot():
    __platform = None
    __version = None

    def __init__(self, platform, version=None):
        self.__platform = platform
        self.__version = version

    def MountProc(self):
        return MountProc(self.__platform, self.__version)

    def SynoBuild(self, args, **kwargs):
        return executeChrootScript(self.__platform, "SynoBuild", ["--" + self.__platform] + args, self.__version, **kwargs)

    def SynoInstall(self, args, **kwargs):
        return executeChrootScript(self.__platform, "SynoInstall", ["--" + self.__platform] + args, self.__version, **kwargs)

    def GetSynoBase(self):
        return getChrootSynoBase(self.__platform, self.__version)

    def GetSourceDir(self):
        return getChrootSourceDir(self.__platform, self.__version)

    def GetScriptDir(self):
        return self.GetSynoBase() + "/" + ScriptDirName

    def ExecuteCommand(self, cmd):
        return executeChrootCommand(self.__platform, cmd, self.__version)

    def ExecuteScript(self, script, args, **kwargs):
        return executeChrootScript(self.__platform, script, args, self.__version, **kwargs)

    def LinkProject(self, proj):
        return LinkProject(proj, self.__platform, self.__version)

    def LinkScript(self):
        return LinkScript(self.__platform, self.__version)


class PlatformNotFoundException(RuntimeError):
    pass


class BuildFailedError(RuntimeError):
    pass


def getIncludeVariable(include_file, variable):
    return subprocess.check_output(
        'source %s/include/init; source %s/include/%s; echo $%s' % (ScriptDir, ScriptDir, include_file, variable),
        shell=True,
        executable='/bin/bash'
    ).decode().strip()


def getChrootSynoBase(platform, version=None, suffix=None):
    if __IsPkgEnv:
        env = 'build_env'
        if suffix:
            env += "-" + suffix
        if version is None:
            version = __PkgEnvVersion
        return os.path.join(SynoBase, env, 'ds.'+platform+'-'+version)
    return Prefix + '/ds.' + platform


def getChrootSourceDir(platform, version=None):
    return getChrootSynoBase(platform, version) + "/source"


def executeChrootScript(platform, script, args, version=None, **kwargs):
    envOpt = []
    if 'env' in kwargs:
        envOpt = ['env']
        for k in kwargs['env']:
            envOpt.append("%s=%s" % (k, kwargs['env'][k]))

    return subprocess.check_call(
        ["chroot", getChrootSynoBase(platform, version)] + envOpt + ["/" + ScriptDirName + "/" + script] + args)


def executeChrootCommand(platform, cmd, version=None):
    return subprocess.check_output(
        ["chroot", getChrootSynoBase(platform, version)] + cmd).decode()


def executeScript(script, args, **kwargs):
    if "suppressOutput" in kwargs and kwargs["suppressOutput"]:
        kwargs.pop("suppressOutput")
        with open(os.devnull, "w") as null:
            return subprocess.check_call([ScriptDir + "/" + script] + args, stdout=null, stderr=null, **kwargs)
    else:
        return subprocess.check_call([ScriptDir + "/" + script] + args, **kwargs)


def ProjectDepends(args):
    return subprocess.check_output([ScriptDir + "/" + ProjectDependsName] + args).decode().rstrip().split()



def SynoBuild(platform, args, version=None):
    try:
        return executeChrootScript(platform, "SynoBuild", args, version)
    except CalledProcessError:
        raise BuildFailedError("Failed to SynoBuild(%s) on platform %s" % (str(args), platform))


def getList(listName):
    ret = []
    for config in ["projects", "config"]:
        if os.path.exists(os.path.join(ScriptDir, 'include', config)):
            ret = getIncludeVariable(config, listName).split()

            if ret:
                return ret

    return None

def getPlatformVariable(platform, var):
    return getIncludeVariable('platform.' + platform, var)


def isVirtualProject(proj):
    return VIRTUAL_PROJECT_SEPARATOR in proj


def isVirInstProject(proj):
    return VIRINST_PROJECT_SEPARATOR in proj


def deVirtual(proj):
    return proj.split(VIRTUAL_PROJECT_SEPARATOR)[0]


def deVirInst(proj):
    return proj.split(VIRINST_PROJECT_SEPARATOR)[0]


def getBasedProject(proj):
    return deVirtual(deVirInst(proj))


def getVirtualName(proj):
    if isVirtualProject(proj):
        return proj.split(VIRTUAL_PROJECT_SEPARATOR)[1]
    else:
        return ""


def getVirInstName(proj):
    if isVirInstProject(proj):
        return proj.split(VIRINST_PROJECT_SEPARATOR)[1]
    else:
        return ""


def getVirtualProjectExtension(proj):
    if isVirtualProject(proj):
        return VIRTUAL_PROJECT_SEPARATOR + getVirtualName(proj)
    if isVirInstProject(proj):
        return VIRINST_PROJECT_SEPARATOR + getVirInstName(proj)

    return ""


def EnvDeploy(args, **kwargs):
    try:
        return executeScript("EnvDeploy", args, **kwargs)
    except CalledProcessError:
        raise RuntimeError("Failed to EnvDeploy(%s) on " % str(args))


def PkgCreate(args, **kwargs):
    try:
        return executeScript("PkgCreate.py", args, **kwargs)
    except CalledProcessError:
        raise BuildFailedError("Failed to PkgCreate(%s) on " % str(args))

def __linkFolder(src, tgt):
    if os.path.exists(tgt):
        shutil.rmtree(tgt)

    print("Link " + src + " -> " + tgt)
    return subprocess.check_call(["cp", "-al", src, tgt])


def LinkProject(proj, platform, version=None):
    return __linkFolder(SourceDir + "/" + deVirtual(proj), getChrootSourceDir(platform, version) + "/" + proj)


def LinkScript(platform, version=None):
    return __linkFolder(ScriptDir, getChrootSynoBase(platform, version) + "/" + ScriptDirName)


def MountProc(platform, version=None):
        mountpoint = getChrootSynoBase(platform, version) + "/proc"
        if not os.path.ismount(mountpoint):
            subprocess.check_call("mount -t proc none " + getChrootSynoBase(platform, version) + "/proc",
                                  shell=True)

def get_namespace():
    return os.path.basename(Prefix)
