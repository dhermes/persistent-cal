import os
import subprocess
import sys


GOOGLE_API_CLIENT_ZIP = ('https://google-api-python-client.googlecode.com'
                         '/files/google-api-python-client-gae-1.2.zip')
GOOGLE_API_CLIENT_FILENAME = os.path.split(GOOGLE_API_CLIENT_ZIP)[-1]

PYTZ_ZIP = ('https://pypi.python.org/packages/source/g/gaepytz/'
            'gaepytz-2011h.zip#md5=0f130ef491509775b5ed8c5f62bf66fb')
PYTZ_FILENAME = 'gaepytz-2011h.zip'
PYTZ_SUBDIR = 'gaepytz-2011h/pytz'
PYTZ_MAINDIR = 'gaepytz-2011h/'


def get_git_root():
  """Retrieves the current root of the git repository.

  Returns:
    String containing the current git root, if in a repository.
  """
  return subprocess.check_output(
      ['git', 'rev-parse', '--show-toplevel']).strip()


GIT_ROOT = get_git_root()
print 'Changing directory to', GIT_ROOT
os.chdir(GIT_ROOT)

print '=' * 60

if os.path.exists(GOOGLE_API_CLIENT_FILENAME):
  print 'google-api-python-client file already exists, please remove'
  sys.exit(1)

print 'Downloading google-api-python-client library'
subprocess.call(['wget', GOOGLE_API_CLIENT_ZIP])
print 'Unzipping google-api-python-client library'
subprocess.call(['unzip', '-oq', GOOGLE_API_CLIENT_FILENAME])
print 'Removing google-api-python-client library zip'
subprocess.call(['rm', '-f', GOOGLE_API_CLIENT_FILENAME])

print '=' * 60

if os.path.exists(PYTZ_FILENAME):
  print 'gae-pytz file already exists, please remove'
  sys.exit(1)

print 'Downloading gae-pytz library'
subprocess.call(['wget', PYTZ_ZIP])
print 'Unzipping gae-pytz library'
subprocess.call(['unzip', '-oq', PYTZ_FILENAME])
print 'Moving library to project root'
subprocess.call(['mv', PYTZ_SUBDIR, GIT_ROOT])
print 'Removing gae-pytz unused files'
subprocess.call(['rm', '-fr', PYTZ_MAINDIR])
print 'Removing gae-pytz library zip'
subprocess.call(['rm', '-f', PYTZ_FILENAME])
