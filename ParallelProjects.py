#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

from ProjectDepends import ProjectNode, DepGraph  # use for pickle
import shelve
from collections import defaultdict
import os
import pickle
import argparse
import sys


def parse_args(args):
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    parser.add_argument('--init', help='Init a project generator')
    group.add_argument('-r', dest='reverse', action='store_false', help="Direct: reverse")
    group.add_argument('-x', dest='traverse', action='store_true', help="Direct: traverse [Default]")
    parser.add_argument('-c', dest='count', type=int, help="Depends level.")
    parser.add_argument('--next', action='store_true', help='Get next build projects.')
    parser.add_argument('--failed', action='store_true', help="Tag given project failed.")
    parser.add_argument('--show', action='store_true', help="show build status.")
    parser.add_argument('--purge', action='store_true', help="Purge this task.")
    parser.add_argument('projects', nargs='*', help='Projects to serve')

    args = parser.parse_args(args)
    if args.init:
        args.direct = args.reverse

    return args


class GraphTraverser:
    def __init__(self, direct, graph, builds):
        self.direct = direct
        self.graph = graph
        self.builds = sorted(builds)
        self.success = []
        self.failed = []
        self.skiped = defaultdict(set)
        self.visit_unreachable_node()

    # We need to update not built projects to `Success`
    def visit_unreachable_node(self):
        set_builds = set(self.builds)
        for proj, node in self.graph.created_projects.items():
            if not set(node.getProjectDepends(0)) & set_builds:
                node.update_status(True)

    def update_infected_projects_failed(self, depend_nodes, failed_root):
        for dep_node in depend_nodes:
            # If parent failed, we dont need to build all depend projects.
            if dep_node.visited:
                continue

            dep_node.update_status(False)

            if dep_node.proj in self.builds:
                self.skiped[failed_root].add(dep_node.proj)
                self.builds.remove(dep_node.proj)

            self.update_infected_projects_failed(self.get_infected_projects(dep_node), failed_root)

    def update_failed_projects(self, projs):
        for proj in projs:
            proj_node = self.graph.getProjectNode(proj)
            proj_node.update_status(False)
            self.failed.append(proj)
            if proj in self.builds:
                self.builds.remove(proj)
            self.update_infected_projects_failed(self.get_infected_projects(proj_node), proj)
            print('%s:%s' % (proj, ",".join(self.skiped[proj])))

    def update_infected_projects_success(self, depend_nodes):
        for dep_node in depend_nodes:
            # We need to build depend proj later, dont update need built dep to success
            if dep_node.visited or dep_node.proj in self.builds:
                continue

            if self.project_ready(dep_node):
                dep_node.update_status(True)
                self.update_infected_projects_success(self.get_infected_projects(dep_node))

    def update_success_projects(self, projs):
        for proj in projs:
            proj_node = self.graph.getProjectNode(proj)
            proj_node.update_status(True)
            self.success.append(proj)
            if proj in self.builds:
                self.builds.remove(proj)
            self.update_infected_projects_success(self.get_infected_projects(proj_node))

    def get_infected_projects(self, proj_node):
        if self.direct:
            return proj_node.rev_depends
        else:
            return proj_node.depends

    def project_ready(self, node):
        if self.direct:
            return all([dep_node.success for dep_node in node.depends])
        else:
            return all([rev_node.success for rev_node in node.rev_depends])

    def get_next(self, count):
        if not self.builds:
            return ['NULL']

        output = []
        for proj in self.builds:
            proj_node = self.graph.getProjectNode(proj)
            if self.project_ready(proj_node):
                output.append(proj_node.proj)
            if len(output) >= count:
                break

        return output

    def show(self):
        if self.success:
            print("\n[Success projects]")
            print(" ".join(self.success))

        if self.failed:
            print("\n[Failed projects -> Skiped projects]")
            for fail in self.failed:
                print("%s -> %s" % (fail, " ".join(self.skiped[fail])))
        print()


def main(args):
    args = parse_args(args)
    sys.setrecursionlimit(3000)
    shelve_file = os.path.join('/', str(os.getppid()) + '.shelve')

    with shelve.open(shelve_file, writeback=True) as sv:
        if args.init:
            with open(args.init, 'rb') as fd:
                depends = pickle.load(fd)
            sv['traverser'] = GraphTraverser(args.direct, depends, args.projects)
            return

        traverser = sv['traverser']
        if args.next:
            traverser.update_success_projects(args.projects)
            print(" ".join(traverser.get_next(args.count)))

        if args.failed:
            traverser.update_failed_projects(args.projects)

        if args.show:
            traverser.show()

    if args.purge:
        os.remove(shelve_file)


if __name__ == '__main__':
    main(sys.argv[1:])
