#! /usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import sys
import os
from subprocess import check_call, check_output, CalledProcessError, STDOUT, Popen
import glob
import tempfile
import shutil
from time import localtime, strftime
from collections import defaultdict
import logging
import re
from version_file import VersionFile

from pkgcommon import Worker, CommandRunner, ChrootRunner, show_msg_block, BaseDir, ScriptName, PkgScripts, logger, check_stage
from pkgerror import PkgCreateError, CollectPackageError, LinkPackageError, BuildPackageError, InstallPacageError, TraverseProjectError
from parallel import doPlatformParallel, doParallel
from link_project import link_projects, link_scripts, LinkProjectError
from include.pythonutils import getBaseEnvironment
import BuildEnv
from project_visitor import ProjectVisitor, ConflictError
from exec_env import ChrootEnv, EnvError
import config_parser

ScriptDir = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))

TimeLogger = []
UpdateSource = []


class StreamToLogging(object):
    def __init__(self, logger, level=logging.INFO):
        self.logger = logger
        self.level = level

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.level, line.rstrip())

    def flush(self):
        pass


sys.stdout = StreamToLogging(logging)
sys.error = StreamToLogging(logging, logging.ERROR)


class WorkerFactory:
    def __init__(self, args):
        self.package = Package(args.package)
        self.env_config = EnvConfig(args.package, args.env_section, args.env_version, args.platforms, args.dep_level,
                                    args.branch, args.suffix, None)
        self.package.chroot = self.env_config.get_chroot()

    def new(self, worker_class, *args, **kwargs):
        return worker_class(self.package, self.env_config, *args, **kwargs)


class EnvPrepareWorker(Worker):
    def __init__(self, package, env_config, update, _):
        Worker.__init__(self, package, env_config)
        self.update = update
        self.sub_workers = []

    def _run(self, *argv):
        depends_cache = None
        updater = None
        for version, platforms in self.env_config.toolkit_versions.items():
            logger.info("Processing [%s]: " % version + " ".join(platforms))
            dsm_ver, build_num = version.split('-')

            for worker in self.sub_workers:
                worker.execute(version, updater, depends_cache)

    def add_subworker(self, sub_worker, force_register=False):
        if force_register or check_stage(self.package.name, sub_worker.__class__.__name__):
            self.sub_workers.append(sub_worker)

    def get_time_cost(self):
        time_cost = []
        if self.sub_workers:
            for sub_worker in self.sub_workers:
                time_cost += sub_worker.get_time_cost()

        return time_cost


class ProjectTraverser(Worker):
    title = "Traverse project"

    def _run(self, version, updater, cache):
        try:
            visitor = ProjectVisitor(updater,
                                     self.env_config.dep_level,
                                     self.env_config.toolkit_versions[version],
                                     depends_cache=cache,
                                     version=version)
            dict_projects = visitor.traverse(self.package.name)
            visitor.show_proj_info()
        except ConflictError as e:
            raise TraverseProjectError(str(e))

        self.package.dict_projects = dict_projects


class ProjectLinker(Worker):
    title = "Link Project"

    def _run(self, version, *argv):
        tasks = []
        for platform in self.env_config.toolkit_versions[version]:
            chroot = self.env_config.get_chroot(platform)
            if not os.path.isdir(os.path.join(chroot, 'source')):
                os.makedirs(os.path.join(chroot, 'source'))
            link_scripts(chroot)
            tasks.append((self.package.get_build_projects(platform) |
                          self.package.ref_projs | set(UpdateSource), chroot))

        try:
            doParallel(link_projects, tasks)
            for platform in self.env_config.toolkit_versions[version]:
                env = self.env_config.get_env(platform)
        except LinkProjectError as e:
            raise LinkPackageError(str(e))


class PackageCollecter(Worker):
    title = "Collect package"

    def _move_to_dest(self, source, source_list, dest_dir):
        logger.info("%s -> %s" % (source_list[0], dest_dir))
        try:
            shutil.copy(source_list[0], dest_dir)
        except Exception:
            raise CollectPackageError("Collect package failed")

        if len(source_list) > 1:
            raise CollectPackageError(
                "Found duplicate %s" % (source), source_list)

    def _run(self):
        spks = defaultdict(list)

        dest_dir = self.package.spk_config.spk_result_dir(
            self.env_config.suffix)
        if os.path.exists(dest_dir):
            old_dir = dest_dir + '.bad.' + strftime('%Y%m%d-%H%M', localtime())
            if os.path.isdir(old_dir):
                shutil.rmtree(old_dir)
            os.rename(dest_dir, old_dir)
        os.makedirs(dest_dir)

        for platform in self.env_config.platforms:
            for spk in self.package.spk_config.chroot_spks(self.env_config.get_chroot(platform)):
                spks[os.path.basename(spk)].append(spk)

        for spk, source_list in spks.items():
            self._move_to_dest(spk, source_list, dest_dir)


class PackageBuilder(ChrootRunner):
    title = "Build Package"
    log = "logs.build"
    __error_msg__ = "Failed to build package."
    __failed_exception__ = BuildPackageError

    def __init__(self, package, env_config, _, sdk_ver, build_opt, *argv, **kwargs):
        ChrootRunner.__init__(self, package, env_config, *argv, **kwargs)
        self.build_opt = build_opt.split()
        self.sdk_ver = sdk_ver

    def _get_command(self, platform):
        build_script = os.path.join(PkgScripts, 'SynoBuild')
        projects = self.package.get_build_projects(platform)

        build_cmd = ['env'] + ['PackageName=' + self.package.name, build_script, '--' + platform,
                                               '-c', '--min-sdk', self.sdk_ver]
        if self.build_opt:
            build_cmd += self.build_opt

        return build_cmd + list(projects)


class PackageInstaller(ChrootRunner):
    title = "Install Package"
    log = "logs.install"
    __error_msg__ = "Failed to install package."
    __failed_exception__ = InstallPacageError

    def __init__(self, package, env_config, install_opt, print_log):
        ChrootRunner.__init__(self, package, env_config, print_log)
        debug_opt = '--with-debug'
        if debug_opt in install_opt:
            self.title += '[{}]'.format(debug_opt)
        self.install_opt = list(install_opt)

    def _get_command(self, platform):
        cmd = ['env'] + ['PackageName=' + self.package.name,
                                         os.path.join(PkgScripts, 'SynoInstall')]
        if self.install_opt:
            cmd += self.install_opt

        return cmd + [self.package.name]

class Package():
    def __init__(self, package):
        self.name = package
        self.package_proj = BuildEnv.Project(self.name)
        self.dict_projects = dict()
        self.__additional_build = defaultdict(list)
        self.__spk_config = None
        self.__chroot = None

    def get_additional_build_projs(self, platform):
        if platform in self.__additional_build:
            return set(self.__additional_build[platform])
        return set()

    def add_additional_build_projs(self, platform, projs):
        self.__additional_build[platform] += projs

    @property
    def ref_projs(self):
        return self.dict_projects['refs'] | self.dict_projects['refTags']

    def get_build_projects(self, platform):
        return self.dict_projects['branches'] | self.get_additional_build_projs(platform)

    @property
    def spk_config(self):
        if not self.__spk_config:
            self.__spk_config = SpkConfig(self.name, self.info, self.settings)

        return self.__spk_config

    @property
    def info(self):
        return self.package_proj.info(self.chroot)

    @property
    def settings(self):
        return self.package_proj.settings(self.chroot)

    @property
    def chroot(self):
        return self.__chroot

    @chroot.setter
    def chroot(self, chroot):
        self.__chroot = chroot


class SpkConfig:
    def __init__(self, name, info, settings):
        self.info = config_parser.KeyValueParser(info)
        try:
            self.settings = config_parser.PackageSettingParser(
                settings).get_section(name)
        except config_parser.ConfigNotFoundError:
            self.settings = None

    @property
    def name(self):
        if self.settings and "pkg_name" in self.settings:
            return self.settings["pkg_name"][0]

        return self.info['package']

    @property
    def version(self):
        return self.info['version']

    def is_beta(self):
        return ('beta' in self.info.keys() and self.info['beta'] == "yes") or 'report_url' in self.info.keys()

    @property
    def build_num(self):
        try:
            return self.version.split("-")[-1]
        except IndexError:
            return self.version

    def get_pattern_file(self, pattern):
        return "{}*{}*{}".format(self.name, self.version, pattern)

    @property
    def spk_pattern(self):
        return self.get_pattern_file('spk')

    @property
    def tar_pattern(self):
        return self.get_pattern_file('tar')

    def chroot_packages_dir(self, chroot):
        return os.path.join(chroot, 'image', 'packages')

    def get_chroot_file(self, chroot, pattern):
        return glob.glob(os.path.join(self.chroot_packages_dir(chroot), pattern))

    def chroot_tars(self, chroot):
        return self.get_chroot_file(chroot, self.tar_pattern)

    def chroot_spks(self, chroot):
        return self.get_chroot_file(chroot, self.spk_pattern)

    def spk_result_dir(self, suffix=""):
        if suffix:
            suffix = '-' + suffix

        return os.path.join(BaseDir, 'result_spk' + suffix, self.name + '-' + self.version)


class EnvConfig():
    def __init__(self, package, env_section, version, platforms, dep_level, branch, suffix, _):
        self.dict_env = getBaseEnvironment(package, env_section, version)
        self.suffix = suffix
        self.env_section = env_section
        self.env_version = version
        self.dep_level = dep_level
        self.branch = branch

        self.platforms = set(self.__get_package_platforms(platforms))

        self.__envs = {}
        for platform in self.platforms:
            self.__envs[platform] = ChrootEnv(self.get_chroot(platform))

        self.toolkit_versions = self.__resolve_toolkit_versions()

    def get_env(self, platform):
        return self.__envs[platform]

    def __get_package_platforms(self, platforms):
        def __get_toolkit_available_platforms(version):
            toolkit_config = os.path.join(
                ScriptDir, 'include', 'toolkit.config')
            major, minor = version.split('.')
            pattern = '$AvailablePlatform_%s_%s' % (major, minor)
            return check_output('source %s && echo %s' % (toolkit_config, pattern),
                                shell=True, executable='/bin/bash').decode().split()

        package_platforms = set()
        for platform in self.dict_env:
            if platform == 'all':
                package_platforms |= set(
                    __get_toolkit_available_platforms(self.dict_env['all']))
            else:
                package_platforms.add(platform)

        if platforms:
            package_platforms = set(package_platforms) & set(platforms)

        found_env, not_found_env = [], []
        for platform in package_platforms:
            if os.path.isdir(self.get_chroot(platform)):
                found_env.append(platform)
            else:
                not_found_env.append(platform)

        msgs = []
        for env in not_found_env:
            msgs.append("Chroot `{}' not found.".format(
                os.path.basename(self.get_chroot(env))))

        if not found_env:
            raise PkgCreateError("All platform chroot not exists.", msgs)
        else:
            for msg in msgs:
                logger.warning('[WARNING] ' + msg)

        return found_env

    def __get_version(self, platform):
        if platform in self.dict_env:
            version = self.dict_env[platform]
        elif 'all' in self.dict_env:
            version = self.dict_env['all']
        else:
            raise PkgCreateError("Package version not found")

        return version

    def get_chroot(self, platform=None):
        if not platform:
            platform = list(self.platforms)[0]

        return BuildEnv.getChrootSynoBase(platform, self.__get_version(platform), self.suffix)

    def __resolve_toolkit_versions(self):
        def __get_toolkit_version(version_file):
            version = VersionFile(version_file)
            return "%s-%s" % (version.dsm_version, version.buildnumber)

        versions = defaultdict(list)
        for platform in self.platforms:
            toolkit_version = __get_toolkit_version(
                self.__get_version_file(platform))
            versions[toolkit_version].append(platform)

        if len(versions) > 1:
            msg = []
            for version, platforms in versions.items():
                msg.append("[%s]: %s" % (version, " ".join(platforms)))
            show_msg_block(
                msg, title="[WARNING] Multiple toolkit version found", level=logging.WARNING)

        return versions

    def __get_version_file(self, platform):
        return self.get_env(platform).get_file('PkgVersion')

    def get_chroot_synodebug(self, platform):
        return self.get_env(platform).get_file(os.path.join('image', 'synodebug'))

    @property
    def prebuild_projects(self):
        return BuildEnv.getList('PreBuildProjects') or []


class PackagePacker:
    def __init__(self, pkg_name):
        self.__workers = []
        self.pkg_name = pkg_name

    @property
    def workers(self):
        return self.__workers

    def register_worker(self, worker, force_register=False):
        if force_register or check_stage(self.pkg_name, worker.__class__.__name__):
            self.__workers.append(worker)

    def pack_package(self):
        for worker in self.__workers:
            worker.execute()

    def show_time_cost(self):
        time_cost = []
        for worker in self.__workers:
            time_cost += worker.get_time_cost()

        show_msg_block(time_cost, title="Time Cost Statistic")
