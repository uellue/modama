import pytest

import os
import subprocess
import warnings
from importlib import reload

import xdg

# Import crawler classes
import modama_crawler.recognition


# MIME for self test
CANARY_MIME = xdg.Mime.MIMEtype('application', 'x.modamatestfile')


# File handler for self test
class Canary(modama_crawler.recognition.BaseFileHandler):
    file_types = (CANARY_MIME, )

    @staticmethod
    def xdg_mimeinfo():
        return """<?xml version="1.0"?>
<mime-info xmlns='http://www.freedesktop.org/standards/shared-mime-info'>
<mime-type type="application/x.modamatestfile">
  <comment>Canary file type to test database installation effect</comment>
  <glob pattern="*.modamatestfile"/>
</mime-type>
</mime-info>
"""


@pytest.fixture(scope='session', autouse=True)
def install_handlers(tmp_path_factory):
    handlers = modama_crawler.recognition.FileHandler.handlers()
    workdir = tmp_path_factory.mktemp('localshare')
    os.environ['XDG_DATA_HOME'] = str(workdir)
    # Make the new base directory active
    reload(xdg.BaseDirectory)
    mimedir = workdir / 'mime'
    mimepackages = mimedir / 'packages'
    mimepackages.mkdir(parents=True)

    names = set()
    for handler in handlers:
        name = handler.__name__
        while name in names:
            name = name + '-alt'
        names.add(name)
        filename = name + '.xml'
        mimeinfo = handler.xdg_mimeinfo()
        if mimeinfo:
            (mimepackages / filename).write_text(handler.xdg_mimeinfo())
    assert Canary.__name__ in names
    command = 'update-mime-database'

    res = subprocess.run(
        (command, str(mimedir)),
        # 'XDG_DATA_HOME' already updated
        env=os.environ,
        check=False,
        capture_output=True
    )
    if res.stderr or res.stdout:
        warnings.warn(res.stderr.decode('utf-8') + '\n' + res.stdout.decode('utf-8'))
    res.check_returncode()

    # Force reload of database cache
    xdg.Mime._cache_uptodate = False
    xdg.Mime.update_cache()
    # Self-test: Make sure the MIME definition installation worked
    assert xdg.Mime.get_type_by_name('/home/whatever.modamatestfile') == CANARY_MIME
