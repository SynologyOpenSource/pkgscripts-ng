#!/usr/bin/python3
# Copyright (c) 2000-2014 Synology Inc. All rights reserved.

import sys
import os
from subprocess import check_call, check_output, CalledProcessError, STDOUT, Popen
import argparse
import glob
import shutil
from time import localtime, strftime, gmtime, time
from collections import defaultdict

# Paths
ScriptDir = os.path.dirname(os.path.abspath(__file__))
BaseDir = os.path.dirname(ScriptDir)
ScriptName = os.path.basename(__file__)
PkgScripts = '/pkgscripts-ng'

sys.path.append(ScriptDir+'/include')
sys.path.append(ScriptDir+'/include/python')
import BuildEnv
from chroot import Chroot
from parallel import doPlatformParallel, doParallel
from link_project import link_projects, link_scripts, LinkProjectError
from tee import Tee
import config_parser
from project_visitor import UpdateHook, ProjectVisitor, UpdateFailedError, ConflictError
from version_file import VersionFile

log_file = os.path.join(BaseDir, 'pkgcreate.log')
sys.stdout = Tee(sys.stdout, log_file)
sys.stderr = Tee(sys.stderr, log_file, move=False)

MinSDKVersion = "6.0"
BasicProjects = set()


class PkgCreateError(RuntimeError):
    pass


class SignPackageError(PkgCreateError):
    pass


class CollectPackageError(PkgCreateError):
    pass


class LinkPackageError(PkgCreateError):
    pass


class BuildPackageError(PkgCreateError):
    pass


class InstallPacageError(PkgCreateError):
    pass


class TraverseProjectError(PkgCreateError):
    pass


def show_msg_block(msg, title=None, error=False):
    if not msg:
        return

    if error:
        tok_s = "#"
        tok_e = "#"
    else:
        tok_s = "="
        tok_e = "-"

    if title:
        print("\n" + tok_s * 60)
        print("{:^60s}".format(title))
        print(tok_e * 60)
    print("\n".join(msg))
    print()


def args_parser(argv):
    argparser = argparse.ArgumentParser()
    argparser.add_argument('-p', dest='platforms',
                           help='Specify target platforms. Default to detect available platforms under build_env/')
    argparser.add_argument('-e', '--env', dest='env_section', default='default',
                           help='Specify environment section in SynoBuildConf/depends. Default is [default].')
    argparser.add_argument('-v', '--version', dest='env_version', help='Specify target DSM version manually.')
    argparser.add_argument('-x', dest='dep_level', type=int, default=1, help='Build dependant level')
    argparser.add_argument('-b', dest='branch', default='master', help='Specify branch of package.')
    argparser.add_argument('-s', dest='suffix', default="",
                           help='Specify suffix of folder of build environment (build_env/).')
    argparser.add_argument('-c', dest='collect', action='store_true', help='collect package.')
    argparser.add_argument('-U', dest='update', action='store_false', help='Not update projects.')
    argparser.add_argument('-L', dest='link', action='store_false', help='Not link projects.')
    argparser.add_argument('-B', dest='build', action='store_false', help='Not build projects.')
    argparser.add_argument('-I', dest='install', action='store_false', help='Not install projects.')
    argparser.add_argument('-i', dest='only_install', action='store_true', help='Only install projects.')
    argparser.add_argument('-S', dest="sign", action='store_false', help='Do not make code sign.')
    argparser.add_argument('--build-opt', default="", help='Argument pass to SynoBuild')
    argparser.add_argument('--install-opt', default="", help='Argument pass to SynoInstall')
    argparser.add_argument('--print-log', action='store_true', help='Print SynoBuild/SynoInstall error log.')
    argparser.add_argument('--min-sdk', dest='sdk_ver', default=MinSDKVersion, help='Min sdk version, default=6.0')
    argparser.add_argument('package', help='Target packages')

    args = argparser.parse_args(argv)
    if not args.build:
        args.link = False

    if args.only_install:
        args.update = args.link = args.build = False

    if args.platforms:
        args.platforms = args.platforms.split()

    msg = []
    for key, value in vars(args).items():
        if isinstance(value, list):
            value = " ".join(value)
        else:
            value = str(value)
            msg.append("{:13s}".format(key) + ": " + value)

    show_msg_block(msg, "Parse argument result")

    return args


class WorkerFactory:
    def __init__(self, args):
        self.package = Package(args.package)
        self.env_config = EnvConfig(args.package, args.env_section, args.env_version, args.platforms, args.dep_level,
                                    args.branch, args.suffix)
        self.package.chroot = self.env_config.get_chroot()

    def new(self, worker_class, *args, **kwargs):
        return worker_class(self.package, self.env_config, *args, **kwargs)


class Worker:
    def __init__(self, package, env_config):
        self.package = package
        self.env_config = env_config
        self.__time_log = None

    def execute(self, *argv):
        if not self._check_executable():
            return

        init_time = time()
        if hasattr(self, 'title'):
            print("\n" + "=" * 60)
            print("{:^60s}".format('Start to run "%s"' % self.title))
            print("-" * 60)
        self._process_output(self._run(*argv))
        self.__time_log = strftime('%H:%M:%S', gmtime(time()-init_time))

    def _run(self):
        pass

    def _check_executable(self):
        return True

    def _process_output(self, output):
        pass

    def get_time_cost(self):
        time_cost = []
        if hasattr(self, 'title') and self.__time_log:
            time_cost.append("%s: %s" % (self.__time_log, self.title))

        return time_cost


class EnvPrepareWorker(Worker):
    def __init__(self, package, env_config, update):
        Worker.__init__(self, package, env_config)
        self.update = update
        self.sub_workers = []

    def _run(self, *argv):
        depends_cache = None
        update_hook = None
        for version, platforms in self.env_config.toolkit_versions.items():
            print("Processing [%s]: " % version + " ".join(platforms))
            dsm_ver, build_num = version.split('-')

            if self.update:
                update_hook = UpdateHook(self.env_config.branch, build_num)

            for worker in self.sub_workers:
                worker.execute(version, update_hook, depends_cache)

    def add_subworker(self, sub_worker):
        self.sub_workers.append(sub_worker)

    def get_time_cost(self):
        time_cost = []
        if self.sub_workers:
            for sub_worker in self.sub_workers:
                time_cost += sub_worker.get_time_cost()

        return time_cost


class ProjectTraverser(Worker):
    title = "Traverse project"

    def _run(self, version, update_hook, cache):
        dep_level = self.env_config.dep_level
        platforms = self.env_config.toolkit_versions[version]

        try:
            visitor = ProjectVisitor(update_hook, dep_level, platforms, depends_cache=cache)
            dict_projects = visitor.traverse(self.package.name)
            visitor.checkout_git_refs()
            visitor.show_proj_info()
        except UpdateFailedError as e:
            log = os.path.join(BaseDir, 'logs', 'error.update')
            with open(log, 'r') as fd:
                print(fd.read())
            raise TraverseProjectError("Error log: " + log)
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
            tasks.append((set(BasicProjects) |
                          self.package.get_build_projects(platform) |
                          self.package.ref_projs, chroot))

        try:
            doParallel(link_projects, tasks)
        except LinkProjectError as e:
            raise LinkPackageError(str(e))


class CodeSignWorker(Worker):
    title = "Generate code sign"

    def _run(self):
        return doPlatformParallel(self._code_sign, self.env_config.platforms)

    def check_gpg_key_exist(self):
        try:
            gpg = check_output(['gpg', '--list-keys']).decode().strip()
        except CalledProcessError:
            return False

        return gpg

    def _code_sign(self, platform):
        spks = self.package.spk_config.chroot_spks(self.env_config.get_chroot(platform))
        if not spks:
            raise SignPackageError('[%s] No spk found' % platform)

        for spk in spks:
            cmd = ' php ' + PkgScripts + '/CodeSign.php --sign=/image/packages/' + os.path.basename(spk)
            with Chroot(self.env_config.get_chroot(platform)):
                if not self.check_gpg_key_exist():
                    raise SignPackageError("[%s] Gpg key not exist. You can add `-S' to skip package code sign or import gpg key first." % platform)

                print("[%s] Sign package: " % platform + cmd)
                try:
                    check_call(cmd, shell=True, executable="/bin/bash")
                except CalledProcessError:
                    raise SignPackageError('Failed to create signature: ' + spk)


class PackageCollecter(Worker):
    title = "Collect package"

    def _run(self):
        spks = defaultdict(list)

        dest_dir = self.package.spk_config.spk_result_dir(self.env_config.suffix)
        if os.path.exists(dest_dir):
            old_dir = dest_dir + '.bad.' + strftime('%Y%m%d-%H%M', localtime())
            if os.path.isdir(old_dir):
                shutil.rmtree(old_dir)
            os.rename(dest_dir, old_dir)
        os.makedirs(dest_dir)

        for platform in self.env_config.platforms:
            for spk in self.package.spk_config.chroot_spks(self.env_config.get_chroot(platform)):
                spks[os.path.basename(spk)].append(spk)

            hook = self.package.collect
            if os.path.isfile(hook):
                print("Run hook " + hook)
                hook_env = {
                    'SPK_SRC_DIR': self.package.spk_config.chroot_packages_dir(self.env_config.get_chroot(platform)),
                    'SPK_DST_DIR': dest_dir,
                    'SPK_VERSION': self.package.spk_config.version,
                    'SPK_NAME': self.package.spk_config.name
                }
                pipe = Popen(hook, shell=True, stdout=None, stderr=None, env=hook_env)
                pipe.communicate()
                if pipe.returncode != 0:
                    raise CollectPackageError("Execute package collect script failed.")

        for spk, source_list in spks.items():
            print("%s -> %s" % (source_list[0], dest_dir))
            try:
                shutil.copy(source_list[0], dest_dir)
            except:
                raise CollectPackageError("Collect package failed")

            if len(source_list) > 1:
                raise CollectPackageError("Found duplicate %s: \n%s" % (spk, "\n".join(source_list)))


class CommandRunner(Worker):
    __log__ = None
    __error_msg__ = None
    __failed_exception__ = None

    def _rename_log(self, suffix='.old'):
        if os.path.isfile(self.log):
            os.rename(self.log, self.log + suffix)

    def _run(self, *argv):
        self._rename_log()
        cmd = self._wrap_cmd(self._get_command(*argv))

        try:
            print(" ".join(cmd))
            output = check_output(" ".join(cmd), stderr=STDOUT, shell=True, executable="/bin/bash").decode()
            self._post_hook()
        except CalledProcessError as e:
            output = e.output.decode()
            print(output)
            raise self.__failed_exception__(self.__error_msg__)

        return output

    def _get_command(self):
        raise PkgCreateError("Not implement")

    def _post_hook(self):
        pass

    def _process_output(self, output):
        pass

    def _wrap_cmd(self, cmd):
        return ["set -o pipefail;"] + cmd + ["2>&1", '|', 'tee', self.log]

    @property
    def log(self):
        return os.path.join(BaseDir, self.__log__)


# Run SynoBuild/SynoInstall in chroot
class ChrootRunner(CommandRunner):
    def __init__(self, package, env_config, print_log=False):
        CommandRunner.__init__(self, package, env_config)
        self.print_log = print_log
        self.__log__ = None

    def _process_output(self, output):
        msg = []
        log_file = []

        for platform, failed_projs in output.items():
            if not failed_projs:
                continue

            if self.print_log:
                self._dump_log(platform)

            msg.append(self.__error_msg__ + ' [%s] : %s' % (platform, " ".join(failed_projs)))
            log_file.append("Error log: " + self.get_platform_log(platform))

        if msg:
            show_msg_block(msg + log_file, title=self.__error_msg__, error=True)
            raise self.__failed_exception__(self.__error_msg__)

    def _dump_log(self, platform):
        log = self.get_platform_log(platform)
        with open(log, 'r') as fd:
            show_msg_block(fd.read().split("\n"), title=log, error=True)

    def get_platform_log(self, platform):
        return os.path.join(self.env_config.get_chroot(platform), self.log)

    def run_command(self, platform, *argv):
        cmd = self._wrap_cmd(self._get_command(platform, *argv))

        with Chroot(self.env_config.get_chroot(platform)):
            self._rename_log()
            try:
                print("[%s] " % platform + " ".join(cmd))
                with open(os.devnull, 'wb') as null:
                    check_call(" ".join(cmd), stdout=null, shell=True, executable='/bin/bash')
            except CalledProcessError:
                failed_projs = self.__get_failed_projects()
                if not failed_projs:
                    raise self.__failed_exception__("%s failed. \n Error log: %s"
                                                    % (" ".join(cmd), self.get_platform_log(platform)))
                return failed_projs

    def __get_failed_projects(self):
        projects = []
        with open(self.log, 'r') as fd:
            for line in fd:
                if 'Error(s) occurred on project' not in line:
                    continue
                projects.append(line.split('"')[1])

        return projects

    def _run(self):
        return doPlatformParallel(self.run_command, self.env_config.platforms)

    @property
    def log(self):
        raise PkgCreateError("Not implemented")


class PackageBuilder(ChrootRunner):
    title = "Build Package"
    log = "logs.build"
    __error_msg__ = "Failed to build package."
    __failed_exception__ = BuildPackageError

    def __init__(self, package, env_config, sdk_ver, build_opt, *argv, **kwargs):
        ChrootRunner.__init__(self, package, env_config, *argv, **kwargs)
        self.build_opt = build_opt
        self.sdk_ver = sdk_ver

    def _get_command(self, platform):
        build_script = os.path.join(PkgScripts, 'SynoBuild')
        projects = self.package.get_build_projects(platform)

        build_cmd = ['env', 'PackageName=' + self.package.name, build_script, '--' + platform,
                     '-c', '--min-sdk', self.sdk_ver]
        if self.build_opt:
            build_cmd.append(self.build_opt)

        return build_cmd + list(projects)


class PackageInstaller(ChrootRunner):
    title = "Install Package"
    log = "logs.install"
    __error_msg__ = "Failed to install package."
    __failed_exception__ = InstallPacageError

    def __init__(self, package, env_config, install_opt, print_log):
        ChrootRunner.__init__(self, package, env_config, print_log)
        self.install_opt = list(install_opt)

    def _get_command(self, platform):
        cmd = ['env', 'PackageName=' + self.package.name, os.path.join(PkgScripts, 'SynoInstall')]
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
    def collect(self):
        return self.package_proj.collect(self.chroot)

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
            self.settings = config_parser.PackageSettingParser(settings).get_section(name)
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

    @property
    def build_num(self):
        try:
            return self.version.split("-")[-1]
        except IndexError:
            return self.version

    @property
    def spk_pattern(self):
        return self.name + '*' + self.version + '*spk'

    def chroot_packages_dir(self, chroot):
        return os.path.join(chroot, 'image', 'packages')

    def chroot_spks(self, chroot):
        return glob.glob(os.path.join(self.chroot_packages_dir(chroot), self.spk_pattern))

    def spk_result_dir(self, suffix=""):
        if suffix:
            suffix = '-' + suffix

        return os.path.join(BaseDir, 'result_spk' + suffix, self.name + '-' + self.version)


class EnvConfig():
    def __init__(self, package, env_section, version, platforms, dep_level, branch, suffix):
        self.dict_env = getBaseEnvironment(package, env_section, version)
        self.suffix = suffix
        self.env_section = env_section
        self.env_version = version
        self.dep_level = dep_level
        self.branch = branch
        self.platforms = set(self.__get_package_platforms(platforms))
        self.toolkit_versions = self.__resolve_toolkit_versions()

        if not self.platforms:
            raise PkgCreateError("No platform found!")

    def __get_package_platforms(self, platforms):
        def __get_toolkit_available_platforms(version):
            toolkit_config = os.path.join(ScriptDir, 'include', 'toolkit.config')
            major, minor = version.split('.')
            pattern = '$AvailablePlatform_%s_%s' % (major, minor)
            return check_output('source %s && echo %s' % (toolkit_config, pattern),
                                shell=True, executable='/bin/bash').decode().split()

        package_platforms = set()
        for platform in self.dict_env:
            if platform == 'all':
                package_platforms |= set(__get_toolkit_available_platforms(self.dict_env['all']))
            else:
                package_platforms.add(platform)

        if platforms:
            package_platforms = set(package_platforms) & set(platforms)

        # remove platform if dir not exist
        return [platform for platform in package_platforms if os.path.isdir(self.get_chroot(platform))]

    def __get_version(self, platform):
        if platform in self.dict_env:
            version = self.dict_env[platform]
        elif 'all' in self.dict_env:
            version = self.dict_env['all']
        else:
            raise PkgCreateError("Package version not found")

        return version

    def get_version_map_file(self, platform):
        return os.path.join(self.get_chroot(platform), 'version_map')

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
            toolkit_version = __get_toolkit_version(self.__get_version_file(platform))
            versions[toolkit_version].append(platform)

        if len(versions) > 1:
            msg = []
            for version, platforms in versions.items():
                msg.append("[%s]: %s" % (version, " ".join(platforms)))
            show_msg_block(msg, title="[WARNING] Multiple toolkit version found", error=True)

        return versions

    def __get_version_file(self, platform):
        return os.path.join(self.get_chroot(platform), 'PkgVersion')

    def get_chroot_synodebug(self, platform):
        return os.path.join(self.get_chroot(platform), 'image', 'synodebug')

    @property
    def prebuild_projects(self):
        return BuildEnv.getList('PreBuildProjects') or []


class PackagePacker:
    def __init__(self):
        self.__workers = []

    def add_worker(self, worker):
        self.__workers.append(worker)

    def pack_package(self):
        for worker in self.__workers:
            worker.execute()

    def show_time_cost(self):
        time_cost = []
        for worker in self.__workers:
            time_cost += worker.get_time_cost()

        show_msg_block(time_cost, title="Time Cost Statistic")


def getBaseEnvironment(proj, env, ver=None):
    dict_env = {}
    if ver:
        dict_env['all'] = ver
        return dict_env

    if not env:
        env = 'default'

    depends = config_parser.DependsParser(BuildEnv.Project(proj).depends_script)
    dict_env = depends.get_env_section(env)
    return dict_env


def main(argv):
    args = args_parser(argv)
    packer = PackagePacker()
    worker_factory = WorkerFactory(args)
    new_worker = worker_factory.new

    prepare_worker = new_worker(EnvPrepareWorker, args.update)
    prepare_worker.add_subworker(new_worker(ProjectTraverser))
    if args.link:
        prepare_worker.add_subworker(new_worker(ProjectLinker))
    packer.add_worker(prepare_worker)

    if args.build:
        packer.add_worker(new_worker(PackageBuilder, args.sdk_ver, args.build_opt, args.print_log))

    if args.install:
        packer.add_worker(new_worker(PackageInstaller,
                                     install_opt=[args.install_opt, '--with-debug'],
                                     print_log=args.print_log))
        packer.add_worker(new_worker(PackageInstaller,
                                     install_opt=[args.install_opt],
                                     print_log=args.print_log))

    if args.collect:
        if args.sign:
            packer.add_worker(new_worker(CodeSignWorker))

        packer.add_worker(new_worker(PackageCollecter))

    packer.pack_package()
    packer.show_time_cost()

if __name__ == '__main__':
    ret = 0
    try:
        main(sys.argv[1:])
        print("[SUCCESS] " + " ".join(sys.argv) + " finished.")
    except PkgCreateError as e:
        ret = 1
        print("\n\033[91m%s:\033[0m" % type(e).__name__)
        print(str(e))
        print("\n[ERROR] " + " ".join(sys.argv) + " failed!")

    sys.exit(ret)
