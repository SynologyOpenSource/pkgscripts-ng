#!/usr/bin/env python
# -*- coding: utf-8 -*-
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import shutil
import time


def move_old(file):
    if os.path.isfile(file):
        old = file + ".old"
        if os.path.isfile(old):
            os.remove(old)
        os.rename(file, old)
