#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import subprocess
import tempfile

import commandrunner


class EnvError(RuntimeError):
    def __init__(self, title, stderr="", retcode=1):
        self.output = stderr
        self.retcode = retcode
        super().__init__(title, stderr)


class ExecuteEnv(object):
    def __init__(self, chroot_dir):
        self.chroot_dir = chroot_dir

    @property
    def platform(self):
        return os.path.basename(self.chroot_dir.split('-')[0].split("ds.")[1])

    def execute(self, cmd, display=False, logfile="", **kwargs):
        raise NotImplementedError("execute not implemented")

    def __enter__(self):
        raise NotImplementedError("__enter__ not implemented")

    def __exit__(self, *args):
        raise NotImplementedError("__exit__ not implemented")

    def get_file(self, filepath):
        raise NotImplementedError("get_file not implemented")

    def get_path(self, path):
        return os.path.join(self.chroot_dir, path.lstrip("/"))

    def remove(self, f):
        self.execute(['rm', '-rf', f], display=False)

    def rename(self, old, new):
        self.execute(['mv', old, new], display=False)

    def file_exists(self, f):
        raise NotImplementedError("file_exists not implemented")

    def isfile(self, f):
        raise NotImplementedError("isfile not implemented")

    def mkdtemp(self, dir="/tmp"):
        raise NotImplementedError("mkdtemp not implemented")

    def makedirs(self, dir):
        raise NotImplementedError("makedirs not implemented")

    def link(self, src, dest):
        self.execute(['ln', '-sf', src, dest])


class ChrootEnv(ExecuteEnv):
    def execute(self, cmd, display=False, logfile="", **kwargs):
        mount_point = os.path.join(self.chroot_dir, 'proc')
        if not os.path.ismount(mount_point):
            subprocess.check_call(['mount', '-t', 'proc', 'none', mount_point])

        if isinstance(cmd, list):
            cmd = ['chroot', self.chroot_dir] + cmd
        else:
            cmd = 'chroot {} '.format(self.chroot_dir) + cmd

        try:
            output = commandrunner.run(cmd, display=display, **kwargs)
        except commandrunner.RunShellFailed as e:
            output = e.output
            raise EnvError(
                "Execute {} failed".format(cmd if isinstance(cmd, str) else " ".join(cmd)),
                stderr=output,
                retcode=e.retcode
            )
        finally:
            if logfile:
                with open(self.get_path(logfile), 'w') as fd:
                    fd.write(output)
        return output

    def get_file(self, filepath):
        ret = self.get_path(filepath)
        if not os.path.exists(ret):
            raise EnvError("{} not exists".format(ret))
        return ret

    def file_exists(self, f):
        return os.path.exists(self.get_path(f))

    def isfile(self, f):
        return os.path.isfile(self.get_path(f))

    def mkdtemp(self, dir="/tmp"):
        return tempfile.mkdtemp(dir=self.get_path(dir))

    def makedirs(self, dir):
        os.makedirs(self.get_path(dir))

    def islink(self, f):
        return os.path.islink(self.get_path(f))
