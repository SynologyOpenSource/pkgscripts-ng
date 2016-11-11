import os
from collections import defaultdict

from config_parser import ProjectDependsParser, DependsParser
import BuildEnv


class UpdateFailedError(RuntimeError):
    pass


class ConflictError(RuntimeError):
    pass


class UpdateHook:
    def __init__(self, *args, **kwargs):
        pass

    def update_tag(self, projects):
        pass

    def update_branch(self, projects):
        pass


class ProjectVisitor:
    def __init__(self, update_hook, dep_level, platforms, depends_cache=None, check_conflict=False):
        self.dict_projects = None
        self.update_hook = update_hook
        self.dep_level = dep_level
        self.proj_depends = ProjectDependsParser(os.path.join(BuildEnv.ScriptDir, 'include', 'project.depends'))
        self.platforms = platforms
        self.depends_cache = depends_cache
        self.check_conflict = check_conflict

    def devirtual_all(self, projs):
        return set(map(BuildEnv.deVirtual, projs))

    def traverse(self, root_proj):
        if not isinstance(root_proj, list):
            root_proj = [root_proj]

        self.dict_projects = defaultdict(set)
        self._traverse_projects(root_proj, 1)
        return self.dict_projects

    def checkout_git_refs(self):
        if self.update_hook:
            self.update_hook.update_tag(self.dict_projects['refTags'])
            self.update_hook.update_branch(self.dict_projects['refs'])
            intersect_projs = self.devirtual_all(self.dict_projects['tags']) & self.devirtual_all(self.dict_projects['branches'])
            if intersect_projs:
                self.update_hook.update_branch(intersect_projs)

    def show_proj_info(self):
        print("[INFO] Branch projects: " + " ".join(self.dict_projects['branches']))
        print("[INFO] Tag projects: " + " ".join(self.dict_projects['tags']))
        print("[INFO] Reference projects: " + " ".join(self.dict_projects['refs']))
        print("[INFO] Reference tag projects: " + " ".join(self.dict_projects['refTags']))

    def _traverse_projects(self, projects, level):
        if not projects:
            return

        if self.update_hook:
            self.update_hook.update_branch(projects)
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

        if self.update_hook and not self.depends_cache:
            self.update_hook.update_tag(projects)
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
        pass
