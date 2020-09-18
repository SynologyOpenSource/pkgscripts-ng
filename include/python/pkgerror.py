#! /usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import logging


class PkgCreateError(RuntimeError):
    def __init__(self, title, msg=[]):
        logging.error('[ERROR] ' + title)
        if isinstance(msg, list):
            for line in msg:
                logging.error(line)
        else:
            logging.error(msg)



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
