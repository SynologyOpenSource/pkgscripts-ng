#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import sys
import string
import os
import glob
import argparse
import pickle
import pprint
from collections import defaultdict
import re

from include import pythonutils
from include.python import BuildEnv
from config_parser import DependsParser, ProjectDependsParser
ScriptDir = os.path.dirname(os.path.abspath(sys.argv[0]))

# XXX: unified the variable with pythonutils.py
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


class ProjectNode:
    def __init__(self, proj):
        # FIXME name
        self.proj = proj
        self.depends = []
        self.rev_depends = []
        self.levels = defaultdict(set)
        self.addProject(1, [self.proj])
        self.success = False
        self.visited = False

    def updateDependLevel(self, child_node):
        for level, projs in child_node.levels.items():
            self.addProject(level + 1, projs)

    def addProject(self, level, projs):
        self.levels[level].update(projs)

    def addDependProj(self, child_node):
        self.depends.append(child_node)
        child_node.rev_depends.append(self)
        self.updateDependLevel(child_node)

    def getProjectOrder(self):
        orders = []
        for level, projs in sorted(self.levels.items(), key=lambda x: x[0], reverse=True):
            for proj in projs:
                if proj not in orders:
                    orders.append(proj)
        return orders

    def update_status(self, success):
        self.visited = True
        self.success = success

    def getProjectDepends(self, level):
        order = self.getProjectOrder()
        if level == 0:
            return order
        else:
            return sorted(self.getLevelsProjects(1, level), key=lambda x: order.index(x))

    def getLevelsProjects(self, low, high):
        output = set()

        for i in range(low, high + 1):
            output.update(self.levels[i])

        return output

    def __repr__(self):
        return self.proj


class DepGraph:
    # all these attributes are not necessary, just for prototype reference
    def __init__(self, dictDepends, direct):
        self.root = ProjectNode('DependRoot')
        self.root.update_status(True)
        self.direct = direct
        self.stack = []
        self.dictDepends = dictDepends
        self.reverseDep = defaultdict(list)
        self.created_projects = {}

    def getProjectNode(self, proj):
        if proj not in self.created_projects:
            raise RuntimeError("%s not created." % proj)
        return self.created_projects[proj]

    def createDepGraph(self, head, listProjs):
        for proj in listProjs:
            if proj in self.stack:
                raise DependencyError(self.stack, proj)
            self.stack.append(proj)

            if proj in self.created_projects:
                proj_node = self.created_projects[proj]
            else:
                proj_node = self.created_projects[proj] = ProjectNode(proj)

                depProj = self.getDepProjList(proj)
                if len(depProj) > 0:
                    self.createDepGraph(proj_node, depProj)

            head.addDependProj(proj_node)

            self.stack.pop()

    def dumpGraph(self, head):
        print(head.proj)
        pprint.pprint(head.levels)
        for p in head.depends:
            self.dumpGraph(p)

    def traverseDepends(self, listProjs, level):
        try:
            self.createDepGraph(self.root, listProjs)
            # self.dumpGraph(self.root)
        except DependencyError as e:
            e.dumpCircluarDepList()
            sys.exit(1)

        output = []
        t_level = level if level == 0 else level + 1
        output = self.root.getProjectDepends(t_level)
        output.remove(self.root.proj)

        if self.direct == 'backwardDependency':
            output.reverse()

        return output

    def getReverseDep(self, proj):
        reverseList = []
        if proj in self.reverseDep:
            return self.reverseDep[proj]

        for key in self.dictDepends.keys():
            if proj in self.dictDepends[key]:
                reverseList.append(key)
        self.reverseDep[proj] = reverseList

        return reverseList

    def getTraverseDep(self, proj):
        if proj in self.dictDepends:
            return self.dictDepends[proj]
        return []

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


# Replace ${XXXX} in dependency list by [${XXXX}] section
def replacePlatformDependsVariable(dictDepends, platforms, config):
    def replaceVariableWithSection(variable, section_name):
        try:
            dictSection = config.get_section_dict(section_name)
        except KeyError:
            print("No such section:" + variable)

        listPlatformDependsProj = findPlatformDependsProj(dictSection, platforms)
        replaceVariableInDictSection(dictDepends, variable, listPlatformDependsProj)

    if not config.dynamic_variables:
        # for old project depends compatibility
        replaceVariableWithSection("${KernelProjs}", pythonutils.SECTION_KERNEL_OLD)
        return
    for variable in config.dynamic_variables:
        replaceVariableWithSection(variable, variable)


def ParseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', dest='display', action='store_true', help='Display (deprecated)')
    parser.add_argument('-p', dest='platform', type=str, help='Platform')
    parser.add_argument('-r', dest='r_level', type=int, default=-1, help='Reverse depenedency traverse level')
    parser.add_argument('-x', dest='level', type=int, default=-1, help="Traverse level")
    parser.add_argument('--header', dest='dump_header', default=False, action='store_true', help="Output kernel header")
    parser.add_argument('--dump', dest='dump_pickle', help="Dump project depends graph into pickle file.")

    group = parser.add_argument_group('Cache')
    group.add_argument('--version', type=int, default=0)
    group.add_argument('--type', choices=['tag', 'dep', 'both'], default='both')

    parser.add_argument('listProj', nargs='*', type=str, help='Replace project list')
    return parser.parse_args()


def loadConfigFiles(config):
    dictDepends = config.project_depends

    confList = glob.glob(ScriptDir + "/../source/*/SynoBuildConf/depends*")
    confList = [conf for conf in confList if re.search(r'^depends(-virtual-[-.\w]+)*$', os.path.basename(conf))]
    for confPath in confList:
        project = confPath.split('/')[-3]
        filename = confPath.split('/')[-1]
        if BuildEnv.isVirtualProject(filename):
            project = BuildEnv.deVirtual(project) + \
                BuildEnv.VIRTUAL_PROJECT_SEPARATOR + \
                BuildEnv.getVirtualName(filename)

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

    if dictArgs.platform:
        platforms = dictArgs.platform.strip().split(" ")

    if dictArgs.level >= 0 and dictArgs.r_level >= 0:
        raise RuntimeError("Error! x and r can not use simultaneously")
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
        replacePlatformDependsVariable(dictDepends, platforms, config)

        depGraph = DepGraph(dictDepends, direct)
        listOut = depGraph.traverseDepends(normalizedProjList, level)
        if dictArgs.dump_pickle:
            sys.setrecursionlimit(3000)
            with open(dictArgs.dump_pickle, 'wb') as fd:
                pickle.dump(depGraph, fd)
            sys.exit(0)

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
