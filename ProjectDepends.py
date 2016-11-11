#!/usr/bin/python3

import sys
import string
import os
import glob
import argparse
import re

ScriptDir = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.append(ScriptDir + '/include')
sys.path.append(ScriptDir + '/include/python')
import BuildEnv
from config_parser import DependsParser, ProjectDependsParser

# config file, to get basic project parameters
section_depends = "project dependency"
section_variables = "variables"
config_path = ScriptDir + "/include/project.depends"

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
    def __init__(self, dictIn, level, direct):
        self.dict = dictIn
        self.direct = direct
        self.stack = []
        self.listOut = []
        self.level = level
        self.visited = {}
        self.graph = {}

    def traveseList(self, listProjs, t_level):
        if self.level != 0 and t_level >= self.level:
            return

        for proj in listProjs:
            if proj in self.stack:
                raise DependencyError(self.stack, proj)
            if proj in self.visited and t_level >= self.visited[proj]:
                continue
            self.stack.append(proj)

            self.visited[proj] = t_level

            depProj = self.getDepProjList(proj)
            if len(depProj) > 0:
                self.traveseList(depProj, t_level+1)

            if proj not in self.listOut:
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
        return self.getReverseList(proj, self.dict)

    def getTraverseList(self, proj, Dict):
        if proj in Dict:
            return Dict[proj]
        return []

    def getTraverseDep(self, proj):
        return self.getTraverseList(proj, self.dict)

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


# replace project.depends Variable section in project dependency section
# i.e. ${KernelPacks} to synobios
def replaceVariableSection(config, dictDepends):
    for var, value in config.variables.items():
        # change key
        if var in dictDepends:
            dictDepends[var] = dictDepends.pop(var)

        # change value
        for proj in dictDepends:
            dictDepends[proj] = [_.replace(var, value[0]) for _ in dictDepends[proj]]


def isKernelHeaderProj(newProj):
    pattern_header = re.compile(r"^linux-.*-virtual-headers$")
    if pattern_header.match(newProj):
        return True

    return False


def normalizeProjects(projects, config, kernels):
    out_projects = set()
    blAddKernelHeader = None
    allKernels = config.all_kernels

    for proj in projects:
        newProj = proj.rstrip("/")

        if isKernelHeaderProj(newProj):
            newProj = ""
            blAddKernelHeader = True
        if newProj in allKernels:
            out_projects.update(kernels)
            continue
        elif newProj == libc_project:    # always skip libc
            newProj = ""

        out_projects.add(newProj)

    return blAddKernelHeader, list(out_projects)


def findPlatformDependsProj(platformDependsSection, platforms):
    listReplaceProj = set()
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


def replaceVariableInDictSection(dictDepends, variable, projsToReplace):
    for proj in dictDepends:
        listDepProj = dictDepends[proj]
        if variable in listDepProj:
            for proj in projsToReplace:
                listDepProj.insert(listDepProj.index(variable), proj)
            listDepProj.remove(variable)


def is64BitPlatform(platform):
    listPlatform64 = ['x64', 'bromolow', 'cedarview', 'avoton',
                      'bromolowESM', 'baytrail', 'dockerx64']
    if platform in listPlatform64:
        return True
    else:
        return False


def ParseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', dest='display', action='store_true', help='Display (deprecated)')
    parser.add_argument('-p', dest='platform', type=str, help='Platform')
    parser.add_argument('-r', dest='r_level',  type=int, default=-1, help='Reverse depenedency traverse level')
    parser.add_argument('-x', dest='level',    type=int, default=-1, help="Traverse level")
    parser.add_argument('--header', dest='dump_header', default=False, action='store_true', help="Output kernel header")
    parser.add_argument('listProj', nargs='*', type=str, help='Replace project list')
    return parser.parse_args()


def loadConfigFiles(config):
    dictDepends = config.project_depends

    confList = glob.glob(ScriptDir + "/../source/*/SynoBuildConf/depends*")
    for confPath in confList:
        project = confPath.split('/')[-3]
        filename = confPath.split('/')[-1]
        if BuildEnv.isVirtualProject(filename):
            project = BuildEnv.deVirtual(project) + BuildEnv.VIRTUAL_PROJECT_SEPARATOR + BuildEnv.getVirtualName(filename)

        if os.path.isfile(confPath):
            depends = DependsParser(confPath)
            if project not in dictDepends:
                dictDepends[project] = []
            dictDepends[project] = list(set(dictDepends[project] + depends.build_dep))
            dictDepends[project] = list(set(dictDepends[project] + depends.build_tag))

    return dictDepends

# main procedure
if __name__ == "__main__":
    # get command line arguments
    dictDepends = {}
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

    config = ProjectDependsParser(config_path)
    dictDepends = loadConfigFiles(config)

    listProjs = dictArgs.listProj

    kernels = config.get_platform_kernels(platforms)

    if listProjs:
        dictDepGraph = {}
        blAddKernelHeader, normalizedProjList = normalizeProjects(listProjs, config, kernels)
        replaceVariableSection(config, dictDepends)
        depGraph = DepGraph(dictDepends, level, direct)
        listOut = depGraph.traverseDepends(normalizedProjList)

        # reorder need filter while args not contain 'x' and 'r'
        if dictArgs.level == -1 and dictArgs.r_level == -1:
            listReorder = []
            for proj in listOut:
                if proj in normalizedProjList:
                    listReorder.append(proj)
            listOut = listReorder

        if blAddKernelHeader or dictArgs.level >= 0 or dictArgs.dump_header:
            listKernelHeader = []
            for kernel in kernels:
                listKernelHeader.append(kernel + '-virtual-headers')
            listOut = listKernelHeader + listOut

        strOut = " ".join(listOut)
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
            print(" ".join(listKernelHeader))
        else:
            print(" ".join(kernels))
    else:  # len(listProjs) <= 0
        sys.exit(1)
