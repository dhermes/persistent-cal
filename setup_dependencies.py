import os
import subprocess
import sys


LIB_DIRS = ('apiclient', 'httplib2', 'oauth2client', 'uritemplate',
            'pytz', 'icalendar')
directory_missing = False
for directory in LIB_DIRS:
  if not os.path.isdir(directory):
    directory_missing = True
    break

if not directory_missing:
  print 'All dependencies already downloaded. Doing nothing and exiting.'
  sys.exit(0)


GOOGLE_API_CLIENT_ZIP = ('https://google-api-python-client.googlecode.com'
                         '/files/google-api-python-client-gae-1.2.zip')
GOOGLE_API_CLIENT_FILENAME = os.path.split(GOOGLE_API_CLIENT_ZIP)[-1]

PYTZ_ZIP = ('https://pypi.python.org/packages/source/g/gaepytz/'
            'gaepytz-2011h.zip#md5=0f130ef491509775b5ed8c5f62bf66fb')
PYTZ_FILENAME = 'gaepytz-2011h.zip'
PYTZ_SUBDIR = 'gaepytz-2011h/pytz'
PYTZ_MAINDIR = 'gaepytz-2011h/'
PYTZ_CODE_DIR = 'pytz'

ICALENDAR_ZIP = ('https://pypi.python.org/packages/source/i/icalendar/'
                 'icalendar-3.6.2.zip#md5=e815c0bbef1097713555925235af0630')
ICALENDAR_FILENAME = 'icalendar-3.6.2.zip'
ICALENDAR_SUBDIR = 'icalendar-3.6.2/src/icalendar'
ICALENDAR_MAINDIR = 'icalendar-3.6.2/'
ICALENDAR_CODE_DIR = 'icalendar'


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
print 'Removing existing gae-pytz code'
subprocess.call(['rm', '-fr', PYTZ_CODE_DIR])
print 'Moving library to project root'
subprocess.call(['mv', PYTZ_SUBDIR, GIT_ROOT])
print 'Removing gae-pytz unused files'
subprocess.call(['rm', '-fr', PYTZ_MAINDIR])
print 'Removing gae-pytz library zip'
subprocess.call(['rm', '-f', PYTZ_FILENAME])

print '=' * 60

print 'Downloading icalendar library'
subprocess.call(['wget', ICALENDAR_ZIP])
print 'Unzipping icalendar library'
subprocess.call(['unzip', '-oq', ICALENDAR_FILENAME])

print 'Removing existing icalendar code'
subprocess.call(['rm', '-fr', ICALENDAR_CODE_DIR])

print 'Moving library to project root'
subprocess.call(['mv', ICALENDAR_SUBDIR, GIT_ROOT])
print 'Removing icalendar unused files'
subprocess.call(['rm', '-fr', ICALENDAR_MAINDIR])
print 'Removing icalendar library zip'
subprocess.call(['rm', '-f', ICALENDAR_FILENAME])

print '=' * 60

print 'Updating iCal with App Engine specific hacks'
subprocess.call(['git', 'apply', 'ical.patch'])
