# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import sys

sys.path.append(os.path.dirname(__file__))

import config_parser


class VersionFile(config_parser.KeyValueParser):
    @property
    def dsm_version(self):
        return self.major + "." + self.minor

    @property
    def buildnumber(self):
        return self['buildnumber']

    @property
    def major(self):
        return self['majorversion']

    @property
    def minor(self):
        return self['minorversion']
