import os
import sys

sys.path.append(os.path.dirname(__file__))

import config_parser


class VersionFile(config_parser.KeyValueParser):
    @property
    def dsm_version(self):
        return self['majorversion'] + "." + self['minorversion']

    @property
    def buildnumber(self):
        return self['buildnumber']
