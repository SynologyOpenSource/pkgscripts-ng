#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

class cache(dict):
    def __init__(self, func):
        self.func = func

    def __call__(self, *args):
        return self[args]

    def __missing__(self, key):
        result = self[key] = self.func(*key)
        return result
