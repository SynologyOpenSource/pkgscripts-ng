import os
import subprocess


class Chroot:
    def umount(self):
        try:
            subprocess.check_call(['umount', os.path.join(self.chroot, 'proc')])
        except subprocess.CalledProcessError:
            pass

    def mount(self):
        try:
            mount_point = os.path.join(self.chroot, 'proc')
            if not os.path.ismount(mount_point):
                subprocess.check_call(['mount', '-t', 'proc', 'none', mount_point])
        except subprocess.CalledProcessError:
            pass

    def __init__(self, path):
        self.chroot = path
        self.orig_fd = os.open("/", os.O_RDONLY)
        self.chroot_fd = os.open(self.chroot, os.O_RDONLY)

    def __enter__(self):
        self.mount()
        os.chroot(self.chroot)
        os.fchdir(self.chroot_fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.fchdir(self.orig_fd)
        os.chroot(".")
        os.close(self.orig_fd)
        os.close(self.chroot_fd)
        self.umount()

    def get_outside_path(self, path):
        return self.chroot + "/" + path

    def get_inside_path(self, path):
        return path.replace(self.chroot, "")
