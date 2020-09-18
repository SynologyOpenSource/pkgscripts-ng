#!/usr/bin/env python
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import sys
import os
import re
import json
import subprocess

sys.path.append(os.path.dirname(os.path.abspath(sys.argv[0])) + '/python')
import BuildEnv

LOG_DIR = '/logs'

# "error_pattern": skip_list
BUILD_ERROR_CHECKLIST = {
    "line.*syntax error": [],
    "Error": ['ignored', 'Error\.[c|o|h|cc|lo|Plo|js]', 'GPG Error', 'distclean'],
    "fatal error": [],
    "missing separator": [],
    "No rule to make target": ["clean", "distclean"],
    "don't know": [],
    "error:": [],
    "was not found in the pkg-config search path": [],
    "ld: cannot find": [],
}

INSTALL_ERROR_CHECKLIST = {
    "No such file or directory": []
}


def is_skipped_error(error, skip_list):
    if not skip_list:
        return False

    for skip in skip_list:
        if skip and re.search(skip, error):
            return True

    return False


def find_errors(check_list, log):
    result = []

    for error in check_list:
        regex = re.compile(error)
        found_error = False

        index = 0
        for line in log:
            index += 1
            line = line.strip()

            if regex.search(line) and not is_skipped_error(line, check_list[error]):
                if not found_error:
                    result.append('======  Find pattern [%s] ======' % error)
                    found_error = True
                result.append('%s: %s' % (str(index), line))

    return result


def load_project_setting(proj, check_list):
    error_script = BuildEnv.Project(proj).error_script
    if not error_script or not os.path.isfile(error_script):
        return

    with open(error_script, 'r') as error_skip_file:
        try:
            error_skip_list = json.load(error_skip_file)
        except ValueError:
            raise RuntimeError("Can't parse error file %s." % error_script)

    for error in error_skip_list:
        if error not in check_list:
            check_list[error] = error_skip_list[error]
            continue

        skips = error_skip_list[error]
        if isinstance(skips, basestring):
            check_list[error].append(skips)
        elif isinstance(skips, list):
            check_list[error].extend(skips)
        else:
            raise RuntimeError("Wrong value type: %s." % skips)


def find_project_log(proj, log_type):
    return os.path.join(LOG_DIR, proj + '.' + log_type)


def main():
    proj = sys.argv[2]
    log_type = sys.argv[1]
    errors = None

    check_list = BUILD_ERROR_CHECKLIST
    if log_type == 'install':
        check_list.update(INSTALL_ERROR_CHECKLIST)

    load_project_setting(proj, check_list)

    # If log file doesn't write back to disk, there will raise IOError because of log file not found.
    # Do `sync` and reopen file again to prevent log file not found.
    try:
        log = open(find_project_log(proj, log_type), 'r')
    except IOError:
        subprocess.check_call(['sync'])
        log = open(find_project_log(proj, log_type), 'r')

    errors = find_errors(check_list, log.readlines())
    log.close()

    if errors:
        print("\n".join(errors))
        sys.exit(2)

    sys.exit(0)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: ./error.py log_type project")
        sys.exit(1)

    main()
