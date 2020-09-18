#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import sys
import os
import argparse
import traceback
import multiprocessing
import logging

ScriptDir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(ScriptDir + '/include')
sys.path.append(ScriptDir + '/include/python')

from pkgcommon import check_stage, show_msg_block, BaseDir, logger
from pkgerror import PkgCreateError
from pkgcustomize import PreBuilder, PostBuilder, PreInstaller, PostInstaller, PreCollecter, PostCollecter
from pkguniform import StreamToLogging, PackagePacker, WorkerFactory, EnvPrepareWorker, ProjectTraverser, ProjectLinker, PackageBuilder, PackageInstaller, PackageCollecter

import BuildEnv
import parallel
from utils import move_old
import config_parser

EnvVersion = BaseDir + '/EnvVersion'
MinSDKVersion = "6.2"

sys.stdout = StreamToLogging(logging)
sys.error = StreamToLogging(logging, logging.ERROR)


def args_parser(argv):
    global sys
    argparser = argparse.ArgumentParser()
    argparser.add_argument('-p', dest='platforms',
                           help='Specify target platforms. Default to detect available platforms under build_env/')
    argparser.add_argument('-e', '--env', dest='env_section', default='default',
                           help='Specify environment section in SynoBuildConf/depends. Default is [default].')
    argparser.add_argument('-v', '--version', dest='env_version',
                           help='Specify target DSM version manually.')
    argparser.add_argument('-x', dest='dep_level', type=int,
                           default=1, help='Build dependant level')
    argparser.add_argument('-X', dest='parallel_proj', type=int, default=1,
                           help='SynoBuild parallel build projects, 0 means build with {} parallel jobs'.format(multiprocessing.cpu_count()))
    argparser.add_argument('-b', dest='branch',
                           default='master', help='Specify branch of package.')
    argparser.add_argument('-s', dest='suffix', default="",
                           help='Specify suffix of folder of build environment (build_env/).')
    argparser.add_argument('-c', dest='collect',
                           action='store_true', help='collect package.')
    argparser.add_argument('--no-collecter', dest='collecter',
                           action='store_false', help='skip doing all collecting behaviors.')
    argparser.add_argument(
        '-L', dest='link', action='store_false', help='Not link projects.')
    argparser.add_argument('-l', dest='update_link',
                           action='store_true', help='Update and link projects.')
    argparser.add_argument(
        '-B', dest='build', action='store_false', help='Not build projects.')
    argparser.add_argument('-I', dest='install',
                           action='store_false', help='Not install projects.')
    argparser.add_argument('-i', dest='only_install',
                           action='store_true', help='Only install projects.')
    argparser.add_argument('-P', dest='parallel', type=int, default=multiprocessing.cpu_count(),
                           help='Parallel platforms, default is {}'.format(multiprocessing.cpu_count()))
    argparser.add_argument('--build-opt', default="",
                           help='Argument pass to SynoBuild')
    argparser.add_argument('--install-opt', default="",
                           help='Argument pass to SynoInstall')
    argparser.add_argument('--print-log', action='store_true',
                           help='Print SynoBuild/SynoInstall error log.')
    argparser.add_argument(
        '--no-tee', dest='tee', action='store_false', help='Not tee stdout/stderr to log.')
    argparser.add_argument('--min-sdk', dest='sdk_ver',
                           default=MinSDKVersion, help='Min sdk version, default={}'.format(MinSDKVersion))
    argparser.add_argument('package', help='Target packages')

    args = argparser.parse_args(argv)

    if args.tee:
        logfile = os.path.join(BuildEnv.SynoBase, 'pkgcreate.log')
        move_old(logfile)
        fh = logging.FileHandler(logfile)
        fh.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s: %(message)s')
        fh.setFormatter(formatter)
        logging.getLogger().addHandler(fh)

    if not args.build:
        args.link = False

    if args.only_install:
        args.link = args.build = False

    if args.update_link:
        args.build = args.install = args.collect = False
        args.link = True

    if args.platforms:
        args.platforms = args.platforms.split()

    parallel.PROCESSES = args.parallel

    if args.parallel_proj == 0:
        args.parallel_proj = multiprocessing.cpu_count()

    if args.parallel_proj > 1:
        parallel_opt = '--parallel'

        if parallel_opt in args.build_opt:
            logger.warning(
                "[WARNING] Skipped -P option in SynoBuild, there is --parallel in --build-opt")
        else:
            args.build_opt += '{} {} {}'.format(
                args.build_opt, parallel_opt, args.parallel_proj)

        if parallel_opt in args.install_opt:
            logger.warning(
                "[WARNING] Skipped -P option in SynoInstall, there is --parallel in --install-opt")
        else:
            args.install_opt += '{} {} {}'.format(
                args.install_opt, parallel_opt, args.parallel_proj)

    msg = []
    for key, value in vars(args).items():
        if isinstance(value, list):
            value = " ".join(value)
        else:
            value = str(value)
        msg.append("{:13s} : {}".format(key, value))
    show_msg_block(msg, "Parse argument result")

    return args


def main(argv):
    args = args_parser(argv)

    packer = PackagePacker(args.package)
    worker_factory = WorkerFactory(args)
    new_worker = worker_factory.new

    prepare_worker = new_worker(EnvPrepareWorker, None, None)
    prepare_worker.add_subworker(new_worker(ProjectTraverser))
    if args.link:
        prepare_worker.add_subworker(new_worker(ProjectLinker))

    packer.register_worker(prepare_worker)

    if args.build:
        packer.register_worker(new_worker(
            PreBuilder, None, args.sdk_ver, args.build_opt, args.print_log))
        packer.register_worker(new_worker(
            PackageBuilder, None, args.sdk_ver, args.build_opt, args.print_log))
        packer.register_worker(new_worker(
            PostBuilder, None, args.sdk_ver, args.build_opt, args.print_log))

    if args.install:
        packer.register_worker(new_worker(
            PreInstaller, args.install_opt, args.print_log))
        packer.register_worker(new_worker(PackageInstaller,
                                          install_opt=[
                                              args.install_opt, '--with-debug'],
                                          print_log=args.print_log))
        packer.register_worker(new_worker(PackageInstaller,
                                          install_opt=[args.install_opt],
                                          print_log=args.print_log))
        packer.register_worker(new_worker(
            PostInstaller, args.install_opt, args.print_log))

    if args.collect:
        if args.collecter:
            packer.register_worker(new_worker(PreCollecter))
            packer.register_worker(new_worker(PackageCollecter))
            packer.register_worker(new_worker(PostCollecter))

    packer.pack_package()
    packer.show_time_cost()


if __name__ == '__main__':
    ret = 0
    try:
        main(sys.argv[1:])
        logger.info("[SUCCESS] " + " ".join(sys.argv) + " finished.")
    except PkgCreateError as e:
        ret = 1
        logger.debug("".join(traceback.format_tb(sys.exc_info()[2])))
        logger.error(" ".join(sys.argv) + " failed!")
        raise e

    sys.exit(ret)
