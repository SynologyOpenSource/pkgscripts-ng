# Synology package toolkit framework


| :exclamation:  This toolkit is only for DSM7.0. If you need toolkit before 7.0, please checkout to other branches.  |
|-----------------------------------------|


## Prepare Build Environment
You can download and set up pre-built environments by using **EnvDeploy** as follows. Use -v to specify DSM version and -p to specify desired platform.
If -p is not given, all available platforms for given version will be set up.

```
cd /toolkit/pkgscripts-ng
./EnvDeploy -v 7.0 -p avoton # for example
```

Finally, the whole working directory will look like the following figure,
and **ds.avoton-7.0** is the chroot environment to build your own projects.

```
toolkit/
├── pkgscripts-ng/
└── build_env/
    ├── ...
    └── ds.avoton-7.0/

```

### Available Platforms
You can use one of following commands to show available platforms. If -v is not given, available platforms for all versions are listed.

```
./EnvDeploy -v 7.0 --list
./EnvDeploy -v 7.0 --info platform
```

### Update Environment
Use EnvDeploy again to update your environments. For example, update avoton for DSM {{ book.ToolkitVersion }} by running the following command.
```
./EnvDeploy -v 7.0 -p avoton
```

### Remove Environment
Removing a building environment is very easy. First chroot to the building environment, umount the **/proc** folder and exit chroot.
After that, remove the building environment folder. The following command illustrates how to remove a building environment with version 7.0 and platform avoton.

```
chroot /toolkit/build_env/ds.avoton-7.0 umount /proc
rm -rf /toolkit/build_env/ds.avoton-7.0
```
