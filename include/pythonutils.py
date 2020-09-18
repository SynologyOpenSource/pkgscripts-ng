#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import sys
import os
import re
sys.path.append(os.path.join(os.path.dirname(__file__), 'python'))
import BuildEnv
from config_parser import DependsParser

def getBaseEnvironment(proj, env, ver=None):
    dict_env = {}
    if ver:
        dict_env['all'] = ver
        return dict_env

    if not env:
        env = 'default'

    depends = DependsParser(BuildEnv.Project(proj).depends_script)
    dict_env = depends.get_env_section(env)
    return dict_env
