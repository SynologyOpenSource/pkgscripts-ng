#!/usr/bin/python2

import sys
import string
import os
import glob
import argparse
import re
from sets import Set

sys.path.append(os.path.dirname(os.path.abspath(sys.argv[0])) + '/include')
import pythonutils
sys.path.append(os.path.dirname(os.path.abspath(sys.argv[0])) + '/include/python')

# XXX: unified the variable with pythonutils.py
# config file, to get basic project parameters
config_path = "include/project.depends"
section_depends = "project dependency"
section_depends64 = "64bit project dependency"
section_variables = "variables"

# for kernel project replacement
kernel_variable = "${Kernel}"
libc_project = "uclibc0929"

# Target sections in SynoBuildConf for packages
target_sections = ["BuildDependent", "BuildDependent-Tag"]
target_sections64 = ["BuildDependent64", "BuildDependent-Tag64"]
dynamic_variable = "dynamic variable list"


class DependencyError(Exception):
    def __init__(self, stack, proj):
        self.stack = stack
        self.project = proj
        print("Error! Circluar dependency found!!")

    def dumpCircluarDepList(self):
        blFound = False
        for proj in self.stack:
            if proj == self.project:
                blFound = True
            if blFound:
                print(proj + " -> ")
        print(self.project)


class DepGraph:
    # all these attributes are not necessary, just for prototype reference
    def __init__(self, dictIn, level, direct, blUseSection64):
        self.dict = dictIn
        self.direct = direct
        self.stack = []
        self.listOut = []
        self.level = level
        self.graph = {}
        self.useSection64 = blUseSection64

    def traveseList(self, listProjs, t_level):
        if self.level != 0 and t_level >= self.level:
            return

        for proj in listProjs:
            if proj in self.stack:
                raise DependencyError(self.stack, proj)
            if proj in self.listOut:
                continue
            self.stack.append(proj)
            depProj = self.getDepProjList(proj)
            if len(depProj) > 0:
                self.traveseList(depProj, t_level+1)
            self.listOut.append(proj)
            self.stack.pop()

    def traverseDepends(self, listProjs):
        try:
            self.traveseList(listProjs, 0)
        except DependencyError as e:
            e.dumpCircluarDepList()
            sys.exit(1)
        return self.listOut

    def getReverseList(self, proj, traveseDict):
        reverseList = []
        for key in traveseDict.keys():
            if proj in traveseDict[key]:
                reverseList.append(key)
        return reverseList

    def getReverseDep(self, proj):
        Dict = {}
        if self.useSection64:
            reverseDep = []
            Dict = self.dict[section_depends64]
            reverseDep = self.getReverseList(proj, Dict)
            if reverseDep:
                return reverseDep

        Dict = self.dict[section_depends]
        return self.getReverseList(proj, Dict)

    def getTraverseList(self, proj, Dict):
        if proj in Dict:
            return Dict[proj]
        return []

    def getTraverseDep(self, proj):
        Dict = {}
        if self.useSection64:
            Dict = self.dict[section_depends64]
            traverseDep = self.getTraverseList(proj, Dict)
            if traverseDep:
                return traverseDep

        Dict = self.dict[section_depends]
        return self.getTraverseList(proj, Dict)

    def getDepProjList(self, proj):
        # -r : Expand project dependency list reversely.
        if self.direct == 'backwardDependency':
            return self.getReverseDep(proj)

        # -x: Traverse all dependant projects
        return self.getTraverseDep(proj)


class DepNode:
    def __init__(self, proj):
        self.nodeName = proj
        self.projDependOn = []
        self.projDependedBy = []

    def dumpNode(self):
        print('Project depened on : ' + self.projDependOn)
        print('Project depended by : ' + self.projDependedBy)


def dumpProjectDepends(project, dict):
    if project in dict:
        print()
        print("check this line in file '" + config_path + "'")
        print(project + ": " + string.join(dict[project]))


def _replaceVariable(dictVars, dictDepends):
    for var in dictVars:
        for proj in dictDepends:
            oldList = dictDepends[proj]
            if var in oldList:    # if var is in dependency list, replace it
                strNew = string.join(oldList)
                strNew = strNew.replace(var, string.join(dictVars[var]))
                dictDepends[proj] = strNew.split()

            # if the variable is a project name, replace the project name
            if var == proj:
                newProj = string.join(dictVars[var])
                newVal = dictDepends.pop(proj)
                dictDepends[newProj] = newVal


# replace project.depends Variable section in project dependency section
# i.e. ${KernelPacks} to synobios
def replaceVariableSection(dict, bl64bit):
    dictVars = dict[section_variables]
    dictDepends = dict[section_depends]
    _replaceVariable(dictVars, dictDepends)

    if bl64bit:
        dictDepends = dict[section_depends64]
        _replaceVariable(dictVars, dictDepends)


def getAllDependencyKey(dict):
    allDepProjkeys = dict[section_depends].keys()

    if dict[section_depends64].keys():
        for proj in dict[section_depends64].keys():
            if proj not in allDepProjkeys:
                allDepProjkeys.append(proj)
    return allDepProjkeys


def isKernelHeaderProj(newProj):
    pattern_header = re.compile(r"^linux-.*-virtual-headers$")
    if pattern_header.match(newProj):
        return True

    return False


def normalizeProjects(dict, projects, kernels):
    out_projects = set()
    blAddKernelHeader = None

    for proj in projects:
        newProj = proj.rstrip("/")

        if isKernelHeaderProj(newProj):
            newProj = ""
            blAddKernelHeader = True
        if isKernelProject(dict, newProj):
            out_projects.update(kernels)
            continue
        elif newProj == libc_project:    # always skip libc
            newProj = ""

        out_projects.add(newProj)

    return blAddKernelHeader, list(out_projects)


def findPlatformDependsProj(platformDependsSection, platforms):
    listReplaceProj = Set()
    projects = []

    # if there is no platform specified, check for all platforms
    if len(platforms) <= 0:
        platforms = platformDependsSection.keys()

    # get all kernel projects of all specific platforms
    for p in platforms:
        if p in platformDependsSection:
            projects = platformDependsSection[p]
        else:  # not in platform depends section
            try:
                projects = platformDependsSection['default']
            except KeyError:
                print("No such platform : " + p)
                sys.exit(1)

        for proj in projects:
            listReplaceProj.add(proj)

    return listReplaceProj


def replaceVariableInDictSection(dictInput, variable, projsToReplace):
    for key in dictInput:
        listDepProj = dictInput[key]
        if variable in listDepProj:
            for proj in projsToReplace:
                listDepProj.insert(listDepProj.index(variable), proj)
            listDepProj.remove(variable)


# Replace ${XXXX} in dependency list by [${XXXX}] section
def replacePlatformDependsVariable(dictInput, platforms, bl64bit):
    def replaceVariableWithSection(variable, section_name):
        try:
            dictSection = dictInput[section_name]
        except KeyError:
            print("No such section:" + variable)

        listPlatformDependsProj = findPlatformDependsProj(dictSection,
                                                          platforms)

        replaceVariableInDictSection(dictInput[section_depends],
                                     variable,
                                     listPlatformDependsProj)
        if bl64bit:
            replaceVariableInDictSection(dictInput[section_depends64],
                                         variable,
                                         listPlatformDependsProj)

    if dynamic_variable not in dictInput:
        # for old project depends compatibility
        replaceVariableWithSection("${KernelProjs}", pythonutils.SECTION_KERNEL_OLD)
        return
    for variable in dictInput[dynamic_variable]['list']:
        replaceVariableWithSection(variable, variable)


def isKernelProject(dictInput, strProj):
    bRet = False
    listKernels = pythonutils.getKernelDict(dictInput).values()
    listKernel = []

    for list in listKernels:
        listKernel += list

    if strProj in listKernel:
        bRet = True

    return bRet


def is64BitPlatform(platform):
    listPlatform64 = ['x64', 'bromolow', 'cedarview', 'avoton', 'braswell']
    if platform in listPlatform64:
        return True
    else:
        return False


def checkPlatform(platforms):
    bl64bit = True
    bl32bit = True
    for platform in platforms:
        blPlatformArch = is64BitPlatform(platform)
        bl64bit &= blPlatformArch
        bl32bit &= not blPlatformArch

    if bl32bit is True:
        return "32"
    if bl64bit is True:
        return "64"

    return "mix"

def ParseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', dest='display', action='store_true', help='Display (deprecated)')
    parser.add_argument('-p', dest='platform', type=str, help='Platform')
    parser.add_argument('-r', dest='r_level',  type=int, default=-1, help='Reverse depenedency traverse level')
    parser.add_argument('-x', dest='level',    type=int, default=-1, help="Traverse level")
    parser.add_argument('--header', dest='dump_header', default=False, action='store_true', help="Output kernel header")
    parser.add_argument('listProj', nargs='*', type=str, help='Replace project list')
    return parser.parse_args()


def loadConfigFiles(platforms):
    dictConfigs = {}

    strCurrentDir = os.path.dirname(os.path.abspath(sys.argv[0]))
    strOutConfigPath = strCurrentDir + "/" + config_path
    dictConfigs = pythonutils.readKeyValueConfig(strOutConfigPath)

    confList = glob.glob(strCurrentDir + "/../source/*/SynoBuildConf/depends*")
    for confPath in confList:
        project = confPath.split('/')[-3]
        filename = confPath.split('/')[-1]

        if os.path.isfile(confPath):
            confSetting = pythonutils.readDependsConf(confPath, platforms)
            for sec, project_type in [(section_depends, 'build'), (section_depends64, 'build64')]:
                # we don't have section_depends64 in old file
                if sec not in dictConfigs and sec == section_depends64:
                    continue
                if project not in dictConfigs[sec]:
                    dictConfigs[sec][project] = []
                dictConfigs[sec][project] += confSetting[project_type]['curr']
                dictConfigs[sec][project] += confSetting[project_type]['base']

                for rewriteProj in confSetting[project_type]['bug']:
                    # XXX: what if the project hasn't loaded into dictConfigs?
                    if rewriteProj in dictConfigs[sec]:
                        dictConfigs[sec][rewriteProj] = confSetting[project_type]['bug'][rewriteProj]

    return dictConfigs

# main procedure
if __name__ == "__main__":
    # get command line arguments
    dictConfigs = {}
    listProjs = []
    listOut = []
    blAddKernelHeader = False
    direct = 'forwardDependency'

    platforms = []
    level = -1

    dictArgs = ParseArgs()

    if dictArgs.level >= 0 and dictArgs.r_level >= 0:
        raise RuntimeError("Error! x and r can not use simultaneously")
    if dictArgs.platform:
        platforms = dictArgs.platform.strip().split(" ")
    if dictArgs.level >= 0:
        level = dictArgs.level
    elif dictArgs.r_level >= 0:
        level = dictArgs.r_level
        direct = 'backwardDependency'

    # Reorder, we need to traverse all depend to sort the input projects.
    if dictArgs.level == -1 and dictArgs.r_level == -1:
        level = 0

    dictConfigs = loadConfigFiles(platforms)

    listProjs = dictArgs.listProj

    kernelSection = pythonutils.getKernelDict(dictConfigs)
    kernels = findPlatformDependsProj(kernelSection, platforms)

    platformArch = checkPlatform(platforms)
    if platformArch == "64" and section_depends64 in dictConfigs:
        bl64bit = True
    else:
        bl64bit = False

    if listProjs:
        dictDepGraph = {}
        blAddKernelHeader, normalizedProjList = normalizeProjects(dictConfigs, listProjs, kernels)
        replaceVariableSection(dictConfigs, bl64bit)
        replacePlatformDependsVariable(dictConfigs, platforms, bl64bit)
        depGraph = DepGraph(dictConfigs, level, direct, bl64bit)
        listOut = depGraph.traverseDepends(normalizedProjList)

        # mix means input has two different arch platform, we need to build
        # another graph for different arch.
        if platformArch == 'mix':
            depGraphMix = DepGraph(dictConfigs, level, direct, not bl64bit)
            listMix = depGraphMix.traverseDepends(normalizedProjList)
            for proj in listMix:
                if proj not in listOut:
                    listOut.append(proj)

        # reorder need filter while args not contain 'x' and 'r'
        if dictArgs.level == -1 and dictArgs.r_level == -1:
            listReorder = []
            for proj in listOut:
                if proj in listProjs:
                    listReorder.append(proj)
            listOut = listReorder

        if blAddKernelHeader or dictArgs.level >= 0 or dictArgs.dump_header:
            listKernelHeader = []
            for kernel in kernels:
                listKernelHeader.append(kernel + '-virtual-headers')
            listOut = listKernelHeader + listOut

        strOut = string.join(listOut, " ")
        if len(strOut) > 0:
            print(strOut)
    elif len(platforms) > 0:
        # has platform specified, print kernel version
        if len(kernels) == 0:
            sys.stderr.write('Error: No matching kernel found!\n')
            sys.exit(1)
        if blAddKernelHeader or dictArgs.dump_header:
            listKernelHeader = []
            for kernel in kernels:
                listKernelHeader.append(kernel + '-virtual-headers')
            print(string.join(listKernelHeader, " "))
        else:
            print(" ".join(kernels))
    else:  # len(listProjs) <= 0
        sys.exit(1)
