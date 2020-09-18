# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os


class TarballManager:
    def __init__(self, version, root):
        self.version = version
        self.root = root

    @property
    def base_tarball_name(self):
        return 'base_env-%s.txz' % self.version

    @property
    def base_tarball_path(self):
        return os.path.join(self.root, self.base_tarball_name)

    def get_env_tarball_name(self, platform):
        return 'ds.%s-%s.env.txz' % (platform, self.version)

    def get_env_tarball_path(self, platform):
        return os.path.join(self.root, self.get_env_tarball_name(platform))

    def get_dev_tarball_name(self, platform):
        return 'ds.%s-%s.dev.txz' % (platform, self.version)

    def get_dev_tarball_path(self, platform):
        return os.path.join(self.root, self.get_dev_tarball_name(platform))
