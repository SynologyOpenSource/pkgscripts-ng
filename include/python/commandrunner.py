# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import subprocess


class RunShellFailed(Exception):
    def __init__(self, retcode, command, output=""):
        self.retcode = retcode
        self.command = command
        self.output = output
        super().__init__()


def run(cmd, display=False, **kwargs):
    try:
        p = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **kwargs
        )
        output = b""
        if display:
            for line in p.stdout:
                print(line.decode().rstrip())
                output += line
            p.wait()
        else:
            output, _ = p.communicate()
    except KeyboardInterrupt:
        p.kill()
        p.wait()
        raise

    output = output.decode().rstrip()
    if p.returncode != 0:
        if output and not display:
            print(output)
        raise RunShellFailed(p.returncode, cmd, output)

    return output
