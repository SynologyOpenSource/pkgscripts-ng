# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os


class Tee:
    def __init__(self, stream, log_file, buffer=1, move=True):
        if move:
            self.move_log_old(log_file)
        self.stream = stream
        self.log = open(log_file, 'a', buffer)

    def write(self, msg):
        self.stream.write(msg)
        self.stream.flush()
        self.log.write(msg)

    def flush(self):
        self.stream.flush()
        self.log.flush()

    def __del__(self):
        self.log.close()

    def move_log_old(self, log):
        if os.path.isfile(log):
            old = log + ".old"
            if os.path.isfile(old):
                os.remove(old)
            os.rename(log, old)
