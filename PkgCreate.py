#!/usr/bin/python2
# Copyright (c) 2000-2016 Synology Inc. All rights reserved.


import sys, os
from getopt import *
from time import localtime, strftime
from shutil import rmtree

# Paths
ScriptDir = os.path.dirname(os.path.abspath(sys.argv[0]))
BaseDir = os.path.dirname(ScriptDir)
ScriptName = os.path.basename(sys.argv[0])
PkgScripts = '/pkgscripts-ng'

sys.path.append(ScriptDir+'/include')
import pythonutils
from pythonutils import *


def displayUsage(code):
    message = '\nUsage\n\t'+ScriptName
    message += ' [-p platforms] [-x level] [OPTIONS] pkg_project'
    message += """

Synopsis
    Build and/or create .spk for packages.

Options
    -e {build_env}
        Specify environment section in SynoBuildConf/depends. Default is [default].
    -v {env version}
        Specify target DSM version manually.
    -p {platforms}
        Specify target platforms. Default to detect available platforms under build_env/.
    -P {platforms}
        Specify platforms to be excluded.
    -b {package_branch}
        Specify branch of package.
    -x {level}
        Build dependant projects (to specified dependency level).
    -s {suffix}
        Specify suffix of folder of build environment (build_env/).
    -m {milestone}
        For release candidate when uploading. Specify which setting defined in SynoBuildConf/milestone to use.
    -c: Build, install, upload (if build machine) package.
    -u: Perform check for SynoUpdate and stop when update failed.
    -U: No update. Do link and do clean, then run SynoBuild only.
    -L: No update. No link and no clean, then run SynoBuild only.
    -l: No update. No build and no clean, then link projects only.
    -B: No Build. Do update only.
    -I: Run install script to create spk.
    -i: Run install script to create spk and upload results.
    -z: Run for all platforms concurrently.
    -J: Do SynoBuild with -J.
    -j: Do SynoBuild with --jobs.
    -S: Disable silent make.
    --ccache-size {size}
        Set size of ccache to reduce compiler activities. Default is 1G.
    --ccache-clean
        Build with a cleared ccache.
    --no-builtin
        Do not skip built-in projects.
    --no-sign
        Do not make code sign
    --demo: Build demo package. Default environment folder is build_env-demo if no suffix is given.
    --base: Build all projects (by default, only projects not on tag are built).
    -h, --help
        Show this help.

Task Control
                        (default) -U   -L   -I   -i   -c   -Uc
    Update source code        o    x    x    x    x    o    x
    Link platform             o    o    x    x    x    o    o
    Build package             o    o    o    x    x    o    o
    Install package           x    x    x    o    o    o    o
    Upload spk files          x    x    x    x    o    o    o    (build machine only)
    Tag and send mail         x    x    x    x    x    o    o    (build machine only)

    Please use ONLY ONE of these options.
"""
    print >> sys.stderr, message
    sys.exit(code)


def updatePkgScripts():
    curr_dir = os.getcwd()
    os.chdir(ScriptDir)
    if os.path.isfile('include/gitutils'):
        try: check_call('. include/gitutils; GitUpdatePkgScripts', shell=True)
        except CalledProcessError: pass
    else:
        try: check_call('. include/envutils; UpdatePkgScripts', shell=True)
        except CalledProcessError: pass
    os.chdir(curr_dir)

def resolveBuildEnvPre(arch):
    curr_dir = os.getcwd()
    os.chdir(ScriptDir)
    if os.path.isfile('include/gitutils'):
        try: check_call('. include/gitutils; GitSetBuildEnvPre '+resolveBaseTarget(arch, DictEnv)+' '+arch, shell=True)
        except CalledProcessError: pass
    else:
        try: check_call('. include/envutils; SetBuildEnvPre '+resolveBaseTarget(arch, DictEnv)+' '+arch, shell=True)
        except CalledProcessError: reportMessage(ERROR_OTHER, "Please contact maintainer");
    os.chdir(curr_dir)

def resolveBuildEnvPost(arch, seen, ref_only):
    param = arch
    curr_dir = os.getcwd()
    os.chdir(ScriptDir)
    if os.path.isfile('include/gitutils'):
        if DoBase:
            for proj in seen | ref_only:
                param += ' '+proj
        try: check_call('. include/gitutils; GitSetBuildEnvPost '+resolveBaseTarget(arch, DictEnv)+' '+arch+' '+param, shell=True)
        except CalledProcessError: pass
    else:
        reportMessage(ERROR_LOG, 'No post-action to be done')
    os.chdir(curr_dir)

def resolveDirSuffix():
    if EnvSuffix != '': return '-'+EnvSuffix
    elif DemoMode: return '-demo'
    else: return ''

def updateProject(projects, target, dictVar=None):
    proj_list = ''
    for proj in projects:
        if proj == 'uistring' and os.path.isdir(BaseDir+'/source/'+proj+'/.git'):
            try: check_call('cd '+BaseDir+'/source/'+proj+'; git reset --hard; git pull --rebase=preserve', shell=True)
            except CalledProcessError: pass
            continue
        if proj == VAR_KERNEL_PROJ:
            continue
        elif re.match(r'^\$', proj):
            # is variable
            if dictVar.has_key(proj):
                proj_list += ' '+dictVar[proj]
            else:
                reportMessage(ERROR_DEP, 'Variable '+proj+' undefined')
        else:
            # is normal project
            proj_list += ' '+proj
    proj_list = proj_list.strip()
    if proj_list == '': return
    update_opt = SynoUpdateOpt+' --env '+target
    reportMessage(ERROR_LOG, 'env RenameLog=no '+ScriptDir+'/SynoUpdate '+update_opt+' '+proj_list)
    try:
        check_call('env RenameLog=no '+ScriptDir+'/SynoUpdate '+update_opt+' '+proj_list, shell=True)
    except CalledProcessError:
        if DoUpdateCheck:
            reportMessage(ERROR_OTHER, 'SynoUpdate error, please check '+BaseDir+'/'+UpdateLog);

class UpdateHook(TraverseHook):
    def perform(self, config, info):
        updateProject(config['proj']['curr'], self.branch, info['var'])
        if self.do_base: updateProject(config['proj']['base'], self.arch+':'+config['base'], info['var'])

def writeUpdateLog(msg):
    if not os.path.isdir(BaseDir+'/logs'): os.mkdir(BaseDir+'/logs')
    try:
        log = open(BaseDir+'/'+UpdateLog, 'a')
    except IOError:
        reportMessage(ERROR_IO, 'Fail to open '+BaseDir+'/'+UpdateLog)
    else:
        log.write(msg)
        log.close()


def prepareProjects(arch):
    cmd = ScriptDir+'/ProjectDepends.py -p '+arch+' '+ProjDependsOpt+' '+string.join(InputProjects, ' ')
    cmd += ' '+string.join(ForPack['curr'], ' ')
    if DoBase: cmd += ' '+string.join(ForPack['base'], ' ')
    reportMessage(ERROR_LOG, cmd)
    pipe = Popen(cmd, stdout=PIPE, shell=True)
    seq = pipe.stdout.read().strip().split(' ')

    if not DoBase:
        projects = Seen['curr'].intersection(seq)
        extra = RefOnly['curr']
    elif IgnoreBuiltin:
        builtin = getBuiltinProjects(ScriptDir)
        projects = (Seen['curr'] | (Seen['base'] - builtin)).intersection(seq)
        extra = RefOnly['curr'] | (RefOnly['base'] - builtin)
    else:
        projects = (Seen['curr'] | Seen['base']).intersection(seq)
        extra = RefOnly['curr'] | RefOnly['base']
    if UpdateScriptExist: extra |= BasicProjects

    dst_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
    if DoLink:
        for proj in ['/source/'+p for p in (projects | extra)]+['/pkgscripts-ng']:
            idx = string.find(proj, VIRTUAL_PROJ_SEP)
            real_proj = proj if idx == -1 else proj[:idx]
            try: check_call('rm -rf '+dst_dir+proj, shell=True)
            except CalledProcessError: pass
            reportMessage(ERROR_LOG, 'Link '+BaseDir+real_proj+' to '+dst_dir+proj)
            try: check_call('cp -al '+BaseDir+real_proj+' '+dst_dir+proj, shell=True)
            except CalledProcessError: pass
    if DoBuild:
        f = open(dst_dir+'/seen_curr.list', 'w')
        f.write(string.join(Seen['curr'].intersection(seq), ' '))
        f.close()
    return projects


def waitBackgroundProcess(plist):
    global PkgError
    print >> sys.stderr, '\tBackground pids: '+string.join([str(p.pid) for p in plist], ' ')
    sys.stderr.write('Wait for:')
    for p in plist:
        sys.stderr.write(' '+str(p.pid))
        p.communicate()
        if p.returncode != 0: PkgError = True
    print >> sys.stderr, ''

def popenPipe(cmd):
    p = Popen('set -o pipefail;'+cmd+';r=$?;set +o pipefail;exit $r', stdout=None, stderr=None, shell=True, executable='/bin/bash')
    return p


def buildPackage(package, projects, build_opt):
    global PkgError
    print(os.getcwd())
    build_cmd =  'chroot . env PackageName=' + package + ' '+ PkgScripts + '/SynoBuild '
    plist = []
    curr_dir = os.getcwd()
    for arch in Platforms:
        arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
        if os.path.isdir(arch_dir): os.chdir(arch_dir)
        else: continue
        sdk_version = ".".join([str(i) for i in getEnvVer(arch, DictEnv)])
        build_opt += ' --min-sdk ' + sdk_version
        log_file = 'logs.build'
        if not os.path.isdir('root/.tmp'): os.mkdir('root/.tmp')
        if os.path.isfile(log_file): os.rename(log_file, log_file+'.old')
        try: check_call('grep -q '+arch_dir+'/proc /proc/mounts', shell=True)
        except CalledProcessError:
            try: check_call('chroot . /bin/mount /proc', shell=True)
            except CalledProcessError: pass

        cmd = build_cmd+' -p '+arch+' '+build_opt+' '+string.join(projects[arch], ' ')
        redirect = ' 2>&1 >> '+log_file if RunBackground else ' 2>&1 | tee -a '+log_file
        hook = 'source/'+PkgProject+'/SynoBuildConf/prebuild'
        if os.access(hook, os.X_OK): cmd = hook+redirect+';'+cmd
        cmd += redirect
        hook = 'source/'+PkgProject+'/SynoBuildConf/postbuild'
        if os.access(hook, os.X_OK): cmd += ';'+hook+redirect
        reportMessage(ERROR_LOG, cmd)

        if RunBackground:
            plist.append(Popen(cmd, stdout=None, stderr=None, shell=True))
        else:
            p = popenPipe(cmd)
            p.communicate()
            if p.returncode != 0: PkgError = True
    os.chdir(curr_dir)
    if RunBackground: waitBackgroundProcess(plist)


def installPackage(package, debug_mode):
    global PkgError
    install_cmd = 'chroot . ' + PkgScripts + '/SynoInstall'
    install_opt = '--with-debug' if debug_mode else ''
    plist = []
    curr_dir = os.getcwd()
    for arch in Platforms:
        arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
        if os.path.isdir(arch_dir): os.chdir(arch_dir)
        else: continue
        log_file = 'logs.install'
        if os.path.isfile(log_file): os.rename(log_file, log_file+'.old')

        cmd = install_cmd+' -p '+arch+' '+install_opt+' '+package
        reportMessage(ERROR_LOG, cmd)
        if RunBackground:
            cmd += ' 2>&1 > '+log_file
            plist.append(Popen(cmd, stdout=None, stderr=None, shell=True))
        else:
            p = popenPipe(cmd+' 2>&1 | tee '+log_file)
            p.communicate()
            if p.returncode != 0: PkgError = True
    os.chdir(curr_dir)
    if RunBackground: waitBackgroundProcess(plist)


def packFlash(package, platforms):
    if not os.access(ScriptDir+'/PkgFlash', os.X_OK): return
    global PkgError
    plist = []
    result_dir = BaseDir+'/result_spk'+resolveDirSuffix()
    for arch in platforms:
        arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
        log_file = arch_dir+'/logs.flash'
        cmd = ScriptDir+'/PkgFlash '+arch+' '+package+' '+result_dir+' '+arch_dir
        reportMessage(ERROR_LOG, cmd)
        if RunBackground:
            cmd += ' 2>&1 > '+log_file
            plist.append(Popen(cmd, stdout=None, stderr=None, shell=True))
        else:
            p = popenPipe(cmd+' 2>&1 | tee '+log_file)
            p.communicate()
            if p.returncode != 0: PkgError = True
    if RunBackground: waitBackgroundProcess(plist)

def sendReleaseMail(package, info):
    cmd = ScriptDir+'/ReleaseMail.php'
    if not os.access(cmd, os.X_OK): return
    version = info['version']
    try:
        build_num = version.split('-')[-1]
        cmd += ' '+build_num+' '+package
    except IndexError:
        reportMessage(ERROR_LOG, 'Fail to get build number from "'+version+'", use it directly to send relase mail.')
        cmd += ' '+version+' '+package
    reportMessage(ERROR_DEBUG, cmd)
    try: check_call(cmd, shell=True)
    except CalledProcessError: pass

def createGitTag(package, platforms, info):
    cmd = ScriptDir+'/PkgTag.py'
    if not os.access(cmd, os.X_OK): return
    name = info['package']
    version = info['version']

    # Add tag
    tag_name = name+'-'+version+'-'+strftime('%y%m%d', localtime())
    tag_opt = '-y -p "'+string.join(platforms, ' ')+'"'
    if EnvTag != '': tag_opt += ' -e '+EnvTag
    if EnvSuffix != '': tag_opt += ' -s '+EnvSuffix
    if pythonutils.ENABLE_DEBUG: tag_opt += ' --debug'
    if DoBase: tag_opt += ' --base'
    cmd += ' '+tag_opt+' '+tag_name+' '+package
    reportMessage(ERROR_LOG, cmd)
    try: check_call(cmd, shell=True)
    except CalledProcessError: pass

    # Commit uistring
    cmd = 'cd '+BaseDir+'/source/uistring;'
    cmd += 'git add .;'
    cmd += 'git commit -m "'+name+' '+version+'. Committed through '+ScriptName+'.";'
    cmd += 'git push;'
    reportMessage(ERROR_DEBUG, cmd)
    try: check_call(cmd, shell=True)
    except CalledProcessError: pass

def signPackage(arch, pattern):
    global PkgError
    major_ver, minor_ver = getEnvVer(arch, DictEnv)
    major_ver = int(major_ver)
    minor_ver = int(minor_ver)
    arch_dir = EnvDir + '/' + getArchDir(arch, DictEnv)
    spk_dir = '/image/packages/'
    src_dir = arch_dir + spk_dir

    if major_ver < 5:
        return
    if not os.path.isdir(arch_dir):
        return
    for spk in os.listdir(src_dir):
        if not re.match(pattern, spk):
            continue
        cmd = 'chroot ' + arch_dir + ' php ' + PkgScripts + '/CodeSign.php --sign=' + spk_dir + spk
        try: check_call(cmd, shell = True)
        except CalledProcessError:
            PkgError = True
            reportMessage(ERROR_LOG, 'Failed to create signature: ' + spk)

def collectPackage(package, do_sign, milestone=None):
    global PkgError
    global FlashFail
    supported_platforms = []
    for arch in Platforms:
        arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
        if os.path.isfile(arch_dir+'/source/'+package+'/INFO'):
            supported_platforms.append(arch)
    if len(supported_platforms) == 0:
        reportMessage(ERROR_LOG, 'No INFO file found!')
        return

    info = readPackageInfo(EnvDir+'/'+getArchDir(supported_platforms[0], DictEnv)+'/source/'+package+'/INFO')
    package_id = info['package']
    name = package_id
    version = info['version']

    # read setting file
    settings = readPackageSetting(EnvDir+'/'+getArchDir(supported_platforms[0], DictEnv)+'/source/'+package+'/SynoBuildConf/settings', package)
    if "pkg_name" in settings:
        name = settings["pkg_name"][0]

    pattern = name + '.*' + version + '.*spk$'

    result_dir = 'result_spk'+resolveDirSuffix()
    dst_dir = BaseDir+'/'+result_dir+'/'+name+'-'+version
    if os.path.exists(dst_dir):
        rename_dir = dst_dir+'.bad.'+strftime('%Y%m%d-%H%M', localtime())
        if os.path.isdir(rename_dir):
            rmtree(rename_dir)
        os.rename(dst_dir, rename_dir)
    os.makedirs(dst_dir)
    for arch in supported_platforms:
        arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
        src_dir = arch_dir + '/image/packages/'

        if do_sign:
            signPackage(arch, pattern)

        hook = arch_dir+'/source/'+package+'/SynoBuildConf/collect'
        hook_env = {'SPK_SRC_DIR': src_dir, 'SPK_DST_DIR': dst_dir, 'SPK_VERSION': version}
        if os.path.isfile(hook):
            if not os.access(hook, os.X_OK):
                reportMessage(ERROR_LOG, hook+' not executable. Ignore it.')
            else:
                pipe = Popen(hook, shell=True, stdout=None, stderr=None, env=hook_env)
                pipe.communicate()
                if pipe.returncode != 0: PkgError = True
                continue
        info = readPackageInfo(arch_dir+'/source/'+package+'/INFO')
        src_files = src_dir+name+'*-'+version+'*.spk'
        try: check_call('mv '+src_files+' '+dst_dir+'/', shell=True)
        except CalledProcessError: reportMessage(ERROR_LOG, 'Fail to mv '+src_files)
    if PkgError: FlashFail = True

    if not PkgError and os.access(ScriptDir+'/PkgImage', os.X_OK):
        upload_opt = '--suffix '+EnvSuffix if EnvSuffix != '' else ''
        if milestone != None: upload_opt += ' --milestone "'+BaseDir+'/source/'+package+'/SynoBuildConf/milestone:'+milestone+'"'
        if DemoMode: upload_opt += ' --demo'
        log_file = BaseDir+'/logs/error.upload'
        if os.path.isfile(log_file): os.rename(log_file, log_file+'.old')
        cmd = ScriptDir+'/PkgImage '+upload_opt+' '+version+' '+name+' 2>&1 | tee '+log_file
        reportMessage(ERROR_DEBUG, cmd)
        try: check_call(cmd, shell=True)
        except CalledProcessError: PkgError = True
    if not PkgError and not DemoMode:
        createGitTag(package, supported_platforms, info)
        if DoSendMail: sendReleaseMail(package, info)
    return


def resolveSettings():
    global EnvDir
    EnvDir = BaseDir+'/build_env'+resolveDirSuffix()
    if not os.path.isdir(EnvDir):
        reportMessage(ERROR_ARG, 'Target folder '+EnvDir+' not found.')
    reportMessage(ERROR_LOG, 'Check available platforms under '+EnvDir)

    if not Platforms :
        Platforms.extend(detectPlatforms(EnvDir, DictEnv))
    else:
        for arch in Platforms:
            arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
            if not os.path.isdir(arch_dir):
                reportMessage(ERROR_ARG, 'Platform '+arch+'('+arch_dir+') not exist in '+EnvDir)
    for arch in ExcludedPlatforms:
        try: Platforms.remove(arch)
        except: pass
    if len(Platforms) == 0:
        reportMessage(ERROR_ARG, 'No existing platform specified')

    # Check whether chroot is ready
    for arch in Platforms:
        arch_dir = EnvDir+'/'+getArchDir(arch, DictEnv)
        check_call('cp -f /etc/resolv.conf '+arch_dir+'/etc/', stderr=None, shell=True)
        check_call('cp -f /etc/hosts '+arch_dir+'/etc/', stderr=None, shell=True)
        try: check_call('chroot '+arch_dir+' echo -n ""', stderr=None, shell=True)
        except CalledProcessError: reportMessage(ERROR_ARG, 'Environment for '+arch+'('+arch_dir+') is not ready')

if __name__ == '__main__':
    RunBackground = False
    DoBase = False
    IgnoreBuiltin = True
    DoUpdate = DoLink = DoBuild = DoSign = True
    DoInstall = DoUpload = False
    DoSendMail = False
    DoUpdateCheck = False
    DemoMode = False
    Milestone = None
    BuildFail = InstallFail = FlashFail = PkgError = False
    Branch = 'master'
    Platforms = []
    ExcludedPlatforms = []
    EnvSuffix = ''
    EnvTag = ''
    EnvVer = ''
    SynoUpdateOpt = ''
    SynoBuildOpt = ''
    ProjDependsOpt = ''
    UpdateLog = 'logs/error.update'

    # Parse options
    Date0 = time()
    LongOptions = ['base', 'no-builtin', 'help', 'debug', 'demo', 'ccache-size=', 'ccache-clean', 'no-sign']
    try:
        DictOpt, ListArg = getopt(sys.argv[1:], 'p:P:e:v:b:x:zs:j:m:JIicULlBSuh', LongOptions)
    except GetoptError:
        displayUsage(ERROR_ARG)
    for opt, arg in DictOpt:
        if opt == '-p': Platforms = arg.split(' ')
        if opt == '-P': ExcludedPlatforms = arg.split(' ')
        if opt == '-e': EnvTag = arg
        if opt == '-v': EnvVer = arg
        if opt == '-b': Branch = arg
        if opt == '-x':
            if re.match(r'^[0-9]+$', arg): ProjDependsOpt = '-x'+arg
            else: reportMessage(ERROR_ARG, 'Invalid dependency level "'+arg+'"')
        if opt == '-z': RunBackground = True
        if opt == '-s': EnvSuffix = arg
        if opt == '-j': SynoBuildOpt += ' --jobs '+arg
        if opt == '-J': SynoBuildOpt += ' -J'
        if opt == '-A': SynoBuildOpt += ' --without-ccache'
        if opt == '-I' or opt == '-i':
            DoUpdate = DoLink = DoBuild = False
            DoInstall = True
            DoUpload = True if opt == '-i' else False
        if opt == '-m': Milestone = arg
        if opt == '-c': DoInstall = DoUpload = DoSendMail =  True
        if opt == '-U': DoUpdate = False
        if opt == '-L': DoUpdate = DoLink = False
        if opt == '-l': DoUpdate = DoBuild = False
        if opt == '-B': DoLink = DoBuild = False
        if opt == '-S': SynoBuildOpt += ' -S'
        if opt == '-u': DoUpdateCheck = True
        if opt == '--no-sign':
            DoSign = False
        if opt == '--demo':
            DemoMode = True
            os.environ['SYNO_DEMO_MODE'] = 'Yes'
        if opt == '--base': DoBase = True
        if opt == '--no-builtin':
            DoBase = True
            IgnoreBuiltin = False
            SynoUpdateOpt += ' --no-builtin'
            SynoBuildOpt += ' --no-builtin'
        if opt == '--debug': pythonutils.ENABLE_DEBUG = True
        if opt == '--ccache-size':
            if re.match(r'^[0-9]+(\.[0-9]+)?[KMG]?$', arg): SynoBuildOpt += ' --with-ccache '+arg
            else: reportMessage(ERROR_ARG, 'Invalid ccache size "'+arg+'"')
        if opt == '--ccache-clean': SynoBuildOpt += ' --with-clean-ccache'
        if opt == '-h' or opt == '--help': displayUsage(ERROR_NONE)

    # Get environment
    if DoUpdate: updatePkgScripts()
    if len(ListArg) == 0:
        reportMessage(ERROR_ARG, 'Please specify package project')
    PkgProject = os.path.basename(ListArg[0])
    InputProjects = set(os.path.basename(p) for p in ListArg)
    UpdateScriptExist = True if os.access(ScriptDir+'/SynoUpdate', os.X_OK) else False

    if DoUpdate and UpdateScriptExist:
        if os.path.isfile(BaseDir+'/'+UpdateLog):
            os.rename(BaseDir+'/'+UpdateLog, BaseDir+'/'+UpdateLog+'.old')
        updateProject(BasicProjects, 'master')
        updateProject(InputProjects, Branch)
    DictEnv = getBaseEnvironment(BaseDir, PkgProject, EnvTag, EnvVer)
    resolveSettings()

    if Milestone != None:
        milestone_file = BaseDir+'/source/'+PkgProject+'/SynoBuildConf/milestone'
        if not os.path.isfile(milestone_file):
            reportMessage(ERROR_ARG, '"'+milestone_file+'" not exist')
        try: check_call(ScriptDir+'/include/check CheckMileStone '+milestone_file+ ' "'+Milestone+'"', shell=True)
        except CalledProcessError: reportMessage(ERROR_ARG, 'Milestone "'+Milestone+'" not found')

    # Update, link and build
    if DoUpdate or DoLink or DoBuild:
        ProjectList = {}
        for arch in Platforms:
            hook = UpdateHook(arch, Branch, '', DoBase) if UpdateScriptExist and DoUpdate else None
            if UpdateScriptExist and DoUpdate: writeUpdateLog('\n\n==== Updating for '+arch+' ====\n\n')
            resolveBuildEnvPre(arch)
            Seen, RefOnly, ForPack = traverseDependProjects(InputProjects, arch, DictEnv, ScriptDir, DoBase, False, hook)
            resolveBuildEnvPost(arch, Seen['base'], RefOnly['base'])
            ProjectList[arch] = prepareProjects(arch)
        if DoLink: SynoBuildOpt += ' --dontask'
        else: SynoBuildOpt += ' --noclean'
        DateBuild0 = time()
        if DoBuild: buildPackage(PkgProject, ProjectList, SynoBuildOpt)
        if PkgError: BuildFail = True
        DateBuild1 = time()

    # Install, collect spk
    DateInstall0 = time()
    if not PkgError and DoInstall:
        installPackage(PkgProject, True)
        if not PkgError: installPackage(PkgProject, False)
        if not PkgError: collectPackage(PkgProject, DoSign, Milestone)
    DateInstall1 = time()

    # Show time consumption
    print ''
    if DoBuild: showTimeCost(DateBuild0, DateBuild1, 'Build')
    if DoInstall: showTimeCost(DateInstall0, DateInstall1, 'Install')
    print '\n['+ctime()+'] '+ScriptName+' Finish\n'
    Date1 = time()
    showTimeCost(Date0, Date1, ScriptName)

    # Report
    if PkgError:
        log_msg = '!\nPlease check '+EnvDir+'/ds.{'+string.join(Platforms, ',')+'}/'
        err_msg = 'Some error(s) happened!'
        if BuildFail: err_msg += log_msg+'logs.build'
        if InstallFail: err_msg += log_msg+'logs.install'
        if FlashFail: err_msg += log_msg+'logs.flash'
        reportMessage(ERROR_OTHER, err_msg)  # Exit
    sys.exit(ERROR_NONE)
