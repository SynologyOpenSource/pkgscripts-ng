# Synology package toolkit framework

## Prepare Build Environment
You can download and set up pre-built environments by using **EnvDeploy **as follows. Use -v to specify DSM version and -p to specify desired platform.
If -p is not given, all available platforms for given version will be set up.

```
cd /toolkit/pkgscripts
./EnvDeploy -v 6.0 -p x64 # for example
```

Finally, the whole working directory will look like the following figure,
and **ds.${platform}-${version}** is the chroot environment to build your own projects.

```
toolkit/
├── pkgscripts/
└── build_env/
    ├── ds.${platform}-${version}/
    ├── ...
    └── ds.${platform}-${version}/

```

### Available Platforms
You can use one of following commands to show available platforms. If -v is not given, available platforms for all versions are listed.

```
./EnvDeploy -v {version} --list
./EnvDeploy -v {version} --info platform
```

### Update Environment
Use EnvDeploy again to update your environments. For example, update x64 for DSM {{ book.ToolkitVersion }} by following command.
```
./EnvDeploy -v {version} -p x64
```

### Remove Environment
Remove a building environment is very easy. First chroot to the building environment, umount the **/proc** folder and exit chroot. 
After that, remove the building environment folder. The following command illustrate how to remove a building environment with version 5.2 and platform x64.

```
chroot /toolkit/build_env/ds.x64-{version} umount /proc
rm -rf /toolkit/build_env/ds.x64-{version}
```
