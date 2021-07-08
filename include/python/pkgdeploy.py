#! /usr/bin/env python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import subprocess
import logging
import urllib.request
import sys
import shutil
import json
import hashlib
from glob import glob
from cache import cache
import BuildEnv
from toolkit import TarballManager
from exec_env import ChrootEnv, EnvError
from parallel import doPlatformParallel, doParallel
from utils import move_old
from version_file import VersionFile
VersionMap = 'version_map'
DownloadDir = os.path.join(BuildEnv.SynoBase, 'toolkit_tarballs')
ToolkitServer = 'https://dataupdate7.synology.com/toolchain/v1/get_download_list?identify=toolkit'


class EnvDeployError(RuntimeError):
    pass


class TarballNotFoundError(EnvDeployError):
    pass


class PlatformNotAvailableError(EnvDeployError):
    pass


class DownloadToolkitError(EnvDeployError):
    pass


class EnvHookError(EnvDeployError):
    pass


def set_log(log_name):
    log = os.path.join(BuildEnv.SynoBase, 'envdeploy.log')
    move_old(log)
    logfmt = '[%(asctime)s] %(levelname)s: %(message)s'
    logging.basicConfig(
        level=logging.DEBUG,
        format=logfmt,
        filename=log
    )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    formatter = logging.Formatter(logfmt)
    console.setFormatter(formatter)
    logging.getLogger().addHandler(console)


def link_project(projects, platforms, version):
    if type(projects) is str:
        projects = [projects]

    for proj in projects:
        for platform in platforms:
            BuildEnv.LinkProject(proj, platform, version)


@cache
def split_version(version):
    if '-' in version:
        return version.split('-')
    else:
        return version, None


class ToolkitDownloader:
    def __init__(self, version, tarball_manager):
        self.dsm_ver, self.build_num = split_version(version)
        self.tarball_manager = tarball_manager

        if not os.path.isdir(DownloadDir):
            os.makedirs(DownloadDir)

    def download_base_tarball(self, quiet):
        self._download(
            self._join_download_url('base'),
            quiet
        )

    def download_platform_tarball(self, platform, quiet):
        self._download(self._join_download_url(platform), quiet)

    def _join_download_url(self, platform):
        return '%s&version=%s&platform=%s' % (ToolkitServer, self.dsm_ver, platform)

    def _download(self, url, quiet):
        logging.info("Download... %s" % (url))
        if quiet or not sys.stdout.isatty():
            reporthook = None
        else:
            reporthook = self.dl_progress

        with urllib.request.urlopen(url) as response:
            data = json.loads(response.read())
            for link in data["fileList"]:
                try:
                    urllib.request.urlretrieve(link, os.path.join(
                        DownloadDir, link.split("/")[-1]), reporthook=reporthook)
                except urllib.error.HTTPError as e:
                    raise DownloadToolkitError("Failed to download toolkit: %s , reason: %s" % (link, str(e)))

    def dl_progress(self, count, dl_size, total_size):
        percent = int(count * dl_size * 50 / total_size)
        sys.stdout.write("[%-50s] %d%%" %
                         ('=' * (percent - 1) + ">", 2 * percent))
        sys.stdout.write("\b" * 102)
        sys.stdout.flush()


class ToolkitEnv(object):
    def __init__(self, version, platforms, suffix=""):
        self.version = version
        self.platforms = platforms
        self.dsm_ver, self.build_num = split_version(version)
        self.suffix = suffix

    def download(self, quiet=False):
        raise NotImplementedError("download() not implemented")

    def deploy(self):
        raise NotImplementedError("deploy() not implemented")

    def clean(self):
        raise NotImplementedError("clean() not implemented")

    def get_chroot(self, platform):
        return BuildEnv.getChrootSynoBase(platform, self.dsm_ver, self.suffix)

    def __remove_chroot(self, chroot):
        for f in os.listdir(chroot):
            if 'ccaches' in f:
                continue
            file_path = os.path.join(chroot, f)
            subprocess.check_call(['rm', '-rf', file_path])

    def __umount_proc(self, chroot):
        proc = os.path.join(chroot, 'proc')
        if os.path.ismount(proc):
            subprocess.check_call(['umount', proc])

    # clear and mkdir chroot
    def clear_chroot(self, platform):
        chroot = self.get_chroot(platform)
        if not os.path.isdir(chroot):
            return

        logging.info("Clear %s..." % chroot)
        self.__umount_proc(chroot)
        self.__remove_chroot(chroot)

    def link_pkgscripts(self, env):
        if not env.islink('pkgscripts'):
            env.link('pkgscripts-ng', 'pkgscripts')

    def get_sysroot_include(self, platform):
        all_sysroot = list()
        for arch in [32, 64]:
            variable = "ToolChainInclude" + str(arch)
            sysroot = BuildEnv.getPlatformVariable(platform, variable)
            if sysroot:
                all_sysroot.append(sysroot)
        return all_sysroot

    def get_env_build_num(self, platform):
        raise NotImplementedError("get_env_build_num() not implemented")

    def create_chroot(self, platform):
        os.makedirs(self.get_chroot(platform), exist_ok=True)


class ChrootToolkit(ToolkitEnv):
    def __init__(self, version, platforms, suffix="", tarball_root=DownloadDir):
        super().__init__(version, platforms, suffix)
        self.tarball_manager = TarballManager(self.dsm_ver, tarball_root)
        self.__downloader = ToolkitDownloader(
            self.version, self.tarball_manager)

    def download(self, quiet):
        self.__downloader.download_base_tarball(quiet)
        for platform in self.platforms:
            self.__downloader.download_platform_tarball(platform, quiet)

    def deploy(self):
        envs = {}
        self.__check_tarball_exists()
        for platform in self.platforms:
            self.create_chroot(platform)
            self.deploy_base_env(platform)
            self.deploy_env(platform)
            self.deploy_dev(platform)
            self.adjust_chroot(platform)

            envs[platform] = ChrootEnv(self.get_chroot(platform))
            self.link_pkgscripts(envs[platform])
        return envs

    def clean(self):
        doPlatformParallel(self.clear_chroot, self.platforms)

    def __check_tarball_exists(self):
        files = [self.tarball_manager.base_tarball_path]
        for platform in self.platforms:
            files.append(self.tarball_manager.get_dev_tarball_path(platform))
            files.append(self.tarball_manager.get_env_tarball_path(platform))

        for f in files:
            if not os.path.isfile(f):
                raise TarballNotFoundError("Needed file not found! %s" % (f))

    @property
    def has_pixz(self):
        try:
            with open(os.devnull, 'wb') as null:
                subprocess.check_call(
                    ['which', 'pixz'], stdout=null, stderr=null)
        except subprocess.CalledProcessError:
            return False
        return True

    def __extract__(self, tarball, dest_dir):
        cmd = ['tar']
        if self.has_pixz:
            cmd.append('-Ipixz')
        cmd += ['-xhf', tarball, '-C', dest_dir]
        logging.info(" ".join(cmd))
        subprocess.check_call(cmd)

    def deploy_base_env(self, platform):
        self.__extract__(
            self.tarball_manager.base_tarball_path,
            self.get_chroot(platform)
        )

    def deploy_env(self, platform):
        self.__extract__(
            self.tarball_manager.get_env_tarball_path(platform),
            self.get_chroot(platform)
        )

    def deploy_dev(self, platform):
        self.__extract__(
            self.tarball_manager.get_dev_tarball_path(platform),
            self.get_chroot(platform)
        )

    def mkdir_source(self, chroot):
        source_dir = os.path.join(chroot, 'source')
        if not os.path.isdir(source_dir):
            os.makedirs(source_dir)

    def copy_user_env_config(self, chroot):
        configs = ['/etc/hosts', '/root/.gitconfig',
                   '/root/.ssh', '/etc/resolv.conf']

        for config in configs:
            dest = chroot + config
            if os.path.isdir(config):
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                shutil.copytree(config, dest)
            elif os.path.isfile(config):
                shutil.copy(config, dest)

    def adjust_chroot(self, platform):
        chroot = self.get_chroot(platform)
        self.mkdir_source(chroot)
        self.copy_user_env_config(chroot)

    def get_env_build_num(self, platform):
        version = VersionFile(os.path.join(
            self.get_chroot(platform), 'PkgVersion'))
        return version.buildnumber

def get_all_platforms(dsm_ver, build_num):
    pattern = 'AvailablePlatform_%s_%s' % (
        dsm_ver.split('.')[0], dsm_ver.split('.')[1])

    if build_num:
        for line in config:
            if pattern in line:
                platforms = line.split('=')[1].strip('"').split()
    else:
        platforms = BuildEnv.getIncludeVariable(
            'toolkit.config', pattern).split()

    return platforms


def filter_platforms(version, platforms):
    dsm_ver, build_num = split_version(version)
    all_platforms = get_all_platforms(dsm_ver, build_num)

    if not platforms:
        return all_platforms

    redundant_platforms = set(platforms) - set(all_platforms)
    if redundant_platforms:
        raise PlatformNotAvailableError(
            "[%s] is not available platform." % " ".join(redundant_platforms))

    return platforms
