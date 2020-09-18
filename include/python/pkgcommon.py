#! /usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import sys
from time import strftime, gmtime, time
from subprocess import check_output, check_call, CalledProcessError, STDOUT
import logging
from include.python.exec_env import EnvError
from pkgerror import PkgCreateError
import BuildEnv

ScriptDir = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
BaseDir = os.path.dirname(ScriptDir)
ScriptName = os.path.basename(__file__)
PkgScripts = '/pkgscripts-ng'
sys.path.append(ScriptDir + '/include')

from parallel import doPlatformParallel
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
sh = logging.StreamHandler()
sh.setLevel(logging.INFO)
sh.setFormatter(logging.Formatter('%(message)s'))
logger.addHandler(sh)


def check_stage(package, stage):
    pkg_name = BuildEnv.deVirtual(package)
    customized = 'source/{}/SynoBuildConf/customized'.format(pkg_name)
    if '-virtual-' in package:
        customized = '{}-virtual-{}'.format(customized,
                                            package.split('-virtual-')[1])
    try:
        script = os.path.join(ScriptDir, 'SynoCustomize')
        # find SynoBuildConf
        customize_file = '{}/{}'.format(os.path.dirname(ScriptDir), customized)
        cmd = '{} -c {} {} 2>&1'.format(script, customize_file, stage)
        check_call(cmd, shell=True, stderr=STDOUT, executable="/bin/bash")
    except CalledProcessError:
        return False

    return True


def show_msg_block(msg, title=None, level=logging.INFO):
    if not msg:
        return

    if level > logging.INFO:
        tok_s = "#"
        tok_e = "#"
    else:
        tok_s = "="
        tok_e = "-"

    if title:
        logging.log(level, tok_s * 60)
        logging.log(level, "{:^60s}".format(title))
        logging.log(level, tok_e * 60)

    if isinstance(msg, list):
        for line in msg:
            logging.log(level, line)
    else:
        logging.log(level, msg)
    logging.log(level, "")


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
            logger.info("=" * 60)
            logger.info("{:^60s}".format('Start to run "%s"' % self.title))
            logger.info("-" * 60)
        self._process_output(self._run(*argv))
        logger.info("")
        self.__time_log = strftime('%H:%M:%S', gmtime(time() - init_time))

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
            logger.info(" ".join(cmd))
            output = check_output(
                " ".join(cmd), stderr=STDOUT, shell=True, executable="/bin/bash").decode()
            self._post_hook()
        except CalledProcessError as e:
            output = e.output.decode()
            logger.error(output)
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
            if self.print_log:
                self._dump_log(platform)

            if not failed_projs:
                continue

            msg.append(self.__error_msg__ +
                       ' [%s] : %s' % (platform, " ".join(failed_projs)))
            log_file.append("Error log: " + self.get_platform_log(platform))

        if msg:
            show_msg_block(
                msg + log_file, title=self.__error_msg__, level=logging.ERROR)
            raise self.__failed_exception__(self.__error_msg__)

    def _dump_log(self, platform):
        log = self.get_platform_log(platform)
        with open(log, 'r') as fd:
            show_msg_block(fd.read().split("\n"),
                           title=log, level=logging.ERROR)

    def get_platform_log(self, platform):
        return os.path.join(self.env_config.get_chroot(platform), self.log)

    def run_command(self, platform, *argv):
        cmd = self._get_command(platform, *argv)

        try:
            logger.info("[%s] " % platform + " ".join(cmd))
            env = self.env_config.get_env(platform)
            env.execute(cmd, display=len(self.env_config.platforms)
                        == 1, logfile=self.log)
        except EnvError:
            log = self.get_platform_log(platform)
            failed_projs = self.__parse_failed_projects(log)
            if not failed_projs:
                raise self.__failed_exception__(
                    "%s failed." % (" ".join(cmd)), log)
            return failed_projs

    def __parse_failed_projects(self, log):
        projects = []
        with open(log, 'r') as fd:
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
