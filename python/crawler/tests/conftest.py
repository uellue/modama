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
        return """
<mime-type type="application/x.modamatestfile">
  <comment>Canary file type to test database installation effect</comment>
  <glob pattern="*.modamatestfile"/>
</mime-type>
"""


@pytest.fixture(scope='session', autouse=True)
def install_handlers(tmp_path_factory):
    workdir = tmp_path_factory.mktemp('localshare')
    os.environ['XDG_DATA_HOME'] = str(workdir)
    # Make the new base directory active
    reload(xdg.BaseDirectory)
    modama_crawler.recognition.FileHandler.install_mime_info()
    # Self-test: Make sure the MIME definition installation worked
    assert xdg.Mime.get_type_by_name('/home/whatever.modamatestfile') == CANARY_MIME
