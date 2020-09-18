#!/usr/bin/python3
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

import os
import json
from collections import defaultdict

from config_parser import ProjectDependsParser, DependsParser, KeyValueParser
import BuildEnv
ScriptDir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ConflictError(RuntimeError):
    pass


class ProjectVisitor:
    def __init__(self, updater, dep_level, platforms=[], depends_cache=None, check_conflict=True, dep_update_projs={}, version=None):
        self.dict_projects = defaultdict(set)
        self.updater = updater
        self.dep_level = dep_level
        self.proj_depends = ProjectDependsParser(os.path.join(BuildEnv.ScriptDir, 'include', 'project.depends'))
        self.platforms = platforms
        self.depends_cache = depends_cache
        self.check_conflict = check_conflict
        self.dep_update_projs = dep_update_projs
        self.version = version

    def devirtual_all(self, projs):
        return set(map(BuildEnv.deVirtual, projs))

    def traverse(self, root_proj):
        if not isinstance(root_proj, list):
            root_proj = [root_proj]

        self._traverse_projects(root_proj, 1)
        return self.dict_projects

    def show_proj_info(self):
        print("Projects: " + " ".join(self.dict_projects['branches']))

    def _traverse_projects(self, projects, level):
        if not projects:
            return

        self.dict_projects['branches'].update(projects)

        self._check_confict()

        if level == self.dep_level:
            return

        new_masters, new_tags, new_refs, new_ref_tags = self._resolve_project_catagory(projects)
        self.dict_projects['refs'].update(new_refs)
        self.dict_projects['refTags'].update(new_ref_tags)

        new_masters -= self.dict_projects['branches']
        new_tags -= self.dict_projects['tags']

        self._traverse_projects(new_masters, level+1)
        self._traverse_tag_projects(new_tags, level+1)

    def _traverse_tag_projects(self, projects, level):
        if not projects:
            return

        if self.updater and not self.depends_cache:
            self.updater.update_tag(projects)
        self.dict_projects['tags'].update(projects)

        self._check_confict()

        if level == self.dep_level:
            return

        if self.depends_cache:
            new_masters, new_tags, new_refs, new_ref_tags = self.depends_cache.get(projects)
        else:
            new_masters, new_tags, new_refs, new_ref_tags = self._resolve_project_catagory(projects)

        self.dict_projects['refs'].update(new_refs)
        self.dict_projects['refTags'].update(new_ref_tags)
        dep_projs = new_masters | new_tags

        tag_projs = dep_projs - self.dict_projects['tags']

        self._traverse_tag_projects(tag_projs, level+1)

    def _resolve_project_catagory(self, projects):
        branches = set()
        tags = set()
        refs = set()
        refTags = set()

        for proj in projects:
            depends_file = BuildEnv.Project(proj).depends_script
            if os.path.isfile(depends_file):
                depends = DependsParser(depends_file)
                branches.update(depends.build_dep)
                tags.update(depends.build_tag)
                refs.update(depends.ref_only)
                refTags.update(depends.ref_only_tag)
            else:
                if proj in self.proj_depends.project_depends:
                    tags.update(self.proj_depends.get_project_dep(proj))

        for catagory in branches, tags, refs, refTags:
            # dynamic variable
            for var in self.proj_depends.dynamic_variables:
                if var in catagory:
                    catagory.remove(var)
                    catagory.update(self.proj_depends.get_dyn_sec_values(var, self.platforms))

            # synobios
            for k, v in self.proj_depends.variables.items():
                if k in catagory:
                    catagory.remove(k)
                    catagory.update(v + self.proj_depends.get_platform_kernels(self.platforms))

        return branches, tags, refs, refTags

    def _check_confict(self):
        if not self.check_conflict:
            return

        conflict = self.dict_projects['branches'] & self.dict_projects['tags']
        if conflict:
            raise ConflictError(("`%s' both in [BuildDependent] and [BuildDependent-Tag] catagory!" % " ".join(conflict)))
        conflict = self.dict_projects['branches'] & self.dict_projects['refTags']
        if conflict:
            raise ConflictError(("`%s' both in [BuildDependent] and [ReferenceOnly-Tag] catagory!" % " ".join(conflict)))
