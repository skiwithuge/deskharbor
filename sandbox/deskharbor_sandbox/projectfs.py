"""Live project access through a filename-filtered FUSE view.

All backing paths are opened relative to directory descriptors. Symlinks are
returned to the FUSE client as checked relative links, never followed by host
file operations. Hardlinked regular files and host sockets/devices are refused.
"""
import argparse
import errno
import fnmatch
import os
from pathlib import Path, PurePosixPath
import stat

from fuse import FUSE, FuseOSError, Operations


class ProjectFS(Operations):
    def __init__(self, root, hidden=()):
        self.root = Path(root).resolve(strict=True)
        self.root_fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.hidden = tuple(self.parts('/' + p) for p in hidden)
        self.handles = {}

    @staticmethod
    def parts(path):
        parts = PurePosixPath(path).parts
        if not path.startswith('/') or '..' in parts or '\x00' in path:
            raise FuseOSError(errno.EACCES)
        return tuple(p for p in parts if p not in ('/', '.'))

    def allowed(self, parts):
        for part in parts:
            if (part == '.env' or fnmatch.fnmatchcase(part, '.env.*')
                    or part in ('.ssh', '.aws', '.azure', '.gnupg', 'secrets')
                    or fnmatch.fnmatchcase(part, '*.pem')
                    or fnmatch.fnmatchcase(part, '*.key')):
                raise FuseOSError(errno.EACCES)
        if any(parts[:len(p)] == p for p in self.hidden):
            raise FuseOSError(errno.EACCES)

    def parent(self, path):
        parts = self.parts(path)
        self.allowed(parts)
        fd = os.dup(self.root_fd)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                                  | os.O_CLOEXEC, dir_fd=fd)
                os.close(fd)
                fd = next_fd
            self.check_location(fd)
            return fd, parts[-1] if parts else '.'
        except BaseException:
            os.close(fd)
            raise

    def check_location(self, fd):
        # Recheck descriptors after host-side renames and before every read/write.
        path = os.readlink(f'/proc/self/fd/{fd}')
        if path.endswith(' (deleted)'):
            raise FuseOSError(errno.ESTALE)
        try:
            relative = Path(path).relative_to(self.root)
        except ValueError:
            raise FuseOSError(errno.EACCES)
        self.allowed(relative.parts)
        st = os.fstat(fd)
        if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
            raise FuseOSError(errno.EACCES)
        return st

    def check_type(self, st):
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)
                or stat.S_ISLNK(st.st_mode)):
            raise FuseOSError(errno.EACCES)
        if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
            raise FuseOSError(errno.EACCES)

    def getattr(self, path, fh=None):
        if fh is not None:
            st = self.check_location(fh)
        else:
            fd, leaf = self.parent(path)
            try:
                st = os.stat(leaf, dir_fd=fd, follow_symlinks=False)
            finally:
                os.close(fd)
        self.check_type(st)
        result = {k: getattr(st, k) for k in ('st_atime', 'st_mtime', 'st_ctime',
                   'st_mode', 'st_nlink', 'st_size', 'st_uid', 'st_gid')}
        result['st_mode'] &= ~(stat.S_ISUID | stat.S_ISGID)
        return result

    def readdir(self, path, fh):
        fd, leaf = self.parent(path)
        try:
            directory = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                                | os.O_CLOEXEC, dir_fd=fd)
        finally:
            os.close(fd)
        try:
            self.check_location(directory)
            result = ['.', '..']
            for name in os.listdir(directory):
                try:
                    self.allowed(self.parts(path) + (name,))
                    self.check_type(os.stat(name, dir_fd=directory, follow_symlinks=False))
                except (OSError, FuseOSError):
                    continue
                result.append(name)
            return result
        finally:
            os.close(directory)

    def open(self, path, flags):
        fd, leaf = self.parent(path)
        try:
            handle = os.open(leaf, (flags & ~os.O_TRUNC) | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            try:
                st = self.check_location(handle)
                if not stat.S_ISREG(st.st_mode):
                    raise FuseOSError(errno.EACCES)
                if flags & os.O_TRUNC:
                    os.ftruncate(handle, 0)
                self.handles[handle] = path
                return handle
            except BaseException:
                os.close(handle)
                raise
        finally:
            os.close(fd)

    def create(self, path, mode, fi=None):
        fd, leaf = self.parent(path)
        try:
            handle = os.open(leaf, os.O_RDWR | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW | os.O_CLOEXEC, mode & 0o777, dir_fd=fd)
            self.handles[handle] = path
            return handle
        finally:
            os.close(fd)

    def read(self, path, size, offset, fh):
        self.check_location(fh)
        return os.pread(fh, size, offset)

    def write(self, path, data, offset, fh):
        self.check_location(fh)
        return os.pwrite(fh, data, offset)

    def release(self, path, fh):
        self.handles.pop(fh, None)
        os.close(fh)
        return 0

    def flush(self, path, fh):
        self.check_location(fh)
        os.fsync(fh)
        return 0

    def fsync(self, path, datasync, fh):
        return self.flush(path, fh)

    def truncate(self, path, length, fh=None):
        owned = fh is None
        if owned:
            fh = self.open(path, os.O_WRONLY)
        try:
            self.check_location(fh)
            os.ftruncate(fh, length)
        finally:
            if owned:
                self.release(path, fh)
        return 0

    def mkdir(self, path, mode):
        fd, leaf = self.parent(path)
        try:
            os.mkdir(leaf, mode & 0o777, dir_fd=fd)
        finally:
            os.close(fd)
        return 0

    def unlink(self, path):
        fd, leaf = self.parent(path)
        try:
            os.unlink(leaf, dir_fd=fd)
        finally:
            os.close(fd)
        return 0

    def rmdir(self, path):
        fd, leaf = self.parent(path)
        try:
            os.rmdir(leaf, dir_fd=fd)
        finally:
            os.close(fd)
        return 0

    def rename(self, old, new):
        old_parts = self.parts(old)
        if any(p[:len(old_parts)] == old_parts for p in self.hidden):
            raise FuseOSError(errno.EACCES)
        old_fd, old_leaf = self.parent(old)
        try:
            new_fd, new_leaf = self.parent(new)
            try:
                os.rename(old_leaf, new_leaf, src_dir_fd=old_fd, dst_dir_fd=new_fd)
            finally:
                os.close(new_fd)
        finally:
            os.close(old_fd)
        return 0

    def checked_link(self, path, target):
        # FUSE resolves links inside /project. Rewrite internal absolute links;
        # reject escape links, secret links and magic links rather than following.
        parent = self.root.joinpath(*self.parts(path)).parent
        resolved = (parent / target).resolve(strict=False)
        try:
            relative = resolved.relative_to(self.root)
        except ValueError:
            raise FuseOSError(errno.EACCES)
        self.allowed(relative.parts)
        return os.path.relpath(resolved, parent)

    def readlink(self, path):
        fd, leaf = self.parent(path)
        try:
            target = os.readlink(leaf, dir_fd=fd)
        finally:
            os.close(fd)
        return self.checked_link(path, target)

    def symlink(self, target, source):
        self.checked_link(target, source)
        fd, leaf = self.parent(target)
        try:
            os.symlink(source, leaf, dir_fd=fd)
        finally:
            os.close(fd)
        return 0

    def link(self, target, source):
        raise FuseOSError(errno.EPERM)

    def mknod(self, path, mode, dev):
        raise FuseOSError(errno.EPERM)

    def chmod(self, path, mode):
        fh = self.open(path, os.O_RDONLY) if not stat.S_ISDIR(self.getattr(path)['st_mode']) else None
        if fh is not None:
            try:
                os.fchmod(fh, mode & 0o777)
            finally:
                self.release(path, fh)
        else:
            fd, leaf = self.parent(path)
            try:
                directory = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    self.check_location(directory)
                    os.fchmod(directory, mode & 0o777)
                finally:
                    os.close(directory)
            finally:
                os.close(fd)
        return 0

    def chown(self, path, uid, gid):
        if uid not in (-1, os.getuid()) or gid not in (-1, os.getgid()):
            raise FuseOSError(errno.EPERM)
        self.getattr(path)
        return 0

    def utimens(self, path, times=None):
        fd, leaf = self.parent(path)
        try:
            os.utime(leaf, times, dir_fd=fd, follow_symlinks=False)
        finally:
            os.close(fd)
        return 0

    def statfs(self, path):
        st = os.fstatvfs(self.root_fd)
        return {k: getattr(st, k) for k in ('f_bavail', 'f_bfree', 'f_blocks',
                'f_bsize', 'f_favail', 'f_ffree', 'f_files', 'f_frsize', 'f_namemax')}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('mountpoint')
    parser.add_argument('--hide', action='append', default=[])
    parser.add_argument('--allow-other', action='store_true')
    args = parser.parse_args()
    fs = ProjectFS(args.root, args.hide)
    FUSE(fs, args.mountpoint, foreground=True, nothreads=True,
         allow_other=args.allow_other, default_permissions=True,
         entry_timeout=0, attr_timeout=0, negative_timeout=0,
         direct_io=True, fsname='deskharbor-project', nosuid=True, nodev=True)


if __name__ == '__main__':
    main()
