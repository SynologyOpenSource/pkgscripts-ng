#!/usr/bin/python2
# Copyright (c) 2000-2016 Synology Inc. All rights reserved.


import sys, os, string, re
from collections import defaultdict
from subprocess import check_call, CalledProcessError, Popen, PIPE
from time import time, ctime


# Error codes
ERROR_NONE = 0
ERROR_DEBUG = 1
ERROR_LOG = 2
ERROR_ARG = 3
ERROR_IO = 4
ERROR_DEP = 5
ERROR_OTHER = 6

VAR_KERNEL_PROJ = '${Kernel}'  # Variable name for kernel project
ENABLE_DEBUG = False  # Debug flag
VIRTUAL_PROJ_SEP = '-virtual-'

# Section names in dependency config files
SECTION_VAR = 'variables'
SECTION_DEP = 'project dependency'
SECTION_DEP64 = '64bit project dependency'
SECTION_KERNEL = VAR_KERNEL_PROJ
SECTION_KERNEL_OLD = 'platform kernel'
BASE_SECTIONS = [SECTION_VAR, SECTION_DEP, SECTION_KERNEL]
SECTION_BUILD = 'BuildDependent'
SECTION_REF = 'ReferenceOnly'
SECTION_PACK = 'PackagePacking'
SECTION_BUG = SECTION_BUILD+'-Bug'
SECTION_DEFAULT = 'default'
CONF_SECTIONS = [SECTION_BUILD, SECTION_BUILD+'-Tag', SECTION_REF, SECTION_REF+'-Tag', SECTION_PACK, SECTION_PACK+'-Tag', SECTION_BUG]

# Keys in INFO to be considered
INFO_KEYS = ['package', 'version', 'arch']

# Basic projects to be checkout
BasicProjects = set(['uistring', 'synopkgutils'])


def reportMessage(code, message):
    if code == ERROR_NONE:
        print >> sys.stderr, 'Warning: '+message+'!\n'
    elif code == ERROR_DEBUG:
        if ENABLE_DEBUG: print >> sys.stdout, '\033[34mDebug: '+message+'\033[0m'
    elif code == ERROR_LOG:
        print >> sys.stdout, 'Log: '+message
    else:
        print >> sys.stderr, '\033[31mError: '+message+'!\033[0m\n'
    if code > ERROR_LOG: sys.exit(code)


def getNextLine(file_handle):
    while (True):
        line = file_handle.readline()
        if line == '': break  # EOF
        line = line.strip()
        if line != '' and line[0] != '#': break  # Get non-empty, non-comment line
    return re.sub(r'\s*#.*', '', line)  # Remove comment and return

def parseSectionName(line):
    name = ''
    if re.match(r'\[.*\]', line): name = line[1:len(line)-1]
    return name

def parseKeyValue(line):
    key = ''
    values = []
    if re.match(r'.*\s*=\s*\"', line):
        key = line.split('=')[0].strip()
        values = line.split('"')[1].strip().split(' ')
    return key, values

def parseSectionNames(filename, arch):  # For platform-specific dependency
    sections = []
    for name in CONF_SECTIONS:
        pipe = Popen('grep "^\['+name+':.*'+arch+'.*\]" '+filename, stdout=PIPE, stderr=PIPE, shell=True)
        line = pipe.communicate()[0].strip()
        if pipe.returncode != 0:
            sections.append(name)
            continue
        line = line.split(']')[0]
        if arch in line[string.index(line, ':')+1:].split(','):
            sections.append(line[1:])
        else:
            sections.append(name)
    return sections


def resolveKeyNames(section):
    # format: [project_type-tag_type(64)?:platform]
    project_mapping = {
        SECTION_BUILD: 'build',
        SECTION_REF: 'ref',
        SECTION_PACK: 'pack',
    }
    tag_mapping = {
        'Tag': 'base',
        'Bug': 'bug',
        '': 'curr',
    }

    #                   project_t    tag_type  64     platform
    matches = re.match(r'([^-:]+)-?([^-:0-9]*)(64)?:?([^-:]*)', section)
    project_type, tag_type, is64, platform = matches.groups()

    if project_type in project_mapping:
        project_type = project_mapping[project_type]
    else:
        return '', None, None

    if is64:
        project_type = project_type + "64"

    tag_type = tag_mapping[tag_type]

    if not platform:
        platform = "all"

    return project_type, tag_type, platform


def readConfigFile(filePath):
    retDict = {}
    if not os.path.isfile(filePath):
        raise RuntimeError(filePath + " is not a file")

    with open(filePath, 'r') as conf:
        currSection = ''
        while (True):
            line = getNextLine(conf)
            if line == '':
                break  # EOF

            section_name = parseSectionName(line)
            if section_name:
                currSection = section_name
                retDict[currSection] = []
                continue

            if currSection:
                retDict[currSection].append(line)
    return retDict


def readKeyValueConfig(filename):
    configDict = readConfigFile(filename)
    retDict = {}
    for sec in configDict:
        retDict[sec] = {}
        for line in configDict[sec]:
            key, values = parseKeyValue(line)
            if not key or not values:
                continue
            retDict[sec][key] = values

    return retDict


def getKernelDict(allDict):
    if SECTION_KERNEL in allDict:
        return allDict[SECTION_KERNEL]

    return allDict[SECTION_KERNEL_OLD]


def readDependsBase(filename):
    configDict = readKeyValueConfig(filename)

    kernelDict = getKernelDict(configDict)

    for key in kernelDict:
        kernelDict[key] = kernelDict[key][0]

    for key in configDict[SECTION_VAR]:
        configDict[SECTION_VAR][key] = ' '.join(configDict[SECTION_VAR][key])

    return configDict[SECTION_VAR], configDict[SECTION_DEP], kernelDict


def readDependsConf(filename, platforms):
    def appendPlatInfo(p, confWithPlat, output):
        for proj_t in confWithPlat:
            for tag_t in confWithPlat[proj_t]:
                if p not in confWithPlat[proj_t][tag_t]:
                    p = 'all'

                if tag_t == 'bug':
                    output[proj_t][tag_t].update(confWithPlat[proj_t][tag_t][p])
                else:
                    output[proj_t][tag_t] = list(set(output[proj_t][tag_t] + confWithPlat[proj_t][tag_t][p]))

    dict_conf = {'build': {'curr': [], 'base': [], 'bug': {}},
                 'ref': {'curr': [], 'base': []},
                 'pack': {'curr': [], 'base': []},
                 'build64': {'curr': [], 'base': [], 'bug': {}},
                 'ref64': {'curr': [], 'base': []},
                 'pack64': {'curr': [], 'base': []}}

    configDict = readConfigFile(filename)
    defaultdicts = lambda:defaultdict(defaultdicts)
    confWithPlat = defaultdicts()

    for sec in configDict:
        project_type, tag_type, platform = resolveKeyNames(sec)
        if not project_type:
            continue

        if configDict[sec]:
            for line in configDict[sec]:
                if tag_type == 'bug':
                    key, values = parseKeyValue(line)
                    if key == '':
                        reportMessage(ERROR_IO, "Line '"+line+"' is not a legal key-value pair")
                    else:
                        confWithPlat[project_type][tag_type][platform][key] = values
                else:
                    # XXX: should be a list
                    confWithPlat[project_type][tag_type][platform] = []
                    confWithPlat[project_type][tag_type][platform] += configDict[sec]
    if platforms:
        for p in platforms:
            appendPlatInfo(p, confWithPlat, dict_conf)
    else:
        appendPlatInfo('all', confWithPlat, dict_conf)

    return dict_conf


def getBaseEnvironment(base_dir, proj, env, ver = ''):
    filename = findDependsFile(base_dir, proj)
    dict_env = {}

    if ver:
        dict_env['all'] = ver
        return dict_env

    if not env:
        env = SECTION_DEFAULT

    try:
        conf = open(filename, 'r')
    except IOError:
        reportMessage(ERROR_LOG, 'Fail to open '+filename+'. Assume not a normal project.')
        dict_env['all'] = 'unknown'
    else:
        while (True):
            line = getNextLine(conf)
            if line == '': break  # EOF
            section_name = parseSectionName(line)
            if section_name != '':
                if section_name == env:
                    section = env
                else:
                    section = ''
                continue
            if section == '':
                continue
            key, value = parseKeyValue(line)
            if key == '':
                reportMessage(ERROR_IO, "Line '"+line+"' is not a legal key-value pair")
            elif len(value) == 0:
                continue  # Skip line without base environment specified
            dict_env[key] = value[0]
        conf.close()
    #if not dict_env.has_key('all'):
    #    reportMessage(ERROR_OTHER, 'Please specify all="..." in '+filename)
    reportMessage(ERROR_LOG, 'Use environment settings in ['+ env +']')
    return dict_env


def getBuiltinProjects(script_dir):
    cmd = '. '+script_dir+'/include/projects; echo $BuiltinProjects'
    reportMessage(ERROR_LOG, cmd)
    pipe = Popen(cmd, stdout=PIPE, shell=True)
    return set(pipe.stdout.read().strip().split(' '))


def readPackageSetting(filename, package_id):
    package_setting = {}
    global_setting = {}

    if os.path.exists(filename):
        global_setting = readKeyValueConfig(filename)

    if package_id in global_setting:
        package_setting = global_setting[package_id]

    return package_setting

def readPackageInfo(filename):
    dict_info = {}
    try:
        info = open(filename, 'r')
    except IOError:
        reportMessage(ERROR_IO, 'Fail to open '+filename)
    else:
        while (True):
            line = getNextLine(info)
            if line == '': break  # EOF
            key, value = parseKeyValue(line)
            if key in INFO_KEYS: dict_info[key] = string.join(value, ' ')
        info.close()
    return dict_info


class TraverseHook:
    def __init__(self, arch, branch, base, do_base):
        self.arch = arch
        self.branch = branch
        self.base = base
        self.do_base = do_base
        pass
    def perform(self, config, info):
        pass


def resolveBaseTarget(arch, dict_env):
    base = ''
    if dict_env.has_key(arch): base = dict_env[arch]
    elif dict_env.has_key('all'): base = dict_env['all']
    else: reportMessage(ERROR_DEP, 'Base environment not specified for '+arch)
    return base


def replaceSingleVariable(group, target, replacement):
    try:
        group.remove(target)
        if replacement != '': group.add(replacement)
    except KeyError: pass


def replaceVariables(group, arch, dict_var, dict_kernel, do_base):
    if VAR_KERNEL_PROJ in group['curr'] | group['base']:
        try:
            kernel = string.join(set(dict_kernel.values()), ' ') if arch == '' else dict_kernel[arch]
        except KeyError:
            kernel = ''
            reportMessage(ERROR_LOG, 'Kernel projects not specified! Skip it.')
        replaceSingleVariable(group['curr'], VAR_KERNEL_PROJ, kernel)
        if do_base: replaceSingleVariable(group['base'], VAR_KERNEL_PROJ, kernel)
    for key in dict_var.keys():
        replaceSingleVariable(group['curr'], key, dict_var[key])
        if do_base: replaceSingleVariable(group['base'], key, dict_var[key])

def traverseSource(projects, base_dir, arch, dict_info, hook, do_base):
    dict_dep = dict_info['dep']

    seen = {'curr': projects.copy()|BasicProjects, 'base': set()}
    build_dep = {'curr': set(), 'base': set()}
    ref_only = {'curr': set(), 'base': set()}
    for_pack = {'curr': set(), 'base': set()}
    base = resolveBaseTarget(arch, dict_info['env'])

    builtin = getBuiltinProjects(base_dir+'/pkgscripts-ng')
    todo = projects.copy()
    while len(todo) != 0:
        build_dep['curr'].clear()
        if do_base: build_dep['base'].clear()
        for proj in todo:
            filename = findDependsFile(base_dir, proj)
            if not re.match(r'^\$', proj) and os.path.isfile(filename):
                dict_conf = readDependsConf(filename, [arch])
                # FIXME merge dict_dep and dict_conf with logs?
                for p in dict_conf['build']['bug']:
                    dict_dep[p] = dict_conf['build']['bug'][p];
                    if len(dict_dep[p]) == 0 or dict_dep[p][0] == '': del dict_dep[p]
                build_dep['curr'].update(dict_conf['build']['curr'])
                build_dep['curr'].update(dict_conf['pack']['curr'])
                ref_only['curr'].update(dict_conf['ref']['curr'])
                for_pack['curr'].update(dict_conf['pack']['curr'])
                if do_base:
                    build_dep['base'].update(dict_conf['build']['base'])
                    build_dep['base'].update(dict_conf['pack']['base'])
                    ref_only['base'].update(dict_conf['ref']['base'])
                    for_pack['curr'].update(dict_conf['pack']['base'])
            elif do_base and dict_dep.has_key(proj):
                build_dep['base'].update(dict_dep[proj])
        build_dep['curr'] -= seen['curr']
        seen['curr'] |= build_dep['curr']
        if do_base:
            build_dep['base'] -= seen['base']
            seen['base'] |= build_dep['base']
            # FIXME better error report?
            conflict = seen['curr'] & seen['base']
            if len(conflict) != 0:
                # Ignore conflict but built-in projects
                level = ERROR_LOG if len(conflict-builtin) == 0 else ERROR_DEP
                reportMessage(level, 'Conflict at {'+string.join(conflict, ',')+'}')

        if hook != None:
            config = {'proj':
                    {'curr': build_dep['curr'],
                    'base': build_dep['base']},
                'base': base, 'do_base': do_base, 'branch': ''}
            hook.perform(config, dict_info)

        todo.clear()
        todo.update(build_dep['curr'])
        if do_base: todo.update(build_dep['base'])

    if hook != None:
        config = {'proj':
                {'curr': ref_only['curr'] - seen['curr'],
                'base': ref_only['base'] - seen['base']},
            'base': base, 'do_base': do_base, 'branch': ''}
        try:
            if VAR_KERNEL_PROJ in seen['curr']:
                config['proj']['curr'].add(dict_info['kernel'][arch])
            elif VAR_KERNEL_PROJ in seen['base']:
                config['proj']['base'].add(dict_info['kernel'][arch])
        except KeyError:
            reportMessage(ERROR_LOG, 'Kernel projects not specified! Skip it.')
        hook.perform(config, dict_info)

    # Replace variables
    for group in [seen, ref_only, for_pack]:
        replaceVariables(group, arch, dict_info['var'], dict_info['kernel'], do_base)
    return seen, ref_only, for_pack


def checkBuildMachine(filename):
    pipe = Popen('. '+filename+'; echo $BuildMachineList', stdout=PIPE, shell=True)
    machine_list = pipe.stdout.read().strip().split(' ')
    for interface in ["eth0", "net0", "net1", "bond0"]:
        cmd = 'ifconfig %s 2> /dev/null | grep "inet addr:" | cut -d":" -f2 | cut -d" " -f1' % interface
        ip = Popen(cmd, stdout=PIPE, shell=True).stdout.read().strip()
        if not ip:
            cmd = "ifconfig %s 2> /dev/null | grep 'inet ' | awk '{print $2}'" % interface
            ip = Popen(cmd, stdout=PIPE, shell=True).stdout.read().strip()
        if ip:
            break
    if ip in machine_list:
        return True
    else:
        print('This IP ('+ip+') is not build machine.')
        return False


def showTimeCost(start, end, tag):
    diff = int(end-start)
    diff_second = diff%60
    diff_minute = (diff/60)%60
    diff_hour = (diff/3600)%60
    print('Time cost: {0:02d}:{1:02d}:{2:02d}  [{3:s}]'.format(diff_hour, diff_minute, diff_second, tag))


def getArchDir(arch, dict_env):
    if dict_env.has_key(arch):
        return 'ds.'+arch+'-'+dict_env[arch]
    elif dict_env.has_key('all'):
        return 'ds.'+arch+'-'+dict_env['all']
    else:
        reportMessage(ERROR_ARG, 'Fail to get directory of '+arch)


def getEnvVer(arch, dict_env):
    version = ''
    result = []
    if dict_env.has_key(arch):
        version = dict_env[arch]
    elif dict_env.has_key('all'):
        version = dict_env['all']
    else:
        reportMessage(ERROR_ARG, 'Fail to get enviroment version of ' + arch)

    result = version.split('.')
    return int(result[0]), int(result[1])


def detectPlatforms(root_folder, dict_env):
    platforms = []
    if not os.path.isdir(root_folder):
        reportMessage(ERROR_ARG, root_folder+' is not a folder')
    for folder in os.listdir(root_folder):
        if not os.path.isdir(root_folder+'/'+folder): continue
        if not re.match(r'^ds\.', folder): continue
        parts = string.join(folder.split('.')[1:], '.').split('-')
        if len(parts) != 2 or parts[0] == '' or parts[1] == '': continue
        arch = parts[0]
        suffix = string.join(parts[1:], '-')
        idx = arch if dict_env.has_key(arch) else 'all'
        if not dict_env.has_key(idx): continue
        if dict_env[idx] == suffix: platforms.append(arch)
    if not platforms :
        reportMessage(ERROR_ARG, 'No platform found in '+root_folder)
    return platforms


def replaceVirtualProjects(projects):
    result = set()
    addedBase = set()
    for proj in projects:
        idx = string.find(proj, VIRTUAL_PROJ_SEP)
        baseName = proj[:idx]
        if baseName in addedBase: continue
        addedBase.add(baseName)
        result.add(proj)
    return result


def findDependsFile(base_dir, proj):
    idx = string.find(proj, VIRTUAL_PROJ_SEP)
    if idx == -1:
        real = proj
        suffix = ''
    else:
        real = proj[:idx]
        suffix = proj[idx:]
    proj_dir = base_dir+'/source/'+proj
    if not os.path.isdir(proj_dir):
        proj_dir = base_dir + '/source/' + real

    filename = proj_dir + '/SynoBuildConf/depends'
    return filename+suffix if os.path.isfile(filename+suffix) else filename


def setDependsFile(script_dir, arch, dict_env):
    curr_dir = os.getcwd()
    os.chdir(script_dir)
    try:
        check_call('. include/gitutils; GitSetDependsFile '+arch+':'+resolveBaseTarget(arch, dict_env), shell=True)
    except CalledProcessError:
        pass
    os.chdir(curr_dir)


def traverseDependProjects(projects, arch, dict_env, script_dir, do_base, checkout_depend_file=True, hook=None):
    # checkout and read base depend file
    if checkout_depend_file:
        setDependsFile(script_dir, arch, dict_env)
    DictVar, DictDep, DictKernel = readDependsBase(script_dir+'/include/project.depends')

    return traverseSource(projects, os.path.dirname(script_dir), arch,
                          {'env': dict_env, 'var': DictVar, 'dep': DictDep, 'kernel': DictKernel}, hook, do_base)
