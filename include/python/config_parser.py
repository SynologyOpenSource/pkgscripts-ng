import os
import configparser
from collections import defaultdict
# Copyright (c) 2000-2020 Synology Inc. All rights reserved.

class ConfigNotFoundError(RuntimeError):
    pass


def remove_quote(string):
    if "#" in string:
        string = string.split("#")[0].strip()

    return string.strip('"').strip("'")


class ConfigParser():
    def __init__(self, config):
        if not os.path.isfile(config):
            raise ConfigNotFoundError(config)

        self.config = configparser.ConfigParser(allow_no_value=True)
        self.config.optionxform = str
        self.config.read(config)

    def _get_section_keys(self, section):
        if self.config.has_section(section):
            return list(set(map(remove_quote, self.config[section].keys())))
        else:
            return []

    def _get_section_values(self, section):
        if self.config.has_section(section):
            return list(set(map(remove_quote, self.config[section].values())))
        else:
            return []

    def get_section_dict(self, section):
        ret = defaultdict(list)
        if self.config.has_section(section):
            ret = defaultdict(list, self.config[section])
            for key, value in ret.items():
                ret[key] = remove_quote(value).split()
        return ret


class DependsParser(ConfigParser):
    sec_build_dep = 'BuildDependent'
    sec_build_tag = 'BuildDependent-Tag'
    sec_ref = 'ReferenceOnly'
    sec_ref_tag = 'ReferenceOnly-Tag'
    sec_pack = 'PackagePacking'
    sec_pack_tag = 'PackagePacking-Tag'
    sec_default = 'default'

    def convert_value_str(self, d):
        ret = {}
        for key, value in d.items():
            ret[key] = value[0]

        return ret

    @property
    def build_dep(self):
        return self._get_section_keys(self.sec_build_dep)

    @property
    def build_tag(self):
        return self._get_section_keys(self.sec_build_tag)

    @property
    def ref_only(self):
        return self._get_section_keys(self.sec_ref)

    @property
    def ref_only_tag(self):
        return self._get_section_keys(self.sec_ref_tag)

    @property
    def pack(self):
        return self._get_section_keys(self.sec_ref)

    @property
    def pack_tag(self):
        return self._get_section_keys(self.sec_ref_tag)


    def get_env_section(self, section):
        return self.convert_value_str(self.get_section_dict(section))

    def get_all_dependent(self):
        return self.build_dep, self.build_dep_tag, self.ref_only, self.ref_only_tag


class ProjectDependsParser(ConfigParser):
    sec_project_dep = 'project dependency'
    sec_64_project_dep = '64bit project dependency'
    sec_kernel = '${Kernel}'
    sec_variables = 'variables'
    sec_dynamic_vars = 'dynamic variable list'

    @property
    def project_depends(self):
        return self.get_section_dict(self.sec_project_dep)

    @property
    def all_kernels(self):
        return self._get_section_values(self.sec_kernel)

    @property
    def variables(self):
        return self.get_section_dict(self.sec_variables)

    @property
    def dynamic_variables(self):
        return self.get_section_dict(self.sec_dynamic_vars)['list']

    def get_platform_kernel(self, platform):
        return self.get_section_dict(self.sec_kernel)[platform][0]

    def get_platform_kernels(self, platforms):
        return [self.get_platform_kernel(_) for _ in platforms]

    def get_project_dep(self, project):
        return self.project_depends[project]

    def get_dyn_sec_value(self, dyn_var, platform):
        if dyn_var not in self.config:
            raise RuntimeError("[{}] not in project.depends.".format(dyn_var))

        if platform in self.get_section_dict(dyn_var):
            return self.get_section_dict(dyn_var)[platform][0]
        elif 'default' in self.get_section_dict(dyn_var):
            return self.get_section_dict(dyn_var)['default'][0]

    def get_dyn_sec_values(self, dyn_var, platforms):
        if dyn_var not in self.config:
            raise RuntimeError("[{}] not in project.depends.".format(dyn_var))

        if not platforms:
            result = []
            for value in self.get_section_dict(dyn_var).values():
                result += value
            return list(set(result))

        return [self.get_dyn_sec_value(dyn_var, _) for _ in platforms]


class PackageSettingParser(ConfigParser):
    def get_section(self, package):
        return self.get_section_dict(package)


class KeyValueParser():
    def __init__(self, f):
        if not os.path.isfile(f):
            raise ConfigNotFoundError(f)

        config = configparser.ConfigParser()
        config.optionxform = str
        with open(f, 'r', encoding='utf-8') as fd:
            config.read_string('[top]\n' + fd.read())
        self.config = dict(config['top'])

    def __getitem__(self, key):
        return remove_quote(self.config[key])

    def keys(self):
        return self.config.keys()
