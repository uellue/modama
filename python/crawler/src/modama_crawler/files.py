"""Opening a file of the tree for reading: never through a symlink, never anything but a regular file.

A folder's listing says what an entry was; by the time a format reads it,
it may have become a symlink (to anything) or a FIFO (which would block an
open). So every read of a file's content opens it without following a
symlink and without blocking, and reads only if the descriptor is a regular
file (change hdf5-links, design D5; review of hdf5-links, MUST 4).
"""

import errno
import io
import os
import stat

# Without following a symlink, without blocking on a FIFO, without making a
# terminal the process's controlling one
FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_NOCTTY


class NotRegular(OSError):
    """The entry is no longer a regular file: a symlink (ELOOP) or a FIFO, device or folder."""

    def __init__(self, path: str, what: str):
        super().__init__(errno.ELOOP, f"not a regular file ({what})", path)


def regular(path: str) -> int:
    """A descriptor of the regular file at path, opened for reading; raises NotRegular otherwise."""
    try:
        fd = os.open(path, FLAGS)
    except OSError as e:
        if e.errno == errno.ELOOP:
            raise NotRegular(path, "a symlink") from None
        raise
    try:
        mode = os.fstat(fd).st_mode
    except BaseException:
        os.close(fd)
        raise
    if not stat.S_ISREG(mode):
        os.close(fd)
        raise NotRegular(path, stat.filemode(mode))
    return fd


class BudgetExceeded(OSError):
    """A read past a file's byte budget (a format's read limit per file).

    An OSError, so that a format skips the file as one it cannot read, and
    goes on with its other files (change read-limit-per-file).
    """


class Counted(io.RawIOBase):
    """A read-only, unbuffered file object of a descriptor that counts the bytes read.

    With a budget, a read that would go past it raises BudgetExceeded, and so
    does every read after it (review of hdf5-links, S12), even when a library
    caught the first error and went on. An OSError of a read is kept in
    `error`, for the caller to tell a read the file system did not answer
    from what a library made of it. Readahead is off: the readers it serves
    (h5py) seek between small pieces (crawler README, "Pitfalls", F14). It
    owns the descriptor and closes it.
    """

    def __init__(self, fd: int, budget: int | None = None, name: str = ""):
        super().__init__()
        self._fd = fd
        self._pos = 0
        self.name = name
        self.budget = budget
        self.read_bytes = 0
        self.over = False
        self.error: OSError | None = None
        if hasattr(os, "posix_fadvise"):
            try:
                os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_RANDOM)
            except OSError:
                pass  # a file system that refuses the advice is still read

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def fileno(self) -> int:
        return self._fd

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        if whence == io.SEEK_SET:
            pos = offset
        elif whence == io.SEEK_CUR:
            pos = self._pos + offset
        elif whence == io.SEEK_END:
            pos = os.fstat(self._fd).st_size + offset
        else:
            raise ValueError(f"invalid whence {whence}")
        if pos < 0:
            raise ValueError("negative seek position")
        self._pos = pos
        return pos

    def readinto(self, buffer) -> int:
        n = len(buffer)
        if self.over or (self.budget is not None and self.read_bytes + n > self.budget):
            self.over = True
            raise BudgetExceeded(
                f"reading {n} bytes of {self.name or 'a file'} at {self._pos} "
                f"exceeds its budget of {self.budget} bytes"
            )
        try:
            data = os.pread(self._fd, n, self._pos)
        except OSError as e:
            self.error = self.error or e
            raise
        got = len(data)
        buffer[:got] = data
        self._pos += got
        self.read_bytes += got
        return got

    def close(self) -> None:
        if not self.closed:
            try:
                os.close(self._fd)
            finally:
                super().close()
